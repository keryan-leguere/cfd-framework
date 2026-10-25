#!/usr/bin/env bash
# Lance l'exemple de bout en bout.
#
# On appelle « python -m cfd_aq » et jamais le script de console « cfd-aq » :
# pip grave sys.executable dans le shebang du script de console, ce qui est
# faux dès que Python vient d'une image Apptainer chargée par « module load »,
# d'un venv déplacé, ou d'un chemin d'interpréteur plus long que les 127
# octets que le noyau accepte dans un « #! ».
#
# CFD_AQ_PYTHON=/chemin/vers/python ./RUN_EXEMPLE.sh pour forcer l'interpréteur.
set -euo pipefail
cd "$(dirname "$0")"
PY="${CFD_AQ_PYTHON:-python3}"

echo "== Validation du cas =="
"$PY" -m cfd_aq check CAS_VOILURE.yaml

echo
echo "== Traînée du cas complet =="
"$PY" -m cfd_aq run CAS_VOILURE.yaml

echo
echo "== Budget de traînée =="
"$PY" 01_budget_trainee.py

echo
echo "== Arête contre deux marches =="
"$PY" 02_arete_contre_deux_marches.py

echo
echo "== Figures =="
"$PY" -m cfd_aq figures FIGURES
