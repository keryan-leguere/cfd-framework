#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  PP.sh — Template de Post-traitement CFD
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Ce script sert de template pour le post-traitement de cas CFD.
#  Il suit une structure modulaire en 5 étapes :
#    1. Setup         : Chargement bibliothèques, validation env vars
#    2. Information   : Extraction des infos du YAML
#    3. Extraction    : Conversion résultats (binaire → CSV)
#    4. Calcul        : Traitement des CSV (adimensionnement, métriques)
#    5. Nettoyage     : Suppression des fichiers temporaires
#
#  Pour des cas plus complexes, étendre les fonctions step_* ci-dessous.
#
# ═══════════════════════════════════════════════════════════════════════════════

set -Euo pipefail

# ══════════════════════════════════════════════════════════════════════════════
#  🎛️  SWITCHES DE CONTRÔLE DES ÉTAPES
# ══════════════════════════════════════════════════════════════════════════════
#  Activer (1) ou désactiver (0) chaque étape selon les besoins.
#  Utile pendant le développement pour tester une étape spécifique.

DO_SETUP=1        # Toujours recommandé (validation env, chemins)
DO_INFO=1         # Lecture du YAML
DO_EXTRACTION=1   # Conversion des résultats (postProcess, etc.)
DO_CALCUL=1       # Calculs dérivés (CL, CD, métriques, etc.)
DO_CLEANUP=0      # Nettoyage (désactivé par défaut pendant les tests)

# ══════════════════════════════════════════════════════════════════════════════
#  📚 VARIABLES GLOBALES
# ══════════════════════════════════════════════════════════════════════════════
METADATA_YAML=".metadata.yaml"

# Variables à remplir par les étapes
GLOBAL_CASE_NAME=""
GLOBAL_CASE_PATH=""

# ─────────────────────────────────────────────────────────────────────────
# 0. Charger la bibliothèque de formatage
# ─────────────────────────────────────────────────────────────────────────
if [[ -z "${CFD_FRAMEWORK:-}" ]]; then
  echo "❌ ERREUR : La variable d'environnement CFD_FRAMEWORK n'est pas définie."
  echo "   Veuillez définir CFD_FRAMEWORK avant d'exécuter ce script."
  exit 1
fi

FORMAT_LIB="${CFD_FRAMEWORK}/lib/format.sh"
if [[ ! -f "$FORMAT_LIB" ]]; then
  echo "❌ ERREUR : Fichier format.sh introuvable à ${FORMAT_LIB}"
  exit 1
fi

# shellcheck source=/dev/null
source "$FORMAT_LIB"

# ══════════════════════════════════════════════════════════════════════════════
#  🔧 ÉTAPE 1 : SETUP
# ══════════════════════════════════════════════════════════════════════════════

step_setup() {
  h1 "Setup"

  # ─────────────────────────────────────────────────────────────────────────
  # Résolution des chemins et vérification du YAML
  # ─────────────────────────────────────────────────────────────────────────
  _info "Vérification du fichier de métadonnées..."

  if [[ ! -f "$METADATA_YAML" ]]; then
    die "Fichier $METADATA_YAML introuvable dans $(pwd)"
  fi

  _result "Fichier $METADATA_YAML trouvé"

  mkdir -p "POST_TRAITEMENT/DATA"
  mkdir -p "POST_TRAITEMENT/FIGURE"
}

# ══════════════════════════════════════════════════════════════════════════════
#  📄 ÉTAPE 2 : INFORMATION CALCUL
# ══════════════════════════════════════════════════════════════════════════════

step_info() {
  h1 "Information Calcul"

  _info "Extraction des informations depuis $METADATA_YAML..."

  # ─────────────────────────────────────────────────────────────────────────
  # Lecture de l'angle d'incidence
  # ─────────────────────────────────────────────────────────────────────────
  ALPHA=$(yq -r ".cas.angle_incidence" "$METADATA_YAML" 2>/dev/null)
  
  if [[ -z "$ALPHA" || "$ALPHA" == "null" ]]; then
    die "Impossible de lire .cas.angle_incidence depuis $METADATA_YAML"
  fi

  _result "Informations extraites du YAML"
  kv "Angle d'incidence" "${ALPHA}°"

  # ─────────────────────────────────────────────────────────────────────────
  # Détection du dernier temps de calcul
  # ─────────────────────────────────────────────────────────────────────────
  LATESTTIME=$(foamListTimes | tail -n 1)
  
  if [[ -z "$LATESTTIME" ]]; then
    die "Impossible de déterminer le dernier temps de calcul"
  fi

  kv "Dernier temps de calcul" "${LATESTTIME}"

  # ─────────────────────────────────────────────────────────────────────────
  # EXTENSION : Pour des cas complexes, ajouter ici d'autres lectures YAML
  # ─────────────────────────────────────────────────────────────────────────
  # Exemples :
  #   REYNOLDS=$(yq -r ".cas.reynolds" "$METADATA_YAML")
  #   MACH=$(yq -r ".cas.mach" "$METADATA_YAML")
  #   kv "Reynolds" "$REYNOLDS"
  #   kv "Mach" "$MACH"
}

