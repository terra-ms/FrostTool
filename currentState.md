# FrostTool — Current State

Last updated: 2026-05-06

---

## What the app is

A geospatial climate visualisation tool built on **AgERA5** daily 2 m air temperature data (NetCDF files). Two pages:

1. **Heatmap** (`/`) — renders a daily or date-range temperature raster on a Leaflet map. Click a cell to get a temperature time-series chart below the map.
2. **Frost Risk** (`/gdd`) — computes per-cell frost event counts (GDD-based) for a selected crop and year, renders the result on a Europe-only Leaflet map.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Uvicorn, port 8000 |
| Frontend | Dash (Plotly) + Dash Bootstrap Components, port 8050 |
| Map rendering | Leaflet 1.9.4 inside `html.Iframe` (srcDoc), `georaster-layer-for-leaflet` for GeoTIFF tiles |
| Data | AgERA5 NetCDF, read with xarray/netcdf4 |
| Raster encoding | rasterio (GeoTIFF via `from_bounds`) |
| Caching | Two-level: in-memory LRU + diskcache (`.cache/`) |

---

## Project structure

```
FrostTool/
├── backend/
│   ├── main.py                     FastAPI app factory, includes both routers
│   ├── core/
│   │   ├── config.py               TEMPERATURE_SOURCES, CONTINENTS, CROPS_CONFIG_PATH
│   │   └── exceptions.py           DatasetNotFoundError, VariableNotFoundError, etc.
│   ├── models/
│   │   ├── domain.py               ColorscaleInfo dataclass
│   │   └── schemas.py              Pydantic response models (incl. GDD models)
│   ├── services/
│   │   ├── netcdf_service.py       NetCDFService: read slices, build GeoTIFF bytes
│   │   ├── gdd_service.py          GDDService: compute frost event counts per cell
│   │   ├── cache_service.py        diskcache + LRU wrapper
│   │   └── aggregation_service.py  min/max/mean aggregation over date ranges
│   └── api/routes/
│       ├── climate.py              /api/v1/* (raster, colorscale, value, timeseries, continents)
│       └── gdd.py                  /api/v1/gdd/* (raster, colorscale, crops, available-years)
├── frontend/
│   ├── app.py                      Dash app (use_pages=True), shared layout
│   ├── config.py                   API_BASE_URL = http://localhost:8000/api/v1
│   ├── pages/
│   │   ├── heatmap.py              Registered at /
│   │   └── gdd.py                  Registered at /gdd
│   ├── components/
│   │   ├── controls.py             create_shared_header(), create_controls(), create_map_frame()
│   │   ├── map_component.py        HTML template + get_map_html() for heatmap iframe
│   │   ├── map.js                  Leaflet + GeoRasterLayer logic for heatmap
│   │   ├── gdd_map_component.py    HTML template + get_gdd_map_html() for GDD iframe
│   │   ├── gdd_map.js              Leaflet + GeoRasterLayer logic for GDD map
│   │   └── timeline_graph.py       Plotly graph container component
│   └── callbacks/
│       ├── map_callbacks.py        Heatmap render, coordinate bridge iframe→Dash
│       ├── graph_callbacks.py      Timeseries chart, date status display
│       └── gdd_callbacks.py        GDD render button → updates iframe srcDoc
├── crops.txt                       INI-format crop parameters (editable without code changes)
└── currentState.md                 This file
```

---

## Data layout (local machine)

```
C:\Olivier\Terra local\data\AgERA5\
├── tmean_v2\
│   └── {YYYY}\   ← years 1979–2022
│       └── *.nc  (one file per day, Temperature_Air_2m_Mean_24h variable)
└── tmin_v2\
    └── {YYYY}\   ← years 1979–2007 only
        └── *.nc  (one file per day, Temperature_Air_2m_Min_24h variable)
```

**Important:** `tmin` only goes to 2007. The GDD year dropdown is therefore limited to years available in BOTH `tmean` and `tmin` folders, determined at runtime by `get_available_gdd_years()`.

---

## Backend API endpoints

### Climate router (`/api/v1`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/raster` | GeoTIFF for a date or date range (min/max/mean aggregation). `zoom_level` param drives downsampling. |
| GET | `/colorscale` | Min/max/mean values for legend scaling |
| GET | `/value` | Single cell temperature at lat/lon/date |
| GET | `/timeseries` | Temperature array across a date range for one cell |
| GET | `/continents` | Bounding boxes for continent zoom |
| GET | `/available-dates` | Sorted list of all available dates |
| GET | `/health` | `{"status": "ok"}` |

### GDD router (`/api/v1/gdd`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/raster` | GeoTIFF frost event count raster for `year` + `crop`. Values: NaN=ocean, -1=never budbreak, 0=no frost, ≥1=count. |
| GET | `/colorscale` | Max frost count for the year (min always 0) |
| GET | `/crops` | List of crop names from `crops.txt` |
| GET | `/available-years` | Years where both tmean and tmin data exist |

