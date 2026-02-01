#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  deplacer_resultats.sh — Déplacement des résultats de 02_PARAMS/CONFIG/ vers 08_RESULTAT/CONFIG
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Ce script permet de cp/mv les cas-tests présents dans 02_PARAMS/CONFIG/ vers 08_RESULTAT/CONFIG
#  Les cas-tests ont tous le même format à savoir $ADAPTATEUR_$VERSION_$CASE_NAME_$TIMESTAMP
#  La standardisation consiste à garder uniquement le $CASE_NAME. 
#  
#  Pour chaque cas-test dans 02_PARAMS/CONFIG/, on va:
#  1. Extraire le $CASE_NAME
#  2. Regarder si le cas-test existe déjà dans 08_RESULTAT/CONFIG/
#  3. Si le cas-test n'existe pas, on le mv dans 08_RESULTAT/CONFIG/
#  4. Si le cas-test existe alors:
#    - l'option --append est spécifiée, au quel cas on va renommer le cas-test en $CASE_NAME_$TIMESTAMP
#    - l'option --force est spécifiée, au quel cas on va écraser le cas-test existant (donc rm -rf du cas puis cp/mv)
#    - Aucune de ces options n'est spécifiée, on va afficher un message interactif à l'utilisateur pour choisir quoi faire
#      -> Option 1: Append le cas-test existant avec le timestamp
#      -> Option 2: Écraser le cas-test existant
#      -> Option 3: Annuler l'opération
#  5. Si l'option --un-safe est spécifée, on utilise "mv" à la place de "cp -a".
#
#  Usage:
#    ./deplacer_resultats.sh --config <CONFIG> [OPTIONS]
#
#  Options:
#    -h, --help              Afficher cette aide
#    --config <CONFIG>       Configuration à déplacer (ex: BASELINE)
#    --append                Append le cas-test existant avec le timestamp
#    --force                 Écraser le cas-test existant
#    --un-safe               Utiliser "mv" à la place de "cp -a"
#
#  Variables d'environnement:
#    CFD_FRAMEWORK           Chemin vers le framework CFD
#
#  Auteur : KL
#  Licence : MIT
# ═══════════════════════════════════════════════════════════════════════════════

set -Euo pipefail
IFS=$'\n\t'

# ══════════════════════════════════════════════════════════════════════════════
#  🔧 RÉSOLUTION DE CFD_FRAMEWORK
# ══════════════════════════════════════════════════════════════════════════════

# Résoudre CFD_FRAMEWORK si non défini
if [[ -z "${CFD_FRAMEWORK:-}" ]]; then
  # Essayer depuis le chemin du script
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  CFD_FRAMEWORK="$(cd "${SCRIPT_DIR}/../.." && pwd)"
  export CFD_FRAMEWORK
fi

# Vérifier que CFD_FRAMEWORK existe
if [[ ! -d "$CFD_FRAMEWORK" ]]; then
  echo "ERREUR: Répertoire CFD_FRAMEWORK introuvable: $CFD_FRAMEWORK" >&2
  exit 1
fi

# ══════════════════════════════════════════════════════════════════════════════
#  📚 CHARGEMENT DES BIBLIOTHÈQUES
# ══════════════════════════════════════════════════════════════════════════════

source "${CFD_FRAMEWORK}/lib/format.sh"
source "${CFD_FRAMEWORK}/lib/gestion_timestamps.sh"
source "${CFD_FRAMEWORK}/lib/utils.sh"

# ══════════════════════════════════════════════════════════════════════════════
#  ❓ FONCTION D'AIDE
# ══════════════════════════════════════════════════════════════════════════════

