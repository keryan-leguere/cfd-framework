#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  gestion_config.sh — Gestion du chargement et validation des configurations
# ═══════════════════════════════════════════════════════════════════════════════
#
#  📚 Fonctions disponibles :
#     • cfg_charger()                      # Charger config.yaml
#     • cfg_obtenir_valeur()               # Extraire une valeur spécifique
#     • cfg_obtenir_valeur_cascade()       # Extraire avec cascade (cas → config → global)
#     • cfg_lister_configurations()        # Lister toutes les configurations
#     • cfg_lister_cas()                   # Lister cas avec expansion boucles
#     • cfg_expander_cas()                 # Expander un cas avec ses boucles
#     • cfg_valider_schema()               # Valider structure YAML
#     • cfg_exporter_env()                 # Exporter en variables d'environnement
#     • cfg_afficher()                     # Afficher config formatée
#
#  Auteur : KL
#  Licence : MIT
# ═══════════════════════════════════════════════════════════════════════════════

# ── Détection si le fichier est sourcé ou exécuté ─────────────────────────────
_is_sourced() {
  (return 0 2>/dev/null)
}

# Mode strict uniquement en exécution directe
if ! _is_sourced; then
  set -Eeuo pipefail
  IFS=$'\n\t'
fi

# ── Vérification de yq (obligatoire) ──────────────────────────────────────────
if ! command -v yq &>/dev/null; then
  echo "ERREUR: yq est requis mais non installé" >&2
  echo "Installation: pip install yq  ou  brew install yq" >&2
  exit 1
fi

# Charger format.sh si disponible
if [[ -z "${_FORMAT_LOADED:-}" ]] && [[ -n "${CFD_FRAMEWORK:-}" ]]; then
  if [[ -f "${CFD_FRAMEWORK}/lib/format.sh" ]]; then
    source "${CFD_FRAMEWORK}/lib/format.sh"
  fi
fi

# Variable interne pour stocker le fichier de config actif
_CFG_FICHIER_ACTIF=""

# ══════════════════════════════════════════════════════════════════════════════
#  📥 CHARGEMENT DE CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

# Charger un fichier de configuration YAML
# Usage: cfg_charger FICHIER_CONFIG
cfg_charger() {
  local fichier="$1"
  
  if [[ ! -f "$fichier" ]]; then
    if command -v _error &>/dev/null; then
      _error "Fichier de configuration inexistant: $fichier"
      exit 1
    else
      echo "ERREUR: Fichier inexistant: $fichier" >&2
      exit 1
    fi
  fi
  
  # Valider que c'est du YAML valide
  if ! yq '.' "$fichier" >/dev/null 2>&1; then
    if command -v _error &>/dev/null; then
      _error "Fichier YAML invalide: $fichier"
      exit 1
    else
      echo "ERREUR: Fichier YAML invalide: $fichier" >&2
      exit 1
    fi
  fi
  
  _CFG_FICHIER_ACTIF="$fichier"
  export YAML_CONFIG_FILE="$fichier"
}

# ══════════════════════════════════════════════════════════════════════════════
#  🔍 EXTRACTION DE VALEURS
# ══════════════════════════════════════════════════════════════════════════════

# Obtenir une valeur depuis la configuration
# Usage: cfg_obtenir_valeur "configurations.BASELINE.cas[0].parametres.angle_attaque"
cfg_obtenir_valeur() {
  local cle="$1"
  
  if [[ -z "$_CFG_FICHIER_ACTIF" ]]; then
    if command -v _error &>/dev/null; then
      _error "Aucune configuration chargée"
    fi
    return 1
  fi
  
  yq -r ".${cle} // empty" "$_CFG_FICHIER_ACTIF" 2>/dev/null
}

# Obtenir une valeur avec système de cascade (cas → configuration → global)
# Usage: cfg_obtenir_valeur_cascade CLE [CHEMIN_CAS]
# Exemple: cfg_obtenir_valeur_cascade "adaptateur" "configurations.BASELINE.cas[0]"
cfg_obtenir_valeur_cascade() {
  local cle="$1"
  local chemin_cas="${2:-}"
  local valeur=""
  
  if [[ -z "$_CFG_FICHIER_ACTIF" ]]; then
    return 1
  fi
  
  # 1. Chercher dans le cas si fourni
  if [[ -n "$chemin_cas" ]]; then
    valeur=$(yq -r "${chemin_cas}.parametres.${cle} // empty" "$_CFG_FICHIER_ACTIF" 2>/dev/null)
    if [[ -n "$valeur" && "$valeur" != "null" && "$valeur" != "empty" ]]; then
      echo "$valeur"
      return 0
    fi
    
    # 2. Chercher dans la configuration parente (extraire le chemin sans .cas[X])
    local config_path="${chemin_cas%%\.cas\[*\]}"
    valeur=$(yq -r "${config_path}.${cle} // empty" "$_CFG_FICHIER_ACTIF" 2>/dev/null)
    if [[ -n "$valeur" && "$valeur" != "null" && "$valeur" != "empty" ]]; then
      echo "$valeur"
      return 0
    fi
  fi
  
  # 3. Chercher au niveau global
  valeur=$(yq -r ".${cle} // empty" "$_CFG_FICHIER_ACTIF" 2>/dev/null)
  echo "$valeur"
}

