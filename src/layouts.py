"""Mise en page : en-tête, filtres, bandeau KPI et les cinq vues."""
from __future__ import annotations

import re
from datetime import date

from dash import dash_table, dcc, html

from . import metrics as mx, theme as th
from .data_loader import ROOT, Data
from .theme import fr

VIEWS = [("territoire", "Territoire"), ("production", "Production"), ("equipements", "Équipements"),
         ("cooperatives", "Coopératives & exploitations"), ("qualite", "Qualité des données")]

# Libellés internes des listes déroulantes (anglais par défaut dans Dash).
DROPDOWN_LABELS = {
    "select_all": "Tout sélectionner", "deselect_all": "Tout désélectionner",
    "selected_count": "{num_selected} sélectionné(s)", "search": "Rechercher",
    "clear_search": "Effacer la recherche", "clear_selection": "Effacer la sélection",
    "no_options_found": "Aucun résultat",
}

_NUMERIC = re.compile(r"^[\d   ,.%<≥—-]+$")

MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
          "novembre", "décembre"]


def date_fr(iso: str | None) -> str:
    if not iso:
        return th.UNAVAILABLE
    d = date.fromisoformat(iso)
    return f"{'1er' if d.day == 1 else d.day} {MONTHS[d.month - 1]} {d.year}"


# ── Briques ───────────────────────────────────────────────────────────────────────────────

def card(title, *children, subtitle=None, tools=None, className=""):
    # `is not None` : un composant Dash sans enfant est évalué à False.
    head = html.Div([
        html.Div([html.H2(title), html.P(subtitle, className="card-sub") if subtitle is not None else None]),
        html.Div(tools, className="card-tools") if tools is not None else None,
    ], className="card-head")
    return html.Section([head, *children], className=f"card {className}".strip())


def segmented(id_, options, value):
    return dcc.RadioItems(id=id_, options=[{"label": l, "value": v} for v, l in options], value=value,
                          className="seg", inline=True)


def graph(id_, height=None, **kw):
    style = {"height": f"{height}px"} if height else {}
    return dcc.Graph(id=id_, config=th.GRAPH_CONFIG, style=style, **kw)


def table(headers, rows, className=""):
    """Tableau HTML ; `rows` est une liste de listes de cellules (texte ou composants)."""
    # Une colonne est alignée à droite si toutes ses cellules sont des nombres formatés.
    numeric = [bool(rows) and all(isinstance(r[i], str) and _NUMERIC.match(r[i]) for r in rows)
               for i in range(len(headers))]
    cls = lambda i: "num" if numeric[i] else None
    return html.Table([
        html.Thead(html.Tr([html.Th(h, className=cls(i)) for i, h in enumerate(headers)])),
        html.Tbody([html.Tr([html.Td(c, className=cls(i)) for i, c in enumerate(r)]) for r in rows]),
    ], className=f"tbl {className}".strip())


def note(text, alert=False):
    return html.P(text, className="note alert" if alert else "note")


def swatch(color):
    return html.Span(className="swatch", style={"background": color})


# ── Structure générale ────────────────────────────────────────────────────────────────────

def filter_bar(data: Data):
    y0, y1 = mx.year_bounds(data)
    regions = sorted(data.prefectures["region"].unique())
    infra_opts = [{"label": l + ("" if t != "intrant" or data.has_intrants else " — indisponible"), "value": t,
                   "disabled": t == "intrant" and not data.has_intrants} for t, l in mx.INFRA_TYPES.items()]

    def field(label, control, className=""):
        return html.Div([html.Label(label), control], id=f"wrap-{control.id}", className=f"filter {className}".strip())

    return html.Div([
        field("Région", dcc.Dropdown(id="f-region", options=regions, multi=True, labels=DROPDOWN_LABELS, placeholder="Toutes")),
        field("Préfecture", dcc.Dropdown(id="f-prefecture", options=[], multi=True, labels=DROPDOWN_LABELS, placeholder="Toutes")),
        field("Canton", dcc.Dropdown(id="f-canton", options=[], multi=True, labels=DROPDOWN_LABELS, placeholder="Rechercher un canton…")),
        field("Type d'exploitation", dcc.Dropdown(
            id="f-expl", options=[{"label": l, "value": t} for t, l in mx.EXPL_TYPES.items()], multi=True, labels=DROPDOWN_LABELS,
            placeholder="Tous")),
        field("Type d'infrastructure", dcc.Dropdown(id="f-infra", options=infra_opts, multi=True, labels=DROPDOWN_LABELS, placeholder="Tous")),
        field("Année de création", dcc.RangeSlider(
            id="f-annee", min=y0, max=y1, step=1, value=[y0, y1], allowCross=False,
            marks={y: str(y) for y in (y0, 1960, 1990, y1)}, tooltip={"placement": "bottom"}), "filter-year"),
    ], className="filters")


