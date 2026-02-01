#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  interface.sh — Interface commune pour tous les adaptateurs CFD
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Ce fichier définit le contrat que tous les adaptateurs doivent respecter.
#  Chaque adaptateur doit implémenter toutes ces fonctions.
#
#  Auteur : KL
#  Licence : MIT
# ═══════════════════════════════════════════════════════════════════════════════

# ── Vérification de CFD_FRAMEWORK ─────────────────────────────────────────────
if [[ -z "${CFD_FRAMEWORK:-}" ]]; then
  echo "ERREUR: Variable CFD_FRAMEWORK non définie" >&2
  exit 1
fi

# Charger format.sh si disponible
if [[ -f "${CFD_FRAMEWORK}/lib/format.sh" ]]; then
  source "${CFD_FRAMEWORK}/lib/format.sh"
fi

# ══════════════════════════════════════════════════════════════════════════════
#  🚫 FONCTION UTILITAIRE POUR FONCTIONS NON IMPLÉMENTÉES
# ══════════════════════════════════════════════════════════════════════════════

adapt_non_impl() {
  local fonction="$1"
  if command -v _error &>/dev/null; then
    _error "Fonction $fonction non implémentée dans cet adaptateur"
  else
    echo "ERREUR: Fonction $fonction non implémentée" >&2
  fi
  return 1
}

# ══════════════════════════════════════════════════════════════════════════════
#  📋 INTERFACE COMMUNE - STUBS PAR DÉFAUT
# ══════════════════════════════════════════════════════════════════════════════

# Informations sur l'adaptateur
adapt_nom() {
  adapt_non_impl "adapt_nom"
}

adapt_version() {
  adapt_non_impl "adapt_version"
}

adapt_description() {
  adapt_non_impl "adapt_description"
}

# Vérifications
adapt_verifier_installation() {
  adapt_non_impl "adapt_verifier_installation"
}

# Préparation et lancement
adapt_preparer_entree() {
  local rep_exec="$1"
  adapt_non_impl "adapt_preparer_entree"
}

adapt_lancer_calcul() {
  local rep_exec="$1"
  local nb_procs="${2:-1}"
  adapt_non_impl "adapt_lancer_calcul"d
}

adapt_lancer_parallele() {
  local rep_exec="$1"
  local nb_procs="${2:-1}"
  adapt_non_impl "adapt_lancer_parallele"
}

# Monitoring
adapt_verifier_etat() {
  local rep_exec="$1"
  adapt_non_impl "adapt_verifier_etat"
}

adapt_extraire_residus() {
  local rep_exec="$1"
  adapt_non_impl "adapt_extraire_residus"
}

adapt_extraire_qoi() {
  local rep_exec="$1"
  adapt_non_impl "adapt_extraire_qoi"
}

adapt_obtenir_iteration() {
  local rep_exec="$1"
  adapt_non_impl "adapt_obtenir_iteration"
}

# Post-traitement
adapt_extraire_champs() {
  local rep_exec="$1"
  adapt_non_impl "adapt_extraire_champs"
}

adapt_nettoyer() {
  local rep_exec="$1"
  adapt_non_impl "adapt_nettoyer"
}

# Liste des éléments à copier (pour wrapper)
adapt_liste_elements_a_copier() {
  adapt_non_impl "adapt_liste_elements_a_copier"
}
