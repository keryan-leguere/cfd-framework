#!/usr/bin/env python3
"""Test de lecture de table du modèle aéro (production) : chaque nœud de chaque table, relu par le code.

    cd ../../PYTHON && bash construire.sh     # une fois : le module instrumenté (sondes /PROBE/)
    cd ../VALIDATION_PRODUCTION/01_LECTURE_TABLES
    python 01_lecture_tables.py                # les 8 tables, entrées libres aux défauts
    python 01_lecture_tables.py --combinaisons # + invariance : toutes les combinaisons des autres entrées

Version de production de ``VALIDATION/01_LECTURE_TABLES/01_lecture_tables.py`` :
aucune option ne fausse la référence. Les tables sont déclarées dans
``../tables_modele.py``.

Code de retour : 0 conforme, 2 non conforme, 1 erreur (module absent, option inconnue).
"""

from __future__ import annotations

import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))  # VALIDATION_PRODUCTION/ : tables_modele

from tables_modele import DEFAUTS, PYTHON, analyseur, charger_modele, declarer_tables, metadonnees  # noqa: E402

from cfd_validation import valider_lecture_tables  # noqa: E402

#: --combinaisons : chaque nœud rejoué pour toutes les combinaisons de ces valeurs
#: (entrées que la table ne pilote pas). La lecture d'une table n'en dépend pas.
COMBINAISONS: dict[str, list[float]] = {
    "alpha": [-5.0, 0.0, 5.0],
    "beta": [-5.0, 0.0, 5.0],
    "xg": [1.0, 1.4],
    "ipropu": [0.0, 1.0],   # entier côté Fortran : converti à l'appel, 0.5 serait refusé
    "dm": [-10.0, 0.0, 10.0],
}


def main() -> int:
    p = analyseur(__doc__.splitlines()[0])
    p.add_argument("--combinaisons", action="store_true", help="rejouer chaque nœud pour toutes les combinaisons des autres entrées")
    p.add_argument("--module", default="aerolib", help="module f2py à tester (défaut aerolib)")
    p.add_argument("--dossier", type=Path, default=PYTHON, help="où chercher le module")
    p.add_argument("--sortie", type=Path, default=None, help="dossier des pièces (défaut SORTIE/<scénario>)")
    p.add_argument("--sans-figures", action="store_true", help="ne pas tracer la figure de synthèse")
    args = p.parse_args()

    modele = charger_modele(args.module, args.dossier)
    if modele is None:
        return 1
    scenario = "combinaisons" if args.combinaisons else "nominal"
    res = valider_lecture_tables(
        declarer_tables(modele),
        evaluer=modele.calcul_aero_elementaire,
        defauts=DEFAUTS,
        combinaisons=COMBINAISONS if args.combinaisons else None,
        identifiant="VAL-TAB-01",
        metadonnees=metadonnees(modele, scenario),
        sortie=args.sortie or ICI / "SORTIE" / scenario,
        figures=not args.sans_figures,
        nettoyer=True,
    )
    return 0 if res.conforme else 2


if __name__ == "__main__":
    sys.exit(main())
