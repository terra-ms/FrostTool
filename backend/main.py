import logging
import os
import sys
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Handle imports for both direct execution and module invocation
try:
    from .api.routes.climate import router as climate_router
    from .api.routes.debug import router as debug_router
    from .api.routes.gdd import router as gdd_router
except ImportError:
    # Add parent directory to path for direct execution
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from backend.api.routes.climate import router as climate_router
    from backend.api.routes.debug import router as debug_router
    from backend.api.routes.gdd import router as gdd_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _warmup_gdd_stacks() -> None:
    """Pre-warm year stacks and all crop×year results for GDD_WARMUP_MIN_YEAR onward.

    Runs in a background daemon thread so the app accepts requests immediately.
    Each year's stack (~166 MB combined) is loaded once from disk and cached; subsequent
    crops for the same year only run fast numpy math on the cached stack.
    """
    try:
        from backend.core.config import GDD_WARMUP_MIN_YEAR
        from backend.services.gdd_service import (
            GDDService,
            get_available_gdd_years,
            load_crops,
            warm_year_stack,
        )

        years = [y for y in get_available_gdd_years() if y >= GDD_WARMUP_MIN_YEAR]
        crops = load_crops()
        logger.info(
            "GDD warm-up starting: %d year(s) from %d, %d crop(s)",
            len(years),
            GDD_WARMUP_MIN_YEAR,
            len(crops),
        )

        # Most recent years first — most likely to be requested first.
        for year in reversed(years):
            try:
                warm_year_stack(year)
                for crop_params in crops.values():
                    GDDService.compute_frost_event_count(year, crop_params)
                logger.info("GDD warm-up: year %d complete", year)
            except Exception as exc:
                logger.warning("GDD warm-up: year %d failed — %s", year, exc)

        logger.info("GDD warm-up complete.")
    except Exception as exc:
        logger.error("GDD warm-up thread failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Pre-populate the available-years cache synchronously before the warm-up thread
    # starts. The warm-up saturates the data drive with concurrent HDF5 reads; without
    # this, the first call to get_available_gdd_years() inside an async endpoint would
    # run its Path.glob() while the drive is under load, blocking the Uvicorn event loop
    # and causing all pending requests (including the trivial /gdd/crops call) to time out.
    from backend.services.gdd_service import get_available_gdd_years

    get_available_gdd_years()
    logger.info("Available GDD years cached: %s", get_available_gdd_years())

    thread = threading.Thread(target=_warmup_gdd_stacks, daemon=True, name="gdd-warmup")
    thread.start()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="FrostTool Backend",
        description="AgERA5 NetCDF Temperature Heatmap API",
        version="1.0.0",
        lifespan=lifespan,
    )

    allowed_origins = os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost:8050,http://127.0.0.1:8050",
    ).split(",")

    # Add CORS middleware BEFORE routes
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.include_router(climate_router)
    app.include_router(gdd_router)
    app.include_router(debug_router)

    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
