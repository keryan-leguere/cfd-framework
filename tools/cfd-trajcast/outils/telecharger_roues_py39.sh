#!/usr/bin/env bash
# Télécharge les roues non standard de cfd-trajcast pour une machine air-gap
# (Python 3.9, Linux x86_64, glibc ≥ 2.28 : RHEL/Rocky 8). Voir README, « Machine sans réseau ».
#
#   bash outils/telecharger_roues_py39.sh [DOSSIER]      # défaut : WHEELS_PY39
#
# Il faut un interpréteur 3.9 (PYTHON39, défaut python3.9) : avec un autre, pip évalue les
# conditions `python_version < "3.10"` avec sa propre version et oublie des dépendances.
set -euo pipefail
PY="${PYTHON39:-python3.9}"
DEST="${1:-WHEELS_PY39}"
"$PY" -c 'import sys; assert sys.version_info[:2] == (3, 9), sys.version' \
  || { echo "il faut Python 3.9 (PYTHON39=/chemin/python3.9)" >&2; exit 1; }

STANDARD=(numpy pandas matplotlib pillow pyyaml rich)              # supposés présents sur la cible
NON_STANDARD=(vtk pyvista trimesh imageio imageio-ffmpeg cascadio)
# Interface (cfd-trajcast gui) : PyQt5 tire PyQt5-Qt5 (Qt embarqué, ~60 Mo) et PyQt5-sip ;
# pyvistaqt tire qtpy. Mettre GUI=0 pour s'en passer.
if [ "${GUI:-1}" = 1 ]; then NON_STANDARD+=(PyQt5 pyvistaqt); fi
PLATEFORMES=()
for p in manylinux_2_28 manylinux_2_27 manylinux_2_24 manylinux_2_17 manylinux2014 \
         manylinux_2_12 manylinux2010 linux; do
  PLATEFORMES+=(--platform "${p}_x86_64")
done

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
dl() { "$PY" -m pip download -q --only-binary=:all: "${PLATEFORMES[@]}" --python-version 3.9 \
         --implementation cp --abi cp39 --abi abi3 --abi none "$@"; }
dl -d "$tmp/tout" "${STANDARD[@]}" "${NON_STANDARD[@]}"
"$PY" -m pip download -q --no-index --find-links "$tmp/tout" -d "$tmp/standard" "${STANDARD[@]}"

mkdir -p "$DEST"
for f in "$tmp"/tout/*.whl; do
  [ -e "$tmp/standard/$(basename "$f")" ] || cp "$f" "$DEST/"
done
(cd "$DEST" && sha256sum ./*.whl | sed 's# \./# #' > SHA256SUMS)
echo "$(ls "$DEST"/*.whl | wc -l) roues dans $DEST ($(du -sh "$DEST" | cut -f1))"
