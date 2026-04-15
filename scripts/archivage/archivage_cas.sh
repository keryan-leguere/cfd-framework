#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  archivage_cas.sh — Archivage complet d'un cas CFD en .tar.xz
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Archive un cas CFD complet via un espace de staging sécurisé :
#    1. Copie le cas vers un staging local (même répertoire, copie parallèle)
#    2. Applique les règles de conservation/suppression par zone
#    3. Exécute adapt_clean ou adapt_rm dans chaque run de 02_PARAMS
#    4. Exécute un hook bash optionnel pour les nettoyages au cas par cas
#    5. Génère CAS.tar.xz à côté du cas source
#    6. Nettoie le staging — le dossier source reste intact
#
#  Usage:
#    archivage_cas.sh --solutions-volumiques <keep|remove> [OPTIONS] <CAS>
#
#  Auteur : KL
#  Licence : MIT
# ═══════════════════════════════════════════════════════════════════════════════

set -Euo pipefail
IFS=$'\n\t'

# ══════════════════════════════════════════════════════════════════════════════
#  🔧 RÉSOLUTION DE CFD_FRAMEWORK
# ══════════════════════════════════════════════════════════════════════════════

if [[ -z "${CFD_FRAMEWORK:-}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  CFD_FRAMEWORK="$(cd "${SCRIPT_DIR}/../.." && pwd)"
  export CFD_FRAMEWORK
fi

if [[ ! -d "$CFD_FRAMEWORK" ]]; then
  echo "ERREUR: Répertoire CFD_FRAMEWORK introuvable: $CFD_FRAMEWORK" >&2
  exit 1
fi

# ══════════════════════════════════════════════════════════════════════════════
#  📚 CHARGEMENT DES BIBLIOTHÈQUES
# ══════════════════════════════════════════════════════════════════════════════

source "${CFD_FRAMEWORK}/lib/format.sh"
source "${CFD_FRAMEWORK}/lib/utils.sh"
source "${CFD_FRAMEWORK}/lib/compress_function.sh"

# ══════════════════════════════════════════════════════════════════════════════
#  📐 RÈGLES DE CONSERVATION PAR ZONE
# ══════════════════════════════════════════════════════════════════════════════
#
#  Chaque zone du cas définit quels fichiers/dossiers conserver dans le
#  staging. Tout ce qui ne correspond pas aux patterns est supprimé.
#  Pour ajouter ou modifier un comportement, il suffit d'éditer la fonction
#  correspondante ou d'en ajouter une nouvelle.

archive_prune_maillage() {
  local dir="$1"
  [[ -d "$dir" ]] || return 0

  _info "Élagage 01_MAILLAGE …"

  # Patterns à conserver (relatifs à $dir)
  local -a keep_patterns=(
    "FICHIER_PARAMETRE"   # dossier complet
    "*SURFACIQUE*"        # fichiers de maillage surfacique
    "*.html"              # rapports
    "*.stp"               # CAO STEP
  )
  archive_prune_keep_patterns "$dir" "${keep_patterns[@]}"
}

archive_prune_decomposition() {
  local dir="$1"
  [[ -d "$dir" ]] || return 0

  _info "Élagage 03_DECOMPOSITION …"

  local -a keep_patterns=(
    "job.data*"
  )
  archive_prune_keep_patterns "$dir" "${keep_patterns[@]}"
}

archive_prune_keep_patterns() {
  local dir="$1"
  shift
  local -a keep_patterns=("$@")
  local -a keep_list=()

  if [[ ${#keep_patterns[@]} -eq 0 ]]; then
    _warn "Aucun pattern de conservation défini pour $dir — élagage ignoré"
    return 0
  fi

  # Recherche récursive des éléments à conserver.
  local find_expr=()
  local pattern
  for pattern in "${keep_patterns[@]}"; do
    find_expr+=( -name "$pattern" -o )
  done
  unset 'find_expr[${#find_expr[@]}-1]'

  while IFS= read -r item; do
    [[ -n "$item" ]] && keep_list+=("$item")
  done < <(find "$dir" -mindepth 1 \( "${find_expr[@]}" \) 2>/dev/null)

  if [[ ${#keep_list[@]} -eq 0 ]]; then
    _warn "Aucun élément ne correspond aux patterns de conservation dans $dir — élagage ignoré"
    return 0
  fi

  # Nettoyage des éléments qui ne sont ni conservés, ni ancêtres/descendants d'un conservé.
  while IFS= read -r item; do
    local base
    local keep=false
    base="$(basename "$item")"
    for kept in "${keep_list[@]}"; do
      if [[ "$item" == "$kept" || "$item" == "$kept"/* || "$kept" == "$item"/* ]]; then
        keep=true
        break
      fi
    done

    if [[ "$keep" == false ]]; then
      rm -rf "$item"
      _debug "Supprimé : $base"
    fi
  done < <(find "$dir" -depth -mindepth 1 2>/dev/null)
}

archive_process_params() {
  local dir="$1"
  local mode="$2"   # keep | remove
  [[ -d "$dir" ]] || return 0

  _info "Traitement 02_PARAMS (mode: $mode) …"

  local run_count=0

  # Parcourir les configurations
  while IFS= read -r config_dir; do
    [[ -d "$config_dir" ]] || continue
    local config_name
    config_name="$(basename "$config_dir")"

    # Parcourir les runs dans chaque configuration
    while IFS= read -r run_dir; do
      [[ -d "$run_dir" ]] || continue
      local run_name
      run_name="$(basename "$run_dir")"

      ((run_count++))
      _bullet "[$config_name] $run_name → adapt_${mode/keep/clean}"

      local saved_info=""
      if declare -F _info >/dev/null 2>&1; then
        saved_info="$(declare -f _info)"
      fi
      _info() { :; }

      case "$mode" in
        keep)   adapt_clean "$run_dir" ;;
        remove) adapt_rm    "$run_dir" ;;
      esac

      if [[ -n "$saved_info" ]]; then
        eval "$saved_info"
      else
        unset -f _info >/dev/null 2>&1 || true
      fi
    done < <(find "$config_dir" -maxdepth 1 -mindepth 1 -type d 2>/dev/null)
  done < <(find "$dir" -maxdepth 1 -mindepth 1 -type d 2>/dev/null)

  _info "Runs traités dans 02_PARAMS : $run_count"
}

# ══════════════════════════════════════════════════════════════════════════════
#  ❓ FONCTION D'AIDE
# ══════════════════════════════════════════════════════════════════════════════

usage() {
  cat <<HEREDOC

╔═══════════════════════════════════════════════════════════════════════════════╗
║       💾 cfd-archivage-cas — Archivage complet d'un cas CFD                  ║
╚═══════════════════════════════════════════════════════════════════════════════╝

$(printf "%bUSAGE:%b" "$BOLD" "$RESET")
  cfd-archivage-cas --solutions-volumiques <keep|remove> [OPTIONS] <CAS>

$(printf "%bDESCRIPTION:%b" "$BOLD" "$RESET")
  Archive un cas CFD complet en CAS.tar.xz via un espace de staging
  sécurisé. Le dossier source n'est jamais modifié.

$(printf "%bARGUMENT OBLIGATOIRE:%b" "$BOLD" "$RESET")
  --solutions-volumiques <keep|remove>
      keep   : conserver la dernière solution volumique (adapt_clean)
      remove : supprimer toutes les solutions volumiques (adapt_rm)

$(printf "%bARGUMENTS POSITIONNELS:%b" "$BOLD" "$RESET")
  CAS     Chemin vers le dossier du cas à archiver

$(printf "%bOPTIONS:%b" "$BOLD" "$RESET")
  -h, --help                 Afficher cette aide
  -o, --output <FICHIER>     Chemin de l'archive de sortie (défaut: CAS.tar.xz)
  --staging-dir <DIR>        Répertoire de staging (défaut: .cfd-staging-CAS-PID/ local)
  --hook <SCRIPT>            Script bash complémentaire exécuté dans le staging
  --threads <N>              Nombre de threads xz (défaut: 0 = auto)
  --copy-jobs <N>            Nombre de copies parallèles (défaut: nproc)
  --dry-run                  Afficher les actions sans les exécuter
  --no-compress              Créer un .tar sans compression xz

$(printf "%bVARIABLES D'ENVIRONNEMENT:%b" "$BOLD" "$RESET")
  CFD_FRAMEWORK              Chemin vers le framework CFD
  ADAPTATEUR                 Adaptateur utilisé (défaut: OF)

$(printf "%bEXEMPLES:%b" "$BOLD" "$RESET")
  # Archiver en conservant la dernière solution volumique
  cfd-archivage-cas --solutions-volumiques keep /data/projets/AILE_DELTA

  # Archiver léger (sans solutions volumiques) avec un hook
  cfd-archivage-cas --solutions-volumiques remove \\
      --hook ./pre_archive.sh /data/projets/AILE_DELTA

  # Staging explicite, copie séquentielle et sortie personnalisée
  cfd-archivage-cas --solutions-volumiques keep \\
      --staging-dir /scratch/staging --copy-jobs 1 \\
      --output /archives/AILE_DELTA_2026.tar.xz \\
      /data/projets/AILE_DELTA

HEREDOC
}

# ══════════════════════════════════════════════════════════════════════════════
#  🔧 ARGUMENT PARSING
# ══════════════════════════════════════════════════════════════════════════════

SOL_VOLUMIQUES=""
OUTPUT_FILE=""
STAGING_DIR=""
HOOK_SCRIPT=""
XZ_THREADS="0"
COPY_JOBS=""
DRY_RUN=false
NO_COMPRESS=false

POSITIONAL_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --solutions-volumiques)
      [[ $# -ge 2 ]] || die "Option --solutions-volumiques requiert une valeur (keep|remove)"
      SOL_VOLUMIQUES="$2"
      shift 2
      ;;
    -o|--output)
      [[ $# -ge 2 ]] || die "Option --output requiert un chemin"
      OUTPUT_FILE="$2"
      shift 2
      ;;
    --staging-dir)
      [[ $# -ge 2 ]] || die "Option --staging-dir requiert un chemin"
      STAGING_DIR="$2"
      shift 2
      ;;
    --hook)
      [[ $# -ge 2 ]] || die "Option --hook requiert un chemin de script"
      HOOK_SCRIPT="$2"
      shift 2
      ;;
    --threads)
      [[ $# -ge 2 ]] || die "Option --threads requiert un nombre"
      XZ_THREADS="$2"
      shift 2
      ;;
    --copy-jobs)
      [[ $# -ge 2 ]] || die "Option --copy-jobs requiert un nombre"
      COPY_JOBS="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --no-compress)
      NO_COMPRESS=true
      shift
      ;;
    -*)
      _error "Option inconnue : $1"
      echo "Utilisez -h ou --help pour l'aide" >&2
      exit 1
      ;;
    *)
      POSITIONAL_ARGS+=("$1")
      shift
      ;;
  esac
done

# ── Validation des arguments ─────────────────────────────────────────────────

if [[ -z "$SOL_VOLUMIQUES" ]]; then
  _error "L'argument --solutions-volumiques <keep|remove> est obligatoire"
  usage
  exit 1
fi

if [[ "$SOL_VOLUMIQUES" != "keep" && "$SOL_VOLUMIQUES" != "remove" ]]; then
  die "Valeur invalide pour --solutions-volumiques : '$SOL_VOLUMIQUES' (attendu: keep ou remove)"
fi

if [[ ${#POSITIONAL_ARGS[@]} -ne 1 ]]; then
  _error "Un seul argument positionnel attendu : le chemin du cas"
  usage
  exit 1
fi

SOURCE_CAS="$(cd "${POSITIONAL_ARGS[0]}" && pwd)"

if [[ ! -d "$SOURCE_CAS" ]]; then
  die "Le dossier du cas n'existe pas : ${POSITIONAL_ARGS[0]}"
fi

CAS_NAME="$(basename "$SOURCE_CAS")"

if [[ -z "$OUTPUT_FILE" ]]; then
  OUTPUT_FILE="$(dirname "$SOURCE_CAS")/${CAS_NAME}.tar.xz"
  [[ "$NO_COMPRESS" == true ]] && OUTPUT_FILE="$(dirname "$SOURCE_CAS")/${CAS_NAME}.tar"
fi

if [[ -n "$HOOK_SCRIPT" && ! -f "$HOOK_SCRIPT" ]]; then
  die "Script hook introuvable : $HOOK_SCRIPT"
fi

if [[ -n "$HOOK_SCRIPT" && ! -x "$HOOK_SCRIPT" ]]; then
  die "Script hook non exécutable : $HOOK_SCRIPT (chmod +x ?)"
fi

COPY_JOBS="${COPY_JOBS:-$(nproc 2>/dev/null || echo 4)}"

archive_get_size_bytes() {
  local path="$1"
  if [[ -d "$path" ]]; then
    du --apparent-size -sb "$path" 2>/dev/null | awk '{print $1}'
    return 0
  fi
  stat -c%s "$path" 2>/dev/null || echo 0
}

archive_human_size() {
  local bytes="$1"
  if command -v numfmt >/dev/null 2>&1; then
    numfmt --to=iec-i --suffix=B "$bytes"
  else
    echo "${bytes} B"
  fi
}

# ══════════════════════════════════════════════════════════════════════════════
#  🔌 CHARGEMENT DE L'ADAPTATEUR
# ══════════════════════════════════════════════════════════════════════════════

ADAPTATEUR="${ADAPTATEUR:-OF}"
_info "Chargement de l'adaptateur : $ADAPTATEUR"

adaptateur_path="${CFD_FRAMEWORK}/adaptateurs/${ADAPTATEUR}/adaptateur.sh"
if [[ ! -f "$adaptateur_path" ]]; then
  adaptateur_path="${CFD_FRAMEWORK}/adaptateurs/${ADAPTATEUR}.sh"
fi

if [[ ! -f "$adaptateur_path" ]]; then
  die "Adaptateur introuvable : $ADAPTATEUR"
fi

source "$adaptateur_path"

if ! adapt_verifier_installation; then
  die "Échec de vérification de l'adaptateur $(adapt_nom)"
fi

_info "Adaptateur $(adapt_nom) chargé et vérifié"

# ══════════════════════════════════════════════════════════════════════════════
#  📊 RÉCAPITULATIF
# ══════════════════════════════════════════════════════════════════════════════

titre_archivage

h1 "Configuration de l'archivage"

kv "Cas source"         "$SOURCE_CAS"
source_size_bytes="$(archive_get_size_bytes "$SOURCE_CAS")"
kv "Taille source"      "$(archive_human_size "$source_size_bytes") ($source_size_bytes bytes)"
kv "Archive de sortie"  "$OUTPUT_FILE"
kv "Solutions vol."     "$SOL_VOLUMIQUES"
kv "Adaptateur"         "$(adapt_nom) v$(adapt_version)"
kv "Threads xz"         "$XZ_THREADS"
kv "Copy jobs"          "$COPY_JOBS"
[[ -n "$HOOK_SCRIPT" ]] && kv "Hook" "$HOOK_SCRIPT"
[[ -n "$STAGING_DIR" ]] && kv "Staging explicite" "$STAGING_DIR"
[[ "$DRY_RUN" == true ]] && boite_warn "MODE DRY-RUN — aucune modification ne sera effectuée"

separator

# ══════════════════════════════════════════════════════════════════════════════
#  📂 CRÉATION DU STAGING
# ══════════════════════════════════════════════════════════════════════════════

h1 "Préparation du staging"

if [[ -n "$STAGING_DIR" ]]; then
  STAGING_ROOT="$STAGING_DIR"
  mkdir -p "$STAGING_ROOT"
else
  STAGING_ROOT="$(dirname "$SOURCE_CAS")/.cfd-staging-${CAS_NAME}-$$"
  mkdir -p "$STAGING_ROOT"
fi

STAGING_CAS="${STAGING_ROOT}/${CAS_NAME}"

cleanup_staging() {
  if [[ -d "$STAGING_ROOT" && -z "$STAGING_DIR" ]]; then
    _info "Nettoyage du staging temporaire …"
    rm -rf "$STAGING_ROOT"
  fi
}
trap cleanup_staging EXIT

_info "Staging : $STAGING_ROOT"

parallel_copy() {
  local src="$1" dst="$2" jobs="$3"
  mkdir -p "$dst"
  (
    cd "$src"
    find . -type d -print0 | ( cd "$dst" && xargs -0 mkdir -p )
    find . ! -type d -print0 | xargs -0 -P "$jobs" -n 10 \
      cp -a --parents -t "$dst"
  )
}

if [[ "$DRY_RUN" == true ]]; then
  _note "DRY-RUN : la copie vers le staging serait effectuée ici"
else
  if [[ "$COPY_JOBS" -le 1 ]]; then
    _wait "Copie du cas vers le staging …"
    cp -a "$SOURCE_CAS" "$STAGING_CAS"
  else
    _wait "Copie parallèle du cas vers le staging (${COPY_JOBS} jobs) …"
    parallel_copy "$SOURCE_CAS" "$STAGING_CAS" "$COPY_JOBS"
  fi
  staging_size_bytes="$(archive_get_size_bytes "$STAGING_CAS")"
  _result "Copie terminée ($(archive_human_size "$staging_size_bytes"), $staging_size_bytes bytes)"
fi

# ══════════════════════════════════════════════════════════════════════════════
#  ✂️ ÉLAGAGE PAR ZONE
# ══════════════════════════════════════════════════════════════════════════════

h1 "Élagage du staging"

if [[ "$DRY_RUN" == true ]]; then
  _note "DRY-RUN : les règles d'élagage seraient appliquées ici"
else
  h2 "01_MAILLAGE"
  archive_prune_maillage "${STAGING_CAS}/01_MAILLAGE"

  h2 "02_PARAMS"
  archive_process_params "${STAGING_CAS}/02_PARAMS" "$SOL_VOLUMIQUES"

  h2 "03_DECOMPOSITION"
  archive_prune_decomposition "${STAGING_CAS}/03_DECOMPOSITION"

  separator
  staging_size_bytes="$(archive_get_size_bytes "$STAGING_CAS")"
  _result "Élagage terminé — taille staging : $(archive_human_size "$staging_size_bytes") ($staging_size_bytes bytes)"
fi

# ══════════════════════════════════════════════════════════════════════════════
#  🪝 HOOK COMPLÉMENTAIRE
# ══════════════════════════════════════════════════════════════════════════════

if [[ -n "$HOOK_SCRIPT" ]]; then
  h1 "Exécution du hook complémentaire"

  _info "Hook : $HOOK_SCRIPT"

  if [[ "$DRY_RUN" == true ]]; then
    _note "DRY-RUN : le hook serait exécuté ici"
  else
    HOOK_SCRIPT_ABS="$(cd "$(dirname "$HOOK_SCRIPT")" && pwd)/$(basename "$HOOK_SCRIPT")"
    "$HOOK_SCRIPT_ABS" "$STAGING_CAS" "$SOURCE_CAS"
    _result "Hook exécuté avec succès"
  fi
fi

# ══════════════════════════════════════════════════════════════════════════════
#  📦 COMPRESSION
# ══════════════════════════════════════════════════════════════════════════════

h1 "Création de l'archive"

if [[ "$DRY_RUN" == true ]]; then
  _note "DRY-RUN : l'archive serait créée ici → $OUTPUT_FILE"
else
  if [[ -f "$OUTPUT_FILE" ]]; then
    _warn "L'archive existe déjà : $OUTPUT_FILE"
    confirmer "Écraser l'archive existante ?" n || die "Archivage annulé"
    rm -f "$OUTPUT_FILE"
  fi

  _wait "Compression en cours …"

  local_start=$(date +%s)

  if [[ "$NO_COMPRESS" == true ]]; then
    tar -cf "$OUTPUT_FILE" -C "$STAGING_ROOT" "$CAS_NAME"
  else
    compress_input="${STAGING_ROOT}/${CAS_NAME}"
    rm -f "${compress_input}.tar.xz"
    (
      cd "$STAGING_ROOT"
      compress_KL "$CAS_NAME"
    )
    generated_archive="${compress_input}.tar.xz"
    [[ -f "$generated_archive" ]] || die "Échec de compression via compress_KL : archive absente"
    mv "$generated_archive" "$OUTPUT_FILE"
  fi

  local_end=$(date +%s)
  local_elapsed=$(( local_end - local_start ))

  _result "Archive créée : $OUTPUT_FILE"
  archive_size_bytes="$(archive_get_size_bytes "$OUTPUT_FILE")"
  source_size_bytes="$(archive_get_size_bytes "$SOURCE_CAS")"
  kv "Taille archive" "$(archive_human_size "$archive_size_bytes") ($archive_size_bytes bytes)"
  kv "Taille source"  "$(archive_human_size "$source_size_bytes") ($source_size_bytes bytes)"
  kv "Durée"          "$(format_eta "$local_elapsed")"
fi

# ══════════════════════════════════════════════════════════════════════════════
#  ✅ RÉSUMÉ FINAL
# ══════════════════════════════════════════════════════════════════════════════

separator_double

if [[ "$DRY_RUN" == true ]]; then
  boite_info "DRY-RUN terminé — aucune modification effectuée"
else
  boite_result "Archivage terminé avec succès"

  tableau_init "Propriété" "Valeur"
  tableau_add "Cas source"     "$SOURCE_CAS"
  tableau_add "Archive"        "$OUTPUT_FILE"
  source_size_bytes="$(archive_get_size_bytes "$SOURCE_CAS")"
  archive_size_bytes="$(archive_get_size_bytes "$OUTPUT_FILE")"
  tableau_add "Taille source"  "$(archive_human_size "$source_size_bytes") ($source_size_bytes bytes)"
  tableau_add "Taille archive" "$(archive_human_size "$archive_size_bytes") ($archive_size_bytes bytes)"
  tableau_add "Solutions vol."  "$SOL_VOLUMIQUES"
  [[ -n "$HOOK_SCRIPT" ]] && tableau_add "Hook" "$HOOK_SCRIPT"
  tableau_print "Récapitulatif d'archivage"
fi

_info "Le dossier source n'a pas été modifié : $SOURCE_CAS"
