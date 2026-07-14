# Claude Code Instructions

> **This file covers conventions, invariants, and gotchas.** For the current app state —
> endpoints, GDD algorithm details, S3/Fargate deployment, CI/CD, and open issues —
> see **`currentState.md`** at the project root. When the two disagree, `currentState.md` wins.

## Project Overview

Full-stack geospatial data application for visualising global climate data from NetCDF (`.nc`) files. The backend is a **FastAPI** REST API; the frontend is a **Dash** app rendering interactive **Leaflet** heatmaps via `georaster-layer-for-leaflet`. Two pages: **Heatmap** (`/`, global temperature rasters) and **Frost Risk** (`/gdd`, per-crop GDD-based frost event counts over Europe).

The app is **deployed on AWS Fargate** (cluster `frosttool-cluster`, region `us-east-1`) behind an ALB, reading data from **S3** (`frosttool-data`). All backend file I/O goes through the local/S3 storage abstraction in `backend/services/storage.py`, switched by the `S3_BUCKET` env var (unset = local mode). The architecture must remain fast and expandable.

**Running locally:**
- Backend: `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000` (from project root with `PYTHONPATH=.`)
- Frontend: `python -m frontend.app` (Dash on port 8050)
- Backend must be running before starting the frontend.
- Or `docker compose up --build` (see `currentState.md` for the `.env` setup).

---

## Tech Stack

| Layer     | Technology                                              |
|-----------|---------------------------------------------------------|
| Backend   | Python 3.11+, FastAPI, Uvicorn                          |
| Data I/O  | xarray, netCDF4, numpy, rasterio                        |
| Frontend  | Dash (Plotly), dash-leaflet, georaster-layer-for-leaflet|
| Caching (climate) | Two-level: in-memory LRU (60 entries) + diskcache (20 GB) — heatmap raster slices |
| Caching (GDD)     | In-memory dict + precomputed `.npz` files in `AgERA5/precomputed/` — no TTL, no expiry |
| Storage   | `backend/services/storage.py` — local `pathlib` or S3 via `s3fs` (`S3_BUCKET` env var) |
| Deployment| Docker (backend + frontend images), AWS Fargate + ALB, GitHub Actions (`.github/workflows/deploy.yml`) |
| Testing   | pytest, httpx (async FastAPI tests)                     |
| Linting   | ruff, black, mypy (strict)                              |

---

## Project Structure

```
project-root/
├── backend/
│   ├── main.py                     # FastAPI app factory + lifespan GDD warm-up
│   ├── api/
│   │   ├── routes/
│   │   │   ├── climate.py          # /api/v1/* — raster, colorscale, value, timeseries, continents
│   │   │   ├── gdd.py              # /api/v1/gdd/* — raster, colorscale, crops, available-years, timeseries
│   │   │   └── debug.py            # /api/v1/debug/s3 — S3 connectivity diagnostic
│   │   └── dependencies.py         # Shared FastAPI dependencies
│   ├── services/
│   │   ├── netcdf_service.py       # NetCDF slice reads, GeoTIFF encoding, _HDF5_LOCK
│   │   ├── gdd_service.py          # GDD computation + YearStack/GDDResult .npz persistence
│   │   ├── aggregation_service.py  # min/max/mean aggregation over date ranges
│   │   ├── cache_service.py        # Two-level temperature cache (LRU + diskcache)
│   │   └── storage.py              # Local/S3 file I/O abstraction (S3_BUCKET switch)
│   ├── models/
│   │   ├── schemas.py              # Pydantic request/response models
│   │   └── domain.py               # Internal domain dataclasses
│   ├── static/                     # Natural Earth border GeoJSONs (served at /api/v1/static)
│   └── core/
│       ├── config.py               # TEMPERATURE_SOURCES, PRECOMPUTED_DIR, S3_BUCKET, GDD_WARMUP_MIN_YEAR, …
│       └── exceptions.py           # Custom exception types
├── frontend/
│   ├── app.py                      # Dash app (use_pages=True), shared layout
│   ├── config.py                   # API URLs (REACT_APP_API_URL / PUBLIC_API_URL), UI constants
│   ├── pages/
│   │   ├── heatmap.py              # Heatmap page (/)
│   │   └── gdd.py                  # Frost Risk page (/gdd)
│   ├── components/
│   │   ├── map_component.py        # Heatmap iframe HTML template
│   │   ├── map.js                  # Leaflet + GeoRasterLayer logic (heatmap)
│   │   ├── gdd_map_component.py    # GDD iframe HTML template
│   │   ├── gdd_map.js              # Leaflet + GeoRasterLayer logic (GDD)
│   │   ├── timeline_graph.py       # Timeline/graph component
│   │   └── controls.py             # Shared header, sidebar controls, map frame
│   ├── utils.py                    # Shared helpers (e.g. kelvin_to_celsius)
│   └── callbacks/
│       ├── map_callbacks.py        # Heatmap render, coordinate bridge, continent/temp-type selection
│       ├── graph_callbacks.py      # Timeseries graph (triggered by map coordinate click)
│       └── gdd_callbacks.py        # GDD dropdowns, render, coordinate bridge, GDD timeseries
├── crops.txt                       # INI-format crop parameters (editable live, reloaded per request)
├── preprocess_gdd.py               # Standalone: recompute GDD .npz locally, then sync to S3
├── download_geodata.py             # Fetch/clip Natural Earth border GeoJSONs
├── scripts/simplify_borders.py     # Simplify border geometries
├── docker-compose.yml              # Local two-container run (backend/Dockerfile, frontend/Dockerfile)
├── tests/
│   ├── backend/
│   └── frontend/
├── currentState.md                 # Living doc: app state, endpoints, deployment, open issues
└── .github/
    └── workflows/deploy.yml        # lint-and-test → build-and-push (ECR) → deploy (ECS)
```

