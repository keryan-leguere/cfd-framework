"""Intervalles réels à bornes ouvertes ou fermées.

Un sous-domaine de calcul est un produit d'intervalles. Les bornes ouvertes ne
sont pas un raffinement : sur un plan de symétrie (β = 0, par exemple), le
miroir divise par deux les braquages, alors qu'au voisinage du plan il ne
divise rien. Le sous-domaine « β > 0 » doit donc *exclure* β = 0, sans quoi les
points du plan sont comptés deux fois — une fois avec la réduction, une fois
sans.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["TOLERANCE", "Intervalle"]

#: Tolérance absolue des comparaisons (degrés). Les grilles CFD sont en
#: dixièmes de degré au mieux : 1e-9 ne confond rien d'utile.
TOLERANCE = 1e-9


@dataclass(frozen=True)
class Intervalle:
    """Intervalle ``[bas, haut]``, chaque borne pouvant être exclue."""

    bas: float
    haut: float
    bas_inclus: bool = True
    haut_inclus: bool = True

    def __post_init__(self) -> None:
        if self.bas > self.haut + TOLERANCE:
            raise ValueError(f"intervalle vide : bas={self.bas} > haut={self.haut}")
        if self.est_point and not (self.bas_inclus and self.haut_inclus):
            raise ValueError("un intervalle réduit à un point doit être fermé")

    # --- Constructeurs ------------------------------------------------------

    @classmethod
    def point(cls, valeur: float) -> Intervalle:
        """L'intervalle ``{valeur}``."""
        return cls(valeur, valeur)

    @classmethod
    def ferme(cls, bas: float, haut: float) -> Intervalle:
        """``[bas, haut]``, réduit à un point si les bornes coïncident."""
        return cls(bas, haut)

    # --- Propriétés ---------------------------------------------------------

    @property
    def est_point(self) -> bool:
        """Vrai si l'intervalle est réduit à une valeur."""
        return abs(self.haut - self.bas) <= TOLERANCE

    @property
    def est_nul(self) -> bool:
        """Vrai si l'intervalle est exactement ``{0}``."""
        return self.est_point and abs(self.bas) <= TOLERANCE

    @property
    def largeur(self) -> float:
        """``haut - bas``."""
        return self.haut - self.bas

    @property
    def amplitude(self) -> float:
        """``max(|bas|, |haut|)`` : demi-largeur de l'enveloppe symétrique."""
        return max(abs(self.bas), abs(self.haut))

    @property
    def est_symetrique(self) -> bool:
        """Vrai si l'intervalle est fermé et symétrique par rapport à 0."""
        return abs(self.bas + self.haut) <= TOLERANCE and self.bas_inclus and self.haut_inclus

    # --- Opérations ---------------------------------------------------------

    def contient(self, valeur: float, tol: float = TOLERANCE) -> bool:
        """Appartenance, bornes ouvertes respectées à ``tol`` près."""
        if self.bas_inclus:
            if valeur < self.bas - tol:
                return False
        elif valeur <= self.bas + tol:
            return False
        if self.haut_inclus:
            return valeur <= self.haut + tol
        return valeur < self.haut - tol

    def symetrise(self) -> Intervalle:
        """L'enveloppe symétrique ``[-M, M]``, ``M = max(|bas|, |haut|)``."""
        m = self.amplitude
        return Intervalle(-m, m)

    def partie_positive_stricte(self) -> Intervalle:
        """``]0, haut]`` pour un intervalle symétrique non réduit à 0."""
        if self.haut <= TOLERANCE:
            raise ValueError("pas de partie strictement positive")
        return Intervalle(0.0, self.haut, bas_inclus=False, haut_inclus=self.haut_inclus)

    def partie_positive(self) -> Intervalle:
        """``[0, haut]``."""
        if self.haut < -TOLERANCE:
            raise ValueError("pas de partie positive")
        return Intervalle(0.0, max(self.haut, 0.0), haut_inclus=self.haut_inclus)
