#!/usr/bin/env bash
# Exécute les six exemples de cfd-dispersion, dans l'ordre.
#
#     bash RUN_EXEMPLE.sh              # tout
#     bash RUN_EXEMPLE.sh -n 200       # plus vite, moins de tirages
#
# Les sorties vont dans SORTIE/ (figures PNG et CSV).
set -euo pipefail

ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ICI"

# Le script console de pip embarque le chemin de l'interpréteur, ce qui casse
# dès que celui-ci bouge (image Apptainer, venv déplacé). `python3 -m` marche
# toujours ; on s'en sert aussi pour lancer les exemples.
PY="${CFD_DISPERSION_PYTHON:-python3}"

if ! "$PY" -c "import cfd_plot" 2>/dev/null; then
    echo "cfd-plot n'est pas installé : les figures exigent ce paquet."
    echo "    pip install -e tools/cfd-plot"
    echo "Le calcul (lois, tirage, validation) tournerait, mais pas les exemples."
    exit 1
fi

echo "== 1. Tirage des lois =========================================="
"$PY" 01_tirage.py "$@"

echo
echo "== 2. Monte-Carlo : validation et synthèse ====================="
"$PY" 02_monte_carlo.py "$@"

echo
echo "== 3. Polaires dispersées via cfd_plot.batch_plot =============="
"$PY" 03_polaire_batch_plot.py "$@"

echo
echo "== 4. Bandes, corrélation, remplissages ========================"
"$PY" 04_bande_et_correlation.py "$@"

echo
echo "== 5. Modele croise : listes d'axes et tableau large ==========="
"$PY" 05_modele_croise.py "$@"

echo
echo "== 6. Figures de tirage, point de vol par point de vol =========="
# Celui-ci écrit 240 figures (4 PDV × 15 tirages × 4 figures) : compter une
# minute sur toutes les mèches, quelques-unes sur un seul cœur.
"$PY" 06_tirages_par_pdv.py "$@"

echo
echo "Terminé. Résultats dans $ICI/SORTIE/"