def logo():
    """Logo de l'en-tête : premier fichier assets/logo.(svg|png|jpg|webp) trouvé, sinon rien."""
    for ext in ("svg", "png", "jpg", "jpeg", "webp"):
        if (ROOT / "assets" / f"logo.{ext}").exists():
            return html.Img(src=f"/assets/logo.{ext}", className="logo", alt="Logo")
    return None


def build_layout(data: Data):
    meta = data.meta
    return html.Div([
        dcc.Location(id="url"),
        dcc.Store(id="sel-click"),
        dcc.Store(id="filters-ready"),
        dcc.Download(id="dl-data"),
        dcc.Download(id="dl-indicateurs"),
        html.Header([
            html.Div([
                logo(),
                html.Div([
                    html.H1("Atlas du tissu productif agricole du Togo"),
                    html.P([f"Données mises à jour le {date_fr(meta.get('date_export'))}", html.Span(" · "),
                            html.Span(id="scope-label")], className="meta"),
                ]),
            ], className="brand"),
            html.Div([
                html.Button("Réinitialiser", id="btn-reset", className="btn"),
                html.Button("Exporter les données", id="btn-export-data", className="btn",
                            title="CSV des enregistrements correspondant aux filtres"),
                html.Button("Exporter les indicateurs", id="btn-export-ind", className="btn btn-primary",
                            title="CSV des indicateurs par préfecture de la vue filtrée"),
            ], className="actions"),
        ], className="header"),
        filter_bar(data),
        html.Div(id="kpis", className="kpis"),
        dcc.Tabs(id="tabs", value=None, className="tabs", parent_className="tabs-wrap",
                 children=[dcc.Tab(label=l, value=v, className="tab", selected_className="tab tab-on") for v, l in VIEWS]),
        dcc.Loading(html.Main(id="view", className="view"), type="dot", color=th.SELECT, delay_show=350,
                    overlay_style={"visibility": "visible", "opacity": 0.5}),
        html.Footer(f"Sources : portail de données ouvertes agricoles du Togo (export du {date_fr(meta.get('date_export'))}) "
                    f"· {meta.get('limites')} · Traitement : {date_fr(meta.get('date_traitement'))}", className="footer"),
    ], className="app")


def kpi_tile(label, value, sub, unavailable=False):
    return html.Div([
        html.Div(label, className="kpi-label"),
        html.Div(value, className="kpi-value" + (" na" if unavailable else "")),
        html.Div(sub, className="kpi-sub"),
    ], className="kpi")


# ── Vues ──────────────────────────────────────────────────────────────────────────────────

def view_territoire(data: Data):
    layers = [("exploitations", "Exploitations"), ("zaap", "ZAAP"), ("cooperatives", "Coopératives"),
              ("marches", "Marchés"), ("intrants", "Intrants"), ("pepinieres", "Pépinières"),
              ("equipement", "Niveau d'équipement")]
    return html.Div([
        card("Carte du territoire",
             html.Div([
                 segmented("map-layer", layers, "exploitations"),
                 html.Div([
                     segmented("map-level", [("prefecture", "Préfectures"), ("region", "Régions")], "prefecture"),
                     segmented("map-measure", [("nombre", "Nombre"), ("densite", "Densité")], "densite"),
                     dcc.Checklist(id="map-options", className="checks", inline=True, value=[],
                                   options=[{"label": "Points localisés", "value": "points"},
                                            {"label": "Fond de carte (en ligne)", "value": "basemap"}]),
                     html.Button("Recentrer", id="map-reset", className="btn btn-sm"),
                 ], className="toolbar-row"),
             ], className="toolbar"),
             graph("map-territoire", 640),
             html.P(id="map-note", className="note"),
             subtitle="Cliquer sur une zone ou un point filtre tout le tableau de bord.", className="span-2"),
        card(html.Span(id="rank-title"), graph("rank-territoire"),
             note("Classement limité au périmètre filtré. Cliquer sur une barre pour filtrer.")),
    ], className="grid grid-3")


