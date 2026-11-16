"""La précision des plans, chiffrée sur un modèle d'essai (``cfd-doe remplir --precision``).

Le niveau de précision d'un plan (:data:`cfd_doe.engine.remplissage.PRECISIONS`)
dit ce qu'on peut attendre de sa table : exacte, interpolée, exacte si les
effets s'ajoutent, ou approchée. Ce module le **chiffre** : chaque plan est
« calculé » sur un modèle aéro d'essai, sa table reconstruite
(:mod:`cfd_doe.engine.reconstruction`) et comparée au modèle sur toute la grille.

Le modèle d'essai est plausible, pas vrai : portance tourbillonnaire en α|α|,
gouvernes qui saturent, couplages δm × δn², β² × δn, paramètres × gouverne,
bosse transsonique. Il est **moyenné sur le groupe de symétrie de l'étude**,
donc exactement symétrique quelle que soit la géométrie. Les chiffres
comparent les méthodes entre elles sur un même banc ; ils ne promettent pas
l'erreur qu'on aura sur l'engin réel — celle-là se mesure aux points
« controle » et « test » (voir :attr:`Tables.ecarts`).

Repère cartésien seulement, comme la reconstruction.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from cfd_doe.engine.reconstruction import Mesures, Tables, grille_carree, reconstruire
from cfd_doe.engine.remplissage import Contexte, PlanDOE, PointDOE, Resultat

__all__ = [
    "MesurePrecision",
    "basse_fidelite",
    "calculer",
    "mesurer",
    "mesurer_plan",
    "modele_brut",
    "verite",
    "verite_sur_grille",
]


# ---------------------------------------------------------------------------
# Le modèle d'essai
# ---------------------------------------------------------------------------


def modele_brut(valeurs: Mapping[str, np.ndarray], contexte: Contexte) -> dict[str, np.ndarray]:
    """Six coefficients plausibles, en repère engin, avant symétrisation.

    Les paramètres de l'étude, quels qu'ils soient, entrent par leur valeur
    réduite dans [0, 1] (moyenne si plusieurs).
    """
    n = len(next(iter(valeurs.values())))

    def v(nom: str) -> np.ndarray:
        return np.asarray(valeurs.get(nom, np.zeros(n)), dtype=float)

    a, b, dm, dn, dl = v("alpha"), v("beta"), v("DM"), v("DN"), v("DL")
    mach = v("mach") if "mach" in valeurs else np.full(n, 0.8)
    k = 1.0 + 0.4 * np.exp(-(((mach - 1.0) / 0.15) ** 2))
    p = np.zeros(n)
    for param in contexte.parametres:
        plage = param.plage
        p += (v(param.nom) - plage.bas) / (plage.largeur or 1.0)
    p /= max(1, len(contexte.parametres))
    gm, gn = np.tanh(dm / 20.0), np.tanh(dn / 20.0)
    return {
        "CA": 0.30 * k + 1e-3 * (a**2 + b**2) + 4e-4 * (dm**2 + dn**2) + 2e-4 * dl**2 - 0.08 * p,
        "CN": k * (0.10 * a + 0.0025 * a * np.abs(a))
        + 0.40 * gm
        + 8e-4 * a * dm
        + 0.10 * p * a / 10
        + 2.5e-5 * dm * dn**2
        + 0.004,  # dissymétrie : ne survit que sans miroir H
        "CY": -0.09 * b + 0.30 * gn + 3e-4 * b**2 * dn,
        "Cl": 0.02 * dl + 6e-4 * a * b - 0.01 * p * dl / 10,
        "Cm": -0.05 * k * a - 0.60 * gm * (1 - 0.25 * p) - 4e-5 * dm * dn**2,
        "Cn": 0.04 * b - 0.60 * gn - 6e-4 * b**2 * dn,
    }


def verite(contexte: Contexte, valeurs: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Le modèle moyenné sur le groupe de l'étude : C(x) = (1/|G|) Σ_g s_g · C_brut(g·x).

    Mêmes signes que la réduction (clé ``symetries`` de l'export) ; seuls les
    coefficients de la trajectoire.
    """
    noms = list(contexte.reduction.etude.trajectoire.coefficients)
    brut = modele_brut(valeurs, contexte)
    total = {c: brut[c].copy() for c in noms}
    for s in contexte.symetries:
        image = {k: (-x if k in s["variables"] else x) for k, x in valeurs.items()}
        brut = modele_brut(image, contexte)
        for c in noms:
            total[c] += (-1.0 if c in s["coefficients"] else 1.0) * brut[c]
    return {c: x / (1 + len(contexte.symetries)) for c, x in total.items()}


