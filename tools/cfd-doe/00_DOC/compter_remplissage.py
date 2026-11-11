"""Décomptes de 00_DOC/02_REMPLISSAGE.md : nombre de calculs CFD par méthode de remplissage.

L'exemple du document : engin à double symétrie (plans vertical et horizontal),
trajectoire 6DOF, repère cartésien — les 8 sous-domaines de

    cfd-doe domaine --traj 6DOF --sym double_symetrie \\
        --alpha -20 20 --beta -5 5 --dl -10 10 --dm -20 20 --dn -20 20

auxquels on ajoute le Mach (8 valeurs) et un paramètre moteur p (3 niveaux).

Tout décompte « avec symétries » est un **nombre d'orbites** : deux points
images l'un de l'autre par une symétrie de l'engin ne comptent qu'une fois.
C'est exactement le nombre de points du plan qui tombent dans les
sous-domaines de cfd-doe (vérifié ci-dessous sur le factoriel complet).

    python 00_DOC/compter_remplissage.py
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from functools import lru_cache
from itertools import product

from cfd_doe.core.plans import box_behnken, composite_centre, grille_creuse
from cfd_doe.data.etude import etude_depuis_dict
from cfd_doe.data.geometries import MIROIR_H, MIROIR_V, ROTATION_180
from cfd_doe.engine.reduction import SousDomaine, reduire

VARIABLES = ("alpha", "beta", "DM", "DN", "DL")

#: Grille de référence du document (degrés).
ALPHA = [-20.0, -15.0, -10.0, -5.0, 0.0, 5.0, 10.0, 15.0, 20.0]
BETA = [-5.0, -2.5, 0.0, 2.5, 5.0]
DM = DN = [-20.0, -10.0, 0.0, 10.0, 20.0]
DL = [-10.0, 0.0, 10.0]
REFERENCE = {"alpha": ALPHA, "beta": BETA, "DM": DM, "DN": DN, "DL": DL}

N_MACH = 8  # 0,6 · 0,8 · 0,95 · 1,05 · 1,2 · 1,5 · 2 · 3
N_MOTEUR = 3  # éteint · régime intermédiaire · plein régime

Point = tuple[float, ...]


def orbites(points: Iterable[Point]) -> int:
    """Nombre de points à calculer : un représentant par orbite du groupe D2."""
    groupe = [frozenset(), MIROIR_V.inverse, MIROIR_H.inverse, ROTATION_180.inverse]
    vus = set()
    for p in points:
        images = [
            tuple(round(-x if v in g else x, 9) + 0.0 for v, x in zip(VARIABLES, p)) for g in groupe
        ]
        vus.add(min(images))
    return len(vus)


def grille(**niveaux: Sequence[float]) -> list[Point]:
    """Produit des niveaux ; une variable absente vaut 0."""
    axes = [niveaux.get(v, [0.0]) for v in VARIABLES]
    return list(product(*axes))


def sans_zero(valeurs: Sequence[float]) -> list[float]:
    return [x for x in valeurs if x != 0.0]


@lru_cache(maxsize=1)
def sous_domaines() -> tuple[SousDomaine, ...]:
    """Les 8 sous-domaines de l'exemple, tels que cfd-doe les produit."""
    etude = etude_depuis_dict(
        {
            "trajectoire": "6DOF",
            "geometrie": "double_symetrie",
            "variables": {v: [min(x), max(x)] for v, x in REFERENCE.items()},
        }
    )
    return reduire(etude).sous_domaines


def est_calcule(point: Point) -> bool:
    """Le point est-il dans un sous-domaine (calculé), ou déduit par symétrie ?"""
    return any(sd.contient(dict(zip(VARIABLES, point))) for sd in sous_domaines())


def dans_les_sous_domaines(points: Iterable[Point]) -> int:
    """Le même décompte que ``orbites``, par appartenance aux sous-domaines de cfd-doe."""
    return sum(est_calcule(p) for p in points)


# ---------------------------------------------------------------------------
# Plans classiques et grilles creuses, sur le pavé [-1, 1]^k
# ---------------------------------------------------------------------------


def orbites_avec_extras(points: Iterable[Point]) -> int:
    """Orbites quand les points portent des facteurs en plus des cinq angles."""
    par_extra: dict[Point, list[Point]] = {}
    for p in points:
        par_extra.setdefault(p[5:], []).append(p[:5])
    return sum(orbites(groupe) for groupe in par_extra.values())


# ---------------------------------------------------------------------------
# Décomptes
# ---------------------------------------------------------------------------

#: Niveaux du factoriel « réduit » (§3.2) : 3 niveaux partout sauf en α.
REDUIT = {
    "alpha": ALPHA,
    "beta": [-5.0, 0.0, 5.0],
    "DM": [-20.0, 0.0, 20.0],
    "DN": [-20.0, 0.0, 20.0],
    "DL": DL,
}


def tables_ordre_1() -> dict[str, int]:
    """Décomposition d'ordre 1 : points par Mach de chaque table (§4.2)."""
    base = orbites(grille(alpha=ALPHA, beta=BETA))
    return {
        "base (α, β)": base,
        "Δδm (α, δm)": orbites(grille(alpha=ALPHA, DM=sans_zero(DM))),
        "Δδn (α, δn)": orbites(grille(alpha=ALPHA, DN=sans_zero(DN))),
        "Δδl (α, δl)": orbites(grille(alpha=ALPHA, DL=sans_zero(DL))),
        "Δmoteur (α, β, p)": base * (N_MOTEUR - 1),
    }


