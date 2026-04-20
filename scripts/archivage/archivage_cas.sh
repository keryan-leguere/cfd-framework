#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  archivage_cas.sh — Archivage complet d'un cas CFD en .tar.xz
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Archive un cas CFD complet via un espace de staging sécurisé :
#    1. Copie le cas vers un staging local (même répertoire, copie parallèle)
#    2. Applique les règles de conservation/suppression par zone
#    3. Exécute adapt_nettoyer_run pour chaque run de 02_PARAMS
#       (options --keep-vol / --keep-surf pilotées par les flags CLI)
#    4. Exécute un hook bash optionnel pour les nettoyages au cas par cas
#    5. Transforme les liens symboliques absolus en liens relatifs
#    6. Génère CAS.tar.xz à côté du cas source (sauf si --no-archive)
#    7. Nettoie le staging — le dossier source reste intact
#
#  Usage:
#    archivage_cas.sh [--keep-vol] [--keep-surf] [OPTIONS] <CAS>
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
  local keep_vol="$2"    # true|false
  local keep_surf="$3"   # true|false
  [[ -d "$dir" ]] || return 0

  _info "Traitement 02_PARAMS (keep-vol=$keep_vol, keep-surf=$keep_surf) …"

  local -a adapt_opts=()
  [[ "$keep_vol"  == true ]] && adapt_opts+=("--keep-vol")
  [[ "$keep_surf" == true ]] && adapt_opts+=("--keep-surf")

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
      local tag="none"
      if [[ "$keep_vol" == true && "$keep_surf" == true ]]; then
        tag="vol+surf"
      elif [[ "$keep_vol" == true ]]; then
        tag="vol"
      elif [[ "$keep_surf" == true ]]; then
        tag="surf"
      fi
      _bullet "[$config_name] $run_name → adapt_nettoyer_run (${tag})"

      local saved_info=""
      if declare -F _info >/dev/null 2>&1; then
        saved_info="$(declare -f _info)"
      fi
      _info() { :; }

      adapt_nettoyer_run "$run_dir" "${adapt_opts[@]}"

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
#  🔗 LIENS SYMBOLIQUES : ABSOLU → RELATIF
# ══════════════════════════════════════════════════════════════════════════════
#
#  Objectif : rendre le cas archivé portable sur une autre machine / un autre
#  utilisateur. Tous les liens symboliques dont la cible absolue pointe à
#  l'intérieur du cas (soit vers le dossier source, soit vers le staging) sont
#  réécrits en chemins relatifs à partir du dossier qui les contient.
#
#  Pour les liens absolus dont la cible est HORS du cas :
#    - Par défaut : conservés tels quels + WARNING (l'archive ne sera pas
#      portable, le lien cassera sur une autre machine).
#    - Avec $copy_external=true : le lien est supprimé et remplacé par une
#      COPIE intégrale (déréférencée) de la cible. L'archive devient portable
#      au prix d'un possible gonflement.
#
#  Args :
#    $1 staging_root   — racine du staging
#    $2 source_root    — dossier source d'origine
#    $3 copy_external  — "true" pour matérialiser les cibles externes

