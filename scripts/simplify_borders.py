"""
Simplify GeoJSON border files for faster browser loading.

Run once whenever the source GeoJSON files change:
    python scripts/simplify_borders.py

Reduces admin0 from ~25 MB to < 1 MB by:
  - Applying Douglas-Peucker geometry simplification
  - Stripping all properties (borders only need geometry)
  - Rounding coordinates to 4 decimal places (~11 m precision)
"""

import json
from pathlib import Path

from shapely.geometry import mapping, shape

STATIC_DIR = Path(__file__).parent.parent / "backend" / "static"

CONFIGS = [
    {
        "src": STATIC_DIR / "ne_admin0.geojson",
        "dst": STATIC_DIR / "ne_admin0.geojson",
        "tolerance": 0.05,  # ~5 km — fine for country outlines at any map zoom
    },
    {
        "src": STATIC_DIR / "ne_admin1.geojson",
        "dst": STATIC_DIR / "ne_admin1.geojson",
        "tolerance": 0.01,  # ~1 km — fine for province outlines at zoom ≥ 5
    },
]

COORD_PRECISION = 4  # decimal places → ~11 m precision at equator


def _round_coords(obj: object) -> object:
    if isinstance(obj, float):
        return round(obj, COORD_PRECISION)
    if isinstance(obj, list):
        return [_round_coords(v) for v in obj]
    return obj


def simplify_file(src: Path, dst: Path, tolerance: float) -> None:
    print(f"Reading {src.name} ({src.stat().st_size / 1_000_000:.1f} MB)…")
    with src.open(encoding="utf-8") as f:
        fc = json.load(f)

    simplified_features = []
    skipped = 0
    for feat in fc["features"]:
        geom = shape(feat["geometry"])
        simplified = geom.simplify(tolerance, preserve_topology=True)
        if simplified.is_empty:
            skipped += 1
            continue
        coords = _round_coords(mapping(simplified)["coordinates"])
        simplified_features.append(
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": mapping(simplified)["type"],
                    "coordinates": coords,
                },
            }
        )

    out = {"type": "FeatureCollection", "features": simplified_features}
    with dst.open("w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))

    size_mb = dst.stat().st_size / 1_000_000
    print(
        f"  done: {dst.name}: {len(simplified_features)} features"
        f" ({skipped} empty skipped), {size_mb:.2f} MB"
    )


if __name__ == "__main__":
    for cfg in CONFIGS:
        simplify_file(cfg["src"], cfg["dst"], cfg["tolerance"])
    print("Done.")
