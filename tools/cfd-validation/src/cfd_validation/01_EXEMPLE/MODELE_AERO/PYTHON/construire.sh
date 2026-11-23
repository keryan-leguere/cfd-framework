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
#
# Le backend est celui que f2py choisit seul (aucun --backend imposé) : distutils
# tant que numpy.distutils existe (Python < 3.12), meson sinon. Avec
# distutils, FFLAGS passe par --opt (en variable d'environnement, numpy.distutils
# remplacerait aussi -fPIC) ; avec meson, par la variable FFLAGS, que meson lit.
#
# Journal : <DOSSIER>/<NOM>.compilation.log — machine, compilateur, options, backend,
# commandes réellement passées au compilateur, empreintes des sources et du module,
# puis la sortie complète de f2py. Écrit aussi en cas d'échec.
# Prérequis : numpy >= 1.26, un compilateur Fortran ; meson et ninja seulement si f2py
# passe par meson (pip install meson ninja).
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
# meson et ninja (backend meson) installés par pip vivent à côté de l'interpréteur, pas forcément sur PATH
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

# -- backend : celui que f2py prendra de lui-même --------------------------------
if "$PY" -c "import numpy.distutils" >/dev/null 2>&1; then
    BACKEND=distutils
    case "$(basename "$FC")" in
        gfortran*) FCOMPILER=(--fcompiler=gnu95) ;;
        ifort*|ifx*) FCOMPILER=(--fcompiler=intelem) ;;
        *) FCOMPILER=() ;;
    esac
    FC_CHEMIN="$(command -v "$FC" || echo "$FC")"
    OPTIONS_F2PY=(${FCOMPILER[@]+"${FCOMPILER[@]}"} --f77exec="$FC_CHEMIN" --f90exec="$FC_CHEMIN" --opt="$FFLAGS")
    FFLAGS_ENV="$FFLAGS"; unset FFLAGS
else
    BACKEND=meson
    OPTIONS_F2PY=()
    FFLAGS_ENV="$FFLAGS"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
JOURNAL="$DOSSIER/$NOM.compilation.log"
COMMANDE=("$PY" -m numpy.f2py -c --build-dir "$TMP/f2py" ${OPTIONS_F2PY[@]+"${OPTIONS_F2PY[@]}"} -m "$NOM"
          "${SOURCES[@]}" "${INCLUDES[@]/#/-I}")