archive_relativiser_liens_symboliques() {
  local staging_root="$1"
  local source_root="$2"
  local copy_external="${3:-false}"

  [[ -d "$staging_root" ]] || return 0

  local staging_abs source_abs
  staging_abs="$(cd "$staging_root" && pwd)"
  source_abs="$(cd "$source_root" && pwd)"

  local converted=0 already_rel=0
  local outside_kept=0 outside_copied=0 outside_broken=0
  local broken=0

  while IFS= read -r -d '' link; do
    local target
    target="$(readlink "$link")"

    # Lien déjà relatif : on ne touche pas.
    if [[ "$target" != /* ]]; then
      ((already_rel++))
      continue
    fi

    # Normaliser d'abord pour éliminer // et trailing slashes.
    local target_norm
    target_norm="$(readlink -m "$target" 2>/dev/null || echo "$target")"

    # Mapper vers l'équivalent dans le staging si la cible pointe vers le
    # dossier source (cas typique après cp -a).
    local mapped=""
    if [[ "$target_norm" == "$source_abs" || "$target_norm" == "$source_abs"/* ]]; then
      mapped="${staging_abs}${target_norm#"$source_abs"}"
    elif [[ "$target_norm" == "$staging_abs" || "$target_norm" == "$staging_abs"/* ]]; then
      mapped="$target_norm"
    else
      # ── Cible HORS du cas ────────────────────────────────────────────────
      local rel_link="${link#"$staging_abs"/}"
      if [[ "$copy_external" == true ]]; then
        if [[ ! -e "$target_norm" ]]; then
          _warn "Lien cassé — impossible de copier : $rel_link → $target"
          ((outside_broken++))
          continue
        fi
        _warn "Lien hors cas → copie matérialisée : $rel_link ← $target"
        rm -f "$link"
        # cp -aL : préserve perms/attrs et déréférence la cible.
        if cp -aL --no-preserve=ownership "$target_norm" "$link"; then
          ((outside_copied++))
        else
          _warn "Échec de la copie : $rel_link ← $target"
          ((outside_broken++))
        fi
      else
        _warn "Lien hors cas conservé absolu (non portable) : $rel_link → $target"
        ((outside_kept++))
      fi
      continue
    fi

    local link_dir rel
    link_dir="$(dirname "$link")"
    if ! rel="$(realpath -m --relative-to="$link_dir" "$mapped" 2>/dev/null)"; then
      ((broken++))
      _warn "Impossible de relativiser : $link → $target"
      continue
    fi

    ln -sfn "$rel" "$link"
    ((converted++))
    _debug "Lien relativisé : ${link#"$staging_abs"/} → $rel"
  done < <(find "$staging_abs" -type l -print0)

  _info "Liens symboliques : $converted relativisés, $already_rel déjà relatifs"
  if (( outside_kept > 0 )); then
    _warn "Liens hors cas conservés absolus : $outside_kept (archive non portable — utilisez --copy-external-links)"
  fi
  if (( outside_copied > 0 )); then
    _info "Liens hors cas matérialisés (copie) : $outside_copied"
  fi
  if (( outside_broken > 0 )); then
    _warn "Liens hors cas cassés/échec de copie : $outside_broken"
  fi
  if (( broken > 0 )); then
    _warn "Liens non relativisables : $broken (voir logs)"
  fi
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
  cfd-archivage-cas [--keep-vol] [--keep-surf] [OPTIONS] <CAS>

$(printf "%bDESCRIPTION:%b" "$BOLD" "$RESET")
  Archive un cas CFD complet en CAS.tar.xz via un espace de staging
  sécurisé. Le dossier source n'est jamais modifié.

$(printf "%bARGUMENTS POSITIONNELS:%b" "$BOLD" "$RESET")
  CAS     Chemin vers le dossier du cas à archiver

$(printf "%bOPTIONS DE NETTOYAGE (adapt_nettoyer_run):%b" "$BOLD" "$RESET")
  --keep-vol                 Conserver la dernière solution volumique
  --keep-surf                Conserver la solution surfacique (patterns adaptateur)
  --solutions-volumiques V   [legacy] keep ⇒ --keep-vol ; remove ⇒ (aucun)

$(printf "%bOPTIONS GÉNÉRALES:%b" "$BOLD" "$RESET")
  -h, --help                 Afficher cette aide
  -o, --output <FICHIER>     Chemin de l'archive de sortie (défaut: CAS.tar.xz)
  --staging-dir <DIR>        Répertoire de staging (défaut: .cfd-staging-CAS-PID/ local)
                             Si fourni, le staging n'est PAS supprimé à la fin.
  --skip-copy                Réutilise le staging existant (pas de copie depuis CAS)
                             Utile pour re-nettoyer/recompresser sans tout recopier.
  --hook <SCRIPT>            Script bash complémentaire exécuté dans le staging
  --threads <N>              Nombre de threads xz (défaut: 0 = auto)
  --copy-jobs <N>            Nombre de copies parallèles (défaut: nproc)
  --dry-run                  Afficher les actions sans les exécuter
  --no-compress              Créer un .tar sans compression xz
  --no-archive               Nettoyer le staging sans compresser NI supprimer
                             (permet d'inspecter/mettre au point les adapt_*)
  --no-relative-links        Ne pas convertir les liens absolus en relatifs
  --copy-external-links      Remplacer les liens absolus pointant HORS du cas
                             par une copie déréférencée de leur cible
                             (archive portable — peut gonfler la taille)

$(printf "%bVARIABLES D'ENVIRONNEMENT:%b" "$BOLD" "$RESET")
  CFD_FRAMEWORK              Chemin vers le framework CFD
  ADAPTATEUR                 Adaptateur utilisé (défaut: OF)
  CFD_ARCHIVE_OF_BASE_KEEP   Patterns « socle » (surcharge OF)
  CFD_ARCHIVE_OF_SURF_KEEP   Patterns « surfacique » (surcharge OF)

$(printf "%bEXEMPLES:%b" "$BOLD" "$RESET")
  # Archive légère : aucune solution conservée
  cfd-archivage-cas /data/projets/AILE_DELTA

  # Archive avec solution volumique uniquement
  cfd-archivage-cas --keep-vol /data/projets/AILE_DELTA

  # Archive avec volumique + surfacique
  cfd-archivage-cas --keep-vol --keep-surf /data/projets/AILE_DELTA

  # Nettoyage seul (sans compression ni suppression du staging)
  cfd-archivage-cas --keep-surf --no-archive --staging-dir /scratch/stage \\
      /data/projets/AILE_DELTA

HEREDOC
}

# ══════════════════════════════════════════════════════════════════════════════
#  🔧 ARGUMENT PARSING
# ══════════════════════════════════════════════════════════════════════════════

KEEP_VOL=false
KEEP_SURF=false
OUTPUT_FILE=""
STAGING_DIR=""
SKIP_COPY=false
HOOK_SCRIPT=""
XZ_THREADS="0"
COPY_JOBS=""
DRY_RUN=false
NO_COMPRESS=false
NO_ARCHIVE=false
RELATIVE_LINKS=true
COPY_EXTERNAL_LINKS=false

POSITIONAL_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --keep-vol)
      KEEP_VOL=true
      shift
      ;;
    --keep-surf)
      KEEP_SURF=true
      shift
      ;;
    --solutions-volumiques)
      [[ $# -ge 2 ]] || die "Option --solutions-volumiques requiert une valeur (keep|remove)"
      case "$2" in
        keep)   KEEP_VOL=true ;;
        remove) KEEP_VOL=false ;;
        *) die "Valeur invalide pour --solutions-volumiques : '$2' (attendu: keep ou remove)" ;;
      esac
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
    --skip-copy)
      SKIP_COPY=true
      shift
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
    --no-archive)
      NO_ARCHIVE=true
      shift
      ;;
    --no-relative-links)
      RELATIVE_LINKS=false
      shift
      ;;
    --copy-external-links)
      COPY_EXTERNAL_LINKS=true
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

if [[ "$SKIP_COPY" == true && -z "$STAGING_DIR" ]]; then
  die "--skip-copy nécessite --staging-dir <DIR> (staging existant)"
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

keep_tag="none"
if [[ "$KEEP_VOL" == true && "$KEEP_SURF" == true ]]; then
  keep_tag="vol+surf"
elif [[ "$KEEP_VOL" == true ]]; then
  keep_tag="vol"
elif [[ "$KEEP_SURF" == true ]]; then
  keep_tag="surf"
fi

kv "Cas source"          "$SOURCE_CAS"
source_size_bytes="$(archive_get_size_bytes "$SOURCE_CAS")"
kv "Taille source"       "$(archive_human_size "$source_size_bytes") ($source_size_bytes bytes)"
if [[ "$NO_ARCHIVE" == true ]]; then
  kv "Archive de sortie" "(désactivée — --no-archive)"
else
  kv "Archive de sortie" "$OUTPUT_FILE"
fi
kv "Conservation"        "$keep_tag"
kv "Liens relatifs"      "$RELATIVE_LINKS"
kv "Copie ext."          "$COPY_EXTERNAL_LINKS"
kv "Adaptateur"          "$(adapt_nom) v$(adapt_version)"
kv "Threads xz"          "$XZ_THREADS"
kv "Copy jobs"           "$COPY_JOBS"
[[ -n "$HOOK_SCRIPT" ]] && kv "Hook" "$HOOK_SCRIPT"
[[ -n "$STAGING_DIR" ]] && kv "Staging explicite" "$STAGING_DIR"
[[ "$SKIP_COPY"   == true ]] && kv "Skip copy"  "true (réutilise le staging)"
[[ "$NO_ARCHIVE"  == true ]] && boite_info "MODE --no-archive : pas de compression, staging conservé"
[[ "$DRY_RUN"     == true ]] && boite_warn "MODE DRY-RUN — aucune modification ne sera effectuée"

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
  # Ne jamais supprimer un staging explicite fourni par l'utilisateur ni si --no-archive.
  if [[ "$NO_ARCHIVE" == true ]]; then
    _info "Staging conservé (--no-archive) : $STAGING_ROOT"
    return 0
  fi
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
elif [[ "$SKIP_COPY" == true ]]; then
  if [[ ! -d "$STAGING_CAS" ]]; then
    die "--skip-copy demandé mais staging introuvable : $STAGING_CAS"
  fi
  _info "--skip-copy : réutilisation du staging existant"
  staging_size_bytes="$(archive_get_size_bytes "$STAGING_CAS")"
  _result "Staging présent ($(archive_human_size "$staging_size_bytes"), $staging_size_bytes bytes)"
else
  if [[ -d "$STAGING_CAS" ]]; then
    _warn "Le staging contient déjà $CAS_NAME — suppression avant copie"
    rm -rf "$STAGING_CAS"
  fi
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
  archive_process_params "${STAGING_CAS}/02_PARAMS" "$KEEP_VOL" "$KEEP_SURF"

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
#  🔗 RELATIVISATION DES LIENS SYMBOLIQUES
# ══════════════════════════════════════════════════════════════════════════════

if [[ "$RELATIVE_LINKS" == true ]]; then
  h1 "Relativisation des liens symboliques"

  if [[ "$DRY_RUN" == true ]]; then
    _note "DRY-RUN : les liens absolus seraient convertis en relatifs"
    [[ "$COPY_EXTERNAL_LINKS" == true ]] && \
      _note "DRY-RUN : les liens hors cas seraient remplacés par une copie"
  else
    archive_relativiser_liens_symboliques "$STAGING_CAS" "$SOURCE_CAS" "$COPY_EXTERNAL_LINKS"
  fi
fi

# ══════════════════════════════════════════════════════════════════════════════
#  📦 COMPRESSION
# ══════════════════════════════════════════════════════════════════════════════

if [[ "$NO_ARCHIVE" == true ]]; then
  h1 "Compression désactivée (--no-archive)"
  _info "Le staging nettoyé est conservé : $STAGING_CAS"
  _info "Inspectez-le, ajustez les adapt_*, puis relancez sans --no-archive."
else
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
fi

# ══════════════════════════════════════════════════════════════════════════════
#  ✅ RÉSUMÉ FINAL
# ══════════════════════════════════════════════════════════════════════════════

separator_double

if [[ "$DRY_RUN" == true ]]; then
  boite_info "DRY-RUN terminé — aucune modification effectuée"
elif [[ "$NO_ARCHIVE" == true ]]; then
  boite_result "Nettoyage terminé (archive non créée)"

  tableau_init "Propriété" "Valeur"
  tableau_add "Cas source"      "$SOURCE_CAS"
  tableau_add "Staging nettoyé" "$STAGING_CAS"
  source_size_bytes="$(archive_get_size_bytes "$SOURCE_CAS")"
  staging_size_bytes="$(archive_get_size_bytes "$STAGING_CAS")"
  tableau_add "Taille source"  "$(archive_human_size "$source_size_bytes") ($source_size_bytes bytes)"
  tableau_add "Taille staging" "$(archive_human_size "$staging_size_bytes") ($staging_size_bytes bytes)"
  tableau_add "Conservation"   "$keep_tag"
  [[ -n "$HOOK_SCRIPT" ]] && tableau_add "Hook" "$HOOK_SCRIPT"
  tableau_print "Récapitulatif d'archivage (no-archive)"
else
  boite_result "Archivage terminé avec succès"

  tableau_init "Propriété" "Valeur"
  tableau_add "Cas source"     "$SOURCE_CAS"
  tableau_add "Archive"        "$OUTPUT_FILE"
  source_size_bytes="$(archive_get_size_bytes "$SOURCE_CAS")"
  archive_size_bytes="$(archive_get_size_bytes "$OUTPUT_FILE")"
  tableau_add "Taille source"  "$(archive_human_size "$source_size_bytes") ($source_size_bytes bytes)"
  tableau_add "Taille archive" "$(archive_human_size "$archive_size_bytes") ($archive_size_bytes bytes)"
  tableau_add "Conservation"   "$keep_tag"
  [[ -n "$HOOK_SCRIPT" ]] && tableau_add "Hook" "$HOOK_SCRIPT"
  tableau_print "Récapitulatif d'archivage"
fi

_info "Le dossier source n'a pas été modifié : $SOURCE_CAS"
