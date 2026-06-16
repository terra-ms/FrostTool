from datetime import datetime

import dash
import requests
from dash import (
    Input,
    Output,
    State,
    callback,
    callback_context,
    clientside_callback,
    html,
)

from frontend.components.map_component import (
    API,
    get_map_html,
    get_map_html_with_initial_raster,
)
from frontend.config import PUBLIC_API_URL
from frontend.utils import kelvin_to_celsius

# ---------------------------------------------------------------------------
# Coordinate bridge: iframe → Dash store
# ---------------------------------------------------------------------------

clientside_callback(
    """
    function(n_clicks) {
        if (window._lastCoordinate) {
            return window._lastCoordinate;
        }
        return undefined;
    }
    """,
    Output("coordinate-intermediate", "data"),
    Input("coordinate-trigger", "n_clicks"),
    prevent_initial_call=False,
)


@callback(
    Output("clicked-coordinate", "data"),
    Input("coordinate-intermediate", "data"),
    prevent_initial_call=True,
)
def sync_coordinate_to_final_store(intermediate_data: dict | None) -> dict | None:
    return intermediate_data


clientside_callback(
    """
    function() {
        if (window._messageListenerSetup) {
            return '';
        }
        window._messageListenerSetup = true;

        window.addEventListener('message', function(e) {
            try {
                if (e.data && e.data.type === 'coordinateClicked') {
                    window._lastCoordinate = {
                        lat: e.data.lat,
                        lon: e.data.lon,
                        date: e.data.date,
                        dateRange: e.data.dateRange,
                    };
                    const btn = document.getElementById('coordinate-trigger');
                    if (btn) { btn.click(); }
                }
            } catch (err) {
                console.error('Error processing postMessage:', err);
            }
        });
        return '';
    }
    """,
    Output("map-frame", "title"),
    Input("map-frame", "id"),
    prevent_initial_call=False,
)


# ---------------------------------------------------------------------------
# Map rendering
# ---------------------------------------------------------------------------

@callback(
    Output("map-frame", "srcDoc"),
    Input("map-frame", "id"),
    Input("raster-trigger", "data"),
    prevent_initial_call=False,
)
def update_map(map_frame_id: str, trigger_data: dict | None) -> str:
    ctx = callback_context
    if ctx.triggered and ctx.triggered[0]["prop_id"].startswith("raster-trigger"):
        if not trigger_data:
            return get_map_html(PUBLIC_API_URL)
        return get_map_html_with_initial_raster(
            api_url=PUBLIC_API_URL,
            raster_url=trigger_data.get("rasterUrl"),
            colorscale_url=trigger_data.get("colorscaleUrl"),
            date=trigger_data.get("date"),
            continent=trigger_data.get("continent"),
            temp_type=trigger_data.get("tempType"),
        )
    return get_map_html(PUBLIC_API_URL)


@callback(
    Output("stats-box", "children"),
    Output("raster-trigger", "data"),
    Input("render-btn", "n_clicks"),
    State("date-range", "start_date"),
    State("date-range", "end_date"),
    State("selected-continent", "data"),
    State("selected-temp-type", "data"),
    prevent_initial_call=True,
)
def render_heatmap(
    n_clicks: int,
    start_date: str | None,
    end_date: str | None,
    selected_continent: str | None,
    selected_temp_type: str | None,
) -> tuple:
    if not start_date or not end_date:
        return (
            [html.Div("Please select a date range first.", style={"color": "#e07050"})],
            dash.no_update,
        )

    d_start_str: str = start_date[:10]
    d_end_str: str = end_date[:10]
    d_start = datetime.strptime(d_start_str, "%Y-%m-%d")
    d_end = datetime.strptime(d_end_str, "%Y-%m-%d")
    days: int = (d_end - d_start).days + 1

    if days > 180:
        return (
            [
                html.Div(
                    f"⚠ Range is {days} days (>6 months). Max allowed: 180 days.",
                    style={"color": "#e07050"},
                )
            ],
            dash.no_update,
        )

    temp_type = selected_temp_type or "mean"

    try:
        qs = f"?start_date={d_start_str}&end_date={d_end_str}&agg_type=min&temp_type={temp_type}"
        colorscale_url_internal = f"{API}/colorscale{qs}"
        colorscale_url = f"{PUBLIC_API_URL}/colorscale{qs}"
        raster_url = f"{PUBLIC_API_URL}/raster{qs}"
        if selected_continent:
            raster_url += f"&continent={selected_continent}"

        cs: dict = requests.get(colorscale_url_internal, timeout=60).json()
    except Exception as exc:
        return (
            [html.Div(f"Backend error: {exc}", style={"color": "#e07050"})],
            dash.no_update,
        )

    if "detail" in cs:
        return (
            [html.Div(f"⚠ {cs['detail']}", style={"color": "#e07050"})],
            dash.no_update,
        )

    temp_type_label = "Minimum (24h)" if temp_type == "min" else "Mean (24h)"

    stats: list = [
        html.Div(f"Date Range : {d_start_str} to {d_end_str}"),
        html.Div(f"Days       : {days}"),
        html.Div(f"Type       : {temp_type_label}"),
        html.Div("Aggregation: Minimum (frost detection)"),
        html.Div("Units      : °C"),
        html.Div(f"Min        : {kelvin_to_celsius(cs['min_value']):.3f}"),
        html.Div(f"Max        : {kelvin_to_celsius(cs['max_value']):.3f}"),
        html.Div(f"Mean       : {kelvin_to_celsius(cs['mean_value']):.3f}"),
    ]

    trigger: dict = {
        "rasterUrl": raster_url,
        "colorscaleUrl": colorscale_url,
        "date": d_start_str,
        "dateRange": {"start": d_start_str, "end": d_end_str} if d_start != d_end else None,
        "continent": selected_continent,
        "tempType": temp_type,
    }
    return stats, trigger


@callback(
    Output("selected-continent", "data"),
    Input("continent-selector", "value"),
    prevent_initial_call=True,
)
def select_continent(value: str | None) -> str | None:
    return value if value else None


@callback(
    Output("selected-temp-type", "data"),
    Input("temp-type-selector", "value"),
    prevent_initial_call=True,
)
def select_temp_type(value: str | None) -> str | None:
    return value if value else "mean"
