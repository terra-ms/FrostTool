import logging
from concurrent.futures import Future, ThreadPoolExecutor

import plotly.graph_objects as go
import requests
from dash import Input, Output, State, callback, callback_context, clientside_callback

from frontend.components.gdd_map_component import get_gdd_map_html, get_gdd_map_html_with_raster
from frontend.config import API_BASE_URL

logger = logging.getLogger(__name__)

# Module-level cache: populated on first successful fetch per Dash server session.
# Subsequent navigations to /gdd return instantly without hitting the backend.
_cached_crop_options: list[dict] | None = None
_cached_year_options: list[dict] | None = None
_cached_default_year: int | None = None

_TIMEOUT = 5  # seconds per request


def _fetch_crops() -> list[dict]:
    r = requests.get(f"{API_BASE_URL}/gdd/crops", timeout=_TIMEOUT)
    r.raise_for_status()
    return [{"label": c["display_name"], "value": c["name"]} for c in r.json()["crops"]]


def _fetch_years() -> tuple[list[dict], int]:
    r = requests.get(f"{API_BASE_URL}/gdd/available-years", timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    options = [{"label": str(y), "value": y} for y in reversed(data["years"])]
    return options, data["max_year"]


@callback(
    Output("gdd-crop-selector", "options"),
    Output("gdd-crop-selector", "value"),
    Output("gdd-year-selector", "options"),
    Output("gdd-year-selector", "value"),
    Input("gdd-page-store", "data"),
    prevent_initial_call=False,
)
def populate_gdd_dropdowns(_: bool) -> tuple[list[dict], str | None, list[dict], int | None]:
    global _cached_crop_options, _cached_year_options, _cached_default_year

    if _cached_crop_options is not None and _cached_year_options is not None:
        default_crop = _cached_crop_options[0]["value"] if _cached_crop_options else None
        return _cached_crop_options, default_crop, _cached_year_options, _cached_default_year

    # Both requests run in parallel — worst-case block is _TIMEOUT, not 2 × _TIMEOUT.
    crop_options: list[dict] = []
    default_crop: str | None = None
    year_options: list[dict] = []
    default_year: int | None = None

    with ThreadPoolExecutor(max_workers=2) as pool:
        crops_future: Future[list[dict]] = pool.submit(_fetch_crops)
        years_future: Future[tuple[list[dict], int]] = pool.submit(_fetch_years)

        try:
            crop_options = crops_future.result()
            default_crop = crop_options[0]["value"] if crop_options else None
        except Exception as exc:
            logger.warning("Could not fetch crop list from backend: %s", exc)
            crop_options = [{"label": "Grapevine", "value": "grapevine"}]
            default_crop = "grapevine"

        try:
            year_options, default_year = years_future.result()
        except Exception as exc:
            logger.warning("Could not fetch available years from backend: %s", exc)
            year_options = [{"label": str(y), "value": y} for y in range(2007, 1978, -1)]
            default_year = 2007

    # Only cache if both fetches succeeded (i.e., we got real data, not fallbacks).
    if crops_future.exception() is None and years_future.exception() is None:
        _cached_crop_options = crop_options
        _cached_year_options = year_options
        _cached_default_year = default_year

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


# ---------------------------------------------------------------------------
# Coordinate bridge: GDD iframe → Dash store
# ---------------------------------------------------------------------------

clientside_callback(
    """
    function(n_clicks) {
        if (window._lastGDDCoordinate) {
            return window._lastGDDCoordinate;
        }
        return undefined;
    }
    """,
    Output("gdd-coordinate-intermediate", "data"),
    Input("gdd-coordinate-trigger", "n_clicks"),
    prevent_initial_call=False,
)

clientside_callback(
    """
    function() {
        if (window._gddMessageListenerSetup) {
            return '';
        }
        window._gddMessageListenerSetup = true;

        window.addEventListener('message', function(e) {
            try {
                if (e.data && e.data.type === 'gddCoordinateClicked') {
                    window._lastGDDCoordinate = {
                        lat: e.data.lat,
                        lon: e.data.lon,
                        year: e.data.year,
                        crop: e.data.crop,
                    };
                    const btn = document.getElementById('gdd-coordinate-trigger');
                    if (btn) { btn.click(); }
                }
            } catch (err) {
                console.error('Error processing GDD postMessage:', err);
            }
        });
        return '';
    }
    """,
    Output("gdd-map-frame", "title"),
    Input("gdd-map-frame", "id"),
    prevent_initial_call=False,
)


@callback(
    Output("gdd-clicked-coordinate", "data"),
    Input("gdd-coordinate-intermediate", "data"),
    prevent_initial_call=True,
)
def sync_gdd_coordinate(intermediate: dict | None) -> dict | None:
    return intermediate


# ---------------------------------------------------------------------------
# Graph panel visibility
# ---------------------------------------------------------------------------

@callback(
    Output("gdd-graph-container", "style"),
    Input("gdd-clicked-coordinate", "data"),
    Input("gdd-close-graph-btn", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_gdd_graph(clicked: dict | None, close_clicks: int | None) -> dict:
    base: dict = {
        "borderTop": "1px solid #3C8361",
        "background": "#0D4F44",
        "overflow": "hidden",
        "transition": "height 0.3s ease",
        "position": "relative",
    }
    trigger = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else None
    base["height"] = "0%" if (trigger == "gdd-close-graph-btn" or not clicked) else "30%"
    return base


# ---------------------------------------------------------------------------
# GDD timeseries graph
# ---------------------------------------------------------------------------

_BASE_LAYOUT: dict = dict(
    template="plotly_dark",
    paper_bgcolor="#0D4F44",
    plot_bgcolor="#0D4F44",
    font=dict(color="#EEF2E6", family="'Space Mono', monospace", size=11),
)

_EMPTY_MARGIN = dict(l=50, r=60, t=35, b=40)


def _empty_figure() -> go.Figure:
    return go.Figure().update_layout(**_BASE_LAYOUT, margin=_EMPTY_MARGIN, showlegend=False)


@callback(
    Output("gdd-timeseries-graph", "figure"),
    Input("gdd-clicked-coordinate", "data"),
    prevent_initial_call=True,
)
def update_gdd_timeseries(clicked: dict | None) -> go.Figure:
    if not clicked:
        return _empty_figure()

    lat = clicked.get("lat")
    lon = clicked.get("lon")
    year = clicked.get("year")
    crop = clicked.get("crop")

    if not all([lat is not None, lon is not None, year, crop]):
        return _empty_figure()

    try:
        url = f"{API_BASE_URL}/gdd/timeseries?lat={lat}&lon={lon}&year={year}&crop={crop}"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        ts = resp.json()
    except Exception as exc:
        fig = _empty_figure()
        fig.add_annotation(
            text=f"Error loading data: {exc}",
            showarrow=False,
            font=dict(size=11, color="#e07050"),
        )
        return fig

    dates = [dp["date"] for dp in ts["data"]]
    gdd_vals = [dp["cumulative_gdd"] for dp in ts["data"]]
    tmin_vals = [dp["daily_tmin"] for dp in ts["data"]]
    gdd_threshold: float = ts["gdd_threshold"]
    frost_threshold: float = ts["frost_threshold"]
    budbreak_date: str | None = ts.get("budbreak_date")
    frost_dates: list[str] = ts.get("frost_event_dates", [])
    crop_label: str = ts["crop_display_name"]

    fig = go.Figure()

    # --- Primary trace: daily Tmin ---
    fig.add_trace(go.Scatter(
        x=dates,
        y=tmin_vals,
        name="Daily Tmin",
        line=dict(color="#3b82f6", width=1.5),
        hovertemplate="%{y:.1f}°C<extra></extra>",
    ))

    # Frost threshold reference line (primary axis)
    fig.add_shape(
        type="line",
        x0=dates[0], x1=dates[-1],
        y0=frost_threshold, y1=frost_threshold,
        line=dict(dash="dash", color="#f97316", width=1.5),
        xref="x", yref="y",
    )
    fig.add_annotation(
        x=dates[-1], y=frost_threshold,
        text=f"Frost ({frost_threshold}°C)",
        xanchor="right", yanchor="top",
        font=dict(color="#f97316", size=9),
        showarrow=False,
        xref="x", yref="y",
    )

    # Frost event markers
    if frost_dates and budbreak_date:
        date_set = set(dates)
        valid_frost = [d for d in frost_dates if d in date_set]
        if valid_frost:
            idx_map = {d: i for i, d in enumerate(dates)}
            frost_tmin = [tmin_vals[idx_map[d]] for d in valid_frost]
            fig.add_trace(go.Scatter(
                x=valid_frost,
                y=frost_tmin,
                mode="markers",
                name="Frost event",
                marker=dict(
                    color="#f97316",
                    size=9,
                    symbol="x-thin",
                    line=dict(width=2.5, color="#f97316"),
                ),
                hovertemplate="<b>Frost: %{x}</b><br>Tmin: %{y:.1f}°C<extra></extra>",
            ))

    # --- Secondary trace: cumulative GDD ---
    fig.add_trace(go.Scatter(
        x=dates,
        y=gdd_vals,
        name="Cumulative GDD",
        line=dict(color="#3C8361", width=2.5),
        hovertemplate="%{y:.1f} GDD°C<extra></extra>",
        yaxis="y2",
    ))

    # GDD threshold reference line (secondary axis)
    fig.add_shape(
        type="line",
        x0=dates[0], x1=dates[-1],
        y0=gdd_threshold, y1=gdd_threshold,
        line=dict(dash="dash", color="#2d8a4e", width=1.5),
        xref="x", yref="y2",
    )
    fig.add_annotation(
        x=dates[-1], y=gdd_threshold,
        text=f"Budbreak ({gdd_threshold:.0f}°C·d)",
        xanchor="right", yanchor="bottom",
        font=dict(color="#2d8a4e", size=9),
        showarrow=False,
        xref="x", yref="y2",
    )

    # Budbreak vertical marker
    if budbreak_date:
        fig.add_shape(
            type="line",
            x0=budbreak_date, x1=budbreak_date,
            y0=0, y1=1,
            line=dict(dash="dot", color="#2d8a4e", width=1.5),
            xref="x", yref="paper",
        )
        fig.add_annotation(
            x=budbreak_date, y=0.97,
            text="Budbreak",
            xanchor="center", yanchor="top",
            font=dict(color="#2d8a4e", size=9),
            showarrow=False,
            xref="x", yref="paper",
        )

    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(
            text=f"{crop_label} — {year}  |  {lat:.2f}°N, {lon:.2f}°E",
            font=dict(size=11),
            x=0.01,
            xanchor="left",
        ),
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(
            title=dict(text="Temperature (°C)", font=dict(color="#3b82f6")),
            tickfont=dict(color="#3b82f6"),
            gridcolor="rgba(0,0,0,0)",
            zeroline=True,
            zerolinecolor="rgba(59,130,246,0.25)",
        ),
        yaxis2=dict(
            title=dict(text="Cumulative GDD (°C·days)", font=dict(color="#3C8361")),
            overlaying="y",
            side="right",
            tickfont=dict(color="#3C8361"),
            gridcolor="rgba(60,131,97,0.15)",
            zeroline=False,
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.01,
            xanchor="right", x=1,
            font=dict(size=9),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=60, r=70, t=45, b=40),
        hovermode="x unified",
        showlegend=True,
    )
    return fig
