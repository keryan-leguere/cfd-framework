#!/usr/bin/env python3
"""Test des bornes de table du modèle aéro (production) : au-delà des grilles, sature-t-il ou extrapole-t-il comme demandé ?

    cd ../../PYTHON && bash construire.sh     # une fois
    cd ../VALIDATION_PRODUCTION/02_BORNES_TABLES
    python 02_bornes_tables.py                 # les 8 tables, à 10 % de l'étendue au-delà de chaque borne
    python 02_bornes_tables.py --ecart 0.25    # plus loin

Version de production de ``VALIDATION/02_BORNES_TABLES/02_bornes_tables.py`` :
aucune option ne change les consignes déclarées. Les tables et leurs consignes
hors bornes sont déclarées dans ``../tables_modele.py``.

Code de retour : 0 conforme, 2 non conforme, 1 erreur (module absent, option inconnue).
"""

from __future__ import annotations

import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))  # VALIDATION_PRODUCTION/ : tables_modele

from tables_modele import DEFAUTS, PYTHON, analyseur, charger_modele, declarer_tables, metadonnees  # noqa: E402

from cfd_validation import valider_bornes_tables  # noqa: E402


def main() -> int:
    p = analyseur(__doc__.splitlines()[0])
    p.add_argument("--ecart", type=float, default=0.10,
                   help="distance hors bornes, en fraction de l'étendue de l'axe (défaut 0.10)")
    p.add_argument("--module", default="aerolib", help="module f2py à tester (défaut aerolib)")
    p.add_argument("--dossier", type=Path, default=PYTHON, help="où chercher le module")
    p.add_argument("--sortie", type=Path, default=None, help="dossier des pièces (défaut SORTIE/nominal)")
    p.add_argument("--sans-figures", action="store_true", help="ne pas tracer la figure de synthèse")
    args = p.parse_args()

    modele = charger_modele(args.module, args.dossier)
    if modele is None:
        return 1
    res = valider_bornes_tables(
        declarer_tables(modele),
        evaluer=modele.calcul_aero_elementaire,
        defauts=DEFAUTS,
        ecart=args.ecart,
        identifiant="VAL-TAB-02",
        metadonnees={**metadonnees(modele, "nominal"), "écart": f"{args.ecart * 100:g} % de l'étendue"},
        sortie=args.sortie or ICI / "SORTIE" / "nominal",
        figures=not args.sans_figures,
        nettoyer=True,
    )
    return 0 if res.conforme else 2


if __name__ == "__main__":
    sys.exit(main())
