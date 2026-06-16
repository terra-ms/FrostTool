from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.api.dependencies import get_netcdf_service
from backend.core.config import CONTINENTS
from backend.core.exceptions import (
    DatasetNotFoundError,
    InvalidTimeIndexError,
    VariableNotFoundError,
)
from backend.models.domain import ColorscaleInfo
from backend.models.schemas import (
    AvailableDatesResponse,
    CellValueResponse,
    ColorscaleResponse,
    ContinentBounds,
    ContinentDetail,
    HealthResponse,
    TimeseriesDataPoint,
    TimeseriesResponse,
)
from backend.services.aggregation_service import VALID_AGGREGATIONS
from backend.services.netcdf_service import NetCDFService

router = APIRouter(prefix="/api/v1", tags=["climate"])


@router.get("/available-dates", response_model=AvailableDatesResponse)
async def get_available_dates(
    temp_type: str = Query("mean", description="Temperature type: mean or min"),
    service: NetCDFService = Depends(get_netcdf_service),
) -> AvailableDatesResponse:
    try:
        dates: list[str] = service.get_available_dates(temp_type)
        return AvailableDatesResponse(dates=dates)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/raster",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"image/tiff": {}}, "description": "GeoTIFF raster tile"}
    },
)
async def get_raster(
    date_str: str | None = Query(None, description="Date in YYYY-MM-DD format"),
    start_date: str | None = Query(
        None, description="Range start in YYYY-MM-DD format (for aggregation)"
    ),
    end_date: str | None = Query(
        None, description="Range end in YYYY-MM-DD format (for aggregation)"
    ),
    agg_type: str = Query("min", description="Aggregation type: min, max, or mean"),
    temp_type: str = Query("mean", description="Temperature type: mean or min"),
    continent: str | None = Query(None, description="Optional continent name"),
    zoom_level: int | None = Query(
        None, ge=0, le=19, description="Map zoom level (0-19) for adaptive resolution"
    ),
    service: NetCDFService = Depends(get_netcdf_service),
) -> StreamingResponse:
    try:
        # If start_date and end_date provided, use aggregation
        if start_date and end_date:
            start_obj: date = date.fromisoformat(start_date)
            end_obj: date = date.fromisoformat(end_date)

            if agg_type not in VALID_AGGREGATIONS:
                raise ValueError(f"Invalid aggregation type: {agg_type}")

            raster_bytes: bytes = service.get_raster_bytes_aggregated(
                start_obj,
                end_obj,
                agg_type,
                temp_type=temp_type,
                continent=continent,
                zoom_level=zoom_level,
            )
            filename = f"{start_date}_to_{end_date}_{agg_type}.tif"
        elif date_str:
            # Single date
            date_obj: date = date.fromisoformat(date_str)
            raster_bytes: bytes = service.get_raster_bytes(
                date_obj,
                temp_type=temp_type,
                continent=continent,
                zoom_level=zoom_level,
            )
            filename = f"{date_str}.tif"
        else:
            raise ValueError(
                "Either date_str or (start_date and end_date) must be provided"
            )

        return StreamingResponse(
            iter([raster_bytes]),
            media_type="image/tiff",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except DatasetNotFoundError:
        raise HTTPException(
            status_code=404, detail="No data for the specified date(s)"
        ) from None
    except (ValueError, VariableNotFoundError, InvalidTimeIndexError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/colorscale", response_model=ColorscaleResponse)
async def get_colorscale(
    date_str: str | None = Query(None, description="Date in YYYY-MM-DD format"),
    start_date: str | None = Query(
        None, description="Range start in YYYY-MM-DD format (for aggregation)"
    ),
    end_date: str | None = Query(
        None, description="Range end in YYYY-MM-DD format (for aggregation)"
    ),
    agg_type: str = Query("min", description="Aggregation type: min, max, or mean"),
    temp_type: str = Query("mean", description="Temperature type: mean or min"),
    service: NetCDFService = Depends(get_netcdf_service),
) -> ColorscaleResponse:
    try:
        if start_date and end_date:
            start_obj: date = date.fromisoformat(start_date)
            end_obj: date = date.fromisoformat(end_date)

            if agg_type not in VALID_AGGREGATIONS:
                raise ValueError(f"Invalid aggregation type: {agg_type}")

            info: ColorscaleInfo = service.get_colorscale_info_aggregated(
                start_obj, end_obj, agg_type, temp_type=temp_type
            )
        elif date_str:
            date_obj: date = date.fromisoformat(date_str)
            info = service.get_colorscale_info(date_obj, temp_type=temp_type)
        else:
            raise ValueError(
                "Either date_str or (start_date and end_date) must be provided"
            )

        return ColorscaleResponse(
            min_value=info.min_value,
            max_value=info.max_value,
            mean_value=info.mean_value,
            units=info.units,
        )
    except DatasetNotFoundError:
        raise HTTPException(
            status_code=404, detail="No data for the specified date(s)"
        ) from None
    except (ValueError, VariableNotFoundError, InvalidTimeIndexError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/value", response_model=CellValueResponse)
async def get_cell_value(
    date_str: str = Query(..., description="Date in YYYY-MM-DD format"),
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    temp_type: str = Query("mean", description="Temperature type: mean or min"),
    service: NetCDFService = Depends(get_netcdf_service),
) -> CellValueResponse:
    try:
        date_obj: date = date.fromisoformat(date_str)
        value: float = service.get_cell_value(date_obj, lat, lon, temp_type=temp_type)
        return CellValueResponse(value=value, lat=lat, lon=lon, date=date_str)
    except DatasetNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"No data for date {date_str}"
        ) from None
    except (ValueError, VariableNotFoundError, InvalidTimeIndexError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/timeseries", response_model=TimeseriesResponse)
async def get_timeseries(
    start_date: str = Query(..., description="Range start in YYYY-MM-DD format"),
    end_date: str = Query(..., description="Range end in YYYY-MM-DD format"),
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    temp_type: str = Query("mean", description="Temperature type: mean or min"),
    service: NetCDFService = Depends(get_netcdf_service),
) -> TimeseriesResponse:
    """Get temperature time series for a specific coordinate across a date range."""
    try:
        start_obj: date = date.fromisoformat(start_date)
        end_obj: date = date.fromisoformat(end_date)

        timeseries_data: list[tuple[date, float]] = service.get_cell_timeseries(
            start_obj, end_obj, lat, lon, temp_type=temp_type
        )

        data_points = [
            TimeseriesDataPoint(date=d.isoformat(), value=v) for d, v in timeseries_data
        ]

        return TimeseriesResponse(
            lat=lat,
            lon=lon,
            start_date=start_date,
            end_date=end_date,
            data=data_points,
            units="K",
        )
    except DatasetNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"No data for date range {start_date} to {end_date}"
        ) from None
    except (ValueError, VariableNotFoundError, InvalidTimeIndexError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/continents", response_model=dict[str, ContinentDetail])
async def get_continents() -> dict[str, ContinentDetail]:
    return {
        name: ContinentDetail(
            bounds=ContinentBounds(
                min_lat=bounds[0],
                max_lat=bounds[1],
                min_lon=bounds[2],
                max_lon=bounds[3],
            )
        )
        for name, bounds in CONTINENTS.items()
    }


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
