"""Nettoyage et normalisation des champs texte, des années et des listes."""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

# Valeurs saisies équivalentes à une absence d'information.
MISSING_TOKENS = {"", "nsp", "neant", "ne sait pas", "nan", "none", "null", "n/a", "-"}

YEAR_MIN, YEAR_MAX = 1900, 2026

_SET_LABELS = {
    "cooperative production": "Production",
    "cooperative transformation": "Transformation",
    "tontine": "Tontine",
    "entraide": "Entraide",
    "small business": "Petit commerce",
    "champ de zaap": "Champ de ZAAP",
    "autre": "Autre",
    "gpc": "GPC",
    "esop": "ESOP",
}


def norm_key(value) -> str:
    """Clé de jointure : minuscules, sans accents ni ponctuation."""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text.lower())


_MISSING_KEYS = {norm_key(t) for t in MISSING_TOKENS}


def fix_mojibake(text: str) -> str:
    """Répare l'UTF-8 lu comme du Latin-1 (« coopÃ©rative » → « coopérative »)."""
    if "Ã" not in text and "Â" not in text:
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def clean_text(value):
    """Texte normalisé, ou None si la valeur est manquante."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = re.sub(r"\s+", " ", fix_mojibake(str(value))).strip()
    if norm_key(text) in _MISSING_KEYS:
        return None
    return text


def clean_place(value):
    """Nom de lieu : les saisies tout en majuscules passent en casse de titre."""
    text = clean_text(value)
    if text and text.isupper() and len(text) > 3:
        text = text.title()
    return text


def parse_year(value):
    """Année plausible (1900-2026) ou NA."""
    text = clean_text(value)
    if text is None or not re.fullmatch(r"\d{4}", text):
        return pd.NA
    year = int(text)
    return year if YEAR_MIN <= year <= YEAR_MAX else pd.NA


def parse_set(value):
    """« {a,b} » → libellés normalisés, dédoublonnés, séparés par « · »."""
    text = clean_text(value)
    if text is None:
        return None
    labels = []
    for item in text.strip("{}").split(","):
        item = item.strip().strip('"')
        if not item:
            continue
        key = unicodedata.normalize("NFKD", item).encode("ascii", "ignore").decode().lower()
        label = _SET_LABELS.get(key, item.capitalize())
        if label not in labels:
            labels.append(label)
    return " · ".join(labels) if labels else None


def parse_days(value):
    """« {lundi,jeudi} » → « Lundi · Jeudi » ; « Tous les jours » si 7 jours."""
    text = clean_text(value)
    if text is None:
        return None
    order = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    days = {d.strip().lower() for d in text.strip("{}").split(",")}
    days = [d for d in order if d in days]
    if len(days) == 7:
        return "Tous les jours"
    return " · ".join(d.capitalize() for d in days) if days else None
