"""Unit tests for NetCDFService, AggregationService, and TemperatureCache."""
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from tests.conftest import VARIABLE, TEST_DATE, make_nc_file

# Patch target for the config dict used inside netcdf_service
_SOURCES_TARGET = "backend.services.netcdf_service.TEMPERATURE_SOURCES"


def _sources(path: Path, variable: str = VARIABLE) -> dict:
    return {
        "mean": {"path": path, "variable": variable, "label": "Mean (24h)"},
    }


# ---------------------------------------------------------------------------
# TemperatureCache
# ---------------------------------------------------------------------------

class TestTemperatureCache:
    def test_miss_returns_none(self, tmp_path) -> None:
        from backend.services.cache_service import TemperatureCache

        cache = TemperatureCache(ttl_seconds=60, cache_dir=tmp_path)
        assert cache.get("nonexistent") is None

    def test_set_and_get(self, tmp_path) -> None:
        from backend.services.cache_service import TemperatureCache

        cache = TemperatureCache(ttl_seconds=60, cache_dir=tmp_path)
        arr = np.array([1.0, 2.0], dtype=np.float32)
        cache.set("k", arr)
        result = cache.get("k")
        assert result is not None
        np.testing.assert_array_equal(result, arr)

    def test_expired_entry_returns_none(self, tmp_path) -> None:
        from backend.services.cache_service import TemperatureCache

        cache = TemperatureCache(ttl_seconds=0, cache_dir=tmp_path)
        cache.set("k", np.array([1.0]))
        assert cache.get("k") is None


# ---------------------------------------------------------------------------
# AggregationService
# ---------------------------------------------------------------------------

class TestAggregationService:
    def test_min_aggregation(self) -> None:
        from backend.services.aggregation_service import AggregationService

        d1 = date(2020, 1, 1)
        d2 = date(2020, 1, 2)
        arr1 = np.array([[270.0, 280.0]], dtype=np.float32)
        arr2 = np.array([[260.0, 290.0]], dtype=np.float32)
        result = AggregationService.aggregate([(d1, arr1), (d2, arr2)], "min", VARIABLE)

        np.testing.assert_array_almost_equal(result.data, [[260.0, 280.0]])
        assert result.aggregation == "min"
        assert result.start_date == d1
        assert result.end_date == d2

    def test_max_aggregation(self) -> None:
        from backend.services.aggregation_service import AggregationService

        d1 = date(2020, 1, 1)
        arr1 = np.array([[270.0]], dtype=np.float32)
        arr2 = np.array([[300.0]], dtype=np.float32)
        result = AggregationService.aggregate([(d1, arr1), (d1, arr2)], "max", VARIABLE)
        assert float(result.data[0, 0]) == pytest.approx(300.0)

    def test_mean_aggregation(self) -> None:
        from backend.services.aggregation_service import AggregationService

        d1 = date(2020, 1, 1)
        arr1 = np.array([[270.0]], dtype=np.float32)
        arr2 = np.array([[280.0]], dtype=np.float32)
        result = AggregationService.aggregate([(d1, arr1), (d1, arr2)], "mean", VARIABLE)
        assert float(result.data[0, 0]) == pytest.approx(275.0)

    def test_nan_ignored_in_aggregation(self) -> None:
        from backend.services.aggregation_service import AggregationService

        d1 = date(2020, 1, 1)
        arr1 = np.array([[np.nan]], dtype=np.float32)
        arr2 = np.array([[280.0]], dtype=np.float32)
        result = AggregationService.aggregate([(d1, arr1), (d1, arr2)], "min", VARIABLE)
        assert float(result.data[0, 0]) == pytest.approx(280.0)

    def test_empty_slices_raises(self) -> None:
        from backend.services.aggregation_service import AggregationService

        with pytest.raises(ValueError, match="No data slices"):
            AggregationService.aggregate([], "min", VARIABLE)

    def test_unknown_aggregation_raises(self) -> None:
        from backend.services.aggregation_service import AggregationService

        d1 = date(2020, 1, 1)
        with pytest.raises(ValueError, match="Unknown aggregation"):
            AggregationService.aggregate([(d1, np.array([[1.0]]))], "median", VARIABLE)

    def test_result_dtype_is_float32(self) -> None:
        from backend.services.aggregation_service import AggregationService

        d1 = date(2020, 1, 1)
        arr = np.array([[270.0]], dtype=np.float64)
        result = AggregationService.aggregate([(d1, arr)], "mean", VARIABLE)
        assert result.data.dtype == np.float32


