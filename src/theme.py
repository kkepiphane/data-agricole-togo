"""Charte graphique noir et blanc : couleurs, formats et mise en page Plotly."""
from __future__ import annotations

import math

import plotly.graph_objects as go

INK = "#111111"
INK_2 = "#525252"
MUTED = "#8C8C8C"
LINE = "#E4E4E2"
SURFACE = "#FFFFFF"
BACKGROUND = "#F5F5F3"
ACCENT = "#D9480F"  # alertes uniquement (sous-équipement, données incomplètes)
SELECT = "#1E8E4E"  # éléments sélectionnés dans l'interface (onglet, option et filtre actifs)
OUTLINE = "#111111"  # contour de la zone filtrée sur les cartes : foncé pour ressortir sur les verts
# Données : une famille de verts (magnitude), plus un ambre et un ardoise pour distinguer les catégories.
# Le noir reste réservé au texte.
FILL = "#2F9E62"
FILL_STRONG = "#176B3C"
FILL_MID = "#8CCBA6"
FILL_LIGHT = "#CFE9DA"
AMBER = "#E3A72F"
SLATE = "#6B7A89"
POINT = "#26302B"

FONT = "Inter, 'Segoe UI', system-ui, -apple-system, Roboto, 'Helvetica Neue', Arial, sans-serif"

# Séquentiel : une seule teinte, clair → foncé.
SEQUENTIAL = [[0.0, "#F1F7F3"], [0.25, FILL_LIGHT], [0.5, FILL_MID], [0.75, "#3BA36B"], [1.0, FILL_STRONG]]
# Version claire, utilisée quand des points noirs sont superposés au fond.
SEQUENTIAL_LIGHT = [[0.0, "#F4F9F6"], [0.5, "#D9EEE2"], [1.0, "#A9D8BC"]]

TYPE_COLORS = {"petite": FILL, "plantation": AMBER, "grande": SLATE}
QUADRANT_COLORS = {"faible_faible": "#E3E3E1", "fort_faible": ACCENT, "faible_fort": FILL_MID, "fort_fort": FILL_STRONG}
EQUIP_COLORS = {0: ACCENT, 1: AMBER, 2: FILL}

UNAVAILABLE = "Donnée indisponible"
EMPTY = "Aucune donnée pour cette sélection"

GRAPH_CONFIG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d", "toggleSpikelines"],
    "toImageButtonOptions": {"format": "png", "scale": 2, "filename": "atlas-agricole-togo"},
    "scrollZoom": True,
}


def fr(value, decimals: int = 0, unit: str = "") -> str:
    """Nombre au format français ; « Donnée indisponible » si la valeur manque."""
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return UNAVAILABLE
    text = f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")
    return f"{text} {unit}" if unit else text


def base_layout(**overrides) -> dict:
    layout = dict(
        font=dict(family=FONT, size=12, color=INK_2),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        margin=dict(l=8, r=16, t=8, b=8),
        separators=", ",
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=FILL_MID, font=dict(family=FONT, size=12, color=INK)),
        showlegend=False,
        xaxis=dict(gridcolor=LINE, zeroline=False, linecolor=LINE, ticks="", automargin=True, title_font_size=11),
        yaxis=dict(gridcolor=LINE, zeroline=False, linecolor=LINE, ticks="", automargin=True, title_font_size=11),
        legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0, font=dict(size=11, color=INK_2)),
        bargap=0.32,
    )
    layout.update(overrides)
    return layout


def empty_figure(message: str = EMPTY, height: int | None = None) -> go.Figure:
    """État vide : un message centré, sans axes."""
    fig = go.Figure()
    fig.update_layout(base_layout(height=height))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
                       font=dict(size=13, color=MUTED))
    return fig
