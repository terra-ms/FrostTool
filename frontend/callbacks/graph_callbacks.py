from datetime import datetime

import plotly.graph_objects as go
import requests
from dash import Input, Output, State, callback, callback_context

from frontend.components.map_component import API
from frontend.utils import kelvin_to_celsius

_EMPTY_LAYOUT: dict = dict(
    template="plotly_dark",
    paper_bgcolor="#0D4F44",
    plot_bgcolor="#0D4F44",
    font=dict(color="#EEF2E6", family="'Space Mono', monospace", size=11),
    showlegend=False,
)


@callback(
    Output("date-status", "children"),
    Input("date-range", "start_date"),
    Input("date-range", "end_date"),
)
def show_date_status(start_date: str | None, end_date: str | None) -> str:
    if not start_date or not end_date:
        return ""
    d_start = datetime.strptime(start_date[:10], "%Y-%m-%d")
    d_end = datetime.strptime(end_date[:10], "%Y-%m-%d")
    days = (d_end - d_start).days + 1
    if days > 180:
        return f"⚠ Range is {days} days (>6 months). Max allowed: 180 days."
    return f"✓ {days} days selected"


@callback(
    Output("graph-container", "style"),
    Input("clicked-coordinate", "data"),
    Input("close-graph-btn", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_graph_visibility(
    clicked_data: dict | None,
    close_clicks: int | None,
) -> dict:
    base_style: dict = {
        "borderTop": "1px solid #3C8361",
        "background": "#0D4F44",
        "padding": "12px",
        "overflow": "hidden",
        "transition": "height 0.3s ease",
        "position": "relative",
    }
    trigger_id: str | None = None
    if callback_context.triggered:
        trigger_id = callback_context.triggered[0]["prop_id"].split(".")[0]

    if trigger_id == "close-graph-btn":
        base_style["height"] = "0%"
    elif clicked_data:
        base_style["height"] = "25%"
    else:
        base_style["height"] = "0%"
    return base_style


@callback(
    Output("timeseries-graph", "figure"),
    Input("clicked-coordinate", "data"),
    State("raster-trigger", "data"),
    prevent_initial_call=True,
)
def update_timeseries_graph(
    clicked_coord: dict | None,
    raster_trigger: dict | None,
) -> go.Figure:
    if not clicked_coord or not raster_trigger:
        return go.Figure().update_layout(
            **_EMPTY_LAYOUT, margin=dict(l=40, r=20, t=30, b=40)
        )

    lat = clicked_coord.get("lat")
    lon = clicked_coord.get("lon")
    temp_type = raster_trigger.get("tempType", "mean")

    raster_date_range = raster_trigger.get("dateRange")
    if isinstance(raster_date_range, dict):
        start_date = raster_date_range.get("start")
        end_date = raster_date_range.get("end")
    else:
        start_date = raster_trigger.get("date")
        end_date = raster_trigger.get("date")

    if not start_date or not end_date:
        return go.Figure().update_layout(
            **_EMPTY_LAYOUT, margin=dict(l=40, r=20, t=30, b=40)
        )

    try:
        ts_url = (
            f"{API}/timeseries"
            f"?start_date={start_date}&end_date={end_date}"
            f"&lat={lat}&lon={lon}&temp_type={temp_type}"
        )
        response = requests.get(ts_url, timeout=30)
        response.raise_for_status()
        ts_data = response.json()

        dates = [d["date"] for d in ts_data["data"]]
        values_c = [kelvin_to_celsius(d["value"]) for d in ts_data["data"]]

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=values_c,
                mode="lines+markers",
                name="Temperature",
                line=dict(color="#D6CDA4", width=2),
                marker=dict(size=4, color="#D6CDA4"),
                hovertemplate="<b>%{x}</b><br>%{y:.1f}°C<extra></extra>",
            )
        )
        fig.update_layout(
            title=f"Temperature at {lat:.2f}°, {lon:.2f}° ({start_date} to {end_date})",
            xaxis_title="Date",
            yaxis_title="Temperature (°C)",
            **_EMPTY_LAYOUT,
            margin=dict(l=40, r=20, t=40, b=40),
            hovermode="x unified",
        )
        return fig

    except Exception as exc:
        fig = go.Figure()
        fig.add_annotation(
            text=f"Error loading timeseries: {exc}",
            showarrow=False,
            font=dict(size=12, color="#e07050"),
        )
        fig.update_layout(**_EMPTY_LAYOUT, margin=dict(l=40, r=20, t=30, b=40))
        return fig