# ---------------------------------------------------------------------------
# NetCDFService
# ---------------------------------------------------------------------------

class TestNetCDFServiceResolvePath:
    def test_resolves_existing_file(self, data_root: Path, nc_file: Path) -> None:
        from backend.services.netcdf_service import NetCDFService

        with patch(_SOURCES_TARGET, _sources(data_root)):
            path = NetCDFService.resolve_nc_path(TEST_DATE, "mean")
        assert path == nc_file

    def test_raises_for_missing_date(self, data_root: Path) -> None:
        from backend.core.exceptions import DatasetNotFoundError
        from backend.services.netcdf_service import NetCDFService

        with patch(_SOURCES_TARGET, _sources(data_root)):
            with pytest.raises(DatasetNotFoundError):
                NetCDFService.resolve_nc_path(date(2099, 1, 1), "mean")

    def test_unknown_temp_type_raises(self, data_root: Path) -> None:
        from backend.services.netcdf_service import NetCDFService

        with patch(_SOURCES_TARGET, _sources(data_root)):
            with pytest.raises(ValueError, match="Unknown temperature type"):
                NetCDFService.resolve_nc_path(TEST_DATE, "bogus")


class TestNetCDFServiceGetSlice:
    def test_returns_float32_array(self, tmp_path, data_root: Path, nc_file: Path) -> None:
        from backend.services.netcdf_service import NetCDFService
        from backend.services.cache_service import TemperatureCache

        fresh_cache = TemperatureCache(ttl_seconds=60, cache_dir=tmp_path)
        with (
            patch(_SOURCES_TARGET, _sources(data_root)),
            patch("backend.services.netcdf_service.temperature_cache", fresh_cache),
        ):
            arr = NetCDFService.get_temperature_slice(TEST_DATE, temp_type="mean")

        assert arr.dtype == np.float32
        assert arr.ndim == 2

    def test_values_in_kelvin_range(self, tmp_path, data_root: Path, nc_file: Path) -> None:
        from backend.services.netcdf_service import NetCDFService
        from backend.services.cache_service import TemperatureCache

        fresh_cache = TemperatureCache(ttl_seconds=60, cache_dir=tmp_path)
        with (
            patch(_SOURCES_TARGET, _sources(data_root)),
            patch("backend.services.netcdf_service.temperature_cache", fresh_cache),
        ):
            arr = NetCDFService.get_temperature_slice(TEST_DATE, temp_type="mean")

        assert float(np.nanmin(arr)) >= 200.0
        assert float(np.nanmax(arr)) <= 350.0

    def test_cache_hit_returns_same_array(self, tmp_path, data_root: Path, nc_file: Path) -> None:
        from backend.services.netcdf_service import NetCDFService
        from backend.services.cache_service import TemperatureCache

        fresh_cache = TemperatureCache(ttl_seconds=60, cache_dir=tmp_path)
        with (
            patch(_SOURCES_TARGET, _sources(data_root)),
            patch("backend.services.netcdf_service.temperature_cache", fresh_cache),
        ):
            arr1 = NetCDFService.get_temperature_slice(TEST_DATE, temp_type="mean")
            arr2 = NetCDFService.get_temperature_slice(TEST_DATE, temp_type="mean")

        np.testing.assert_array_equal(arr1, arr2)  # diskcache deserializes; check values not identity


class TestNetCDFServiceColorscale:
    def test_colorscale_info_fields(self, tmp_path, data_root: Path, nc_file: Path) -> None:
        from backend.models.domain import ColorscaleInfo
        from backend.services.netcdf_service import NetCDFService
        from backend.services.cache_service import TemperatureCache

        fresh_cache = TemperatureCache(ttl_seconds=60, cache_dir=tmp_path)
        with (
            patch(_SOURCES_TARGET, _sources(data_root)),
            patch("backend.services.netcdf_service.temperature_cache", fresh_cache),
        ):
            info = NetCDFService.get_colorscale_info(TEST_DATE, temp_type="mean")

        assert isinstance(info, ColorscaleInfo)
        assert info.min_value <= info.mean_value <= info.max_value
        assert info.units == "K"


