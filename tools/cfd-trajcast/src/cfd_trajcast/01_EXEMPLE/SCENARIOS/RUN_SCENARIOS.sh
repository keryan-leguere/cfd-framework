#!/usr/bin/env bash
# Vérifie puis rend les trois scénarios (aperçu 540p par défaut, --complet pour le 1080p).
set -euo pipefail
cd "$(dirname "$0")"
if command -v cfd-trajcast >/dev/null 2>&1; then CMD=(cfd-trajcast); else CMD=(python3 -m cfd_trajcast); fi
OPTION=(--apercu)
[[ "${1:-}" == "--complet" ]] && OPTION=()
for s in AVION_MANOEUVRES AVION_PANNE FUSEE_BI_ETAGE; do
  "${CMD[@]}" check "$s.yaml"
  "${CMD[@]}" rendre "$s.yaml" "${OPTION[@]}"
done
