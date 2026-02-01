#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  utils.sh — Utilitaires généraux réutilisables
# ═══════════════════════════════════════════════════════════════════════════════
#
#  📚 Fonctions disponibles :
#     • util_verifier_dependances()     # Vérifier outils requis
#     • util_resoudre_liens()            # Résoudre liens symboliques
#     • util_copier_recursif()           # Copie récursive intelligente
#     • util_obtenir_taille()           # Obtenir taille répertoire
#     • util_nettoyer_chemin()          # Normaliser chemin
#     • util_verifier_repertoire()      # Vérifier structure cas test
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

# Charger les bibliothèques
if [[ -z "${CFD_FRAMEWORK}" ]]; then
  echo "ERREUR: Variable CFD_FRAMEWORK non définie" >&2
  exit 1
fi

source "${CFD_FRAMEWORK}/lib/format.sh"

# ══════════════════════════════════════════════════════════════════════════════
#  🔍 VÉRIFICATION DES DÉPENDANCES
# ══════════════════════════════════════════════════════════════════════════════

# Vérifier la présence des outils requis
# Usage: util_verifier_dependances
util_verifier_dependances() {
  # Initialiser explicitement (évite "unbound variable" avec set -u)
  local -a manquants=()
  local -a optionnels_manquants=()
  
  # Outils requis
  local outils_requis=("bash" "git")
  # Outils optionnels mais recommandés
  local outils_optionnels=("yq" "rsync" "parallel" "tmux")
  
  for outil in "${outils_requis[@]}"; do
    if ! command -v "$outil" &>/dev/null; then
      manquants+=("$outil")
    fi
  done
  
  for outil in "${outils_optionnels[@]}"; do
    if ! command -v "$outil" &>/dev/null; then
      optionnels_manquants+=("$outil")
    fi
  done
  
  if [[ ${#manquants[@]} -gt 0 ]]; then
    if command -v _error &>/dev/null; then
      _error "Outils requis manquants: ${manquants[*]}"
    else
      echo "ERREUR: Outils requis manquants: ${manquants[*]}" >&2
    fi
    return 1
  fi
  
  if [[ ${#optionnels_manquants[@]} -gt 0 ]]; then
    if command -v _warn &>/dev/null; then
      _warn "Outils optionnels manquants: ${optionnels_manquants[*]}"
    else
      echo "AVERTISSEMENT: Outils optionnels manquants: ${optionnels_manquants[*]}" >&2
    fi
  fi
  
  return 0
}

# ══════════════════════════════════════════════════════════════════════════════
#  🔗 GESTION DES LIENS SYMBOLIQUES
# ══════════════════════════════════════════════════════════════════════════════

# Résoudre les liens symboliques en copiant les fichiers réels
# Usage: util_resoudre_liens REPERTOIRE
util_resoudre_liens() {
  local repertoire="$1"
  
  if [[ ! -d "$repertoire" ]]; then
    if command -v _error &>/dev/null; then
      _error "Répertoire inexistant: $repertoire"
    fi
    return 1
  fi
  
  # Trouver tous les liens symboliques et les remplacer par des copies
  while IFS= read -r -d '' lien; do
    local cible=$(readlink -f "$lien")
    if [[ -e "$cible" ]]; then
      rm "$lien"
      if [[ -d "$cible" ]]; then
        cp -r "$cible" "$lien"
      else
        cp "$cible" "$lien"
      fi
    fi
  done < <(find "$repertoire" -type l -print0)
}

# ══════════════════════════════════════════════════════════════════════════════
#  📋 COPIE RÉCURSIVE INTELLIGENTE
# ══════════════════════════════════════════════════════════════════════════════

# Copie récursive avec rsync si disponible, sinon cp
# Usage: util_copier_recursif SOURCE DESTINATION
util_copier_recursif() {
  local source="$1"
  _debug $source
  local dest="$2"
  
  if [[ ! -e "$source" ]]; then
    if command -v _error &>/dev/null; then
      _error "Source inexistante: $source"
    fi
    return 1
  fi

  if [[ ! -e "$dest" ]]; then
    if command -v _error &>/dev/null; then
      _error "Destination inexistante: $dest"
    fi
    return 1
  fi
  
  if command -v rsync &>/dev/null; then
    rsync -a "$source" "$dest"
  else
    if [[ -d "$source" ]]; then
      cp -r $source/* $dest
    else
      cp $source $dest
    fi
  fi
}

# ══════════════════════════════════════════════════════════════════════════════
#  📏 TAILLE DES FICHIERS/RÉPERTOIRES
# ══════════════════════════════════════════════════════════════════════════════

# Obtenir la taille d'un fichier ou répertoire (format human-readable)
# Usage: util_obtenir_taille CHEMIN
util_obtenir_taille() {
  local chemin="$1"
  
  if [[ ! -e "$chemin" ]]; then
    echo "0"
    return 1
  fi
  
  if command -v du &>/dev/null; then
    du -sh "$chemin" 2>/dev/null | cut -f1
  else
    echo "N/A"
  fi
}

# ══════════════════════════════════════════════════════════════════════════════
#  🧹 NETTOYAGE DE CHEMINS
# ══════════════════════════════════════════════════════════════════════════════

# Normaliser un chemin (absolu, sans //)
# Usage: util_nettoyer_chemin CHEMIN
util_nettoyer_chemin() {
  local chemin="$1"
  
  if command -v realpath &>/dev/null; then
    realpath "$chemin" 2>/dev/null || echo "$chemin"
  elif command -v readlink &>/dev/null; then
    readlink -f "$chemin" 2>/dev/null || echo "$chemin"
  else
    # Fallback: nettoyage basique
    echo "$chemin" | sed 's|//|/|g'
  fi
}

# ══════════════════════════════════════════════════════════════════════════════
#  ✅ VÉRIFICATION DE STRUCTURE
# ══════════════════════════════════════════════════════════════════════════════

# Vérifier la structure d'un répertoire cas test
# Usage: util_verifier_repertoire REPERTOIRE_CAS
util_verifier_repertoire() {
  local rep_cas="$1"
  # Initialiser explicitement (évite "unbound variable" avec set -u)
  local -a manquants=()
  
  # Répertoires attendus selon le plan
  local repertoires_attendus=(
    "01_MAILLAGE"
    "02_PARAMS"
    "03_DECOMPOSITION"
    "04_CONDITION_INITIALE"
    "05_DOCUMENTATION"
    "06_REFERENCE"
    "07_NOTE"
    "08_RESULTAT"
    "09_POST_TRAITEMENT"
    "10_SCRIPT"
  )
  
  for rep in "${repertoires_attendus[@]}"; do
    if [[ ! -d "${rep_cas}/${rep}" ]]; then
      manquants+=("$rep")
    fi
  done
  
  if [[ ${#manquants[@]} -gt 0 ]]; then
    if command -v _warn &>/dev/null; then
      _warn "Répertoires manquants dans $rep_cas: ${manquants[*]}"
    else
      echo "AVERTISSEMENT: Répertoires manquants: ${manquants[*]}" >&2
    fi
    return 1
  fi
  
  return 0
}
