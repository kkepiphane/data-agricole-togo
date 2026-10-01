"""Lecture des fichiers bruts, construction et chargement des données traitées."""
from __future__ import annotations

import json
import re
import warnings
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd

from . import geo
from .cleaning import clean_place, clean_text, norm_key, parse_days, parse_set, parse_year

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
BOUNDARY_DIR = RAW_DIR / "limites_admin"

ADMIN_COLS = {"region_nom_bdd": "region", "prefecture_nom_bdd": "prefecture",
              "commune_nom_bdd": "commune", "canton_nom_bdd": "canton"}

# type → (motif du nom de fichier, couche, libellé, colonne nom, colonne année, détails)
DATASETS = [
    dict(type="grande", couche="exploitation", pattern="Grandes exploitations", label="Grandes exploitations",
         nom="exploitation_nom", annee="exploitation_annee", detail=[]),
    dict(type="petite", couche="exploitation", pattern="Petites exploitations", label="Petites exploitations",
         nom="cooperative_nom", annee=None, detail=[("cooperative_type", parse_set)]),
    dict(type="plantation", couche="exploitation", pattern="Plantations", label="Plantations",
         nom="exploitation_nom", annee="exploitation_annee", detail=[("terrain", clean_text)]),
    dict(type="zaap", couche="zaap", pattern="ZAAP", label="ZAAP / ZAPB (champs individuels)",
         nom="cooperative_nom", annee=None, detail=[("cooperative_type", parse_set)]),
    dict(type="cooperative", couche="cooperative", pattern="Coopératives", label="Coopératives agricoles",
         nom="cooperative_nom", annee=None, detail=[("cooperative_statut", parse_set), ("cooperative_type", clean_text)]),
    dict(type="marche", couche="marche", pattern="Marchés", label="Marchés",
         nom="marche_nom", annee=None, detail=[("jour", parse_days)]),
    dict(type="pepiniere", couche="pepiniere", pattern="Pépinières", label="Pépinières agricoles",
         nom="etab_nom", annee="etab_creation_date", detail=[("terrain", clean_text)]),
    # Jeu facultatif : sans lui, les indicateurs d'intrants affichent « Donnée indisponible ».
    dict(type="intrant", couche="intrant", pattern="intrant", label="Magasins d'intrants",
         nom="etab_nom", annee=None, detail=[("organisme", clean_text), ("ouverture_jour", parse_days)], optional=True),
]

POLYGON_TYPES = {"petite", "zaap", "marche"}


@dataclass
class Data:
    entities: pd.DataFrame
    prefectures: pd.DataFrame
    cantons: pd.DataFrame
    geojson_prefectures: dict
    geojson_regions: dict
    quality: pd.DataFrame
    completeness: pd.DataFrame
    meta: dict

    @property
    def has_intrants(self) -> bool:
        return bool((self.entities["type"] == "intrant").any())


def find_raw(pattern: str) -> Path | None:
    # Comparaison sans accents ni casse : les noms accentués varient selon le système (NFC/NFD).
    matches = sorted(p for p in RAW_DIR.glob("*.csv") if norm_key(pattern) in norm_key(p.name))
    return matches[0] if matches else None


def _export_date(paths: list[Path]) -> str | None:
    dates = []
    for p in paths:
        m = re.search(r"(\d{2})-(\d{2})-(\d{4})", p.name)
        if m:
            dates.append(date(int(m[3]), int(m[2]), int(m[1])))
    return max(dates).isoformat() if dates else None


