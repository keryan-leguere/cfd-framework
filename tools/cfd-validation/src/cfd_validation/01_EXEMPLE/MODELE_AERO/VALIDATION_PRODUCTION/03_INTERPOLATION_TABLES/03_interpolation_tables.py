#!/usr/bin/env python3
"""Test d'interpolation de table du modèle aéro (production) : entre les nœuds, le code interpole-t-il la table ?

    cd ../../PYTHON && bash construire.sh          # une fois
    cd ../VALIDATION_PRODUCTION/03_INTERPOLATION_TABLES
    python 03_interpolation_tables.py               # les 8 tables, ¼ ½ ¾ de chaque maille + centres, polaires
    python 03_interpolation_tables.py --jobs 4      # polaires tracées sur 4 processus

Version de production de ``VALIDATION/03_INTERPOLATION_TABLES/03_interpolation_tables.py`` :
le code est toujours appelé tel quel, aucune option ne remplace l'évaluateur.
Les tables, leurs polaires et les libellés des axes sont déclarés dans
``../tables_modele.py``.

Code de retour : 0 conforme, 2 non conforme, 1 erreur (module absent, option inconnue).
"""

from __future__ import annotations

import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))  # VALIDATION_PRODUCTION/ : tables_modele

from tables_modele import (  # noqa: E402
    DEFAUTS,
    LIBELLES,
    POLAIRES,
    PYTHON,
    analyseur,
    charger_modele,
    declarer_tables,
    metadonnees,
)

from cfd_validation import valider_interpolation_tables  # noqa: E402


def main() -> int:
    p = analyseur(__doc__.splitlines()[0])
    p.add_argument("--fractions", type=float, nargs="+", default=[0.25, 0.5, 0.75],
                   help="positions dans chaque maille, strictement entre 0 et 1 (défaut 0.25 0.5 0.75)")
    p.add_argument("--jobs", type=int, default=1, help="processus pour tracer les polaires (-1 : tous)")
    p.add_argument("--sans-superposition", action="store_true",
                   help="ne pas tracer les figures superposées (fold « overlay » de batch_plot)")
    p.add_argument("--module", default="aerolib", help="module f2py à tester (défaut aerolib)")
    p.add_argument("--dossier", type=Path, default=PYTHON, help="où chercher le module")
    p.add_argument("--sortie", type=Path, default=None, help="dossier des pièces (défaut SORTIE/nominal)")
    p.add_argument("--sans-figures", action="store_true", help="ne pas tracer les polaires")
    args = p.parse_args()

    modele = charger_modele(args.module, args.dossier)
    if modele is None:
        return 1
    res = valider_interpolation_tables(
        declarer_tables(modele),
        evaluer=modele.calcul_aero_elementaire,
        defauts=DEFAUTS,
        fractions=args.fractions,
        polaires=POLAIRES,
        libelles=LIBELLES,
        superposer=not args.sans_superposition,
        n_jobs=args.jobs,
        identifiant="VAL-TAB-03",
        metadonnees=metadonnees(modele, "nominal"),
        sortie=args.sortie or ICI / "SORTIE" / "nominal",
        figures=not args.sans_figures,
        nettoyer=True,
    )
    return 0 if res.conforme else 2


if __name__ == "__main__":
    sys.exit(main())
