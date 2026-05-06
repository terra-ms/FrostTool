from pathlib import Path

import dash
import dash_bootstrap_components as dbc

from .components.controls import create_shared_header
from . import callbacks  # noqa: F401 — registers all callbacks

app = dash.Dash(
    __name__,
    use_pages=True,
    pages_folder=str(Path(__file__).parent / "pages"),
    external_stylesheets=[
        dbc.themes.CYBORG,
        "https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap",
    ],
    suppress_callback_exceptions=True,
    title="AgERA5 Climate Tool",
)

app.layout = dbc.Container(
    fluid=True,
    style={"background": "#1B6758", "minHeight": "100vh", "padding": "0"},
    children=[
        create_shared_header(),
        dash.page_container,
    ],
)


if __name__ == "__main__":
    app.run(debug=True, port=8050)
