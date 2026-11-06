"""Render the 64x64 Pixoo weather GIF from weather data and baked sprites.

Usage: python render.py weather.json [out.gif]
Runtime dependency: Pillow only.
"""
import json, pathlib, sys
from datetime import date, datetime
from PIL import Image

ROOT = pathlib.Path(__file__).parent
FRAMES, FRAME_MS, MAIN = 20, 200, 24
BLACK = (0, 0, 0)

# ---- Same condition-to-icon mapping as animated-weather-card: (day, night) ----
ICON_MAP = {
    "clear-night": ("night", "night"), "sunny": ("day", "night"),
    "partlycloudy": ("cloudy-day-3", "cloudy-night-3"), "cloudy": ("cloudy", "cloudy"),
    "fog": ("cloudy", "cloudy"), "windy": ("cloudy", "cloudy"),
    "windy-variant": ("cloudy-day-2", "cloudy-night-2"), "rainy": ("rainy-5", "rainy-5"),
    "pouring": ("rainy-6", "rainy-6"), "lightning": ("thunder", "thunder"),
    "lightning-rainy": ("thunder", "thunder"), "snowy": ("snowy-5", "snowy-5"),
    "snowy-rainy": ("rainy-7", "rainy-7"), "hail": ("rainy-7", "rainy-7"),
    "exceptional": ("cloudy", "cloudy"),
}

# ---- 3x5 pixel font ----
FONT = {
    "0": "111101101101111", "1": "010110010010111", "2": "111001111100111", "3": "111001111001111",
    "4": "101101111001001", "5": "111100111001111", "6": "111100111101111", "7": "111001001001001",
    "8": "111101111101111", "9": "111101111001111", "A": "010101111101101", "B": "110101110101110",
    "C": "011100100100011", "D": "110101101101110", "E": "111100110100111", "F": "111100110100100",
    "G": "011100101101011", "H": "101101111101101", "I": "111010010010111", "J": "001001001101010",
    "K": "101101110101101", "L": "100100100100111", "M": "101111111101101", "N": "110101101101101",
    "O": "010101101101010", "P": "110101110100100", "Q": "010101101110011", "R": "110101110101101",
    "S": "011100010001110", "T": "111010010010010", "U": "101101101101111", "V": "101101101101010",
    "W": "101101111111101", "X": "101101010101101", "Y": "101101010010010", "Z": "111001010100111",
    "-": "000000111000000", ":": "000010000010000", "%": "101001010100101", "!": "010010010000010",
}

def text_width(s, scale=1):
    return (len(s) * 4 - 1) * scale if s else 0

def draw_text(px, x, y, s, color, scale=1):
    for ch in s.upper():
        bits = FONT.get(ch)
        if bits:
            for r in range(5):
                for c in range(3):
                    if bits[r * 3 + c] == "1":
                        for dy in range(scale):
                            for dx in range(scale):
                                put(px, x + c * scale + dx, y + r * scale + dy, color)
        x += 4 * scale

def put(px, x, y, color):
    if 0 <= x < 64 and 0 <= y < 64:
        px[x, y] = color

# ---- Hand-drawn 12px forecast icons, in the card icons' colors ----
PAL = {"O": (255, 165, 0), "W": (255, 255, 255), "B": (87, 160, 238), "L": (145, 192, 248), "Y": (255, 232, 150)}
CLOUD = ["....WWWW....",
         "...WBBBBWWW.",
         "..WBBBBBBBBW",
         ".WWBBBBBBBBW",
         "WBBBBBBBBBBW",
         "WBBBBBBBBBBW",
         ".WWWWWWWWWW."]
SUN = [[".....OO.....", ".....OO.....", "..O......O..", "....OOOO....", "...OOOOOO...", "OO.OOOOOO.OO",
        "OO.OOOOOO.OO", "...OOOOOO...", "....OOOO....", "..O......O..", ".....OO.....", ".....OO....."],
       ["............", ".....OO.....", ".O........O.", "..O.OOOO.O..", "...OOOOOO...", ".O.OOOOOO.O.",
        ".O.OOOOOO.O.", "...OOOOOO...", "..O.OOOO.O..", ".O........O.", ".....OO.....", "............"]]
