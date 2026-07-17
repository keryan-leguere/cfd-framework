#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  interface.sh — Contrat commun des adaptateurs de capture pilote (cfd-perf)
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Ce fichier définit le contrat que tout adaptateur de capture doit respecter,
#  et fournit des implémentations par défaut réutilisables (notamment la lecture
#  de la RAM crête via SLURM).
#
#  Il est VOLONTAIREMENT autonome : il ne dépend pas de $CFD_FRAMEWORK et
#  fournit ses propres primitives de log si le framework n'est pas présent, de
#  sorte que cfd-perf reste utilisable copié seul sur un calculateur isolé.
#
#  Chaque adaptateur (mock.sh, OF.sh, …) source ce fichier puis redéfinit les
#  fonctions marquées « À IMPLÉMENTER ». Les fonctions échouent bruyamment si
#  elles ne sont pas surchargées.
#
#  Voir ADAPTATEUR/README.md pour le guide de rédaction d'un adaptateur.
#  Licence : MIT
# ═══════════════════════════════════════════════════════════════════════════════

# ── Locale numérique neutre ───────────────────────────────────────────────────
# Force le point décimal (et non la virgule) dans awk/printf, quelle que soit la
# locale de l'hôte : les valeurs capturées sont relues par Python.
export LC_ALL=C

# ── Primitives de log (réutilise le framework si disponible, sinon repli) ─────
if [[ -n "${CFD_FRAMEWORK:-}" ]] && [[ -f "${CFD_FRAMEWORK}/lib/format.sh" ]]; then
  # shellcheck disable=SC1091
  source "${CFD_FRAMEWORK}/lib/format.sh"
fi
if ! command -v _info &>/dev/null; then
  _info()   { echo "[INFO] $*" >&2; }
  _warn()   { echo "[WARN] $*" >&2; }
  _error()  { echo "[ERREUR] $*" >&2; }
  _result() { echo "[OK] $*" >&2; }
fi

# ── Fonction utilitaire pour fonctions non implémentées ───────────────────────
adapt_non_impl() {
  _error "Fonction $1 non implémentée dans cet adaptateur"
  return 1
}

# ══════════════════════════════════════════════════════════════════════════════
#  📋 INFORMATIONS — À IMPLÉMENTER
# ══════════════════════════════════════════════════════════════════════════════

# Identifiant court de l'adaptateur (ex. « mock », « OF »). Écrit sur stdout.
adapt_nom() { adapt_non_impl "adapt_nom"; }

# Renvoie 0 si le solveur est installé/disponible, non-zéro sinon.
adapt_verifier_installation() { adapt_non_impl "adapt_verifier_installation"; }

# Liste (une par ligne) des éléments à copier dans un répertoire de run.
adapt_liste_elements_a_copier() { adapt_non_impl "adapt_liste_elements_a_copier"; }

# ══════════════════════════════════════════════════════════════════════════════
#  🚀 PRÉPARATION ET SOUMISSION — À IMPLÉMENTER
# ══════════════════════════════════════════════════════════════════════════════

# Prépare le cas pour tourner sur <cores> cœurs (décomposition, etc.).
#   adapt_pilote_preparer <run_dir> <cores>
adapt_pilote_preparer() { adapt_non_impl "adapt_pilote_preparer"; }

# Lance/soumet le run. Écrit sur stdout l'IDENTIFIANT DE JOB (id SLURM, ou le
# sentinelle « LOCAL » pour un lancement synchrone). Renvoie 0 si soumis.
#   adapt_pilote_soumettre <run_dir> <cores> [queue]
adapt_pilote_soumettre() { adapt_non_impl "adapt_pilote_soumettre"; }

# ══════════════════════════════════════════════════════════════════════════════
#  👁️ ÉTAT ET EXTRACTION — À IMPLÉMENTER (sauf RAM : défaut SLURM ci-dessous)
# ══════════════════════════════════════════════════════════════════════════════

# État du run : écrit PENDING | RUNNING | DONE | FAILED sur stdout.
#   adapt_pilote_etat <run_dir> <job_id>
adapt_pilote_etat() { adapt_non_impl "adapt_pilote_etat"; }

# Temps solveur total du run pilote, en SECONDES (flottant). stdout.
#   adapt_pilote_temps_total <run_dir>
adapt_pilote_temps_total() { adapt_non_impl "adapt_pilote_temps_total"; }

# Nombre d'itérations effectuées par le run pilote (entier). stdout.
#   adapt_pilote_nb_iterations <run_dir>
adapt_pilote_nb_iterations() { adapt_non_impl "adapt_pilote_nb_iterations"; }

# Nombre de mailles du maillage (entier). Utilisé pour mesh.num_cells. stdout.
#   adapt_maillage_nb_cellules <case_dir>
adapt_maillage_nb_cellules() { adapt_non_impl "adapt_maillage_nb_cellules"; }

# Nombre d'itérations CIBLE du calcul de production (study.n_iterations).
# PLACEHOLDER : à extraire d'un fichier de contrôle via sed. stdout.
#   adapt_cible_iterations <case_dir>
adapt_cible_iterations() { adapt_non_impl "adapt_cible_iterations"; }

# ══════════════════════════════════════════════════════════════════════════════
#  💾 RAM CRÊTE — implémentation SLURM par défaut (surchargée par mock)
# ══════════════════════════════════════════════════════════════════════════════

# Convertit une valeur MaxRSS de sacct (ex. « 3200000K », « 3.2G », « 512M »)
# en gigaoctets (base 1024). Écrit un flottant sur stdout.
adapt_maxrss_vers_go() {
  local v="$1"
  [[ -z "$v" || "$v" == "0" ]] && { echo "0"; return 0; }
  local num unit
  num="${v//[^0-9.]/}"
  unit="${v//[0-9.]/}"
  [[ -z "$num" ]] && { echo "0"; return 0; }
  awk -v n="$num" -v u="${unit^^}" 'BEGIN {
    f = 1;                       # défaut : octets
    if (u == "K") f = 1/1048576;
    else if (u == "M") f = 1/1024;
    else if (u == "G") f = 1;
    else if (u == "T") f = 1024;
    else if (u == "") f = 1/1073741824;   # octets bruts
    printf "%.4f", n * f;
  }'
}

# RAM crête TOTALE du run, en Go. Défaut : SLURM.
#   total = MaxRSS (par tâche) × NTasks
# Renvoie chaîne vide si SLURM/job indisponible (RAM alors non mesurée).
#   adapt_pilote_ram_crete <run_dir> <job_id>
adapt_pilote_ram_crete() {
  local job_id="$2"
  [[ -z "$job_id" || "$job_id" == "LOCAL" ]] && { echo ""; return 0; }
  command -v sacct &>/dev/null || { echo ""; return 0; }

  # Ligne du step principal (job_id.0 ou .batch) portant MaxRSS et NTasks.
  local line maxrss ntasks
  line=$(sacct -j "$job_id" --format=MaxRSS,NTasks -P --noheader 2>/dev/null \
           | awk -F'|' '$1 != "" {print; exit}')
  [[ -z "$line" ]] && { echo ""; return 0; }
  maxrss=$(echo "$line" | cut -d'|' -f1)
  ntasks=$(echo "$line" | cut -d'|' -f2)
  [[ -z "$ntasks" || "$ntasks" == "0" ]] && ntasks=1

  local go_par_tache
  go_par_tache=$(adapt_maxrss_vers_go "$maxrss")
  awk -v g="$go_par_tache" -v n="$ntasks" 'BEGIN { printf "%.4f", g * n }'
}
