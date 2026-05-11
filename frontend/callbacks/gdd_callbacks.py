import logging

import requests
from dash import Input, Output, State, callback

from frontend.components.gdd_map_component import get_gdd_map_html, get_gdd_map_html_with_raster
from frontend.config import API_BASE_URL

logger = logging.getLogger(__name__)


@callback(
    Output("gdd-crop-selector", "options"),
    Output("gdd-crop-selector", "value"),
    Output("gdd-year-selector", "options"),
    Output("gdd-year-selector", "value"),
    Input("gdd-crop-selector", "id"),
    prevent_initial_call=False,
)
def populate_gdd_dropdowns(_: str) -> tuple[list[dict], str | None, list[dict], int | None]:
    crop_options: list[dict] = []
    default_crop: str | None = None
    year_options: list[dict] = []
    default_year: int | None = None

    try:
        r = requests.get(f"{API_BASE_URL}/gdd/crops", timeout=5)
        r.raise_for_status()
        crops = r.json()["crops"]
        crop_options = [{"label": c["display_name"], "value": c["name"]} for c in crops]
        default_crop = crop_options[0]["value"] if crop_options else None
    except Exception:
        logger.warning("Could not fetch crop list from backend.")
        crop_options = [{"label": "Grapevine", "value": "grapevine"}]
        default_crop = "grapevine"

    try:
        r = requests.get(f"{API_BASE_URL}/gdd/available-years", timeout=5)
        r.raise_for_status()
        data = r.json()
        year_options = [{"label": str(y), "value": y} for y in reversed(data["years"])]
        default_year = data["max_year"]
    except Exception:
        logger.warning("Could not fetch GDD available years; falling back to 1979–2007.")
        year_options = [{"label": str(y), "value": y} for y in range(2007, 1978, -1)]
        default_year = 2007

    return crop_options, default_crop, year_options, default_year


@callback(
    Output("gdd-map-frame", "srcDoc"),
    Output("gdd-status", "children"),
    Input("gdd-render-btn", "n_clicks"),
    State("gdd-crop-selector", "value"),
    State("gdd-year-selector", "value"),
    prevent_initial_call=True,
)
def render_gdd_map(
    n_clicks: int | None,
    crop: str | None,
    year: int | None,
) -> tuple[str, str]:
    if not crop or not year:
        return get_gdd_map_html(), "Select a crop and year, then click Render."

    raster_url = f"{API_BASE_URL}/gdd/raster?year={year}&crop={crop}"
    src = get_gdd_map_html_with_raster(raster_url, year, crop)
    crop_label = crop.capitalize()
    return src, f"Rendering {year} · {crop_label} — this may take ~30 s on first load."
