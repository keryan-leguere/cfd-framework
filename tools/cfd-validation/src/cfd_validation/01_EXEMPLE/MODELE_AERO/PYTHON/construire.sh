#!/usr/bin/env bash
# Compile les sources Fortran en module Python avec f2py.
#
#   bash construire.sh                                      # aerolib, -O2, dans ce dossier
#   FFLAGS="-O3 -ffast-math" bash construire.sh aerolib_o3  # une autre compilation, sous un autre nom
#   FC=ifx bash construire.sh aerolib /ailleurs             # autre compilateur, autre dossier
#
# Arguments : [NOM [DOSSIER]]. Variables : FFLAGS (défaut -O2), FC (défaut gfortran),
# CFD_VALIDATION_PYTHON (interpréteur qui a numpy, défaut python3).
#
# Pour un autre code : modifier DOSSIER_SOURCES (et au besoin MOTIFS, INCLUDES) ci-dessous.
# Tout fichier du dossier qui répond à un motif est compilé : n'y laisser que le code livré.
#
# f2py lit les directives « Cf2py intent(in/out) » placées après chaque ENTRY ; chaque
# phase devient une fonction du module. Le nom du module est figé dans le binaire
# (PyInit_<nom>) : deux compilations à comparer se construisent sous deux noms.
# Prérequis : numpy >= 1.26, un compilateur Fortran, meson et ninja (pip install meson ninja).
set -euo pipefail

ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RACINE="$(dirname "$ICI")"

# -- ce qui change d'un code à l'autre ---------------------------------------
DOSSIER_SOURCES="$RACINE/SOURCES"                  # les sources Fortran, en un dossier
MOTIFS=("*.f" "*.F" "*.for" "*.f90" "*.F90")      # ce qui y est compilé
INCLUDES=("$DOSSIER_SOURCES")                      # dossiers des INCLUDE (-I), ici le même
# -----------------------------------------------------------------------------

NOM="${1:-aerolib}"
DOSSIER="$(mkdir -p "${2:-$ICI}" && cd "${2:-$ICI}" && pwd)"
PY="${CFD_VALIDATION_PYTHON:-python3}"
export FC="${FC:-gfortran}"
export FFLAGS="${FFLAGS:--O2}"
# meson et ninja installés par pip vivent à côté de l'interpréteur, pas forcément sur PATH
export PATH="$(dirname "$(command -v "$PY")"):$PATH"

[[ -d "$DOSSIER_SOURCES" ]] || { echo "dossier des sources introuvable : $DOSSIER_SOURCES" >&2; exit 1; }
shopt -s nullglob
SOURCES=()
for motif in "${MOTIFS[@]}"; do
    SOURCES+=("$DOSSIER_SOURCES"/$motif)
done
shopt -u nullglob
# ordre stable, sans doublon (un système de fichiers insensible à la casse rend *.f et *.F deux fois)
mapfile -t SOURCES < <(printf '%s\n' "${SOURCES[@]}" | sort -u)
if [[ ${#SOURCES[@]} -eq 0 || -z "${SOURCES[0]}" ]]; then
    echo "aucune source ${MOTIFS[*]} dans $DOSSIER_SOURCES" >&2
    exit 1
fi
echo "sources ($DOSSIER_SOURCES) : $(for f in "${SOURCES[@]}"; do printf '%s ' "$(basename "$f")"; done)"
# f2py lit les sources en ASCII : un seul accent dans un commentaire fait échouer la lecture.
# Les INCLUDE sont lus aussi : on les vérifie avec.
INCLUS=()
for d in "${INCLUDES[@]}"; do
    shopt -s nullglob; INCLUS+=("$d"/*.inc "$d"/*.h "$d"/*.fi); shopt -u nullglob
done
if LC_ALL=C grep -n $'[\x80-\xff]' "${SOURCES[@]}" "${INCLUS[@]}"; then
    echo "caractères non ASCII ci-dessus : f2py les refuse" >&2
    exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
(cd "$TMP" && "$PY" -m numpy.f2py -c --backend meson -m "$NOM" "${SOURCES[@]}" "${INCLUDES[@]/#/-I}" \
    > f2py.log 2>&1) || { cat "$TMP/f2py.log" >&2; echo "échec de f2py" >&2; exit 1; }
mv "$TMP"/"$NOM".*.so "$DOSSIER"/
echo "$(ls "$DOSSIER"/"$NOM".*.so)  ($FC $FFLAGS)"

# Ce que f2py a exposé : « sorties = routine(entrées) », ou un COMMON.
"$PY" - "$DOSSIER" "$NOM" <<'EOF'
import importlib, sys
sys.path.insert(0, sys.argv[1])
m = importlib.import_module(sys.argv[2])
for n in sorted(x for x in dir(m) if not x.startswith("_")):
    tete = (getattr(m, n).__doc__ or "").strip().splitlines()[0]
    print("  " + (f"COMMON /{n}/" if " : " in tete else tete))
EOF
