"""Construction des cartes et graphiques Plotly."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import geo, metrics as mx, theme as th
from .data_loader import Data
from .theme import fr

# couche → (libellé, colonne effectif, colonne densité, unité effectif, unité densité, types de points)
LAYERS = {
    "exploitations": ("Exploitations", "n_expl", "dens_expl", "exploitations", "expl. / 100 km²", list(mx.EXPL_TYPES)),
    "zaap": ("ZAAP", "zaap_ha", "dens_zaap", "ha", "ha / 100 km²", ["zaap"]),
    "cooperatives": ("Coopératives", "n_cooperative", "dens_coop", "coopératives", "coop. / 100 km²", ["cooperative"]),
    "marches": ("Marchés", "n_marche", "dens_marche", "marchés", "marchés / 100 km²", ["marche"]),
    "intrants": ("Intrants", "n_intrant", "dens_intrant", "magasins", "magasins / 100 km²", ["intrant"]),
    "pepinieres": ("Pépinières", "n_pepiniere", "dens_pepiniere", "pépinières", "pép. / 100 km²", ["pepiniere"]),
    "equipement": ("Niveau d'équipement", None, None, None, None, []),
}
TYPE_LABELS = {**mx.EXPL_TYPES, **mx.INFRA_TYPES, "zaap": "Champ ZAAP / ZAPB", "cooperative": "Coopérative"}
TYPE_SINGULAR = {"grande": "Grande exploitation", "petite": "Petite exploitation", "plantation": "Plantation",
                 "zaap": "Champ ZAAP / ZAPB", "cooperative": "Coopérative", "marche": "Marché",
                 "pepiniere": "Pépinière", "intrant": "Magasin d'intrants"}


def layer_unavailable(data: Data, layer: str) -> bool:
    return layer == "intrants" and not data.has_intrants


# ── Cartes ────────────────────────────────────────────────────────────────────────────────

def _scope_bounds(data: Data, f: mx.Filters):
    if f.cantons:
        c = mx.scope_cantons(data, f)
        if len(c):
            pad = 0.06
            return c["lon"].min() - pad, c["lat"].min() - pad, c["lon"].max() + pad, c["lat"].max() + pad
    p = mx.scope_prefectures(data, f)
    if not f.has_geo or p.empty:
        return geo.TOGO_BOUNDS
    return p["lon_min"].min(), p["lat_min"].min(), p["lon_max"].max(), p["lat_max"].max()


def _outline_layer(gj: dict, keys) -> list:
    """Contour foncé autour des zones sélectionnées."""
    keys = set(keys)
    features = [ft for ft in gj["features"] if ft["id"] in keys]
    if not features:
        return []
    return [dict(sourcetype="geojson", source={"type": "FeatureCollection", "features": features},
                 type="line", color=th.OUTLINE, line=dict(width=2.6))]


def _map_layout(data: Data, f: mx.Filters, uirevision, basemap: bool, layers=None, **extra) -> dict:
    view = geo.map_view(_scope_bounds(data, f))
    return th.base_layout(
        margin=dict(l=0, r=0, t=0, b=0), uirevision=uirevision,
        map=dict(style="carto-positron" if basemap else "white-bg", layers=layers or [], **view),
        **extra,
    )


def _unit_frame(data: Data, f: mx.Filters, level: str):
    pref = mx.prefecture_table(data, f)
    if level == "region":
        return mx.region_table(pref), "region", data.geojson_regions
    return pref, "prefecture", data.geojson_prefectures


def _unit_hover(df: pd.DataFrame, key: str) -> list[str]:
    rows = []
    for r in df.itertuples():
        head = f"<b>{getattr(r, key)}</b>" + (f"  ·  {r.region}" if key == "prefecture" else "")
        rows.append(
            f"{head}<br>Exploitations : {fr(r.n_expl)}  ({fr(r.dens_expl, 1)} / 100 km²)"
            f"<br>Coopératives : {fr(r.n_cooperative)}  ·  ZAAP : {fr(r.zaap_ha, 0)} ha"
            f"<br>Marchés : {fr(r.n_marche)}  ·  Pépinières : {fr(r.n_pepiniere)}"
            f"<br>Superficie : {fr(r.superficie_km2)} km²"
        )
    return rows


def _choropleth(df, key, gj, z, colorscale, f, title=None, showscale=True, **kw) -> go.Choroplethmap:
    dim = f.has_geo and not df["in_scope"].all()
    return go.Choroplethmap(
        geojson=gj, locations=df[key], z=z, featureidkey="id", colorscale=colorscale, showscale=showscale,
        marker=dict(line=dict(color=th.SURFACE, width=1), opacity=np.where(df["in_scope"], 1.0, 0.28) if dim else 1.0),
        text=_unit_hover(df, key), hovertemplate="%{text}<extra></extra>",
        customdata=[[key, k] for k in df[key]],
        colorbar=dict(title=dict(text=title, font=dict(size=11)), thickness=8, len=0.42, x=0.99, xanchor="right",
                      y=0.03, yanchor="bottom", outlinewidth=0, tickfont=dict(size=10), bgcolor="rgba(255,255,255,0.85)"),
        **kw,
    )


def _points_trace(ent: pd.DataFrame, types: list[str], size: float = 5, opacity: float = 0.6) -> go.Scattermap | None:
    pts = ent[ent["type"].isin(types)]
    if pts.empty:
        return None
    label = pts["type"].astype(str).map(TYPE_SINGULAR)
    name = pts["nom"].fillna(label)
    text = ("<b>" + name + "</b><br>" + label + "<br>" + pts["canton"].astype(str) + ", " + pts["prefecture"].astype(str))
    surf = pts["surface_ha"]
    if surf.notna().any() and types == ["zaap"]:
        text = text + "<br>" + surf.map(lambda v: f"{fr(v, 2)} ha")
    return go.Scattermap(
        lat=pts["lat"], lon=pts["lon"], mode="markers", text=text, hovertemplate="%{text}<extra></extra>",
        marker=dict(size=size, color=th.POINT, opacity=opacity),
        customdata=[["canton", c] for c in pts["canton_id"]], showlegend=False,
    )


def _selected_outline(data: Data, f: mx.Filters, level: str, gj: dict) -> list:
    if not f.has_geo:
        return []
    scope = mx.scope_prefectures(data, f)
    return _outline_layer(gj, scope["region"] if level == "region" else scope["prefecture"])


def map_figure(data: Data, f: mx.Filters, layer: str, level: str, measure: str, points: bool,
               basemap: bool, uirevision) -> go.Figure:
    """Carte principale : choroplèthe (région ou préfecture) et points localisés."""
    if layer_unavailable(data, layer):
        return th.empty_figure("Magasins d'intrants — donnée indisponible<br>"
                               "<span style='font-size:11px'>Aucun jeu de données source n'a été fourni.</span>")
    if layer == "equipement":
        return equipment_map(data, f, basemap, uirevision)

    label, col_n, col_d, unit_n, unit_d, point_types = LAYERS[layer]
    df, key, gj = _unit_frame(data, f, level)
    col, unit = (col_d, unit_d) if measure == "densite" else (col_n, unit_n)
    ent = mx.filter_entities(data, f)
    trace_pts = _points_trace(ent, point_types) if points else None

    # L'échelle sature au 90e centile : quelques préfectures très denses écraseraient sinon toutes les autres.
    zmax, q90 = float(df[col].max()), float(df[col].quantile(0.9))
    capped = len(df) > 10 and 0 < q90 < zmax
    zmax = q90 if capped else max(zmax, 1e-9)
    fig = go.Figure(_choropleth(df, key, gj, df[col], th.SEQUENTIAL_LIGHT if trace_pts else th.SEQUENTIAL, f,
                                title=unit, zmin=0, zmax=zmax))
    dec = 1 if zmax < 20 else 0
    fig.data[0].colorbar.update(tickvals=[0, zmax / 2, zmax],
                                ticktext=["0", fr(zmax / 2, dec), ("≥ " if capped else "") + fr(zmax, dec)])
    if trace_pts:
        fig.add_trace(trace_pts)
    fig.update_layout(_map_layout(data, f, uirevision, basemap, layers=_selected_outline(data, f, level, gj)))
    return fig


def equipment_map(data: Data, f: mx.Filters, basemap: bool, uirevision) -> go.Figure:
    """Cantons colorés selon le nombre de types de service présents."""
    pref = mx.prefecture_table(data, f)
    gj = data.geojson_prefectures
    flat = [[0, "#EEF3F0"], [1, "#EEF3F0"]]
    fig = go.Figure(_choropleth(pref, "prefecture", gj, np.zeros(len(pref)), flat, f, showscale=False,
                                zmin=0, zmax=1))
    fig.data[0].marker.line.color = "#C9C9C7"
    cantons = mx.canton_table(data, f)
    # Tri décroissant : les cantons sans service sont tracés en dernier, donc au-dessus.
    cantons = cantons.sort_values("niveau", ascending=False)
    if len(cantons):
        text = [f"<b>{r.canton}</b>  ·  {r.prefecture}<br>{mx.EQUIP_LEVELS[r.niveau]}"
                f"<br>Marchés : {fr(r.n_marche)}  ·  Intrants : {fr(r.n_intrant)}  ·  Pépinières : {fr(r.n_pepiniere)}"
                f"<br>Exploitations : {fr(r.n_expl)}" for r in cantons.itertuples()]
        fig.add_trace(go.Scattermap(
            lat=cantons["lat"], lon=cantons["lon"], mode="markers", showlegend=False,
            marker=dict(size=9, color=cantons["niveau"].map(th.EQUIP_COLORS).tolist(), opacity=0.92),
            text=text, hovertemplate="%{text}<extra></extra>", customdata=[["canton", c] for c in cantons["canton_id"]],
        ))
    fig.update_layout(_map_layout(data, f, uirevision, basemap, layers=_selected_outline(data, f, "prefecture", gj)))
    return fig


def quadrant_map(data: Data, pref: pd.DataFrame, f: mx.Filters, uirevision) -> go.Figure:
    order = list(mx.QUADRANTS)
    steps = []
    for i, q in enumerate(order):
        steps += [[i / 4, th.QUADRANT_COLORS[q]], [(i + 1) / 4, th.QUADRANT_COLORS[q]]]
    z = pref["quadrant"].map(order.index)
    trace = _choropleth(pref, "prefecture", data.geojson_prefectures, z, steps, f, showscale=False, zmin=-0.5, zmax=3.5)
    trace.text = [f"<b>{r.prefecture}</b>  ·  {r.region}<br>{mx.QUADRANTS[r.quadrant]}"
                  f"<br>Exploitations : {fr(r.dens_expl, 1)} / 100 km²<br>Coopératives : {fr(r.dens_coop, 1)} / 100 km²"
                  for r in pref.itertuples()]
    fig = go.Figure(trace)
    fig.update_layout(_map_layout(data, f, uirevision, False,
                                  layers=_selected_outline(data, f, "prefecture", data.geojson_prefectures)))
    return fig


# ── Graphiques ────────────────────────────────────────────────────────────────────────────

def _hbar_height(n: int, row: int = 26, base: int = 30) -> int:
    return max(70, n * row + base)


def ranking_figure(data: Data, f: mx.Filters, layer: str, level: str, measure: str, top: int = 12) -> go.Figure:
    """Classement des unités du périmètre pour la couche affichée."""
    if layer_unavailable(data, layer):
        return th.empty_figure(th.UNAVAILABLE, height=180), LAYERS[layer][0]
    if layer == "equipement":
        layer = "marches"
    label, col_n, col_d, unit_n, unit_d, _ = LAYERS[layer]
    if f.prefectures or f.cantons:
        # Sous une préfecture, le classement descend au canton (effectifs seuls : superficie inconnue).
        df, key, name, units, col, unit = mx.canton_table(data, f), "canton_id", "canton", "cantons", col_n, unit_n
        measure = "nombre"
    else:
        df, key, _ = _unit_frame(data, f, level)
        df, name, units = df[df["in_scope"]], key, "régions" if level == "region" else "préfectures"
        col, unit = (col_d, unit_d) if measure == "densite" else (col_n, unit_n)
    title = f"{label} — {units} ({unit})"
    df = df[df[col] > 0].nlargest(top, col).iloc[::-1]
    if df.empty:
        return th.empty_figure(height=180), title
    dec = 1 if measure == "densite" or layer == "zaap" else 0
    fig = go.Figure(go.Bar(
        x=df[col], y=df[key], orientation="h", width=0.62, marker=dict(color=th.FILL, cornerradius=3),
        text=[fr(v, dec) for v in df[col]], textposition="outside", textfont=dict(size=11, color=th.INK_2),
        cliponaxis=False,
        customdata=[["canton" if key == "canton_id" else key, k, n] for k, n in zip(df[key], df[name])],
        hovertemplate="<b>%{customdata[2]}</b><br>%{text} " + unit + "<extra></extra>",
    ))
    fig.update_layout(th.base_layout(height=_hbar_height(len(df)), margin=dict(l=8, r=48, t=4, b=4)))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(showgrid=False, tickfont=dict(size=12, color=th.INK), tickmode="array", tickvals=df[key],
                     ticktext=df[name])
    return fig, title


def type_figure(k: dict, f: mx.Filters) -> go.Figure:
    types = [t for t in mx.EXPL_TYPES if not f.expl or t in f.expl]
    values = [k["by_type"][t] for t in types]
    if not sum(values):
        return th.empty_figure(height=190)
    total = sum(values)
    fig = go.Figure(go.Bar(
        x=values, y=[mx.EXPL_TYPES[t] for t in types], orientation="h", width=0.5,
        marker=dict(color=[th.TYPE_COLORS[t] for t in types], cornerradius=3),
        text=[f"{fr(v)}  ·  {fr(v / total * 100, 1)} %" for v in values], textposition="outside",
        textfont=dict(size=12, color=th.INK), cliponaxis=False, hovertemplate="<b>%{y}</b><br>%{text}<extra></extra>",
    ))
    fig.update_layout(th.base_layout(height=190, margin=dict(l=8, r=120, t=4, b=4)))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(showgrid=False, autorange="reversed", tickfont=dict(size=12, color=th.INK))
    return fig


def production_ranking(data: Data, f: mx.Filters, measure: str, top: int = 40):
    """Barres empilées par type. Retourne (figure, niveau, note)."""
    by_canton = bool(f.prefectures or f.cantons)
    note = None
    if by_canton:
        df, key, label, click = mx.canton_table(data, f), "canton_id", "canton", "canton"
        if measure == "densite":
            measure, note = "nombre", "Densité indisponible au niveau canton (superficie inconnue) : effectifs affichés."
    else:
        df = mx.prefecture_table(data, f)
        df, key, label, click = df[df["in_scope"]], "prefecture", "prefecture", "prefecture"
    df = df[df["n_expl"] > 0].nlargest(top, "n_expl" if measure == "nombre" else "dens_expl").iloc[::-1]
    if df.empty:
        return th.empty_figure(), by_canton, note
    scale = 100 / df["superficie_km2"] if measure == "densite" else 1
    dec = 1 if measure == "densite" else 0
    unit = "/ 100 km²" if measure == "densite" else ""
    fig = go.Figure()
    for t in [t for t in ("petite", "plantation", "grande") if not f.expl or t in f.expl]:
        vals = df[f"n_{t}"] * scale
        fig.add_trace(go.Bar(
            x=vals, y=df[key], orientation="h", name=mx.EXPL_TYPES[t],
            marker=dict(color=th.TYPE_COLORS[t], line=dict(color=th.SURFACE, width=1)),
            customdata=[[click, k, lab, fr(v, dec)] for k, lab, v in zip(df[key], df[label], vals)],
            hovertemplate="<b>%{customdata[2]}</b><br>" + mx.EXPL_TYPES[t] + f" : %{{customdata[3]}} {unit}<extra></extra>",
        ))
    fig.update_layout(th.base_layout(barmode="stack", showlegend=True, height=_hbar_height(len(df), 22, 80),
                                     margin=dict(l=8, r=24, t=30, b=8), bargap=0.3))
    fig.update_xaxes(side="top", tickfont=dict(size=10, color=th.MUTED))
    fig.update_yaxes(showgrid=False, tickfont=dict(size=11, color=th.INK), tickmode="array", tickvals=df[key],
                     ticktext=df[label])
    return fig, by_canton, note


def timeline_figure(ent: pd.DataFrame, f: mx.Filters, start: int = 1960, step: int = 5) -> go.Figure:
    """Années de création déclarées, par période de 5 ans (grandes exploitations et plantations)."""
    d = ent[ent["type"].isin(["grande", "plantation"]) & ent["annee"].notna()]
    if d.empty:
        return th.empty_figure("Aucune année de création renseignée pour cette sélection", height=260)
    year = d["annee"].astype(int).clip(lower=start - step)
    period = (year - start) // step * step + start
    tab = pd.crosstab(period, d["type"].astype(str))
    fig = go.Figure()
    for t in ("plantation", "grande"):
        if t not in tab or (f.expl and t not in f.expl):
            continue
        labels = [f"Avant {start}" if p < start else f"{p}–{p + step - 1}" for p in tab.index]
        fig.add_trace(go.Bar(x=labels, y=tab[t], name=mx.EXPL_TYPES[t],
                             marker=dict(color=th.TYPE_COLORS[t], line=dict(color=th.SURFACE, width=1)),
                             hovertemplate="<b>%{x}</b><br>" + mx.EXPL_TYPES[t] + " : %{y}<extra></extra>"))
    fig.update_layout(th.base_layout(barmode="stack", showlegend=True, height=260, margin=dict(l=8, r=8, t=30, b=8),
                                     bargap=0.25))
    fig.update_xaxes(showgrid=False, tickfont=dict(size=10), tickangle=-40)
    fig.update_yaxes(tickfont=dict(size=10, color=th.MUTED))
    return fig


def coverage_figure(cantons: pd.DataFrame, f: mx.Filters) -> go.Figure:
    """Part des cantons disposant d'au moins un service, par région (ou préfecture si une seule région)."""
    if cantons.empty:
        return th.empty_figure(height=220)
    key = "prefecture" if cantons["region"].nunique() == 1 else "region"
    g = cantons.groupby(key).agg(total=("canton_id", "size"), eq=("niveau", lambda s: int((s > 0).sum())))
    g["taux"] = g["eq"] / g["total"] * 100
    g = g.sort_values("taux")
    fig = go.Figure(go.Bar(
        x=g["taux"], y=g.index, orientation="h", width=0.62, marker=dict(color=th.FILL, cornerradius=3),
        text=[f"{fr(t, 0)} %  ·  {e}/{n}" for t, e, n in zip(g["taux"], g["eq"], g["total"])],
        textposition="outside", textfont=dict(size=11, color=th.INK_2), cliponaxis=False,
        customdata=[[key, k] for k in g.index], hovertemplate="<b>%{y}</b><br>%{text} cantons équipés<extra></extra>",
    ))
    fig.update_layout(th.base_layout(height=_hbar_height(len(g)), margin=dict(l=8, r=96, t=4, b=4)))
    fig.update_xaxes(visible=False, range=[0, 100])
    fig.update_yaxes(showgrid=False, tickfont=dict(size=12, color=th.INK))
    return fig