MOON = ["....OOOO....", "..OOOOO.....", ".OOOOO......", ".OOOO.......", "OOOOO.......", "OOOOO.......",
        "OOOOO.......", ".OOOOO.....O", ".OOOOOO...OO", "..OOOOOOOOO.", "....OOOOOO..", "............"]
SMALL_SUN = ["...O....", ".O...O..", "...OOO..", "..OOOOO.", "O.OOOOO.", "..OOOOO.", ".O.OOO.O", "........"]
SMALL_MOON = ["..OOO...", ".OOO....", "OOO.....", "OOO.....", "OOOO...O", ".OOOOOOO", "..OOOOO.", "........"]
BOLT = ["..OO", ".OO.", "OOOO", ".OO.", ".O.."]
REAR_CLOUD = ["..LLL...", ".LLLLLL.", "LLLLLLLL", "LLLLLLLL", "LLLLLLLL"]

def blit(px, x, y, rows, swap=None):
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch != ".":
                put(px, x + c, y + r, PAL[(swap or {}).get(ch, ch)])

def icon12(px, x, y, cond, i):
    """Draw a 12x12 icon. i is the frame (0-19); every cycle divides 20 so it loops cleanly."""
    if cond == "sunny":
        blit(px, x, y, SUN[(i // 5) % 2])
    elif cond == "clear-night":
        blit(px, x, y, MOON)
        if (i // 5) % 2:
            put(px, x + 8, y + 2, PAL["W"])
        else:
            put(px, x + 10, y + 5, PAL["W"])
    elif cond in ("partlycloudy", "windy-variant"):
        blit(px, x, y, SMALL_SUN)
        if (i // 5) % 2:  # rays twinkle
            for dx, dy in ((3, 0), (1, 1), (5, 1), (0, 4), (1, 6)):
                put(px, x + dx, y + dy, BLACK)
        blit(px, x, y + 5, CLOUD)
    elif cond in ("cloudy", "fog", "windy", "exceptional"):
        back = (i // 5) % 2  # pale rear cloud drifts one pixel
        blit(px, x + back, y + 1, REAR_CLOUD)
        blit(px, x, y + 4, CLOUD)
    elif cond in ("rainy", "pouring"):
        blit(px, x, y, CLOUD)
        cols = (2, 5, 8) if cond == "rainy" else (1, 4, 7, 10)
        for n, cx in enumerate(cols):
            p = ((i // 2) + n * 2) % 5
            for d in (0, 1):
                if 8 <= 7 + p + d <= 11:
                    put(px, x + cx, y + 7 + p + d, PAL["L"])
    elif cond in ("snowy", "snowy-rainy", "hail"):
        blit(px, x, y, CLOUD)
        color = PAL["W"] if cond == "snowy" else PAL["L"]
        for n, cx in enumerate((2, 6, 10)):
            p = ((i // 4) + n * 2) % 5
            if p <= 3:
                put(px, x + cx, y + 8 + p, color)
    elif cond in ("lightning", "lightning-rainy"):
        blit(px, x, y, CLOUD)
        flash = i in (0, 1, 10, 11)
        blit(px, x + 4, y + 7, BOLT, {"O": "Y"} if flash else None)
    else:
        blit(px, x, y + 3, CLOUD)

# ---- Baked 24px sprites ----
_cache = {}
def main_icon(cond, night):
    name = ICON_MAP.get(cond, ("cloudy", "cloudy"))[1 if night else 0]
    if name not in _cache:
        sheet = Image.open(ROOT / "sprites" / f"{name}.png").convert("RGBA")
        # Boost partial alpha so thin details (raindrops, rays) stay visible on black.
        sheet.putalpha(sheet.getchannel("A").point(lambda a: min(255, int(a * 1.6))))
        _cache[name] = sheet
    return _cache[name]

# ---- Layout ----
COL = dict(date=(150, 190, 255), time=(255, 255, 255), day=(255, 190, 90), rule=(55, 55, 70),
           temp=(255, 255, 255), hum=(120, 200, 255), hi=(255, 205, 90), lo=(90, 160, 255),
           fc_day=(235, 235, 235), fc_hi=(230, 230, 230), alert=(255, 70, 50), rain=(70, 150, 255),
           rain_track=(30, 40, 65))
DROP = ["..L..", "..L..", ".LLL.", "LLLLL", ".LLL."]

def clock(now):
    h = now.hour % 12 or 12
    return f"{h}:{now.minute:02d}{'A' if now.hour < 12 else 'P'}"

def render_frame(w, now, i):
    img = Image.new("RGB", (64, 64), BLACK)
    px = img.load()

    # Header: date, time, weekday
    draw_text(px, 0, 0, f"{now.month}-{now.day:02d}", COL["date"])
    t = clock(now)
    wd = now.strftime("%a").upper()[:3]
    draw_text(px, 64 - text_width(wd), 0, wd, COL["day"])
    d_end = text_width(f"{now.month}-{now.day:02d}")  # centre the time in the gap
    draw_text(px, d_end + (64 - text_width(wd) - d_end - text_width(t)) // 2, 0, t, COL["time"])
    for x in range(64):
        px[x, 6] = COL["rule"]

    # Current: animated 24px icon, large temperature, humidity or alert, today's high/low
    sheet = main_icon(w["condition"], w.get("is_night", False))
    frame = sheet.crop((i * MAIN, 0, (i + 1) * MAIN, MAIN))
    img.paste(frame, (1, 8), frame)

    temp = str(round(w["temperature"]))
    tw = text_width(temp, 2)
    tx = 61 - tw  # leaves a one-pixel gap before the degree mark
    draw_text(px, tx, 8, temp, COL["temp"], 2)
    for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):  # degree mark
        put(px, 62 + dx, 8 + dy, COL["temp"])

    if w.get("alerts"):
        if (i // 5) % 2 == 0:
            draw_text(px, 29, 20, "ALERT", COL["alert"])
    else:
        hum = f"{round(w['humidity'])}%"
        hx = 63 - text_width(hum)
        blit(px, hx - 6, 20, DROP)
        draw_text(px, hx, 20, hum, COL["hum"])

    today = w["forecast"][0]
    hi, lo = str(round(today["temperature"])), str(round(today["templow"]))
    draw_text(px, 63 - text_width(lo), 27, lo, COL["lo"])
    draw_text(px, 63 - text_width(lo) - 2 - text_width(hi), 27, hi, COL["hi"])
    for x in range(64):
        px[x, 32] = COL["rule"]

    # Next four days, 16px columns: label, icon + rain bar, high, low
    for n, day in enumerate(w["forecast"][1:5]):
        cx = n * 16
        label = date.fromisoformat(day["date"]).strftime("%a").upper()[:2]
        draw_text(px, cx + (16 - text_width(label)) // 2 + 1, 34, label, COL["fc_day"])
        icon12(px, cx + 3, 40, day["condition"], i)
        fill = round((day.get("precipitation_probability") or 0) / 100 * 12)
        for k in range(12):  # rain-chance gauge
            put(px, cx + 1, 51 - k, COL["rain"] if k < fill else COL["rain_track"])
        h, l = str(round(day["temperature"])), str(round(day["templow"]))
        draw_text(px, cx + (16 - text_width(h)) // 2 + 1, 53, h, COL["fc_hi"])
        draw_text(px, cx + (16 - text_width(l)) // 2 + 1, 59, l, COL["lo"])
    return img

def render_gif(w, out, now=None):
    """Write the GIF to a path or binary stream. now defaults to w["captured"], then the clock."""
    if now is None:
        now = datetime.fromisoformat(w["captured"]) if w.get("captured") else datetime.now()
    frames = [render_frame(w, now, i) for i in range(FRAMES)]
    # One shared palette across all frames, so colors can't flicker between frames.
    strip = Image.new("RGB", (64, 64 * FRAMES))
    for i, f in enumerate(frames):
        strip.paste(f, (0, 64 * i))
    pal = strip.quantize(colors=128, method=Image.MEDIANCUT, dither=Image.NONE)
    pframes = [f.quantize(palette=pal, dither=Image.NONE) for f in frames]
    pframes[0].save(out, format="GIF", save_all=True, append_images=pframes[1:], duration=FRAME_MS,
                    loop=0, disposal=1, optimize=False)
    return frames

if __name__ == "__main__":
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "weather.gif")
    render_gif(json.loads(pathlib.Path(src).read_text()), out)
    print("wrote", out)
