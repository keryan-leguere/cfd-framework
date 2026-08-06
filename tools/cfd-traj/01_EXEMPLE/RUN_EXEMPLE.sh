#!/usr/bin/env bash
# =====================================================================
#  cfd-traj — exemple complet
#
#  Déroule la chaîne entière sur le lot de 24 trajectoires livré dans
#  TRAJECTOIRES/ : comprendre, analyser, réduire, vérifier.
#
#  Tout ce qui est produit va dans SORTIE/.
# =====================================================================
set -euo pipefail

ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ICI"

if ! command -v cfd-traj >/dev/null 2>&1; then
    echo "cfd-traj introuvable dans le PATH." >&2
    echo "Installez le paquet et sa dépendance :" >&2
    echo "    pip install -e ../../cfd-atm" >&2
    echo "    pip install -e .." >&2
    exit 1
fi

mkdir -p SORTIE

echo
echo "=== 1. Comprendre le lot ==============================================="
echo "    Statistiques, corrélations, dimension intrinsèque du nuage."
cfd-traj inspecter TRAJECTOIRES --etude ETUDE.yaml \
    --figure SORTIE/01_inspection.png \
    --csv SORTIE/01_statistiques.csv

echo
echo "=== 2. Enveloppe conditionnelle ========================================"
echo "    Le tube réellement balayé, bande de Mach par bande de Mach."
cfd-traj analyser ETUDE.yaml \
    --figure SORTIE/02_enveloppe.png \
    --csv SORTIE/02_enveloppe.csv

echo
echo "=== 3. Plan d'expériences =============================================="
echo "    Grille anisotrope par bande, coins inclus, coût en équivalents"
echo "    configuration complète. Le classeur Excel est le livrable de revue."
cfd-traj doe ETUDE.yaml \
    --sortie SORTIE/03_PLAN.csv \
    --excel SORTIE/03_PLAN.xlsx \
    --yaml SORTIE/03_PLAN.yaml \
    --figure SORTIE/03_plan.png

echo
echo "=== 4. Variante hypercube latin ========================================"
echo "    Ce qu'on emploie quand la grille tensorielle explose."
cfd-traj doe ETUDE.yaml --methode lhs \
    --sortie SORTIE/04_PLAN_lhs.csv \
    --figure SORTIE/04_plan_lhs.png

echo
echo "=== 5. Contrôle de couverture =========================================="
echo "    Rejeu de toutes les trajectoires à travers l'enveloppe finale."
echo "    Le code de retour 2 signale une couverture incomplète : c'est un"
echo "    résultat, pas une panne."
set +e
cfd-traj couverture ETUDE.yaml \
    --figure SORTIE/05_couverture.png \
    --csv SORTIE/05_hors_domaine.csv \
    --pires 5
COUVERTURE=$?
set -e
if [ "$COUVERTURE" -gt 2 ]; then
    echo "échec inattendu de la commande couverture (code $COUVERTURE)" >&2
    exit "$COUVERTURE"
fi

echo
echo "=== Fichiers produits =================================================="
ls -1 SORTIE/
