"""Callbacks Dash : filtres croisés, KPI, vues et exports."""
from __future__ import annotations

import time
from urllib.parse import parse_qs

import pandas as pd
from dash import Dash, Input, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

from . import figures as fg, layouts as lo, metrics as mx, theme as th
from .data_loader import Data
from .theme import fr

FILTER_IDS = ["f-region", "f-prefecture", "f-canton", "f-expl", "f-infra", "f-annee"]
FILTER_INPUTS = [Input(i, "value") for i in FILTER_IDS]
CLICKABLE_GRAPHS = ["map-territoire", "rank-territoire", "prod-ranking", "equip-map", "equip-coverage",
                    "coop-map", "coop-scatter"]


def register(app: Dash, data: Data) -> None:
    year_full = list(mx.year_bounds(data))
    canton_pref = data.cantons.set_index("canton_id")["prefecture"].to_dict()
    pref_region = data.prefectures.set_index("prefecture")["region"].to_dict()

    def uirev(f: mx.Filters, clicks=None) -> str:
        return f"{f.regions}|{f.prefectures}|{f.cantons}|{clicks}"

    # ── Navigation ────────────────────────────────────────────────────────────────────────
    @app.callback(Output("tabs", "value"), Input("url", "search"))
    def tab_from_url(search):
        # L'onglet initial vient de l'URL (?vue=production) : une seule vue est montée au chargement.
        view = parse_qs((search or "").lstrip("?")).get("vue", [None])[0]
        return view if view in lo.VIEW_BUILDERS else "territoire"

    @app.callback(Output("view", "children"), Input("tabs", "value"), Input("filters-ready", "data"))
    def render_view(view, ready):
        # La vue n'est montée qu'une fois les filtres initialisés : ses graphiques ne sont ainsi
        # dessinés qu'une fois (deux mises à jour rapprochées pouvaient laisser une carte vide).
        if not ready or view not in lo.VIEW_BUILDERS:
            raise PreventUpdate
        return lo.VIEW_BUILDERS[view](data)

    # ── Filtres croisés ───────────────────────────────────────────────────────────────────
    @app.callback(
        Output("f-region", "value"), Output("f-prefecture", "value"), Output("f-canton", "value"),
        Output("f-prefecture", "options"), Output("f-canton", "options"),
        Output("f-expl", "value"), Output("f-infra", "value"), Output("f-annee", "value"),
        Output("filters-ready", "data"),
        Input("f-region", "value"), Input("f-prefecture", "value"), Input("f-canton", "value"),
        Input("btn-reset", "n_clicks"), Input("sel-click", "data"), State("url", "search"),
    )
    def sync_filters(regions, prefs, cantons, _reset, click, search):
        regions, prefs, cantons = list(regions or []), list(prefs or []), list(cantons or [])
        before = (list(regions), list(prefs), list(cantons))
        others = (no_update, no_update, no_update)
        if len(ctx.triggered_prop_ids) != 1:
            # Chargement initial : lien partageable ?region=Savanes&prefecture=Oti
            query = parse_qs((search or "").lstrip("?"))
            regions = [r for r in query.get("region", []) if r in set(pref_region.values())]
            prefs = [p for p in query.get("prefecture", []) if p in pref_region]
        elif ctx.triggered_id == "btn-reset":
            regions, prefs, cantons, others = [], [], [], ([], [], year_full)
        elif ctx.triggered_id == "sel-click" and click:
            level, value = click["level"], click["value"]
            if level == "region":
                regions, prefs, cantons = ([] if regions == [value] else [value]), [], []
            elif level == "prefecture":
                prefs, cantons = ([] if prefs == [value] else [value]), []
                if prefs and regions and pref_region[value] not in regions:
                    regions = [pref_region[value]]
            elif level == "canton":
                cantons = [] if cantons == [value] else [value]
                if cantons and prefs and canton_pref[value] not in prefs:
                    prefs = [canton_pref[value]]
                if cantons and regions and pref_region[canton_pref[value]] not in regions:
                    regions = [pref_region[canton_pref[value]]]

        p = data.prefectures
        p_opts = p[p["region"].isin(regions)] if regions else p
        pref_options = sorted(p_opts["prefecture"])
        prefs = [x for x in prefs if x in pref_options]
        c = data.cantons
        c = c[c["prefecture"].isin(prefs)] if prefs else c[c["prefecture"].isin(pref_options)]
        c = c.sort_values(["canton", "prefecture"])
        canton_options = [{"label": f"{n} — {pf}", "value": i} for n, pf, i in zip(c["canton"], c["prefecture"], c["canton_id"])]
        valid = set(c["canton_id"])
        cantons = [x for x in cantons if x in valid]
        # Une valeur inchangée n'est pas réémise, pour ne pas redessiner toutes les vues. Exception : au
        # chargement initial, Dash n'exécute les callbacks dépendants que si les valeurs sont émises.
        initial = len(ctx.triggered_prop_ids) != 1
        values = [new if initial or new != old else no_update for new, old in zip((regions, prefs, cantons), before)]
        return *values, pref_options, canton_options, *others, True if initial else no_update

    def register_click(graph_id: str) -> None:
        @app.callback(Output("sel-click", "data", allow_duplicate=True), Output(graph_id, "clickData"),
                      Input(graph_id, "clickData"), prevent_initial_call=True)
        def on_click(click):
            custom = (click or {}).get("points", [{}])[0].get("customdata")
            if not custom or custom[0] not in ("region", "prefecture", "canton"):
                raise PreventUpdate
            # clickData est remis à zéro pour qu'un second clic sur la même zone désélectionne.
            return {"level": custom[0], "value": custom[1], "t": time.time()}, None

    for graph_id in CLICKABLE_GRAPHS:
        register_click(graph_id)

    # ── Bandeau KPI ───────────────────────────────────────────────────────────────────────
    @app.callback(Output("kpis", "children"), Output("scope-label", "children"), Output("scope-label", "className"),
                  *[Output(f"wrap-{i}", "className") for i in FILTER_IDS], *FILTER_INPUTS)
    def update_kpis(*values):
        f = mx.Filters.from_inputs(*values)
        k = mx.kpis(data, f)
        bt = k["by_type"]
        dens_na = pd.isna(k["dens_expl"])
        services = [mx.INFRA_TYPES[t].lower() for t in mx.equipment_types(data, f)]
        share = k["cantons_equipes"] / k["cantons_total"] * 100 if k["cantons_total"] else float("nan")
        coop_ratio = k["n_coop"] / k["n_expl"] * 100 if k["n_expl"] else float("nan")
        tiles = [
            lo.kpi_tile("Exploitations", fr(k["n_expl"]),
                        f"{fr(bt['petite'])} petites · {fr(bt['plantation'])} plantations · {fr(bt['grande'])} grandes"),
            lo.kpi_tile("Densité d'exploitations", th.UNAVAILABLE if dens_na else fr(k["dens_expl"], 1),
                        "superficie inconnue au niveau canton" if dens_na else f"pour 100 km² · {fr(k['km2'])} km²",
                        unavailable=dens_na),
            lo.kpi_tile("Superficie ZAAP", f"{fr(k['zaap_ha'], 0)} ha",
                        f"{fr(k['zaap_n'])} champs localisés · surface calculée"),
            lo.kpi_tile("Coopératives", fr(k["n_coop"]),
                        "aucune exploitation dans la sélection" if pd.isna(coop_ratio)
                        else f"{fr(coop_ratio, 0)} pour 100 exploitations"),
            lo.kpi_tile("Cantons équipés", [fr(k["cantons_equipes"]), html.Span(f" / {fr(k['cantons_total'])}", className="kpi-of")],
                        "aucun canton dans la sélection" if pd.isna(share)
                        else f"{fr(share, 0)} % · {', '.join(services) or 'aucun service retenu'}"),
        ]
        parts = []
        if f.cantons:
            parts.append(f"{len(f.cantons)} canton(s)")
        elif f.prefectures:
            parts.append(", ".join(f.prefectures[:3]) + ("…" if len(f.prefectures) > 3 else ""))
        elif f.regions:
            parts.append("Région " + ", ".join(f.regions))
        if f.years and list(f.years) != year_full:
            parts.append(f"créations {f.years[0]}–{f.years[1]}")
        # Les filtres actifs sont signalés en vert (couleur de sélection).
        year_on = bool(f.years) and list(f.years) != year_full
        active = [f.regions, f.prefectures, f.cantons, f.expl, f.infra, year_on]
        classes = ["filter" + (" filter-year" if i == "f-annee" else "") + (" active" if on else "")
                   for i, on in zip(FILTER_IDS, active)]
        label = ("Périmètre : " + " · ".join(parts)) if parts else "Périmètre : Togo entier"
        return tiles, label, "filtered" if parts else "", *classes

    # ── Territoire ────────────────────────────────────────────────────────────────────────
    @app.callback(
        Output("map-territoire", "figure"), Output("rank-territoire", "figure"), Output("rank-title", "children"),
        Output("map-note", "children"),
        Input("map-layer", "value"), Input("map-level", "value"), Input("map-measure", "value"),
        Input("map-options", "value"), Input("map-reset", "n_clicks"), *FILTER_INPUTS,
    )
    def update_territoire(layer, level, measure, options, recenter, *values):
        f = mx.Filters.from_inputs(*values)
        options = options or []
        fig = fg.map_figure(data, f, layer, level, measure, "points" in options, "basemap" in options, uirev(f, recenter))
        rank, title = fg.ranking_figure(data, f, layer, level, measure)
        notes = {
            "zaap": "ZAAP : surface calculée à partir des champs individuels levés ; les préfectures à 0 n'ont aucun champ dans le jeu de données.",
            "equipement": "Un point par canton, placé à la position médiane de ses enregistrements. Services pris en compte : "
                          + ", ".join(mx.INFRA_TYPES[t].lower() for t in mx.equipment_types(data, f)) + ".",
            "exploitations": "Densité = exploitations recensées pour 100 km² (superficies OCHA 2021).",
        }
        note = notes.get(layer, "Infrastructures localisées par leurs coordonnées ; agrégats par limites OCHA 2021.")
        if fg.layer_unavailable(data, layer):
            note = "Aucun jeu « magasins d'intrants » dans data/raw/."
        return fig, rank, title, note

    # ── Production ────────────────────────────────────────────────────────────────────────
    @app.callback(
        Output("prod-types", "figure"), Output("prod-timeline", "figure"), Output("prod-timeline-sub", "children"),
        Output("prod-ranking", "figure"), Output("prod-rank-title", "children"), Output("prod-rank-note", "children"),
        Input("prod-measure", "value"), *FILTER_INPUTS,
    )
    def update_production(measure, *values):
        f = mx.Filters.from_inputs(*values)
        ent = mx.filter_entities(data, f)
        dated = ent[ent["type"].isin(["grande", "plantation"])]
        sub = (f"{fr(dated['annee'].notna().sum())} unités datées sur {fr(len(dated))}" if len(dated)
               else "Aucune unité datée")
        ranking, by_canton, note = fg.production_ranking(data, f, measure)
        title = "Classement des cantons" if by_canton else "Classement des préfectures"
        return fg.type_figure(mx.kpis(data, f), f), fg.timeline_figure(ent, f), sub, ranking, title, note or ""

    # ── Équipements ───────────────────────────────────────────────────────────────────────
    # Deux callbacks : changer de couche ne redessine que la carte, pas la matrice ni la couverture.
    @app.callback(
        Output("equip-map", "figure"), Output("equip-legend", "children"), Output("equip-map-note", "children"),
        Input("equip-layer", "value"), *FILTER_INPUTS,
    )
    def update_equipment_map(layer, *values):
        f = mx.Filters.from_inputs(*values)
        fig = fg.map_figure(data, f, layer, "prefecture", "nombre", layer != "equipement", False, uirev(f))
        if layer != "equipement":
            return fig, [], ""
        cantons = mx.canton_table(data, f)
        services = ", ".join(mx.INFRA_TYPES[t].lower() for t in mx.equipment_types(data, f))
        legend = [html.Div([lo.swatch(th.EQUIP_COLORS[lv]), html.Span(f"{label} ({int((cantons['niveau'] == lv).sum())})")],
                           className="legend-item") for lv, label in mx.EQUIP_LEVELS.items()]
        return fig, legend, f"Niveau d'équipement = nombre de types de service présents dans le canton ({services})."

    @app.callback(
        Output("equip-stats", "children"), Output("equip-coverage", "figure"), Output("equip-matrix", "children"),
        Output("equip-matrix-sub", "children"), *FILTER_INPUTS,
    )
    def update_equipment_tables(*values):
        f = mx.Filters.from_inputs(*values)
        cantons = mx.canton_table(data, f)
        services = mx.equipment_types(data, f)
        n = len(cantons)

        def pct(mask):
            return f"{fr(mask.sum() / n * 100, 0)} %" if n else th.UNAVAILABLE

        stats = []
        for t, label in mx.INFRA_TYPES.items():
            if t == "intrant" and not data.has_intrants:
                stats.append(lo.stat(th.UNAVAILABLE, label))
            elif t in services:
                stats.append(lo.stat(pct(cantons[f"n_{t}"] > 0), label))
        none = int((cantons["niveau"] == 0).sum())
        stats.append(lo.stat(fr(none), "cantons sans aucun service", alert=none > 0))

        ordered = cantons.sort_values(["niveau", "n_expl"], ascending=[True, False])
        rows = pd.DataFrame({"Canton": ordered["canton"], "Préfecture": ordered["prefecture"]})
        for t, label in mx.INFRA_TYPES.items():
            # Un service non observable (jeu absent ou exclu par le filtre) reste vide, jamais à zéro.
            rows[label] = ordered[f"n_{t}"].astype(int) if t in services else None
        rows["Exploitations"] = ordered["n_expl"].astype(int)
        rows["Niveau"] = ordered["niveau"].map(mx.EQUIP_LEVELS)
        matrix = lo.equipment_matrix(rows) if n else html.Div(th.EMPTY, className="empty")
        sub = f"{fr(n)} cantons · sous-équipés en tête · cliquer sur un en-tête pour trier"
        return stats, fg.coverage_figure(cantons, f), matrix, sub

    # ── Coopératives & exploitations ──────────────────────────────────────────────────────
    @app.callback(
        Output("coop-map", "figure"), Output("coop-scatter", "figure"), Output("coop-stats", "children"),
        Output("coop-priorities", "children"), Output("coop-conclusion", "children"), *FILTER_INPUTS,
    )
    def update_cooperatives(*values):
        f = mx.Filters.from_inputs(*values)
        pref = mx.prefecture_table(data, f)
        cantons = mx.canton_table(data, f)
        corr = mx.spearman(pref[pref["in_scope"]])
        prio = mx.priorities(data, f, pref, cantons)

        if corr["rho"] is None:
            stats = [lo.stat(th.UNAVAILABLE, f"ρ de Spearman (n = {corr['n']}, minimum {mx.MIN_N_CORRELATION})")]
        else:
            p_txt = "< 0,001" if corr["p"] < 0.001 else fr(corr["p"], 3)
            stats = [lo.stat(fr(corr["rho"], 2), "ρ de Spearman"), lo.stat(p_txt, "valeur p"),
                     lo.stat(str(corr["n"]), "préfectures")]

        def block(title, criterion, body):
            return html.Div([html.H3(title), html.P(criterion, className="criterion"), body], className="prio")

        def empty(msg="Aucune zone ne répond au critère."):
            return html.Div(msg, className="empty small")

        g = prio["coop_gap"]
        coop_body = lo.table(["Préfecture", "Expl. / 100 km²", "Coop. / 100 km²"],
                             [[r.prefecture, fr(r.dens_expl, 1), fr(r.dens_coop, 1)] for r in g.itertuples()]) if len(g) else empty()
        g = prio["intrant_gap"]
        if g is None:
            intr_body = html.Div(th.UNAVAILABLE, className="empty small na")
        else:
            intr_body = lo.table(["Préfecture", "Expl. / 100 km²", "Magasins / 1 000 expl."],
                                 [[r.prefecture, fr(r.dens_expl, 1), fr(r.intrants_p1000, 1)] for r in g.itertuples()]) if len(g) else empty()
        g = prio["zaap_gap"]
        zaap_body = lo.table(["Canton", "Préfecture", "ZAAP (ha)", "Niveau"],
                             [[r.canton, r.prefecture, fr(r.zaap_ha, 1), mx.EQUIP_LEVELS[r.niveau]] for r in g.itertuples()]) if len(g) else empty()
        thr = prio["zaap_threshold"]
        blocks = [
            block("Forte production, faible présence coopérative",
                  "Densité d'exploitations > médiane et densité de coopératives ≤ médiane.", coop_body),
            block("Forte production, faible accès aux intrants",
                  "Densité d'exploitations > médiane et magasins pour 1 000 exploitations ≤ médiane.", intr_body),
            block("ZAAP importantes, faible équipement",
                  f"Superficie ZAAP ≥ médiane des cantons dotés ({fr(thr, 1)} ha) et au plus un type de service."
                  if not pd.isna(thr) else "Aucun champ ZAAP avec les filtres actuels.", zaap_body),
        ]
        text = [html.P(s) for s in mx.conclusion(data, pref, corr, prio)]
        return fg.quadrant_map(data, pref, f, uirev(f)), fg.scatter_figure(pref), stats, blocks, text

    # ── Exports ───────────────────────────────────────────────────────────────────────────
    def csv_download(df: pd.DataFrame, name: str) -> dict:
        content = "﻿" + df.to_csv(index=False, sep=";", decimal=",")
        return dict(content=content, filename=f"{name}_{time.strftime('%Y%m%d')}.csv", type="text/csv")

    @app.callback(Output("dl-data", "data"), Input("btn-export-data", "n_clicks"),
                  *[State(i, "value") for i in FILTER_IDS], prevent_initial_call=True)
    def export_data(_n, *values):
        f = mx.Filters.from_inputs(*values)
        return csv_download(mx.filter_entities(data, f).drop(columns=["fid_source"]), "atlas_togo_donnees_filtrees")

    @app.callback(Output("dl-indicateurs", "data"), Input("btn-export-ind", "n_clicks"),
                  *[State(i, "value") for i in FILTER_IDS], prevent_initial_call=True)
    def export_indicators(_n, *values):
        f = mx.Filters.from_inputs(*values)
        pref = mx.prefecture_table(data, f)
        pref = pref[pref["in_scope"]].drop(columns=["in_scope", "lon_min", "lat_min", "lon_max", "lat_max"])
        return csv_download(pref.round(3), "atlas_togo_indicateurs_prefectures")
