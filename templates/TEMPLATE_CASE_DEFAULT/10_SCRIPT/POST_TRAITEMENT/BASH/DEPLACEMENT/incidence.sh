#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  incidence.sh — Extraction des coefficients aérodynamiques par angle d'incidence
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Ce script extrait les résultats scalaires (alpha, CL, CD) depuis le fichier
#  .metadata.yaml du cas-test et les concatène dans un fichier incidence.dat.
#
#  Usage:
#    ./incidence.sh <DATA_DIR> <CASE_PATH> <CASE_NAME>
#
#  Arguments:
#    DATA_DIR      Répertoire de destination pour les résultats
#    CASE_PATH     Chemin vers le cas-test
#    CASE_NAME     Nom du cas-test
#
#  Fonctionnement:
#    1. Extrait alpha, CL, CD depuis .metadata.yaml dans CASE_PATH
#    2. Crée le fichier incidence.dat s'il n'existe pas (avec en-tête)
#    3. Ajoute ou met à jour la ligne correspondant à l'angle alpha
#    4. Trie le fichier par ordre croissant d'alpha
#
#  Format du fichier de sortie:
#    # alpha    CL          CD
#    0.0       0.01998     0.24598
#    5.0       0.54321     0.26543
#
#  Variables d'environnement:
#    CFD_FRAMEWORK    Chemin vers le framework CFD
#
#  Auteur : KL
#  Licence : MIT
# ═══════════════════════════════════════════════════════════════════════════════

set -Euo pipefail
IFS=$'\n\t'

# ──────────────────────────────────────────────────────────────────────────────────────
# 0. Charger la bibliothèque de formatage
# ──────────────────────────────────────────────────────────────────────────────────────
if [[ -z "${CFD_FRAMEWORK:-}" ]]; then
  echo "❌ ERREUR : La variable d'environnement CFD_FRAMEWORK n'est pas définie."
  echo "   Veuillez définir CFD_FRAMEWORK avant d'exécuter ce script."
  exit 1
fi

source "${CFD_FRAMEWORK}/lib/format.sh"

# ──────────────────────────────────────────────────────────────────────────────────────
# 1. Validation des arguments
# ──────────────────────────────────────────────────────────────────────────────────────
if [[ $# -lt 1 ]]; then
  die "Usage: $0 <DATA_DIR>"
fi

DATA_DIR="$1"
kv "DATA_DIR" "$DATA_DIR"

# ──────────────────────────────────────────────────────────────────────────────────────
# 2. Vérifications
# ──────────────────────────────────────────────────────────────────────────────────────
if [[ ! -d "$DATA_DIR" ]]; then
  die "Le répertoire DATA_DIR n'existe pas: $DATA_DIR"
fi

# ─────────────────────────────────────────────────────────────────────────
# Résolution des chemins et vérification du YAML
# ─────────────────────────────────────────────────────────────────────────
_info "Vérification du fichier de métadonnées..."
METADATA_YAML=".metadata.yaml"

if [[ ! -f "$METADATA_YAML" ]]; then
die "Fichier $METADATA_YAML introuvable dans $(pwd)"
fi

_result "Fichier $METADATA_YAML trouvé"

# Constuction du fichier de sortie
SCRIPT_NAME=$(basename $0)
SCRIPT_NAME_WHITHOUT_EXTENSION=$(echo $SCRIPT_NAME | cut -d '.' -f 1)
OUTPUT_FILE="$DATA_DIR/$SCRIPT_NAME_WHITHOUT_EXTENSION.dat"

kv "SCRIPT_NAME" "$SCRIPT_NAME"
kv "SCRIPT_NAME_WHITHOUT_EXTENSION" "$SCRIPT_NAME_WHITHOUT_EXTENSION"
kv "OUTPUT_FILE" "$OUTPUT_FILE"

# ──────────────────────────────────────────────────────────────────────────────────────
# 3. Extraction des données depuis .metadata.yaml
# ──────────────────────────────────────────────────────────────────────────────────────
_info "Extraction des données depuis: $METADATA_YAML"

# Extraire les valeurs avec grep et sed (|| true pour éviter erreurs si absent)
ALPHA=$(yq -r ".cas.angle_incidence" "$METADATA_YAML" 2>/dev/null)
CL=$(yq -r ".cas.CL" "$METADATA_YAML" 2>/dev/null)
CD=$(yq -r ".cas.CD" "$METADATA_YAML" 2>/dev/null)

# Vérifier que toutes les valeurs ont été extraites
if [[ -z "$ALPHA" ]]; then
  die "Impossible d'extraire l'angle d'incidence depuis le fichier YAML"
fi

if [[ -z "$CL" ]] || [[ -z "$CD" ]]; then
  _warn "CL ou CD manquant dans le fichier YAML (CL=$CL, CD=$CD)"
  _note "Le cas n'a probablement pas encore été post-traité"
  exit 0
fi

_info "Valeurs extraites:"
kv "Angle (alpha)" "$ALPHA°"
kv "CL" "$CL"
kv "CD" "$CD"

# ──────────────────────────────────────────────────────────────────────────────────────
# 4. Création ou mise à jour du fichier incidence.dat
# ──────────────────────────────────────────────────────────────────────────────────────
_info "Mise à jour du fichier: $OUTPUT_FILE"

# Créer le fichier avec en-tête s'il n'existe pas
if [[ ! -f "$OUTPUT_FILE" ]]; then
  _info "Création du fichier $OUTPUT_FILE avec en-tête"
  cat > "$OUTPUT_FILE" <<EOF
# Coefficients aérodynamiques en fonction de l'angle d'incidence
# alpha    CL              CD
# -----------------------------------
EOF
fi

# Créer un fichier temporaire
TEMP_FILE=$(mktemp)

# Lire le fichier existant en excluant les lignes qui commencent par l'alpha actuel
# (pour éviter les doublons si on réexécute le script)
grep -Ev "^${ALPHA}[[:space:]]" "$OUTPUT_FILE" > "$TEMP_FILE" || true

# Ajouter la nouvelle ligne
printf "%-10s %-15s %-15s\n" "$ALPHA" "$CL" "$CD" >> "$TEMP_FILE"

# Trier le fichier par alpha (en ignorant les commentaires)
{
  grep '^#' "$TEMP_FILE" || true
  grep -v '^#' "$TEMP_FILE" | LC_ALL=C sort -n -k1 || true
} > "$OUTPUT_FILE"

# Nettoyer
rm -f "$TEMP_FILE"

_result "Données ajoutées pour alpha=$ALPHA° dans incidence.dat"

# ──────────────────────────────────────────────────────────────────────────────────────
# 5. Afficher le contenu du fichier de sortie
# ──────────────────────────────────────────────────────────────────────────────────────
_info "Contenu actuel de incidence.dat:"
echo
cat "$OUTPUT_FILE"
echo

_end "Extraction terminée avec succès"
