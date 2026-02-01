#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  run_parametrique.sh — Lance une étude paramétrique AIRFOIL_2D
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Ce script charge un config.yaml, génère les cas à partir des templates,
#  fait la substitution des paramètres et lance OpenFOAM via cfd-run.
#
#  Usage:
#    ./run_parametrique.sh [OPTIONS]
#
#  Options:
#    -h, --help              Afficher cette aide
#    --config <NOM>          Lancer uniquement la configuration spécifiée
#    --dry-run               Préparer les cas sans lancer les calculs
#
#  Prérequis:
#    - Variable CFD_FRAMEWORK définie
#    - yq installé (pour gestion_config.sh)
#
#  Auteur : Helios
#  Licence : MIT
# ═══════════════════════════════════════════════════════════════════════════════

set -Euo pipefail
IFS=$'\n\t'

# ══════════════════════════════════════════════════════════════════════════════
#  🔧 RÉSOLUTION DES CHEMINS
# ══════════════════════════════════════════════════════════════════════════════

# Résoudre le répertoire de base
BASE_DIR="$(pwd)"

# ══════════════════════════════════════════════════════════════════════════════
#  📚 CHARGEMENT DES BIBLIOTHÈQUES
# ══════════════════════════════════════════════════════════════════════════════

if [[ -z "${CFD_FRAMEWORK:-}" ]]; then
  echo "ERREUR: Variable CFD_FRAMEWORK non définie" >&2
  echo "Veuillez définir CFD_FRAMEWORK pour utiliser ce script" >&2
  exit 1
fi

source "${CFD_FRAMEWORK}/lib/format.sh"
source "${CFD_FRAMEWORK}/lib/gestion_config.sh"
source "${CFD_FRAMEWORK}/lib/substitution_params.sh"
source "${CFD_FRAMEWORK}/lib/gestion_timestamps.sh"

# ══════════════════════════════════════════════════════════════════════════════
#  ❓ FONCTION D'AIDE
# ══════════════════════════════════════════════════════════════════════════════

usage() {
  cat <<EOF

╔═══════════════════════════════════════════════════════════════════════════════╗
║              🚀 run_parametrique.sh — Étude Paramétrique                      ║
╚═══════════════════════════════════════════════════════════════════════════════╝

${BOLD}USAGE:${RESET}
  $0 [OPTIONS]

${BOLD}DESCRIPTION:${RESET}
  Lance une étude paramétrique à partir du fichier config.yaml.
  Génère les cas depuis les templates, substitue les paramètres et lance
  le code CFD via cfd-run.

${BOLD}OPTIONS:${RESET}
  -h, --help              Afficher cette aide
  --config <NOM>          Lancer uniquement la configuration spécifiée
  --dry-run               Préparer les cas sans lancer les calculs
  --in-place              Exécuter dans le répertoire actuel (pas de copie horodatée)
  --name <NOM>            Spécifier le nom du répertoire de cas

${BOLD}EXEMPLES:${RESET}
  # Lancer toutes les configurations
  $0

  # Lancer uniquement la configuration ANGLE_INCIDENCE
  $0 --config ANGLE_INCIDENCE

  # Mode dry-run pour vérifier la préparation
  $0 --config BASELINE --dry-run
  
  # Exécuter sur place sans créer de répertoires horodatés
  $0 --config BASELINE --in-place
  
  # Spécifier un nom personnalisé pour les répertoires
  $0 --config ANGLE_INCIDENCE --name TEST_ALPHA

EOF
}

# ══════════════════════════════════════════════════════════════════════════════
#  🔧 PARSING DES ARGUMENTS
# ══════════════════════════════════════════════════════════════════════════════

CONFIG_NAME=""
DRY_RUN=false
IN_PLACE=false
CASE_NAME="${CASE_NAME:-}"
ALL_CONFIGS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --config)
      if [[ $# -lt 2 ]]; then
        _error "Option --config requiert un argument"
        exit 1
      fi
      CONFIG_NAME="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --in-place)
      IN_PLACE=true
      shift
      ;;
    --all)
      ALL_CONFIGS=true
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
    *)
      _error "Option inconnue: $1"
      echo "Utilisez -h ou --help pour afficher l'aide" >&2
      exit 1
      ;;
  esac
done

# ══════════════════════════════════════════════════════════════════════════════
#  🔧 VÉRIFICATIONS PRÉALABLES
# ══════════════════════════════════════════════════════════════════════════════

# Vérifier que CASE_NAME est défini
if [[ -z "$CASE_NAME" ]]; then
  _error "CASE_NAME non défini"
  _error "Définissez la variable d'environnement CASE_NAME ou utilisez --name"
  exit 1
fi

if [[ "$ALL_CONFIGS" == true ]] && [[ -n "$CONFIG_NAME" ]]; then
  _error "CONFIG_NAME et ALL_CONFIGS ne peuvent pas être utilisés ensemble"
  exit 1
fi

# ══════════════════════════════════════════════════════════════════════════════
#  🎯 BANNIÈRE DE LANCEMENT
# ══════════════════════════════════════════════════════════════════════════════

