#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  ANGLE_INCIDENCE.sh — Lance une étude paramétrique sur l'angle d'incidence
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Ce script convertit les values du cas du yaml en un .metadata dans le repertoire
#  du calcul pour la configuration ANGLE_INCIDENCE.
#  Les balises à remplacées sont:
#  - @U_ENTREE@
#  - @V_ENTREE@
#  Le yaml prends l'incidence alpha, qu'il faut convertir
#
#  Usage:
#    ./ANGLE_INCIDENCE.sh <YAML_PATH> <CONFIG_FILE>
#
#  Prérequis:
#    - Variable CFD_FRAMEWORK définie
#    - yq installé (pour gestion_config.sh)
#
#  Auteur : KL
#  Licence : MIT
# ═══════════════════════════════════════════════════════════════════════════════

set -Euo pipefail
IFS=$'\n\t'

# ══════════════════════════════════════════════════════════════════════════════
#  🔧 RÉSOLUTION DES CHEMINS
# ══════════════════════════════════════════════════════════════════════════════

YAML_PATH="${1}"
CONFIG_FILE="${2}"
LOCAL_CASE_DIR="${3}"

if [[ -z "${YAML_PATH:-}" ]]; then
  echo "ERREUR: YAML_PATH non définie" >&2
  exit 1
fi
if [[ -z "${CONFIG_FILE:-}" ]]; then
  echo "ERREUR: CONFIG_FILE non définie" >&2
  exit 1
fi
if [[ -z "${LOCAL_CASE_DIR:-}" ]]; then
  echo "ERREUR: LOCAL_CASE_DIR non définie" >&2
  exit 1
fi

# ══════════════════════════════════════════════════════════════════════════════
#  📚 CHARGEMENT DES BIBLIOTHÈQUES
# ══════════════════════════════════════════════════════════════════════════════

if [[ -z "${CFD_FRAMEWORK:-}" ]]; then
  echo "ERREUR: Variable CFD_FRAMEWORK non définie" >&2
  echo "Veuillez définir CFD_FRAMEWORK pour utiliser ce script" >&2
  exit 1
fi

source "${CFD_FRAMEWORK}/lib/format.sh"

# ══════════════════════════════════════════════════════════════════════════════
#  ❓ FONCTION D'AIDE
# ══════════════════════════════════════════════════════════════════════════════

usage() {
  cat <<EOF

╔══════════════════════════════════════════════════════════════════════════╗
║      🚀 ANGLE_INCIDENCE.sh — Étude pour la configuration ANGLE_INCIDENCE ║
╚══════════════════════════════════════════════════════════════════════════╝

${BOLD}USAGE:${RESET}
  $0 [OPTIONS]

${BOLD}DESCRIPTION:${RESET}
  Conversion des values du cas du yaml en un .metadata dans le repertoire
  du calcul pour la configuration ANGLE_INCIDENCE.

${BOLD}OPTIONS:${RESET}
  -h, --help              Afficher cette aide

${BOLD}EXEMPLES:${RESET}
  $0 <YAML_PATH> <CONFIG_FILE>
  $0 ".configurations.ANGLE_INCIDENCE.cas[0]" "02_PARAMS/config.yaml"

EOF
}

# ══════════════════════════════════════════════════════════════════════════════
#  🔄 TRAITEMENT
# ══════════════════════════════════════════════════════════════════════════════

ALPHA=$(yq -r "${YAML_PATH}.parametres.angle_incidence // 0" "$CONFIG_FILE")
U0=$(yq -r "${YAML_PATH}.parametres.U0 // 20.0" "$CONFIG_FILE")

# Calculer les composantes de vitesse
# U_ENTREE = U0 * cos(alpha)
# V_ENTREE = U0 * sin(alpha)
# (conversion degrés -> radians avec awk, forcer locale C pour point décimal)
velocities=$(LC_ALL=C awk -v u0="$U0" -v alpha="$ALPHA" '
    BEGIN {
    pi = 3.14159265358979323846
    alpha_rad = alpha * pi / 180.0
    u_entree = u0 * cos(alpha_rad)
    v_entree = u0 * sin(alpha_rad)
    printf "%.6f %.6f", u_entree, v_entree
    }
')
U_ENTREE=$(echo "$velocities" | awk '{print $1}')
V_ENTREE=$(echo "$velocities" | awk '{print $2}')

yq -i -y "${YAML_PATH}.parametres.U_ENTREE = $U_ENTREE" "$CONFIG_FILE"
yq -i -y "${YAML_PATH}.parametres.V_ENTREE = $V_ENTREE" "$CONFIG_FILE"
