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
    if n == 1:
        d.update(temperature=104, humidity=100)
        d["forecast"][0].update(temperature=108, templow=99)
    if n == 2:
        d.update(temperature=-12, alerts=1)
        d["forecast"][1].update(temperature=-10, templow=-22)
    f = render.render_frame(d, render.datetime(2026, 12, 28, 12, 45), 6)
    sheet.paste(f.resize((64 * Z, 64 * Z), Image.NEAREST), ((n % 5) * (64 * Z + 8) + 4, (n // 5) * (64 * Z + 8) + 4))
sheet.save(ROOT / "docs" / "conditions.png")
print("cases", len(cases[:20]))
