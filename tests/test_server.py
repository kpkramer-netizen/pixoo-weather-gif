"""End-to-end test of the app against a mock Home Assistant API."""
import io, json, os, pathlib, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from PIL import Image

APP = pathlib.Path(__file__).resolve().parent.parent / "pixoo_weather_gif"
SAMPLE = json.loads((pathlib.Path(__file__).resolve().parent / "sample_weather.json").read_text())
MODE = {"state": "partlycloudy", "fail": False, "alerts": "0", "calls": 0}

class HA(BaseHTTPRequestHandler):
    def reply(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        MODE["calls"] += 1
        if MODE["fail"]: return self.reply({}, 500)
        if self.path.endswith("/config"): return self.reply({"time_zone": "America/New_York"})
        if self.path.endswith("/states"): return self.reply([
            {"entity_id": "weather.test", "state": MODE["state"], "attributes": {"friendly_name": "Test <Weather>"}},
            {"entity_id": "weather.other", "state": "sunny", "attributes": {"friendly_name": "Other"}},
            {"entity_id": "weather.noforecast", "state": "sunny", "attributes": {"friendly_name": "No forecast"}},
            {"entity_id": "sensor.alerts", "state": MODE["alerts"], "attributes": {"friendly_name": "Weather Alerts"}},
            {"entity_id": "sensor.power", "state": "5", "attributes": {"friendly_name": "Power"}}])
        if "weather." in self.path: return self.reply({"state": MODE["state"], "attributes": {"temperature": 47.4, "humidity": 60}})
        if "alerts" in self.path: return self.reply({"state": MODE["alerts"]})
        if "sun.sun" in self.path: return self.reply({"state": "above_horizon"})
        self.reply({}, 404)
    def do_POST(self):
        entity = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["entity_id"]
        if MODE["fail"] or entity == "weather.noforecast": return self.reply({}, 500)
        # Forecast dates in UTC, like Pirate Weather: local midnight, 05:00Z. The first is yesterday.
        fc = [{"datetime": "2020-01-01T05:00:00+00:00", "condition": "fog", "temperature": 1, "templow": 1}]
        for d in SAMPLE["forecast"]:
            fc.append(dict(d, datetime=d["date"] + "T05:00:00+00:00"))
        self.reply({"service_response": {entity: {"forecast": fc}}})
    def log_message(self, *a): pass

srv = HTTPServer(("127.0.0.1", 18123), HA)
threading.Thread(target=srv.serve_forever, daemon=True).start()
opts = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
json.dump({"forecast_entity": "weather.test", "alerts_entity": "sensor.alerts"}, opts); opts.close()
SETTINGS_FILE = os.path.join(tempfile.mkdtemp(), "settings.json")
env = dict(os.environ, HA_URL="http://127.0.0.1:18123", SUPERVISOR_TOKEN="x", OPTIONS_FILE=opts.name, PORT="16943",
           SETTINGS_FILE=SETTINGS_FILE, INGRESS_PORT="18099", INGRESS_ALLOW="127.0.0.1")
p = subprocess.Popen([sys.executable, "-u", "server.py"], cwd=APP, env=env)

def get(path="/", port=16943):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return r.status, r.headers["Content-Type"], r.read()

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None

def post(form, path="/save"):
    data = urllib.parse.urlencode(form).encode()
    try:
        r = urllib.request.build_opener(NoRedirect).open(f"http://127.0.0.1:18099{path}", data, timeout=5)
        return r.status, r.headers.get("Location"), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location"), e.read().decode()

def saved():
    try:
        return json.load(open(SETTINGS_FILE))
    except FileNotFoundError:
        return None
ok = True
def check(name, cond, extra=""):
    global ok
    ok &= bool(cond)
    print("PASS" if cond else "FAIL", name, extra)
try:
    for _ in range(30):
        try: status, ctype, body = get(); break
        except OSError: time.sleep(0.2)
    im = Image.open(io.BytesIO(body))
    check("serves a GIF", status == 200 and ctype == "image/gif" and im.format == "GIF")
    check("64x64, 20 frames", im.size == (64, 64) and im.n_frames == 20, f"{im.size} {im.n_frames} {len(body)} bytes")
    check("alias path", get("/weather.gif")[0] == 200)
    try: get("/nope"); check("404 on other paths", False)
    except urllib.error.HTTPError as e: check("404 on other paths", e.code == 404)
    n = MODE["calls"]; get(); get()
    check("caches weather between requests", MODE["calls"] == n)

    # Settings page
    status, ctype, page = get("/", 18099); page = page.decode()
    check("settings page served", status == 200 and ctype.startswith("text/html"))
    check("lists weather entities, current one selected", 'value="weather.test" selected' in page and 'value="weather.other"' in page)
    check("lists alert-like sensors only", 'value="sensor.alerts" selected' in page and "sensor.power" not in page)
    check("escapes entity names", "Test &lt;Weather&gt;" in page and "Test <Weather>" not in page)
    check("smiley starts off", 'name="show_smiley" value="on">' in page)
    check("preview GIF on the settings port", get("/preview.gif", 18099)[1] == "image/gif")
    status, loc, _ = post({"forecast_entity": "weather.nope", "alerts_entity": ""})
    check("rejects an unknown weather entity", status == 400 and saved() is None)
    status, loc, _ = post({"forecast_entity": "weather.test", "alerts_entity": "sensor.missing"})
    check("rejects a missing alerts sensor", status == 400 and saved() is None)
    status, loc, body = post({"forecast_entity": "weather.noforecast", "alerts_entity": ""})
    check("rejects a weather entity with no daily forecast", status == 400 and saved() is None and "not saved" in body)
    check("screen unaffected by a rejected save", get()[0] == 200)
    status, loc, _ = post({"forecast_entity": "weather.other", "alerts_entity": "", "show_smiley": "on"})
    check("saves and redirects relative to ingress", status == 303 and loc == "./?saved=1")
    check("settings written", saved() == {"forecast_entity": "weather.other", "alerts_entity": "", "show_smiley": True}, str(saved()))
    page = get("/?saved=1", 18099)[2].decode()
    check("page reflects saved settings", "Saved." in page and 'value="weather.other" selected' in page
          and 'name="show_smiley" value="on" checked' in page)
    check("GIF still served after a change", get()[0] == 200)
    MODE["fail"] = True
    check("keeps serving through HA failure (cached)", get()[0] == 200)
finally:
    p.terminate(); p.wait()

# Failure paths and today-filtering, directly
sys.path.insert(0, str(APP))
import server
from zoneinfo import ZoneInfo
from datetime import datetime
server.HA_URL = "http://127.0.0.1:18123"
MODE["fail"] = False
w = server.Weather({"forecast_entity": "weather.test", "alerts_entity": "sensor.alerts"}, ZoneInfo("America/New_York"))
d = server.fetch_weather(w.opts, w.tz)
today = datetime.now(w.tz).date().isoformat()
check("skips past days, converts UTC to local date", d["forecast"][0]["date"] >= today and "2020-01-01" not in [x["date"] for x in d["forecast"]],
      d["forecast"][0]["date"])
MODE["state"] = "unavailable"
check("no data + entity unavailable gives no GIF", w.gif() is None)
MODE["state"] = "rainy"; w.fetched = 0
check("recovers when entity returns", w.gif() is not None)
MODE["fail"] = True; w.fetched = 0
check("refresh failure keeps last data", w.gif() is not None and w.data["condition"] == "rainy")
MODE["fail"] = False; MODE["alerts"] = "2"; w.fetched = 0; w.gif()
check("alert count read", w.data["alerts"] == 2)
MODE["alerts"] = "unknown"; w.fetched = 0; w.gif()
check("bad alert state doesn't break the screen", w.data["alerts"] == 0)

# Settings precedence and the ingress-only check
d = tempfile.mkdtemp()
server.OPTIONS, server.SETTINGS = os.path.join(d, "options.json"), os.path.join(d, "settings.json")
check("defaults with no files", server.load_settings() == server.DEFAULTS)
json.dump({"forecast_entity": "weather.a", "alerts_entity": "sensor.a", "junk": 1}, open(server.OPTIONS, "w"))
check("Configuration tab values used first", server.load_settings() == {"forecast_entity": "weather.a", "alerts_entity": "sensor.a", "show_smiley": False})
server.save_settings({"forecast_entity": "weather.b", "alerts_entity": "", "show_smiley": True})
check("settings page values win", server.load_settings() == {"forecast_entity": "weather.b", "alerts_entity": "", "show_smiley": True})
w.update({"forecast_entity": "weather.b", "alerts_entity": "", "show_smiley": True})
check("changing the entity drops cached data", w.data is None)
server.INGRESS_ALLOW = {"10.9.9.9"}
from http.server import ThreadingHTTPServer
blocked = ThreadingHTTPServer(("127.0.0.1", 18098), server.make_settings_handler(w))
threading.Thread(target=blocked.serve_forever, daemon=True).start()
try:
    get("/", 18098); check("refuses clients other than ingress", False)
except urllib.error.HTTPError as e:
    check("refuses clients other than ingress", e.code == 403)
before = server.load_settings()
try:
    urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18098/save", b"forecast_entity=weather.test"), timeout=5)
    check("refuses saves from other clients", False)
except urllib.error.HTTPError as e:
    check("refuses saves from other clients", e.code == 403 and server.load_settings() == before)
blocked.shutdown()
print("ALL PASS" if ok else "FAILURES")
sys.exit(0 if ok else 1)
