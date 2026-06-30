import dash_bootstrap_components as dbc
from dash import dcc, html

from frontend.config import PUBLIC_API_URL

from .map_component import get_map_html


def create_map_frame() -> html.Iframe:
    map_html: str = get_map_html(PUBLIC_API_URL)
    return html.Iframe(
        id="map-frame",
        srcDoc=map_html,
        style={"width": "100%", "height": "100%", "border": "none"},
    )


def create_controls() -> dbc.Col:
    label_style: dict = {
        "fontFamily": "'Montserrat',sans-serif",
        "fontSize": "10px",
        "letterSpacing": "2px",
        "color": "#3C8361",
        "marginBottom": "10px",
    }

    sidebar_style: dict = {
        "background": "#EEF2E6",
        "borderRight": "1px solid #3C8361",
        "padding": "26px 20px",
        "overflowY": "auto",
        "height": "100%",
    }

    return dbc.Col(
        width=3,
        style=sidebar_style,
        children=[
            html.H6("CONTINENT", style=label_style),
            dcc.Dropdown(
                id="continent-selector",
                options=[
                    {"label": "Global", "value": ""},
                    {"label": "Africa", "value": "Africa"},
                    {"label": "North America", "value": "North America"},
                    {"label": "South America", "value": "South America"},
                    {"label": "Europe", "value": "Europe"},
                    {"label": "Asia", "value": "Asia"},
                    {"label": "Oceania", "value": "Oceania"},
                ],
                value="",
                clearable=False,
                style={"width": "100%", "marginBottom": "12px"},
            ),
            dcc.Store(id="selected-continent", data=None),
            html.Hr(style={"borderColor": "#3C8361", "margin": "22px 0"}),
            html.H6("TEMPERATURE TYPE", style=label_style),
            dcc.Dropdown(
                id="temp-type-selector",
                options=[
                    {"label": "Mean (24h)", "value": "mean"},
                    {"label": "Minimum (24h)", "value": "min"},
                ],
                value="mean",
                clearable=False,
                style={"width": "100%", "marginBottom": "12px"},
            ),
            dcc.Store(id="selected-temp-type", data="mean"),
            html.Hr(style={"borderColor": "#3C8361", "margin": "22px 0"}),
            html.H6("DATE RANGE", style=label_style),
            dcc.DatePickerRange(
                id="date-range",
                start_date="2026-01-01",
                end_date="2026-01-31",
                display_format="YYYY-MM-DD",
                style={"width": "100%"},
            ),
            html.Div(
                id="date-status",
                style={
                    "fontFamily": "'Montserrat',sans-serif",
                    "fontSize": "11px",
                    "marginTop": "8px",
                    "color": "#3C8361",
                },
            ),
            html.Hr(style={"borderColor": "#3C8361", "margin": "22px 0"}),
            dbc.Button(
                "Render Heatmap",
                id="render-btn",
                style={
                    "width": "100%",
                    "fontFamily": "'Montserrat',sans-serif",
                    "fontWeight": "700",
                    "letterSpacing": "1px",
                    "background": "linear-gradient(135deg,#3C8361,#1B6758)",
                    "border": "none",
                    "color": "#EEF2E6",
                    "padding": "12px",
                    "borderRadius": "8px",
                },
            ),
            html.Hr(style={"borderColor": "#3C8361", "margin": "22px 0"}),
            html.H6("STATS", style=label_style),
            html.Div(
                id="stats-box",
                style={
                    "fontFamily": "'Montserrat',sans-serif",
                    "fontSize": "11px",
                    "color": "#3C8361",
                    "lineHeight": "1.9",
                },
            ),
        ],
    )


_NAV_LINK_STYLE: dict = {
    "fontFamily": "'Montserrat',sans-serif",
    "fontSize": "11px",
    "letterSpacing": "1px",
    "color": "#D6CDA4",
    "textDecoration": "none",
    "padding": "6px 14px",
    "borderRadius": "6px",
    "border": "1px solid rgba(214,205,164,0.35)",
    "transition": "background 0.2s",
}


def create_shared_header() -> html.Div:
    return html.Div(
        style={
            "background": "linear-gradient(135deg,#1B6758,#3C8361)",
            "borderBottom": "1px solid #3C8361",
            "padding": "16px 30px",
            "display": "flex",
            "alignItems": "center",
            "gap": "18px",
            "height": "72px",
            "boxSizing": "border-box",
        },
        children=[
            html.Img(
                src="/assets/logoWhite.png",
                style={"height": "42px", "width": "auto"},
            ),
            html.Div(
                style={"flex": "1"},
                children=[
                    html.H1(
                        "TERRA FrostExplorer",
                        style={
                            "fontFamily": "'Montserrat',sans-serif",
                            "fontWeight": "800",
                            "fontSize": "22px",
                            "color": "#EEF2E6",
                            "margin": "0",
                        },
                    ),
                    html.P(
                        "Global daily 2 m air temperature · ERA5-based · georaster-layer-for-leaflet",
                        style={
                            "fontFamily": "'Montserrat',sans-serif",
                            "fontSize": "10px",
                            "color": "#D6CDA4",
                            "margin": "3px 0 0",
                        },
                    ),
                ],
            ),
            html.Nav(
                style={"display": "flex", "gap": "10px"},
                children=[
                    dcc.Link("HEATMAP", href="/", style=_NAV_LINK_STYLE),
                    dcc.Link("FROST RISK", href="/gdd", style=_NAV_LINK_STYLE),
                ],
            ),
        ],
    )