def scatter_figure(pref: pd.DataFrame) -> go.Figure:
    """Densité de coopératives en fonction de la densité d'exploitations, par préfecture."""
    df = pref[pref["in_scope"]]
    if df.empty:
        return th.empty_figure(height=420)
    fig = go.Figure()
    med_x, med_y = pref.attrs["med_expl"], pref.attrs["med_coop"]
    fig.add_vline(x=med_x, line=dict(color=th.LINE, width=1.5, dash="dot"))
    fig.add_hline(y=med_y, line=dict(color=th.LINE, width=1.5, dash="dot"))
    if len(df) >= mx.MIN_N_CORRELATION and df["dens_expl"].nunique() > 1:
        slope, intercept = np.polyfit(df["dens_expl"], df["dens_coop"], 1)
        xs = np.array([df["dens_expl"].min(), df["dens_expl"].max()])
        fig.add_trace(go.Scatter(x=xs, y=slope * xs + intercept, mode="lines", hoverinfo="skip",
                                 line=dict(color=th.INK_2, width=1.5, dash="dash")))
    flagged = set(df[df["quadrant"] == "fort_faible"].nlargest(4, "dens_expl")["prefecture"])
    flagged |= {df.loc[df["dens_expl"].idxmax(), "prefecture"], df.loc[df["dens_coop"].idxmax(), "prefecture"]}
    fig.add_trace(go.Scatter(
        x=df["dens_expl"], y=df["dens_coop"], mode="markers+text",
        text=[p if p in flagged else "" for p in df["prefecture"]], textposition="top center",
        textfont=dict(size=10, color=th.INK_2),
        marker=dict(size=11, color=df["quadrant"].map(th.QUADRANT_COLORS), line=dict(color=th.SURFACE, width=1.5)),
        customdata=[["prefecture", p, mx.QUADRANTS[q], fr(e), fr(c)] for p, q, e, c in
                    zip(df["prefecture"], df["quadrant"], df["n_expl"], df["n_cooperative"])],
        hovertemplate="<b>%{customdata[1]}</b><br>%{customdata[2]}<br>Exploitations : %{x:.1f} / 100 km² (%{customdata[3]})"
                      "<br>Coopératives : %{y:.1f} / 100 km² (%{customdata[4]})<extra></extra>",
    ))
    fig.update_layout(th.base_layout(height=420, margin=dict(l=8, r=16, t=16, b=8)))
    fig.update_xaxes(title_text="Exploitations pour 100 km²", rangemode="tozero")
    fig.update_yaxes(title_text="Coopératives pour 100 km²", rangemode="tozero")
    return fig
