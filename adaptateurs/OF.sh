#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  OF.sh — Adaptateur OpenFOAM pour le framework CFD
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Cet adaptateur permet d'utiliser OpenFOAM avec le framework CFD.
#  Compatible avec OpenFOAM v13+ (foamRun).
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
  [[ -f "${CFD_FRAMEWORK}/lib/utils.sh" ]] && source "${CFD_FRAMEWORK}/lib/utils.sh"
fi

# ══════════════════════════════════════════════════════════════════════════════
#  📋 INFORMATIONS SUR L'ADAPTATEUR
# ══════════════════════════════════════════════════════════════════════════════

adapt_nom() {
  echo "OF"
}

adapt_version() {
    echo "${WM_PROJECT_VERSION}"
}

adapt_description() {
  echo "Adaptateur OpenFOAM (foamRun)"
}

# ══════════════════════════════════════════════════════════════════════════════
#  ✅ VÉRIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════

adapt_verifier_installation() {
  # Vérifier que foamRun est disponible
  if ! command -v foamRun &>/dev/null; then
    if command -v _error &>/dev/null; then
      _error "foamRun non trouvé - veuillez charger votre environnement OpenFOAM"
    else
      echo "ERREUR: foamRun non trouvé" >&2
    fi
    return 1
  fi
  
  return 0
}

# ══════════════════════════════════════════════════════════════════════════════
#  📁 HELPER: LISTE DES ÉLÉMENTS À COPIER (pour wrapper)
# ══════════════════════════════════════════════════════════════════════════════

# Cette fonction n'est pas dans l'interface standard mais est utilisée
# par wrapper_commande_lancement.sh pour savoir quoi copier
adapt_liste_elements_a_copier() {
  echo "0/"
  echo "constant/"
  echo "system/"
  echo ".metadata.yaml"
}

# ══════════════════════════════════════════════════════════════════════════════
#  🚀 PRÉPARATION ET LANCEMENT
# ══════════════════════════════════════════════════════════════════════════════

adapt_preparer_entree() {
  local rep_exec="$1"
  
  # Convertir en chemin absolu si nécessaire
  if [[ ! "$rep_exec" =~ ^/ ]]; then
    rep_exec="$(cd "$(dirname "$rep_exec")" 2>/dev/null && pwd)/$(basename "$rep_exec")"
  fi
  
  if [[ ! -d "$rep_exec" ]]; then
    if command -v _error &>/dev/null; then
      _error "Répertoire d'exécution inexistant: $rep_exec"
    fi
    return 1
  fi
  
  # Pour OpenFOAM, la préparation consiste principalement à s'assurer
  # que le répertoire LOG existe
  mkdir -p "${rep_exec}/LOG"
  
  if command -v _info &>/dev/null; then
    _info "Préparation OpenFOAM terminée"
  fi
  
  return 0
}

adapt_lancer_calcul() {
  local rep_exec="$1"
  local nb_procs="${2:-1}"
  
  # Vérifier que le répertoire existe
  if [[ ! -d "$rep_exec" ]]; then
    if command -v _error &>/dev/null; then
      _error "Répertoire d'exécution inexistant: $rep_exec"
    fi
    return 1
  fi
  
  # Se déplacer dans le répertoire d'exécution
  cd "$rep_exec" || return 1
  
  # Créer le répertoire de logs si nécessaire
  mkdir -p LOG
  
  if command -v _info &>/dev/null; then
    _info "Lancement de foamRun (single processor)..."
  fi
  
  # Lancer foamRun avec redirection vers LOG/foamRun.log
  # foamRun 2>&1 | tee "LOG/foamRun.log"
  foamRun > LOG/foamRun.log 2>&1
  
  # Récupérer le code de sortie de foamRun (pas de tee)
  local exit_code="${PIPESTATUS[0]}"
  
  if [[ $exit_code -eq 0 ]]; then
    if command -v _result &>/dev/null; then
      _result "Calcul OpenFOAM terminé avec succès"
    fi
  else
    if command -v _error &>/dev/null; then
      _error "Calcul OpenFOAM échoué avec le code: $exit_code"
    fi
  fi
  
  return "$exit_code"
}

