"""Test de fumée : exécute chaque callback via le serveur Flask, sans navigateur.

    python tests/smoke_test.py

Vérifie le démarrage, les filtres croisés (clic carte → filtre), les cinq vues sous plusieurs
combinaisons de filtres (dont une sélection vide) et les deux exports CSV.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from app import create_app  # noqa: E402

app = create_app()
client = app.server.test_client()
YEARS = [1900, 2022]

DEFAULTS = {
    "url.search": "", "tabs.value": "territoire", "filters-ready.data": True, "btn-reset.n_clicks": None, "sel-click.data": None,
    "f-region.value": [], "f-prefecture.value": [], "f-canton.value": [], "f-expl.value": [], "f-infra.value": [],
    "f-annee.value": YEARS, "map-layer.value": "exploitations", "map-level.value": "prefecture",
    "map-measure.value": "densite", "map-options.value": ["points"], "map-reset.n_clicks": None,
    "prod-measure.value": "nombre", "equip-layer.value": "equipement",
    "btn-export-data.n_clicks": 1, "btn-export-ind.n_clicks": 1,
}


def call(output_key: str, overrides: dict | None = None, triggered: list[str] | None = None) -> dict:
    """Appelle le callback identifié par sa clé de sortie et retourne la réponse décodée."""
    cb = app.callback_map[output_key]
    values = {**DEFAULTS, **(overrides or {})}
    spec = lambda items: [{"id": i["id"], "property": i["property"], "value": values.get(f"{i['id']}.{i['property']}")}
                          for i in items]
    outputs = [dict(zip(("id", "property"), part.rsplit(".", 1))) for part in output_key.strip(".").split("...")]
    payload = {"output": output_key, "outputs": outputs if output_key.startswith("..") else outputs[0],
               "inputs": spec(cb["inputs"]), "state": spec(cb["state"]),
               "changedPropIds": triggered if triggered is not None else [f"{i['id']}.{i['property']}" for i in cb["inputs"]]}
    resp = client.post("/_dash-update-component", json=payload)
    assert resp.status_code in (200, 204), f"{output_key} → HTTP {resp.status_code}\n{resp.get_data(as_text=True)[:2000]}"
    return json.loads(resp.data)["response"] if resp.status_code == 200 else {}


def key(fragment: str) -> str:
    matches = [k for k in app.callback_map if fragment in k]
    assert len(matches) == 1, f"{fragment}: {matches}"
    return matches[0]


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK ' if condition else 'ÉCHEC'}  {label}{'  — ' + detail if detail else ''}")
    assert condition, label


print("Démarrage")
check("page d'accueil", client.get("/").status_code == 200)
check("mise en page", client.get("/_dash-layout").status_code == 200)

print("Navigation")
for view in ("territoire", "production", "equipements", "cooperatives", "qualite"):
    r = call(key("view.children"), {"tabs.value": view})
    check(f"vue {view}", "children" in r["view"])
check("onglet depuis l'URL", call(key("tabs.value"), {"url.search": "?vue=production"})["tabs"]["value"] == "production")

print("Filtres croisés")
K_SYNC = key("f-region.value")
r = call(K_SYNC, {"f-region.value": ["Savanes"]}, ["f-region.value"])
check("région → préfectures proposées", len(r["f-prefecture"]["options"]) == 7, f"{len(r['f-prefecture']['options'])} préfectures")
r = call(K_SYNC, {"sel-click.data": {"level": "prefecture", "value": "Oti"}}, ["sel-click.data"])
check("clic carte → filtre préfecture", r["f-prefecture"]["value"] == ["Oti"], f"{len(r['f-canton']['options'])} cantons proposés")
r = call(K_SYNC, {"f-prefecture.value": ["Oti"], "sel-click.data": {"level": "prefecture", "value": "Oti"}}, ["sel-click.data"])
check("second clic → désélection", r["f-prefecture"]["value"] == [])
r = call(K_SYNC, {"sel-click.data": {"level": "canton", "value": "Oti|Loko"}}, ["sel-click.data"])
check("clic canton → filtre canton", r["f-canton"]["value"] == ["Oti|Loko"])
r = call(K_SYNC, {"f-region.value": ["Kara"], "f-prefecture.value": ["Kozah"]}, ["btn-reset.n_clicks"])
check("réinitialisation", r["f-region"]["value"] == [] and r["f-annee"]["value"] == YEARS)
r = call(K_SYNC, {"url.search": "?region=Savanes&prefecture=Oti"})
check("lien partageable", r["f-region"]["value"] == ["Savanes"] and r["f-prefecture"]["value"] == ["Oti"])
click = {"points": [{"customdata": ["prefecture", "Zio"]}]}
r = call(key("map-territoire.clickData"), {"map-territoire.clickData": click})
check("clic graphique → sélection", r["sel-click"]["data"]["value"] == "Zio")

SCENARIOS = {
    "Togo entier": {},
    "région Savanes": {"f-region.value": ["Savanes"]},
    "préfecture Oti": {"f-region.value": ["Savanes"], "f-prefecture.value": ["Oti"]},
    "canton Loko (Oti)": {"f-canton.value": ["Oti|Loko"]},
    "plantations 2010-2022": {"f-expl.value": ["plantation"], "f-annee.value": [2010, 2022]},
    "marchés seuls": {"f-infra.value": ["marche"]},
    "sélection vide (Golfe × grandes)": {"f-prefecture.value": ["Golfe"], "f-expl.value": ["grande"], "f-annee.value": [1900, 1901]},
}
print("Vues × scénarios de filtres")
for name, filters in SCENARIOS.items():
    k = call(key("kpis.children."), filters)
    for layer in ("exploitations", "zaap", "cooperatives", "marches", "intrants", "pepinieres", "equipement"):
        for level in ("prefecture", "region"):
            call(key("map-territoire.figure"), {**filters, "map-layer.value": layer, "map-level.value": level})
    for measure in ("nombre", "densite"):
        call(key("prod-ranking.figure"), {**filters, "prod-measure.value": measure})
    for layer in ("equipement", "marches", "intrants", "pepinieres"):
        call(key("equip-map.figure."), {**filters, "equip-layer.value": layer})
    call(key("equip-matrix.children"), filters)
    call(key("coop-map.figure"), filters)
    check(name, len(k["kpis"]["children"]) == 5, k["scope-label"]["children"])

print("Exports")
r = call(key("dl-data.data"), {"f-prefecture.value": ["Oti"]}, ["btn-export-data.n_clicks"])
rows = r["dl-data"]["data"]["content"].count("\n") - 1
check("CSV des données filtrées", rows > 100 and "prefecture" in r["dl-data"]["data"]["content"][:300], f"{rows} lignes")
r = call(key("dl-indicateurs.data"), {"f-region.value": ["Savanes"]}, ["btn-export-ind.n_clicks"])
rows = r["dl-indicateurs"]["data"]["content"].count("\n") - 1
check("CSV des indicateurs", rows == 7, f"{rows} préfectures")

print("\nTous les contrôles sont passés.")