def view_production(data: Data):
    return html.Div([
        html.Div([
            card("Répartition par type", graph("prod-types", 190), subtitle="Nombre d'exploitations recensées"),
            card("Années de création déclarées", graph("prod-timeline", 260),
                 note("Grandes exploitations et plantations uniquement, par période de 5 ans. Il s'agit de l'année "
                      "de création des unités encore recensées, pas d'une évolution du nombre d'exploitations : "
                      "aucune comparaison temporelle fiable n'est possible."),
                 subtitle=html.Span(id="prod-timeline-sub")),
        ], className="stack"),
        card(html.Span(id="prod-rank-title"),
             html.Div(graph("prod-ranking"), className="scroll-y tall"),
             html.P(id="prod-rank-note", className="note"),
             tools=segmented("prod-measure", [("nombre", "Nombre"), ("densite", "Densité / 100 km²")], "nombre"),
             subtitle="Par type d'exploitation. Cliquer sur une barre pour filtrer.", className="span-2"),
    ], className="grid grid-3")


def view_equipements(data: Data):
    layers = [("equipement", "Niveau d'équipement"), ("marches", "Marchés"), ("intrants", "Magasins d'intrants"),
              ("pepinieres", "Pépinières")]
    return html.Div([
        card("Carte des équipements", graph("equip-map", 560),
             html.Div(id="equip-legend", className="legend legend-row"),
             html.P(id="equip-map-note", className="note"),
             tools=segmented("equip-layer", layers, "equipement"), className="span-2"),
        card("Couverture territoriale", html.Div(id="equip-stats", className="stats"),
             html.H3("Cantons équipés d'au moins un service"), graph("equip-coverage"),
             subtitle="Part des cantons du périmètre disposant de chaque service"),
        card("Matrice canton × équipement", html.Div(id="equip-matrix"),
             subtitle=html.Span(id="equip-matrix-sub"), className="span-3"),
    ], className="grid grid-3")


def view_cooperatives(data: Data):
    legend = html.Div([
        html.Div([swatch(th.QUADRANT_COLORS[q]), html.Span(l)], className="legend-item")
        for q, l in mx.QUADRANTS.items()
    ], className="legend")
    return html.Div([
        card("Typologie des préfectures", graph("coop-map", 520), legend,
             note("Fort / faible : au-dessus ou au-dessous de la médiane nationale des 39 préfectures."),
             subtitle="Densité d'exploitations × densité de coopératives"),
        card("Exploitations et coopératives par préfecture", html.Div(id="coop-stats", className="stats"),
             graph("coop-scatter", 420),
             note("Droite : tendance linéaire indicative. Pointillés : médianes nationales. "
                  "Une corrélation ne prouve aucun lien de cause à effet."),
             className="span-2"),
        card("Zones prioritaires", html.Div(id="coop-priorities", className="prio-grid"), className="span-2"),
        card("Lecture", html.Div(id="coop-conclusion", className="conclusion")),
    ], className="grid grid-3")


