# Hodograph Analysis Tool

## Overview
A Flask-based meteorological hodograph analysis tool that displays NEXRAD radar data, METAR surface observations, and NWS weather warnings on an interactive map. Users can select radar sites, load VAD wind profiles, and generate hodograph plots with various meteorological parameters.

## Architecture
- **Backend**: Flask (Python) serving API endpoints and generating matplotlib hodograph plots
- **Frontend**: Vanilla HTML/CSS/JS with Leaflet.js for maps
- **Data Sources**:
  - NEXRAD Level-III VAD data via AWS S3
  - METAR surface observations via `https://aviationweather.gov/api/data/metar` (v2 API)
  - NWS weather warnings via `https://api.weather.gov/alerts/active`

## Key Files
- `app.py` - Main Flask application with all API routes
- `hodograph_plotter.py` - Matplotlib-based hodograph rendering
- `metar_utils.py` - METAR data fetching (Aviation Weather Center v2 API)
- `warning_utils.py` - NWS warning data fetching
- `nexrad_fetcher.py` - NEXRAD VAD data retrieval from AWS
- `wind_profile.py` - Wind profile data model
- `params.py` - Meteorological parameter calculations (SRH, shear, Bunkers)
- `radar_sites.py` - Radar site database
- `templates/index.html` - Main HTML template
- `static/js/app.js` - Frontend JavaScript
- `static/css/style.css` - Styles

## Features
- Interactive radar site selection on map
- METAR station auto-discovery within 100nm of selected radar
- Storm motion input with Bunkers calculation (RM, LM, Mean Wind)
- Hodograph generation with SRH shading (0.5km, 1km, 3km), critical angle, shear vector
- Deviant Tornado Motion (DTM) calculation
- Esterheld critical angle uses 0.5km interpolated wind point
- Interactive mode shows SRH values, Bunkers LM/RM, Mean Wind, and DTM in a responsive info box below the hodograph
- **Analyst Mode**: Fully interactive HTML5 Canvas-based hodograph
  - Scroll-to-zoom with smooth scaling, drag-to-pan navigation
  - Hover over data points for detailed tooltips (height, wind speed/direction, U/V)
  - Real-time feature toggling: speed rings, height markers, SRH shading, shear vector, critical angle lines, storm/surface markers, parameter text
  - Reset View button to return to default zoom/pan
  - `static/js/interactive-hodograph.js` - Canvas renderer class
  - `/api/wind-profile-data` - JSON endpoint for raw profile data (used by interactive mode)
- **VAD Loop & Scrubber**: After the latest hodograph renders the app prefetches
  the previous 6 VAD scans for the same site and exposes a scrubber strip
  (slider, play/pause, prev/next, timestamp, frame counter) below the
  hodograph. Works in both Analyst (canvas data swap, zoom/pan preserved) and
  Standard (matplotlib image swap) modes. Storm motion and METAR inputs are
  reused for every frame. Failed frames are skipped silently. The scrubber is
  torn down on Reset, on a new site selection, and on Analyst↔Standard toggle.
  - `nexrad_fetcher.fetch_recent(site_id, count=7)` — parallel download with
    on-disk + 5 min in-memory cache
  - `nexrad_fetcher.get_frame_path(site_id, file_id)` — resolves a cached frame
  - `/api/vad-history/<site_id>` — ordered metadata `{file_id, valid_time}`
  - `/api/wind-profile-frame/<site_id>/<file_id>` — JSON payload (Analyst)
  - `/api/hodograph-frame/<site_id>/<file_id>` — base64 PNG (Standard)
  - In-memory `_frame_payload_cache` keyed by
    `(mode, site_id, file_id, storm_motion, metar, show_half_km)`; cleared on
    `/api/reset`
- Active NWS tornado/severe thunderstorm warning overlay

## Running
```bash
python app.py
# Runs on port 5000
```
