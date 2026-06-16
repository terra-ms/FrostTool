"""
Filesystem abstraction — local disk or S3.

Set the S3_BUCKET environment variable to enable S3 mode.
When S3_BUCKET is unset the module falls back to local Path I/O, so docker-compose
and local development work unchanged.

S3 key layout mirrors the local folder names:
    tmean_v2/{YYYY}/*.nc
    tmin_v2/{YYYY}/*.nc
    precomputed/year_stacks/gdd_stack_{year}.npz
    precomputed/gdd_results/gdd_frost_{year}_{crop}.npz
"""

import io
import logging
import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager, suppress
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

S3_BUCKET: str | None = os.environ.get("S3_BUCKET")


def using_s3() -> bool:
    return S3_BUCKET is not None


@lru_cache(maxsize=1)
def _fs() -> Any:
    """Lazily-imported, cached s3fs filesystem. Not touched in local mode."""
    import s3fs  # noqa: PLC0415

    return s3fs.S3FileSystem()


def _posix(path: Path) -> str:
    return path.as_posix()


def _npz_s3_key(path: Path) -> str:
    """
    Convert a local .npz path to an S3 key.

    PRECOMPUTED_DIR can be absolute (/data/precomputed) or relative (precomputed).
    Either way the S3 key is 'precomputed/year_stacks/gdd_stack_2020.npz'.
    """
    from backend.core.config import PRECOMPUTED_DIR  # local import avoids circular dep

    if PRECOMPUTED_DIR.is_absolute():
        relative = path.relative_to(PRECOMPUTED_DIR.parent)
    else:
        relative = path
    return _posix(relative)


# ── NetCDF helpers ─────────────────────────────────────────────────────────────


def _s3_folder_name(data_root: Path) -> str:
    """
    Return the leaf folder name for use as an S3 key prefix.

    Calling data_root.name on Linux when data_root was built from a Windows-style
    path (e.g. C:\\path\\tmean_v2) returns the entire string rather than just
    'tmean_v2', because backslashes are not path separators on POSIX.  Splitting
    on both separators makes this work correctly in both environments.
    """
    parts = [p for p in str(data_root).replace("\\", "/").split("/") if p]
    return parts[-1] if parts else str(data_root)


def find_nc_file(data_root: Path, year: int, date_str: str) -> str | Path:
    """
    Locate the NetCDF file whose name contains *date_str* (YYYYMMDD).
    Returns an S3 URL string in S3 mode or a local Path in local mode.
    Raises FileNotFoundError if no match is found.
    """
    if S3_BUCKET:
        prefix = f"{S3_BUCKET}/{_s3_folder_name(data_root)}/{year:04d}"
        s3_matches: list[Any] = list(_fs().glob(f"{prefix}/*{date_str}*.nc"))
        if not s3_matches:
            raise FileNotFoundError(f"No NetCDF for {date_str} in s3://{prefix}/")
        if len(s3_matches) > 1:
            logger.warning("Multiple S3 matches for %s; using first", date_str)
        return str(f"s3://{s3_matches[0]}")

    folder = data_root / f"{year:04d}"
    matches = list(folder.glob(f"*{date_str}*.nc"))
    if not matches:
        raise FileNotFoundError(f"No NetCDF for {date_str} in {folder}")
    return matches[0]


def list_year_dirs(data_root: Path) -> list[int]:
    """List year-numbered subdirectories under *data_root*."""
    if S3_BUCKET:
        try:
            items = _fs().ls(f"{S3_BUCKET}/{_s3_folder_name(data_root)}", detail=False)
        except FileNotFoundError:
            return []
        years = []
        for item in items:
            name = item.rstrip("/").split("/")[-1]
            if len(name) == 4 and name.isdigit():
                years.append(int(name))
        return sorted(years)

    return sorted(
        int(p.name) for p in data_root.glob("????") if p.is_dir() and p.name.isdigit()
    )


def list_nc_files(data_root: Path, year: int) -> list[str]:
    """Return .nc filenames (not full paths) in a year subfolder."""
    if S3_BUCKET:
        try:
            items = _fs().ls(f"{S3_BUCKET}/{data_root.name}/{year:04d}", detail=False)
        except FileNotFoundError:
            return []
        return [item.split("/")[-1] for item in items if item.endswith(".nc")]

    folder = data_root / f"{year:04d}"
    if not folder.is_dir():
        return []
    return [p.name for p in folder.glob("*.nc")]


@contextmanager
def open_nc(path: str | Path) -> Generator[Path, None, None]:
    """
    Context manager yielding a Path that xr.open_dataset can consume.

    Local mode: yields the Path directly — no overhead.
    S3 mode:    downloads the file to a named temp file and yields that path.
                The NetCDF4 C library cannot follow s3:// URLs itself (it tries
                its own curl access without AWS credentials and fails with
                errno -68). Fetching via s3fs and handing xarray a real file
                path avoids that entirely. BytesIO does not work because
                xarray's netcdf4 backend leaks the original URL to the C
                library instead of isolating it in memory.
    """
    if S3_BUCKET and isinstance(path, str) and path.startswith("s3://"):
        key = path[5:]  # strip "s3://" → "bucket/prefix/file.nc"
        logger.debug("Fetching NC from S3: %s", key)
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".nc")
        try:
            with os.fdopen(tmp_fd, "wb") as f:
                f.write(_fs().cat(key))
            yield Path(tmp_path)
        finally:
            with suppress(OSError):
                os.unlink(tmp_path)
    else:
        yield Path(path) if not isinstance(path, Path) else path


# ── NPZ helpers ────────────────────────────────────────────────────────────────


def npz_exists(path: Path) -> bool:
    if S3_BUCKET:
        return bool(_fs().exists(f"{S3_BUCKET}/{_npz_s3_key(path)}"))
    return path.exists()


def load_npz(path: Path) -> dict[str, Any]:
    """Load a .npz and return all arrays as a plain dict (eagerly read)."""
    if S3_BUCKET:
        key = f"{S3_BUCKET}/{_npz_s3_key(path)}"
        logger.debug("Loading npz from S3: %s", key)
        with _fs().open(key, "rb") as fobj:
            buf = io.BytesIO(fobj.read())
        with np.load(buf) as data:
            return dict(data)

    with np.load(path) as data:
        return dict(data)


def save_npz(path: Path, **arrays: np.ndarray) -> None:
    """Save arrays as compressed .npz to S3 or local disk."""
    if S3_BUCKET:
        buf = io.BytesIO()
        np.savez_compressed(buf, **arrays)  # type: ignore[arg-type]
        buf.seek(0)
        key = f"{S3_BUCKET}/{_npz_s3_key(path)}"
        logger.info("Saving npz to S3: %s", key)
        with _fs().open(key, "wb") as fobj:
            fobj.write(buf.read())
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrays)  # type: ignore[arg-type]
    logger.info("Saved npz locally: %s", path)
