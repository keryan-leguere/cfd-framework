#!/usr/bin/env bash
# Exemple complet de cfd-nozzle. Tout est écrit dans SORTIE/.
set -euo pipefail

ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SORTIE="$ICI/SORTIE"
mkdir -p "$SORTIE"

echo "=== 1. Validation du fichier de cas ==============================="
cfd-nozzle check "$ICI/CAS_MOTEUR.yaml"

echo
echo "=== 2. Analyse du point de fonctionnement + figures ==============="
cfd-nozzle run "$ICI/CAS_MOTEUR.yaml" --figure "$SORTIE"

echo
echo "=== 3. Le même moteur en altitude (sous-détendu) =================="
cfd-nozzle tuyere --p0 100e5 --t0 3500 --pa 5e3 \
  --diametre-col 0.20 --eps 16 --gaz lox_rp1 --eta-cstar 0.96 --lambda-contour

echo
echo "=== 4. Contour galbé de Rao, exporté pour le maillage ============="
cfd-nozzle geometrie --rayon-col 0.10 --eps 16 --type bell \
  --export "$SORTIE/contour_galbe.dat" --figure "$SORTIE"

echo
echo "=== 5. Tuyère à longueur minimale (MOC), axisymétrique ============"
cfd-nozzle moc --mach-sortie 2.4 --n 30 --axisymetrique \
  --export "$SORTIE/contour_moc.dat" --figure "$SORTIE"

echo
echo "=== 6. Balayage en altitude : quel ε choisir ? ===================="
python3 "$ICI/balayage_altitude.py" "$SORTIE"

echo
echo "Terminé — résultats dans $SORTIE"
