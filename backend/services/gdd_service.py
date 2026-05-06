import configparser
import logging
from dataclasses import dataclass
from datetime import date
from typing import NamedTuple

import numpy as np

from backend.core.config import CONTINENTS, CROPS_CONFIG_PATH, TEMPERATURE_SOURCES
from backend.services.cache_service import temperature_cache
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


def get_available_gdd_years() -> list[int]:
    """Return years for which both tmean and tmin season data exist."""
    def _year_folders(temp_type: str) -> set[int]:
        root = TEMPERATURE_SOURCES[temp_type]["path"]
        return {
            int(p.name)
            for p in root.glob("????")  # type: ignore[union-attr]
            if p.is_dir() and p.name.isdigit()
        }

    return sorted(_year_folders("mean") & _year_folders("min"))


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
        cache_key = f"gdd_frost_{year}_{crop.name}"
        cached = temperature_cache.get(cache_key)
        if cached is not None:
            logger.debug("GDD cache hit: %s", cache_key)
            eu_min_lat, eu_max_lat, eu_min_lon, eu_max_lon = CONTINENTS["Europe"]
            return GDDResult(cached, EuropeBounds(eu_min_lat, eu_max_lat, eu_min_lon, eu_max_lon))

        start = date(year, *_SEASON_START)
        end = date(year, *_SEASON_END)

        mean_pairs = NetCDFService.get_temperature_slice_range(start, end, temp_type="mean")
        min_pairs = NetCDFService.get_temperature_slice_range(start, end, temp_type="min")

        mean_by_date = {d: arr for d, arr in mean_pairs}
        min_by_date = {d: arr for d, arr in min_pairs}
        common = sorted(set(mean_by_date) & set(min_by_date))

        if not common:
            raise ValueError(f"No overlapping dates for {year} season")

        # Clip to Europe before stacking — reduces stack size from ~3.7 GB to ~166 MB
        lat_size, lon_size = mean_by_date[common[0]].shape
        r0, r1, c0, c1 = _europe_row_col_slice(lat_size, lon_size)

        tmean_stack = np.stack([mean_by_date[d][r0:r1, c0:c1] for d in common], axis=0)
        tmin_stack = np.stack([min_by_date[d][r0:r1, c0:c1] for d in common], axis=0)

        nan_mask = (
            np.any(np.isnan(tmean_stack), axis=0) | np.any(np.isnan(tmin_stack), axis=0)
        )

        tavg_c = tmean_stack - 273.15
        tmin_c = tmin_stack - 273.15

        gdd_daily = np.maximum(tavg_c - crop.base_temperature, 0.0)
        gdd_accum = np.cumsum(gdd_daily, axis=0)

        sensitive = gdd_accum >= crop.gdd_threshold     # (T, lat, lon)
        ever_sensitive = sensitive.any(axis=0)           # (lat, lon)
        frost = sensitive & (tmin_c < crop.frost_threshold)

        frost_count = frost.sum(axis=0).astype(np.float32)
        frost_count[nan_mask] = np.nan
        # Cells that never warmed enough to reach budbreak
        frost_count[(~ever_sensitive) & (~nan_mask)] = _NEVER_REACHED_BUDBREAK

        temperature_cache.set(cache_key, frost_count)
        logger.info("GDD computed: year=%d crop=%s", year, crop.name)

        # Recover exact lat/lon bounds from the slice we used
        lat_idx = np.linspace(90, -90, lat_size)
        lon_idx = np.linspace(-180, 180, lon_size)
        bounds = EuropeBounds(
            min_lat=float(lat_idx[r1 - 1]),
            max_lat=float(lat_idx[r0]),
            min_lon=float(lon_idx[c0]),
            max_lon=float(lon_idx[c1 - 1]),
        )
        return GDDResult(frost_count, bounds)
