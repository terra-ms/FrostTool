import configparser
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import NamedTuple

import numpy as np

from backend.core.config import CONTINENTS, CROPS_CONFIG_PATH, PRECOMPUTED_DIR, TEMPERATURE_SOURCES
from backend.services.netcdf_service import NetCDFService

logger = logging.getLogger(__name__)

_SEASON_START = (1, 1)
_SEASON_END = (5, 31)
_NEVER_REACHED_BUDBREAK = -1.0  # sentinel written into the raster


class EuropeBounds(NamedTuple):
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


class GDDResult(NamedTuple):
    frost_count: np.ndarray  # float32 (lat, lon), clipped to Europe
    bounds: EuropeBounds


@dataclass(frozen=True)
class CropParams:
    name: str
    display_name: str
    base_temperature: float
    gdd_threshold: float
    frost_threshold: float


@dataclass
class YearStack:
    """Europe-clipped tmean/tmin daily stacks for a Jan–May season. Crop-agnostic."""

    tmean_stack: np.ndarray  # (T, lat, lon) Kelvin
    tmin_stack: np.ndarray   # (T, lat, lon) Kelvin
    bounds: EuropeBounds
    dates: list[date] = field(default_factory=list)  # length T; older cache entries omit this


@dataclass
class GDDTimeseriesResult:
    season_dates: list[str]
    gdd_accum: np.ndarray   # float64 (T,)
    tmin_c: np.ndarray      # float64 (T,)
    tavg_c: np.ndarray      # float64 (T,)
    budbreak_date: str | None
    frost_event_dates: list[str]


# In-memory caches — populated from disk on first access, survive for the process lifetime.
_year_stack_mem: dict[int, YearStack] = {}
_gdd_result_mem: dict[str, GDDResult] = {}

_available_years: list[int] | None = None


# ---------------------------------------------------------------------------
# Pre-computed file I/O
# ---------------------------------------------------------------------------

def _stack_path(year: int) -> Path:
    return PRECOMPUTED_DIR / "year_stacks" / f"gdd_stack_{year}.npz"


def _result_path(year: int, crop_name: str) -> Path:
    return PRECOMPUTED_DIR / "gdd_results" / f"gdd_frost_{year}_{crop_name}.npz"


def _write_year_stack(path: Path, stack: YearStack) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        tmean_stack=stack.tmean_stack,
        tmin_stack=stack.tmin_stack,
        bounds=np.array(
            [stack.bounds.min_lat, stack.bounds.max_lat, stack.bounds.min_lon, stack.bounds.max_lon],
            dtype=np.float64,
        ),
        dates=np.array([d.isoformat() for d in stack.dates]),
    )
    logger.info("YearStack saved: %s", path)


def _read_year_stack(path: Path) -> YearStack:
    with np.load(path) as data:
        b = data["bounds"]
        bounds = EuropeBounds(float(b[0]), float(b[1]), float(b[2]), float(b[3]))
        dates = [date.fromisoformat(s) for s in data["dates"].tolist()]
        tmean = data["tmean_stack"]
        tmin = data["tmin_stack"]
    return YearStack(tmean_stack=tmean, tmin_stack=tmin, bounds=bounds, dates=dates)


def _write_gdd_result(path: Path, result: GDDResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        frost_count=result.frost_count,
        bounds=np.array(
            [result.bounds.min_lat, result.bounds.max_lat, result.bounds.min_lon, result.bounds.max_lon],
            dtype=np.float64,
        ),
    )
    logger.info("GDDResult saved: %s", path)


def _read_gdd_result(path: Path) -> GDDResult:
    with np.load(path) as data:
        b = data["bounds"]
        bounds = EuropeBounds(float(b[0]), float(b[1]), float(b[2]), float(b[3]))
        frost_count = data["frost_count"]
    return GDDResult(frost_count=frost_count, bounds=bounds)


def get_available_gdd_years() -> list[int]:
    """Return years for which both tmean and tmin season data exist.

    Result is cached in memory for the lifetime of the process. Call this once
    at startup (before the warm-up thread begins disk I/O) to prevent the data-drive
    glob from blocking the Uvicorn async event loop on subsequent requests.
    """
    global _available_years
    if _available_years is not None:
        return _available_years

    def _year_folders(temp_type: str) -> set[int]:
        root = TEMPERATURE_SOURCES[temp_type]["path"]
        return {
            int(p.name)
            for p in root.glob("????")  # type: ignore[union-attr]
            if p.is_dir() and p.name.isdigit()
        }

    _available_years = sorted(_year_folders("mean") & _year_folders("min"))
    return _available_years