title_launch_simulation
title "Etude Parametrique ${CASE_NAME}"
separator_wave

# ══════════════════════════════════════════════════════════════════════════════
#  📥 CHARGEMENT DE LA CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

h1 "Choix de la configuration"

CONFIG_FILE="${BASE_DIR}/02_PARAMS/config.yaml"

_info "Chargement de la configuration: $CONFIG_FILE"

if [[ ! -f "$CONFIG_FILE" ]]; then
  _error "Fichier de configuration introuvable: $CONFIG_FILE"
  exit 1
fi

cfg_charger "$CONFIG_FILE"

_info "Validation du schéma YAML..."
if ! cfg_valider_schema; then
  _error "Le fichier de configuration contient des erreurs"
  exit 1
fi

_result "Configuration chargée et validée"

# Afficher les informations de l'étude

cfg_afficher


separator

# ══════════════════════════════════════════════════════════════════════════════
#  📋 SÉLECTION DES CONFIGURATIONS À TRAITER
# ══════════════════════════════════════════════════════════════════════════════

if [[ -n "$CONFIG_NAME" ]]; then
  _info "Configuration sélectionnée: $CONFIG_NAME"
  configs=("$CONFIG_NAME")
elif [[ "$ALL_CONFIGS" == true ]]; then
  _info "Traitement de toutes les configurations disponibles"
  mapfile -t configs < <(cfg_lister_configurations)
else
    # 1) Charger la liste
    mapfile -t configs < <(cfg_lister_configurations)

    if [[ "${#configs[@]}" -eq 0 ]]; then
        _error "Aucune configuration disponible"
        exit 1
    fi

    # 2) Menu interactif
    action=$(choisir_option "Choisir la configuration à lancer" \
        "${configs[@]}") || exit 1

    # 3) On ne garde que celle choisie
    configs=("$action")
fi

