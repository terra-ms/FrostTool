import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from frontend.components.gdd_map_component import create_gdd_map_frame

dash.register_page(__name__, path="/gdd", name="Frost Risk")

_LABEL_STYLE: dict = {
    "fontFamily": "'Montserrat',sans-serif",
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
    "fontFamily": "'Montserrat',sans-serif",
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


def layout() -> dbc.Row:
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
                    dcc.Store(id="gdd-page-store", data=True),
                    html.H6("CROP", style=_LABEL_STYLE),
                    dcc.Dropdown(
                        id="gdd-crop-selector",
                        options=[],
                        value=None,
                        clearable=False,
                        placeholder="Loading…",
                        style={"width": "100%", "marginBottom": "12px"},
                    ),
                    html.Hr(style={"borderColor": "#3C8361", "margin": "22px 0"}),
                    html.H6("YEAR", style=_LABEL_STYLE),
                    dcc.Dropdown(
                        id="gdd-year-selector",
                        options=[],
                        value=None,
                        clearable=False,
                        placeholder="Loading…",
                        style={"width": "100%", "marginBottom": "12px"},
                    ),
                    html.Hr(style={"borderColor": "#3C8361", "margin": "22px 0"}),
                    html.H6("TIME PERIOD", style=_LABEL_STYLE),
                    html.P(
                        "Filter frost events by date range within the season. "
                        "Leave blank to show the full Jan – May season.",
                        style={
                            "fontFamily": "'Montserrat',sans-serif",
                            "fontSize": "9px",
                            "color": "#3C8361",
                            "lineHeight": "1.6",
                            "marginBottom": "10px",
                        },
                    ),
                    dcc.DatePickerRange(
                        id="gdd-period-picker",
                        start_date=None,
                        end_date=None,
                        start_date_placeholder_text="From",
                        end_date_placeholder_text="To",
                        display_format="D MMM",
                        style={"marginBottom": "12px"},
                    ),
                    html.Hr(style={"borderColor": "#3C8361", "margin": "22px 0"}),
                    dbc.Button(
                        "Render Frost Map", id="gdd-render-btn", style=_BTN_STYLE
                    ),
                    html.Div(
                        id="gdd-status",
                        style={
                            "fontFamily": "'Montserrat',sans-serif",
                            "fontSize": "11px",
                            "color": "#3C8361",
                            "marginTop": "12px",
                            "lineHeight": "1.9",
                        },
                    ),
                    html.Hr(style={"borderColor": "#3C8361", "margin": "22px 0"}),
                    html.H6("LEGEND", style=_LABEL_STYLE),
                    html.Div(
                        [
                            html.Div(
                                style={
                                    "display": "flex",
                                    "alignItems": "center",
                                    "gap": "8px",
                                    "marginBottom": "8px",
                                },
                                children=[
                                    html.Div(
                                        style={
                                            "width": "18px",
                                            "height": "18px",
                                            "borderRadius": "3px",
                                            "background": color,
                                            "flexShrink": "0",
                                            "border": "1px solid rgba(0,0,0,0.15)",
                                        }
                                    ),
                                    html.Span(
                                        label,
                                        style={
                                            "fontFamily": "'Montserrat',sans-serif",
                                            "fontSize": "10px",
                                            "color": "#3C8361",
                                        },
                                    ),
                                ],
                            )
                            for color, label in _LEGEND_ITEMS
                        ]
                    ),
                    html.Hr(style={"borderColor": "#3C8361", "margin": "22px 0"}),
                    html.P(
                        "Season: 1 Jan – 31 May. Frost event = Tmin < frost threshold "
                        "after accumulated GDD exceeds budbreak threshold. "
                        "Crop parameters are editable in crops.txt.",
                        style={
                            "fontFamily": "'Montserrat',sans-serif",
                            "fontSize": "9px",
                            "color": "#3C8361",
                            "lineHeight": "1.7",
                        },
                    ),
                ],
            ),
            dbc.Col(
                width=9,
                style={
                    "padding": "0",
                    "height": "100%",
                    "display": "flex",
                    "flexDirection": "column",
                },
                children=[
                    html.Div(
                        style={"flex": "1", "minHeight": "0", "position": "relative"},
                        children=[
                            create_gdd_map_frame(),
                            dcc.Store(id="gdd-coordinate-intermediate"),
                            dcc.Store(id="gdd-clicked-coordinate"),
                            dcc.Store(id="gdd-active-period"),
                            html.Button(
                                id="gdd-coordinate-trigger",
                                style={"display": "none"},
                                n_clicks=0,
                            ),
                        ],
                    ),
                    html.Div(
                        id="gdd-graph-container",
                        style={
                            "height": "0%",
                            "display": "none",
                            "borderTop": "1px solid #3C8361",
                            "background": "#0D4F44",
                            "overflow": "hidden",
                            "transition": "height 0.3s ease",
                            "position": "relative",
                        },
                        children=[
                            html.Button(
                                "✕",
                                id="gdd-close-graph-btn",
                                n_clicks=0,
                                style={
                                    "position": "absolute",
                                    "top": "8px",
                                    "right": "8px",
                                    "background": "transparent",
                                    "border": "none",
                                    "color": "#D6CDA4",
                                    "fontSize": "20px",
                                    "cursor": "pointer",
                                    "padding": "0",
                                    "width": "24px",
                                    "height": "24px",
                                    "display": "flex",
                                    "alignItems": "center",
                                    "justifyContent": "center",
                                    "zIndex": "10",
                                },
                            ),
                            dcc.Graph(
                                id="gdd-timeseries-graph",
                                style={"height": "100%", "margin": "0"},
                                config={"responsive": True, "displayModeBar": False},
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )
