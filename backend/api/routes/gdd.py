import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.core.exceptions import DatasetNotFoundError
from backend.models.schemas import CropInfo, CropsResponse, GDDAvailableYearsResponse, GDDColorscaleResponse
from backend.services.gdd_service import GDDService, get_available_gdd_years, load_crops
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
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/crops", response_model=CropsResponse)
async def get_crops() -> CropsResponse:
    try:
        crops = load_crops()
        return CropsResponse(
            crops=[CropInfo(name=k, display_name=v.display_name) for k, v in crops.items()]
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/raster",
    response_class=StreamingResponse,
    responses={200: {"content": {"image/tiff": {}}, "description": "GeoTIFF frost-event-count raster"}},
)
async def get_gdd_raster(
    year: int = Query(..., ge=1979, le=2100),
    crop: str = Query(..., description="Crop key from crops.txt"),
    zoom_level: int | None = Query(None, ge=0, le=19),
) -> StreamingResponse:
    try:
        crops = load_crops()
        if crop not in crops:
            raise HTTPException(status_code=404, detail=f"Crop '{crop}' not found in crops.txt")
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
            headers={"Content-Disposition": f"attachment; filename=gdd_{year}_{crop}.tif"},
        )
    except HTTPException:
        raise
    except DatasetNotFoundError:
        raise HTTPException(status_code=404, detail=f"No climate data for year {year}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/colorscale", response_model=GDDColorscaleResponse)
async def get_gdd_colorscale(
    year: int = Query(..., ge=1979, le=2100),
    crop: str = Query(..., description="Crop key from crops.txt"),
) -> GDDColorscaleResponse:
    try:
        crops = load_crops()
        if crop not in crops:
            raise HTTPException(status_code=404, detail=f"Crop '{crop}' not found in crops.txt")
        result = GDDService.compute_frost_event_count(year, crops[crop])
        frost_count = result.frost_count
        # Exclude NaN and the "never reached budbreak" sentinel from the max
        valid = frost_count[~np.isnan(frost_count) & (frost_count >= 0)]
        max_count = int(np.max(valid)) if len(valid) > 0 else 0
        return GDDColorscaleResponse(min_value=0, max_value=max_count)
    except HTTPException:
        raise
    except DatasetNotFoundError:
        raise HTTPException(status_code=404, detail=f"No climate data for year {year}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