---

## Coding Conventions

### Core Principles

| Principle | Rule |
|-----------|------|
| **DRY** | Never duplicate logic. Extract repeated patterns into shared utilities or base classes. |
| **SRP** | Every module, class, and function has exactly one reason to change. Services handle logic; routes handle HTTP; components handle rendering only. |
| **YAGNI** | Do not add abstractions, parameters, or features until they are actually needed. No speculative generality. |
| **KISS** | Prefer simple, readable solutions. Complexity must be justified by a concrete requirement. |
| **OCP** | Design for extension without modification. New climate parameters must be addable without touching existing route/service code. |

### Python Style

- Follow **PEP 8**; enforced by `ruff` and `black` (line length: 88).
- Use **type hints everywhere** — all function signatures, class attributes, and return types.
- Use `mypy --strict`; fix all errors before committing.
- Prefer **`dataclasses`** or **Pydantic models** over plain dicts for structured data.
- Avoid mutable default arguments. Never use `def f(x=[])`.

```python
# Good
def get_temperature_slice(
    path: Path,
    time_index: int,
    variable: str = "Temperature_Air_2m_Mean_24h",
) -> np.ndarray:
    ...

# Bad — no types, magic variable name
def get_data(p, t):
    ...
```

### FastAPI Conventions

- Use **APIRouter** per domain; never add routes directly to the `FastAPI()` instance.
- All endpoints must declare **response models** via `response_model=`.
- Use **dependency injection** (`Depends`) for shared resources (DB sessions, config, caches).
- Raise `HTTPException` only in route handlers. Services raise domain exceptions (see `core/exceptions.py`); routes convert them.
- Async endpoints (`async def`) for I/O-bound routes; sync (`def`) only for CPU-heavy operations offloaded to a thread pool.

```python
# Good
router = APIRouter(prefix="/climate", tags=["climate"])

@router.get("/temperature", response_model=TemperatureResponse)
async def get_temperature(
    time_index: int = Query(..., ge=0),
    service: NetCDFService = Depends(get_netcdf_service),
) -> TemperatureResponse:
    ...
```

### Dash / Frontend Conventions

- Each **page** owns its layout function; each **component** is a pure function returning a Dash element.
- Callbacks live in `callbacks/` and are registered via a `register_callbacks(app)` function — never inline in layout files.
- Callbacks must be **lean**: fetch data from the API, transform minimally, return to component. Heavy logic belongs in a service or utility module.
- Use `dcc.Store` for shared client-side state between callbacks.
- Avoid `global` variables in Dash; use `diskcache` or server-side sessions for cross-request state.

### NetCDF / Data Processing

