"""Bake the card's animated SVG icons into looping PNG sprite frames.

Run once at build time (needs Edge + playwright). The runtime renderer only
needs Pillow and the PNGs this writes to sprites/.
"""
import io, pathlib
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
SRC, OUT = ROOT / "source_icons", ROOT.parent / "pixoo_weather_gif" / "sprites"
ICONS = "day night cloudy-day-3 cloudy-night-3 cloudy-day-2 cloudy-night-2 cloudy rainy-5 rainy-6 rainy-7 thunder snowy-5".split()
FRAMES, LOOP_MS, SIZE, SCALE = 20, 4000, 24, 8

# Every animation is retimed to a whole number of cycles in the loop, as close
# to its real speed as possible, so frame 20 flows back into frame 1.
SEEK = """([i, n, loop]) => {
  for (const a of document.getAnimations()) {
    a.pause();
    const D = a.effect.getComputedTiming().duration, el = a.effect.target, name = a.animationName;
    let f;  // progress through the animation's own cycle
    if (name === 'am-weather-rain') {
      const dash = (el.getAttribute('stroke-dasharray') || '4,7').split(',').map(Number);
      const period = dash[0] + dash[1], cycles = Math.max(1, Math.round((100 / D * loop) / period));
      f = (period * cycles / 100) * (i / n);
    } else if (name === 'am-weather-sun') {
      f = (Math.max(1, Math.round((loop / D) * 8)) / 8) * (i / n);  // rays repeat every 45 degrees
    } else {
      f = Math.max(1, Math.round(loop / D)) * (i / n);
    }
    a.currentTime = (f % 1) * D;
  }
}"""

def main():
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)
        pg = b.new_page(viewport={"width": 64 * SCALE, "height": 64 * SCALE})
        for name in ICONS:
            svg = (SRC / f"{name}.svg").read_text(encoding="utf-8").split("?>", 1)[-1].replace("viewbox=", "viewBox=")
            pg.set_content(f"<!doctype html><style>html,body{{margin:0;background:transparent}}svg{{display:block;width:{64*SCALE}px;height:{64*SCALE}px}}</style>{svg}")
            raw = []
            for i in range(FRAMES):
                pg.evaluate(SEEK, [i, FRAMES, LOOP_MS])
                raw.append(Image.open(io.BytesIO(pg.screenshot(omit_background=True))).convert("RGBA"))
            # One crop box for all frames so nothing jitters.
            box = None
            for f in raw:
                bb = f.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
                if bb:
                    box = bb if box is None else (min(box[0], bb[0]), min(box[1], bb[1]), max(box[2], bb[2]), max(box[3], bb[3]))
            w, h = box[2] - box[0], box[3] - box[1]
            k = SIZE / max(w, h)
            nw, nh = max(1, round(w * k)), max(1, round(h * k))
            sheet = Image.new("RGBA", (SIZE * FRAMES, SIZE), (0, 0, 0, 0))
            for i, f in enumerate(raw):
                s = f.crop(box).resize((nw, nh), Image.LANCZOS)
                sheet.paste(s, (i * SIZE + (SIZE - nw) // 2, (SIZE - nh) // 2))
            sheet.save(OUT / f"{name}.png")
            print(name, "crop", box, "->", (nw, nh))
        b.close()

if __name__ == "__main__":
    main()
