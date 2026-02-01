#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  mock.sh — Adaptateur de test/développement qui simule un solveur CFD
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Cet adaptateur simule un calcul CFD pour tester le framework sans solveur réel.
#
#  Auteur : KL
#  Licence : MIT
# ═══════════════════════════════════════════════════════════════════════════════

# Charger l'interface commune
if [[ -n "${CFD_FRAMEWORK:-}" ]] && [[ -f "${CFD_FRAMEWORK}/adaptateurs/interface.sh" ]]; then
  source "${CFD_FRAMEWORK}/adaptateurs/interface.sh"
else
  echo "ERREUR: Impossible de charger interface.sh" >&2
  exit 1
fi

# Charger les bibliothèques nécessaires
if [[ -n "${CFD_FRAMEWORK:-}" ]]; then
  [[ -f "${CFD_FRAMEWORK}/lib/format.sh" ]] && source "${CFD_FRAMEWORK}/lib/format.sh"
  [[ -f "${CFD_FRAMEWORK}/lib/gestion_config.sh" ]] && source "${CFD_FRAMEWORK}/lib/gestion_config.sh"
  [[ -f "${CFD_FRAMEWORK}/lib/substitution_params.sh" ]] && source "${CFD_FRAMEWORK}/lib/substitution_params.sh"
fi

# ══════════════════════════════════════════════════════════════════════════════
#  📋 INFORMATIONS SUR L'ADAPTATEUR
# ══════════════════════════════════════════════════════════════════════════════

adapt_nom() {
  echo "mock"
}

adapt_version() {
  echo "1.0"
}

adapt_description() {
  echo "Adaptateur de test qui simule un solveur CFD"
}

# ══════════════════════════════════════════════════════════════════════════════
#  ✅ VÉRIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════

adapt_verifier_installation() {
  # Pas de dépendances externes pour mock
  return 0
}

# ══════════════════════════════════════════════════════════════════════════════
#  🚀 PRÉPARATION ET LANCEMENT
# ══════════════════════════════════════════════════════════════════════════════

adapt_preparer_entree() {
  local rep_exec="$1"
  local original_dir=$(pwd)
  
  # Convertir en chemin absolu si nécessaire (sans doubler)
  if [[ ! "$rep_exec" =~ ^/ ]]; then
    # Le chemin est relatif, le rendre absolu depuis le répertoire courant
    rep_exec="${original_dir}/${rep_exec}"
    # Normaliser (supprimer les .. et .)
    rep_exec=$(cd "$(dirname "$rep_exec")" 2>/dev/null && echo "$(pwd)/$(basename "$rep_exec")" || echo "$rep_exec")
  fi
  
  if [[ ! -d "$rep_exec" ]]; then
    if command -v _error &>/dev/null; then
      _error "Répertoire d'exécution inexistant: $rep_exec"
    fi
    return 1
  fi
  
  cd "$rep_exec" || return 1
  
  # Chercher les fichiers .org et les convertir
  if command -v _info &>/dev/null; then
    _info "Préparation des fichiers d'entrée..."
  fi
  
  # Si generer_jeu_donnees.sh est disponible, l'utiliser
  if [[ -n "${CFD_FRAMEWORK:-}" ]] && [[ -f "${CFD_FRAMEWORK}/scripts/lancement/generer_jeu_donnees.sh" ]]; then
    source "${CFD_FRAMEWORK}/scripts/lancement/generer_jeu_donnees.sh"
    local template_dir="${rep_exec}/template"
    if [[ -d "$template_dir" ]]; then
      # Chercher config.yaml dans le répertoire ou parent
      local config_file=""
      if [[ -f "${rep_exec}/config.yaml" ]]; then
        config_file="${rep_exec}/config.yaml"
      elif [[ -f "${rep_exec}/../config.yaml" ]]; then
        config_file="${rep_exec}/../config.yaml"
      elif [[ -f "${rep_exec}/../../config.yaml" ]]; then
        config_file="${rep_exec}/../../config.yaml"
      fi
      
      if [[ -n "$config_file" ]]; then
        generer_jeu_donnees "$template_dir" "$rep_exec" "$config_file" "${CFD_CHEMIN_CAS:-}" 2>/dev/null || true
      fi
    fi
  fi
  
  # Fallback: chercher solver_input.org et le convertir directement
  if [[ -f "${rep_exec}/solver_input.org" ]]; then
    if command -v param_substituer_tout &>/dev/null; then
      local config_file=""
      [[ -f "${rep_exec}/config.yaml" ]] && config_file="${rep_exec}/config.yaml"
      [[ -z "$config_file" ]] && [[ -f "${rep_exec}/../config.yaml" ]] && config_file="${rep_exec}/../config.yaml"
      
      if [[ -n "$config_file" ]]; then
        param_substituer_tout "${rep_exec}/solver_input.org" "${rep_exec}/solver_input" "$config_file" "${CFD_CHEMIN_CAS:-}"
      else
        cp "${rep_exec}/solver_input.org" "${rep_exec}/solver_input"
      fi
    else
      cp "${rep_exec}/solver_input.org" "${rep_exec}/solver_input"
    fi
  fi
  
  return 0
}

