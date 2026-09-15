#!/usr/bin/env bash
# Déroule l'exemple complet, dans l'ordre.
#
# On appelle `python3 -m` plutôt que le script console `cfd-validation` :
# pip grave `sys.executable` dans le shebang du script console, et ce chemin
# est faux partout où l'interpréteur n'est pas là où pip croyait — Python servi
# depuis une image Apptainer, environnement virtuel déplacé, chemin plus long
# que les 127 octets que le noyau accepte dans un `#!`.
#
#   CFD_VALIDATION_PYTHON=/chemin/vers/python bash RUN_EXEMPLE.sh
set -euo pipefail

PY="${CFD_VALIDATION_PYTHON:-python3}"
cd "$(dirname "$0")"

titre() { printf '\n\033[36m=== %s ===\033[0m\n' "$1"; }

titre "1. Lire les tables dans les COMMON blocks"
"$PY" 01_lire_table.py

titre "2. Contrôler un modèle juste"
"$PY" 02_valider.py

titre "3. Rejouer chaque panne, et nommer son motif"
"$PY" 03_diagnostics.py

titre "4. Tracer les planches (nécessite cfd-plot)"
if "$PY" -c "import cfd_plot" 2>/dev/null; then
    "$PY" 04_figures_batch_plot.py
else
    echo "cfd-plot absent : pip install -e ../../cfd-plot — on passe."
fi

titre "5. Le même contrôle sur du Fortran réellement compilé"
"$PY" 05_fortran_reel.py

titre "6. La même chose en ligne de commande"
"$PY" -m cfd_validation toolchain || true
"$PY" -m cfd_validation check --tables TABLES.yaml
"$PY" -m cfd_validation inspecter --module aero_factice
"$PY" -m cfd_validation valider \
    --tables TABLES.yaml \
    --module aero_factice \
    --modele mon_modele:appeler

printf '\n\033[32mExemple déroulé.\033[0m Les sorties sont dans SORTIE/.\n'
