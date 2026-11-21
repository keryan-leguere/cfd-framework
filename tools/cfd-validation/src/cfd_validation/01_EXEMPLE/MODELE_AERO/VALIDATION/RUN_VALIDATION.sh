#!/usr/bin/env bash
# Lance tous les tests de validation du modèle, puis écrit le récapitulatif.
#
#   bash RUN_VALIDATION.sh                  # tous les tests
#   bash RUN_VALIDATION.sh --sans-figures   # options transmises à chaque test
#
# Le module f2py doit être construit avant (l'utilisateur le fait lui-même) :
#   cd ../PYTHON && bash construire.sh
#
# Pièces : SORTIE/<TEST>/ (celles du test), SORTIE/<TEST>.txt (sa sortie terminal),
# SORTIE/RECAP.txt (une ligne par test, conforme ou non, et le pourcentage).
# Code de retour : 0 si tous les tests sont conformes, 1 sinon.
#
# L'interpréteur se choisit par CFD_VALIDATION_PYTHON (défaut python3).
set -uo pipefail

ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${CFD_VALIDATION_PYTHON:-python3}"
SORTIE="$ICI/SORTIE"

# Un test par ligne : répertoire | script | options propres au test.
# Contrat d'un script de test : il accepte --sortie DIR, y écrit resume.json, et
# rend 0 (conforme), 2 (non conforme) ou autre chose (il a échoué).
TESTS=(
    "01_LECTURE_TABLES|01_lecture_tables.py|--combinaisons"
)

rm -rf "$SORTIE"
mkdir -p "$SORTIE"
bilans=()
for t in "${TESTS[@]}"; do
    IFS='|' read -r rep script options <<< "$t"
    printf '== %-22s ' "$rep"
    debut=$SECONDS
    # shellcheck disable=SC2086  # options : plusieurs mots voulus
    "$PY" "$ICI/$rep/$script" $options --sortie "$SORTIE/$rep" "$@" > "$SORTIE/$rep.txt" 2>&1
    code=$?
    case $code in
        0) etat="conforme" ;;
        2) etat="NON CONFORME" ;;
        *) etat="ERREUR (code $code)" ;;
    esac
    echo "$etat ($((SECONDS - debut)) s) — SORTIE/$rep.txt"
    bilans+=("$rep:$code")
done

echo
"$PY" "$ICI/recapituler.py" "$SORTIE" "${bilans[@]}"