# ══════════════════════════════════════════════════════════════════════════════
#  📊 ÉTAPE 3 : EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

step_extraction() {
  h1 "Extraction"

  _info "Extraction des résultats via OpenFOAM postProcess..."

  # ─────────────────────────────────────────────────────────────────────────
  # 3.1 Exécution de postProcess pour les coefficients de force
  # ─────────────────────────────────────────────────────────────────────────
  _info "Calcul des coefficients de force (forceCoeffsIncompressible)..."
  if ! postProcess -func "forceCoeffsIncompressible" -fields '(U p)' \
                   -solver incompressibleFluid -latestTime > postProcess.log 2>&1
  then
    boite_error "Échec de l'exécution de postProcess"
    _debug "Log de postProcess : $(pwd)/postProcess.log"
    _info "Log de postProcess :"
    cat postProcess.log
    exit 1
  fi

  _result "postProcess exécuté avec succès"

  # ─────────────────────────────────────────────────────────────────────────
  # 3.2 Vérification du fichier de sortie
  # ─────────────────────────────────────────────────────────────────────────
  local force_file="postProcessing/forceCoeffsIncompressible/${LATESTTIME}/forceCoeffs.dat"
  
  if [[ ! -f "$force_file" ]]; then
    die "Fichier $force_file introuvable"
  fi

  _result "Fichier de résultats trouvé : $force_file"

  # ═════════════════════════════════════════════════════════════════════════
  # EXTENSION : Extraction via outils tiers (Paraview, Tecplot)
  # ═════════════════════════════════════════════════════════════════════════
  #
  # Pour des extractions plus complexes (pression le long d'une paroi,
  # coupes 2D/3D, etc.), utiliser Paraview ou Tecplot :
  #
  # Exemple avec Paraview (pvpython) :
  #   _info "Extraction de la pression pariétale via Paraview..."
  #   pvpython extract_wall_pressure.py \
  #     --case "$GLOBAL_CASE_PATH" \
  #     --output "postProcessing/wallPressure.csv"
  #   _result "Pression pariétale extraite"
  #
  # Exemple avec Tecplot (tec360) :
  #   _info "Conversion des résultats en format Tecplot..."
  #   foamToTecplot360 -latestTime
  #   tec360 -b extract_data.mcr
  #   _result "Données Tecplot extraites"
  #
  # Note : Ces outils nécessitent des scripts Python/Macro supplémentaires
  #        à placer dans le répertoire du cas ou dans CFD_FRAMEWORK/tools/
  # ═════════════════════════════════════════════════════════════════════════
}

# ══════════════════════════════════════════════════════════════════════════════
#  🧮 ÉTAPE 4 : CALCUL
# ══════════════════════════════════════════════════════════════════════════════

