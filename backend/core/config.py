import os
from pathlib import Path

_DATA_ROOT_MEAN: Path = Path(
    os.environ.get("DATA_ROOT_MEAN", r"C:\Olivier\Terra local\data\AgERA5\tmean_v2")
)
_DATA_ROOT_MIN: Path = Path(
    os.environ.get("DATA_ROOT_MIN", r"C:\Olivier\Terra local\data\AgERA5\tmin_v2")
)

# Temperature data sources configuration
TEMPERATURE_SOURCES: dict[str, dict[str, Path | str]] = {
    "mean": {
        "path": _DATA_ROOT_MEAN,
        "variable": "Temperature_Air_2m_Mean_24h",
        "label": "Mean (24h)",
        "units": "K",
    },
    "min": {
        "path": _DATA_ROOT_MIN,
        "variable": "Temperature_Air_2m_Min_24h",
        "label": "Minimum (24h)",
        "units": "K",
    },
}

# Pre-computed GDD artifacts (YearStack + GDDResult .npz files).
# Defaults to a sibling of tmean_v2 so all AgERA5 data lives in one place.
# Override with PRECOMPUTED_DIR env var (or an S3-mounted path in production).
PRECOMPUTED_DIR: Path = Path(
    os.environ.get("PRECOMPUTED_DIR", str(_DATA_ROOT_MEAN.parent / "precomputed"))
)

# Default to mean, but can be overridden
DEFAULT_TEMP_TYPE: str = "mean"

# Legacy support
DATA_ROOT: Path = Path(str(TEMPERATURE_SOURCES[DEFAULT_TEMP_TYPE]["path"]))
VARIABLE: str = str(TEMPERATURE_SOURCES[DEFAULT_TEMP_TYPE]["variable"])

CACHE_DIR: Path = Path(
    os.environ.get("CACHE_DIR", str(Path(__file__).parent.parent.parent / ".cache"))
)

# S3 mode: set this to the bucket name (e.g. "frosttool-data").
# When unset, the app reads from the local DATA_ROOT_* paths (docker-compose / local dev).
S3_BUCKET: str | None = os.environ.get("S3_BUCKET")

CROPS_CONFIG_PATH: Path = Path(
    os.environ.get(
        "CROPS_CONFIG", str(Path(__file__).parent.parent.parent / "crops.txt")
    )
)

# Earliest year included in the background GDD warm-up at startup.
# Pre-2000 years are rarely needed; raise this value to reduce cold-start time.
GDD_WARMUP_MIN_YEAR: int = int(os.environ.get("GDD_WARMUP_MIN_YEAR", "2015"))

CONTINENTS: dict[str, tuple[float, float, float, float]] = {
    "Africa": (-35, 37, -18, 52),
    "North America": (15, 83, -170, -50),
    "South America": (-56, 13, -82, -35),
    "Europe": (30, 76, -15, 54),
    "Asia": (-10, 77, 26, 180),
    "Oceania": (-47, -10, 113, 180),
}