def tables_ordre_2() -> dict[str, int]:
    """Décomposition d'ordre 2 : incréments en (α, β) et couplages choisis (§4.3)."""
    base = orbites(grille(alpha=ALPHA, beta=BETA))
    return {
        "base (α, β)": base,
        "Δδm (α, β, δm)": orbites(grille(alpha=ALPHA, beta=BETA, DM=sans_zero(DM))),
        "Δδn (α, β, δn)": orbites(grille(alpha=ALPHA, beta=BETA, DN=sans_zero(DN))),
        "Δδl (α, β, δl)": orbites(grille(alpha=ALPHA, beta=BETA, DL=sans_zero(DL))),
        "Δδm×δn (α, δm, δn)": orbites(grille(alpha=ALPHA, DM=sans_zero(DM), DN=sans_zero(DN))),
        "Δmoteur (α, β, p)": base * (N_MOTEUR - 1),
        "Δmoteur×δm (α, δm, p)": orbites(grille(alpha=ALPHA, DM=sans_zero(DM))) * (N_MOTEUR - 1),
    }


def decomptes() -> dict[str, tuple[int, int]]:
    """Méthode → (calculs par Mach, total sur les 8 Mach), symétries exploitées.

    Les deux dernières entrées sont des **ordres de grandeur** (règle 30·d
    points vus par le métamodèle, divisés par 4 ; adaptatif : milieu de la
    fourchette du §8.1), non des décomptes.
    """
    plein = grille(**REFERENCE)
    n_plein = orbites(plein)
    assert n_plein == dans_les_sous_domaines(plein), "orbites ≠ sous-domaines"
    n_reduit = orbites(grille(**REDUIT))
    etoile = [
        *grille(alpha=ALPHA),
        *grille(beta=BETA),
        *grille(DM=DM),
        *grille(DN=DN),
        *grille(DL=DL),
    ]
    par_mach = {
        "factoriel complet, sans symétrie": len(plein) * N_MOTEUR,
        "factoriel complet": n_plein * N_MOTEUR,
        "factoriel à niveaux inégaux": n_reduit * N_MOTEUR,
        "décomposition ordre 2": sum(tables_ordre_2().values()),
        "grille creuse niveau 3": orbites_avec_extras(grille_creuse(6, 3)),
        "décomposition ordre 1": sum(tables_ordre_1().values()),
        "remplissage d'espace 30·d": remplissage(1),
        "adaptatif": 35,
        "grille creuse niveau 2": orbites_avec_extras(grille_creuse(6, 2)),
        "composite centré": orbites_avec_extras(composite_centre(6, fraction=1)),
        "Box-Behnken": orbites_avec_extras(box_behnken(6)),
        "étoile": orbites(etoile) + N_MOTEUR - 1,
    }
    return {methode: (n, n * N_MACH) for methode, n in par_mach.items()}


#: Les méthodes de ``decomptes`` dont le chiffre est un ordre de grandeur.
ESTIMEES = ("remplissage d'espace 30·d", "adaptatif")


def remplissage(n: int) -> int:
    """Règle 30·d points vus par le métamodèle, d = 5 + n, divisés par les 4 symétries."""
    return -(-30 * (5 + n) // 4)


def par_nombre_de_parametres(n_max: int = 3) -> dict[str, list[int]]:
    """Totaux sur les 8 Mach pour n = 0…n_max paramètres à 3 niveaux (§10)."""
    n_plein = orbites(grille(**REFERENCE))
    ordre_1 = tables_ordre_1()
    base = ordre_1["base (α, β)"]
    increments = sum(v for k, v in ordre_1.items() if "moteur" not in k)
    plage = range(n_max + 1)
    return {
        "factoriel complet": [n_plein * N_MOTEUR**n * N_MACH for n in plage],
        "décomposition ordre 1": [(increments + n * base * (N_MOTEUR - 1)) * N_MACH for n in plage],
        "grille creuse niveau 2": [
            orbites_avec_extras(grille_creuse(5 + n, 2)) * N_MACH for n in plage
        ],
        "remplissage d'espace 30·d": [remplissage(n) * N_MACH for n in plage],
    }


def main() -> None:
    print(f"{'méthode':36s} {'par Mach':>9s} {'total':>8s}")
    for methode, (par_mach, total) in decomptes().items():
        marque = " *" if methode in ESTIMEES else ""
        print(f"{methode:36s} {par_mach:9d} {total:8d}{marque}")
    print("  * ordre de grandeur")
    print("\ndécomposition ordre 1 :", tables_ordre_1())
    print("décomposition ordre 2 :", tables_ordre_2())
    print(
        "\npoints bruts — composite centré :",
        len(composite_centre(6, 1)),
        "· Box-Behnken :",
        len(box_behnken(6)),
    )
    print(
        "grilles creuses brutes, d = 5, 6, 7, niveaux 1 à 3 :",
        [[len(grille_creuse(d, n)) for n in (1, 2, 3)] for d in (5, 6, 7)],
    )
    print("\ntotaux pour n = 0, 1, 2, 3 paramètres à 3 niveaux :")
    for methode, totaux in par_nombre_de_parametres().items():
        print(f"  {methode:28s}", totaux)


if __name__ == "__main__":
    main()