_result "$(echo "${#configs[@]}") configuration(s) à traiter: ${configs[*]}"

separator_double

# ══════════════════════════════════════════════════════════════════════════════
#  🔄 TRAITEMENT DES CONFIGURATIONS
# ══════════════════════════════════════════════════════════════════════════════

# Compteurs globaux
total_cas=0
cas_reussis=0
cas_echoues=0

  # Traiter chaque configuration
for config in "${configs[@]}"; do
  h1 "Configuration: $config";
  separator
  
  # Récupérer la description
  description=$(cfg_obtenir_valeur "configurations.${config}.description" || echo "N/A")
  _info "Description: $description"
  
  # Récupérer l'adaptateur (avec cascade)
  adaptateur=$(cfg_obtenir_valeur_cascade "adaptateur" "configurations.${config}" || echo "OF")
  _info "Adaptateur: $adaptateur"
  
  # Lister tous les cas
  _info "Récupération des cas..."
  # Récupérer directement les cas sans utiliser cfg_lister_cas (problème avec set -e)
  nb_cas=$(yq ".configurations.${config}.cas | length" "$CONFIG_FILE")
  _result "$nb_cas cas à générer"
  
  if [[ "$nb_cas" -eq 0 ]]; then
    _warn "Aucun cas défini pour la configuration $config"
    separator
    continue
  fi
  
  separator
  
  # Traiter chaque cas (itérer directement avec yq)
  for ((ii=0; ii < (nb_cas); ii++)); do
    ((total_cas++)) || true
    
    # Chemin du repertoire du cas
    LOCAL_CASE_DIR="${BASE_DIR}/02_PARAMS/${config}"
    mkdir -p "$LOCAL_CASE_DIR"
    cp -a ${LOCAL_CASE_DIR}/template/* ${LOCAL_CASE_DIR}

    YAML_PATH=".configurations.${config}.cas[$ii]"
    nom_cas=$(yq -r "${YAML_PATH}.nom" "$CONFIG_FILE")

    h2 "Cas: $nom_cas"

    description_etude=$(cfg_obtenir_valeur "etude.description")
    date_creation=$(cfg_obtenir_valeur "etude.date_creation")
    auteur=$(cfg_obtenir_valeur "etude.auteur")

    # Création d'un nouveau fichier .metadata.yaml
    touch "${LOCAL_CASE_DIR}/.metadata.yaml"
    echo "{}" > "${LOCAL_CASE_DIR}/.metadata.yaml"

    yq -i -Y ".etude.nom = \"${CASE_NAME}\"" "${LOCAL_CASE_DIR}/.metadata.yaml"
    yq -i -Y ".etude.chemin = \"${BASE_DIR}\"" "${LOCAL_CASE_DIR}/.metadata.yaml"
    yq -i -Y ".etude.description = \"${description_etude}\"" "${LOCAL_CASE_DIR}/.metadata.yaml"
    yq -i -Y ".etude.date_creation = \"${date_creation}\"" "${LOCAL_CASE_DIR}/.metadata.yaml"
    yq -i -Y ".etude.auteur = \"${auteur}\"" "${LOCAL_CASE_DIR}/.metadata.yaml"

    yq -i -Y ".configuration.nom = \"${config}\"" "${LOCAL_CASE_DIR}/.metadata.yaml"
    yq -i -Y ".configuration.chemin = \"${LOCAL_CASE_DIR}\"" "${LOCAL_CASE_DIR}/.metadata.yaml"
    yq -i -Y ".configuration.description = \"${description}\"" "${LOCAL_CASE_DIR}/.metadata.yaml"

    yq -i -Y ".cas.nom = \"${nom_cas}\"" "${LOCAL_CASE_DIR}/.metadata.yaml"
    yq -i -Y ".cas.adaptateur = \"${adaptateur}\"" "${LOCAL_CASE_DIR}/.metadata.yaml"
    yq -i -Y ".cas.in_place = \"${IN_PLACE}\"" "${LOCAL_CASE_DIR}/.metadata.yaml"

    # 1. En fonction de la configuration, lancer le script custom dans 10_SCRIPT/LANCEMENT_CALCUL/CONFIG_NAME.sh
    # 2. Le script custom convertit les values du cas du yaml en un .metadata dans le repertoire du calcul.
    CUSTOM_SCRIPT="${BASE_DIR}/10_SCRIPT/LANCEMENT_CALCUL/${config}.sh"
    h3 "Lancement du script custom: $CUSTOM_SCRIPT";
    _note "Conversion des values du cas du yaml en un .metadata dans le repertoire du calcul."

    if [[ ! -f "$CUSTOM_SCRIPT" ]]; then
      _error "Script custom introuvable: $CUSTOM_SCRIPT"
      continue
    fi
    bash "${CUSTOM_SCRIPT}" "$YAML_PATH" "$CONFIG_FILE" "$LOCAL_CASE_DIR"
    cfg_show_parametres "$CONFIG_FILE" "$YAML_PATH"
    cfg_add_parametres_to_new_file "$CONFIG_FILE" "$YAML_PATH" "$LOCAL_CASE_DIR/.metadata.yaml"
    # -------------------------------------------------------------------------- #

    # 3. Le wizard construit dans CFD_FRAMEWORK, lit le .metadata comme entrée standard et subsitue les balises @...@ dans le cas généré.
    h3 "Substitution des balises @...@ dans le cas généré."
    
    # Rechercher les fichiers contenant des balises @...@ dans le cas généré
    balises_files=$(grep -rl "@[^@]*@" --exclude-dir=template "$LOCAL_CASE_DIR" 2>/dev/null || true)
    _info balises_files: $balises_files
    
    if [[ -n "$balises_files" ]]; then
      while IFS= read -r fichier; do
        if [[ -f "$fichier" ]]; then
          _bullet "Substitution: $(basename "$fichier")"
          param_valider_template "$fichier" "$CONFIG_FILE" "$YAML_PATH"
          if [[ $? -ne 0 ]]; then
            _error "Erreur de validation du template: $fichier"
            continue
          fi
          param_substituer_tout "$fichier" "$fichier" "$CONFIG_FILE" "$YAML_PATH"
        fi
      done <<< "$balises_files"
      
      _result "Substitution terminée"
    else
      _note "Aucune balise à substituer"
    fi

    # -------------------------------------------------------------------------- #

    # 4. Le script custom lance le calcul avec cfd-run et les options transmises par le script lui-même.
    h3 "Lancement du calcul"
    _note "Lancement du calcul avec cfd-run et les options transmises par le script lui-même."
    
    # Construire la commande cfd-run avec les arguments appropriés
    cfd_run_args=("--adaptateur" "$adaptateur")
    
    if [[ "$IN_PLACE" == true ]]; then
      cfd_run_args+=("--in-place")
    fi
    
    if [[ -n "$nom_cas" ]]; then
      cfd_run_args+=("--name" "$nom_cas")
    fi

    if [[ "$DRY_RUN" == true ]]; then
      cfd_run_args+=("--dry-run")
    fi
    
    _start "Lancement du calcul OpenFOAM..."
    
    # Se déplacer dans le répertoire de cas
    cd "$LOCAL_CASE_DIR"
    
    # Lancer via cfd-run avec les arguments
    _debug "Commande cfd-run: ${CFD_FRAMEWORK}/bin/cfd-run ${cfd_run_args[@]}"
    ${CFD_FRAMEWORK}/bin/cfd-run ${cfd_run_args[@]}

    ((cas_reussis++)) || true
    
    # Retourner au répertoire de base
    cd "$BASE_DIR"
    
    separator

  done
  
  separator_double
done

# ══════════════════════════════════════════════════════════════════════════════
#  📊 RÉSUMÉ FINAL
# ══════════════════════════════════════════════════════════════════════════════

h1 "Résumé de l'étude paramétrique"

separator

kv "Cas traités:" "$total_cas"
kv "Cas réussis:" "$cas_reussis"

if [[ $cas_echoues -gt 0 ]]; then
  _warn "Certains cas ont échoué"
  exit 1
else
  boite_result "Tous les cas ont été traités avec succès"
fi

separator_wave