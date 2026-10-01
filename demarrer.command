#!/bin/sh
# Atlas du tissu productif agricole du Togo - lanceur macOS.
# Double-clic dans le Finder. Au premier lancement : clic droit puis Ouvrir.
cd "$(dirname "$0")" || exit 1

PY=""
for candidate in python3 python3.12 python3.11 python3.10 python; do
    if command -v "$candidate" >/dev/null 2>&1 \
        && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
        PY="$candidate"
        break
    fi
done

if [ -z "$PY" ]; then
    echo
    echo "Python 3.10 ou plus recent est introuvable."
    echo "Installer Python depuis https://www.python.org/downloads/ puis relancer."
    echo
    printf "Appuyer sur Entree pour fermer. "
    read _
    exit 1
fi

"$PY" lancer.py "$@"
status=$?
if [ $status -ne 0 ]; then
    echo
    printf "Appuyer sur Entree pour fermer. "
    read _
fi
exit $status
