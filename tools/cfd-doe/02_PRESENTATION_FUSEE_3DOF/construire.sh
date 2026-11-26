#!/usr/bin/env bash
# Reconstruit toute la présentation : données factices → tracés → .pptx.
#
#   bash construire.sh            # PYTHON=… pour un autre interpréteur, JOBS=… pour les tracés
#
# Prérequis : cfd-doe, cfd-plot et cfd-atm installés dans l'interpréteur (pip install -e),
# pandas ; Node.js pour le deck (pptxgenjs, installé dans deck/ au premier passage).
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"

echo "== 1/3 données : DOE, CFD factice, tables carrées, incrément"
"$PY" generer_donnees.py

echo "== 2/3 tracés : tracer_base_aero.py (cfd-plot)"
"$PY" tracer_base_aero.py DONNEES/tables_carrees.csv DONNEES/increment_dzca.csv \
    --sortie SORTIE/FIGURES --planches PLANCHES --jobs "${JOBS:-4}"

echo "== 3/3 présentation"
cd deck
[ -d node_modules ] || npm install --silent
node deck.js