usage() {
  echo ""
  echo "╔═══════════════════════════════════════════════════════════════════════════════╗"
  echo "║          📦 deplacer_resultats.sh — Archivage des résultats CFD              ║"
  echo "╚═══════════════════════════════════════════════════════════════════════════════╝"
  echo ""
  printf "%bUSAGE:%b\n" "$BOLD" "$RESET"
  echo "  $0 [OPTIONS] <SOURCE_DIRECTORY> <DESTINATION_DIRECTORY>"
  echo "  cfd-archiver [OPTIONS] <SOURCE_DIRECTORY> <DESTINATION_DIRECTORY>"
  echo ""
  printf "%bDESCRIPTION:%b\n" "$BOLD" "$RESET"
  echo "  Déplace ou copie les cas-tests depuis 02_PARAMS/CONFIG/ vers 08_RESULTAT/CONFIG/"
  echo "  Les cas-tests suivent le format: \${ADAPTATEUR}_V\${VERSION}_\${CASE_NAME}_\${TIMESTAMP}"
  echo "  Le script standardise en conservant uniquement \${CASE_NAME}"
  echo ""
  printf "%bARGUMENTS:%b\n" "$BOLD" "$RESET"
  echo "  SOURCE_DIRECTORY        Répertoire source contenant les runs (ex: 02_PARAMS/BASELINE)"
  echo "  DESTINATION_DIRECTORY   Répertoire de destination (ex: 08_RESULTAT/BASELINE)"
  echo ""
  printf "%bOPTIONS:%b\n" "$BOLD" "$RESET"
  echo "  -h, --help              Afficher cette aide"
  echo "  --append                Ajouter le timestamp si le cas existe déjà"
  echo "  --force                 Écraser le cas existant sans confirmation"
  echo "  --un-safe               Utiliser 'mv' au lieu de 'cp -a' (mode déplacement)"
  echo ""
  printf "%bVARIABLES D'ENVIRONNEMENT:%b\n" "$BOLD" "$RESET"
  echo "  CFD_FRAMEWORK           Chemin vers le framework CFD"
  echo "  ADAPTATEUR              Adaptateur utilisé (défaut: OF)"
  echo ""
  printf "%bEXEMPLES:%b\n" "$BOLD" "$RESET"
  echo "  # Copier les résultats (mode safe par défaut)"
  echo "  cfd-archiver 02_PARAMS/BASELINE 08_RESULTAT/BASELINE"
  echo ""
  echo "  # Déplacer les résultats (mode unsafe)"
  echo "  cfd-archiver --un-safe 02_PARAMS/ANGLE_INCIDENCE 08_RESULTAT/ANGLE_INCIDENCE"
  echo ""
  echo "  # Écraser les cas existants sans confirmation"
  echo "  cfd-archiver --force 02_PARAMS/BASELINE 08_RESULTAT/BASELINE"
  echo ""
  echo "  # Ajouter le timestamp aux cas existants"
  echo "  cfd-archiver --append 02_PARAMS/BASELINE 08_RESULTAT/BASELINE"
  echo ""
}

# ══════════════════════════════════════════════════════════════════════════════
#  🔧 ARGUMENT PARSING
# ══════════════════════════════════════════════════════════════════════════════

APPEND=false
FORCE=false
UNSAFE=false

POSITIONAL_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --append)
      APPEND=true
      shift
      ;;
    --force)
      FORCE=true
      shift
      ;;
    --un-safe)
      UNSAFE=true
      shift
      ;;
    -*)
      _error "Unknown option: $1"
      echo "Use -h or --help for help" >&2
      exit 1
      ;;
    *)
      POSITIONAL_ARGS+=("$1")
      shift
      ;;
  esac
done

# ─────────────────────────────────────────────────────────────────────────────
# Positional arguments validation
# ─────────────────────────────────────────────────────────────────────────────

