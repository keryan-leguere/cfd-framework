#!/usr/bin/env python3
"""Un modèle qui **ne rend pas** les coefficients qu'il disperse.

``sortie_modele.py`` est le cas facile : la table de lois disperse ``CN``, et
le modèle rend une colonne ``CN``. Le cas réel est plus souvent celui-ci — les
lois portent sur les grandeurs du **repère de soufflerie**, les sorties sur
celles du **repère avion**, et entre les deux il y a une relation ::

    lois       CZ                    CX1, CX2
    sorties    CN = -CZ              CA = CX1 + CX2

Deux décalages, et deux raisons différentes :

``CN = -CZ``
    un simple changement de signe — le repère est retourné. Un seul terme, pas
    de constante : la loi de ``CN`` se déduit de celle de ``CZ`` **sans rien
    connaître des valeurs nominales**.
``CA = CX1 + CX2``
    une somme de contributions — frottement plus pression. Le facteur d'échelle
    de ``CA`` est alors une **moyenne pondérée** de ceux de ``CX1`` et ``CX2``,
    au prorata de ce que chacun pèse : sa loi dépend des nominaux, donc du
    point de vol.

C'est exactement ce que ``relations=`` sait faire des deux
(:mod:`cfd_dispersion.core.relation`), et ce que ``10_relations.py`` montre.

Les colonnes
------------
======================  =========================================================
famille                 colonnes
======================  =========================================================
point de vol            ``Mach``, ``Altitude_m``
sorties **dérivées**    ``CN``, ``CA`` — ce que le modèle publie
sorties intermédiaires  ``CZ``, ``CX1``, ``CX2`` — publiées ici, pour que la
                        référence porte les nominaux des sources
coefficient direct      ``Cm_alpha`` — dispersé et rendu, sans relation
sortie non dispersée    ``CY`` — rendue, mais ni loi ni relation ne la décrit
les deux dictionnaires  ``DICT_LAW_DISPERSION``, ``DICT_TIRAGE``
numéro de tirage        ``tirage``
======================  =========================================================

Pourquoi publier ``CX1`` et ``CX2``
-----------------------------------
Parce que les poids de la dérivation sont des **parts** : sans ``CX1`` et
``CX2`` nominaux, rien ne dit que ``CX1`` pèse 70 % de ``CA`` plutôt que 30 %,
et la loi dérivée de ``CA`` n'existe pas. Ils n'ont besoin d'être là que dans
le tableau de **référence** — celui du tirage neutre — mais tant qu'à faire, ce
modèle-ci les publie partout.

Un modèle qui ne les publierait pas garderait la voie courte : passer les
nominaux à la main, ``nominaux={"CX1": 0.021, "CX2": 0.0086}``, quand ils ne
dépendent pas du point de vol.

    python sortie_modele_relations.py [--sortie SORTIE] [-n 200]
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console

from cfd_dispersion import charger_lois, convention, tirage_neutre, tirer_lot

ICI = Path(__file__).resolve().parent

#: Les trois points de vol de l'étude.
POINTS_DE_VOL: tuple[dict[str, float], ...] = (
    {"Mach": 0.70, "Altitude_m": 0.0},
    {"Mach": 0.85, "Altitude_m": 10_000.0},
    {"Mach": 0.92, "Altitude_m": 10_000.0},
)

#: La table de lois : elle parle de ce que le modèle **consomme**.
#:
#: ``CZ``, ``CX1`` et ``CX2`` ne sont pas des sorties : ce sont les grandeurs
#: sur lesquelles porte l'incertitude. ``Cm_alpha``, lui, est dispersé et rendu
#: directement — il est là pour qu'on voie côte à côte un coefficient qui a ses
#: lois et deux qui les tiennent d'une relation.
DICT_LAW_DISPERSION: dict[str, dict[str, float]] = {
    "CZ": {
        "Biais_Type": 5,  # Gaussienne ±3σ
        "Biais_M": 0.0,
        "Biais_ET": 0.020,  # DEMI-ÉTENDUE : σ = 0.010
        "FE_Type": 6,  # Gaussienne ±2σ
        "FE_M": 1.0,  # facteur neutre de la convention `lineaire`
        "FE_ET": 0.080,
    },
    "CX1": {
        "Biais_Type": 3,  # Uniforme — le frottement, recalé par abaque
        "Biais_M": 0.0,
        "Biais_ET": 0.0008,
        "FE_Type": 6,
        "FE_M": 1.0,
        "FE_ET": 0.100,
    },
    "CX2": {
        "Biais_Type": 5,  # Gaussienne ±3σ — la pression, tirée du calcul
        "Biais_M": 0.0,
        "Biais_ET": 0.0004,
        "FE_Type": 5,
        "FE_M": 1.0,
        "FE_ET": 0.060,
    },
    "Cm_alpha": {
        "Biais_Type": 5,
        "Biais_M": 0.0,
        "Biais_ET": 0.015,
        "FE_Type": 6,
        "FE_M": 1.0,
        "FE_ET": 0.100,
    },
}

#: Les relations qui mènent des grandeurs dispersées aux sorties publiées.
#: C'est ce dictionnaire qu'on passe en ``relations=`` — tel quel.
RELATIONS: dict[str, str] = {
    "CN": "-CZ",
    "CA": "CX1 + CX2",
}

#: Une sortie que le modèle calcule sans la disperser : ni loi, ni relation.
#: Elle n'est donc tracée que si on la demande — c'est le cas d'usage de
#: ``coefficients_en_plus=``.
CY_NOMINAL: dict[tuple[float, float], float] = {
    (0.70, 0.0): 0.0041,
    (0.85, 10_000.0): 0.0047,
    (0.92, 10_000.0): 0.0052,
}

#: Les valeurs **nominales** des grandeurs dispersées, point de vol par point
#: de vol. Écrites en dur : c'est ce qu'une base aérodynamique fournirait.
#:
#: La part de ``CX1`` dans ``CA`` change d'un point de vol à l'autre — 72 %,
#: 71 %, puis 61 % en transsonique, où la traînée d'onde gonfle ``CX2``. C'est
#: précisément ce que les lois dérivées de ``CA`` suivront.
COEFFICIENTS_NOMINAUX: dict[tuple[float, float], dict[str, float]] = {
    (0.70, 0.0): {"CZ": -0.780, "CX1": 0.0212, "CX2": 0.0083, "Cm_alpha": -2.35},
    (0.85, 10_000.0): {"CZ": -0.868, "CX1": 0.0221, "CX2": 0.0090, "Cm_alpha": -2.58},
    (0.92, 10_000.0): {"CZ": -0.905, "CX1": 0.0228, "CX2": 0.0146, "Cm_alpha": -2.74},
}

#: Métadonnées communes à toutes les lignes ; le paquet ne les lit pas.
METADONNEES: dict[str, Any] = {
    "maillage": "M4_18M",
    "solveur": "OF_V13",
    "version_modele": "3.0.0",
    "date": "2026-09-09",
}

#: Le nombre de tirages, et la graine qui les rend reproductibles.
N_TIRAGES = 200
GRAINE = 7

#: La relation de reconstruction employée par ce modèle.
CONVENTION = "lineaire"


def appliquer_relations(disperses: dict[str, float]) -> dict[str, float]:
    """Ce que **le modèle** fait des grandeurs dispersées : ses sorties.

    Trois lignes de physique, et c'est tout l'objet de l'exemple : le paquet ne
    les connaît pas, il ne connaît que le ``RELATIONS`` ci-dessus. Que les deux
    disent la même chose est ce que la figure de tirage vérifie, point de vol
    par point de vol et tirage par tirage.
    """
    return {
        "CN": -disperses["CZ"],
        "CA": disperses["CX1"] + disperses["CX2"],
        "Cm_alpha": disperses["Cm_alpha"],
    }


def _ligne(point: dict[str, float], tirage: Any, numero: int) -> dict[str, Any]:
    """Une ligne du tableau : le point de vol, les grandeurs, les dicts."""
    nominaux = COEFFICIENTS_NOMINAUX[(point["Mach"], point["Altitude_m"])]
    disperses = {nom: float(valeur) for nom, valeur in tirage.appliquer(nominaux).items()}
    return {
        **point,
        **METADONNEES,
        # Les intermédiaires, pour que la référence porte les nominaux des
        # sources — et pour qu'on puisse comparer à la main si on veut.
        **disperses,
        # Les sorties, calculées par le modèle et par lui seul.
        **appliquer_relations(disperses),
        # Une sortie que la dispersion ne touche pas.
        "CY": CY_NOMINAL[(point["Mach"], point["Altitude_m"])],
        "DICT_LAW_DISPERSION": DICT_LAW_DISPERSION,
        "DICT_TIRAGE": tirage.vers_dict(),
        "tirage": numero,
    }


def sortie_modele(
    n_tirages: int = N_TIRAGES,
    *,
    graine: int = GRAINE,
    methode: str = "lhs",
    convention_: str = CONVENTION,
) -> pd.DataFrame:
    """Le tableau de sortie : une ligne par (point de vol × tirage).

    Parameters
    ----------
    n_tirages:
        Nombre de tirages — donc de lignes par point de vol.
    graine:
        Graine du lot.
    methode:
        Plan d'échantillonnage (``"mc"``, ``"lhs"`` ou ``"sobol"``).
    convention_:
        La relation de reconstruction appliquée aux valeurs nominales.

    Returns
    -------
    pandas.DataFrame
        ``len(POINTS_DE_VOL) × n_tirages`` lignes.
    """
    lois = charger_lois(DICT_LAW_DISPERSION)
    relation = convention(convention_)
    lot = tirer_lot(lois, n_tirages, graine=graine, methode=methode, convention_=relation)

    return pd.DataFrame(
        [
            _ligne(dict(point), tirage, int(tirage.numero or 0))
            for point in POINTS_DE_VOL
            for tirage in lot
        ]
    )


def sortie_modele_reference(*, convention_: str = CONVENTION) -> pd.DataFrame:
    """Le **même modèle**, tourné une fois avec un tirage neutre.

    Une ligne par point de vol, la même structure, et des grandeurs non
    dispersées : c'est de là que viennent les valeurs nominales — celles des
    sorties **et celles des sources**, dont les lois dérivées ont besoin.
    """
    lois = charger_lois(DICT_LAW_DISPERSION)
    relation = convention(convention_)
    neutre = tirage_neutre(lois, convention_=relation)
    return pd.DataFrame([_ligne(dict(point), neutre, 0) for point in POINTS_DE_VOL])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sortie", type=Path, default=ICI / "SORTIE")
    parser.add_argument("-n", type=int, default=N_TIRAGES, help="tirages par point de vol")
    args = parser.parse_args()

    console = Console()
    args.sortie.mkdir(parents=True, exist_ok=True)

    df = sortie_modele(args.n)
    reference = sortie_modele_reference()

    console.print(f"[bold]Sortie du modèle[/] : {len(df)} lignes")
    console.print(f"  lois sur    : {list(DICT_LAW_DISPERSION)}")
    console.print(f"  colonnes    : {[c for c in df.columns if c not in METADONNEES]}")
    console.print(f"  relations   : {RELATIONS}")
    console.print("\n[bold]Référence[/] (tirage neutre) :")
    colonnes = ["Mach", "Altitude_m", "CZ", "CX1", "CX2", "CN", "CA"]
    console.print("  " + reference[colonnes].to_string(index=False).replace("\n", "\n  "))

    for nom, table in (("SORTIE_MODELE_RELATIONS", df), ("SORTIE_MODELE_RELATIONS_REF", reference)):
        chemin = args.sortie / f"{nom}.csv"
        table.to_csv(chemin, index=False)
        console.print(f"[green]écrit :[/] {chemin}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