def load_crops() -> dict[str, CropParams]:
    parser = configparser.ConfigParser()
    parser.read(CROPS_CONFIG_PATH, encoding="utf-8")
    return {
        section: CropParams(
            name=section,
            display_name=parser.get(section, "display_name", fallback=section.capitalize()),
            base_temperature=parser.getfloat(section, "base_temperature"),
            gdd_threshold=parser.getfloat(section, "gdd_threshold"),
            frost_threshold=parser.getfloat(section, "frost_threshold"),
        )
        for section in parser.sections()
    }


def _europe_row_col_slice(lat_size: int, lon_size: int) -> tuple[int, int, int, int]:
    """Return (r0, r1, c0, c1) index slices for the Europe bounding box."""
    eu_min_lat, eu_max_lat, eu_min_lon, eu_max_lon = CONTINENTS["Europe"]
    lat_idx = np.linspace(90, -90, lat_size)
    lon_idx = np.linspace(-180, 180, lon_size)
    lat_rows = np.where((lat_idx >= eu_min_lat) & (lat_idx <= eu_max_lat))[0]
    lon_cols = np.where((lon_idx >= eu_min_lon) & (lon_idx <= eu_max_lon))[0]
    return int(lat_rows[0]), int(lat_rows[-1]) + 1, int(lon_cols[0]), int(lon_cols[-1]) + 1


def _load_year_stack(year: int) -> YearStack:
    """Load the Europe-clipped tmean+tmin stacks for a full Jan–May season.

    Priority: in-memory → precomputed .npz file → compute from NetCDF (then save).
    The .npz file persists indefinitely; delete it manually to force recomputation.
    """
    if year in _year_stack_mem:
        return _year_stack_mem[year]

    path = _stack_path(year)
    if path.exists():
        stack = _read_year_stack(path)
        _year_stack_mem[year] = stack
        logger.info("YearStack loaded from file: year=%d", year)
        return stack

    start = date(year, *_SEASON_START)
    end = date(year, *_SEASON_END)

    mean_pairs = NetCDFService.get_temperature_slice_range(start, end, temp_type="mean")
    min_pairs = NetCDFService.get_temperature_slice_range(start, end, temp_type="min")

    mean_by_date = {d: arr for d, arr in mean_pairs}
    min_by_date = {d: arr for d, arr in min_pairs}
    common = sorted(set(mean_by_date) & set(min_by_date))

    if not common:
        raise ValueError(f"No overlapping tmean/tmin dates for {year} season")

    lat_size, lon_size = mean_by_date[common[0]].shape
    r0, r1, c0, c1 = _europe_row_col_slice(lat_size, lon_size)

    tmean_stack = np.stack([mean_by_date[d][r0:r1, c0:c1] for d in common], axis=0)
    tmin_stack = np.stack([min_by_date[d][r0:r1, c0:c1] for d in common], axis=0)

    lat_idx = np.linspace(90, -90, lat_size)
    lon_idx = np.linspace(-180, 180, lon_size)
    bounds = EuropeBounds(
        min_lat=float(lat_idx[r1 - 1]),
        max_lat=float(lat_idx[r0]),
        min_lon=float(lon_idx[c0]),
        max_lon=float(lon_idx[c1 - 1]),
    )

    stack = YearStack(tmean_stack=tmean_stack, tmin_stack=tmin_stack, bounds=bounds, dates=common)
    _write_year_stack(path, stack)
    _year_stack_mem[year] = stack
    logger.info("YearStack computed and saved: year=%d shape=%s", year, tmean_stack.shape)
    return stack


def warm_year_stack(year: int) -> None:
    """Ensure the precomputed .npz file exists for a year's stack. Idempotent."""
    _load_year_stack(year)


