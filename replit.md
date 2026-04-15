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
- Storm motion input with Bunkers calculation
- Hodograph generation with SRH shading, critical angle, shear vector
- **Analyst Mode**: Fully interactive HTML5 Canvas-based hodograph
  - Scroll-to-zoom with smooth scaling, drag-to-pan navigation
  - Hover over data points for detailed tooltips (height, wind speed/direction, U/V)
  - Real-time feature toggling: speed rings, height markers, SRH shading, shear vector, critical angle lines, storm/surface markers, parameter text
  - Reset View button to return to default zoom/pan
  - `static/js/interactive-hodograph.js` - Canvas renderer class
  - `/api/wind-profile-data` - JSON endpoint for raw profile data (used by interactive mode)
- Active NWS tornado/severe thunderstorm warning overlay

## Running
```bash
python app.py
# Runs on port 5000
```
