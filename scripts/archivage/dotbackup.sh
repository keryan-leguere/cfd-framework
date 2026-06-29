#!/usr/bin/env bash
# =============================================================================
#  dotbackup — Export dotfiles and config directories to a target location
#
#  Usage:  dotbackup [OPTIONS] <target-directory>
#  Options:
#    -n, --dry-run    Preview what would be copied (no changes made)
#    -h, --help       Show this help message
#
#  Examples:
#    ./dotbackup.sh ~/dotfiles-backup
#    ./dotbackup.sh -n /tmp/preview
#    ./dotbackup.sh /media/usb/configs
# =============================================================================

set -uo pipefail

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
# Edit these arrays to match your setup.
# All paths are relative to $HOME.

FILES=(
    ".bashrc"
    ".bash_aliases"
    ".bash_profile"
    ".inputrc"
    ".vimrc"
    ".tmux.conf"
    ".gitconfig"
    ".gitignore_global"
    ".editorconfig"
    # ".zshrc"
    # ".zsh_aliases"
    # ".profile"
)

DIRECTORIES=(
    ".vim"
    ".config/tmux"
    ".config/nvim"
    # ".config/alacritty"
    # ".config/kitty"
    # ".ssh"             # ⚠  uncomment with caution — contains sensitive keys
)

# ─── COLORS ───────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    RESET='\033[0m'
else
    RED='' GREEN='' YELLOW='' CYAN='' BOLD='' RESET=''
fi

# ─── GLOBAL STATE ─────────────────────────────────────────────────────────────
DRY_RUN=false
HAS_RSYNC=false
COUNT_OK=0
COUNT_SKIP=0
COUNT_ERR=0

# ─── LOGGING ──────────────────────────────────────────────────────────────────
log_ok()      { printf "  ${GREEN}✔${RESET}  %s\n"  "$*"; }
log_skip()    { printf "  ${YELLOW}–${RESET}  %s\n" "$*"; }
log_err()     { printf "  ${RED}✘${RESET}  %s\n"    "$*" >&2; }
log_dry()     { printf "  ${CYAN}~${RESET}  %s\n"   "$*"; }
log_section() { printf "\n${BOLD}  %s${RESET}\n  %s\n" "$1" "$(printf '─%.0s' {1..42})"; }

# ─── USAGE ────────────────────────────────────────────────────────────────────
usage() {
    cat <<EOF

${BOLD}USAGE${RESET}
    $(basename "$0") [OPTIONS] <target-directory>

${BOLD}OPTIONS${RESET}
    -n, --dry-run    Preview what would be copied (no changes made)
    -h, --help       Show this help message

${BOLD}EXAMPLES${RESET}
    $(basename "$0") ~/dotfiles-backup
    $(basename "$0") -n /tmp/preview
    $(basename "$0") /media/usb/configs

EOF
}

# ─── DEPENDENCY CHECK ─────────────────────────────────────────────────────────
check_deps() {
    command -v rsync &>/dev/null && HAS_RSYNC=true || HAS_RSYNC=false

    if ! $HAS_RSYNC; then
        printf "  ${YELLOW}⚠${RESET}  rsync not found — using cp -r for directories\n"
    fi
}

# ─── SYNC DIRECTORY ───────────────────────────────────────────────────────────
# Syncs src/ into dest/, using rsync if available, cp -r otherwise.
sync_dir() {
    local src="$1"
    local dest="$2"

    if $HAS_RSYNC; then
        rsync -aq --delete "$src/" "$dest/"
    else
        # Remove destination first to replicate --delete behaviour, then copy.
        rm -rf "$dest"
        cp -rp "$src" "$dest"
    fi
}

# ─── COPY ITEM ────────────────────────────────────────────────────────────────
# copy_item <path-relative-to-HOME> <target-dir>
#   Copies a single file or recursively syncs a directory.
#   Silently skips entries that do not exist on this machine.
copy_item() {
    local rel="$1"
    local target="$2"
    local src="$HOME/$rel"
    local dest="$target/$rel"

    # ── Source missing → skip silently ──
    if [[ ! -e "$src" ]]; then
        log_skip "~/$rel  ${YELLOW}(not found, skipping)${RESET}"
        (( ++COUNT_SKIP )) || true
        return 0
    fi

    # ── Dry-run → preview only ──
    if $DRY_RUN; then
        log_dry "~/$rel  →  $dest"
        (( ++COUNT_OK )) || true
        return 0
    fi

    mkdir -p "$(dirname "$dest")"

    # ── Directory → sync ──
    if [[ -d "$src" ]]; then
        if sync_dir "$src" "$dest"; then
            log_ok "~/$rel/"
            (( ++COUNT_OK )) || true
        else
            log_err "~/$rel/  (directory sync failed)"
            (( ++COUNT_ERR )) || true
        fi
    # ── Regular file → cp ──
    else
        if cp -p "$src" "$dest"; then
            log_ok "~/$rel"
            (( ++COUNT_OK )) || true
        else
            log_err "~/$rel  (copy failed)"
            (( ++COUNT_ERR )) || true
        fi
    fi
}

# ─── MAIN ─────────────────────────────────────────────────────────────────────
main() {
    local target=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -n|--dry-run)  DRY_RUN=true; shift ;;
            -h|--help)     usage; exit 0 ;;
            -*)            printf "${RED}Unknown option:${RESET} %s\n\n" "$1" >&2
                           usage; exit 1 ;;
            *)             target="$1"; shift ;;
        esac
    done

    # Require a target directory
    if [[ -z "$target" ]]; then
        printf "${RED}Error:${RESET} No target directory specified.\n\n" >&2
        usage
        exit 1
    fi

    # ── Banner ────────────────────────────────────────────────────────────────
    printf "\n${BOLD}  dotbackup${RESET}\n"
    printf "  %-14s %s\n" "Target:" "$target"
    printf "  %-14s %s\n" "Date:" "$(date '+%Y-%m-%d %H:%M:%S')"
    $DRY_RUN && printf "  ${CYAN}%-14s dry run — no changes will be made${RESET}\n" "Mode:"

    check_deps

    # Create target directory (unless dry run)
    if ! $DRY_RUN; then
        mkdir -p "$target" || {
            log_err "Cannot create target directory: $target"
            exit 1
        }
    fi

    # ── Files ─────────────────────────────────────────────────────────────────
    log_section "Files"
    for rel in "${FILES[@]}"; do
        copy_item "$rel" "$target"
    done

    # ── Directories ───────────────────────────────────────────────────────────
    log_section "Directories"
    for rel in "${DIRECTORIES[@]}"; do
        copy_item "$rel" "$target"
    done

    # ── Summary ───────────────────────────────────────────────────────────────
    log_section "Summary"
    if $DRY_RUN; then
        printf "  ${CYAN}%-14s${RESET} %d\n"   "Would copy:"  "$COUNT_OK"
        printf "  ${YELLOW}%-14s${RESET} %d\n" "Would skip:"  "$COUNT_SKIP"
    else
        printf "  ${GREEN}%-14s${RESET} %d\n"  "Copied:"      "$COUNT_OK"
        printf "  ${YELLOW}%-14s${RESET} %d\n" "Skipped:"     "$COUNT_SKIP"
        [[ $COUNT_ERR -gt 0 ]] && \
            printf "  ${RED}%-14s${RESET} %d\n" "Errors:" "$COUNT_ERR"
    fi
    echo

    [[ $COUNT_ERR -gt 0 ]] && exit 1 || exit 0
}

main "$@"
