#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  test_sprint1_2.sh — Tests end-to-end pour Sprints 1 & 2
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail
IFS=$'\n\t'

# Charger les bibliothèques
if [[ -z "${CFD_FRAMEWORK}" ]]; then
  echo "ERREUR: Variable CFD_FRAMEWORK non définie" >&2
  exit 1
fi
# Configuration
TEST_DIR="${CFD_FRAMEWORK}/tests/exemple_cas"

export CFD_FRAMEWORK
export CFD_ADAPTATEUR="mock"

# Charger format.sh
source "${CFD_FRAMEWORK}/lib/format.sh"

# ══════════════════════════════════════════════════════════════════════════════
#  🧪 TESTS
# ══════════════════════════════════════════════════════════════════════════════

title "Tests Sprint 1 & 2"

# Test 1: Vérifier que les bibliothèques se chargent
h1 "Test 1: Chargement des bibliothèques"
source "${CFD_FRAMEWORK}/lib/gestion_timestamps.sh"
source "${CFD_FRAMEWORK}/lib/utils.sh"
source "${CFD_FRAMEWORK}/lib/gestion_config.sh"
source "${CFD_FRAMEWORK}/lib/substitution_params.sh"
_result "Bibliothèques chargées"

# Test 2: Génération de timestamp
h1 "Test 2: Génération de timestamp"
timestamp=$(ts_generer)
_info "Timestamp généré: $timestamp"
if [[ "$timestamp" =~ ^[0-9]{8}_[0-9]{6}$ ]]; then
  _result "Format timestamp valide"
else
  _error "Format timestamp invalide"
  exit 1
fi

# Test 3: Chargement de configuration
h1 "Test 3: Chargement de configuration"
config_file="${TEST_DIR}/02_PARAMS/config.yaml"
if [[ -f "$config_file" ]]; then
  cfg_charger "$config_file"
  adaptateur=$(cfg_obtenir_valeur "adaptateur")
  _info "Adaptateur: $adaptateur"
  if [[ "$adaptateur" == "mock" ]]; then
    _result "Configuration chargée correctement"
  else
    _error "Adaptateur incorrect: $adaptateur"
    exit 1
  fi
else
  _error "Fichier config.yaml introuvable: $config_file"
  exit 1
fi

# Test 4: Substitution de paramètres
h1 "Test 4: Substitution de paramètres"
template_file="${TEST_DIR}/02_PARAMS/BASELINE/template/solver_input.org"
if [[ -f "$template_file" ]]; then
  output_file="${TEST_DIR}/solver_input_test"
  # Exporter les paramètres comme variables d'environnement pour le test
  export angle_attaque="5.0"
  export reynolds="6000000.0"
  export maillage="mesh_coarse.cgns"
  export nb_iterations="10000"
  
  param_substituer_tout "$template_file" "$output_file" "$config_file"
  
  if [[ -f "$output_file" ]]; then
    if grep -q "angle_of_attack = 5.0" "$output_file"; then
      _result "Substitution réussie"
      rm -f "$output_file"
    else
      _error "Substitution échouée"
      cat "$output_file"
      exit 1
    fi
  else
    _error "Fichier de sortie non créé"
    exit 1
  fi
else
  _error "Template introuvable: $template_file"
  exit 1
fi

# Test 5: Lancement d'un cas mock
h1 "Test 5: Lancement cas mock"
cd "$TEST_DIR" || exit 1

# Lancer le cas
if "${CFD_FRAMEWORK}/bin/cfd-lancer" BASELINE --cas CASE_1; then
  _result "Lancement réussi"
else
  _error "Lancement échoué"
  exit 1
fi

# Vérifier les résultats
h1 "Test 6: Vérification des résultats"
cas_dir=$(find 02_PARAMS/BASELINE -name "CASE_1_*" -type d | head -1)
if [[ -n "$cas_dir" ]] && [[ -d "$cas_dir" ]]; then
  _info "Répertoire cas trouvé: $cas_dir"
  
  # Vérifier fichiers attendus
  local erreurs=0
  [[ -f "${cas_dir}/log.mock" ]] || { _error "log.mock manquant"; ((erreurs++)); }
  [[ -f "${cas_dir}/solver_input" ]] || { _error "solver_input manquant"; ((erreurs++)); }
  [[ -f "${cas_dir}/.timestamp" ]] || { _error ".timestamp manquant"; ((erreurs++)); }
  
  if [[ $erreurs -eq 0 ]]; then
    _result "Tous les fichiers attendus sont présents"
    
    # Afficher un extrait du log
    _info "Extrait du log:"
    head -n 5 "${cas_dir}/log.mock" | while IFS= read -r ligne; do
      _bullet "$ligne"
    done
  else
    _error "$erreurs fichier(s) manquant(s)"
    exit 1
  fi
else
  _error "Répertoire cas non trouvé"
  exit 1
fi

# Nettoyage optionnel
if [[ "${CLEANUP:-false}" == "true" ]]; then
  h1 "Nettoyage"
  rm -rf "${TEST_DIR}/02_PARAMS/BASELINE/CASE_1_"*
  _result "Nettoyage effectué"
fi

separator_eq
_result "Tous les tests sont passés avec succès!"