adapt_lancer_parallele() {
  local rep_exec="$1"
  local nb_procs="${2:-1}"
  
  if command -v _warn &>/dev/null; then
    _warn "Lancement parallèle non implémenté - utilisation du mode série"
  fi
  
  # Pour l'instant, on redirige vers le lancement série
  adapt_lancer_calcul "$rep_exec" "$nb_procs"
}

# ══════════════════════════════════════════════════════════════════════════════
#  👁️ MONITORING
# ══════════════════════════════════════════════════════════════════════════════

adapt_verifier_etat() {
  local rep_exec="$1"
  local log_file="${rep_exec}/LOG/foamRun.log"
  
  if [[ ! -f "$log_file" ]]; then
    echo "NOT_STARTED"
    return 0
  fi
  
  # Vérifier si le calcul est terminé (chercher des patterns de fin)
  if grep -q "End" "$log_file" 2>/dev/null; then
    echo "DONE"
  elif grep -q "FOAM FATAL" "$log_file" 2>/dev/null; then
    echo "FAILED"
  else
    echo "RUNNING"
  fi
  
  return 0
}

adapt_extraire_residus() {
  local rep_exec="$1"
  local log_file="${rep_exec}/LOG/foamRun.log"
  
  if [[ ! -f "$log_file" ]]; then
    return 1
  fi
  
  # Extraire les résidus (pattern simplifié)
  # Format typique: "Solving for Ux, Initial residual = 1.234e-05"
  grep "Initial residual" "$log_file" 2>/dev/null | awk '{print $NF}' || true
  
  return 0
}

adapt_extraire_qoi() {
  local rep_exec="$1"
  
  # Pour OpenFOAM, on pourrait extraire des forces, coefficients, etc.
  # Pour l'instant, retourner un message simple
  if [[ -d "${rep_exec}/postProcessing" ]]; then
    echo "# Quantités d'intérêt disponibles dans: ${rep_exec}/postProcessing"
    find "${rep_exec}/postProcessing" -type f -name "*.dat" 2>/dev/null | head -5 || true
  else
    echo "# Aucune quantité d'intérêt disponible"
  fi
  
  return 0
}

adapt_obtenir_iteration() {
  local rep_exec="$1"
  
  # Compter le nombre de répertoires de temps
  if [[ -d "$rep_exec" ]]; then
    # Lister les répertoires qui sont des nombres (temps)
    local max_time=$(find "$rep_exec" -maxdepth 1 -type d -name "[0-9]*" -o -name "[0-9]*.[0-9]*" 2>/dev/null | \
      sed 's|.*/||' | sort -n | tail -1)
    
    if [[ -n "$max_time" ]]; then
      echo "$max_time"
    else
      echo "0"
    fi
  else
    echo "0"
  fi
  
  return 0
}

# ══════════════════════════════════════════════════════════════════════════════
#  📊 POST-TRAITEMENT
# ══════════════════════════════════════════════════════════════════════════════

adapt_extraire_champs() {
  local rep_exec="$1"
  
  if command -v _info &>/dev/null; then
    _info "Extraction des champs OpenFOAM..."
  fi
  
  # Pour OpenFOAM, les champs sont déjà dans les répertoires de temps
  # On pourrait lancer foamToVTK ici
  if [[ -d "$rep_exec" ]]; then
    cd "$rep_exec" || return 1
    
    # Créer un fichier récapitulatif
    local output="${rep_exec}/champs.txt"
    {
      echo "# Champs OpenFOAM disponibles"
      echo "# Répertoire: $rep_exec"
      echo ""
      echo "## Répertoires de temps:"
      find . -maxdepth 1 -type d -name "[0-9]*" -o -name "[0-9]*.[0-9]*" | sort -n
    } > "$output"
    
    echo "$output"
  fi
  
  return 0
}

adapt_nettoyer() {
  local rep_exec="$1"
  
  if command -v _info &>/dev/null; then
    _info "Nettoyage des fichiers temporaires OpenFOAM..."
  fi
  
  # Nettoyer les fichiers temporaires typiques d'OpenFOAM
  if [[ -d "$rep_exec" ]]; then
    cd "$rep_exec" || return 1
    
    # Supprimer les fichiers de processeurs si présents (décomposition)
    rm -rf processor* 2>/dev/null || true
    
    # Supprimer les fichiers dynamicCode
    rm -rf dynamicCode 2>/dev/null || true
    
    if command -v _result &>/dev/null; then
      _result "Nettoyage terminé"
    fi
  fi
  
  return 0
}