def view_qualite(data: Data):
    q, comp = data.quality, data.completeness
    total = int(q["lignes_brutes"].sum())
    kept = int(q["lignes_retenues"].sum())
    off = int(q["hors_prefecture_declaree"].sum())
    stats = html.Div([
        stat(fr(total), "enregistrements bruts"),
        stat(fr(int(q["sans_coordonnees"].sum())), "sans coordonnées"),
        stat(fr(int(q["doublons_exclus"].sum())), "doublons exacts exclus"),
        stat(fr(int(q["geometries_corrigees"].sum())), "géométries invalides réparées"),
        stat(f"{fr((1 - off / kept) * 100, 1)} %", "points situés dans la préfecture déclarée"),
    ], className="stats stats-5")

    rows = []
    for r in q.itertuples():
        if not r.lignes_brutes:
            rows.append([r.jeu, html.Span(th.UNAVAILABLE, className="na"), "—", "—", "—", "—", "—"])
            continue
        rows.append([r.jeu, fr(r.lignes_brutes), fr(r.lignes_retenues), r.geometrie, fr(r.sans_coordonnees),
                     fr(r.geometries_corrigees), fr(r.hors_prefecture_declaree)])
    datasets = table(["Jeu de données", "Lignes brutes", "Retenues", "Géométrie", "Sans coordonnées",
                      "Géométries réparées", "Hors préfecture déclarée"], rows)

    comp_rows = []
    for r in comp[~comp["variable"].isin(["region_nom_bdd", "commune_nom_bdd"])].itertuples():
        pct = r.taux * 100
        bar = html.Div(html.Div(className="bar-fill" + (" low" if pct < 80 else ""), style={"width": f"{pct:.1f}%"}),
                       className="bar")
        comp_rows.append([r.jeu, html.Code(r.variable), bar, f"{fr(pct, 1)} %", fr(r.total - r.renseignes)])
    completeness = table(["Jeu de données", "Variable", "Complétude", "Taux", "Manquants"], comp_rows, "tbl-compact")

    warnings = [
        "Les jeux recensent des unités géolocalisées, pas un recensement exhaustif : une préfecture sans "
        "enregistrement peut refléter une collecte incomplète plutôt qu'une absence réelle.",
        "Les petites exploitations sont très inégalement réparties (41 % en région Maritime, 3 % en Centrale) et "
        "portent un champ « coopérative » : la collecte semble liée aux réseaux coopératifs, ce qui peut gonfler "
        "mécaniquement la corrélation coopératives–exploitations.",
        "ZAAP : le jeu contient des champs individuels (16 préfectures, 3 régions), pas les périmètres officiels. "
        "La superficie est la somme des polygones levés et sous-estime la superficie aménagée.",
        "Densités : superficies des préfectures issues des limites OCHA de 2021 (Golfe inclut Lomé Commune). "
        "Aucune superficie fiable n'existe au niveau canton : la densité y est indisponible.",
        "Cantons : 394 cantons apparaissent dans les données ; ce total sert de référence faute de liste officielle "
        "concordante. Leur position est la médiane de leurs enregistrements.",
        "Année : disponible seulement pour grandes exploitations, plantations et pépinières ; le filtre Année "
        "n'agit que sur ces trois jeux.",
    ]
    sources = table(["Source", "Contenu", "Date"], [
        ["Portail de données ouvertes agricoles du Togo", "8 jeux géolocalisés (CSV)", date_fr(data.meta.get("date_export"))],
        ["OCHA COD-AB Togo v02 (HDX), CC BY-IGO", "Limites et superficies des régions et préfectures", "7 janvier 2021"],
        ["Banque mondiale via HDX", "Indicateurs nationaux (contexte, non cartographiés)", "1960–2023"],
    ])
    return html.Div([
        card("Synthèse de la préparation", stats, datasets,
             note("« Nsp », « Néant » et valeurs vides sont traités comme manquants. Les enregistrements exclus sont "
                  "listés dans data/processed/exclusions.csv."), className="span-3"),
        card("Complétude par variable", html.Div(completeness, className="scroll-y"),
             subtitle="Part des valeurs renseignées", className="span-2"),
        html.Div([
            card("Avertissements méthodologiques", html.Ul([html.Li(w) for w in warnings], className="warn-list")),
            card("Sources", sources),
        ], className="stack"),
    ], className="grid grid-3")


def equipment_matrix(rows):
    """Matrice canton × équipement : tableau paginé et triable (un seul composant, donc rapide)."""
    services = list(mx.INFRA_TYPES.values())
    cell = {"fontFamily": th.FONT, "fontSize": "12.5px", "padding": "7px 10px", "textAlign": "left",
            "border": "none", "borderBottom": f"1px solid {th.LINE}", "color": th.INK}
    conditional = [{"if": {"column_id": c}, "textAlign": "right"} for c in services + ["Exploitations"]]
    conditional += [{"if": {"column_id": "Canton"}, "fontWeight": 600}]
    conditional += [{"if": {"column_id": c, "filter_query": f"{{{c}}} = 0"}, "color": "#C2C2C0"} for c in services]
    conditional += [{"if": {"column_id": c, "filter_query": f"{{{c}}} > 0"}, "fontWeight": 700, "color": th.SELECT}
                    for c in services]
    conditional += [
        {"if": {"column_id": "Niveau", "filter_query": f'{{Niveau}} = "{mx.EQUIP_LEVELS[0]}"'},
         "color": th.ACCENT, "fontWeight": 700},
        {"if": {"column_id": "Niveau", "filter_query": f'{{Niveau}} = "{mx.EQUIP_LEVELS[1]}"'}, "color": th.INK_2},
    ]
    return dash_table.DataTable(
        data=rows.to_dict("records"), columns=[{"name": c, "id": c} for c in rows.columns],
        page_size=15, sort_action="native", cell_selectable=False, style_as_list_view=True,
        style_cell=cell, style_data_conditional=conditional,
        style_header={"fontSize": "10.5px", "fontWeight": 600, "textTransform": "uppercase", "letterSpacing": ".05em",
                      "color": th.MUTED, "backgroundColor": th.SURFACE, "borderBottom": "1px solid #CFCFCD"},
        style_table={"overflowX": "auto"},
    )


def stat(value, label, alert=False):
    return html.Div([html.Div(value, className="stat-value" + (" alert" if alert else "")),
                     html.Div(label, className="stat-label")], className="stat")


VIEW_BUILDERS = {"territoire": view_territoire, "production": view_production, "equipements": view_equipements,
                 "cooperatives": view_cooperatives, "qualite": view_qualite}
