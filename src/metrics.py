"""Filtres, agrégations et indicateurs. Aucune valeur n'est estimée : ce qui manque reste NaN."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

from .data_loader import Data

EXPL_TYPES = {"grande": "Grandes exploitations", "petite": "Petites exploitations", "plantation": "Plantations"}
INFRA_TYPES = {"marche": "Marchés", "intrant": "Magasins d'intrants", "pepiniere": "Pépinières"}
YEAR_TYPES = ("grande", "plantation", "pepiniere")
ALL_TYPES = ["grande", "petite", "plantation", "zaap", "cooperative", "marche", "pepiniere", "intrant"]

QUADRANTS = {
    "faible_faible": "Exploitations faibles · coopératives faibles",
    "fort_faible": "Exploitations fortes · coopératives faibles",
    "faible_fort": "Exploitations faibles · coopératives fortes",
    "fort_fort": "Exploitations fortes · coopératives fortes",
}
EQUIP_LEVELS = {0: "Aucun service", 1: "Un service", 2: "Plusieurs services"}
MIN_N_CORRELATION = 5


@dataclass
class Filters:
    regions: list = field(default_factory=list)
    prefectures: list = field(default_factory=list)
    cantons: list = field(default_factory=list)  # canton_id
    expl: list = field(default_factory=list)
    infra: list = field(default_factory=list)
    years: list | None = None

    @classmethod
    def from_inputs(cls, regions, prefectures, cantons, expl, infra, years):
        return cls(regions or [], prefectures or [], cantons or [], expl or [], infra or [], years)

    @property
    def has_geo(self) -> bool:
        return bool(self.regions or self.prefectures or self.cantons)


def year_bounds(data: Data) -> tuple[int, int]:
    years = data.entities["annee"].dropna()
    return int(years.min()), int(years.max())


def _year_active(data: Data, f: Filters) -> bool:
    return bool(f.years) and tuple(f.years) != year_bounds(data)


def filter_entities(data: Data, f: Filters, geo: bool = True) -> pd.DataFrame:
    """Applique les filtres. `geo=False` ignore région/préfecture/canton (référence nationale)."""
    ent = data.entities
    m = np.ones(len(ent), dtype=bool)
    if geo:
        if f.regions:
            m &= ent["region"].isin(f.regions).to_numpy()
        if f.prefectures:
            m &= ent["prefecture"].isin(f.prefectures).to_numpy()
        if f.cantons:
            m &= ent["canton_id"].isin(f.cantons).to_numpy()
    if f.expl:
        m &= ~((ent["couche"] == "exploitation") & ~ent["type"].isin(f.expl)).to_numpy()
    if f.infra:
        m &= ~(ent["type"].isin(list(INFRA_TYPES)) & ~ent["type"].isin(f.infra)).to_numpy()
    if _year_active(data, f):
        # L'année ne s'applique qu'aux jeux qui la portent ; les autres ne sont pas filtrés.
        in_range = ent["annee"].between(f.years[0], f.years[1]).fillna(False)
        m &= ~(ent["type"].isin(YEAR_TYPES) & ~in_range).to_numpy()
    return ent[m]


def scope_prefectures(data: Data, f: Filters) -> pd.DataFrame:
    p = data.prefectures
    if f.cantons:
        prefs = data.cantons.loc[data.cantons["canton_id"].isin(f.cantons), "prefecture"].unique()
        p = p[p["prefecture"].isin(prefs)]
    if f.prefectures:
        p = p[p["prefecture"].isin(f.prefectures)]
    if f.regions:
        p = p[p["region"].isin(f.regions)]
    return p


def scope_cantons(data: Data, f: Filters) -> pd.DataFrame:
    c = data.cantons
    if f.regions:
        c = c[c["region"].isin(f.regions)]
    if f.prefectures:
        c = c[c["prefecture"].isin(f.prefectures)]
    if f.cantons:
        c = c[c["canton_id"].isin(f.cantons)]
    return c


def _counts(ent: pd.DataFrame, by: str) -> pd.DataFrame:
    """Effectifs par type et superficie ZAAP, par unité `by`."""
    counts = pd.crosstab(ent[by].astype(str), ent["type"].astype(str)).reindex(columns=ALL_TYPES, fill_value=0)
    counts.columns = [f"n_{c}" for c in counts.columns]
    counts["n_expl"] = counts[["n_grande", "n_petite", "n_plantation"]].sum(axis=1)
    zaap = ent[ent["type"] == "zaap"]
    counts["zaap_ha"] = zaap.groupby(zaap[by].astype(str))["surface_ha"].sum()
    counts["zaap_ha"] = counts["zaap_ha"].fillna(0.0)
    return counts


def _add_densities(df: pd.DataFrame) -> pd.DataFrame:
    """Densités pour 100 km² (NaN si la superficie est inconnue)."""
    per = 100 / df["superficie_km2"]
    df["dens_expl"] = df["n_expl"] * per
    df["dens_coop"] = df["n_cooperative"] * per
    df["dens_marche"] = df["n_marche"] * per
    df["dens_pepiniere"] = df["n_pepiniere"] * per
    df["dens_intrant"] = df["n_intrant"] * per
    df["dens_zaap"] = df["zaap_ha"] * per
    return df


def prefecture_table(data: Data, f: Filters) -> pd.DataFrame:
    """Indicateurs des 39 préfectures (filtres de type/année appliqués, géographie nationale).

    `in_scope` marque les préfectures retenues par les filtres géographiques ; les quadrants
    sont définis par rapport aux médianes nationales, donc stables quel que soit le zoom.
    """
    ent = filter_entities(data, f, geo=False)
    df = data.prefectures.merge(_counts(ent, "prefecture"), left_on="prefecture", right_index=True, how="left")
    count_cols = [c for c in df.columns if c.startswith("n_")] + ["zaap_ha"]
    df[count_cols] = df[count_cols].fillna(0)
    df = _add_densities(df)
    df["intrants_p1000"] = df["n_intrant"] / df["n_expl"].replace(0, np.nan) * 1000
    med_e, med_c = df["dens_expl"].median(), df["dens_coop"].median()
    hi_e, hi_c = df["dens_expl"] > med_e, df["dens_coop"] > med_c
    df["quadrant"] = np.select([hi_e & hi_c, hi_e & ~hi_c, ~hi_e & hi_c], ["fort_fort", "fort_faible", "faible_fort"],
                               "faible_faible")
    df["in_scope"] = df["prefecture"].isin(scope_prefectures(data, f)["prefecture"])
    df.attrs.update(med_expl=med_e, med_coop=med_c)
    return df


def region_table(pref: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in pref.columns if c.startswith("n_")] + ["zaap_ha", "superficie_km2"]
    df = pref.groupby("region", as_index=False)[cols].sum()
    df["in_scope"] = df["region"].isin(pref.loc[pref["in_scope"], "region"])
    return _add_densities(df)


def equipment_types(data: Data, f: Filters) -> list[str]:
    """Types de service observables et retenus par le filtre d'infrastructure."""
    available = [t for t in INFRA_TYPES if t != "intrant" or data.has_intrants]
    return [t for t in available if not f.infra or t in f.infra]


