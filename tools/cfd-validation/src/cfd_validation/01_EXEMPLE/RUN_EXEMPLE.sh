#!/usr/bin/env bash
# Exemple complet : tables factices, trois scénarios en Python, puis la ligne de commande.
#
#   bash RUN_EXEMPLE.sh
#
# L'interpréteur se choisit par CFD_VALIDATION_PYTHON (défaut python3). On passe par
# « python -m cfd_validation », jamais par le script console : il survit à un venv
# déplacé ou à un Python servi depuis une image Apptainer.
set -euo pipefail

ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${CFD_VALIDATION_PYTHON:-python3}"
cd "$ICI"

echo "== 1. API Python : trois scénarios (identique, arrondi, regression)"
"$PY" 01_test_integration.py

echo
echo "== 2. Grande table : 10 entrées, 15 sorties, 3 000 cas"
"$PY" 02_grande_table.py

echo
echo "== 3. Ligne de commande, sur les tables écrites par l'étape 1"
set +e
"$PY" -m cfd_validation integration \
    SORTIE_INTEGRATION/DONNEES/reference.csv \
    SORTIE_INTEGRATION/DONNEES/test_regression.csv \
    --config INTEGRATION.yaml \
    --sortie SORTIE_INTEGRATION/cli_regression --sans-figures --lignes 10
code=$?
set -e
echo
echo "Code de retour : $code (0 conforme, 1 erreur d'entrée, 2 non conforme — 2 attendu ici)"