if [[ ${#POSITIONAL_ARGS[@]} -ne 2 ]]; then
  _error "Expected SOURCE_DIRECTORY and DESTINATION_DIRECTORY"
  _error "Usage: $0 [options] <SOURCE_DIRECTORY> <DESTINATION_DIRECTORY>" >&2
  usage
  exit 1
fi

SOURCE_DIRECTORY="${POSITIONAL_ARGS[0]}"
DESTINATION_DIRECTORY="${POSITIONAL_ARGS[1]}"

# ══════════════════════════════════════════════════════════════════════════════
#  🔌 CHARGEMENT DE L'ADAPTATEUR
# ══════════════════════════════════════════════════════════════════════════════

ADAPTATEUR="${ADAPTATEUR:-OF}"
_info "Chargement de l'adaptateur: $ADAPTATEUR"

# Charger l'adaptateur (convention: essayer ${adaptateur}/adaptateur.sh puis ${adaptateur}.sh)
adaptateur_path="${CFD_FRAMEWORK}/adaptateurs/${ADAPTATEUR}/adaptateur.sh"
if [[ ! -f "$adaptateur_path" ]]; then
  adaptateur_path="${CFD_FRAMEWORK}/adaptateurs/${ADAPTATEUR}.sh"
fi

if [[ ! -f "$adaptateur_path" ]]; then
  _error "Adaptateur introuvable: $ADAPTATEUR"
  _error "Chemin recherché: $adaptateur_path"
  exit 1
fi

source "$adaptateur_path"

# Vérifier l'installation de l'adaptateur
if ! adapt_verifier_installation; then
  _error "Échec de vérification de l'adaptateur $(adapt_nom)"
  exit 1
fi

_info "Adaptateur $(adapt_nom) chargé et vérifié"


deplacer_one_test_case() {
    local SRC_CAS_TEST="$1"          # 02_PARAMS/BASELINE/OF_V13_CAS_1_20260126_143052
    local DESTINATION_DIRECTORY="$2" # 08_RESULTAT/BASELINE

    # 1. Vérifier source existe
    [[ -d "$SRC_CAS_TEST" ]] || die "Source inexistante : $SRC_CAS_TEST"
    
    # 2. Extraire nom sans timestamp
    local BASENAME_WITH_TIMESTAMP=$(basename "$SRC_CAS_TEST") # OF_V13_CAS_1_20260126_143052
    local BASENAME_WITHOUT_ADAPTATEUR=$(echo "$BASENAME_WITH_TIMESTAMP" | sed -E 's/^$(adapt_nom)_V$(adapt_version)_//') # CAS_1_20260126_143052 --> TODO Use adaptateur here
    local CASE_NAME=$(ts_supprimer_timestamp "$BASENAME_WITHOUT_ADAPTATEUR") # CAS_1

    # 3. Vérifier que le cas-test existe déjà dans 08_RESULTAT/${CONFIG}
    local DEST_CAS_TEST="${DESTINATION_DIRECTORY}/${CASE_NAME}"
    if [[ -d "$DEST_CAS_TEST" ]]; then
        _warn "Le cas-test existe déjà dans le répertoire de destination: $DESTINATION_DIRECTORY"
        if [[ "$APPEND" == true ]]; then
            _info "Append le cas-test existant avec le timestamp"
            DEST_CAS_TEST=$DESTINATION_DIRECTORY/$BASENAME_WITHOUT_ADAPTATEUR
        elif [[ "$FORCE" == true ]]; then
            _warn "Écraser le cas-test existant"
            _debug "Run command: rm -rf \"$DEST_CAS_TEST\""
            rm -rf "$DEST_CAS_TEST"
        else
            action=$(choisir_option "Que faire avec le cas-test existant?" \
            "Append" \
            "Overwrite" \
            "Cancel" \
            ) || exit 1
            case "$action" in
                "Append")
                    _info "Append le cas-test existant avec le timestamp"
                    DEST_CAS_TEST=$DESTINATION_DIRECTORY/$BASENAME_WITHOUT_ADAPTATEUR
                    ;;
                "Overwrite")
                    _warn "Écraser le cas-test existant"
                    _debug "Run command: rm -rf \"$DEST_CAS_TEST\""
                    rm -rf "$DEST_CAS_TEST"
                    ;;
                "Cancel")
                    _error "Opération annulée"
                    continue
                    ;;
            esac
        fi
    fi

    # 4. Déplacer le cas-test
_info "Déplacement : $SRC_CAS_TEST -> $DEST_CAS_TEST"

if [[ "$UNSAFE" == true ]]; then
    _debug "Run command: mv \"$SRC_CAS_TEST\" \"$DEST_CAS_TEST\""
    mv "$SRC_CAS_TEST" "$DEST_CAS_TEST"
else
    _debug "Run command: cp -a \"$SRC_CAS_TEST\" \"$DEST_CAS_TEST\""
    cp -a "$SRC_CAS_TEST" "$DEST_CAS_TEST"
fi


    
    _result "Résultats archivés : $DEST_CAS_TEST"

    separator
}

deplacer_resultats() {

    titre_archivage

    if [[ ! -d "$SOURCE_DIRECTORY" ]]; then
        _error "Le répertoire de configuration n'existe pas: $SOURCE_DIRECTORY"
        exit 1
    fi

    if [[ ! -d "$DESTINATION_DIRECTORY" ]]; then
        _warn "Le répertoire de destination n'existe pas: $DESTINATION_DIRECTORY"
        _debug "Run command: mkdir -p \"$DESTINATION_DIRECTORY\""
        mkdir -p "$DESTINATION_DIRECTORY"
    fi

    # 1. Lister les cas-tests dans 02_PARAMS/CONFIG/
    declare -a LIST_CASE_TESTS_TO_MOVE=()

    LIST_CASE_TESTS_TO_MOVE=($(find "$SOURCE_DIRECTORY" -maxdepth 1 -type d -name "$(adapt_nom)_V$(adapt_version)_*"))

    _info "Liste des cas-tests à déplacer vers $DESTINATION_DIRECTORY"
    for CASE_TEST in "${LIST_CASE_TESTS_TO_MOVE[@]}"; do
        _bullet "$CASE_TEST"
    done

    separator_eq

    for CASE_TEST in "${LIST_CASE_TESTS_TO_MOVE[@]}"; do
        h1 "Déplacement du cas-test $CASE_TEST"
        deplacer_one_test_case $CASE_TEST $DESTINATION_DIRECTORY
    done

    boite_result "Résultats archivés"
}

deplacer_resultats "$@"