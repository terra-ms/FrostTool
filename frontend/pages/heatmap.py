import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from frontend.components.controls import create_controls, create_map_frame
from frontend.components.timeline_graph import create_graph_container

# dash.register_page has no type annotations in the dash package itself.
dash.register_page(__name__, path="/", name="Heatmap")  # type: ignore[no-untyped-call]


def layout() -> dbc.Row:
    return dbc.Row(
        style={
            "margin": "0",
            "height": "calc(100vh - 72px)",
            "display": "flex",
            "flexDirection": "column",
        },
        children=[
            dbc.Row(
                style={"margin": "0", "flex": "1", "minHeight": "0"},
                children=[
                    create_controls(),
                    dbc.Col(
                        width=9,
                        style={
                            "padding": "0",
                            "display": "flex",
                            "flexDirection": "column",
                        },
                        children=[
                            html.Div(
                                style={
                                    "flex": "1",
                                    "minHeight": "0",
                                    "position": "relative",
                                },
                                children=[
                                    create_map_frame(),
                                    dcc.Store(id="raster-trigger"),
                                    dcc.Store(id="raster-postmessage-ack"),
                                    dcc.Store(id="raster-trigger-sent"),
                                    dcc.Store(id="clicked-coordinate"),
                                    dcc.Store(id="coordinate-intermediate"),
                                    html.Button(
                                        id="coordinate-trigger",
                                        style={"display": "none"},
                                    ),
                                ],
                            ),
                            create_graph_container(),
                        ],
                    ),
                ],
            ),
        ],
    )
