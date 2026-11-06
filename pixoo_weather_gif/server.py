"""Serve a live 64x64 weather GIF for the Pixoo, using Home Assistant weather data."""
import io, json, logging, os, threading, time, urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

import render

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pixoo_weather_gif")

HA_URL = os.environ.get("HA_URL", "http://supervisor/core/api")
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
OPTIONS = os.environ.get("OPTIONS_FILE", "/data/options.json")
PORT = int(os.environ.get("PORT", "6943"))
REFRESH_S = 30  # the Pixoo asks about once a minute; weather never needs fetching more often


def ha(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{HA_URL}/{path}", data=data, headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def fetch_weather(opts, tz):
    """Read Home Assistant into the shape render.py expects. Raises if the data is unusable."""
    entity = opts["forecast_entity"]
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
            "humidity": attrs.get("humidity") or 0, "is_night": is_night, "alerts": alerts,
            "forecast": forecast}


class Weather:
    """Caches weather data. On failure it keeps serving the last good data."""

    def __init__(self, opts, tz):
        self.opts, self.tz = opts, tz
        self.data, self.fetched, self.lock = None, 0.0, threading.Lock()

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
            render.render_gif(self.data, out, now=datetime.now(self.tz))
            return out.getvalue()


def make_handler(weather):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] not in ("/", "/weather.gif"):
                self.send_error(404)
                return
            body = weather.gif()
            if body is None:
                self.send_error(503, "Weather data not available yet")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/gif")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            log.debug(fmt, *args)
    return Handler


def main():
    with open(OPTIONS) as f:
        opts = json.load(f)
    while True:  # Home Assistant may still be starting when the app boots
        try:
            tz = ZoneInfo(ha("config")["time_zone"])
            break
        except Exception as err:
            log.info("waiting for Home Assistant: %s", err)
            time.sleep(10)
    log.info("serving %s on port %d, time zone %s", opts["forecast_entity"], PORT, tz.key)
    ThreadingHTTPServer(("", PORT), make_handler(Weather(opts, tz))).serve_forever()


if __name__ == "__main__":
    main()
