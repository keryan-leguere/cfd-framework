#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  gestion_timestamps.sh — Gestion des timestamps pour répertoires horodatés
# ═══════════════════════════════════════════════════════════════════════════════
#
#  📚 Fonctions disponibles :
#     • ts_generer()                    # Générer timestamp YYYYMMDD_HHMMSS
#     • ts_creer_repertoire()           # Créer répertoire avec timestamp
#     • ts_supprimer_timestamp()        # Retirer timestamp d'un nom
#     • ts_extraire_timestamp()         # Extraire timestamp d'un chemin
#     • ts_trier_par_date()             # Trier répertoires par date
#     • ts_plus_recent()                # Obtenir répertoire le plus récent
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

# ══════════════════════════════════════════════════════════════════════════════
#  🕐 GÉNÉRATION DE TIMESTAMPS
# ══════════════════════════════════════════════════════════════════════════════

# Générer un timestamp au format YYYYMMDD_HHMMSS
ts_generer() {
  date +"%Y%m%d_%H%M%S"
}

# ══════════════════════════════════════════════════════════════════════════════
#  📁 GESTION DES RÉPERTOIRES HORODATÉS
# ══════════════════════════════════════════════════════════════════════════════

# Créer un répertoire avec timestamp
# Usage: ts_creer_repertoire BASE_DIR PREFIX
# Retourne le chemin complet du répertoire créé
ts_creer_repertoire() {
  local base_dir="$1"
  local prefix="${2:-CAS}"
  local timestamp=$(ts_generer)
  local nom_repertoire="${prefix}_${timestamp}"
  local chemin_complet="${base_dir}/${nom_repertoire}"
  
  mkdir -p "$chemin_complet"
  echo "$chemin_complet"
}

# Supprimer le timestamp d'un nom de répertoire
# Usage: ts_supprimer_timestamp "CAS_1_20260126_143052" -> "CAS_1"
ts_supprimer_timestamp() {
  local nom="$1"
  # Supprime le pattern _YYYYMMDD_HHMMSS à la fin
  echo "$nom" | sed -E 's/_[0-9]{8}_[0-9]{6}$//'
}

# Extraire uniquement le timestamp d'un chemin
# Usage: ts_extraire_timestamp "CAS_1_20260126_143052" -> "20260126_143052"
ts_extraire_timestamp() {
  local chemin="$1"
  local nom=$(basename "$chemin")
  # Extrait le pattern _YYYYMMDD_HHMMSS
  if [[ "$nom" =~ _([0-9]{8}_[0-9]{6})$ ]]; then
    echo "${BASH_REMATCH[1]}"
  else
    echo ""
  fi
}

# Trier une liste de répertoires par timestamp (croissant)
# Usage: ts_trier_par_date "02_PARAMS/BASELINE/"*
ts_trier_par_date() {
  local dirs=("$@")
  local -a timestamps
  local -a sorted
  
  for dir in "${dirs[@]}"; do
    local ts=$(ts_extraire_timestamp "$dir")
    if [[ -n "$ts" ]]; then
      timestamps+=("${ts}|${dir}")
    fi
  done
  
  # Trier par timestamp
  IFS=$'\n' sorted=($(printf '%s\n' "${timestamps[@]}" | sort -t'|' -k1))
  
  # Afficher les chemins triés
  for item in "${sorted[@]}"; do
    echo "${item#*|}"
  done
}

# Obtenir le répertoire le plus récent parmi une liste
# Usage: ts_plus_recent "02_PARAMS/BASELINE/"*
ts_plus_recent() {
  local dirs=("$@")
  local -a timestamps
  
  for dir in "${dirs[@]}"; do
    local ts=$(ts_extraire_timestamp "$dir")
    if [[ -n "$ts" ]]; then
      timestamps+=("${ts}|${dir}")
    fi
  done
  
  if [[ ${#timestamps[@]} -eq 0 ]]; then
    return 1
  fi
  
  # Trier et prendre le dernier (le plus récent)
  IFS=$'\n' sorted=($(printf '%s\n' "${timestamps[@]}" | sort -t'|' -k1))
  echo "${sorted[-1]#*|}"
}