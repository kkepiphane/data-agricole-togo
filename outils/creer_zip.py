"""Crée dist/atlas-agricole-togo.zip, l'archive à remettre.

    python outils/creer_zip.py

L'archive exclut l'environnement virtuel, les caches et les exports bruts redondants, et conserve
le droit d'exécution des lanceurs macOS/Linux (perdu par l'outil de compression de Windows).
"""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "atlas-agricole-togo"
EXCLUDED_DIRS = {".venv", "venv", "__pycache__", ".claude", ".git", ".vscode", ".idea", "dist"}
EXCLUDED_RAW_SUFFIXES = {".kml", ".xlsx", ".json", ".zip"}  # seuls les CSV de data/raw/ sont lus
EXECUTABLES = {"demarrer.sh", "demarrer.command"}


def included(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if EXCLUDED_DIRS & set(rel.parts) or path.suffix == ".pyc":
        return False
    if rel.parts[:2] == ("data", "raw") and len(rel.parts) == 3 and path.suffix.lower() in EXCLUDED_RAW_SUFFIXES:
        return False
    return not (rel.parts[:3] == ("data", "raw", "limites_admin") and path.suffix == ".zip")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    out = ROOT / "dist" / f"{NAME}.zip"
    out.parent.mkdir(exist_ok=True)
    files = sorted(p for p in ROOT.rglob("*") if p.is_file() and included(p))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in files:
            info = zipfile.ZipInfo.from_file(path, f"{NAME}/{path.relative_to(ROOT).as_posix()}")
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3  # Unix : permet de transporter les droits d'accès
            mode = 0o755 if path.name in EXECUTABLES else 0o644
            info.external_attr = (0o100000 | mode) << 16
            z.writestr(info, path.read_bytes())
    print(f"{out}  —  {len(files)} fichiers, {out.stat().st_size / 1e6:.1f} Mo")


if __name__ == "__main__":
    main()
