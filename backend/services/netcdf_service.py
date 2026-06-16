import io
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import rasterio
import xarray as xr
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from backend.core.config import CONTINENTS, TEMPERATURE_SOURCES
from backend.core.exceptions import (
    DatasetNotFoundError,
    InvalidTimeIndexError,
    VariableNotFoundError,
)
from backend.models.domain import ColorscaleInfo
from backend.services import storage
from backend.services.aggregation_service import AggregationService
from backend.services.cache_service import temperature_cache

logger = logging.getLogger(__name__)

# HDF5/NetCDF4 is not thread-safe in its default (non-threadsafe) build.
# This lock serialises file open+read so the ThreadPoolExecutor can still
# parallelise cache checks and path resolution without corrupting HDF5 state.
_HDF5_LOCK = threading.Lock()


def _get_data_root(temp_type: str = "mean") -> Path:
    if temp_type not in TEMPERATURE_SOURCES:
        raise ValueError(f"Unknown temperature type: {temp_type}")
    return TEMPERATURE_SOURCES[temp_type]["path"]  # type: ignore[return-value]


def _get_variable(temp_type: str = "mean") -> str:
    if temp_type not in TEMPERATURE_SOURCES:
        raise ValueError(f"Unknown temperature type: {temp_type}")
    return TEMPERATURE_SOURCES[temp_type]["variable"]  # type: ignore[return-value]


def _get_units(temp_type: str = "mean") -> str:
    if temp_type not in TEMPERATURE_SOURCES:
        raise ValueError(f"Unknown temperature type: {temp_type}")
    return TEMPERATURE_SOURCES[temp_type].get("units", "K")  # type: ignore[return-value]


def _build_raster_bytes(
    data: np.ndarray,
    continent: str | None = None,
    zoom_level: int | None = None,
) -> bytes:
    """Clip to bounds, optionally downsample, and encode as GeoTIFF bytes."""
    lat_size, lon_size = data.shape

    if continent and continent in CONTINENTS:
        min_lat, max_lat, min_lon, max_lon = CONTINENTS[continent]
    else:
        min_lat, max_lat, min_lon, max_lon = -60, 90, -180, 180

    lat_indices = np.linspace(90, -90, lat_size)
    lon_indices = np.linspace(-180, 180, lon_size)

    lat_rows = np.where((lat_indices >= min_lat) & (lat_indices <= max_lat))[0]
    lon_cols = np.where((lon_indices >= min_lon) & (lon_indices <= max_lon))[0]

    if len(lat_rows) == 0 or len(lon_cols) == 0:
        clipped = np.full((1, 1), np.nan, dtype=np.float32)
        new_min_lat, new_max_lat = min_lat, max_lat
        new_min_lon, new_max_lon = min_lon, max_lon
    else:
        row_start, row_end = lat_rows[0], lat_rows[-1] + 1
        col_start, col_end = lon_cols[0], lon_cols[-1] + 1

        clipped = data[row_start:row_end, col_start:col_end].astype(np.float32)
        new_max_lat = lat_indices[row_start]
        new_min_lat = lat_indices[row_end - 1]
        new_min_lon = lon_indices[col_start]
        new_max_lon = lon_indices[col_end - 1]

    if zoom_level is not None:
        if zoom_level < 4:
            clipped = clipped[::4, ::4]
            logger.debug(f"Downsampled 4x for zoom {zoom_level}")
        elif zoom_level < 8:
            clipped = clipped[::2, ::2]
            logger.debug(f"Downsampled 2x for zoom {zoom_level}")

    h, w = clipped.shape
    transform = from_bounds(new_min_lon, new_min_lat, new_max_lon, new_max_lat, w, h)

    output = io.BytesIO()
    with rasterio.open(
        output,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=1,
        dtype=clipped.dtype,
        crs=CRS.from_epsg(4326),
        transform=transform,
    ) as dst:
        dst.write(clipped, 1)

    output.seek(0)
    return output.getvalue()


def _build_raster_bytes_preclipped(
    data: np.ndarray,
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    zoom_level: int | None = None,
) -> bytes:
    """Encode a pre-clipped region array as a GeoTIFF without re-clipping."""
    clipped = data.astype(np.float32)

    if zoom_level is not None:
        if zoom_level < 4:
            clipped = clipped[::4, ::4]
        elif zoom_level < 8:
            clipped = clipped[::2, ::2]

    h, w = clipped.shape
    transform = from_bounds(min_lon, min_lat, max_lon, max_lat, w, h)

    output = io.BytesIO()
    with rasterio.open(
        output,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=1,
        dtype=clipped.dtype,
        crs=CRS.from_epsg(4326),
        transform=transform,
    ) as dst:
        dst.write(clipped, 1)

    output.seek(0)
    return output.getvalue()