adapt_lancer_calcul() {
  local rep_exec="$1"
  local nb_procs="${2:-1}"
  
  # Le chemin devrait déjà être absolu depuis lancer_cas_unique
  # Vérifier simplement qu'il existe
  if [[ ! -d "$rep_exec" ]]; then
    if command -v _error &>/dev/null; then
      _error "Répertoire d'exécution inexistant: $rep_exec"
      _error "Répertoire courant: $(pwd)"
    fi
    return 1
  fi
  
  cd "$rep_exec" || return 1
  
  if command -v _info &>/dev/null; then
    _info "Lancement du calcul mock (simulation)..."
  fi
  
  local log_file="log.mock"
  local nb_iterations=100
  
  # Simuler un calcul avec progression
  {
    echo "=== Calcul CFD Mock ==="
    echo "Itérations: $nb_iterations"
    echo "Processeurs: $nb_procs"
    echo ""
    
    for ((i=1; i<=nb_iterations; i++)); do
      # Calculer résidus décroissants
      local residu=$(awk "BEGIN {printf \"%.6e\", 1.0 / ($i * 0.1 + 1)}")
      
      if (( i % 10 == 0 )); then
        echo "Itération $i: Résidu = $residu"
      fi
      
      # Sleep court pour simuler le calcul
      sleep 0.01
    done
    
    echo ""
    echo "=== Calcul terminé ==="
    echo "Itérations finales: $nb_iterations"
    echo "Résidu final: $(awk 'BEGIN {printf "%.6e", 1.0 / (100 * 0.1 + 1)}')"
  } > "$log_file"
  
  # Créer un fichier de sortie factice
  echo "# Résultats CFD Mock" > "resultats.mock"
  echo "Convergence: OUI" >> "resultats.mock"
  echo "Itérations: $nb_iterations" >> "resultats.mock"
  echo "Résidu final: $(awk 'BEGIN {printf "%.6e", 1.0 / (100 * 0.1 + 1)}')" >> "resultats.mock"
  
  if command -v _result &>/dev/null; then
    _result "Calcul mock terminé: $log_file"
  fi
  
  return 0
}

adapt_lancer_parallele() {
  # Pour mock, identique à adapt_lancer_calcul
  adapt_lancer_calcul "$@"
}

# ══════════════════════════════════════════════════════════════════════════════
#  👁️ MONITORING
# ══════════════════════════════════════════════════════════════════════════════

adapt_verifier_etat() {
  local rep_exec="$1"
  local log_file="${rep_exec}/log.mock"
  
  if [[ ! -f "$log_file" ]]; then
    echo "NOT_STARTED"
    return 0
  fi
  
  if grep -q "=== Calcul terminé ===" "$log_file" 2>/dev/null; then
    echo "DONE"
  else
    echo "RUNNING"
  fi
  
  return 0
}

adapt_extraire_residus() {
  local rep_exec="$1"
  local log_file="${rep_exec}/log.mock"
  
  if [[ ! -f "$log_file" ]]; then
    return 1
  fi
  
  # Extraire les résidus du log
  grep "Résidu" "$log_file" | awk '{print $NF}'
}

adapt_extraire_qoi() {
  local rep_exec="$1"
  local resultats_file="${rep_exec}/resultats.mock"
  
  if [[ -f "$resultats_file" ]]; then
    cat "$resultats_file"
  else
    echo "QoI non disponibles"
  fi
}

adapt_obtenir_iteration() {
  local rep_exec="$1"
  local log_file="${rep_exec}/log.mock"
  
  if [[ ! -f "$log_file" ]]; then
    echo "0"
    return 0
  fi
  
  # Extraire la dernière itération mentionnée
  grep "Itération" "$log_file" | tail -1 | awk '{print $2}' || echo "0"
}

# ══════════════════════════════════════════════════════════════════════════════
#  📊 POST-TRAITEMENT
# ══════════════════════════════════════════════════════════════════════════════

adapt_extraire_champs() {
  local rep_exec="$1"
  
  # Pour mock, créer un fichier factice
  echo "# Champs CFD Mock" > "${rep_exec}/champs.mock"
  echo "Format: VTK" >> "${rep_exec}/champs.mock"
  echo "Fichiers: resultats.mock" >> "${rep_exec}/champs.mock"
  
  echo "${rep_exec}/champs.mock"
}

adapt_nettoyer() {
  local rep_exec="$1"
  
  if command -v _info &>/dev/null; then
    _info "Nettoyage des fichiers temporaires mock..."
  fi
  
  # Supprimer les fichiers temporaires si nécessaire
  # Pour mock, on garde tout par défaut
  return 0
}

# Liste des éléments à copier (pour wrapper)
adapt_liste_elements_a_copier() {
  # Pour mock, on copie tout ce qui n'est pas un répertoire de résultats
  echo "0"
  echo "constant"
  echo "system"
}
