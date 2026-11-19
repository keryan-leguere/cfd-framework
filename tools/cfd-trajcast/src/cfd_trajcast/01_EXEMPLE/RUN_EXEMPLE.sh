#!/usr/bin/env bash
# Vérifie les deux lectures du vol de référence. Repli sur `python -m` si le
# script console est absent ou cassé.
set -euo pipefail
cd "$(dirname "$0")"
if command -v cfd-trajcast >/dev/null 2>&1; then CMD=(cfd-trajcast); else CMD=(python3 -m cfd_trajcast); fi
"${CMD[@]}" check CONFIG.yaml
"${CMD[@]}" check CONFIG_EULER.yaml   # demande l'extra [step]
"${CMD[@]}" check CONFIG_MULTIVUES.yaml
"${CMD[@]}" rendre CONFIG_MULTIVUES.yaml --apercu
"${CMD[@]}" rendre CONFIG_ENSEMBLE.yaml --apercu
"${CMD[@]}" ensemble CONFIG_ENSEMBLE.yaml --video --apercu   # vue d'ensemble seule : SVG + MP4
python3 vue_ensemble.py --svg-seul                          # la même, depuis Python
"${CMD[@]}" rendre CONFIG_VIRAGE.yaml --apercu
# RocketPy (Python ≥ 3.10, pip install 'cfd-trajcast[rocketpy]') : sauté s'il est absent.
if python3 -c "import rocketpy" >/dev/null 2>&1; then
  (cd ROCKETPY && "${CMD[@]}" rendre CONFIG_ROCKETPY.yaml --apercu)
else
  echo "RocketPy absent : exemple ROCKETPY/ sauté"
fi
