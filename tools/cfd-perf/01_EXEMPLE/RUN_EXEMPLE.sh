#!/usr/bin/env bash
# ---------------------------------------------------------------------
#  Exemple cfd-perf prêt à l'exécution.
#
#      ./RUN_EXEMPLE.sh
#
#  Rejoue la même étude sous les trois stratégies et écrit les figures
#  dans SORTIE/. Aucun solveur CFD requis : les mesures pilotes du
#  fichier YAML tiennent lieu de données d'entrée.
# ---------------------------------------------------------------------
set -euo pipefail

ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ICI"

ETUDE="ONERA_M6_CRUISE.yaml"
SORTIE="SORTIE"

if ! command -v cfd-perf >/dev/null 2>&1; then
    echo "cfd-perf introuvable. Installez-le d'abord :" >&2
    echo "    cd $(dirname "$ICI") && pip install -e \".[dev]\"" >&2
    exit 1
fi

mkdir -p "$SORTIE"

echo "=== 0. Contrôle du fichier d'étude et de la qualité du pilote"
cfd-perf check "$ETUDE"

echo
echo "=== 1. Efficacité — « je ne veux pas gaspiller l'allocation »"
cfd-perf run "$ETUDE" --strategy efficiency \
    --figure "$SORTIE/scalabilite_efficacite.png" -v

echo
echo "=== 2. Échéance — « il me le faut dans 4 h 30 »"
cfd-perf run "$ETUDE" --strategy deadline --deadline 4.5 \
    --figure "$SORTIE/scalabilite_echeance.png"

echo
echo "=== 3. Le plus rapide — « peu importe le coût »"
cfd-perf run "$ETUDE" --strategy fastest \
    --figure "$SORTIE/scalabilite_rapide.png"

echo
echo "Figures écrites dans $ICI/$SORTIE :"
ls -1 "$SORTIE"/*.png | sed 's/^/  /'
echo
echo "Comparez les trois réponses : même courbe, même contraintes,"
echo "seule la question posée change le nombre de cœurs recommandé."
