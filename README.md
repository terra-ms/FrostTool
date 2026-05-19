# FrostTool

A geospatial climate visualisation tool for AgERA5 daily temperature data. Two pages:

- **Heatmap** (`/`) — interactive temperature raster for any date or date range (up to 180 days). Click a cell for a timeseries chart.
- **Frost Risk** (`/gdd`) — per-cell frost event count for a selected crop and year, Europe only. Click a cell for a dual-axis GDD accumulation + Tmin chart with budbreak and frost event indicators.

---

## Quick start

Both services must run from the **project root** with `PYTHONPATH=.`.

```bash
# Backend (FastAPI, port 8000)
uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Frontend (Dash, port 8050)
python -m frontend.app
```

Open http://localhost:8050

API docs: http://localhost:8000/docs

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Data I/O | xarray, netCDF4, numpy, rasterio |
| Frontend | Dash (Plotly), Dash Bootstrap Components |
| Map | Leaflet 1.9.4 inside `html.Iframe`, georaster-layer-for-leaflet |
| Caching (climate) | Two-level: in-memory LRU (60 entries) + diskcache 20 GB |
| Caching (GDD) | In-memory dict + precomputed `.npz` files (no expiry) |
| Testing | pytest, httpx (async) |
| Linting | ruff, black, mypy --strict |

---

## Data

AgERA5 daily rasters stored locally at `C:\Olivier\Terra local\data\AgERA5\`:

| Variable | Path | Years available |
|---|---|---|
| `Temperature_Air_2m_Mean_24h` | `tmean_v2\{YYYY}\*.nc` | 1979–2022 |
| `Temperature_Air_2m_Min_24h` | `tmin_v2\{YYYY}\*.nc` | 1979–2007 (test dataset) |

GDD precomputed artifacts live alongside the data in `precomputed\` — generated on first run, loaded from disk on all subsequent startups.

---

## Project structure

```
FrostTool/
├── backend/
│   ├── main.py                  FastAPI app + lifespan warm-up
│   ├── core/
│   │   ├── config.py            TEMPERATURE_SOURCES, CONTINENTS, PRECOMPUTED_DIR, GDD_WARMUP_MIN_YEAR
│   │   └── exceptions.py        Domain exception types
│   ├── models/
│   │   ├── domain.py            ColorscaleInfo dataclass
│   │   └── schemas.py           Pydantic response models
│   ├── services/
│   │   ├── netcdf_service.py    NetCDF I/O, GeoTIFF encoding
│   │   ├── gdd_service.py       GDD computation, .npz persistence, timeseries
│   │   ├── cache_service.py     diskcache + LRU wrapper (climate data only)
│   │   └── aggregation_service.py  min/max/mean aggregation
│   └── api/routes/
│       ├── climate.py           /api/v1/* endpoints
│       └── gdd.py               /api/v1/gdd/* endpoints
├── frontend/
│   ├── app.py                   Dash app factory (use_pages=True)
│   ├── config.py                API_BASE_URL
│   ├── pages/
│   │   ├── heatmap.py           Registered at /
│   │   └── gdd.py               Registered at /gdd
│   ├── components/
│   │   ├── controls.py          Shared header + sidebar controls
│   │   ├── map_component.py     Heatmap iframe HTML template
│   │   ├── map.js               Leaflet logic for heatmap
│   │   ├── gdd_map_component.py GDD iframe HTML template
│   │   └── gdd_map.js           Leaflet logic for GDD map
│   └── callbacks/
│       ├── map_callbacks.py     Heatmap render + coordinate bridge
│       ├── graph_callbacks.py   Temperature timeseries chart
│       └── gdd_callbacks.py     GDD dropdowns, render, coordinate bridge, GDD timeseries
├── crops.txt                    Crop parameters (INI format, editable live)
├── CLAUDE.md                    Architecture and coding conventions for Claude Code
└── currentState.md              Detailed current state, known issues, and next priorities
```

---

## Configuration

All paths and variable names are in `backend/core/config.py`. Override via environment variables:

| Env var | Default | Purpose |
|---|---|---|
| `DATA_ROOT_MEAN` | `…\AgERA5\tmean_v2` | tmean NetCDF root |
| `DATA_ROOT_MIN` | `…\AgERA5\tmin_v2` | tmin NetCDF root |
| `PRECOMPUTED_DIR` | `…\AgERA5\precomputed` | GDD `.npz` artifact storage |
| `CACHE_DIR` | `.cache` | diskcache directory |
| `GDD_WARMUP_MIN_YEAR` | `2005` | Earliest year pre-warmed at startup |

---

## Crop parameters

Edit `crops.txt` without restarting the server. If you change a crop's parameters, delete the affected `gdd_frost_{year}_{crop}.npz` files to force recomputation.

```ini
[grapevine]
display_name = Grapevine
base_temperature = 5
gdd_threshold = 250
frost_threshold = -2
```

---

## First-run note

On first startup with no precomputed files, the backend warm-up reads ~302 NetCDF files per year and saves compressed `.npz` artifacts. Expect ~60 s per year (for 2005–2007: ~8–10 min total). All subsequent startups load from disk in seconds. The app serves requests immediately; only the first render of an uncomputed year is slow.
