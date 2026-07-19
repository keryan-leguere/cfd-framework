#!/usr/bin/env bash
# Exemple cfd-atm : rapport d'un point + génération des diagrammes iso-Vc.
set -euo pipefail

cd "$(dirname "$0")"

# Résoudre le package `plotting` du framework si CFD_FRAMEWORK n'est pas déjà posé.
if [[ -z "${CFD_FRAMEWORK:-}" ]]; then
  CFD_FRAMEWORK="$(cd ../../.. && pwd)"
  export CFD_FRAMEWORK
fi
echo "CFD_FRAMEWORK = $CFD_FRAMEWORK"

echo
echo "=== 1. Point atmosphérique : FL350, ISA+10, Vc = 280 kt ==="
cfd-atm point --altitude 35000 --nature pression --unite-altitude ft \
  --modele ISA+X --dt 10 --vitesse 280 --grandeur cas --unite-vitesse kt

echo
echo "=== 2. Génération des diagrammes iso-Vc / iso-TAS ==="
python3 tracer_iso_vitesses.py

echo
echo "Figures disponibles dans : $(pwd)/SORTIE"
ls -1 SORTIE
