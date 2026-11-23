#!/usr/bin/env bash
# Une cible CMake en une commande, depuis n'importe quel dossier :
#
#   bash cmake.sh                     # le module (cible par défaut)
#   bash cmake.sh validation          # une ou plusieurs cibles : bash cmake.sh modele exemple
#   bash cmake.sh aide                # toutes les cibles
#
# Configure le dossier de construction s'il ne l'est pas encore (c'est l'oubli de
# « cmake -B build » qui donne « build is not a directory »), puis construit.
# Dossier de construction : CFD_VALIDATION_BUILD (défaut <ce dossier>/build).
# Réglages (FFLAGS, MODELE_NOM…) : une fois cmake -B build -DFFLAGS="-O3 -march=native",
# puis cmake.sh comme d'habitude ; build/ les garde.
set -euo pipefail
ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="${CFD_VALIDATION_BUILD:-$ICI/build}"
command -v cmake >/dev/null || { echo "cmake introuvable : bash PYTHON/construire.sh et les scripts de VALIDATION/ marchent sans" >&2; exit 1; }
if [[ ! -f "$BUILD/CMakeCache.txt" ]]; then
    cmake -S "$ICI" -B "$BUILD"
fi
if [[ $# -eq 0 ]]; then
    exec cmake --build "$BUILD"
fi
exec cmake --build "$BUILD" --target "$@"
