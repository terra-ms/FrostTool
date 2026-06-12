"""
Diagnostic endpoint for S3 connectivity.

GET /api/v1/debug/s3
Walks through every step of the S3 read path and returns a JSON report.
Remove or gate behind auth before a public release.
"""
import os
import tempfile
import traceback
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/debug", tags=["debug"])


def _step(results: list, name: str):
    """Context manager that appends a pass/fail entry to *results*."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        entry: dict = {"step": name, "ok": False, "detail": None}
        results.append(entry)
        try:
            yield entry
            entry["ok"] = True
        except Exception as exc:
            entry["detail"] = f"{type(exc).__name__}: {exc}"
            entry["traceback"] = traceback.format_exc(limit=5)

    return _ctx()


@router.get("/s3")
async def debug_s3() -> JSONResponse:
    results: list[dict] = []

    # ── 1. Environment variables ──────────────────────────────────────────────
    with _step(results, "env_vars") as s:
        s3_bucket = os.environ.get("S3_BUCKET")
        data_root_mean = os.environ.get("DATA_ROOT_MEAN", "<default>")
        data_root_min = os.environ.get("DATA_ROOT_MIN", "<default>")
        precomputed_dir = os.environ.get("PRECOMPUTED_DIR", "<default>")
        s["detail"] = {
            "S3_BUCKET": s3_bucket,
            "DATA_ROOT_MEAN": data_root_mean,
            "DATA_ROOT_MIN": data_root_min,
            "PRECOMPUTED_DIR": precomputed_dir,
        }

    # ── 2. Import s3fs and build filesystem object ────────────────────────────
    with _step(results, "s3fs_import") as s:
        import s3fs  # noqa: PLC0415
        fs = s3fs.S3FileSystem()
        s["detail"] = f"s3fs version {s3fs.__version__}"

    if not all(r["ok"] for r in results):
        return JSONResponse({"results": results})

    if not s3_bucket:
        results.append({"step": "s3_bucket_check", "ok": False,
                         "detail": "S3_BUCKET env var is not set — stopping here"})
        return JSONResponse({"results": results})

    # ── 3. List bucket root ───────────────────────────────────────────────────
    with _step(results, "list_bucket_root") as s:
        items = fs.ls(s3_bucket, detail=False)
        s["detail"] = [i.split("/")[-1] for i in items[:20]]

    # ── 4. Resolve the folder names from config paths ────────────────────────
    with _step(results, "resolve_folder_names") as s:
        from backend.core.config import TEMPERATURE_SOURCES  # noqa: PLC0415

        def _folder_name(p: Path) -> str:
            parts = [x for x in str(p).replace("\\", "/").split("/") if x]
            return parts[-1] if parts else str(p)

        mean_root: Path = TEMPERATURE_SOURCES["mean"]["path"]  # type: ignore[assignment]
        min_root: Path = TEMPERATURE_SOURCES["min"]["path"]  # type: ignore[assignment]
        mean_prefix = _folder_name(mean_root)
        min_prefix = _folder_name(min_root)
        s["detail"] = {
            "mean_root_raw": str(mean_root),
            "mean_prefix": mean_prefix,
            "min_root_raw": str(min_root),
            "min_prefix": min_prefix,
        }

    # ── 5. List year dirs for tmean ───────────────────────────────────────────
    with _step(results, "list_tmean_years") as s:
        tmean_path = f"{s3_bucket}/{mean_prefix}"
        items = fs.ls(tmean_path, detail=False)
        years = sorted(
            int(i.rstrip("/").split("/")[-1])
            for i in items
            if i.rstrip("/").split("/")[-1].isdigit()
        )
        s["detail"] = {"path_listed": tmean_path, "years": years}

    # ── 6. List year dirs for tmin ────────────────────────────────────────────
    with _step(results, "list_tmin_years") as s:
        tmin_path = f"{s3_bucket}/{min_prefix}"
        items = fs.ls(tmin_path, detail=False)
        years_min = sorted(
            int(i.rstrip("/").split("/")[-1])
            for i in items
            if i.rstrip("/").split("/")[-1].isdigit()
        )
        s["detail"] = {"path_listed": tmin_path, "years": years_min}

    # ── 7. Find a sample NC file (most recent tmean year, first file) ─────────
    sample_key: str | None = None
    with _step(results, "find_sample_nc") as s:
        if not years:
            raise RuntimeError("No tmean years found — cannot find a sample file")
        latest_year = years[-1]
        year_prefix = f"{s3_bucket}/{mean_prefix}/{latest_year:04d}"
        nc_items = fs.ls(year_prefix, detail=False)
        nc_files = [i for i in nc_items if i.endswith(".nc")]
        if not nc_files:
            raise FileNotFoundError(f"No .nc files under s3://{year_prefix}/")
        sample_key = nc_files[0]
        s["detail"] = {
            "year": latest_year,
            "prefix": year_prefix,
            "file": sample_key,
            "total_nc_files": len(nc_files),
        }

    if not all(r["ok"] for r in results):
        return JSONResponse({"results": results})

    # ── 8. Download the sample NC file ────────────────────────────────────────
    tmp_path: str | None = None
    with _step(results, "download_sample_nc") as s:
        raw_bytes = fs.cat(sample_key)
        s["detail"] = {"bytes_downloaded": len(raw_bytes), "source": sample_key}

    # ── 9. Write to temp file ─────────────────────────────────────────────────
    with _step(results, "write_temp_file") as s:
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".nc")
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(raw_bytes)
        s["detail"] = {"tmp_path": tmp_path, "size_bytes": os.path.getsize(tmp_path)}

    # ── 10. Open with xarray ──────────────────────────────────────────────────
    with _step(results, "xarray_open") as s:
        import xarray as xr  # noqa: PLC0415
        with xr.open_dataset(tmp_path, engine="netcdf4") as ds:
            variables = list(ds.data_vars)
            dims = dict(ds.dims)
            s["detail"] = {"variables": variables, "dims": dims}

    # ── 11. Cleanup temp file ─────────────────────────────────────────────────
    with _step(results, "cleanup_temp") as s:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        s["detail"] = "temp file deleted"

    overall_ok = all(r["ok"] for r in results)
    return JSONResponse({"ok": overall_ok, "results": results}, status_code=200 if overall_ok else 500)