class TestNetCDFServiceCellValue:
    def test_cell_value_is_float(self, tmp_path, data_root: Path, nc_file: Path) -> None:
        from backend.services.netcdf_service import NetCDFService
        from backend.services.cache_service import TemperatureCache

        fresh_cache = TemperatureCache(ttl_seconds=60, cache_dir=tmp_path)
        with (
            patch(_SOURCES_TARGET, _sources(data_root)),
            patch("backend.services.netcdf_service.temperature_cache", fresh_cache),
        ):
            value = NetCDFService.get_cell_value(TEST_DATE, lat=0.0, lon=0.0, temp_type="mean")

        assert isinstance(value, float)
        assert 200.0 <= value <= 350.0


class TestNetCDFServiceAvailableDates:
    def test_finds_synthetic_file(self, data_root: Path, nc_file: Path) -> None:
        from backend.services.netcdf_service import NetCDFService

        with patch(_SOURCES_TARGET, _sources(data_root)):
            dates = NetCDFService.get_available_dates("mean")

        assert TEST_DATE.isoformat() in dates

    def test_returns_sorted_list(self, data_root: Path) -> None:
        from backend.services.netcdf_service import NetCDFService

        d1 = date(2020, 1, 1)
        d2 = date(2020, 6, 15)
        make_nc_file(data_root, d1)
        make_nc_file(data_root, d2)

        with patch(_SOURCES_TARGET, _sources(data_root)):
            dates = NetCDFService.get_available_dates("mean")

        assert dates == sorted(dates)
        assert d1.isoformat() in dates
        assert d2.isoformat() in dates


class TestNetCDFServiceSliceRange:
    """
    Tests for get_temperature_slice_range focus on orchestration logic
    (parallel loading, error handling, result sorting). The individual
    get_temperature_slice behaviour is covered by TestNetCDFServiceGetSlice.
    We mock get_temperature_slice to avoid concurrent netCDF4 file access,
    which segfaults on CPython 3.14 due to a known netCDF4/threading issue.
    """

    def test_loads_multiple_dates(self, data_root: Path) -> None:
        from backend.services.netcdf_service import NetCDFService

        d1 = date(2020, 12, 30)
        d2 = date(2020, 12, 31)
        arr = np.ones((10, 20), dtype=np.float32) * 280.0

        with (
            patch(_SOURCES_TARGET, _sources(data_root)),
            patch.object(NetCDFService, "get_temperature_slice", return_value=arr),
        ):
            pairs = NetCDFService.get_temperature_slice_range(d1, d2, temp_type="mean")

        assert len(pairs) == 2
        assert pairs[0][0] == d1
        assert pairs[1][0] == d2

    def test_skips_missing_dates_gracefully(self, data_root: Path) -> None:
        from backend.core.exceptions import DatasetNotFoundError
        from backend.services.netcdf_service import NetCDFService

        d1 = date(2020, 12, 30)
        d2 = date(2020, 12, 31)
        arr = np.ones((10, 20), dtype=np.float32) * 280.0

        def fake_slice(d: date, time_index: int = 0, temp_type: str = "mean") -> np.ndarray:
            if d == d2:
                raise DatasetNotFoundError(d2)
            return arr

        with (
            patch(_SOURCES_TARGET, _sources(data_root)),
            patch.object(NetCDFService, "get_temperature_slice", side_effect=fake_slice),
        ):
            pairs = NetCDFService.get_temperature_slice_range(d1, d2, temp_type="mean")

        assert len(pairs) == 1
        assert pairs[0][0] == d1

    def test_all_missing_raises(self, data_root: Path) -> None:
        from backend.core.exceptions import DatasetNotFoundError
        from backend.services.netcdf_service import NetCDFService

        with (
            patch(_SOURCES_TARGET, _sources(data_root)),
            patch.object(
                NetCDFService,
                "get_temperature_slice",
                side_effect=DatasetNotFoundError(date(2099, 1, 1)),
            ),
        ):
            with pytest.raises(DatasetNotFoundError):
                NetCDFService.get_temperature_slice_range(
                    date(2099, 1, 1), date(2099, 1, 3), temp_type="mean"
                )
