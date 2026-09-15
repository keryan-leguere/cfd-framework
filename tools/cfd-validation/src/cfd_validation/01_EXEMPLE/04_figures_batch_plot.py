"""4 — Les planches : la table et le modèle superposés.

Un appel de `cfd_plot.batch_plot` par table. Dans chacun, deux configurations —
TABLE, ce qui est écrit dans le COMMON block, et MODELE, ce que le code en a
relu — et une polaire par variable indépendante, les autres variables devenant
des niveaux de répertoire.

Les points hors tolérance sont entourés de rouge et reliés à leur valeur
tabulée, et un encadré dit combien il y en a sur la planche. C'est ce qui rend
la panne visible : une courbe fausse, seule, reste lisse.

    python3 04_figures_batch_plot.py                 # trace
    python3 04_figures_batch_plot.py --a-blanc       # énumère sans écrire
    python3 04_figures_batch_plot.py --toutes-valeurs

Nécessite cfd-plot :  pip install -e ../../cfd-plot
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import mon_modele
from cfd_validation import charger_fichier, valider_tables
from cfd_validation.report.figures import planches_prevues, tracer_rapport
from cfd_validation.report.parcours import imprimer_bilan, imprimer_plan
from cfd_validation.wrap.factice import ModeleFactice, module_factice

import aero_factice

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--sortie", type=Path, default=Path("SORTIE") / "FIGURE")
parser.add_argument("--a-blanc", action="store_true", dest="a_blanc")
parser.add_argument(
    "--toutes-valeurs",
    action="store_true",
    help="ne pas échantillonner les variables épinglées (beaucoup plus de planches)",
)
parser.add_argument(
    "--juste",
    action="store_true",
    help="tracer le modèle juste plutôt que le modèle écrêté",
)
args = parser.parse_args()

specs = charger_fichier("TABLES.yaml")

# Par défaut on trace une panne : sur un modèle juste, les deux courbes se
# superposent exactement, ce qui est rassurant mais peu instructif.
if args.juste:
    rapport = valider_tables(aero_factice, specs, modele=mon_modele.appeler)
else:
    module = module_factice()
    rapport = valider_tables(module, specs, modele=ModeleFactice(module, bug="ecretage"))

max_valeurs = None if args.toutes_valeurs else 5

imprimer_plan(
    rapport,
    sortie=args.sortie,
    planches=planches_prevues(rapport, max_valeurs=max_valeurs),
    max_valeurs=max_valeurs,
    a_blanc=args.a_blanc,
)

ecrits = tracer_rapport(
    rapport,
    sortie=args.sortie,
    formats=("png",),
    max_valeurs=max_valeurs,
    a_blanc=args.a_blanc,
    compte_rendu=False,
)

imprimer_bilan(ecrits, a_blanc=args.a_blanc)
