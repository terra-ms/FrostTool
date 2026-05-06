from dash import Input, Output, State, callback

from frontend.components.gdd_map_component import get_gdd_map_html, get_gdd_map_html_with_raster
from frontend.config import API_BASE_URL


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