# Le journal : ce qu'il faut pour refaire la même compilation, ou dire en quoi une autre diffère.
ecrire_journal() {
    local statut="$1" so="${2:-}"
    {
        echo "# Compilation f2py de $NOM — $statut"
        echo "date            : $(date '+%Y-%m-%d %H:%M:%S %z')"
        echo "utilisateur     : $(id -un 2>/dev/null || echo '?')@$(hostname 2>/dev/null || echo '?')"
        echo
        echo "## Machine"
        echo "système         : $(uname -srm)"
        [[ -r /etc/os-release ]] && echo "distribution    : $(. /etc/os-release && echo "${PRETTY_NAME:-?}")"
        echo "processeur      : $(LC_ALL=C lscpu 2>/dev/null | sed -n 's/^Model name: *//p' | head -1)"
        echo "cœurs logiques  : $(nproc 2>/dev/null || echo '?')"
        echo "mémoire         : $(awk '/MemTotal/ {printf "%.1f Go", $2/1048576}' /proc/meminfo 2>/dev/null)"
        echo "jeux SIMD       : $(grep -m1 -o -w -E 'sse4_2|avx|avx2|fma|avx512f|avx512vl' /proc/cpuinfo 2>/dev/null | sort -u | tr '\n' ' ')"
        if [[ "$(basename "$FC")" == gfortran* ]]; then
            echo "-march=native   : $("$FC" -march=native -Q --help=target 2>/dev/null | awk '$1 == "-march=" {print $2; exit}')"
        fi
        [[ -n "${SLURM_JOB_ID:-}" ]] && echo "travail SLURM   : $SLURM_JOB_ID (${SLURM_JOB_PARTITION:-?})"
        echo
        echo "## Compilateurs"
        echo "Fortran (FC)    : $FC -> $(command -v "$FC" || echo introuvable)"
        echo "                  $("$FC" --version 2>&1 | head -1)"
        echo "cible           : $("$FC" -dumpmachine 2>/dev/null || echo '?')"
        echo "options FFLAGS  : $FFLAGS_ENV"
        echo "C (enveloppe)   : ${CC:-cc} -> $(command -v "${CC:-cc}" || echo introuvable)"
        echo "                  $("${CC:-cc}" --version 2>&1 | head -1)"
        echo
        echo "## Python et f2py"
        echo "interpréteur    : $(command -v "$PY") ($("$PY" -c 'import sys; print(sys.version.split()[0])'))"
        echo "numpy           : $("$PY" -c 'import numpy; print(numpy.__version__)' 2>&1)"
        echo "backend f2py    : $BACKEND"
        if [[ $BACKEND == meson ]]; then
            echo "meson / ninja   : $(meson --version 2>/dev/null || echo absent) / $(ninja --version 2>/dev/null || echo absent)"
            echo "                  (meson part de buildtype=release, soit -O3 ; FFLAGS vient après et l'emporte)"
        fi
        echo "commande        : ${COMMANDE[*]}"
        echo
        echo "## Sources (SHA-256)"
        for f in "${SOURCES[@]}" ${INCLUS[@]+"${INCLUS[@]}"}; do
            echo "  $(sha256sum "$f" | cut -d' ' -f1)  $f"
        done
        echo
        echo "## Commandes réelles du compilateur Fortran"
        local cc_json
        cc_json="$(find "$TMP" -name compile_commands.json 2>/dev/null | head -1)"
        if [[ -n "$cc_json" ]]; then
            "$PY" - "$cc_json" <<'EOF'
import json, os, shlex, sys
# Une ligne par source : compilateur et options ; -I, -J, -o et le fichier sont omis
# (la commande complète suit, puis la sortie de f2py).
entrees = [e for e in json.load(open(sys.argv[1])) if e["file"].lower().endswith((".f", ".for", ".f90"))]
for e in entrees:
    mots, garde, saute = shlex.split(e["command"]), [], False
    for m in mots:
        if saute:
            saute = False
        elif m in ("-o", "-c"):
            saute = m == "-o"
        elif not m.startswith(("-I", "-J")) and m != e["file"]:
            garde.append(m)
    print(f"  {os.path.basename(e['file']):<20} {' '.join(garde)}")
if entrees:
    print("  commande complète (" + os.path.basename(entrees[0]["file"]) + ") :")
    print("    " + entrees[0]["command"])
EOF
        else
            grep -E "(^| )$(basename "$FC")[^ ]* .* -c " "$TMP/f2py.log" 2>/dev/null | sed 's/^/  /' || echo "  (non trouvées dans la sortie de f2py)"
        fi
        if [[ -n "$so" ]]; then
            echo
            echo "## Module"
            echo "  $(sha256sum "$so" | cut -d' ' -f1)  $so  ($(stat -c %s "$so") octets)"
        fi
        echo
        echo "## Sortie complète de f2py"
        cat "$TMP/f2py.log" 2>/dev/null
    } > "$JOURNAL"
}

if ! (cd "$TMP" && "${COMMANDE[@]}" > f2py.log 2>&1); then
    cat "$TMP/f2py.log" >&2
    ecrire_journal "ÉCHEC"
    echo "échec de f2py (backend $BACKEND) — journal : $JOURNAL" >&2
    exit 1
fi
mv "$TMP"/"$NOM".*.so "$DOSSIER"/
SO="$(ls "$DOSSIER"/"$NOM".*.so)"
ecrire_journal "réussie" "$SO"
echo "$SO  ($FC $FFLAGS_ENV, backend $BACKEND)"
echo "journal : $JOURNAL"

# Ce que f2py a exposé : « sorties = routine(entrées) », ou un COMMON.
"$PY" - "$DOSSIER" "$NOM" <<'EOF'
import importlib, sys
sys.path.insert(0, sys.argv[1])
m = importlib.import_module(sys.argv[2])
for n in sorted(x for x in dir(m) if not x.startswith("_")):
    tete = (getattr(m, n).__doc__ or "").strip().splitlines()[0]
    print("  " + (f"COMMON /{n}/" if " : " in tete else tete))
EOF
