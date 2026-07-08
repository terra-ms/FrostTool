from dash import dcc, html


def create_graph_container() -> html.Div:
    return html.Div(
        id="graph-container",
        style={
            "height": "0%",
            "display": "none",
            "borderTop": "1px solid #3C8361",
            "background": "#0D4F44",
            "padding": "12px",
            "overflow": "hidden",
            "transition": "height 0.3s ease",
            "position": "relative",
        },
        children=[
            html.Button(
                "✕",
                id="close-graph-btn",
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
                id="timeseries-graph",
                style={"height": "100%", "margin": "0"},
                config={"responsive": True, "displayModeBar": False},
            ),
        ],
    )
