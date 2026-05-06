import logging
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Handle imports for both direct execution and module invocation
try:
    from .api.routes.climate import router as climate_router
    from .api.routes.gdd import router as gdd_router
except ImportError:
    # Add parent directory to path for direct execution
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from backend.api.routes.climate import router as climate_router
    from backend.api.routes.gdd import router as gdd_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="FrostTool Backend",
        description="AgERA5 NetCDF Temperature Heatmap API",
        version="1.0.0",
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
    
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

