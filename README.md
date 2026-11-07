# Pixoo Weather GIF

A Home Assistant app that serves a live, animated 64×64 weather screen for the Divoom Pixoo 64.

![Animated weather screen, enlarged 8x](docs/preview.gif)

## Reading the screen

![The weather screen with each element numbered](docs/layout.png)

The top half is today; the bottom half is the next four days. Settings mentioned below are on the [settings page](#settings).

| # | Element | What it shows |
|---|---|---|
| 1 | Date | Today's date, month-day (`11-06`) or day-month (`6-11`) |
| 2 | Time | When the GIF was drawn, 12-hour (`2:30P`) or 24-hour (`14:30`). It only moves on when the display fetches the GIF again. |
| 3 | Weekday | Today's day of the week |
| 4 | Current conditions | Animated icon for the weather right now, with night versions after sunset |
| 5 | Alert | A red warning triangle while the alerts sensor reports one or more active alerts. Blinks once a second, or stays solid. Empty when there are no alerts. |
| 6 | Today's outlook | Today's chance of rain or snow with `RAIN` or `SNOW`, when it's at or above the threshold (10% by default). Shows `FOG` on foggy days, and either nothing or an optional smiley when the chance is below the threshold. |
| 7 | Temperature | Current temperature, in the weather entity's units |
| 8 | Reading | Current humidity (drop icon), or the "feels like" temperature (thermometer icon) |
| 9 | Today's range | Today's forecast high (yellow) and low (blue) |
| 10 | Day | Day of the week for each forecast column |
| 11 | Forecast | Animated icon for that day's forecast conditions |
| 12 | Rain chance | That day's chance of precipitation. The brighter part fills from the bottom, about 8% per pixel; the dim part is the empty track. |
| 13 | High | That day's forecast high |
| 14 | Low | That day's forecast low |

Every weather condition has its own icon, with day and night versions where they apply:

![Screens for each weather condition](docs/conditions.png)

## How it works

The app reads a `weather.*` entity through the Home Assistant API and draws a new GIF each time one is requested. The GIF has 20 frames at 200 ms each, loops seamlessly, and is about 16 KB. Weather data is cached for 30 seconds. If Home Assistant has a problem, the app keeps serving the last good data.

The GIF is served at `http://<home-assistant-ip>:6943/`. The clock in each GIF is fixed at the moment it was drawn, so it only moves forward when the display fetches the GIF again.

## Install

1. In Home Assistant, go to **Settings → Apps → Install app**, open the **⋮** menu, choose **Repositories**, and add this repository's URL.
2. Install **Pixoo Weather GIF**.
3. Start the app, then open its settings page with **Open web UI** and choose your entities.
4. Open `http://<home-assistant-ip>:6943/` to check the GIF.

## Settings

The settings page runs inside Home Assistant and only answers requests that come through it. It lists your entities, shows the current screen, and applies changes on the Pixoo's next refresh.

| Setting | Description |
|---|---|
| Weather entity | A `weather.*` entity. It must provide a daily forecast; the page checks before saving. |
| Weather alerts sensor | Optional. A sensor whose state is the number of active alerts. The list shows sensors with "alert" in their name. |
| Rain and snow threshold | Default 10%. Today's chance of rain or snow is shown at or above this. Foggy days always show `FOG`. |
| Smiley for low chances | Off by default. Shows a smiley instead of nothing when today's chance is below the threshold. |
| Reading under the temperature | Humidity (default), or the "feels like" temperature with a thermometer icon. Falls back to humidity if the weather entity has no apparent temperature. |
| Clock | 12-hour (default) or 24-hour. |
| Date | Month-day (default) or day-month. |
| Alert icon | Blinking (default) or solid. |

The app's **Configuration** tab has the same settings. They're used as starting values; once you save on the settings page, its values take priority.

## Show it on the Pixoo

This app only serves the GIF, so something else has to tell the Pixoo to play it. The [Divoom Pixoo 64 integration](https://github.com/gickowtf/pixoo-homeassistant) works well. Add a `gif` page to its configuration:

```yaml
- page_type: gif
  gif_url: http://<home-assistant-ip>:6943/
  duration: 55
```

With a single page and no others, set the integration's scan interval to control how often the GIF reloads. The clock only updates on a reload.

## Development

The app and its tests need Python and Pillow, plus `tzdata` on Windows. The app's Docker image uses Python 3.13.

```bash
python tests/test_server.py
```

```bash
python tests/test_render.py
```

```bash
python tools/check.py
```

`tests/test_server.py` runs the server against a mock Home Assistant API. `tests/test_render.py` checks the alert icon, precipitation text and humidity. `tools/check.py` validates the GIF and rebuilds the images in `docs/`, including the labeled layout diagram.

The 24px icon sprites in `pixoo_weather_gif/sprites` are generated once from the SVGs in `tools/source_icons`, and only need rebuilding if the icons change. That step also needs Playwright and Microsoft Edge:

```bash
python tools/bake_sprites.py
```

## License

The code is under the [MIT License](LICENSE).

The weather icons are by [amCharts](https://www.amcharts.com/free-animated-svg-weather-icons/), under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). See [NOTICE.md](NOTICE.md) for details and the changes made to them.

This project is not affiliated with Divoom, amCharts or Home Assistant.
