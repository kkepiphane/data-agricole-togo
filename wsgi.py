"""Point d'entrée WSGI pour un serveur de production.

    waitress-serve --listen=0.0.0.0:8050 wsgi:server      (Windows, Linux, macOS)
    gunicorn --bind 0.0.0.0:8050 --workers 2 wsgi:server  (Linux, macOS)
"""
from app import create_app

server = create_app().server