step_calcul() {
  h1 "Calcul"

  _info "Traitement des données extraites..."

  # ─────────────────────────────────────────────────────────────────────────
  # 4.1 Lecture des coefficients normaux et axiaux
  # ─────────────────────────────────────────────────────────────────────────
  local force_file="postProcessing/forceCoeffsIncompressible/${LATESTTIME}/forceCoeffs.dat"
  
  local CN CA
  CN=$(tail -n 1 "$force_file" | awk '{print $4}')
  CA=$(tail -n 1 "$force_file" | awk '{print $3}')

  if [[ -z "$CN" || -z "$CA" ]]; then
    die "Impossible d'extraire CN et CA depuis $force_file"
  fi

  _info "Coefficients extraits : CN=$CN, CA=$CA"

  # ─────────────────────────────────────────────────────────────────────────
  # 4.2 Calcul des coefficients aérodynamiques CL et CD
  # ─────────────────────────────────────────────────────────────────────────
  # Formules :
  #   CL = CN*cos(alpha) - CA*sin(alpha)
  #   CD = CN*sin(alpha) + CA*cos(alpha)
  # (conversion degrés → radians, forcer locale C pour point décimal)

  _info "Calcul de CL et CD avec alpha=${ALPHA}°..."

  local coeffs CL CD
  coeffs=$(LC_ALL=C awk -v cn="$CN" -v ca="$CA" -v alpha="$ALPHA" '
    BEGIN {
        pi = 3.14159265358979323846
        alpha_rad = alpha * pi / 180.0

        cl = cn * cos(alpha_rad) - ca * sin(alpha_rad)
        cd = cn * sin(alpha_rad) + ca * cos(alpha_rad)

        printf "%.8e %.8e", cl, cd
    }
  ')

  CL=$(echo "$coeffs" | awk '{print $1}')
  CD=$(echo "$coeffs" | awk '{print $2}')

  _result "Coefficients aérodynamiques calculés"
  kv "CL (portance)" "$CL"
  kv "CD (traînée)" "$CD"

  # ─────────────────────────────────────────────────────────────────────────
  # 4.3 Écriture des résultats dans le YAML
  # ─────────────────────────────────────────────────────────────────────────
  _info "Mise à jour du fichier $METADATA_YAML..."

  yq -i -Y ".cas.CL = (\"$CL\" | tonumber)" "$METADATA_YAML"
  yq -i -Y ".cas.CD = (\"$CD\" | tonumber)" "$METADATA_YAML"

  _result "Fichier $METADATA_YAML mis à jour"

  # ═════════════════════════════════════════════════════════════════════════
  # EXTENSION : Calculs avancés
  # ═════════════════════════════════════════════════════════════════════════
  #
  # Pour des cas complexes, ajouter ici :
  #
  # - Adimensionnement de données CSV :
  #     _info "Adimensionnement des profils de pression..."
  #     awk -v pref="$PREF" '{print $1, $2/pref}' raw.csv > nondim.dat
  #
  # - Calcul de métriques (longueur de recirculation) :
  #     _info "Calcul de la longueur de recirculation..."
  #     RECIRCULATION_LENGTH=$(python3 compute_recirculation.py \
  #       --velocity-field "postProcessing/velocity.csv")
  #     kv "Longueur recirculation" "${RECIRCULATION_LENGTH} m"
  #
  # - Intégrations numériques :
  #     _info "Intégration du flux de chaleur..."
  #     HEAT_FLUX=$(awk '{sum+=$2} END {print sum}' heat_flux.dat)
  #     kv "Flux total" "${HEAT_FLUX} W"
  #
  # ═════════════════════════════════════════════════════════════════════════
}

# ══════════════════════════════════════════════════════════════════════════════
#  🧹 ÉTAPE 5 : NETTOYAGE
# ══════════════════════════════════════════════════════════════════════════════

step_cleanup() {
  h1 "Nettoyage"

  _info "Suppression des fichiers temporaires..."

  # ─────────────────────────────────────────────────────────────────────────
  # Supprimer les fichiers CSV intermédiaires, logs temporaires, etc.
  # ─────────────────────────────────────────────────────────────────────────
  # Exemples :
  #   rm -f postProcessing/*.csv
  #   rm -f *.tmp
  #   rm -rf temp_extraction/

  _result "Nettoyage terminé (aucun fichier à supprimer pour ce template)"

  # ═════════════════════════════════════════════════════════════════════════
  # EXTENSION : Nettoyage personnalisé
  # ═════════════════════════════════════════════════════════════════════════
  #
  # Pour des cas complexes, ajouter ici la suppression de fichiers
  # volumineux ou temporaires générés par les étapes précédentes.
  #
  # Exemples :
  #   - Fichiers VTK non compressés
  #   - Logs de conversion Paraview/Tecplot
  #   - Fichiers .csv bruts avant adimensionnement
  #
  # ═════════════════════════════════════════════════════════════════════════
}

# ══════════════════════════════════════════════════════════════════════════════
#  🚀 POINT D'ENTRÉE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

main() {

  _start "Début du post-traitement"

  # Exécution conditionnelle des étapes selon les switches
  [[ $DO_SETUP -eq 1 ]]      && step_setup
  [[ $DO_INFO -eq 1 ]]       && step_info
  [[ $DO_EXTRACTION -eq 1 ]] && step_extraction
  [[ $DO_CALCUL -eq 1 ]]     && step_calcul
  [[ $DO_CLEANUP -eq 1 ]]    && step_cleanup

  separator_double
  _end "Post-traitement terminé avec succès"
  
  # Affichage final du YAML pour vérification
  echo
  _info "Contenu final de $METADATA_YAML :"
  cat "$METADATA_YAML"
  sleep 20
}

# Lancement du script
main "$@"
