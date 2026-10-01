"""Lanceur en un clic : crée l'environnement, installe les dépendances, démarre l'atlas et ouvre le navigateur.

Appelé par demarrer.bat (Windows), demarrer.command (macOS) et demarrer.sh (Linux).
Peut aussi être lancé directement :  python lancer.py     (python3 sous Linux/macOS)

N'utilise que la bibliothèque standard : il doit fonctionner avant toute installation.
"""
import hashlib
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
MARKER = VENV / ".dependances-installees"
MIN_PYTHON = (3, 10)
FIRST_PORT = 8050


def say(message: str) -> None:
    print(f"[Atlas] {message}", flush=True)


def fail(message: str) -> None:
    print(f"\n[Atlas] ERREUR : {message}\n", flush=True)
    sys.exit(1)


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_venv() -> None:
    if venv_python().exists():
        return
    say("Création de l'environnement Python (.venv)…")
    result = subprocess.run([sys.executable, "-m", "venv", str(VENV)])
    if result.returncode != 0 or not venv_python().exists():
        hint = ("\nSous Debian/Ubuntu, installer d'abord le module venv :\n    sudo apt install python3-venv"
                if sys.platform.startswith("linux") else "")
        fail("impossible de créer l'environnement virtuel." + hint)


def ensure_dependencies() -> None:
    """Installe les dépendances une seule fois ; relance l'installation si requirements.txt change."""
    wanted = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    if MARKER.exists() and MARKER.read_text().strip() == wanted:
        return
    say("Installation des bibliothèques (2 à 5 minutes la première fois, connexion Internet requise)…")
    pip = [str(venv_python()), "-m", "pip", "install", "--disable-pip-version-check"]
    subprocess.run(pip + ["--quiet", "--upgrade", "pip"])  # facultatif : un échec ici n'est pas bloquant
    if subprocess.run(pip + ["-r", str(REQUIREMENTS)]).returncode != 0:
        fail("l'installation des bibliothèques a échoué. Vérifier la connexion Internet puis relancer.")
    MARKER.write_text(wanted)


def free_port(start: int = FIRST_PORT) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    fail(f"aucun port libre entre {start} et {start + 49}.")


def open_when_ready(url: str, port: int, process: subprocess.Popen) -> None:
    for _ in range(240):  # jusqu'à 2 minutes : le premier démarrage peut reconstruire les données
        if process.poll() is not None:
            return
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                say(f"Prêt : {url}")
                say("Laisser cette fenêtre ouverte. Pour arrêter : la fermer ou appuyer sur Ctrl + C.")
                if not os.environ.get("ATLAS_SANS_NAVIGATEUR"):
                    webbrowser.open(url)
                return
        time.sleep(0.5)


def main() -> None:
    if sys.version_info < MIN_PYTHON:
        fail(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} ou plus récent est requis "
             f"(version détectée : {sys.version.split()[0]}).\nTélécharger Python : https://www.python.org/downloads/")
    os.chdir(ROOT)
    ensure_venv()
    ensure_dependencies()
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    say("Démarrage de l'atlas…")
    process = subprocess.Popen([str(venv_python()), "app.py", "--port", str(port), *sys.argv[1:]], cwd=ROOT)
    threading.Thread(target=open_when_ready, args=(url, port, process), daemon=True).start()
    try:
        code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        code = 0
        say("Arrêté.")
    sys.exit(code)


if __name__ == "__main__":
    main()