def basse_fidelite(y: np.ndarray) -> np.ndarray:
    """Un solveur moins fidèle : biais lisse, fonction impaire de C (symétries conservées)."""
    return np.asarray(0.9 * y + 0.03 * y**3)


def calculer(points: Sequence[PointDOE], contexte: Contexte) -> Mesures:
    """« Lance la CFD » d'essai sur ces points (basse fidélité pour les points ``BF``)."""
    valeurs = {c: np.array([p.valeurs[c] for p in points]) for c in contexte.colonnes}
    y = verite(contexte, valeurs)
    bf = np.array([p.fidelite == "BF" for p in points])
    if bf.any():
        y = {c: np.where(bf, basse_fidelite(x), x) for c, x in y.items()}
    return Mesures(tuple(points), y)


def verite_sur_grille(contexte: Contexte) -> dict[str, np.ndarray]:
    """Le modèle d'essai aux nœuds de la grille de référence complète."""
    grille = grille_carree(contexte)
    points = grille.points()
    colonnes = list(grille.colonnes)
    valeurs = {
        col: points[:, colonnes.index(col)]
        if col in colonnes
        else np.full(len(points), contexte.reference[col])
        for col in contexte.colonnes
    }
    return verite(contexte, valeurs)


# ---------------------------------------------------------------------------
# Mesure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MesurePrecision:
    """L'erreur de la table d'un plan sur le modèle d'essai, en % de l'étendue du coefficient."""

    plan: PlanDOE
    #: Coefficient → erreur RMS sur toute la grille (nœuds exclus ignorés).
    rms: dict[str, float]
    #: Coefficient → erreur maximale.
    maxi: dict[str, float]
    #: Rôle (« controle », « test ») → écart RMS du pire coefficient à ces points.
    verification: dict[str, float] = field(default_factory=dict)
    tables: Tables | None = None

    @property
    def pire(self) -> str:
        """Le coefficient le moins bien reconstruit."""
        return max(self.rms, key=lambda c: self.rms[c])

    @property
    def erreur(self) -> float:
        """Erreur RMS du pire coefficient (%)."""
        return self.rms[self.pire]

    @property
    def erreur_max(self) -> float:
        """Erreur maximale, tous coefficients (%)."""
        return max(self.maxi.values())

    @property
    def mesuree(self) -> float | None:
        """L'écart que la démarche du plan mesurerait en vrai (contrôle, sinon test)."""
        return self.verification.get("controle", self.verification.get("test"))


def _etendue(x: np.ndarray) -> float:
    finis = x[np.isfinite(x)]
    e = float(finis.max() - finis.min()) if len(finis) else 0.0
    return e if e > 1e-12 else 1.0


def evaluer(
    plan: PlanDOE, tables: Tables, vraie: Mapping[str, np.ndarray], *, garder: bool = False
) -> MesurePrecision:
    """Compare les tables d'un plan à la vérité sur la grille."""
    rms, maxi = {}, {}
    for c, t in tables.valeurs.items():
        e = t - vraie[c]
        echelle = _etendue(vraie[c])
        finis = np.isfinite(e)
        rms[c] = 100 * float(np.sqrt(np.mean(e[finis] ** 2))) / echelle if finis.any() else 0.0
        maxi[c] = 100 * float(np.abs(e[finis]).max()) / echelle if finis.any() else 0.0
    verification = {
        role: max(
            100 * float(np.sqrt(np.mean(e**2))) / _etendue(vraie[c]) for c, e in ecarts.items()
        )
        for role, ecarts in tables.ecarts.items()
    }
    return MesurePrecision(plan, rms, maxi, verification, tables if garder else None)


def mesurer_plan(
    plan: PlanDOE,
    contexte: Contexte,
    vraie: Mapping[str, np.ndarray] | None = None,
    *,
    rapide: bool = True,
    garder: bool = False,
) -> MesurePrecision:
    """L'erreur de la table d'un plan sur le modèle d'essai.

    ``rapide`` : krigeage à portées communes aux coefficients (un ajustement
    par Mach au lieu d'un par coefficient). Plan adaptatif : le lot initial
    seul, comme le fichier DOE.
    """
    vraie = vraie if vraie is not None else verite_sur_grille(contexte)
    tables = reconstruire(plan, contexte, calculer(plan.points, contexte), portees_communes=rapide)
    return evaluer(plan, tables, vraie, garder=garder)


def mesurer(
    resultat: Resultat, *, rapide: bool = True, garder: bool = False
) -> dict[str, MesurePrecision]:
    """La précision de chaque plan du résultat, sur le modèle d'essai."""
    vraie = verite_sur_grille(resultat.contexte)
    return {
        plan.nom: mesurer_plan(plan, resultat.contexte, vraie, rapide=rapide, garder=garder)
        for plan in resultat.plans
    }
