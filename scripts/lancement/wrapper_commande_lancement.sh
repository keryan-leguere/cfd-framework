#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  wrapper_commande_lancement.sh — Wrapper générique pour lancer un calcul CFD
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Ce script est un wrapper générique qui charge un adaptateur CFD et lance
#  un calcul. Il peut soit exécuter dans le répertoire actuel (--in-place),
#  soit créer une copie horodatée du cas.
#
#  Usage:
#    ./wrapper_commande_lancement.sh [OPTIONS]
#
#  Options:
#    -h, --help              Afficher cette aide
#    --adaptateur <ID>       Adaptateur à utiliser (défaut: $CFD_ADAPTATEUR ou OF)
#    --in-place              Exécuter dans le répertoire actuel
#    --dry-run               Préparer le cas sans lancer le calcul
#    --name <NOM>            Spécifier le nom du cas (remplace $CASE_NAME)
#    --new-dir-name <DIR>    Spécifier le nom complet du répertoire de calcul
#
#  Variables d'environnement:
#    CFD_FRAMEWORK           Chemin vers le framework CFD
#    CFD_ADAPTATEUR          Adaptateur à utiliser par défaut
#    CASE_NAME               Nom du cas (requis si --name non fourni)
#
#  Auteur : KL
#  Licence : MIT
# ═══════════════════════════════════════════════════════════════════════════════

set -Eeuo pipefail
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
  echo "║           🚀 wrapper_commande_lancement.sh — Lanceur CFD Générique            ║"
  echo "╚═══════════════════════════════════════════════════════════════════════════════╝"
  echo ""
  printf "%bUSAGE:%b\n" "$BOLD" "$RESET"
  echo "  $0 [OPTIONS]"
  echo "  cfd-run [OPTIONS]"
  echo ""
  printf "%bDESCRIPTION:%b\n" "$BOLD" "$RESET"
  echo "  Wrapper générique pour lancer un calcul CFD avec un adaptateur."
  echo "  Supporte la copie horodatée et le mode dry-run."
  echo ""
  printf "%bOPTIONS:%b\n" "$BOLD" "$RESET"
  echo "  -h, --help              Afficher cette aide"
  echo "  --adaptateur <ID>       Adaptateur à utiliser (défaut: \$CFD_ADAPTATEUR ou OF)"
  echo "  --in-place              Exécuter dans le répertoire actuel"
  echo "  --dry-run               Préparer le cas sans lancer le calcul"
  echo "  --name <NOM>            Spécifier le nom du cas (remplace \$CASE_NAME)"
  echo "  --new-dir-name <DIR>    Spécifier le nom complet du répertoire de calcul"
  echo ""
  printf "%bVARIABLES D'ENVIRONNEMENT:%b\n" "$BOLD" "$RESET"
  echo "  CFD_FRAMEWORK           Chemin vers le framework CFD"
  echo "  CFD_ADAPTATEUR          Adaptateur à utiliser par défaut"
  echo "  CASE_NAME               Nom du cas (requis si --name non fourni)"
  echo ""
  printf "%bEXEMPLES:%b\n" "$BOLD" "$RESET"
  echo "  # Exécuter avec adaptateur OpenFOAM dans le répertoire actuel"
  echo "  $0 --adaptateur OF --in-place"
  echo ""
  echo "  # Créer une copie horodatée et exécuter"
  echo "  export CASE_NAME=AIRFOIL"
  echo "  $0 --adaptateur OF"
  echo ""
  echo "  # Mode dry-run pour tester"
  echo "  $0 --adaptateur OF --name NACA0012 --dry-run"
  echo ""
  printf "%bADAPTATEURS DISPONIBLES:%b\n" "$BOLD" "$RESET"
  echo "  - OF      : OpenFOAM (foamRun)"
  echo "  - mock    : Adaptateur de test"
  echo ""
}

# ══════════════════════════════════════════════════════════════════════════════
#  🔧 PARSING DES ARGUMENTS
# ══════════════════════════════════════════════════════════════════════════════