- Open NetCDF files with `xarray.open_dataset(path, engine="netcdf4")` — **without** `chunks={}`. Dask lazy-loading was removed because `.values` must be called inside the `_HDF5_LOCK` to guarantee thread safety with `ThreadPoolExecutor`.
- All file reads must be wrapped in `_HDF5_LOCK` (defined in `netcdf_service.py`). HDF5/NetCDF4 is not thread-safe; the lock serialises opens so parallel cache-miss loads don't corrupt state.
- Close datasets explicitly or use context managers; never leave file handles open.
- Clip, downsample, or slice data **server-side** before sending to the frontend — never ship a raw full-resolution grid to the browser.
- Cache expensive computed slices using `temperature_cache` (two-level: memory LRU + diskcache). This is for **climate/heatmap data only**. Each global slice is ~25 MB; the diskcache `size_limit` is set to **20 GB** — do not lower it or large date ranges will cause evictions and make every timeseries click slow.
- **GDD data uses a separate file-based persistence layer** — `YearStack` and `GDDResult` are stored as `.npz` files in `AgERA5/precomputed/` (path configured by `PRECOMPUTED_DIR` in `core/config.py`). Do **not** route GDD data through `temperature_cache`; it has a 1-hour TTL which would cause the warm-up to re-run on every restart.

### Naming Conventions

| Context            | Convention           | Example                          |
|--------------------|----------------------|----------------------------------|
| Files/modules      | `snake_case`         | `netcdf_service.py`              |
| Classes            | `PascalCase`         | `NetCDFService`                  |
| Functions/methods  | `snake_case`         | `get_temperature_slice()`        |
| Constants          | `UPPER_SNAKE_CASE`   | `DATA_ROOT`, `VARIABLE`          |
| Pydantic schemas   | `PascalCase` + noun  | `TemperatureRequest`             |
| Dash component IDs | `kebab-case`         | `"heatmap-layer"`, `"time-slider"` |
| API routes         | Plural nouns         | `/climate/temperatures`          |

---

## Data Source & Layout

### Dataset

The application uses **AgERA5** daily climate rasters. Two temperature variables are supported:

| Key    | NetCDF variable name                  | Local data root (default)                              |
|--------|---------------------------------------|--------------------------------------------------------|
| `mean` | `Temperature_Air_2m_Mean_24h`         | `C:\Olivier\Terra local\data\AgERA5\tmean_v2`          |
| `min`  | `Temperature_Air_2m_Min_24h`          | `C:\Olivier\Terra local\data\AgERA5\tmin_v2`           |

Local data: `tmean` covers **1979–2022**, `tmin` only **1979–2007** (test dataset). The full dataset lives in **S3** (`s3://frosttool-data/`, same folder layout). The GDD year dropdown only offers years present in **both** variables. All values are in **Kelvin**; the frontend converts to °C for display.

### Directory Layout on Disk (actual)

```
DATA_ROOT/
└── YYYY/
    └── <filename_containing_YYYYMMDD>.nc
```

**Important:** there is no `MM/` subfolder. Files sit directly under the year folder. The date in the filename uses `YYYYMMDD` format (no hyphens).

Real example:
```
C:\Olivier\Terra local\data\AgERA5\tmean_v2\
└── 2020\
    └── Temperature-Air-2m_Mean-24h_C3S-glob-agric_AgERA5_20200101_final-v2.0.0.nc
```

### Configuration (`core/config.py`)

Data roots and variable names are centralised in `TEMPERATURE_SOURCES`. Backend env vars: `DATA_ROOT_MEAN`, `DATA_ROOT_MIN`, `CACHE_DIR`, `PRECOMPUTED_DIR`, `S3_BUCKET`, `CROPS_CONFIG`, `GDD_WARMUP_MIN_YEAR` (default **2015**). Never read `os.environ` or construct data paths in backend code outside of `core/config.py` and `services/storage.py`. Frontend config lives in `frontend/config.py` (`REACT_APP_API_URL` for server-side calls, `PUBLIC_API_URL` for browser/iframe JS).

In **S3 mode** (`S3_BUCKET` set), `DATA_ROOT_MEAN`/`DATA_ROOT_MIN`/`PRECOMPUTED_DIR` only need the folder name (e.g. `tmean_v2`) — the last path component becomes the S3 key prefix.

### File Resolution

