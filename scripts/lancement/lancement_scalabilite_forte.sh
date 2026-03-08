#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  lancement_scalabilite_forte.sh — Lancement de l'analyse de scalabilité forte
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Ce script lance une campagne d'analyse de scalabilité forte en exécutant
#  le même cas pour différentes configurations de nombre de cœurs. Les résultats
#  permettent d'évaluer l'efficacité parallèle (speedup, efficacité) en fonction
#  du nombre de processus.
#
#  Usage:
#    ./lancement_scalabilite_forte.sh --coeurs "1 2 4 8" [OPTIONS]
#
#  Arguments obligatoires:
#    --coeurs <LISTE>        Liste des nombres de cœurs à tester (ex: "1 2 4 8")
#
#  Options:
#    -h, --help              Afficher cette aide
#    --dry-run               Afficher les actions sans exécuter les calculs
#    --queue <NOM>           Nom de la queue / partition (scheduler)
#    --init                  Effectuer l'initialisation avant la campagne
#
#  Variables d'environnement (optionnelles):
#    CFD_FRAMEWORK           Chemin vers le framework CFD
#
#  Auteur : KL
#  Licence : MIT
# ═══════════════════════════════════════════════════════════════════════════════

set -Eeuo pipefail
IFS=$'\n\t'

# ══════════════════════════════════════════════════════════════════════════════
#  🔧 RÉSOLUTION DE CFD_FRAMEWORK
# ══════════════════════════════════════════════════════════════════════════════

if [[ -z "${CFD_FRAMEWORK:-}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  CFD_FRAMEWORK="$(cd "${SCRIPT_DIR}/../.." && pwd)"
  export CFD_FRAMEWORK
fi

if [[ ! -d "$CFD_FRAMEWORK" ]]; then
  echo "ERREUR: Répertoire CFD_FRAMEWORK introuvable: $CFD_FRAMEWORK" >&2
  exit 1
fi

# ══════════════════════════════════════════════════════════════════════════════
#  📚 CHARGEMENT DES BIBLIOTHÈQUES
# ══════════════════════════════════════════════════════════════════════════════

source "${CFD_FRAMEWORK}/lib/format.sh"

# ══════════════════════════════════════════════════════════════════════════════
#  ❓ FONCTION D'AIDE
# ══════════════════════════════════════════════════════════════════════════════

usage() {
  echo ""
  echo "╔═══════════════════════════════════════════════════════════════════════════════╗"
  echo "║     📈 lancement_scalabilite_forte.sh — Analyse de scalabilité forte          ║"
  echo "╚═══════════════════════════════════════════════════════════════════════════════╝"
  echo ""
  printf "%bUSAGE:%b\n" "$BOLD" "$RESET"
  echo "  $0 --coeurs \"<N1> [N2] ...\" [OPTIONS]"
  echo ""
  printf "%bDESCRIPTION:%b\n" "$BOLD" "$RESET"
  echo "  Lance une campagne de calcul pour mesurer la scalabilité forte en faisant"
  echo "  varier le nombre de cœurs. Chaque valeur de la liste correspond à un run."
  echo ""
  printf "%bARGUMENTS OBLIGATOIRES:%b\n" "$BOLD" "$RESET"
  echo "  --coeurs <LISTE>        Liste des nombres de cœurs (ex: \"1 2 4 8\" ou \"1 4 16\")"
  echo ""
  printf "%bOPTIONS:%b\n" "$BOLD" "$RESET"
  echo "  -h, --help              Afficher cette aide"
  echo "  --dry-run               Simuler sans lancer les calculs"
  echo "  --queue <NOM>           Queue / partition à utiliser (scheduler)"
  echo "  --init                  Effectuer l'initialisation avant la campagne"
  echo ""
  printf "%bEXEMPLES:%b\n" "$BOLD" "$RESET"
  echo "  # Lancer avec 1, 2, 4 et 8 cœurs"
  echo "  $0 --coeurs \"1 2 4 8\""
  echo ""
  echo "  # Avec queue et initialisation"
  echo "  $0 --coeurs \"1 4 16 32\" --queue normal --init"
  echo ""
  echo "  # Vérifier les paramètres sans exécuter"
  echo "  $0 --coeurs \"1 2 4\" --dry-run"
  echo ""
}

# ══════════════════════════════════════════════════════════════════════════════
#  🔧 PARSING DES ARGUMENTS
# ══════════════════════════════════════════════════════════════════════════════

COEURS=()
DRY_RUN=false
QUEUE=""
INIT=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --coeurs)
      if [[ $# -lt 2 ]]; then
        _error "Option --coeurs requiert un argument (ex: \"1 2 4 8\")"
        exit 1
      fi
      # Convertir la chaîne en tableau (nombres séparés par espaces)
      # IFS temporairement à l'espace car le script utilise IFS=$'\n\t' en tête
      IFS=' ' read -ra COEURS <<< "$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --queue)
      if [[ $# -lt 2 ]]; then
        _error "Option --queue requiert un argument"
        exit 1
      fi
      QUEUE="$2"
      shift 2
      ;;
    --init)
      INIT=true
      shift
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

if [[ ${#COEURS[@]} -eq 0 ]]; then
  _error "La liste --coeurs est obligatoire et ne peut pas être vide"
  echo "Exemple: $0 --coeurs \"1 2 4 8\"" >&2
  exit 1
fi

# Vérifier que chaque élément est un entier strictement positif
for n in "${COEURS[@]}"; do
  if [[ ! "$n" =~ ^[0-9]+$ ]] || [[ "$n" -lt 1 ]]; then
    _error "Valeur de cœurs invalide: '$n' (attendu: entier >= 1)"
    exit 1
  fi
done

# ══════════════════════════════════════════════════════════════════════════════
#  🎯 RÉSUMÉ DES OPTIONS
# ══════════════════════════════════════════════════════════════════════════════

_info "Scalabilité forte — Cœurs: ${COEURS[*]}"
[[ -n "$QUEUE" ]]    && _info "Queue: $QUEUE"
[[ "$DRY_RUN" == true ]] && _note "Mode dry-run activé"
[[ "$INIT" == true ]]    && _info "Initialisation demandée"

# ══════════════════════════════════════════════════════════════════════════════
#  🚀 BANNIÈRE ET CORPS (à compléter par l'utilisateur)
# ══════════════════════════════════════════════════════════════════════════════
#  Variables disponibles après parsing:
#    COEURS[]   — tableau des nombres de cœurs (ex: (1 2 4 8))
#    DRY_RUN    — true/false
#    QUEUE      — chaîne (vide si non fourni)
#    INIT       — true/false
# ══════════════════════════════════════════════════════════════════════════════

boite_result "Lancement analyse scalabilité forte"

# --- Corps à compléter ---
echo ""

# --- Fin ---
echo ""
_result "Campagne scalabilité forte terminée"

exit 0