class GDDService:
    @staticmethod
    def compute_frost_event_count(year: int, crop: CropParams) -> GDDResult:
        """
        Per grid cell (Europe only): count days in Jan–May where accumulated GDD exceeded
        the budbreak threshold AND Tmin dropped below the frost threshold.

        Encoding in the returned float32 array:
          NaN  → ocean / no-data
          -1   → never reached budbreak GDD threshold (too cold for crop to develop)
           0   → reached budbreak but no frost events
          ≥1   → number of frost events during the sensitive period
        """
        mem_key = f"{year}_{crop.name}"
        if mem_key in _gdd_result_mem:
            return _gdd_result_mem[mem_key]

        path = _result_path(year, crop.name)
        if path.exists():
            result = _read_gdd_result(path)
            _gdd_result_mem[mem_key] = result
            logger.info("GDDResult loaded from file: year=%d crop=%s", year, crop.name)
            return result

        stack = _load_year_stack(year)

        nan_mask = (
            np.any(np.isnan(stack.tmean_stack), axis=0)
            | np.any(np.isnan(stack.tmin_stack), axis=0)
        )

        tavg_c = stack.tmean_stack - 273.15
        tmin_c = stack.tmin_stack - 273.15

        gdd_daily = np.maximum(tavg_c - crop.base_temperature, 0.0)
        gdd_accum = np.cumsum(gdd_daily, axis=0)

        sensitive = gdd_accum >= crop.gdd_threshold
        ever_sensitive = sensitive.any(axis=0)
        frost = sensitive & (tmin_c < crop.frost_threshold)

        frost_count = frost.sum(axis=0).astype(np.float32)
        frost_count[nan_mask] = np.nan
        frost_count[(~ever_sensitive) & (~nan_mask)] = _NEVER_REACHED_BUDBREAK

        result = GDDResult(frost_count, stack.bounds)
        _write_gdd_result(path, result)
        _gdd_result_mem[mem_key] = result
        logger.info("GDDResult computed and saved: year=%d crop=%s", year, crop.name)
        return result


def get_gdd_timeseries(
    lat: float,
    lon: float,
    year: int,
    crop: CropParams,
) -> GDDTimeseriesResult:
    """Return daily GDD accumulation + Tmin series for a single Europe grid cell.

    Uses the cached YearStack so this is fast when the stack is already warm.
    Raises ValueError for ocean cells or coordinates outside the Europe extent.
    """
    stack = _load_year_stack(year)
    bounds = stack.bounds

    if not (bounds.min_lat <= lat <= bounds.max_lat and bounds.min_lon <= lon <= bounds.max_lon):
        raise ValueError(
            f"Coordinates ({lat}, {lon}) are outside the Europe dataset bounds "
            f"(lat {bounds.min_lat}–{bounds.max_lat}, lon {bounds.min_lon}–{bounds.max_lon})"
        )

    n_days = stack.tmean_stack.shape[0]
    lat_size = stack.tmean_stack.shape[1]
    lon_size = stack.tmean_stack.shape[2]

    # Reconstruct coordinate arrays — lat decreases top-to-bottom, lon increases left-to-right.
    lat_arr = np.linspace(bounds.max_lat, bounds.min_lat, lat_size)
    lon_arr = np.linspace(bounds.min_lon, bounds.max_lon, lon_size)
    row = int(np.argmin(np.abs(lat_arr - lat)))
    col = int(np.argmin(np.abs(lon_arr - lon)))

    tmean_series = stack.tmean_stack[:, row, col]
    tmin_series = stack.tmin_stack[:, row, col]

    if np.any(np.isnan(tmean_series)) or np.any(np.isnan(tmin_series)):
        raise ValueError("Selected cell contains no data (ocean or missing)")

    tavg_c = tmean_series - 273.15
    tmin_c = tmin_series - 273.15
    gdd_daily = np.maximum(tavg_c - crop.base_temperature, 0.0)
    gdd_accum = np.cumsum(gdd_daily)

    # Use stored dates when available; fall back to consecutive days from Jan 1.
    stored = getattr(stack, "dates", None)
    if stored:
        season_dates = [d.isoformat() for d in stored]
    else:
        season_dates = [
            (date(year, 1, 1) + timedelta(days=i)).isoformat() for i in range(n_days)
        ]

    budbreak_idx = np.where(gdd_accum >= crop.gdd_threshold)[0]
    budbreak_date = season_dates[budbreak_idx[0]] if len(budbreak_idx) > 0 else None

    sensitive = gdd_accum >= crop.gdd_threshold
    frost = sensitive & (tmin_c < crop.frost_threshold)
    frost_event_dates = [season_dates[i] for i in range(n_days) if frost[i]]

    logger.debug(
        "GDD timeseries: year=%d crop=%s lat=%.4f lon=%.4f budbreak=%s frost_events=%d",
        year, crop.name, lat, lon, budbreak_date, len(frost_event_dates),
    )
    return GDDTimeseriesResult(
        season_dates=season_dates,
        gdd_accum=gdd_accum,
        tmin_c=tmin_c,
        tavg_c=tavg_c,
        budbreak_date=budbreak_date,
        frost_event_dates=frost_event_dates,
    )