`NetCDFService.resolve_nc_path` (`netcdf_service.py`) is a thin wrapper that delegates to `storage.find_nc_file(data_root, year, date_str)`, which returns a local `Path` in local mode or an `s3://...` URL string in S3 mode. **Do not build NetCDF paths anywhere else** — all file I/O (glob, open, npz load/save) goes through `backend/services/storage.py`.

- The match pattern is `YYYYMMDD` (hyphens stripped), matching the real filenames.
- API endpoints accept dates as `YYYY-MM-DD` strings; parse to `datetime.date` in the route before passing to the service.
- If multiple files match the same date, log a warning and use the first match.
- Opening: `storage.open_nc(path)` is a context manager — in S3 mode it downloads to a temp file first (the NetCDF4 C library cannot open `s3://` URLs). Always use it together with `_HDF5_LOCK`.

### What NOT to Do (data-specific)

- Do not add a `MM/` subfolder level — the actual layout has none.
- Do not use `date.isoformat()` directly as the glob pattern; strip hyphens first (`replace("-", "")`).
- Do not scan `DATA_ROOT` recursively at startup; resolve paths lazily per request.
- Do not commit any `.nc` files or reference absolute local paths outside `core/config.py`.

---

## Expandability Rules

These rules exist so that new parameters (wind, precipitation, soil moisture) and new features (crop damage, timeline graphs) can be added without architectural rewrites.

1. **Parameter-agnostic services**: `NetCDFService` must accept a `variable: str` argument. Never hard-code `"Temperature_Air_2m_Mean_24h"` (or any variable name) outside of `core/config.py`.
2. **Config-driven file paths**: All `.nc` file paths and variable-to-file mappings live in `core/config.py` (loaded from environment variables or a `.env` file). No hardcoded paths elsewhere. See **Data Source & Layout** section for the canonical path-resolution rules.
3. **Pluggable aggregation**: `AggregationService` must accept a region geometry (GeoJSON) and a variable name. New aggregation methods (mean, max, weighted crop-damage index) are added as strategy functions, not as branching conditionals.
4. **Component isolation**: Each Dash component accepts only the data it needs as props — no component reaches into another component's state.
5. **Versioned API**: All routes are prefixed `/api/v1/`. Breaking changes increment the version; old versions are deprecated, not deleted immediately.

---

## Performance Guidelines

- **Lazy-load** NetCDF files; never load an entire file into memory upfront.
- **Downsample** grids to match the current map zoom level (coarser grid at low zoom, finer at high zoom).
- **Cache** processed tiles and aggregation results with `temperature_cache` (climate/heatmap only). Cache keys for individual slices: `"{date}_{time_index}_{temp_type}"`. Cache keys for aggregations: `"agg_{start}_{end}_{agg}_{time_index}_{temp_type}"`. The aggregation key is shared between `/raster` and `/colorscale` via `_get_aggregated_data()` — both endpoints hit the same cached numpy array.
- **GDD artifacts** (`YearStack`, `GDDResult`) are persisted as `.npz` files — see `gdd_service.py`. Lookup order: in-memory dict → `.npz` file → compute from NetCDF + save. Deleting a `.npz` file forces recomputation of that artifact.
- **Expected timings (local SSD):** first render of an uncached date range loads from NC files (~200 ms/file serialised through `_HDF5_LOCK`); second render and timeseries are disk-cache hits (~100 ms/entry) or memory hits (~1 ms/entry). For a 180-day range, first render ≈ 36 s; subsequent ≈ 3–7 s.
- Use `numpy` vectorised operations — avoid Python-level loops over grid cells.
- Prefer `float32` over `float64` for grid arrays sent to the frontend.
- Profile with `py-spy` or `cProfile` before optimising; do not pre-optimise without evidence of a bottleneck.

---

## Error Handling

- Define all custom exceptions in `core/exceptions.py` (e.g., `DatasetNotFoundError`, `VariableNotFoundError`, `InvalidTimeIndexError`).
- Services raise domain exceptions; routes catch them and return the appropriate `HTTPException`.
- Never swallow exceptions silently with bare `except: pass`.
- All exceptions must be **logged** with context (file path, variable, index) before re-raising or converting.

```python
# Good
try:
    ds = xr.open_dataset(path)
except FileNotFoundError as exc:
    logger.error("NetCDF file not found", extra={"path": str(path)})
    raise DatasetNotFoundError(path) from exc
```

---

## Testing

