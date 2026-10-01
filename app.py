"""Atlas du tissu productif agricole du Togo — point d'entrée.

    python app.py              lance le tableau de bord sur http://127.0.0.1:8050
    python app.py --rebuild    reconstruit d'abord data/processed/ depuis data/raw/
    python app.py --host 0.0.0.0 --port 8060    accès depuis le réseau local, autre port
"""
import argparse
import os

from dash import Dash

from src import callbacks, layouts
from src.data_loader import load


def create_app(rebuild: bool = False) -> Dash:
    data = load(rebuild=rebuild)
    app = Dash(__name__, title="Atlas agricole du Togo", suppress_callback_exceptions=True,
               meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}])
    app.layout = layouts.build_layout(data)
    callbacks.register(app, data)
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rebuild", action="store_true", help="reconstruire les données traitées")
    parser.add_argument("--host", default="127.0.0.1", help="0.0.0.0 pour ouvrir l'accès au réseau local")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8050)))
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    create_app(rebuild=args.rebuild).run(host=args.host, port=args.port, debug=args.debug)