ADAPTATEUR="${CFD_ADAPTATEUR:-OF}"
IN_PLACE=false
DRY_RUN=false
CASE_NAME="${CASE_NAME:-}"
NEW_DIR_NAME=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --adaptateur)
      if [[ $# -lt 2 ]]; then
        _error "Option --adaptateur requiert un argument"
        exit 1
      fi
      ADAPTATEUR="$2"
      shift 2
      ;;
    --in-place)
      IN_PLACE=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --name)
      if [[ $# -lt 2 ]]; then
        _error "Option --name requiert un argument"
        exit 1
      fi
      CASE_NAME="$2"
      shift 2
      ;;
    --new-dir-name)
      if [[ $# -lt 2 ]]; then
        _error "Option --new-dir-name requiert un argument"
        exit 1
      fi
      NEW_DIR_NAME="$2"
      shift 2
      ;;
    *)
      _error "Option inconnue: $1"
      echo "Utilisez -h ou --help pour afficher l'aide" >&2
      exit 1
      ;;
  esac
done

# ══════════════════════════════════════════════════════════════════════════════
#  ✅ VÉRIFICATIONS PRÉALABLES
# ══════════════════════════════════════════════════════════════════════════════

# Vérifier que CASE_NAME est défini si pas en mode in-place
if [[ "$IN_PLACE" == false ]] && [[ -z "$NEW_DIR_NAME" ]] && [[ -z "$CASE_NAME" ]]; then
  _error "CASE_NAME non défini"
  _error "Définissez la variable d'environnement CASE_NAME ou utilisez --name"
  exit 1
fi

# ══════════════════════════════════════════════════════════════════════════════
#  🔌 CHARGEMENT DE L'ADAPTATEUR
# ══════════════════════════════════════════════════════════════════════════════

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
_info "Version de l'adaptateur: $(adapt_version)"

# ══════════════════════════════════════════════════════════════════════════════
#  🎯 BANNIÈRE DE LANCEMENT
# ══════════════════════════════════════════════════════════════════════════════

boite_result "Lancement du calcul"

# ══════════════════════════════════════════════════════════════════════════════
#  📁 SÉLECTION DU RÉPERTOIRE D'EXÉCUTION
# ══════════════════════════════════════════════════════════════════════════════

src_dir="$PWD"
run_dir=""

if [[ "$IN_PLACE" == true ]]; then
  _info "Mode: Exécution sur place"
  run_dir="$src_dir"
else
  # Générer le timestamp
  timestamp=$(ts_generer)
  
  # Déterminer le nom du répertoire de destination
  if [[ -n "$NEW_DIR_NAME" ]]; then
    dest_name="$NEW_DIR_NAME"
    _info "Nom de répertoire personnalisé: $dest_name"
  else
    dest_name="$(adapt_nom)_V$(adapt_version)_${CASE_NAME}_${timestamp}"
    _info "Nom de répertoire généré: $dest_name"
  fi
  
  # Créer le répertoire de destination (à l'intérieur du répertoire source)
  dest_dir="${src_dir}/${dest_name}"
  
  if [[ -e "$dest_dir" ]]; then
    _error "Le répertoire de destination existe déjà: $dest_dir"
    exit 1
  fi
  
  _info "Création du répertoire: $dest_dir"
  mkdir -p "$dest_dir"
  
  # Copier les éléments définis par l'adaptateur
  _info "Copie des fichiers d'entrée..."
  
  # Récupérer la liste des éléments à copier
  mapfile -t elements < <(adapt_liste_elements_a_copier)
  
  copied_count=0
  
  for element in "${elements[@]}"; do
  # ignorer lignes vides
  [[ -z "$element" ]] && continue
  
  src_item="${src_dir}/${element}"
  dst_item="${dest_dir}/$(basename "$element")"
  
  set +e
  if [[ -e "$src_item" ]]; then
      _bullet "Copie : $element"
      cp -a "$src_item" "$dest_dir/" || { _warn "Échec de copie : $src_item"; continue; }
      ((copied_count++))
  else
      _warn "Élément introuvable (ignoré) : $src_item"
  fi
  done
  set -e
  
  _result "Copie terminée : $copied_count élément(s) copié(s)"
  
  run_dir="$dest_dir"
  yq -i -Y ".cas.timestamp = \"$timestamp\"" "${run_dir}/.metadata.yaml"
fi

if [[ ! -f "${run_dir}/.metadata.yaml" ]]; then
  touch "${run_dir}/.metadata.yaml"
  echo "{}" > "${run_dir}/.metadata.yaml"
  _warn "Le fichier .metadata.yaml n'existe pas, il a été créé"
fi
yq -i -Y ".cas.chemin = \"$run_dir\"" "${run_dir}/.metadata.yaml"
yq -i -Y ".cas.adaptateur = \"$ADAPTATEUR\"" "${run_dir}/.metadata.yaml"
finale_name=$(basename "$run_dir")
yq -i -Y ".cas.nom = \"$finale_name\"" "${run_dir}/.metadata.yaml"
_result "Répertoire d'exécution: $run_dir"

# ══════════════════════════════════════════════════════════════════════════════
#  🚀 LANCEMENT DU CALCUL
# ══════════════════════════════════════════════════════════════════════════════

# Créer le répertoire de logs
mkdir -p "${run_dir}/LOG"

# Préparer l'entrée avec l'adaptateur
_info "Préparation des fichiers d'entrée..."
if ! adapt_preparer_entree "$run_dir"; then
  _error "Échec de la préparation des fichiers d'entrée"
  exit 1
fi

# Mode dry-run ou lancement réel
if [[ "$DRY_RUN" == true ]]; then
  _note "Mode --dry-run activé: le calcul ne sera pas lancé"
  _result "Cas préparé dans: $run_dir"
  _info "Pour lancer le calcul, utilisez:"
  _info "  cd $run_dir && ${CFD_FRAMEWORK}/scripts/lancement/wrapper_commande_lancement.sh --in-place --adaptateur $ADAPTATEUR"
  exit 0
fi

_start "Lancement du calcul avec adaptateur $(adapt_nom)..."

# Lancer le calcul
if ! adapt_lancer_calcul "$run_dir" 1; then
  _error "Échec du lancement du calcul"
  exit 1
fi

_end "Calcul terminé"
_result "Résultats disponibles dans: $run_dir"

exit 0
