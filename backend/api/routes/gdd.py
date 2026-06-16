import logging
import os
import tempfile
import traceback
from datetime import date

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

from backend.core.exceptions import DatasetNotFoundError
from backend.models.schemas import (
    CropInfo,
    CropsResponse,
    GDDAvailableYearsResponse,
    GDDColorscaleResponse,
    GDDTimeseriesDataPoint,
    GDDTimeseriesResponse,
)
from backend.services.gdd_service import (
    GDDService,
    compute_frost_event_count_in_period,
    get_available_gdd_years,
    get_gdd_timeseries,
    load_crops,
)
from backend.services.netcdf_service import _build_raster_bytes_preclipped

router = APIRouter(prefix="/api/v1/gdd", tags=["gdd"])


@router.get("/available-years", response_model=GDDAvailableYearsResponse)
async def get_available_years() -> GDDAvailableYearsResponse:
    try:
        years = get_available_gdd_years()
        return GDDAvailableYearsResponse(
            years=years,
            min_year=years[0] if years else 1979,
            max_year=years[-1] if years else 2007,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/crops", response_model=CropsResponse)
async def get_crops() -> CropsResponse:
    try:
        crops = load_crops()
        return CropsResponse(
            crops=[
                CropInfo(name=k, display_name=v.display_name) for k, v in crops.items()
            ]
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/raster",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"image/tiff": {}},
            "description": "GeoTIFF frost-event-count raster",
        }
    },
)
async def get_gdd_raster(
    year: int = Query(..., ge=1979, le=2100),
    crop: str = Query(..., description="Crop key from crops.txt"),
    zoom_level: int | None = Query(None, ge=0, le=19),
    date_from: date | None = Query(
        None, description="Start of display period (YYYY-MM-DD, within season)"
    ),
    date_to: date | None = Query(
        None, description="End of display period (YYYY-MM-DD, within season)"
    ),
) -> StreamingResponse:
    try:
        crops = load_crops()
        if crop not in crops:
            raise HTTPException(
                status_code=404, detail=f"Crop '{crop}' not found in crops.txt"
            )
        if date_from is not None or date_to is not None:
            season_start = date(year, 1, 1)
            season_end = date(year, 5, 31)
            period_start = date_from or season_start
            period_end = date_to or season_end
            if period_start > period_end:
                raise HTTPException(
                    status_code=422, detail="date_from must not be later than date_to"
                )
            result = compute_frost_event_count_in_period(
                year, crops[crop], period_start, period_end
            )
        else:
            result = GDDService.compute_frost_event_count(year, crops[crop])
        raster_bytes = _build_raster_bytes_preclipped(
            result.frost_count,
            result.bounds.min_lat,
            result.bounds.max_lat,
            result.bounds.min_lon,
            result.bounds.max_lon,
            zoom_level=zoom_level,
        )
        return StreamingResponse(
            iter([raster_bytes]),
            media_type="image/tiff",
            headers={
                "Content-Disposition": f"attachment; filename=gdd_{year}_{crop}.tif"
            },
        )
    except HTTPException:
        raise
    except DatasetNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"No climate data for year {year}"
        ) from None
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/timeseries", response_model=GDDTimeseriesResponse)
async def get_gdd_timeseries_endpoint(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    year: int = Query(..., ge=1979, le=2100),
    crop: str = Query(..., description="Crop key from crops.txt"),
) -> GDDTimeseriesResponse:
    try:
        crops = load_crops()
        if crop not in crops:
            raise HTTPException(
                status_code=404, detail=f"Crop '{crop}' not found in crops.txt"
            )
        crop_params = crops[crop]
        result = get_gdd_timeseries(lat, lon, year, crop_params)
        return GDDTimeseriesResponse(
            lat=lat,
            lon=lon,
            year=year,
            crop=crop,
            crop_display_name=crop_params.display_name,
            gdd_threshold=crop_params.gdd_threshold,
            frost_threshold=crop_params.frost_threshold,
            budbreak_date=result.budbreak_date,
            frost_event_dates=result.frost_event_dates,
            data=[
                GDDTimeseriesDataPoint(
                    date=result.season_dates[i],
                    cumulative_gdd=float(result.gdd_accum[i]),
                    daily_tmin=float(result.tmin_c[i]),
                    daily_tavg=float(result.tavg_c[i]),
                )
                for i in range(len(result.season_dates))
            ],
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DatasetNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"No climate data for year {year}"
        ) from None
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/colorscale", response_model=GDDColorscaleResponse)
async def get_gdd_colorscale(
    year: int = Query(..., ge=1979, le=2100),
    crop: str = Query(..., description="Crop key from crops.txt"),
    date_from: date | None = Query(
        None, description="Start of display period (YYYY-MM-DD, within season)"
    ),
    date_to: date | None = Query(
        None, description="End of display period (YYYY-MM-DD, within season)"
    ),
) -> GDDColorscaleResponse:
    try:
        crops = load_crops()
        if crop not in crops:
            raise HTTPException(
                status_code=404, detail=f"Crop '{crop}' not found in crops.txt"
            )
        if date_from is not None or date_to is not None:
            season_start = date(year, 1, 1)
            season_end = date(year, 5, 31)
            period_start = date_from or season_start
            period_end = date_to or season_end
            result = compute_frost_event_count_in_period(
                year, crops[crop], period_start, period_end
            )
        else:
            result = GDDService.compute_frost_event_count(year, crops[crop])
        frost_count = result.frost_count
        # Exclude NaN and the "never reached budbreak" sentinel from the max
        valid = frost_count[~np.isnan(frost_count) & (frost_count >= 0)]
        max_count = int(np.max(valid)) if len(valid) > 0 else 0
        return GDDColorscaleResponse(min_value=0, max_value=max_count)
    except HTTPException:
        raise
    except DatasetNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"No climate data for year {year}"
        ) from None
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/debug/s3")
async def debug_s3() -> JSONResponse:
    """S3 connectivity diagnostic — walks each step and reports pass/fail."""
    _log = logging.getLogger(__name__)
    steps: list[dict] = []

    def step(name: str, fn):  # type: ignore[no-untyped-def]
        entry: dict = {"step": name, "ok": False, "detail": None}
        steps.append(entry)
        try:
            entry["detail"] = fn()
            entry["ok"] = True
        except Exception as exc:
            entry["detail"] = f"{type(exc).__name__}: {exc}"
            entry["traceback"] = traceback.format_exc(limit=6)
        return entry["ok"]

    # 1. env vars
    s3_bucket = os.environ.get("S3_BUCKET")
    step(
        "env_vars",
        lambda: {
            "S3_BUCKET": s3_bucket,
            "DATA_ROOT_MEAN": os.environ.get("DATA_ROOT_MEAN", "<default>"),
            "DATA_ROOT_MIN": os.environ.get("DATA_ROOT_MIN", "<default>"),
            "PRECOMPUTED_DIR": os.environ.get("PRECOMPUTED_DIR", "<default>"),
        },
    )

    if not s3_bucket:
        steps.append({"step": "abort", "ok": False, "detail": "S3_BUCKET not set"})
        return JSONResponse({"ok": False, "steps": steps})

    # 2. import s3fs
    fs = None
    if step("s3fs_import", lambda: __import__("s3fs").__version__):
        import s3fs as _s3fs

        fs = _s3fs.S3FileSystem()

    if fs is None:
        return JSONResponse({"ok": False, "steps": steps})

    # 3. list bucket root
    step(
        "list_bucket_root",
        lambda: [i.split("/")[-1] for i in fs.ls(s3_bucket, detail=False)[:20]],
    )

    # 4. resolve folder names from config paths
    from backend.core.config import TEMPERATURE_SOURCES  # noqa: PLC0415

    def _fname(p) -> str:  # type: ignore[no-untyped-def]
        parts = [x for x in str(p).replace("\\", "/").split("/") if x]
        return parts[-1] if parts else str(p)

    mean_prefix = _fname(TEMPERATURE_SOURCES["mean"]["path"])
    min_prefix = _fname(TEMPERATURE_SOURCES["min"]["path"])
    step("folder_names", lambda: {"mean_prefix": mean_prefix, "min_prefix": min_prefix})

    # 5. list tmean year dirs
    years: list[int] = []

    def _list_mean():
        nonlocal years
        items = fs.ls(f"{s3_bucket}/{mean_prefix}", detail=False)
        years = sorted(
            int(i.rstrip("/").split("/")[-1])
            for i in items
            if i.rstrip("/").split("/")[-1].isdigit()
        )
        return {"path": f"{s3_bucket}/{mean_prefix}", "years": years}

    step("list_tmean_years", _list_mean)

    # 6. list tmin year dirs
    step(
        "list_tmin_years",
        lambda: {
            "path": f"{s3_bucket}/{min_prefix}",
            "years": sorted(
                int(i.rstrip("/").split("/")[-1])
                for i in fs.ls(f"{s3_bucket}/{min_prefix}", detail=False)
                if i.rstrip("/").split("/")[-1].isdigit()
            ),
        },
    )

    if not years:
        steps.append({"step": "abort", "ok": False, "detail": "No tmean years found"})
        return JSONResponse({"ok": False, "steps": steps})

    # 7. find a sample NC file (most recent tmean year)
    sample_key: str | None = None

    def _find_nc():
        nonlocal sample_key
        latest = years[-1]
        prefix = f"{s3_bucket}/{mean_prefix}/{latest:04d}"
        nc_files = [i for i in fs.ls(prefix, detail=False) if i.endswith(".nc")]
        if not nc_files:
            raise FileNotFoundError(f"No .nc files under {prefix}")
        sample_key = nc_files[0]
        return {"year": latest, "file": sample_key, "total_nc": len(nc_files)}

    step("find_sample_nc", _find_nc)

    if sample_key is None:
        return JSONResponse({"ok": False, "steps": steps})

    # 8. download via s3fs
    raw: bytes | None = None

    def _download():
        nonlocal raw
        raw = fs.cat(sample_key)
        return {"bytes": len(raw)}

    step("download_nc", _download)

    if raw is None:
        return JSONResponse({"ok": False, "steps": steps})

    # 9. write to named temp file
    tmp_path: str | None = None

    def _write_tmp():
        nonlocal tmp_path
        fd, tmp_path = tempfile.mkstemp(suffix=".nc")
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        return {"tmp_path": tmp_path, "size_bytes": os.path.getsize(tmp_path)}

    step("write_temp_file", _write_tmp)

    # 10. open with xarray / netcdf4
    def _xr_open():
        import xarray as xr  # noqa: PLC0415

        assert tmp_path is not None
        with xr.open_dataset(tmp_path, engine="netcdf4") as ds:
            return {"variables": list(ds.data_vars), "dims": dict(ds.sizes)}

    step("xarray_open", _xr_open)

    # 11. cleanup
    step("cleanup", lambda: os.unlink(tmp_path) or "deleted")  # type: ignore[func-returns-value, arg-type]

    ok = all(s["ok"] for s in steps)
    _log.info("S3 debug: %s", "PASS" if ok else "FAIL")
    return JSONResponse({"ok": ok, "steps": steps}, status_code=200 if ok else 500)