def canton_table(data: Data, f: Filters) -> pd.DataFrame:
    """Indicateurs par canton du périmètre, avec niveau d'équipement (0, 1, 2 = plusieurs)."""
    ent = filter_entities(data, f)
    df = scope_cantons(data, f).merge(_counts(ent, "canton_id"), left_on="canton_id", right_index=True, how="left")
    count_cols = [c for c in df.columns if c.startswith("n_")] + ["zaap_ha"]
    df[count_cols] = df[count_cols].fillna(0)
    services = equipment_types(data, f)
    df["n_services"] = sum((df[f"n_{t}"] > 0).astype(int) for t in services) if services else 0
    df["niveau"] = df["n_services"].clip(upper=2)
    return df


def kpis(data: Data, f: Filters) -> dict:
    ent = filter_entities(data, f)
    types = ent["type"].astype(str)
    n_expl = int(ent["couche"].eq("exploitation").sum())
    cantons = canton_table(data, f)
    # La superficie n'existe qu'au niveau préfecture : pas de densité pour une sélection de cantons.
    km2 = np.nan if f.cantons else scope_prefectures(data, f)["superficie_km2"].sum()
    zaap = ent[types == "zaap"]
    return dict(
        n_expl=n_expl,
        dens_expl=n_expl / km2 * 100 if km2 and not np.isnan(km2) else np.nan,
        km2=km2,
        zaap_ha=float(zaap["surface_ha"].sum()),
        zaap_n=len(zaap),
        n_coop=int((types == "cooperative").sum()),
        cantons_equipes=int((cantons["niveau"] > 0).sum()),
        cantons_total=len(cantons),
        by_type={t: int((types == t).sum()) for t in ALL_TYPES},
    )


