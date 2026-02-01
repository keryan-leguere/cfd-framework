#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  substitution_params.sh — Substitution de paramètres dans templates
# ═══════════════════════════════════════════════════════════════════════════════
#
#  📚 Fonctions disponibles :
#     • param_trouver_balises()         # Identifier toutes les balises
#     • param_remplacer_balise()        # Remplacer une balise spécifique
#     • param_valider_template()        # Vérifier cohérence template/config
#     • param_substituer_tout()         # Substituer tous les paramètres
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

# Charger les dépendances
if [[ -z "${_FORMAT_LOADED:-}" ]] && [[ -n "${CFD_FRAMEWORK:-}" ]]; then
  if [[ -f "${CFD_FRAMEWORK}/lib/format.sh" ]]; then
    source "${CFD_FRAMEWORK}/lib/format.sh"
  fi
  if [[ -f "${CFD_FRAMEWORK}/lib/gestion_config.sh" ]]; then
    source "${CFD_FRAMEWORK}/lib/gestion_config.sh"
  fi
fi

# ══════════════════════════════════════════════════════════════════════════════
#  🔍 DÉTECTION DES BALISES
# ══════════════════════════════════════════════════════════════════════════════

# Trouver toutes les balises dans un template
# Format supporté: @PARAM_NAME@ et {{PARAM_NAME}}
# Usage: param_trouver_balises FICHIER_TEMPLATE
param_trouver_balises() {
  local fichier_template="$1"
  
  if [[ ! -f "$fichier_template" ]]; then
    return 1
  fi
  
  local -a balises
  
  # Format @PARAM@
  while IFS= read -r ligne; do
    while [[ "$ligne" =~ @([^@]+)@ ]]; do
      balises+=("${BASH_REMATCH[1]}")
      ligne="${ligne#*@${BASH_REMATCH[1]}@}"
    done
  done < "$fichier_template"
  
  # Format {{PARAM}}
  while IFS= read -r ligne; do
    while [[ "$ligne" =~ \{\{([^}]+)\}\} ]]; do
      balises+=("${BASH_REMATCH[1]}")
      ligne="${ligne#*${BASH_REMATCH[0]}}"
    done
  done < "$fichier_template"
  
  # Dédupliquer et trier
  printf '%s\n' "${balises[@]}" | sort -u
}

# ══════════════════════════════════════════════════════════════════════════════
#  🔄 REMPLACEMENT DE BALISES
# ══════════════════════════════════════════════════════════════════════════════

# Remplacer une balise spécifique dans un fichier
# Usage: param_remplacer_balise TEMPLATE SORTIE NOM_BALISE VALEUR
param_remplacer_balise() {
  local template="$1"
  local sortie="$2"
  local nom_balise="$3"
  local valeur="$4"

  local balise1="@${nom_balise}@"
  local balise2="{{${nom_balise}}}"

  # Escape pour sed
  local valeur_escape
  valeur_escape=$(printf '%s\n' "$valeur" | sed 's/[[\.*^$()+?{|]/\\&/g')

  echo "▶ Remplacement de la balise '${nom_balise}'"
  _check "  Valeur: ${valeur}"
  echo

  # --- Repérage lignes impactées (numéros + contenu AVANT)
  mapfile -t lignes_avant < <(
    grep -n -E "(${balise1}|${balise2})" "$template"
  )

  local count="${#lignes_avant[@]}"

  _note "Lignes AVANT remplacement :"
  if (( count == 0 )); then
    echo "  (aucune occurrence)"
  else
    printf '%s\n' "${lignes_avant[@]}"
  fi
  echo

  # --- Remplacement
  sed "s|${balise1}|${valeur_escape}|g" "$template" > "$sortie.tmp"
  sed -i "s|${balise2}|${valeur_escape}|g" "$sortie.tmp"

  # --- Affichage APRÈS (mêmes lignes uniquement)
  _note "Lignes APRÈS remplacement :"
  if (( count == 0 )); then
    echo "  (aucune ligne modifiée)"
  else
    for l in "${lignes_avant[@]}"; do
      local lineno="${l%%:*}"
      sed -n "${lineno}p" "$sortie.tmp" | sed "s/^/${lineno}:/"
    done
  fi
  echo

  _info "${count} occurrence(s) remplacée(s)"
  echo "────────────────────────────────────────"

  mv "$sortie.tmp" "$sortie"
}



