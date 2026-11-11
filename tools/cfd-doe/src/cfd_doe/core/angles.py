"""Passage (α, β) ↔ (αt, φa) et repère mixte (00_DOC/01_BASE_AERO.md §2, §3, §7.1).

Tout est en **degrés**. Conventions : x avant, y droite, z bas ; α = atan(w/u),
β = asin(v/V) ; αt angle entre x et V, φa = atan2(v, w) ramené dans [0, 360[.
"""

from __future__ import annotations

import math

from cfd_doe.core.intervalle import TOLERANCE, Intervalle

__all__ = [
    "Arc",
    "arc_phia_rectangle",
    "braquages_engin",
    "braquages_mixtes",
    "incidence_totale",
    "normaliser_angle",
    "plage_alphat_rectangle",
    "vers_alpha_beta",
    "vers_alphat_phia",
]


def normaliser_angle(angle: float) -> float:
    """Ramène un angle dans [0, 360[."""
    resultat = math.fmod(angle, 360.0)
    if resultat < 0.0:
        resultat += 360.0
    if resultat >= 360.0 - TOLERANCE:
        resultat = 0.0
    return resultat


def incidence_totale(alpha: float, beta: float) -> float:
    """αt = acos(cos α cos β)."""
    c = math.cos(math.radians(alpha)) * math.cos(math.radians(beta))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def vers_alphat_phia(alpha: float, beta: float) -> tuple[float, float]:
    """(α, β) → (αt, φa), §2.2. À αt = 0, φa vaut 0 par convention (§2.5)."""
    alphat = incidence_totale(alpha, beta)
    if alphat <= TOLERANCE:
        return 0.0, 0.0
    a, b = math.radians(alpha), math.radians(beta)
    phia = math.degrees(math.atan2(math.sin(b), math.sin(a) * math.cos(b)))
    return alphat, normaliser_angle(phia)


def vers_alpha_beta(alphat: float, phia: float) -> tuple[float, float]:
    """(αt, φa) → (α, β), §2.2.

    α est tiré de atan2(sin αt cos φa, cos αt) plutôt que de tan α, pour rester
    défini quand αt approche 90°.
    """
    at, ph = math.radians(alphat), math.radians(phia)
    alpha = math.degrees(math.atan2(math.sin(at) * math.cos(ph), math.cos(at)))
    beta = math.degrees(math.asin(max(-1.0, min(1.0, math.sin(at) * math.sin(ph)))))
    return alpha, beta


def braquages_mixtes(dm: float, dn: float, phia: float) -> tuple[float, float]:
    """(δm, δn) engin → (δmB, δnB) mixte, §7.1."""
    c, s = math.cos(math.radians(phia)), math.sin(math.radians(phia))
    return c * dm - s * dn, s * dm + c * dn


def braquages_engin(dmb: float, dnb: float, phia: float) -> tuple[float, float]:
    """(δmB, δnB) mixte → (δm, δn) engin : rotation inverse de :func:`braquages_mixtes`."""
    c, s = math.cos(math.radians(phia)), math.sin(math.radians(phia))
    return c * dmb + s * dnb, -s * dmb + c * dnb


# ---------------------------------------------------------------------------
# Image polaire d'un rectangle (α, β)
# ---------------------------------------------------------------------------


def plage_alphat_rectangle(alpha: Intervalle, beta: Intervalle) -> Intervalle:
    """Plage d'αt couverte par le rectangle ``alpha × beta`` (§5.1).

    αt croît avec |α| et avec |β| : le maximum est au coin le plus éloigné de
    l'origine, le minimum au point du rectangle le plus proche de l'origine.
    """
    a_max = max(abs(alpha.bas), abs(alpha.haut))
    b_max = max(abs(beta.bas), abs(beta.haut))
    a_min = 0.0 if alpha.contient(0.0) else min(abs(alpha.bas), abs(alpha.haut))
    b_min = 0.0 if beta.contient(0.0) else min(abs(beta.bas), abs(beta.haut))
    return Intervalle.ferme(incidence_totale(a_min, b_min), incidence_totale(a_max, b_max))


class Arc:
    """Arc fermé de cercle : de ``debut`` à ``debut + longueur`` (degrés, sens direct)."""

    __slots__ = ("debut", "longueur")

    def __init__(self, debut: float, longueur: float) -> None:
        self.debut = normaliser_angle(debut)
        self.longueur = min(max(longueur, 0.0), 360.0)

    @property
    def est_complet(self) -> bool:
        """Vrai si l'arc fait le tour entier."""
        return self.longueur >= 360.0 - TOLERANCE

    def __repr__(self) -> str:
        return f"Arc(debut={self.debut:g}, longueur={self.longueur:g})"


def arc_phia_rectangle(alpha: Intervalle, beta: Intervalle) -> Arc:
    """L'arc de φa couvert par les points du rectangle où αt > 0.

    Le long d'un côté du rectangle, φa varie de façon monotone (à α fixé,
    tan φa = tan β / sin α ; à β fixé, φa = atan2(sin β, sin α cos β)). Les
    directions extrêmes sont donc celles des coins, et l'arc cherché est le
    plus petit arc contenant les directions des coins — le complément du plus
    grand écart entre elles. Si l'origine est strictement intérieure, l'arc est
    complet. Un coin à l'origine n'a pas de direction et est ignoré : les deux
    côtés qui y aboutissent donnent leurs directions par leurs autres coins.
    """
    if (
        alpha.bas < -TOLERANCE
        and alpha.haut > TOLERANCE
        and beta.bas < -TOLERANCE
        and beta.haut > TOLERANCE
    ):
        return Arc(0.0, 360.0)
    directions = sorted(
        {
            vers_alphat_phia(a, b)[1]
            for a in (alpha.bas, alpha.haut)
            for b in (beta.bas, beta.haut)
            if incidence_totale(a, b) > TOLERANCE
        }
    )
    if not directions:
        raise ValueError("le rectangle (α, β) est réduit à l'origine : aucun φa")
    if len(directions) == 1:
        return Arc(directions[0], 0.0)
    ecarts = [
        ((directions[(i + 1) % len(directions)] - d) % 360.0, i) for i, d in enumerate(directions)
    ]
    plus_grand, i = max(ecarts)
    debut = directions[(i + 1) % len(directions)]
    return Arc(debut, 360.0 - plus_grand)
