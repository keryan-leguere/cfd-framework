#!/usr/bin/env bash
# Run ParaView state with custom data files and export a snapshot (CLI wrapper).
# Requires: pvpython on PATH (ParaView installation).
#
# Usage:
#   run_state_snapshot.sh STATE.pvsm OUTPUT.png [FILE1 [FILE2 ...]]
#   run_state_snapshot.sh STATE.pvsm OUTPUT.png --data-dir /path/to/data
#
# Example:
#   run_state_snapshot.sh my_state.pvsm snapshot.png result_001.vtk result_002.vtk

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="${SCRIPT_DIR}/run_state_and_snapshot.py"

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 STATE.pvsm OUTPUT.png [FILE1 [FILE2 ...]]" >&2
  echo "   or: $0 STATE.pvsm OUTPUT.png --data-dir /path/to/data" >&2
  exit 1
fi

if ! command -v pvpython &>/dev/null; then
  echo "Error: pvpython not found. Add ParaView bin directory to PATH." >&2
  exit 1
fi

exec pvpython "$RUNNER" "$@"
