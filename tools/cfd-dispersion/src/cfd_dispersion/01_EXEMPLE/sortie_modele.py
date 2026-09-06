#!/usr/bin/env python3
"""Un exemple **écrit en dur** de ce qu'un modèle rend : le tableau de sortie.

Ce fichier ne contient pas de modèle. Il contient la *forme* de sa sortie —
celle que le paquet lit — écrite noir sur blanc pour qu'on puisse la comparer à
la sienne :

    4 points de vol × 100 tirages = 400 lignes

Le lot de tirages est tiré **une fois** et rejoué à l'identique sur chaque point
de vol : c'est ce que fait un modèle appelé en croisé, et c'est pour cela que le
tirage numéro 7 est le même partout. Il porte donc le même numéro partout, ce
qui est exactement ce qui permet de dédoublonner ensuite.

Les colonnes, par famille
-------------------------
======================  =========================================================
famille                 colonnes
======================  =========================================================
point de vol            ``Mach``, ``Altitude_m``
métadonnées             ``cas``, ``maillage``, ``solveur``, ``version_modele``,
                        ``date``, ``convergence``
coefficients dispersés  ``CN``, ``CA``, ``Cm_alpha`` — ce que le modèle a calculé
valeurs nominales       ``CN_nominal``, ``CA_nominal``, ``Cm_alpha_nominal``
les deux dictionnaires  ``DICT_LAW_DISPERSION``, ``DICT_TIRAGE``
numéro de tirage        ``tirage``
======================  =========================================================

Un mot sur les deux familles de coefficients, parce que c'est le point où deux
modèles ne se ressemblent pas :

* ``<coeff>`` porte ici le coefficient **dispersé**, celui que le modèle a
  produit avec le tirage de la ligne — il change d'une ligne à l'autre ;
* ``<coeff>_nominal`` porte la valeur **non dispersée** du point de vol — elle
  est constante sur les cent lignes d'un point de vol.

Les figures cherchent la valeur nominale d'abord dans la colonne du **même nom**
que le coefficient, puis dans ``<coeff>_nominal``. Si votre modèle ne sort que
la première et qu'elle est constante par point de vol, c'est elle qui sert ;
s'il n'en sort aucune, les figures le disent au lieu d'inventer un nominal.

Les deux colonnes de dictionnaires sont écrites telles quelles — des dicts
Python. Après un aller-retour par CSV elles reviennent en chaînes, et le paquet
les relit dans les deux cas.

    python sortie_modele.py [--sortie SORTIE] [-n 100]

écrit ``SORTIE_MODELE.csv`` et affiche les premières lignes.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console

from cfd_dispersion import charger_lois, convention, tirer_lot

ICI = Path(__file__).resolve().parent

#: Les quatre points de vol de l'étude. Ce sont eux qu'on retrouve en
#: ``points_de_vol=`` dans les figures.
POINTS_DE_VOL: tuple[dict[str, float], ...] = (
    {"Mach": 0.70, "Altitude_m": 0.0},
    {"Mach": 0.70, "Altitude_m": 10_000.0},
    {"Mach": 0.85, "Altitude_m": 0.0},
    {"Mach": 0.85, "Altitude_m": 10_000.0},
)

#: La table de lois de l'étude — celle que le tableau de sortie recopie sur
#: chacune de ses lignes, pour qu'il se relise dans six mois sans elle.
DICT_LAW_DISPERSION: dict[str, dict[str, float]] = {
    "CN": {
        "Biais_Type": 5,  # Gaussienne ±3σ
        "Biais_M": 0.0,
        "Biais_ET": 0.02,  # DEMI-ÉTENDUE : σ = 0.01
        "FE_Type": 6,  # Gaussienne ±2σ
        "FE_M": 1.0,  # facteur neutre pour la convention `lineaire`
        "FE_ET": 0.08,
    },
    "CA": {
        "Biais_Type": 3,  # Uniforme
        "Biais_M": 0.0,
        "Biais_ET": 0.0015,
        "FE_Type": 4,  # Gaussienne, support non borné
        "FE_M": 1.0,
        "FE_ET": 0.06,
    },
    "Cm_alpha": {
        "Biais_Type": 5,
        "Biais_M": 0.0,
        "Biais_ET": 0.015,
        "FE_Type": 6,
        "FE_M": 1.0,
        "FE_ET": 0.10,
    },
}

#: Les coefficients **nominaux**, point de vol par point de vol. Écrits en dur :
#: c'est ce qu'une base aérodynamique fournirait.
COEFFICIENTS_NOMINAUX: dict[tuple[float, float], dict[str, float]] = {
    (0.70, 0.0): {"CN": 0.780, "CA": 0.0295, "Cm_alpha": -2.35},
    (0.70, 10_000.0): {"CN": 0.795, "CA": 0.0288, "Cm_alpha": -2.41},
    (0.85, 0.0): {"CN": 0.850, "CA": 0.0320, "Cm_alpha": -2.50},
    (0.85, 10_000.0): {"CN": 0.868, "CA": 0.0311, "Cm_alpha": -2.58},
}

#: Les métadonnées que le modèle traîne avec lui. Le paquet ne les lit pas ; il
#: ne les perd pas non plus.
METADONNEES: dict[tuple[float, float], dict[str, Any]] = {
    (0.70, 0.0): {"cas": "CROISIERE_BASSE", "convergence": 1.8e-7},
    (0.70, 10_000.0): {"cas": "CROISIERE_HAUTE", "convergence": 2.4e-7},
    (0.85, 0.0): {"cas": "TRANSSONIQUE_BASSE", "convergence": 9.1e-7},
    (0.85, 10_000.0): {"cas": "TRANSSONIQUE_HAUTE", "convergence": 1.2e-6},
}

#: Métadonnées communes à toutes les lignes.
METADONNEES_COMMUNES: dict[str, Any] = {
    "maillage": "M3_12M",
    "solveur": "OF_V13",
    "version_modele": "2.4.1",
    "date": "2026-09-05",
}

#: Le nombre de tirages, et la graine qui les rend reproductibles.
N_TIRAGES = 100
GRAINE = 42

#: La relation de reconstruction employée par ce modèle.
CONVENTION = "lineaire"


def sortie_modele(
    n_tirages: int = N_TIRAGES,
    *,
    graine: int = GRAINE,
    methode: str = "lhs",
    convention_: str = CONVENTION,
) -> pd.DataFrame:
    """Construit le tableau de sortie : une ligne par (point de vol × tirage).

    Le lot est tiré **une fois**, puis appliqué à chaque point de vol : c'est
    la forme d'un appel croisé, et c'est ce qui fait que le tirage *i* est le
    même aux quatre points de vol.

    Parameters
    ----------
    n_tirages:
        Nombre de tirages — donc de lignes par point de vol.
    graine:
        Graine du lot.
    methode:
        Plan d'échantillonnage du lot (``"mc"``, ``"lhs"`` ou ``"sobol"``).
    convention_:
        La relation de reconstruction appliquée aux coefficients nominaux.

    Returns
    -------
    pandas.DataFrame
        ``len(POINTS_DE_VOL) × n_tirages`` lignes.
    """
    lois = charger_lois(DICT_LAW_DISPERSION)
    relation = convention(convention_)

    # Un seul lot pour toute l'étude : le même tirage à tous les points de vol.
    lot = tirer_lot(lois, n_tirages, graine=graine, methode=methode, convention_=relation)

    lignes: list[dict[str, Any]] = []
    for point in POINTS_DE_VOL:
        cle = (point["Mach"], point["Altitude_m"])
        nominaux = COEFFICIENTS_NOMINAUX[cle]

        for tirage in lot:
            disperses = tirage.appliquer(nominaux)
            lignes.append(
                {
                    **point,
                    **METADONNEES_COMMUNES,
                    **METADONNEES[cle],
                    **{coeff: float(valeur) for coeff, valeur in disperses.items()},
                    **{f"{coeff}_nominal": valeur for coeff, valeur in nominaux.items()},
                    "DICT_LAW_DISPERSION": DICT_LAW_DISPERSION,
                    "DICT_TIRAGE": tirage.vers_dict(),
                    "tirage": tirage.numero,
                }
            )

    return pd.DataFrame(lignes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sortie", type=Path, default=ICI / "SORTIE")
    parser.add_argument("-n", type=int, default=N_TIRAGES)
    args = parser.parse_args()

    console = Console()
    args.sortie.mkdir(parents=True, exist_ok=True)

    df = sortie_modele(args.n)
    console.print(
        f"[bold]Sortie du modèle[/] : {len(df)} lignes "
        f"({len(POINTS_DE_VOL)} points de vol × {args.n} tirages)"
    )
    console.print(f"colonnes : {list(df.columns)}\n")

    apercu = df.loc[:, ["Mach", "Altitude_m", "tirage", "CN", "CN_nominal", "cas"]]
    console.print(apercu.head(4).to_string(index=False))
    premiere = dict(df.iloc[0])
    console.print(
        "\nles deux dictionnaires, sur la première ligne :\n"
        f"  DICT_TIRAGE          {premiere['DICT_TIRAGE']}\n"
        f"  DICT_LAW_DISPERSION  {{'CN': {DICT_LAW_DISPERSION['CN']}, …}}"
    )

    chemin = args.sortie / "SORTIE_MODELE.csv"
    df.to_csv(chemin, index=False)
    console.print(f"\n[green]écrit :[/] {chemin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
