#!/usr/bin/env bash
# Régénère les données factices et toutes les figures (PLANCHES/ : prêtes à coller dans
# Fusee_3DOF_base_aero.pptx, qui se modifie ensuite directement dans PowerPoint).
#
#   bash construire.sh            # PYTHON=… pour un autre interpréteur, JOBS=… pour les tracés
#
# Prérequis : cfd-doe, cfd-plot et cfd-atm installés dans l'interpréteur (pip install -e),
# pandas.
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"

echo "== 1/2 données : DOE, CFD factice, tables carrées, incrément"
"$PY" generer_donnees.py

echo "== 2/2 tracés : tracer_base_aero.py (cfd-plot)"
"$PY" tracer_base_aero.py DONNEES/tables_carrees.csv DONNEES/increment_dzca.csv \
    --sortie SORTIE/FIGURES --planches PLANCHES --jobs "${JOBS:-4}"