---

## GDD algorithm (gdd_service.py)

Season: **1 Jan – 31 May** per year.

1. Load daily `tmean` and `tmin` NetCDF slices for the full season.
2. **Clip to Europe before stacking** — reduces stack from ~3.7 GB to ~166 MB.
3. Compute:
   ```
   gdd_daily  = max(Tavg_celsius - base_temperature, 0)
   gdd_accum  = cumsum(gdd_daily, axis=time)
   sensitive  = gdd_accum >= gdd_threshold          # budbreak reached
   frost      = sensitive & (Tmin_celsius < frost_threshold)
   frost_count = frost.sum(axis=time)               # per cell
   ```
4. Cells where `sensitive` was never True → set to sentinel `-1.0` (never reached budbreak).
5. Ocean/no-data cells stay `NaN`.
6. Result cached in diskcache with key `gdd_frost_{year}_{crop}`.

### Crop parameters (`crops.txt`)

INI format, editable without restarting the server (reloaded per request via `configparser`):

```ini
[grapevine]
display_name = Grapevine
base_temperature = 5
gdd_threshold = 250
frost_threshold = -2

[apple]
display_name = Apple
base_temperature = 4
gdd_threshold = 150
frost_threshold = -2
```

---

## Frontend — Heatmap page (`/`)

- **Sidebar:** continent selector, temperature type (mean/min), date range picker (max 180 days), Render button, stats box.
- **Map iframe:** Leaflet + `georaster-layer-for-leaflet`. Absolute temperature colour scale −40°C (blue) → 50°C (dark red). Click sends `postMessage` to parent Dash frame.
- **Coordinate bridge:** `clientside_callback` listens for `coordinateClicked` postMessage, clicks a hidden button, stores lat/lon/date in `dcc.Store`.
- **Graph panel:** Plotly timeseries chart slides up (25% height) on cell click, shows temperature for the selected date range at the clicked coordinate. Closeable.
- **Zoom refetch:** re-fetches raster at crossing zoom thresholds (4, 8) for adaptive resolution.

---

## Frontend — Frost Risk page (`/gdd`)

- **Sidebar:** crop dropdown (fetched from `/gdd/crops`), year dropdown (fetched from `/gdd/available-years`, newest year default), Render button, status text, legend, methodology note.
- **Map iframe:** Leaflet + `georaster-layer-for-leaflet`, centered on Europe `[52, 15]` zoom 4.
- **Colour scale:**
  - Grey (`rgba(190,190,190,0.60)`) — never reached budbreak
  - Green (`rgba(45,138,78,0.55)`) — budbreak reached, 0 frost events
  - Blue (`rgba(59,130,246,0.75)`) — 1 frost event
  - Orange → dark red (chroma.mix LAB, 0.82 alpha) — 2+ frost events
- **Render flow:** button click → `gdd_callbacks.py` builds URL `/gdd/raster?year=…&crop=…` → replaces iframe `srcDoc` with HTML that auto-calls `window.loadGDDRaster(url, year, crop)` after 100 ms.
- Click sends `gddCoordinateClicked` postMessage (lat/lon only, no further handling yet).

---

## Shared header

72 px tall gradient bar with title, subtitle, and nav links:
- **HEATMAP** → `/`
- **FROST RISK** → `/gdd`

Page layouts use `height: calc(100vh - 72px)` to fill below the header.

---

## Known open issue

**Tile grid visible on the GDD (and heatmap) map.** A rectangular grid matching the `georaster-layer-for-leaflet` canvas tile boundaries is visible on both maps. The grid lines are the CartoDB dark basemap showing through gaps between tiles. This is a known rendering artefact of canvas-based tile layers.

Things that were tried and **did not work** or **made it worse**:
- `padding: 0.1` on `GeoRasterLayer` — wrong option, does nothing for seams
- `transform: scale(1.01)` CSS on `.leaflet-tile-pane canvas` — made the grid intensify with every zoom step (compounds with Leaflet's own zoom transforms)

Things currently in place (partial mitigation only):
- `updateWhenZooming: false` on `GeoRasterLayer` in both `map.js` and `gdd_map.js`

The root cause is still being investigated. The canvas tiles from `georaster-layer-for-leaflet` have sub-pixel gaps that expose the layer behind them. The `transform: scale()` approach is ruled out. Approaches not yet tried include overriding individual tile canvas `width`/`height` in CSS (e.g. `257px` instead of `256px` to create a 1px overlap without using transforms).

---

## How to run

```
# Backend (from project root)
uvicorn backend.main:app --reload --port 8000

# Frontend (from project root)
python -m frontend.app
```

CORS is configured to allow `http://localhost:8050` and `http://127.0.0.1:8050`.

JS files (`map.js`, `gdd_map.js`) are read from disk at **Dash server startup** — restart required after JS changes.