- Minimum **80% coverage** on all service modules.
- Use `pytest` fixtures for shared test data (small synthetic `.nc` files, not production data).
- Test FastAPI routes with `httpx.AsyncClient` + `pytest-anyio`.
- Test Dash callbacks with `dash.testing` or by unit-testing callback functions directly (extract logic out of the callback decorator).
- All tests must pass before merging to `main`.

---

## Git & Commit Conventions

- Branch names: `feature/<short-description>`, `fix/<short-description>`, `chore/<short-description>`.
- Commit messages follow **Conventional Commits**: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`.
- No commits directly to `main`; all changes via pull requests.
- Each PR should change one thing — do not mix feature work with refactoring.

---

## Frontend: Map ↔ Dash Coordinate Bridge

The Leaflet map runs inside an `<iframe>` (`srcDoc`). To relay a map click to Dash callbacks:

1. `map.js` fires `window.parent.postMessage({ type: 'coordinateClicked', lat, lon, date, dateRange }, '*')` on click.
2. A `clientside_callback` in `map_callbacks.py` listens for the message and writes to the `coordinate-intermediate` store.
3. A server-side `@callback` copies `coordinate-intermediate` → `clicked-coordinate`.
4. `graph_callbacks.update_timeseries_graph` triggers on `clicked-coordinate` and reads the date range from the `raster-trigger` store (set by the last "Render Heatmap" click).

The Leaflet map also has a `postMessage` listener for `{ type: 'loadRaster' }` commands from the parent frame, used for future optimisation (load raster without regenerating the full iframe `srcDoc`).

---

## GDD (Growing Degree Days) — Implemented

GDD is fully implemented. Key facts for future work:

- **Season:** 1 Jan – 31 May per year (Europe clip only).
- **Algorithm:** `gdd_daily = max(Tavg_celsius − base_temp, 0)`; `frost_count` = days where `gdd_accum >= gdd_threshold` AND `Tmin < frost_threshold`.
- **Timeseries graph axes:** left (blue) = daily Tmin + frost threshold; right (green) = cumulative GDD + budbreak threshold. This is intentional — do not swap back.
- **Persistence:** `YearStack` and `GDDResult` stored as `.npz` files in `PRECOMPUTED_DIR`. Lookup order: in-memory dict → `.npz` file → compute from NetCDF + save.
- **Crop config:** `crops.txt` (INI format). Reloaded per request. If parameters change, delete affected `gdd_frost_{year}_{crop}.npz` files manually.

**Known open bug — GDD map intermittent missing tile:**
When zooming out on the `/gdd` map, a vertical band at roughly 0°–22.5°E (one Leaflet tile at zoom 4) occasionally fails to render. Root cause is likely a tile invalidation race condition in `georaster-layer-for-leaflet`. Attempted: removing `zoom_level` from raster URL, setting `updateWhenZooming: true`. Neither fixed it. Next things to try: `keepBuffer: 4`, calling `currentLayer.redraw()` after zoom ends, or refetching the raster layer on zoom threshold crossings (like the heatmap page does).

---

## What NOT to Do

- Do not mix data-processing logic into route handlers or Dash callbacks.
- Do not load entire NetCDF datasets eagerly at startup.
- Do not hardcode file paths, variable names, or CRS values anywhere except `config.py` / constants.
- Do not add configuration options or abstraction layers "just in case" (YAGNI).
- Do not use `Any` in type hints without a comment explaining why it is unavoidable.
- Do not create God-classes or God-modules; if a file exceeds ~300 lines, split it.
- Do not return raw numpy arrays from API endpoints — always serialise to a defined Pydantic schema or a tiled binary format.
- Do not lower the diskcache `size_limit` below 20 GB — each global raster slice is ~25 MB and a 180-day range needs ~4.5 GB per temperature type.
- Do not remove `_HDF5_LOCK` from `netcdf_service.py` — concurrent HDF5 reads without it will corrupt file state under `ThreadPoolExecutor`.
- Do not route GDD data (`YearStack`, `GDDResult`) through `temperature_cache` — it has a 1-hour TTL that would silently expire precomputed data and re-trigger the full warm-up on every restart. GDD persistence uses `.npz` files in `PRECOMPUTED_DIR`.
- If crop parameters in `crops.txt` are changed, manually delete the affected `gdd_frost_{year}_{crop}.npz` files — the filename does not encode crop parameters, so stale files will not be detected automatically.