def _load_dataset(spec: dict, path: Path):
    """Nettoie un jeu brut. Retourne (entités, exclusions, complétude, synthèse qualité)."""
    raw = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    attrs = [c for c in raw.columns if c not in ("FID", "geometry")]
    clean = raw[attrs].apply(lambda s: s.map(clean_text))

    geoms = geo.parse_wkt(raw["geometry"])
    no_coord = geoms.isna() | geoms.is_empty
    invalid = ~no_coord & ~geoms.is_valid
    geoms = geoms.make_valid()
    points = geoms.representative_point()

    name_col = spec["nom"] if spec["nom"] in attrs else None
    out = pd.DataFrame({new: clean[old] for old, new in ADMIN_COLS.items()})
    out["localite"] = raw["nom_localite"].map(clean_place) if "nom_localite" in raw else None
    out["nom"] = clean[name_col] if name_col else None
    out["annee"] = raw[spec["annee"]].map(parse_year).astype("Int64") if spec["annee"] else pd.array([pd.NA] * len(raw), dtype="Int64")
    details = [raw[col].map(fn) for col, fn in spec["detail"] if col in raw]
    out["detail"] = (pd.concat(details, axis=1).apply(lambda r: " — ".join(v for v in r if v) or None, axis=1)
                     if details else None)
    out["surface_ha"] = area_ha_or_na(geoms, spec["type"])
    out["lon"], out["lat"] = points.x.round(6), points.y.round(6)
    out["geom_corrigee"] = invalid.to_numpy()
    out.insert(0, "type", spec["type"])
    out.insert(0, "couche", spec["couche"])
    out.insert(0, "fid_source", raw["FID"])

    dup = raw.drop(columns="FID").duplicated(keep="first")
    no_admin = out[["region", "prefecture", "canton"]].isna().any(axis=1)
    reason = pd.Series("", index=raw.index)
    reason[dup] = "Doublon exact (attributs et géométrie identiques)"
    reason[no_coord.to_numpy()] = "Géométrie absente ou illisible"
    reason[no_admin] = "Région, préfecture ou canton manquant"
    excluded = out[reason != ""].assign(motif=reason[reason != ""])
    kept = out[reason == ""].copy()

    completeness = pd.DataFrame({
        "jeu": spec["label"], "variable": attrs + ["geometry"],
        "renseignes": [int(clean[c].notna().sum()) for c in attrs] + [int((~no_coord).sum())],
        "total": len(raw),
    })
    if spec["annee"]:
        valid = int(out["annee"].notna().sum())
        completeness.loc[len(completeness)] = [spec["label"], f"{spec['annee']} (année plausible)", valid, len(raw)]
    completeness["taux"] = (completeness["renseignes"] / completeness["total"]).round(4)

    summary = dict(jeu=spec["label"], type=spec["type"], fichier=path.name, lignes_brutes=len(raw),
                   sans_coordonnees=int(no_coord.sum()), geometries_corrigees=int(invalid.sum()),
                   doublons_exclus=int(dup.sum()), lignes_retenues=len(kept),
                   geometrie="Polygone" if spec["type"] in POLYGON_TYPES else "Point")
    return kept, excluded, completeness, summary


def area_ha_or_na(geoms: gpd.GeoSeries, type_: str):
    if type_ not in POLYGON_TYPES:
        return pd.NA
    return geo.area_ha(geoms).round(4).to_numpy()


