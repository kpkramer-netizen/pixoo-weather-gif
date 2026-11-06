# Third-party notices

## Weather icons

The weather icons are "Free Animated SVG Weather Icons" by amCharts:
https://www.amcharts.com/free-animated-svg-weather-icons/

They are licensed under the Creative Commons Attribution 4.0 International license (CC BY 4.0):
https://creativecommons.org/licenses/by/4.0/

- `tools/source_icons/` contains the icon SVGs. The only change is correcting `viewbox` to `viewBox` at render time; the files themselves are unmodified.
- `pixoo_weather_gif/sprites/` contains adaptations: the icons are cropped, scaled to 24 pixels, and captured as 20-frame sprite sheets, with each animation retimed to fit a 4-second loop.
- The 12-pixel forecast icons in `pixoo_weather_gif/render.py` are original pixel art, drawn in the same colors.

The MIT License in this repository does not apply to the amCharts icons or to the sprites adapted from them.