class NetCDFService:
    @staticmethod
    def resolve_nc_path(date_obj: date, temp_type: str = "mean") -> str | Path:
        data_root = _get_data_root(temp_type)
        date_str: str = date_obj.isoformat().replace("-", "")
        try:
            return storage.find_nc_file(data_root, date_obj.year, date_str)
        except FileNotFoundError:
            logger.error("NetCDF file not found for %s (%s)", date_obj, temp_type)
            raise DatasetNotFoundError(date_obj) from None

    @staticmethod
    def get_temperature_slice(
        date_obj: date,
        time_index: int = 0,
        temp_type: str = "mean",
    ) -> np.ndarray:
        variable = _get_variable(temp_type)
        cache_key = f"{date_obj.isoformat()}_{time_index}_{temp_type}"

        cached = temperature_cache.get(cache_key)
        if cached is not None:
            return cached

        path: Path = NetCDFService.resolve_nc_path(date_obj, temp_type)

        try:
            with (
                _HDF5_LOCK,
                storage.open_nc(path) as nc_src,
                xr.open_dataset(nc_src, engine="netcdf4") as ds,
            ):
                if variable not in ds.data_vars:
                    logger.error(
                        "Variable not found",
                        extra={"variable": variable, "path": str(path)},
                    )
                    raise VariableNotFoundError(variable, str(path))

                data_array = ds[variable]

                if time_index >= data_array.sizes.get("time", 1):
                    logger.error(
                        "Time index out of range",
                        extra={
                            "index": time_index,
                            "max": data_array.sizes.get("time", 1) - 1,
                        },
                    )
                    raise InvalidTimeIndexError(
                        time_index, data_array.sizes.get("time", 1) - 1
                    )

                slice_data: np.ndarray = data_array.isel(time=time_index).values.astype(
                    np.float32
                )

        except FileNotFoundError as exc:
            logger.error("NetCDF file not found", extra={"path": str(path)})
            raise DatasetNotFoundError(date_obj) from exc

        temperature_cache.set(cache_key, slice_data)
        return slice_data

    @staticmethod
    def get_colorscale_info(
        date_obj: date,
        time_index: int = 0,
        temp_type: str = "mean",
    ) -> ColorscaleInfo:
        data: np.ndarray = NetCDFService.get_temperature_slice(
            date_obj, time_index, temp_type
        )
        valid: np.ndarray = data[~np.isnan(data)]
        return ColorscaleInfo(
            min_value=float(np.min(valid)),
            max_value=float(np.max(valid)),
            mean_value=float(np.mean(valid)),
            units=_get_units(temp_type),
        )

    @staticmethod
    def get_raster_bytes(
        date_obj: date,
        time_index: int = 0,
        temp_type: str = "mean",
        continent: str | None = None,
        zoom_level: int | None = None,
    ) -> bytes:
        data: np.ndarray = NetCDFService.get_temperature_slice(
            date_obj, time_index, temp_type
        )
        return _build_raster_bytes(data, continent, zoom_level)

    @staticmethod
    def get_cell_value(
        date_obj: date,
        lat: float,
        lon: float,
        time_index: int = 0,
        temp_type: str = "mean",
    ) -> float:
        data: np.ndarray = NetCDFService.get_temperature_slice(
            date_obj, time_index, temp_type
        )

        lat_idx: int = int((90 - lat) * (data.shape[0] - 1) / 180)
        lon_idx: int = int((lon + 180) * (data.shape[1] - 1) / 360)
        lat_idx = max(0, min(lat_idx, data.shape[0] - 1))
        lon_idx = max(0, min(lon_idx, data.shape[1] - 1))

        value = data[lat_idx, lon_idx]

        if np.isnan(value):
            raise ValueError(f"No data available at lat={lat}, lon={lon}")

        return float(value)

    @staticmethod
    def get_cell_timeseries(
        start_date: date,
        end_date: date,
        lat: float,
        lon: float,
        time_index: int = 0,
        temp_type: str = "mean",
    ) -> list[tuple[date, float]]:
        date_data_pairs = NetCDFService.get_temperature_slice_range(
            start_date, end_date, time_index, temp_type
        )

        timeseries: list[tuple[date, float]] = []

        for date_obj, data in date_data_pairs:
            lat_idx: int = int((90 - lat) * (data.shape[0] - 1) / 180)
            lon_idx: int = int((lon + 180) * (data.shape[1] - 1) / 360)
            lat_idx = max(0, min(lat_idx, data.shape[0] - 1))
            lon_idx = max(0, min(lon_idx, data.shape[1] - 1))

            value = data[lat_idx, lon_idx]
            if not np.isnan(value):
                timeseries.append((date_obj, float(value)))

        if not timeseries:
            raise ValueError(
                f"No valid data available at lat={lat}, lon={lon} for the date range"
            )

        return timeseries

    @staticmethod
    def get_available_dates(temp_type: str = "mean") -> list[str]:
        data_root = _get_data_root(temp_type)
        dates: list[str] = []

        for year in storage.list_year_dirs(data_root):
            for filename in storage.list_nc_files(data_root, year):
                for part in filename.split("_"):
                    if len(part) == 8 and part.isdigit():
                        try:
                            date_obj = date(
                                int(part[:4]), int(part[4:6]), int(part[6:8])
                            )
                            dates.append(date_obj.isoformat())
                            break
                        except (ValueError, IndexError):
                            continue

        return sorted(set(dates))

    @staticmethod
    def get_temperature_slice_range(
        start_date: date,
        end_date: date,
        time_index: int = 0,
        temp_type: str = "mean",
    ) -> list[tuple[date, np.ndarray]]:
        """Load multiple dates in parallel. Returns sorted list of (date, ndarray) tuples."""
        dates: list[date] = []
        current = start_date
        while current <= end_date:
            dates.append(current)
            current += timedelta(days=1)

        results: list[tuple[date, np.ndarray]] = []
        failed_dates: list[tuple[date, str]] = []

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(
                    NetCDFService.get_temperature_slice, d, time_index, temp_type
                ): d
                for d in dates
            }
            for future in futures:
                date_obj = futures[future]
                try:
                    results.append((date_obj, future.result()))
                except Exception as exc:
                    failed_dates.append((date_obj, str(exc)))
                    logger.warning(f"Failed to load date {date_obj}: {exc}")

        if not results:
            failed_summary = "; ".join(
                f"{d.isoformat()}: {err}" for d, err in failed_dates[:3]
            )
            logger.error(
                f"No data available for range {start_date} to {end_date}. Failures: {failed_summary}"
            )
            raise DatasetNotFoundError(start_date)

        if failed_dates:
            logger.info(
                f"Loaded {len(results)}/{len(dates)} dates; skipped {len(failed_dates)} missing"
            )

        return sorted(results, key=lambda x: x[0])

    @staticmethod
    def _get_aggregated_data(
        start_date: date,
        end_date: date,
        aggregation: str,
        time_index: int,
        temp_type: str,
    ) -> np.ndarray:
        """Load, aggregate, and cache the result so zoom changes skip re-aggregation."""
        cache_key = (
            f"agg_{start_date}_{end_date}_{aggregation}_{time_index}_{temp_type}"
        )
        cached = temperature_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Aggregation cache hit: {cache_key}")
            return cached

        date_data_pairs = NetCDFService.get_temperature_slice_range(
            start_date, end_date, time_index, temp_type
        )
        aggregated = AggregationService.aggregate(
            date_data_pairs, aggregation, _get_variable(temp_type)
        )
        temperature_cache.set(cache_key, aggregated.data)
        return aggregated.data

    @staticmethod
    def get_raster_bytes_aggregated(
        start_date: date,
        end_date: date,
        aggregation: str = "min",
        time_index: int = 0,
        temp_type: str = "mean",
        continent: str | None = None,
        zoom_level: int | None = None,
    ) -> bytes:
        data = NetCDFService._get_aggregated_data(
            start_date, end_date, aggregation, time_index, temp_type
        )
        return _build_raster_bytes(data, continent, zoom_level)

    @staticmethod
    def get_colorscale_info_aggregated(
        start_date: date,
        end_date: date,
        aggregation: str = "min",
        time_index: int = 0,
        temp_type: str = "mean",
    ) -> ColorscaleInfo:
        data = NetCDFService._get_aggregated_data(
            start_date, end_date, aggregation, time_index, temp_type
        )
        valid = data[~np.isnan(data)]
        return ColorscaleInfo(
            min_value=float(np.min(valid)),
            max_value=float(np.max(valid)),
            mean_value=float(np.mean(valid)),
            units=_get_units(temp_type),
        )