# ══════════════════════════════════════════════════════════════════════════════
#  ✅ VALIDATION DES TEMPLATES
# ══════════════════════════════════════════════════════════════════════════════

# Valider qu'un template peut être rempli avec la configuration
# Usage: param_valider_template TEMPLATE CONFIG_FILE
param_valider_template() {
  local template="$1"
  local config_file="${2:-$_CFG_FICHIER_ACTIF}"
  local chemin_cas="${3:-}"
  
  if [[ ! -f "$template" ]]; then
    if command -v _error &>/dev/null; then
      _error "Template inexistant: $template"
    fi
    return 1
  fi
  
  # Charger la config si nécessaire
  if [[ -n "$config_file" ]] && [[ "$config_file" != "$_CFG_FICHIER_ACTIF" ]]; then
    cfg_charger "$config_file"
  fi
  
  local -a balises
  mapfile -t balises < <(param_trouver_balises "$template")
  
  local manquantes=0
  
  for balise in "${balises[@]}"; do
    # Essayer d'obtenir la valeur depuis la config
    local valeur=""
    local valeur=$(cfg_obtenir_valeur_cascade "$balise" "$chemin_cas" 2>/dev/null)
    
    if [[ -z "$valeur" ]]; then
      if command -v _warn &>/dev/null; then
        _warn "Balise non résolue: $balise"
      else
        echo "AVERTISSEMENT: Balise non résolue: $balise" >&2
      fi
      ((manquantes++))
    fi
  done
  
  if [[ $manquantes -gt 0 ]]; then
    _cross "Les balises précédentes n'ont pas été trouvées dans le fichier de configuration: $config_file"
    return 1
  fi
  
  return 0
}

# ══════════════════════════════════════════════════════════════════════════════
#  🔄 SUBSTITUTION COMPLÈTE
# ══════════════════════════════════════════════════════════════════════════════

# Substituer tous les paramètres d'un template
# Usage: param_substituer_tout TEMPLATE SORTIE CONFIG_FILE [CHEMIN_CAS]
param_substituer_tout() {
  local template="$1"
  local sortie="$2"
  local config_file="$3"
  local chemin_cas="${4:-}"
  
  if [[ ! -f "$template" ]]; then
    if command -v _error &>/dev/null; then
      _error "Template inexistant: $template"
    fi
    return 1
  fi
  
  # Charger la configuration
  if [[ -n "$config_file" ]]; then
    cfg_charger "$config_file"
  fi
  
  # Copier le template vers la sortie
  if [[ $template != $sortie ]]; then
    cp "$template" "$sortie"
  fi
  
  # Trouver toutes les balises
  local -a balises
  mapfile -t balises < <(param_trouver_balises "$template")
  
  # Construire le mapping balise -> valeur
  declare -A valeurs
  
  for balise in "${balises[@]}"; do
    local valeur=""
    
    # Essayer depuis la config avec chemin complet si chemin_cas fourni
    if [[ -n "$chemin_cas" ]]; then
      # Essayer plusieurs formats de chemin
      valeur=$(cfg_obtenir_valeur_cascade "${balise}" "$chemin_cas" 2>/dev/null || echo "")
    fi
    
    if [[ -n "$valeur" ]]; then
      valeurs["$balise"]="$valeur"
    else
      if command -v _warn &>/dev/null; then
        _warn "Balise non résolue, laissée telle quelle: $balise"
      fi
    fi
  done
  
  # Appliquer les remplacements
  echo "────────────────────────────────────────"
  for balise in "${!valeurs[@]}"; do

    local valeur="${valeurs[$balise]}"
    param_remplacer_balise "$sortie" "$sortie" "$balise" "$valeur"

  done
  
  return 0
}
