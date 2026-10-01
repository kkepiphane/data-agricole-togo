"""Limites administratives, géométries et calculs spatiaux."""
from __future__ import annotations

import json
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from .cleaning import norm_key

WGS84 = 4326
UTM_TOGO = 32631  # UTM 31N, adapté au Togo (0°–1,8° E) pour les surfaces

# Préfectures dont le nom diffère entre les limites OCHA (2021) et les données.
# « Lomé Commune » est fusionnée dans Golfe : les données ne la distinguent pas.
PREFECTURE_ALIASES = {
    "plainedumo": "Mô",
    "nakiouest": "Kpendjal-Ouest",
    "lomecommune": "Golfe",
}

TOGO_BOUNDS = (-0.15, 6.10, 1.81, 11.14)


def parse_wkt(series: pd.Series) -> gpd.GeoSeries:
    """WKT → géométries ; les valeurs illisibles deviennent None."""
    return gpd.GeoSeries(shapely.from_wkt(series.to_numpy(), on_invalid="ignore"), crs=WGS84)


def area_ha(geoms: gpd.GeoSeries) -> pd.Series:
    """Surface en hectares, calculée en projection UTM 31N."""
    return geoms.to_crs(UTM_TOGO).area / 10_000


def load_prefectures(boundary_dir: Path, data_names: list[str]) -> gpd.GeoDataFrame:
    """Polygones des préfectures, renommés selon l'orthographe des données."""
    path = boundary_dir / "tgo_admin2.geojson"
    if not path.exists():
        raise FileNotFoundError(
            f"Limites administratives introuvables : {path}. "
            "Télécharger « Togo - Subnational Administrative Boundaries » (HDX, cod-ab-tgo)."
        )
    raw = gpd.read_file(path)
    lookup = {norm_key(n): n for n in data_names}
    raw["prefecture"] = raw["adm2_name"].map(
        lambda n: PREFECTURE_ALIASES.get(norm_key(n)) or lookup.get(norm_key(n)) or n
    )
    out = raw.dissolve(by="prefecture", aggfunc={"adm1_name": "first", "area_sqkm": "sum"}).reset_index()
    out = out.rename(columns={"adm1_name": "region", "area_sqkm": "superficie_km2"})
    return out[["prefecture", "region", "superficie_km2", "geometry"]].sort_values("prefecture", ignore_index=True)


def simplify_coverage(gdf: gpd.GeoDataFrame, tolerance: float = 0.002) -> gpd.GeoDataFrame:
    """Simplifie les contours pour l'affichage sans créer de vides entre voisins."""
    out = gdf.copy()
    try:
        out["geometry"] = shapely.coverage_simplify(out.geometry.to_numpy(), tolerance)
    except Exception:
        out["geometry"] = out.geometry.simplify(tolerance / 2, preserve_topology=True)
    return out


def to_geojson(gdf: gpd.GeoDataFrame, id_col: str) -> dict:
    """GeoJSON dont l'identifiant de chaque entité est `id_col`."""
    gj = json.loads(gdf.to_json(drop_id=True))
    for feature in gj["features"]:
        feature["id"] = feature["properties"][id_col]
        for ring in _rings(feature["geometry"]):
            ring[:] = [[round(x, 5), round(y, 5)] for x, y in ring]
    return gj


def _rings(geometry: dict):
    polys = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    for poly in polys:
        yield from poly


def within_declared(points: gpd.GeoDataFrame, prefectures: gpd.GeoDataFrame) -> pd.Series:
    """Vrai si le point tombe dans le polygone de sa préfecture déclarée."""
    joined = gpd.sjoin(points[["prefecture", "geometry"]], prefectures[["prefecture", "geometry"]],
                       how="left", predicate="within", lsuffix="decl", rsuffix="geo")
    joined = joined[~joined.index.duplicated()]
    return (joined["prefecture_decl"] == joined["prefecture_geo"]).reindex(points.index)


def map_view(bounds, width: int = 760, height: int = 640) -> dict:
    """Centre et zoom cadrant une emprise (lon_min, lat_min, lon_max, lat_max)."""
    minx, miny, maxx, maxy = bounds
    lon_span, lat_span = max(maxx - minx, 0.06), max(maxy - miny, 0.06)
    zoom = min(math.log2(360 * width / (512 * lon_span)), math.log2(360 * height / (512 * lat_span)))
    return {"center": {"lon": (minx + maxx) / 2, "lat": (miny + maxy) / 2},
            "zoom": float(np.clip(zoom - 0.35, 5.2, 12))}
