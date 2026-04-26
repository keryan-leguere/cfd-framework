# ═══════════════════════════════════════════════════════════════════════════════
#  cfd-case — tmuxifier session layout for CFD cases
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Required environment variables (set by cfd-creer):
#    CASE_NAME        — Name of the CFD case (used as session name)
#    CASE_PATH        — Absolute path to the case directory
#    CFD_CASE_IS_NEW  — 1 if newly created, 0 if existing
#    CFD_LAYOUT_DIR   — Path to tmuxifier-layouts directory (for overrides)
#
# ═══════════════════════════════════════════════════════════════════════════════

: "${CASE_NAME:?CASE_NAME must be set}"
: "${CASE_PATH:?CASE_PATH must be set}"
: "${CFD_CASE_IS_NEW:=0}"
: "${CFD_LAYOUT_DIR:=}"

session_root "$CASE_PATH"

if initialize_session "$CASE_NAME"; then

  # Detect pane-base-index now that the server is guaranteed to be running.
  _pb=$(tmux show-options -gv pane-base-index 2>/dev/null) || _pb=0

  tmux setenv -t "$session:" CASE_NAME "$CASE_NAME"
  tmux setenv -t "$session:" CASE_PATH "$CASE_PATH"

  # ── CAS ────────────────────────────────────────────────────────────────────
  new_window "CAS"
  run_cmd "ls -larth"
  split_v 50
  run_cmd "htop"
  select_pane "$_pb"

  # ── HPC ────────────────────────────────────────────────────────────────────
  # Override: drop an executable hpc.window.sh in CFD_LAYOUT_DIR and it will
  # be sourced instead of the default layout below.  The override file has
  # access to the same tmuxifier primitives (new_window, split_v, run_cmd …).
  _hpc_override="${CFD_LAYOUT_DIR:+${CFD_LAYOUT_DIR}/hpc.window.sh}"
  if [[ -n "$_hpc_override" && -f "$_hpc_override" ]]; then
    source "$_hpc_override"
  else
    new_window "HPC"
    run_cmd "echo '[HPC] top pane — placeholder'"
    split_v 50
    # Bottom half: 20 % left / 80 % right
    split_h 80
    run_cmd "echo '[HPC] bottom-right — placeholder'"
    select_pane "$((_pb + 1))"
    run_cmd "echo '[HPC] bottom-left — placeholder'"
    select_pane "$_pb"
  fi

  # ── MAILLAGE ───────────────────────────────────────────────────────────────
  new_window "MAILLAGE"
  run_cmd "cd '${CASE_PATH}/01_MAILLAGE' 2>/dev/null || true"
  split_v 20
  run_cmd "htop"
  select_pane "$_pb"

  # ── PARAMS windows ─────────────────────────────────────────────────────────
  _params_dir="${CASE_PATH}/02_PARAMS"

  if [[ -d "$_params_dir" ]]; then
    if [[ "$CFD_CASE_IS_NEW" -eq 1 ]]; then
      # New case: open only the first subdirectory
      _dirs=("${_params_dir}"/*/)
      if [[ -d "${_dirs[0]:-}" ]]; then
        _dir="${_dirs[0]}"
        _name="$(basename "$_dir")"
        new_window "$_name"
        run_cmd "cd '${_dir}' && echo \"Statistics: \$(du -sh . 2>/dev/null | cut -f1) — \$(find . -type f | wc -l) files\""
        split_v 10
        run_cmd "cd '${_dir}' && echo '${_name} monitoring'"
        select_pane "$_pb"
      fi
    else
      # Existing case: one window per subdirectory
      for _dir in "${_params_dir}"/*/; do
        [[ -d "$_dir" ]] || continue
        _name="$(basename "$_dir")"
        new_window "$_name"
        run_cmd "cd '${_dir}' && echo \"Statistics: \$(du -sh . 2>/dev/null | cut -f1) — \$(find . -type f | wc -l) files\""
        split_v 10
        run_cmd "cd '${_dir}' && echo '${_name} monitoring'"
        select_pane "$_pb"
      done
    fi
  fi

  # ── DOCUMENTATION ──────────────────────────────────────────────────────────
  new_window "DOCUMENTATION"
  run_cmd "cd '${CASE_PATH}/05_DOCUMENTATION' 2>/dev/null || cd '${CASE_PATH}'"
  split_h 50
  run_cmd "cd '${CASE_PATH}/06_REFERENCE' 2>/dev/null || cd '${CASE_PATH}'"

  # ── POST_TRAITEMENT ────────────────────────────────────────────────────────
  new_window "POST_TRAITEMENT"
  run_cmd "cd '${CASE_PATH}/09_POST_TRAITEMENT/DATA' 2>/dev/null || cd '${CASE_PATH}'"
  split_h 50
  run_cmd "cd '${CASE_PATH}/09_POST_TRAITEMENT/FIGURE' 2>/dev/null || cd '${CASE_PATH}'"

  # ── GIT ───────────────────────────────────────────────────────────────────
  new_window "GIT"
  run_cmd "watch -n 5 --color git -c color.status=always status --short --branch"
  split_v 30
  run_cmd "git log --oneline --graph --decorate -20"
  select_pane "$_pb"

  # ── SCRIPT ─────────────────────────────────────────────────────────────────
  new_window "SCRIPT"
  run_cmd "cd '${CASE_PATH}/10_SCRIPT' 2>/dev/null || cd '${CASE_PATH}'"
  run_cmd "vim"

  # Focus CAS on session start
  select_window "CAS"

fi

finalize_and_go_to_session
