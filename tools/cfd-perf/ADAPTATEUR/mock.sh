#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  mock.sh — Adaptateur de capture simulé (aucun solveur, aucun SLURM)
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Simule des runs pilotes pour tester toute la chaîne capture → YAML →
#  recommandation sans solveur CFD ni ordonnanceur. « Soumettre » exécute le run
#  de façon SYNCHRONE et écrit un run.log analysable ; l'état est DONE aussitôt.
#
#  Le temps total suit une loi de scalabilité forte réaliste
#     T(cores) = n_iter · (t_ser + t_par/cores + t_comm·cores^γ)
#  de sorte que les points capturés forment une vraie courbe en U.
#
#  Licence : MIT
# ═══════════════════════════════════════════════════════════════════════════════

_ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${_ICI}/interface.sh"

# Constantes de la loi synthétique (secondes par itération).
_MOCK_N_ITER=200
_MOCK_T_SER=0.5
_MOCK_T_PAR=120.0
_MOCK_T_COMM=0.000002
_MOCK_GAMMA=1.7

adapt_nom() { echo "mock"; }
adapt_description() { echo "Adaptateur de capture simulé (sans solveur ni SLURM)"; }
adapt_verifier_installation() { return 0; }
adapt_liste_elements_a_copier() { echo "constant"; echo "system"; }

adapt_pilote_preparer() {
  local run_dir="$1" cores="$2"
  mkdir -p "$run_dir"
  echo "$cores" > "${run_dir}/.cores"
  return 0
}

adapt_pilote_soumettre() {
  local run_dir="$1" cores="$2"
  mkdir -p "$run_dir"

  local temps ram
  temps=$(awk -v n="$_MOCK_N_ITER" -v ts="$_MOCK_T_SER" -v tp="$_MOCK_T_PAR" \
              -v tc="$_MOCK_T_COMM" -v g="$_MOCK_GAMMA" -v c="$cores" \
    'BEGIN { printf "%.4f", n * (ts + tp / c + tc * (c ^ g)) }')
  ram=$(awk -v c="$cores" 'BEGIN { printf "%.4f", 8.0 + c * 0.05 }')

  {
    echo "=== Run pilote mock ==="
    echo "Cores: $cores"
    echo "Iterations: $_MOCK_N_ITER"
    echo "TempsTotal_s: $temps"
    echo "RAM_Go: $ram"
    echo "=== Termine ==="
  } > "${run_dir}/run.log"

  echo "LOCAL"
  return 0
}

adapt_pilote_etat() {
  local run_dir="$1"
  if [[ -f "${run_dir}/run.log" ]] && grep -q "=== Termine ===" "${run_dir}/run.log"; then
    echo "DONE"
  else
    echo "PENDING"
  fi
}

adapt_pilote_temps_total() {
  local run_dir="$1"
  awk -F': ' '/^TempsTotal_s:/ {print $2; exit}' "${run_dir}/run.log"
}

adapt_pilote_nb_iterations() {
  local run_dir="$1"
  awk -F': ' '/^Iterations:/ {print $2; exit}' "${run_dir}/run.log"
}

adapt_pilote_ram_crete() {
  local run_dir="$1"
  awk -F': ' '/^RAM_Go:/ {print $2; exit}' "${run_dir}/run.log"
}

adapt_maillage_nb_cellules() {
  local case_dir="$1"
  if [[ -f "${case_dir}/.mock_cells" ]]; then
    cat "${case_dir}/.mock_cells"
  else
    echo "2000000"
  fi
}

adapt_cible_iterations() {
  # PLACEHOLDER : dans un vrai adaptateur, extraire d'un fichier de contrôle
  # via sed. Ici, valeur lisible depuis un marqueur, sinon défaut.
  local case_dir="$1"
  if [[ -f "${case_dir}/.mock_niter" ]]; then
    cat "${case_dir}/.mock_niter"
  else
    echo "5000"
  fi
}
