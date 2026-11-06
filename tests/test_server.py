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
        if "weather." in self.path: return self.reply({"state": MODE["state"], "attributes": {"temperature": 47.4, "humidity": 60}})
        if "alerts" in self.path: return self.reply({"state": MODE["alerts"]})
        if "sun.sun" in self.path: return self.reply({"state": "above_horizon"})
        self.reply({}, 404)
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        if MODE["fail"]: return self.reply({}, 500)
        # Forecast dates in UTC, like Pirate Weather: local midnight, 05:00Z. The first is yesterday.
        fc = [{"datetime": "2020-01-01T05:00:00+00:00", "condition": "fog", "temperature": 1, "templow": 1}]
        for d in SAMPLE["forecast"]:
            fc.append(dict(d, datetime=d["date"] + "T05:00:00+00:00"))
        self.reply({"service_response": {"weather.test": {"forecast": fc}}})
    def log_message(self, *a): pass

srv = HTTPServer(("127.0.0.1", 18123), HA)
threading.Thread(target=srv.serve_forever, daemon=True).start()
opts = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
json.dump({"forecast_entity": "weather.test", "alerts_entity": "sensor.alerts"}, opts); opts.close()
env = dict(os.environ, HA_URL="http://127.0.0.1:18123", SUPERVISOR_TOKEN="x", OPTIONS_FILE=opts.name, PORT="16943")
p = subprocess.Popen([sys.executable, "-u", "server.py"], cwd=APP, env=env)

def get(path="/"):
    with urllib.request.urlopen(f"http://127.0.0.1:16943{path}", timeout=5) as r:
        return r.status, r.headers["Content-Type"], r.read()
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
print("ALL PASS" if ok else "FAILURES")
sys.exit(0 if ok else 1)