def build_processed(verbose: bool = True) -> None:
    """Reconstruit data/processed/ à partir de data/raw/."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    warnings.simplefilter("ignore", FutureWarning)  # concat de colonnes entièrement vides
    frames, excluded, completeness, summaries, paths = [], [], [], [], []
    for spec in DATASETS:
        path = find_raw(spec["pattern"])
        if path is None:
            if not spec.get("optional"):
                raise FileNotFoundError(f"Fichier brut introuvable pour « {spec['label']} » dans {RAW_DIR}")
            summaries.append(dict(jeu=spec["label"], type=spec["type"], fichier=None, lignes_brutes=0,
                                  sans_coordonnees=0, geometries_corrigees=0, doublons_exclus=0,
                                  lignes_retenues=0, geometrie=None))
            continue
        kept, excl, comp, summ = _load_dataset(spec, path)
        frames.append(kept); excluded.append(excl); completeness.append(comp); summaries.append(summ); paths.append(path)
        if verbose:
            print(f"  {spec['label']:<36} {summ['lignes_brutes']:>6} lignes → {summ['lignes_retenues']:>6} retenues")

    ent = pd.concat(frames, ignore_index=True)
    ent.insert(0, "id", [f"{t[:3].upper()}-{i:05d}" for i, t in enumerate(ent["type"], 1)])
    ent["canton_id"] = ent["prefecture"] + "|" + ent["canton"]

    prefs = geo.load_prefectures(BOUNDARY_DIR, sorted(ent["prefecture"].unique()))
    pts = gpd.GeoDataFrame(ent[["prefecture"]], geometry=gpd.points_from_xy(ent["lon"], ent["lat"]), crs=geo.WGS84)
    ent["dans_prefecture_declaree"] = geo.within_declared(pts, prefs).to_numpy()
    for s in summaries:
        sub = ent[ent["type"] == s["type"]]
        s["hors_prefecture_declaree"] = int((~sub["dans_prefecture_declaree"]).sum())

    missing = sorted(set(ent["prefecture"]) - set(prefs["prefecture"]))
    if missing:
        raise ValueError(f"Préfectures sans polygone : {missing}")

    simple = geo.simplify_coverage(prefs)
    regions = simple.dissolve(by="region", aggfunc={"superficie_km2": "sum"}).reset_index()
    (PROCESSED_DIR / "prefectures.geojson").write_text(json.dumps(geo.to_geojson(simple, "prefecture")), encoding="utf-8")
    (PROCESSED_DIR / "regions.geojson").write_text(json.dumps(geo.to_geojson(regions, "region")), encoding="utf-8")

    pref_tab = prefs.drop(columns="geometry").copy()
    b = prefs.geometry.bounds.round(4)
    pref_tab[["lon_min", "lat_min", "lon_max", "lat_max"]] = b.to_numpy()
    pref_tab["superficie_km2"] = pref_tab["superficie_km2"].round(1)

    cantons = (ent.groupby(["region", "prefecture", "canton", "canton_id"], as_index=False)
               .agg(lon=("lon", "median"), lat=("lat", "median"), enregistrements=("id", "size")))

    csv = dict(index=False, encoding="utf-8-sig")
    ent.to_csv(PROCESSED_DIR / "entites.csv", **csv)
    pref_tab.to_csv(PROCESSED_DIR / "prefectures.csv", **csv)
    cantons.to_csv(PROCESSED_DIR / "cantons.csv", **csv)
    pd.concat(excluded, ignore_index=True).to_csv(PROCESSED_DIR / "exclusions.csv", **csv)
    pd.concat(completeness, ignore_index=True).to_csv(PROCESSED_DIR / "qualite_completude.csv", **csv)
    pd.DataFrame(summaries).to_csv(PROCESSED_DIR / "qualite_jeux.csv", **csv)
    pd.DataFrame(DATA_DICTIONARY, columns=["table", "variable", "type", "nature", "description"]).to_csv(
        PROCESSED_DIR / "dictionnaire_donnees.csv", **csv)

    wb = RAW_DIR / "agriculture-and-rural-development-tgo.csv"
    if wb.exists():
        nat = pd.read_csv(wb, skiprows=[1])
        nat.columns = ["pays", "iso3", "annee", "indicateur", "code", "valeur"]
        nat.to_csv(PROCESSED_DIR / "indicateurs_nationaux.csv", **csv)

    meta = dict(date_export=_export_date(paths), date_traitement=date.today().isoformat(),
                limites="OCHA COD-AB Togo v02 (HDX), valides au 07/01/2021",
                n_entites=len(ent), n_prefectures=len(pref_tab), n_cantons=len(cantons))
    (PROCESSED_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if verbose:
        print(f"  {len(ent)} entités, {len(pref_tab)} préfectures, {len(cantons)} cantons → {PROCESSED_DIR}")


def load(rebuild: bool = False) -> Data:
    """Charge les données traitées, en les construisant si nécessaire."""
    if rebuild or not (PROCESSED_DIR / "meta.json").exists():
        print("Préparation des données…")
        build_processed()
    read = lambda name: pd.read_csv(PROCESSED_DIR / name, encoding="utf-8-sig")
    ent = read("entites.csv")
    ent["annee"] = ent["annee"].astype("Int64")
    for col in ("couche", "type", "region", "prefecture"):
        ent[col] = ent[col].astype("category")
    return Data(
        entities=ent,
        prefectures=read("prefectures.csv"),
        cantons=read("cantons.csv"),
        geojson_prefectures=json.loads((PROCESSED_DIR / "prefectures.geojson").read_text(encoding="utf-8")),
        geojson_regions=json.loads((PROCESSED_DIR / "regions.geojson").read_text(encoding="utf-8")),
        quality=read("qualite_jeux.csv"),
        completeness=read("qualite_completude.csv"),
        meta=json.loads((PROCESSED_DIR / "meta.json").read_text(encoding="utf-8")),
    )


DATA_DICTIONARY = [
    ("entites.csv", "id", "texte", "calculée", "Identifiant unique attribué au nettoyage (préfixe = type)."),
    ("entites.csv", "fid_source", "texte", "observée", "Identifiant FID du fichier source."),
    ("entites.csv", "couche", "catégorie", "calculée", "exploitation, zaap, cooperative, marche, pepiniere, intrant."),
    ("entites.csv", "type", "catégorie", "calculée", "grande, petite, plantation, zaap, cooperative, marche, pepiniere, intrant."),
    ("entites.csv", "region", "texte", "observée", "Région déclarée (region_nom_bdd)."),
    ("entites.csv", "prefecture", "texte", "observée", "Préfecture déclarée (prefecture_nom_bdd)."),
    ("entites.csv", "commune", "texte", "observée", "Commune déclarée (commune_nom_bdd)."),
    ("entites.csv", "canton", "texte", "observée", "Canton déclaré (canton_nom_bdd)."),
    ("entites.csv", "canton_id", "texte", "calculée", "Clé « préfecture|canton » (lève l'homonymie du canton Loko)."),
    ("entites.csv", "localite", "texte", "observée", "Localité (nom_localite), casse harmonisée."),
    ("entites.csv", "nom", "texte", "observée", "Nom de l'entité ; pour petites exploitations et ZAAP : coopérative de rattachement."),
    ("entites.csv", "annee", "entier", "observée", "Année de création déclarée (grandes exploitations, plantations, pépinières). Hors 1900-2026 → manquante."),
    ("entites.csv", "detail", "texte", "observée", "Attributs descriptifs normalisés (statut, type, foncier, jours de marché)."),
    ("entites.csv", "surface_ha", "décimal", "calculée", "Surface du polygone en hectares (UTM 31N). Vide pour les points."),
    ("entites.csv", "lon / lat", "décimal", "calculée", "Point représentatif de la géométrie (WGS84)."),
    ("entites.csv", "geom_corrigee", "booléen", "calculée", "Géométrie source invalide, réparée (make_valid)."),
    ("entites.csv", "dans_prefecture_declaree", "booléen", "calculée", "Le point tombe dans le polygone OCHA de la préfecture déclarée."),
    ("prefectures.csv", "prefecture / region", "texte", "observée", "39 préfectures, orthographe des données."),
    ("prefectures.csv", "superficie_km2", "décimal", "observée", "Superficie OCHA COD-AB (Golfe = Golfe + Lomé Commune)."),
    ("cantons.csv", "canton_id / canton", "texte", "observée", "Cantons présents dans au moins un jeu de données."),
    ("cantons.csv", "lon / lat", "décimal", "calculée", "Position médiane des enregistrements du canton (pas un centroïde officiel)."),
    ("exclusions.csv", "motif", "texte", "calculée", "Raison de l'exclusion (doublon exact, géométrie absente, niveau administratif manquant)."),
    ("qualite_completude.csv", "taux", "décimal", "calculée", "Part des valeurs renseignées par variable (« Nsp », « Néant », vide = manquant)."),
    ("qualite_jeux.csv", "*", "entier", "calculée", "Par jeu : lignes brutes, retenues, doublons, géométries corrigées, incohérences spatiales."),
    ("indicateurs_nationaux.csv", "*", "décimal", "observée", "Indicateurs Banque mondiale (HDX), niveau national uniquement — non utilisés dans les cartes."),
]


if __name__ == "__main__":
    build_processed()
