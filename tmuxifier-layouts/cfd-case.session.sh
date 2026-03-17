# ═══════════════════════════════════════════════════════════════════════════════
#  cfd-case — tmuxifier session layout for CFD cases
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Required environment variables (set by cfd-creer):
#    CFD_CASE_NAME   — Name of the CFD case (used as session name)
#    CFD_BASE_DIR    — Absolute path to the case directory
#
#  Optional environment variables:
#    CFD_BINARY_CMD  — Command to auto-run in a dedicated BINARY window
#    CFD_POST_CMD    — Command to auto-run in a dedicated POST window
#
# ═══════════════════════════════════════════════════════════════════════════════

: "${CFD_CASE_NAME:?CFD_CASE_NAME must be set}"
: "${CFD_BASE_DIR:?CFD_BASE_DIR must be set}"

session_root "$CFD_BASE_DIR"

if initialize_session "$CFD_CASE_NAME"; then

  # Propagate runtime variables to every pane spawned in this session
  tmux setenv -t "$session:" CASE_NAME  "$CFD_CASE_NAME"
  tmux setenv -t "$session:" CONTEXT    "DEV"
  tmux setenv -t "$session:" CASE_PATH  "$CFD_BASE_DIR"

  # ── SETUP ──────────────────────────────────────────────────────────────────
  new_window "SETUP"

  # ── CONFIGURATION ──────────────────────────────────────────────────────────
  new_window "CONFIGURATION"
  run_cmd "cd '${CFD_BASE_DIR}/02_PARAMS' 2>/dev/null || cd '${CFD_BASE_DIR}'"

  # ── RESULTAT ───────────────────────────────────────────────────────────────
  new_window "RESULTAT"
  run_cmd "cd '${CFD_BASE_DIR}/08_RESULTAT' 2>/dev/null || cd '${CFD_BASE_DIR}'"

  # ── DATA ───────────────────────────────────────────────────────────────────
  new_window "DATA"
  run_cmd "cd '${CFD_BASE_DIR}/09_POST_TRAITEMENT/DATA' 2>/dev/null || cd '${CFD_BASE_DIR}'"

  # ── FIGURE (split: Python scripts top, figures output bottom) ──────────────
  new_window "FIGURE"
  run_cmd "cd '${CFD_BASE_DIR}/10_SCRIPT/POST_TRAITEMENT/PYTHON/FIGURE' 2>/dev/null || cd '${CFD_BASE_DIR}'"
  split_v 50
  run_cmd "cd '${CFD_BASE_DIR}/09_POST_TRAITEMENT/FIGURE' 2>/dev/null || cd '${CFD_BASE_DIR}'"
  select_pane 0

  # ── Optional: auto-start a binary ──────────────────────────────────────────
  if [[ -n "${CFD_BINARY_CMD:-}" ]]; then
    new_window "BINARY"
    run_cmd "$CFD_BINARY_CMD"
  fi

  # ── Optional: auto-start post-processing ───────────────────────────────────
  if [[ -n "${CFD_POST_CMD:-}" ]]; then
    new_window "POST"
    run_cmd "$CFD_POST_CMD"
  fi

  # Focus the SETUP window on session start
  select_window "SETUP"

fi

finalize_and_go_to_session
