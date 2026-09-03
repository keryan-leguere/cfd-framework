#!/usr/bin/env bash
# Exécute les trois exemples de cfd-dispersion, dans l'ordre.
#
#     bash RUN_EXEMPLE.sh
#
# Les sorties vont dans SORTIE/ (figures PNG et CSV).
set -euo pipefail

ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ICI"

# Le script console de pip embarque le chemin de l'interpréteur, ce qui casse
# dès que celui-ci bouge (image Apptainer, venv déplacé). `python3 -m` marche
# toujours ; on s'en sert aussi pour lancer les exemples.
PY="${CFD_DISPERSION_PYTHON:-python3}"

echo "== 1. Tirage des lois =========================================="
"$PY" 01_tirage.py "$@"

echo
echo "== 2. Monte-Carlo : validation et synthèse ====================="
"$PY" 02_monte_carlo.py "$@"

echo
echo "== 3. Polaires dispersées via cfd_plot.batch_plot =============="
if "$PY" -c "import cfd_plot" 2>/dev/null; then
    "$PY" 03_polaire_batch_plot.py "$@"
else
    echo "cfd-plot n'est pas installé — étape ignorée."
    echo "    pip install -e tools/cfd-plot"
fi

echo
echo "Terminé. Résultats dans $ICI/SORTIE/"
