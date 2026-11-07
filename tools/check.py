"""Build the docs previews and check the GIF: size, frames, seamless loop, every condition."""
import json, pathlib, sys, tempfile, time
from PIL import Image, ImageChops
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pixoo_weather_gif"))
import render

w = json.loads((ROOT / "tests" / "sample_weather.json").read_text())

t = time.perf_counter()
GIF = pathlib.Path(tempfile.gettempdir()) / "pixoo_weather_check.gif"
render.render_gif(w, GIF)
print(f"render {time.perf_counter() - t:.3f}s, {GIF.stat().st_size} bytes")

g = Image.open(GIF)
frames, durations = [], []
for n in range(g.n_frames):
    g.seek(n)
    frames.append(g.convert("RGB").copy())
    durations.append(g.info.get("duration"))
print("size", g.size, "frames", g.n_frames, "durations", sorted(set(durations)), "loop", g.info.get("loop"))

def changed(a, b):
    d = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v else 0)
    return d.histogram()[255]
steps = [changed(frames[i], frames[(i + 1) % len(frames)]) for i in range(len(frames))]
print("pixels changed per step", steps)
print(f"loop seam {steps[-1]} vs typical {sorted(steps)[len(steps) // 2]}")

# 8x animated preview
big = [f.resize((512, 512), Image.NEAREST) for f in frames]
big[0].save(ROOT / "docs" / "preview.gif", save_all=True, append_images=big[1:], duration=200, loop=0, disposal=1)

# Every condition, day and night, plus edge-case values
conds = list(render.ICON_MAP)
Z = 3
sheet = Image.new("RGB", (5 * (64 * Z + 8), 4 * (64 * Z + 8)), (40, 40, 48))
cases = [(c, False) for c in conds[:15]] + [("partlycloudy", True), ("sunny", True), ("windy-variant", True)]
fc = ["sunny", "clear-night", "partlycloudy", "cloudy", "rainy", "pouring", "snowy", "lightning", "hail", "fog"]
for n, (c, night) in enumerate(cases[:20]):
    d = dict(w, condition=c, is_night=night)
    d["forecast"] = [dict(x) for x in w["forecast"]]
    for k in range(1, 5):
        d["forecast"][k]["condition"] = fc[(n + k * 2) % len(fc)]
        d["forecast"][k]["precipitation_probability"] = (n * 17 + k * 25) % 101
    d["forecast"][0]["condition"] = c
    d["forecast"][0]["precipitation_probability"] = (n * 23) % 101
    if n == 1:
        d.update(temperature=104, humidity=100)
        d["forecast"][0].update(temperature=108, templow=99)
    if n == 2:
        d.update(temperature=-12, alerts=1)
        d["forecast"][1].update(temperature=-10, templow=-22)
    f = render.render_frame(d, render.datetime(2026, 12, 28, 12, 45), 0)
    sheet.paste(f.resize((64 * Z, 64 * Z), Image.NEAREST), ((n % 5) * (64 * Z + 8) + 4, (n // 5) * (64 * Z + 8) + 4))
sheet.save(ROOT / "docs" / "conditions.png")
print("cases", len(cases[:20]))

# Labeled diagram of the screen for the README's "Reading the screen" section
from PIL import ImageDraw, ImageFont
S, M = 6, 70  # scale, margin
now = render.datetime(2026, 11, 6, 14, 30)
d = dict(w, alerts=1)
f = render.render_frame(d, now, 0).resize((64 * S, 64 * S), Image.NEAREST)
canvas = Image.new("RGB", (64 * S + 2 * M, 64 * S + M + 20), (24, 24, 30))
canvas.paste(f, (M, M))
draw = ImageDraw.Draw(canvas)
font = ImageFont.load_default(15)
ds = render.date_text(now)
tx0 = render.text_width(ds) + (64 - render.text_width("FRI") - render.text_width(ds) - render.text_width(render.clock(now))) // 2
# number: (box in screen pixels x0, y0, x1, y1), side of the badge, position along that side in screen pixels
labels = {
    1: ((0, 0, render.text_width(ds), 5), "left", 2.5),
    2: ((tx0, 0, tx0 + render.text_width(render.clock(now)), 5), "top", tx0 + 1),
    3: ((64 - render.text_width("FRI"), 0, 64, 5), "right", 2.5),
    4: ((0, 8, 24, 32), "left", 18),
    5: ((render.GAP_X, 9, render.GAP_X + 9, 17), "top", render.GAP_X + 6),
    6: ((render.GAP_X, 20, render.GAP_X + 15, 32), "left", 26),
    7: ((47, 8, 64, 18), "right", 13),
    8: ((45, 20, 64, 25), "right", 22.5),
    9: ((47, 27, 64, 32), "right", 29.5),
    10: ((3, 34, 12, 39), "left", 36.5),
    11: ((3, 40, 15, 52), "left", 43),
    12: ((1, 40, 2, 52), "left", 49),
    13: ((3, 53, 12, 58), "left", 55.5),
    14: ((3, 59, 12, 64), "left", 61.5),
}
for n, ((x0, y0, x1, y1), side, at) in labels.items():
    box =(M + x0 * S, M + y0 * S, M + x1 * S - 1, M + y1 * S - 1)
    if side == "left":
        cx, cy, ex, ey = M // 2, M + at * S, box[0], M + at * S
    elif side == "right":
        cx, cy, ex, ey = M + 64 * S + M // 2, M + at * S, box[2], M + at * S
    else:
        cx, cy, ex, ey = M + at * S, M // 2, M + at * S, box[1]
    draw.line((cx, cy, ex, ey), fill=(255, 214, 10), width=2)
    draw.rectangle(box, outline=(255, 214, 10), width=2)
    draw.ellipse((cx - 13, cy - 13, cx + 13, cy + 13), fill=(255, 214, 10))
    draw.text((cx, cy), str(n), fill=(20, 20, 20), font=font, anchor="mm")
canvas.save(ROOT / "docs" / "layout.png")
print("layout", canvas.size)
