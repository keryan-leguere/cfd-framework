  #!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  test_gestion_timestamps.sh — Démonstration de la bibliothèque gestion_timestamps
# ═══════════════════════════════════════════════════════════════════════════════

# Charger les bibliothèques
if [[ -z "${CFD_FRAMEWORK}" ]]; then
  echo "ERREUR: Variable CFD_FRAMEWORK non définie" >&2
  exit 1
fi

source "${CFD_FRAMEWORK}/lib/format.sh"
source "${CFD_FRAMEWORK}/lib/gestion_timestamps.sh"


# ══════════════════════════════════════════════════════════════════════════════
#  DÉMONSTRATION
# ══════════════════════════════════════════════════════════════════════════════

title "=== Test gestion_timestamps.sh ==="
_result "Timestamp généré: $(ts_generer)"

test_dir=$(mktemp -d)
_info "Répertoire test: $test_dir"

rep1=$(ts_creer_repertoire "$test_dir" "TEST")
# On s'attend à un repertoire $test_dir/TEST_timestamp, crée et un retourné par la fonction
_result "Répertoire créé: $rep1"

nom_base=$(ts_supprimer_timestamp "$(basename "$rep1")")
# On s'attend à obtenir à nouveau TEST
_result "Nom sans timestamp: $nom_base"

ts_extrait=$(ts_extraire_timestamp "$rep1")
# On s'attend à obtenir à nouveau $(ts_generer)
_result "Timestamp extrait: $ts_extrait"

rm -rf "$test_dir"
boite_result "Tests terminés"