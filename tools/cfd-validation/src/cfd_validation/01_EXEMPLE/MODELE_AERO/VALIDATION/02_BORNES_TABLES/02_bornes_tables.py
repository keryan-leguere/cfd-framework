#!/usr/bin/env python3
"""Test des bornes de table du modèle aéro : au-delà des grilles, sature-t-il ou extrapole-t-il comme demandé ?

    cd ../../PYTHON && bash construire.sh     # une fois
    cd ../VALIDATION/02_BORNES_TABLES
    python 02_bornes_tables.py                 # les 11 déclarations, à 10 % de l'étendue au-delà de chaque borne
    python 02_bornes_tables.py --ecart 0.25    # plus loin
    python 02_bornes_tables.py --defaut        # consigne d'alpha de CX déclarée « sature » : NON CONFORME

Les tables et leurs consignes hors bornes (``bornes=``) sont déclarées dans
``../tables_modele.py``, commun à tous les tests. Pour chaque axe et chaque
côté, le code est appelé sur toute la face de la table déplacée au-delà de la
borne ; la valeur attendue est calculée sur la table selon la consigne, et le
rapport dit ce que le code fait réellement (« observé »).

Code de retour : 0 conforme, 2 non conforme.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))  # VALIDATION/ : tables_modele

from tables_modele import DEFAUTS, PYTHON, charger_modele, declarer_tables, metadonnees  # noqa: E402

from cfd_validation import valider_bornes_tables  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--ecart", type=float, default=0.10,
                   help="distance hors bornes, en fraction de l'étendue de l'axe (défaut 0.10)")
    p.add_argument("--defaut", action="store_true",
                   help="déclarer « sature » pour alpha de CX, que le code extrapole (verdict NON CONFORME)")
    p.add_argument("--module", default="aerolib", help="module f2py à tester (défaut aerolib)")
    p.add_argument("--dossier", type=Path, default=PYTHON, help="où chercher le module")
    p.add_argument("--sortie", type=Path, default=None, help="dossier des pièces (défaut SORTIE/<scénario>)")
    p.add_argument("--sans-figures", action="store_true", help="ne pas tracer la figure de synthèse")
    args = p.parse_args()

    modele = charger_modele(args.module, args.dossier)
    if modele is None:
        return 1
    scenario = "defaut" if args.defaut else "nominal"
    res = valider_bornes_tables(
        declarer_tables(modele, consigne_cx_alpha="sature" if args.defaut else None),
        evaluer=modele.calcul_aero_elementaire,
        defauts=DEFAUTS,
        ecart=args.ecart,
        identifiant="VAL-TAB-02",
        metadonnees={**metadonnees(modele, scenario), "écart": f"{args.ecart * 100:g} % de l'étendue"},
        sortie=args.sortie or ICI / "SORTIE" / scenario,
        figures=not args.sans_figures,
        nettoyer=True,
    )
    return 0 if res.conforme else 2


if __name__ == "__main__":
    sys.exit(main())