def spearman(df: pd.DataFrame, x: str = "dens_expl", y: str = "dens_coop") -> dict:
    """Corrélation de rang ; `rho` vaut None si l'effectif est insuffisant ou une série constante."""
    d = df[[x, y]].dropna()
    n = len(d)
    if n < MIN_N_CORRELATION or d[x].nunique() < 2 or d[y].nunique() < 2:
        return dict(rho=None, p=None, n=n)
    rho, p = stats.spearmanr(d[x], d[y])
    return dict(rho=float(rho), p=float(p), n=n)


def priorities(data: Data, f: Filters, pref: pd.DataFrame, cantons: pd.DataFrame, top: int = 5) -> dict:
    """Zones prioritaires. Une liste vaut None lorsque la donnée nécessaire est indisponible."""
    scope = pref[pref["in_scope"]]
    coop_gap = scope[scope["quadrant"] == "fort_faible"].nlargest(top, "dens_expl")

    intrant_gap = None
    if data.has_intrants:
        # Forte production = densité > médiane ; faible accès = magasins pour 1 000 exploitations ≤ médiane.
        ratios = pref["intrants_p1000"].dropna()
        low = scope["intrants_p1000"].fillna(0) <= (ratios.median() if len(ratios) else 0)
        intrant_gap = scope[(scope["dens_expl"] > pref.attrs["med_expl"]) & low].nsmallest(top, "intrants_p1000")

    all_cantons = canton_table(data, Filters(expl=f.expl, infra=f.infra, years=f.years))
    with_zaap = all_cantons.loc[all_cantons["zaap_ha"] > 0, "zaap_ha"]
    zaap_gap = cantons.iloc[0:0]
    threshold = np.nan
    if len(with_zaap):
        threshold = with_zaap.median()
        zaap_gap = cantons[(cantons["zaap_ha"] >= threshold) & (cantons["niveau"] <= 1)].nlargest(top, "zaap_ha")
    return dict(coop_gap=coop_gap, intrant_gap=intrant_gap, zaap_gap=zaap_gap, zaap_threshold=threshold)


def _strength(rho: float) -> str:
    a = abs(rho)
    return "très faible" if a < 0.2 else "faible" if a < 0.4 else "modérée" if a < 0.6 else "forte" if a < 0.8 else "très forte"


def conclusion(data: Data, pref: pd.DataFrame, corr: dict, prio: dict) -> list[str]:
    """Deux ou trois phrases, strictement fondées sur les données filtrées."""
    from .theme import fr

    out = []
    if corr["rho"] is None:
        out.append(f"Seulement {corr['n']} préfecture(s) dans la sélection : effectif insuffisant pour mesurer une "
                   "association entre coopératives et exploitations.")
    else:
        sign = "positive" if corr["rho"] > 0 else "négative"
        signif = "statistiquement significative" if corr["p"] < 0.05 else "non significative au seuil de 5 %"
        out.append(f"Sur {corr['n']} préfectures, l'association entre densité d'exploitations et densité de "
                   f"coopératives est {sign} et {_strength(corr['rho'])} (ρ de Spearman = {fr(corr['rho'], 2)}, {signif}).")
    gap = prio["coop_gap"]
    n_gap = int((pref["in_scope"] & (pref["quadrant"] == "fort_faible")).sum())
    if n_gap:
        names = ", ".join(gap["prefecture"].head(3))
        out.append(f"{n_gap} préfecture(s) combinent une densité d'exploitations supérieure à la médiane nationale "
                   f"et une densité de coopératives inférieure, dont {names}.")
    else:
        out.append("Aucune préfecture de la sélection ne combine forte densité d'exploitations et faible densité de coopératives.")
    caveat = "Cette association ne démontre aucun lien de cause à effet"
    if not data.has_intrants:
        caveat += " ; l'accès aux intrants ne peut pas être évalué (donnée indisponible)"
    out.append(caveat + ".")
    return out
