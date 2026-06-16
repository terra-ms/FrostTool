from datetime import date
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

VARIABLE = "Temperature_Air_2m_Mean_24h"
TEST_DATE = date(2020, 12, 31)
TEST_DATE_STR = "20201231"


def make_nc_file(directory: Path, date_obj: date, variable: str = VARIABLE) -> Path:
    """Create a minimal synthetic NetCDF file in DATA_ROOT/YYYY/ layout."""
    year_dir = directory / f"{date_obj.year:04d}"
    year_dir.mkdir(parents=True, exist_ok=True)

    filename = f"AgERA5_{date_obj.isoformat().replace('-', '')}_{variable}.nc"
    path = year_dir / filename

    data = np.random.uniform(250.0, 310.0, (1, 10, 20)).astype(np.float32)
    ds = xr.Dataset(
        {variable: (["time", "lat", "lon"], data)},
        coords={
            "time": [0],
            "lat": np.linspace(90, -90, 10, dtype=np.float32),
            "lon": np.linspace(-180, 180, 20, dtype=np.float32),
        },
    )
    ds.to_netcdf(path)
    return path


@pytest.fixture()
def data_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture()
def nc_file(data_root: Path) -> Path:
    return make_nc_file(data_root, TEST_DATE)


@pytest.fixture()
def backend_api_url() -> str:
    return "http://localhost:8000/api/v1"
