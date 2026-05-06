import logging

import dash
import requests
from dash import dcc, html
import dash_bootstrap_components as dbc

from frontend.components.gdd_map_component import create_gdd_map_frame
from frontend.config import API_BASE_URL

dash.register_page(__name__, path="/gdd", name="Frost Risk")

logger = logging.getLogger(__name__)

_LABEL_STYLE: dict = {
    "fontFamily": "'Space Mono',monospace",
    "fontSize": "10px",
    "letterSpacing": "2px",
    "color": "#3C8361",
    "marginBottom": "10px",
}

_SIDEBAR_STYLE: dict = {
    "background": "#EEF2E6",
    "borderRight": "1px solid #3C8361",
    "padding": "26px 20px",
    "overflowY": "auto",
    "height": "100%",
}

_BTN_STYLE: dict = {
    "width": "100%",
    "fontFamily": "'Space Mono',monospace",
    "fontWeight": "700",
    "letterSpacing": "1px",
    "background": "linear-gradient(135deg,#3C8361,#1B6758)",
    "border": "none",
    "color": "#EEF2E6",
    "padding": "12px",
    "borderRadius": "8px",
}

_LEGEND_ITEMS = [
    ("#bebebe", "Never reached budbreak"),
    ("#2d8a4e", "Budbreak reached, no frost"),
    ("#3b82f6", "1 frost event"),
    ("#f97316", "2–4 frost events"),
    ("#7f1d1d", "5+ frost events"),
]


def _fetch_crop_options() -> list[dict]:
    try:
        r = requests.get(f"{API_BASE_URL}/gdd/crops", timeout=5)
        r.raise_for_status()
        return [
            {"label": c["display_name"], "value": c["name"]}
            for c in r.json()["crops"]
        ]
    except Exception:
        logger.warning("Could not fetch crop list from backend; using defaults.")
        return [{"label": "Grapevine", "value": "grapevine"}]


def _fetch_year_options() -> tuple[list[dict], int]:
    """Returns (dropdown options, default year). Falls back to 1979–2007 if API is unreachable."""
    try:
        r = requests.get(f"{API_BASE_URL}/gdd/available-years", timeout=5)
        r.raise_for_status()
        data = r.json()
        years = data["years"]
        options = [{"label": str(y), "value": y} for y in reversed(years)]
        default = data["max_year"]
        return options, default
    except Exception:
        logger.warning("Could not fetch GDD available years; falling back to 1979–2007.")
        options = [{"label": str(y), "value": y} for y in range(2007, 1978, -1)]
        return options, 2007


def layout() -> dbc.Row:
    crop_options = _fetch_crop_options()
    default_crop = crop_options[0]["value"] if crop_options else None
    year_options, default_year = _fetch_year_options()

    return dbc.Row(
        style={
            "margin": "0",
            "height": "calc(100vh - 72px)",
            "flexWrap": "nowrap",
        },
        children=[
            dbc.Col(
                width=3,
                style=_SIDEBAR_STYLE,
                children=[
                    html.H6("CROP", style=_LABEL_STYLE),
                    dcc.Dropdown(
                        id="gdd-crop-selector",
                        options=crop_options,
                        value=default_crop,
                        clearable=False,
                        style={"width": "100%", "marginBottom": "12px"},
                    ),
                    html.Hr(style={"borderColor": "#3C8361", "margin": "22px 0"}),
                    html.H6("YEAR", style=_LABEL_STYLE),
                    dcc.Dropdown(
                        id="gdd-year-selector",
                        options=year_options,
                        value=default_year,
                        clearable=False,
                        style={"width": "100%", "marginBottom": "12px"},
                    ),
                    html.Hr(style={"borderColor": "#3C8361", "margin": "22px 0"}),
                    dbc.Button("Render Frost Map", id="gdd-render-btn", style=_BTN_STYLE),
                    html.Div(
                        id="gdd-status",
                        style={
                            "fontFamily": "'Space Mono',monospace",
                            "fontSize": "11px",
                            "color": "#3C8361",
                            "marginTop": "12px",
                            "lineHeight": "1.9",
                        },
                    ),
                    html.Hr(style={"borderColor": "#3C8361", "margin": "22px 0"}),
                    html.H6("LEGEND", style=_LABEL_STYLE),
                    html.Div([
                        html.Div(
                            style={
                                "display": "flex",
                                "alignItems": "center",
                                "gap": "8px",
                                "marginBottom": "8px",
                            },
                            children=[
                                html.Div(style={
                                    "width": "18px",
                                    "height": "18px",
                                    "borderRadius": "3px",
                                    "background": color,
                                    "flexShrink": "0",
                                    "border": "1px solid rgba(0,0,0,0.15)",
                                }),
                                html.Span(label, style={
                                    "fontFamily": "'Space Mono',monospace",
                                    "fontSize": "10px",
                                    "color": "#3C8361",
                                }),
                            ],
                        )
                        for color, label in _LEGEND_ITEMS
                    ]),
                    html.Hr(style={"borderColor": "#3C8361", "margin": "22px 0"}),
                    html.P(
                        "Season: 1 Jan – 31 May. Frost event = Tmin < frost threshold "
                        "after accumulated GDD exceeds budbreak threshold. "
                        "Crop parameters are editable in crops.txt.",
                        style={
                            "fontFamily": "'Space Mono',monospace",
                            "fontSize": "9px",
                            "color": "#3C8361",
                            "lineHeight": "1.7",
                        },
                    ),
                ],
            ),
            dbc.Col(
                width=9,
                style={"padding": "0", "height": "100%"},
                children=[create_gdd_map_frame()],
            ),
        ],
    )
