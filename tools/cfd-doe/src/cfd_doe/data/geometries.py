"""Géométries d'engin et leurs symétries (00_DOC/01_BASE_AERO.md §4.3).

Une géométrie est décrite par l'ordre de sa symétrie de rotation autour de x
(N : rotation de 360°/N) et par la présence de plans de symétrie contenant x
(alors aux angles φs = k·180°/N). Le corps de révolution est le cas limite
N = ∞.

Les **signes** des actions cartésiennes sont ici, et nulle part ailleurs. Ils
suivent les conventions du document (x avant, y droite, z bas ; δl, δm, δn
dans le sens des moments qu'ils créent). Si vos conventions de braquage
diffèrent, c'est ce fichier qu'il faut ajuster (§8, points ouverts).
"""

from __future__ import annotations

from dataclasses import dataclass

from cfd_doe.core.symetrie import ElementSigne

__all__ = [
    "COEFFICIENTS_HORS_PAV",
    "COEFFICIENT_DE",
    "GEOMETRIES",
    "MIROIR_H",
    "MIROIR_PLAN_POLAIRE",
    "MIROIR_V",
    "ROTATION_180",
    "Geometrie",
    "coefficients_retournes",
    "resoudre_geometrie",
]

#: Miroir dans le plan vertical (x, z) : y → −y.
MIROIR_V = ElementSigne("miroir V", frozenset({"beta", "DL", "DN"}))
#: Miroir dans le plan horizontal (x, y) : z → −z.
MIROIR_H = ElementSigne("miroir H", frozenset({"alpha", "DL", "DM"}))
#: Rotation de 180° autour de x : composée des deux miroirs.
ROTATION_180 = ElementSigne("rotation 180°", frozenset({"alpha", "beta", "DM", "DN"}))

#: Sur un plan de symétrie φa = φs, en repère mixte (§7.2) : δl et δnB changent
#: de signe, δmB est conservé.
MIROIR_PLAN_POLAIRE = ElementSigne("miroir du plan", frozenset({"DL", "DNB"}))

#: Le coefficient qui accompagne chaque variable cartésienne (repère engin) :
#: une symétrie le change de signe exactement quand elle change le signe de sa
#: variable. Miroir V (y → −y) : β, δl, δn et CY, Cl, Cn ; miroir H (z → −z) :
#: α, δl, δm et CN (= −CZ), Cl, Cm ; CA ne change jamais.
COEFFICIENT_DE: dict[str, str] = {"alpha": "CN", "beta": "CY", "DL": "Cl", "DM": "Cm", "DN": "Cn"}

#: En repère mixte, un miroir change le signe des coefficients hors du PAV
#: (§4.2) ; ceux du PAV (CA, CN, Cm) et toute rotation les laissent inchangés.
COEFFICIENTS_HORS_PAV: tuple[str, ...] = ("CY", "Cl", "Cn")


def coefficients_retournes(element: ElementSigne) -> tuple[str, ...]:
    """Les coefficients qu'une symétrie cartésienne change de signe (repère engin)."""
    return tuple(c for v, c in COEFFICIENT_DE.items() if v in element.inverse)


@dataclass(frozen=True)
class Geometrie:
    """Une géométrie d'engin.

    ``n_rotation = 0`` désigne la révolution (toute rotation est une symétrie).
    """

    nom: str
    description: str
    n_rotation: int
    miroirs: bool

    @property
    def revolution(self) -> bool:
        """Vrai pour un corps de révolution."""
        return self.n_rotation == 0

    @property
    def ordre_groupe(self) -> int | None:
        """Nombre de symétries (``None`` : infini, révolution)."""
        if self.revolution:
            return None
        return self.n_rotation * (2 if self.miroirs else 1)

    @property
    def nom_groupe(self) -> str:
        """Notation du groupe : C1, D1, D2, D4, D_N, O(2)."""
        if self.revolution:
            return "O(2)"
        return f"{'D' if self.miroirs else 'C'}{self.n_rotation}"

    @property
    def secteur_phia(self) -> float | None:
        """Largeur du domaine fondamental en φa (§4.3), ``None`` pour la révolution."""
        if self.revolution:
            return None
        return (180.0 if self.miroirs else 360.0) / self.n_rotation

    @property
    def plans_phia(self) -> tuple[float, ...]:
        """Angles φs des plans de symétrie, dans [0, 180[."""
        if self.revolution or not self.miroirs:
            return ()
        return tuple(k * 180.0 / self.n_rotation for k in range(self.n_rotation))

    def generateurs_cartesiens(self) -> tuple[ElementSigne, ...]:
        """Les symétries qui agissent par changement de signe sur (α, β, δ).

        Le miroir V existe dès qu'il y a des miroirs (φs = 0 en fait partie) ;
        le miroir H, si 90° est un plan (N pair, ou révolution) ; la rotation
        de 180°, si N est pair. Les autres (rotation de 90°, miroirs à 45°…)
        ne s'expriment pas en cartésien.
        """
        n_pair = self.revolution or self.n_rotation % 2 == 0
        gens: list[ElementSigne] = []
        if self.miroirs:
            gens.append(MIROIR_V)
            if n_pair:
                gens.append(MIROIR_H)
        if n_pair:
            gens.append(ROTATION_180)
        return tuple(gens)

    def symetries_non_cartesiennes(self) -> tuple[str, ...]:
        """Les symétries perdues si l'on reste en (α, β)."""
        if self.revolution:
            return ("rotations quelconques autour de x",)
        perdues: list[str] = []
        n = self.n_rotation
        if n >= 3:
            perdues.append(f"rotation de {360 / n:g}°")
            if self.miroirs:
                autres = [f"{phis:g}°" for phis in self.plans_phia if phis not in (0.0, 90.0)]
                if autres:
                    perdues.append(f"miroirs à φs = {', '.join(autres)}")
        return tuple(perdues)


GEOMETRIES: dict[str, Geometrie] = {
    g.nom: g
    for g in (
        Geometrie("quelconque", "aucune symétrie", 1, False),
        Geometrie("plan_vertical", "un plan de symétrie vertical", 1, True),
        Geometrie("double_symetrie", "plans vertical et horizontal", 2, True),
        Geometrie("cruciforme", "4 ailettes identiques", 4, True),
        Geometrie("revolution", "corps de révolution, sans ailettes", 0, True),
    )
}


def resoudre_geometrie(nom: str, n_ailettes: int | None = None) -> Geometrie:
    """Retrouve une géométrie ; ``n_ailettes`` pour le type ``n_ailettes``."""
    cle = nom.strip().lower()
    if cle == "n_ailettes":
        if n_ailettes is None or n_ailettes < 1:
            raise ValueError("géométrie n_ailettes : donner « n_ailettes » (entier ≥ 1)")
        return Geometrie("n_ailettes", f"{n_ailettes} ailettes identiques", int(n_ailettes), True)
    if n_ailettes is not None:
        raise ValueError(f"« n_ailettes » ne s'applique qu'à la géométrie n_ailettes, pas à {nom}")
    try:
        return GEOMETRIES[cle]
    except KeyError:
        admis = ", ".join([*GEOMETRIES, "n_ailettes"])
        raise ValueError(f"géométrie inconnue : {nom!r} ; admises : {admis}") from None
