from typing import Any

# JSON payloads exchanged with dcc.Store, the browser (postMessage), or the
# backend API are heterogeneous by nature — Any is unavoidable here.
JSONDict = dict[str, Any]


def kelvin_to_celsius(kelvin: float) -> float:
    return kelvin - 273.15