# ══════════════════════════════════════════════════════════════════════════════
#  🔄 EXPANSION DES BOUCLES
# ══════════════════════════════════════════════════════════════════════════════

# Expander un cas avec ses boucles (si définies)
# Usage: cfg_expander_cas "configurations.BASELINE.cas[0]"
# Retourne: JSON array des cas expansés (ou cas unique si pas de boucle)
#
# Formats supportés pour les boucles:
#   boucle:
#     reynolds: [1e6, 2e6, 3e6]              # Tableau direct
#     angle_attaque:                          # Range
#       debut: 0
#       fin: 20
#       pas: 5
cfg_expander_cas() {
  local chemin_cas="$1"
  local config_path="${chemin_cas%%\.cas\[*\]}"
  
  if [[ -z "$_CFG_FICHIER_ACTIF" ]]; then
    echo "[]"
    return 1
  fi
  
  # Vérifier si des boucles sont définies au niveau de la configuration
  local has_boucle=$(yq -r ".${config_path}.boucle // empty" "$_CFG_FICHIER_ACTIF" 2>/dev/null)
  
  if [[ -z "$has_boucle" || "$has_boucle" == "null" || "$has_boucle" == "empty" ]]; then
    # Pas de boucle, retourner le cas tel quel dans un tableau
    local cas_json=$(yq -c ".${chemin_cas}" "$_CFG_FICHIER_ACTIF" 2>/dev/null)
    echo "[$cas_json]"
    return 0
  fi
  
  # Récupérer les clés de boucle
  local boucle_keys=$(yq -r ".${config_path}.boucle | keys[]" "$_CFG_FICHIER_ACTIF" 2>/dev/null)
  
  if [[ -z "$boucle_keys" ]]; then
    local cas_json=$(yq -c ".${chemin_cas}" "$_CFG_FICHIER_ACTIF" 2>/dev/null)
    echo "[$cas_json]"
    return 0
  fi
  
  # Construire les tableaux de valeurs pour chaque paramètre de boucle
  local -A loop_arrays
  local loop_keys_array=()
  
  while IFS= read -r key; do
    [[ -z "$key" ]] && continue
    loop_keys_array+=("$key")
    
    # Vérifier si c'est un tableau ou un objet range
    local value_type=$(yq -r ".${config_path}.boucle.${key} | type" "$_CFG_FICHIER_ACTIF" 2>/dev/null)
    
    if [[ "$value_type" == "array" ]]; then
      # Tableau direct: extraire les valeurs
      local values=$(yq -r ".${config_path}.boucle.${key}[]" "$_CFG_FICHIER_ACTIF" 2>/dev/null | tr '\n' ' ')
      loop_arrays["$key"]="$values"
    elif [[ "$value_type" == "object" ]]; then
      # Range: générer le tableau
      local debut=$(yq -r ".${config_path}.boucle.${key}.debut" "$_CFG_FICHIER_ACTIF" 2>/dev/null)
      local fin=$(yq -r ".${config_path}.boucle.${key}.fin" "$_CFG_FICHIER_ACTIF" 2>/dev/null)
      local pas=$(yq -r ".${config_path}.boucle.${key}.pas" "$_CFG_FICHIER_ACTIF" 2>/dev/null)
      
      # Générer la séquence avec awk pour supporter les nombres décimaux
      local values=$(awk -v start="$debut" -v end="$fin" -v step="$pas" '
        BEGIN {
          for (i = start; i <= end; i += step) {
            printf "%.10g ", i
          }
        }
      ')
      loop_arrays["$key"]="$values"
    fi
  done <<< "$boucle_keys"
  
  # Récupérer le cas de base
  local base_cas=$(yq -c ".${chemin_cas}" "$_CFG_FICHIER_ACTIF" 2>/dev/null)
  
  # Générer le produit cartésien et créer les cas
  local result="["
  local first=true
  
  # Fonction récursive pour générer le produit cartésien
  _generate_cartesian_product() {
    local depth=$1
    local current_values="$2"
    
    if [[ $depth -eq ${#loop_keys_array[@]} ]]; then
      # Créer un cas avec les valeurs actuelles
      local new_cas="$base_cas"
      
      # Injecter les valeurs des boucles dans parametres
      local idx=0
      for key in "${loop_keys_array[@]}"; do
        local val_array=($current_values)
        local val="${val_array[$idx]}"
        
        # Mettre à jour le paramètre dans le JSON
        new_cas=$(echo "$new_cas" | jq --arg key "$key" --arg val "$val" '.parametres[$key] = ($val | tonumber? // $val)')
        
        ((idx++)) || true
      done
      
      # Ajouter au résultat
      if [[ "$first" == true ]]; then
        result+="$new_cas"
        first=false
      else
        result+=",$new_cas"
      fi
      
      return
    fi
    
    local key="${loop_keys_array[$depth]}"
    local values="${loop_arrays[$key]}"
    
    for val in $values; do
      _generate_cartesian_product $((depth + 1)) "$current_values $val"
    done
  }
  
  # Lancer la génération
  _generate_cartesian_product 0 ""
  
  result+="]"
  echo "$result"
}

# ══════════════════════════════════════════════════════════════════════════════
#  📋 LISTAGE DES CONFIGURATIONS ET CAS
# ══════════════════════════════════════════════════════════════════════════════

# Lister toutes les configurations disponibles
# Usage: cfg_lister_configurations
cfg_lister_configurations() {
  if [[ -z "$_CFG_FICHIER_ACTIF" ]]; then
    return 1
  fi
  
  yq -r '.configurations | keys[]' "$_CFG_FICHIER_ACTIF" 2>/dev/null
}

# Lister tous les cas d'une configuration (avec expansion des boucles)
# Usage: cfg_lister_cas "BASELINE"
# Retourne: JSON array des cas (expansés si boucles présentes)
cfg_lister_cas() {
  local config_name="$1"
  local config_path="configurations.${config_name}"
  
  if [[ -z "$_CFG_FICHIER_ACTIF" ]]; then
    return 1
  fi
  
  # Récupérer le nombre de cas
  local nb_cas=$(yq -r ".${config_path}.cas | length" "$_CFG_FICHIER_ACTIF" 2>/dev/null)
  
  if [[ -z "$nb_cas" || "$nb_cas" == "null" || "$nb_cas" -eq 0 ]]; then
    echo "[]"
    return 0
  fi
  
  # Pour chaque cas, l'expander
  local all_cases="["
  local first=true
  
  for ((i=0; i<nb_cas; i++)); do
    local expanded=$(cfg_expander_cas "${config_path}.cas[$i]")
    
    if [[ "$first" == true ]]; then
      first=false
    else
      all_cases+=","
    fi
    
    all_cases+="$expanded"
  done
  
  all_cases+="]"
  echo "$all_cases"
}

# ══════════════════════════════════════════════════════════════════════════════
#  ✅ VALIDATION DU SCHÉMA
# ══════════════════════════════════════════════════════════════════════════════

# Valider la structure de la configuration
# Usage: cfg_valider_schema
cfg_valider_schema() {
  if [[ -z "$_CFG_FICHIER_ACTIF" ]]; then
    if command -v _error &>/dev/null; then
      _error "Aucune configuration chargée"
    fi
    return 1
  fi
  
  local erreurs=0
  
  # Vérifier présence de "configurations"
  local has_configs=$(yq -r '.configurations // empty' "$_CFG_FICHIER_ACTIF" 2>/dev/null)
  if [[ -z "$has_configs" || "$has_configs" == "null" ]]; then
    if command -v _error &>/dev/null; then
      _error "Section 'configurations' manquante"
    else
      echo "ERREUR: Section 'configurations' manquante" >&2
    fi
    ((erreurs++))
  fi
  
  # Vérifier présence de "adaptateur" (recommandé, pas obligatoire)
  local has_adaptateur=$(yq -r '.adaptateur // empty' "$_CFG_FICHIER_ACTIF" 2>/dev/null)
  if [[ -z "$has_adaptateur" ]]; then
    if command -v _warn &>/dev/null; then
      _warn "Clé 'adaptateur' non trouvée (sera utilisé le défaut)"
    fi
  fi
  
  # Valider les boucles si présentes
  local configs=$(yq -r '.configurations | keys[]' "$_CFG_FICHIER_ACTIF" 2>/dev/null)
  
  while IFS= read -r config; do
    [[ -z "$config" ]] && continue
    
    local has_boucle=$(yq -r ".configurations.${config}.boucle // empty" "$_CFG_FICHIER_ACTIF" 2>/dev/null)
    
    if [[ -n "$has_boucle" && "$has_boucle" != "null" && "$has_boucle" != "empty" ]]; then
      # Valider chaque boucle
      local boucle_keys=$(yq -r ".configurations.${config}.boucle | keys[]" "$_CFG_FICHIER_ACTIF" 2>/dev/null)
      
      while IFS= read -r key; do
        [[ -z "$key" ]] && continue
        
        local value_type=$(yq -r ".configurations.${config}.boucle.${key} | type" "$_CFG_FICHIER_ACTIF" 2>/dev/null)
        
        if [[ "$value_type" == "object" ]]; then
          # Valider format range
          local debut=$(yq -r ".configurations.${config}.boucle.${key}.debut // empty" "$_CFG_FICHIER_ACTIF" 2>/dev/null)
          local fin=$(yq -r ".configurations.${config}.boucle.${key}.fin // empty" "$_CFG_FICHIER_ACTIF" 2>/dev/null)
          local pas=$(yq -r ".configurations.${config}.boucle.${key}.pas // empty" "$_CFG_FICHIER_ACTIF" 2>/dev/null)
          
          if [[ -z "$debut" || -z "$fin" || -z "$pas" ]]; then
            if command -v _error &>/dev/null; then
              _error "Boucle '${key}' dans '${config}': format range incomplet (debut, fin, pas requis)"
            fi
            ((erreurs++))
          fi
          
          # Vérifier cohérence: debut < fin et pas > 0
          local valid=$(awk -v d="$debut" -v f="$fin" -v p="$pas" 'BEGIN { print (d < f && p > 0) ? "1" : "0" }')
          if [[ "$valid" != "1" ]]; then
            if command -v _warn &>/dev/null; then
              _warn "Boucle '${key}' dans '${config}': valeurs incohérentes (debut=$debut, fin=$fin, pas=$pas)"
            fi
          fi
        elif [[ "$value_type" != "array" ]]; then
          if command -v _error &>/dev/null; then
            _error "Boucle '${key}' dans '${config}': type invalide (array ou object attendu)"
          fi
          ((erreurs++))
        fi
      done <<< "$boucle_keys"
    fi
  done <<< "$configs"
  
  return $erreurs
}


# ══════════════════════════════════════════════════════════════════════════════
#  📊 AFFICHAGE DE LA CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

# Afficher un résumé de la configuration
# Usage: cfg_afficher
cfg_afficher() {
  if [[ -z "$_CFG_FICHIER_ACTIF" ]]; then
    if command -v _warn &>/dev/null; then
      _warn "Aucune configuration chargée"
    fi
    return 1
  fi
  
  if command -v h2 &>/dev/null; then
    h2 "Configuration: $_CFG_FICHIER_ACTIF"
  else
    echo "=== Configuration: $_CFG_FICHIER_ACTIF ==="
  fi
  
  local nom_etude=$(cfg_obtenir_valeur "etude.nom")
  local adaptateur=$(cfg_obtenir_valeur "adaptateur")
  local configs=$(cfg_lister_configurations)
  
  if command -v kv &>/dev/null; then
    kv "Étude" "${nom_etude:-N/A}"
    kv "Adaptateur" "${adaptateur:-mock}"
    kv "Configurations" "$(echo "$configs" | tr '\n' ' ')"
  else
    echo "  Étude: ${nom_etude:-N/A}"
    echo "  Adaptateur: ${adaptateur:-mock}"
    echo "  Configurations: $(echo "$configs" | tr '\n' ' ')"
  fi
}

# Fonction pour afficher les paramètres d'un cas donné
cfg_show_parametres() {
  local CONFIG_FILE="$1"
  local YAML_PATH="$2"

  # Initialiser le tableau
  tableau_init "Paramètre" "Valeur"

  # Extraire tous les paramètres du cas en key/value
  local keys
  keys=$(yq -r "${YAML_PATH}.parametres | keys[]" "$CONFIG_FILE")

  for key in $keys; do
    local value
    value=$(yq -r "${YAML_PATH}.parametres.${key}" "$CONFIG_FILE")

    tableau_add "$key" "$value"
  done

  tableau_print "Paramètres de la simulation"
}

cfg_add_parametres_to_new_file() {
  local CONFIG_FILE="$1"
  local YAML_PATH="$2"
  local NEW_YAML_FILE="$3"

  # Extraire tous les paramètres du cas en key/value
  local keys
  keys=$(yq -r "${YAML_PATH}.parametres | keys[]" "$CONFIG_FILE")

  for key in $keys; do
    local value
    value=$(yq -r "${YAML_PATH}.parametres.${key}" "$CONFIG_FILE")

    yq -i -Y ".cas.${key} = ${value}" "$NEW_YAML_FILE"
  done
}

