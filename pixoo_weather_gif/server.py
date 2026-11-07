"""Serve a live 64x64 weather GIF for the Pixoo, plus a settings page inside Home Assistant."""
import html, io, json, logging, os, threading, time, urllib.parse, urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

import render

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pixoo_weather_gif")

HA_URL = os.environ.get("HA_URL", "http://supervisor/core/api")
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
OPTIONS = os.environ.get("OPTIONS_FILE", "/data/options.json")
SETTINGS = os.environ.get("SETTINGS_FILE", "/data/settings.json")
PORT = int(os.environ.get("PORT", "6943"))
INGRESS_PORT = int(os.environ.get("INGRESS_PORT", "8099"))
# Home Assistant's ingress proxy is the only client allowed to reach the settings page.
INGRESS_ALLOW = set(os.environ.get("INGRESS_ALLOW", "172.30.32.2").split(","))
REFRESH_S = 30  # the Pixoo asks about once a minute; weather never needs fetching more often
DEFAULTS = {"forecast_entity": "", "alerts_entity": "", "show_smiley": False, "precip_threshold": 10,
            "reading": "humidity", "clock_format": "12h", "date_format": "month_day", "alert_style": "blink"}
CHOICES = {  # setting: [(value, label)]; the first is the default
    "reading": [("humidity", "Humidity"), ("feels_like", "Feels like temperature")],
    "clock_format": [("12h", "12-hour (7:22P)"), ("24h", "24-hour (19:22)")],
    "date_format": [("month_day", "Month-day (11-07)"), ("day_month", "Day-month (7-11)")],
    "alert_style": [("blink", "Blinking"), ("solid", "Solid")],
}
DISPLAY = ("show_smiley", "precip_threshold", "reading", "clock_format", "date_format", "alert_style")


def ha(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{HA_URL}/{path}", data=data, headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def load_settings():
    """Defaults, then the app's Configuration tab, then anything saved from the settings page."""
    settings = dict(DEFAULTS)
    for path in (OPTIONS, SETTINGS):
        try:
            with open(path) as f:
                settings.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
        except FileNotFoundError:
            pass
    return settings


def save_settings(settings):
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(settings, f, indent=2)
    os.replace(tmp, SETTINGS)


def fetch_weather(opts, tz):
    """Read Home Assistant into the shape render.py expects. Raises if the data is unusable."""
    entity = opts["forecast_entity"]
    if not entity:
        raise ValueError("no weather entity chosen yet")
    state = ha(f"states/{entity}")
    if state["state"] in ("unavailable", "unknown"):
        raise ValueError(f"{entity} is {state['state']}")
    attrs = state["attributes"]
    response = ha("services/weather/get_forecasts?return_response",
                  {"entity_id": entity, "type": "daily"})
    days = response["service_response"][entity]["forecast"]

    today = datetime.now(tz).date()
    forecast = []
    for d in days:
        local = datetime.fromisoformat(d["datetime"].replace("Z", "+00:00")).astimezone(tz).date()
        if local >= today:
            forecast.append({"date": local.isoformat(), "condition": d.get("condition", "cloudy"),
                             "temperature": d.get("temperature") or 0, "templow": d.get("templow") or 0,
                             "precipitation_probability": d.get("precipitation_probability") or 0})
    if not forecast:
        raise ValueError("no forecast for today onward")

    alerts = 0
    if opts.get("alerts_entity"):
        try:
            alerts = int(float(ha(f"states/{opts['alerts_entity']}")["state"]))
        except (ValueError, OSError) as err:
            log.warning("alerts unavailable: %s", err)
    is_night = False
    try:
        is_night = ha("states/sun.sun")["state"] == "below_horizon"
    except OSError as err:
        log.warning("sun.sun unavailable: %s", err)
    return {"condition": state["state"], "temperature": attrs.get("temperature") or 0,
            "humidity": attrs.get("humidity") or 0, "apparent_temperature": attrs.get("apparent_temperature"),
            "is_night": is_night, "alerts": alerts, "forecast": forecast}


class Weather:
    """Caches weather data. On failure it keeps serving the last good data."""

    def __init__(self, opts, tz):
        self.opts, self.tz = opts, tz
        self.data, self.fetched, self.lock = None, 0.0, threading.Lock()

    def update(self, opts, data=None):
        """Apply new settings now. data, if given, is already fetched for the new settings."""
        with self.lock:
            if data is not None:
                self.data, self.fetched = data, time.monotonic()
            else:
                if opts.get("forecast_entity") != self.opts.get("forecast_entity"):
                    self.data = None
                self.fetched = 0.0
            self.opts = dict(opts)

    def gif(self):
        with self.lock:
            if time.monotonic() - self.fetched >= REFRESH_S or self.data is None:
                try:
                    self.data = fetch_weather(self.opts, self.tz)
                    self.fetched = time.monotonic()
                except Exception as err:  # keep the display alive through any HA hiccup
                    log.warning("weather refresh failed: %s", err)
            if self.data is None:
                return None
            out = io.BytesIO()
            display = {k: self.opts.get(k, DEFAULTS[k]) for k in DISPLAY}
            render.render_gif(dict(self.data, **display), out, now=datetime.now(self.tz))
            return out.getvalue()


def send_gif(handler, weather):
    body = weather.gif()
    if body is None:
        handler.send_error(503, "Weather data not available yet")
        return
    handler.send_response(200)
    handler.send_header("Content-Type", "image/gif")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def make_handler(weather):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] not in ("/", "/weather.gif"):
                self.send_error(404)
                return
            send_gif(self, weather)

        def log_message(self, fmt, *args):
            log.debug(fmt, *args)
    return Handler


