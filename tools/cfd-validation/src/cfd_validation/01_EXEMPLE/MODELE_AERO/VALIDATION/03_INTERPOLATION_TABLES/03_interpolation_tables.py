#!/usr/bin/env python3
"""Test d'interpolation de table du modèle aéro : entre les nœuds, le code interpole-t-il la table ?

    cd ../../PYTHON && bash construire.sh          # une fois
    cd ../VALIDATION/03_INTERPOLATION_TABLES
    python 03_interpolation_tables.py               # les 8 tables, ¼ ½ ¾ de chaque maille + centres, polaires
    python 03_interpolation_tables.py --jobs 4      # polaires tracées sur 4 processus
    python 03_interpolation_tables.py --defaut      # CM relu en palier (simulé) : NON CONFORME

Les tables, leurs polaires et les libellés des axes sont déclarés dans
``../tables_modele.py``, commun à tous les tests. Pour chaque table, le code est
appelé dans chaque maille de chaque axe (les autres axes sur leurs nœuds) et au
centre de chaque maille ; la valeur attendue est l'interpolation multilinéaire
de la table, et le rapport dit ce que le code fait réellement (« observé »).

Les polaires (``SORTIE/<scénario>/POLAIRES/``, ``cfd_plot.batch_plot``, SVG)
montrent les trois tests de table d'un coup d'œil : la courbe du code (trait
vermillon) passe par les nœuds (points bleus), droite entre eux, et sature ou
se prolonge dans les zones grisées au-delà des bornes, selon la consigne.

Code de retour : 0 conforme, 2 non conforme.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))  # VALIDATION/ : tables_modele

from tables_modele import (  # noqa: E402
    DEFAUTS,
    LIBELLES,
    POLAIRES,
    PYTHON,
    ModeleAero,
    charger_modele,
    declarer_tables,
    metadonnees,
)

from cfd_validation import valider_interpolation_tables  # noqa: E402


def cm_en_palier(modele: ModeleAero):  # type: ignore[no-untyped-def]
    """``--defaut`` : un évaluateur dont la sonde de CM est lue alpha arrondi au nœud le plus proche.

    Simule, côté Python, un code qui ne fait pas d'interpolation en alpha sur
    CM (un « plus proche nœud ») : les nœuds restent justes — le test de
    lecture ne verrait rien —, l'intérieur des mailles devient un escalier.
    """
    talpha = modele.lire("aertab.talpha")

    def evaluer(df: pd.DataFrame) -> pd.DataFrame:
        sortie = modele.calcul_aero_elementaire(df)
        proche = talpha[np.abs(df["alpha"].to_numpy()[:, None] - talpha[None, :]).argmin(axis=1)]
        dans = (df["alpha"] >= talpha[0]) & (df["alpha"] <= talpha[-1])
        arrondi = modele.calcul_aero_elementaire(df.assign(alpha=np.where(dans, proche, df["alpha"])))
        sortie["valid_tab_cm"] = arrondi["valid_tab_cm"].to_numpy()
        return sortie

    return evaluer


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--fractions", type=float, nargs="+", default=[0.25, 0.5, 0.75],
                   help="positions dans chaque maille, strictement entre 0 et 1 (défaut 0.25 0.5 0.75)")
    p.add_argument("--defaut", action="store_true",
                   help="CM relu en palier (alpha au nœud le plus proche, simulé) : verdict NON CONFORME")
    p.add_argument("--jobs", type=int, default=1, help="processus pour tracer les polaires (-1 : tous)")
    p.add_argument("--sans-superposition", action="store_true",
                   help="ne pas tracer les figures superposées (fold « overlay » de batch_plot)")
    p.add_argument("--module", default="aerolib", help="module f2py à tester (défaut aerolib)")
    p.add_argument("--dossier", type=Path, default=PYTHON, help="où chercher le module")
    p.add_argument("--sortie", type=Path, default=None, help="dossier des pièces (défaut SORTIE/<scénario>)")
    p.add_argument("--sans-figures", action="store_true", help="ne pas tracer les polaires")
    args = p.parse_args()

    modele = charger_modele(args.module, args.dossier)
    if modele is None:
        return 1
    scenario = "defaut" if args.defaut else "nominal"
    res = valider_interpolation_tables(
        declarer_tables(modele),
        evaluer=cm_en_palier(modele) if args.defaut else modele.calcul_aero_elementaire,
        defauts=DEFAUTS,
        fractions=args.fractions,
        polaires=POLAIRES,
        libelles=LIBELLES,
        superposer=not args.sans_superposition,
        n_jobs=args.jobs,
        identifiant="VAL-TAB-03",
        metadonnees=metadonnees(modele, scenario),
        sortie=args.sortie or ICI / "SORTIE" / scenario,
        figures=not args.sans_figures,
        nettoyer=True,
    )
    return 0 if res.conforme else 2


if __name__ == "__main__":
    sys.exit(main())
