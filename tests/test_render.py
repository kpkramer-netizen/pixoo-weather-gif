"""Checks for the area beside the main icon: precipitation outlook, alert icon and humidity."""
import pathlib, sys
from datetime import datetime
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "pixoo_weather_gif"))
import render

NOW = datetime(2026, 11, 6, 19, 22)
ALERT_BOX = (render.GAP_X, 9, render.GAP_X + 9, 17)
PERCENT_BOX = (render.GAP_X, 20, render.GAP_X + 15, 25)
LABEL_BOX = (render.GAP_X, 27, render.GAP_X + 15, 32)
DROP_BOX = (42, 20, 47, 25)
ok = True

def check(name, cond):
    global ok
    ok &= bool(cond)
    print("PASS" if cond else "FAIL", name)

def frame(condition="rainy", chance=37, i=0, alerts=0, humidity=76, temperature=44, smiley=False):
    today = {"date": "2026-11-06", "condition": condition, "temperature": 49, "templow": 37,
             "precipitation_probability": chance}
    w = {"condition": "cloudy", "temperature": temperature, "humidity": humidity, "alerts": alerts,
         "show_smiley": smiley,
         "forecast": [today] + [dict(today, date=f"2026-11-{d:02d}") for d in range(7, 11)]}
    return render.render_frame(w, NOW, i)

def blank(img, box):
    return img.crop(box).getbbox() is None

def text_is(img, box, text):
    expected = Image.new("RGB", (64, 64), render.BLACK)
    render.draw_text(expected.load(), box[0], box[1], text, render.COL["precip"])
    return list(img.crop(box).getdata()) == list(expected.crop(box).getdata())

for chance in (None, 0, 9):
    f = frame(chance=chance)
    check(f"{chance} chance shows nothing", blank(f, PERCENT_BOX) and blank(f, LABEL_BOX))
f = frame(chance=9.5)
check("9.5 rounds up to 10%", text_is(f, PERCENT_BOX, "10%"))
f = frame(chance=10)
check("10% rain shown", text_is(f, PERCENT_BOX, "10%") and text_is(f, LABEL_BOX, "RAIN"))
f = frame(chance=100)
check("100% rain shown", text_is(f, PERCENT_BOX, "100%"))
for condition in ("snowy", "snowy-rainy"):
    f = frame(condition, 60)
    check(f"{condition} labelled SNOW", text_is(f, PERCENT_BOX, "60%") and text_is(f, LABEL_BOX, "SNOW"))
for condition in ("hail", "lightning-rainy", "pouring"):
    check(f"{condition} labelled RAIN", text_is(frame(condition, 60), LABEL_BOX, "RAIN"))
for chance in (0, 29):
    f = frame("fog", chance)
    check(f"fog at {chance} shows FOG with no percentage", blank(f, PERCENT_BOX) and text_is(f, LABEL_BOX, "FOG"))

check("no alert, no icon", blank(frame(alerts=0), ALERT_BOX))
check("alert icon on during first second", not blank(frame(alerts=1, i=0), ALERT_BOX))
check("alert icon off during next second", blank(frame(alerts=1, i=5), ALERT_BOX))
check("alert icon clear of 3-digit temperature", frame(alerts=1, temperature=104).getpixel((38, 16)) == render.BLACK)
check("humidity stays during an alert", not blank(frame(alerts=1), (52, 20, 64, 25)))
check("drop shown normally", not blank(frame(humidity=100, chance=99), DROP_BOX))
check("drop hidden at 100% rain and 100% humidity", blank(frame(humidity=100, chance=100), DROP_BOX))
check("drop shown at 100% rain and 76% humidity", not blank(frame(humidity=76, chance=100), (46, 20, 51, 25)))

SMILEY_BOX = (render.GAP_X + 3, 21, render.GAP_X + 12, 30)
check("no smiley unless switched on", blank(frame(chance=5), SMILEY_BOX))
f = frame(chance=5, smiley=True)
check("smiley under 10% when on", f.getpixel((render.GAP_X + 5, 21)) == render.PAL["S"])
check("smiley doesn't touch humidity drop", f.getpixel((render.GAP_X + 13, 23)) == render.BLACK)
check("no smiley at 10% (shows rain)", text_is(frame(chance=10, smiley=True), PERCENT_BOX, "10%"))
check("no smiley on fog (shows FOG)", text_is(frame("fog", 0, smiley=True), LABEL_BOX, "FOG"))
check("smiley and alert together", not blank(frame(chance=0, smiley=True, alerts=1), ALERT_BOX)
      and frame(chance=0, smiley=True, alerts=1).getpixel((render.GAP_X + 5, 21)) == render.PAL["S"])

print("ALL PASS" if ok else "FAILURES")
sys.exit(0 if ok else 1)
