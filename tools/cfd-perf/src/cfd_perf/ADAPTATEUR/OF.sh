#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  OF.sh — Adaptateur de capture OpenFOAM (référence)
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Adaptateur de référence pour OpenFOAM v13+ (foamRun). Il montre comment
#  implémenter le contrat de capture pour un vrai solveur avec SLURM. Il ne peut
#  pas être testé sans OpenFOAM ni ordonnanceur : servez-vous-en comme modèle et
#  adaptez les commandes à votre installation.
#
#  Points d'attention marqués « ADAPTER » : à ajuster selon votre cas.
#  Licence : MIT
# ═══════════════════════════════════════════════════════════════════════════════

_ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${CFD_PERF_INTERFACE:-${_ICI}/interface.sh}"

adapt_nom() { echo "OF"; }
adapt_description() { echo "Adaptateur de capture OpenFOAM (foamRun)"; }

adapt_verifier_installation() {
  if ! command -v foamRun &>/dev/null; then
    _error "foamRun introuvable — chargez votre environnement OpenFOAM"
    return 1
  fi
  return 0
}

adapt_liste_elements_a_copier() {
  echo "0"
  echo "constant"
  echo "system"
}

# Prépare la décomposition pour <cores> sous-domaines.
adapt_pilote_preparer() {
  local run_dir="$1" cores="$2"
  mkdir -p "${run_dir}/LOG"
  local dict="${run_dir}/system/decomposeParDict"
  if [[ -f "$dict" ]]; then
    # ADAPTER : remplace le nombre de sous-domaines par <cores>.
    sed -i "s/^numberOfSubdomains.*/numberOfSubdomains ${cores};/" "$dict"
  else
    _warn "system/decomposeParDict absent — décomposition scotch par défaut"
    cat > "$dict" <<EOF
FoamFile { version 2.0; format ascii; class dictionary; object decomposeParDict; }
numberOfSubdomains ${cores};
method scotch;
EOF
  fi
  ( cd "$run_dir" && decomposePar -force > LOG/decomposePar.log 2>&1 ) || {
    _error "decomposePar a échoué (voir LOG/decomposePar.log)"; return 1;
  }
  return 0
}

# Soumet le run. SLURM si dispo (ou queue fournie), sinon mpirun local synchrone.
adapt_pilote_soumettre() {
  local run_dir="$1" cores="$2" queue="${3:-}"
  mkdir -p "${run_dir}/LOG"

  if command -v sbatch &>/dev/null; then
    local script="${run_dir}/pilote.sbatch"
    # ADAPTER : partition, temps, modules, commande solveur.
    cat > "$script" <<EOF
#!/usr/bin/env bash
#SBATCH --job-name=cfdperf_pilote
#SBATCH --ntasks=${cores}
${queue:+#SBATCH --partition=${queue}}
#SBATCH --output=${run_dir}/LOG/foamRun.log
#SBATCH --error=${run_dir}/LOG/foamRun.log
cd "${run_dir}" || exit 1
mpirun -np ${cores} foamRun -parallel
EOF
    local job_id
    job_id=$(sbatch --parsable "$script") || { _error "sbatch a échoué"; return 1; }
    echo "$job_id"
    return 0
  fi

  # Repli local : lancement synchrone (bloquant).
  _warn "sbatch indisponible — lancement local synchrone"
  ( cd "$run_dir" && mpirun -np "$cores" foamRun -parallel > LOG/foamRun.log 2>&1 )
  echo "LOCAL"
  return 0
}

adapt_pilote_etat() {
  local run_dir="$1" job_id="$2"
  if [[ "$job_id" != "LOCAL" ]] && command -v sacct &>/dev/null; then
    local state
    state=$(sacct -j "$job_id" --format=State -P --noheader 2>/dev/null | head -1)
    case "$state" in
      COMPLETED)                 echo "DONE" ;;
      RUNNING|COMPLETING)        echo "RUNNING" ;;
      PENDING|REQUEUED)          echo "PENDING" ;;
      *)                         echo "FAILED" ;;
    esac
    return 0
  fi
  # Local : lire le log foamRun.
  local log="${run_dir}/LOG/foamRun.log"
  if [[ ! -f "$log" ]]; then echo "PENDING";
  elif grep -q "FOAM FATAL" "$log"; then echo "FAILED";
  elif grep -q "^End" "$log"; then echo "DONE";
  else echo "RUNNING"; fi
}

# Temps solveur total = dernier ExecutionTime du log foamRun (secondes).
adapt_pilote_temps_total() {
  local log="${1}/LOG/foamRun.log"
  grep "ExecutionTime = " "$log" | tail -1 | awk '{print $3}'
}

# Nombre d'itérations = nombre de pas de temps « Time = » dans le log.
adapt_pilote_nb_iterations() {
  local log="${1}/LOG/foamRun.log"
  grep -c "^Time = " "$log"
}

# Nombre de mailles via checkMesh (ADAPTER si vous le lisez ailleurs).
adapt_maillage_nb_cellules() {
  local case_dir="$1"
  local log="${case_dir}/LOG/checkMesh.log"
  [[ -f "$log" ]] || ( cd "$case_dir" && checkMesh > LOG/checkMesh.log 2>&1 ) || true
  grep -i "cells:" "$log" 2>/dev/null | head -1 | awk '{print $2}'
}

# PLACEHOLDER : itérations cible = endTime de system/controlDict via sed.
adapt_cible_iterations() {
  local ctrl="${1}/system/controlDict"
  [[ -f "$ctrl" ]] || { echo ""; return 0; }
  sed -n 's/^endTime[[:space:]]*\([0-9]*\).*/\1/p' "$ctrl" | head -1
}

# adapt_pilote_ram_crete : hérité de interface.sh (sacct MaxRSS × NTasks).