# ---- Settings page (served only through Home Assistant ingress) ----

def entity_choices():
    """Weather entities, and sensors that look like alert counts, as (entity_id, name, state)."""
    states = ha("states")
    weather = sorted((s["entity_id"], s["attributes"].get("friendly_name", ""), s["state"])
                     for s in states if s["entity_id"].startswith("weather."))
    alerts = sorted((s["entity_id"], s["attributes"].get("friendly_name", ""), s["state"])
                    for s in states if s["entity_id"].startswith("sensor.")
                    and "alert" in (s["entity_id"] + s["attributes"].get("friendly_name", "")).lower())
    return weather, alerts, {s["entity_id"] for s in states}


def options_html(choices, selected, none_label=None):
    items = [f'<option value=""{" selected" if not selected else ""}>{html.escape(none_label)}</option>'] if none_label else []
    ids = [c[0] for c in choices]
    if selected and selected not in ids:  # keep a saved choice visible even if it no longer matches
        choices = [(selected, "", "not found")] + list(choices)
    for entity_id, name, state in choices:
        label = f"{name} ({entity_id}): {state}" if name else f"{entity_id}: {state}"
        sel = " selected" if entity_id == selected else ""
        items.append(f'<option value="{html.escape(entity_id)}"{sel}>{html.escape(label)}</option>')
    return "\n".join(items)


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pixoo Weather GIF</title>
<style>
:root {{ color-scheme: light dark; --bg: #fafafa; --fg: #1c1c1c; --muted: #666; --card: #fff; --line: #ddd; --accent: #03a9f4; --bad: #c62828; --good: #2e7d32; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #111; --fg: #e8e8e8; --muted: #9a9a9a; --card: #1c1c1c; --line: #333; --bad: #ef5350; --good: #66bb6a; }} }}
body {{ margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.5 system-ui, sans-serif; }}
main {{ max-width: 640px; margin: 0 auto; padding: 24px 16px; }}
h1 {{ font-size: 22px; margin: 0 0 4px; }}
p.sub {{ color: var(--muted); margin: 0 0 20px; }}
.card {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px; margin-bottom: 16px; }}
label {{ display: block; font-weight: 600; margin: 14px 0 4px; }}
label:first-child {{ margin-top: 0; }}
.hint {{ color: var(--muted); font-size: 13px; margin-top: 4px; }}
h2 {{ font-size: 16px; margin: 22px 0 0; padding-top: 14px; border-top: 1px solid var(--line); }}
input[type=number] {{ width: 90px; font: inherit; padding: 8px; border-radius: 8px; border: 1px solid var(--line); background: var(--bg); color: var(--fg); }}
select {{ width: 100%; font: inherit; padding: 8px; border-radius: 8px; border: 1px solid var(--line); background: var(--bg); color: var(--fg); }}
.check {{ display: flex; gap: 10px; align-items: flex-start; font-weight: 600; margin-top: 16px; }}
.check input {{ width: 18px; height: 18px; margin-top: 2px; }}
button {{ font: inherit; font-weight: 600; background: var(--accent); color: #fff; border: 0; border-radius: 8px; padding: 10px 18px; margin-top: 18px; cursor: pointer; }}
.msg {{ border-radius: 8px; padding: 10px 12px; margin-bottom: 16px; border: 1px solid; }}
.msg.ok {{ color: var(--good); }} .msg.err {{ color: var(--bad); }}
.preview {{ display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }}
.preview img {{ width: 256px; max-width: 100%; image-rendering: pixelated; border-radius: 6px; background: #000; }}
code {{ font-size: 13px; }}
</style></head><body><main>
<h1>Pixoo Weather GIF</h1>
<p class="sub">Settings for the weather screen. Changes apply on the Pixoo's next refresh.</p>
{message}
<form class="card" method="post" action="save">
<label for="forecast_entity">Weather entity</label>
<select id="forecast_entity" name="forecast_entity" required>
{weather_options}
</select>
<div class="hint">Provides current conditions and the daily forecast.</div>
<label for="alerts_entity">Weather alerts sensor</label>
<select id="alerts_entity" name="alerts_entity">
{alert_options}
</select>
<div class="hint">A sensor whose state is the number of active alerts. Any number above 0 shows the alert icon.</div>
<h2>Display</h2>
<label for="precip_threshold">Rain and snow threshold (%)</label>
<input type="number" id="precip_threshold" name="precip_threshold" min="1" max="100" step="1" value="{precip_threshold}" required>
<div class="hint">Today's chance of rain or snow is shown at or above this. Foggy days always show FOG.</div>
<div class="check"><input type="checkbox" id="show_smiley" name="show_smiley" value="on"{smiley_checked}>
<label for="show_smiley" style="margin:0">Show a smiley when today's chance is below the threshold</label></div>
<label for="reading">Reading under the temperature</label>
<select id="reading" name="reading">
{reading_options}
</select>
<div class="hint">Feels like uses the weather entity's apparent temperature. Without it, humidity is shown.</div>
<label for="clock_format">Clock</label>
<select id="clock_format" name="clock_format">
{clock_format_options}
</select>
<label for="date_format">Date</label>
<select id="date_format" name="date_format">
{date_format_options}
</select>
<label for="alert_style">Alert icon</label>
<select id="alert_style" name="alert_style">
{alert_style_options}
</select>
<button type="submit">Save</button>
</form>
<div class="card preview">
<img src="preview.gif?t={stamp}" alt="Current weather screen">
<div><strong>Current screen</strong><div class="hint">The GIF is served at <code>http://&lt;home-assistant-ip&gt;:{port}/</code></div></div>
</div>
</main></body></html>"""


def render_page(settings, message="", error=False):
    try:
        weather, alerts, _ = entity_choices()
    except Exception as err:
        weather, alerts = [], []
        message, error = f"Couldn't read entities from Home Assistant: {err}", True
    box = f'<div class="msg {"err" if error else "ok"}">{html.escape(message)}</div>' if message else ""
    return PAGE.format(
        message=box, port=PORT, stamp=int(time.time()),
        weather_options=options_html(weather, settings["forecast_entity"],
                                     None if settings["forecast_entity"] else "Choose a weather entity"),
        alert_options=options_html(alerts, settings["alerts_entity"], "None (no alert icon)"),
        smiley_checked=" checked" if settings["show_smiley"] else "",
        precip_threshold=int(settings["precip_threshold"]),
        **{f"{name}_options": choice_html(name, settings[name]) for name in CHOICES})


def choice_html(name, selected):
    return "\n".join(f'<option value="{v}"{" selected" if v == selected else ""}>{html.escape(label)}</option>'
                     for v, label in CHOICES[name])


def validate(form, tz):
    """Turn a submitted form into (settings, weather data), or raise ValueError with a message for the page.

    The chosen entity's forecast is fetched here, so a setting that can't produce a screen is never saved.
    """
    weather, _, known = entity_choices()
    forecast = form.get("forecast_entity", [""])[0]
    alerts = form.get("alerts_entity", [""])[0]
    if forecast not in {w[0] for w in weather}:
        raise ValueError("Choose a weather entity from the list.")
    if alerts and alerts not in known:
        raise ValueError(f"{alerts} doesn't exist in Home Assistant.")
    try:
        threshold = int(form.get("precip_threshold", [""])[0])
    except ValueError:
        threshold = 0
    if not 1 <= threshold <= 100:
        raise ValueError("The rain and snow threshold must be a whole number from 1 to 100.")
    settings = {"forecast_entity": forecast, "alerts_entity": alerts,
                "show_smiley": form.get("show_smiley", [""])[0] == "on", "precip_threshold": threshold}
    for name, options in CHOICES.items():
        value = form.get(name, [options[0][0]])[0]
        if value not in {v for v, _ in options}:
            raise ValueError(f"Unknown value for {name}: {value}")
        settings[name] = value
    try:
        data = fetch_weather(settings, tz)
    except Exception as err:
        raise ValueError(f"{forecast} didn't return a usable daily forecast ({err}). Settings not saved.")
    return settings, data


def make_settings_handler(weather):
    class Handler(BaseHTTPRequestHandler):
        def allowed(self):
            if self.client_address[0] in INGRESS_ALLOW:
                return True
            log.warning("settings page refused a request from %s", self.client_address[0])
            self.send_error(403)
            return False

        def send_page(self, body, code=200):
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self.allowed():
                return
            path, _, query = self.path.partition("?")
            if path == "/preview.gif":
                send_gif(self, weather)
            elif path == "/":
                saved = "saved=1" in query
                self.send_page(render_page(weather.opts, "Saved." if saved else ""))
            else:
                self.send_error(404)

        def do_POST(self):
            if not self.allowed():
                return
            if self.path.split("?")[0] != "/save":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            form = urllib.parse.parse_qs(self.rfile.read(min(length, 10000)).decode(), keep_blank_values=True)
            try:
                settings, data = validate(form, weather.tz)
            except ValueError as err:
                self.send_page(render_page(weather.opts, str(err), error=True), 400)
                return
            except Exception as err:
                self.send_page(render_page(weather.opts, f"Couldn't check the entities: {err}", error=True), 502)
                return
            try:
                save_settings(settings)
            except OSError as err:
                self.send_page(render_page(weather.opts, f"Couldn't save settings: {err}", error=True), 500)
                return
            weather.update(settings, data)
            log.info("settings saved: %s", settings)
            self.send_response(303)
            self.send_header("Location", "./?saved=1")  # relative, so it stays under the ingress path
            self.end_headers()

        def log_message(self, fmt, *args):
            log.debug(fmt, *args)
    return Handler


def main():
    settings = load_settings()
    while True:  # Home Assistant may still be starting when the app boots
        try:
            tz = ZoneInfo(ha("config")["time_zone"])
            break
        except Exception as err:
            log.info("waiting for Home Assistant: %s", err)
            time.sleep(10)
    weather = Weather(settings, tz)
    log.info("serving %s on port %d, settings page on %d, time zone %s",
             settings["forecast_entity"] or "(no weather entity yet)", PORT, INGRESS_PORT, tz.key)
    settings_server = ThreadingHTTPServer(("", INGRESS_PORT), make_settings_handler(weather))
    threading.Thread(target=settings_server.serve_forever, daemon=True).start()
    ThreadingHTTPServer(("", PORT), make_handler(weather)).serve_forever()


if __name__ == "__main__":
    main()
