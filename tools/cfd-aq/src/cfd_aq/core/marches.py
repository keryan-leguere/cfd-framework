"""Drag ratio CDe/Cfe of a step or a ridge, after AGARD-AG-264 §4.3.

One function per excrescence shape, each returning the dimensionless ratio
``CDe/Cfe`` that :mod:`cfd_aq.core.trainee` turns into a force. The three
shapes are the ones the AGARDograph treats as a family (§4.3.1, §4.3.2):

``marche montante``
    forward-facing step — flow runs onto a surface that steps up.
``marche descendante``
    rearward-facing step — the surface steps down.
``arête``
    ridge, i.e. a forward step followed closely by a rearward one.

A ridge is **not** the sum of its two steps. Superposing them underestimates
the measured square-ridge drag by about half at low Mach number (§4.3.2.1):
the recirculation behind the forward face never reattaches before the rearward
face, so the interference is of the same order as the parts.
:func:`interference_arete` exposes that comparison.

Mach number is handled in three bands, as the report prescribes:

* ``M ≤ 0.8`` and ``M ≥ 1.4`` — read the straight line of the relevant figure,
  interpolating linearly in Mach between the tabulated lines;
* ``0.8 < M < 1.4`` — equations 4(27), 4(32) and 4(38), which blend the M = 0.8
  and M = 1.4 lines with a measured transonic factor PC₁, PC₂ or PC₃.

Outside the tabulated Mach range the nearest line is held constant, and
:func:`verifier_domaine` reports every extrapolation the caller is making.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from cfd_aq.core import donnees

__all__ = [
    "Avertissement",
    "TypeAsperite",
    "facteur_arrondi_descendante",
    "facteur_arrondi_montante",
    "facteur_chanfrein_descendante",
    "facteur_chanfrein_montante",
    "facteur_derapage",
    "facteur_epaisseur_arete",
    "interference_arete",
    "pc1",
    "pc2",
    "pc3",
    "ratio_arete",
    "ratio_arete_rectangulaire_2h",
    "ratio_asperite",
    "ratio_marche_descendante",
    "ratio_marche_montante",
    "verifier_domaine",
]


class TypeAsperite(str, Enum):
    """The three excrescence shapes the module knows."""

    MONTANTE = "montante"
    DESCENDANTE = "descendante"
    ARETE = "arete"


@dataclass(frozen=True)
class Avertissement:
    """One extrapolation outside the measured domain.

    Attributes:
        grandeur: which quantity left the domain ("h+", "Mach", "h/delta"…).
        valeur: the value that left it.
        domaine: the interval the data actually cover.
        message: a sentence an engineer can act on.
    """

    grandeur: str
    valeur: float
    domaine: tuple[float, float]
    message: str


# --------------------------------------------------------------------------
# Interpolation
# --------------------------------------------------------------------------


def _interpoler(x: float, abscisses: Sequence[float], ordonnees: Sequence[float]) -> float:
    """Piecewise-linear interpolation, holding the end values outside the range."""
    if x <= abscisses[0]:
        return float(ordonnees[0])
    if x >= abscisses[-1]:
        return float(ordonnees[-1])
    for i in range(1, len(abscisses)):
        if x <= abscisses[i]:
            x0, x1 = abscisses[i - 1], abscisses[i]
            y0, y1 = ordonnees[i - 1], ordonnees[i]
            return float(y0 + (y1 - y0) * (x - x0) / (x1 - x0))
    return float(ordonnees[-1])  # pragma: no cover - unreachable, bornes traitées


def _droite(table: donnees.DroitesLogH, mach: float, h_plus: float) -> float:
    """``A·log₁₀(h⁺) + B`` at ``mach``, interpolating linearly between the tabulated lines.

    Interpolating the *drag ratio* rather than the coefficients A and B is
    deliberate: A and B are a slope and an intercept at h⁺ = 1, a decade below
    anything measured, so a Mach-interpolation of B alone has no physical
    meaning. Blending the two lines at the h⁺ of interest keeps the result
    inside the envelope of the two measured curves.
    """
    machs = sorted(table)
    valeurs = [table[m][0] * math.log10(h_plus) + table[m][1] for m in machs]
    return _interpoler(mach, machs, valeurs)


def pc1(mach: float) -> float:
    """Transonic blending factor PC₁ for a forward-facing step — Figure 4.25."""
    return _interpoler(mach, *donnees.PC1_MARCHE_MONTANTE)


def pc2(mach: float) -> float:
    """Transonic blending factor PC₂ for a rearward-facing step — Figure 4.30."""
    return _interpoler(mach, *donnees.PC2_MARCHE_DESCENDANTE)


def pc3(mach: float) -> float:
    """Transonic blending factor PC₃ for a ridge — Figure 4.38."""
    return _interpoler(mach, *donnees.PC3_ARETE)


def _transsonique(
    table: donnees.DroitesLogH,
    facteur_pc: float,
    h_plus: float,
) -> float:
    """Equations 4(27), 4(32), 4(38): blend the M = 0.8 and M = 1.4 lines."""
    bas = table[0.8][0] * math.log10(h_plus) + table[0.8][1]
    haut = table[1.4][0] * math.log10(h_plus) + table[1.4][1]
    return bas + facteur_pc * (haut - bas)


# --------------------------------------------------------------------------
# Rapports de traînée
# --------------------------------------------------------------------------


def ratio_marche_montante(h_plus: float, mach: float) -> float:
    """CDe/Cfe of a plain 2-D forward-facing step normal to the flow.

    Figures 4.23 and 4.25, equations 4(26) and 4(27). Above M = 1.4 the report
    gives a single supersonic line, so the result stops varying with Mach.

    Args:
        h_plus: roughness Reynolds number u_τ·h/ν_w [-].
        mach: local Mach number at the boundary-layer edge [-].

    Returns:
        CDe/Cfe [-], never negative.
    """
    _valider_h_plus(h_plus)
    if 0.8 < mach < 1.4:
        valeur = _transsonique(donnees.MARCHE_MONTANTE, pc1(mach), h_plus)
    else:
        valeur = _droite(donnees.MARCHE_MONTANTE, mach, h_plus)
    return max(valeur, 0.0)


def ratio_marche_descendante(h_plus: float, mach: float) -> float:
    """CDe/Cfe of a plain 2-D rearward-facing step normal to the flow.

    Figures 4.28 and 4.30, equations 4(31) and 4(32). The drag peaks near
    M ≈ 1.15 — PC₂ exceeds 1 there — then falls away with increasing Mach
    number, unlike the forward step.

    Args:
        h_plus: roughness Reynolds number u_τ·h/ν_w [-].
        mach: local Mach number at the boundary-layer edge [-].

    Returns:
        CDe/Cfe [-], never negative.
    """
    _valider_h_plus(h_plus)
    if 0.8 < mach < 1.4:
        valeur = _transsonique(donnees.MARCHE_DESCENDANTE, pc2(mach), h_plus)
    else:
        valeur = _droite(donnees.MARCHE_DESCENDANTE, mach, h_plus)
    return max(valeur, 0.0)


def ratio_arete(h_plus: float, mach: float, t_sur_h: float = 1.0) -> float:
    """CDe/Cfe of a 2-D ridge with vertical faces, thickness ``t_sur_h``·h.

    Square ridge from the published coefficients of equation 4(37), transonic
    range from equation 4(38) with PC₃, thickness effect from equation 4(39)
    with T(t/h) of Figure 4.40.

    ``t_sur_h = 0`` is a plate normal to the flow (a ridge of zero thickness);
    T saturates at 0.58 beyond t/h ≈ 4, where the flow reattaches between the
    two faces.

    Args:
        h_plus: roughness Reynolds number u_τ·h/ν_w [-].
        mach: local Mach number at the boundary-layer edge [-].
        t_sur_h: ridge thickness over height [-].

    Returns:
        CDe/Cfe [-], never negative.
    """
    _valider_h_plus(h_plus)
    if t_sur_h < 0.0:
        raise ValueError(f"t/h doit être ≥ 0 (reçu {t_sur_h})")
    if 0.8 < mach < 1.4:
        valeur = _transsonique(donnees.ARETE_CARREE, pc3(mach), h_plus)
    else:
        valeur = _droite(donnees.ARETE_CARREE, mach, h_plus)
    return max(valeur * facteur_epaisseur_arete(t_sur_h), 0.0)


def ratio_arete_rectangulaire_2h(h_plus: float, mach: float) -> float:
    """CDe/Cfe of a ridge of thickness exactly t = 2h, from its own published table.

    The AGARDograph gives this case twice and the two routes disagree. This
    table crosses the square-ridge line at h⁺ ≈ 1000 — above it below, under
    it above — which is what §4.3.2.1 describes in words. The generic
    ``T(2)·(square ridge)`` of equation 4(39) instead sits a flat 21 % below
    the square ridge everywhere, so the two differ by 80 % at h⁺ = 100 and by
    27 % at h⁺ = 1000. The report says why: the T curve comes from Wieghardt's
    ridges, all at h/δ > 3 %, while the square/rectangular crossover sits at
    h/δ ≈ 0.02–0.03.

    :func:`ratio_arete` deliberately follows the generic route, which is the
    only one defined for every t/h; use this function when t = 2h and the
    excrescence is shallowly immersed.
    """
    _valider_h_plus(h_plus)
    if 0.8 < mach < 1.4:
        valeur = _transsonique(donnees.ARETE_RECTANGULAIRE_2H, pc3(mach), h_plus)
    else:
        valeur = _droite(donnees.ARETE_RECTANGULAIRE_2H, mach, h_plus)
    return max(valeur, 0.0)


def ratio_asperite(
    type_asperite: TypeAsperite,
    h_plus: float,
    mach: float,
    t_sur_h: float = 1.0,
) -> float:
    """Dispatch to the plain drag ratio of ``type_asperite``."""
    if type_asperite is TypeAsperite.MONTANTE:
        return ratio_marche_montante(h_plus, mach)
    if type_asperite is TypeAsperite.DESCENDANTE:
        return ratio_marche_descendante(h_plus, mach)
    return ratio_arete(h_plus, mach, t_sur_h)


def interference_arete(h_plus: float, mach: float) -> tuple[float, float, float]:
    """Compare a square ridge with the sum of its two steps — §4.3.2.1.

    Returns:
        ``(arête, somme des deux marches, rapport somme/arête)``. The report's
        observation is that the ratio is about 0.5 at low Mach number and
        climbs to 1 by M = 2.8, where the interference has disappeared.
    """
    arete = ratio_arete(h_plus, mach)
    somme = ratio_marche_montante(h_plus, mach) + ratio_marche_descendante(h_plus, mach)
    return arete, somme, somme / arete if arete > 0.0 else math.nan


# --------------------------------------------------------------------------
# Corrections de forme
# --------------------------------------------------------------------------


def _interpoler_famille_mach(famille: dict[float, donnees.Courbe], mach: float, x: float) -> float:
    """Interpolate a Mach-keyed family of curves at ``x``, then across Mach."""
    machs = sorted(famille)
    valeurs = [_interpoler(x, *famille[m]) for m in machs]
    return _interpoler(mach, machs, valeurs)


def facteur_arrondi_montante(r_sur_h: float, mach: float) -> float:
    """Multiplying factor (1 − E) for a rounded forward step — eq. 4(28), Figure 4.26(a).

    Rounding the upstream edge always helps: at M = 0.8 a radius of 0.4 h
    already removes 60 % of the step's drag. The benefit collapses with Mach
    number — at M = 2 the same radius buys 6 %.
    """
    if r_sur_h < 0.0:
        raise ValueError(f"r/h doit être ≥ 0 (reçu {r_sur_h})")
    return max(1.0 - _interpoler_famille_mach(donnees.ARRONDI_MONTANTE, mach, r_sur_h), 0.0)


def facteur_chanfrein_montante(angle: float, mach: float) -> float:
    """Multiplying factor (1 − E) for a chamfered forward step — eq. 4(29), Figure 4.26(b).

    Args:
        angle: chamfer angle θ in **degrees**; 90° is the plain square step
            (factor 1), 0° a complete fairing (factor 0).
        mach: local Mach number [-].
    """
    if not 0.0 <= angle <= 90.0:
        raise ValueError(f"l'angle de chanfrein doit être dans [0°, 90°] (reçu {angle})")
    return max(1.0 - _interpoler_famille_mach(donnees.CHANFREIN_MONTANTE, mach, angle), 0.0)


def facteur_arrondi_descendante(r_sur_h: float) -> float:
    """Multiplying factor (1 + 1.43·r/h) for a rounded rearward step — eq. 4(34).

    Note the sign: rounding the downstream edge **increases** the drag
    (Figure 4.32). The relation is single-valued, independent of Mach number.
    """
    if r_sur_h < 0.0:
        raise ValueError(f"r/h doit être ≥ 0 (reçu {r_sur_h})")
    return 1.0 + donnees.RAPPORT_ARRONDI_DESCENDANTE * r_sur_h


def facteur_chanfrein_descendante(angle: float, mach: float) -> float:
    """Multiplying factor (1 − G) for a chamfered rearward step — eq. 4(33), Figure 4.33.

    Chamfering the downstream face does nothing until about 45°, and between
    12° and 45° it mildly *increases* the drag at transonic and supersonic Mach
    numbers (factor above 1). Only below 12° does the drag fall sharply.

    This is the least reliable correlation in the package: see the note on
    :data:`cfd_aq.core.donnees.CHANFREIN_DESCENDANTE`.
    """
    if not 0.0 <= angle <= 90.0:
        raise ValueError(f"l'angle de chanfrein doit être dans [0°, 90°] (reçu {angle})")
    return max(1.0 - _interpoler_famille_mach(donnees.CHANFREIN_DESCENDANTE, mach, angle), 0.0)


def facteur_epaisseur_arete(t_sur_h: float) -> float:
    """Thickness factor T(t/h) of a ridge — eq. 4(39), Figure 4.40."""
    if t_sur_h < 0.0:
        raise ValueError(f"t/h doit être ≥ 0 (reçu {t_sur_h})")
    return _interpoler(t_sur_h, *donnees.EPAISSEUR_ARETE)


def facteur_derapage(angle: float) -> float:
    """Multiplying factor sin²α for an excrescence swept to the flow — eq. 4(30), 4(35), 4(41).

    Args:
        angle: angle α between the flow and the excrescence axis, in
            **degrees**; 90° means the excrescence lies across the flow
            (factor 1), 0° means it lies along it (factor 0).

    The report establishes sin²α on ridges (Figure 4.45) and states that
    applying it to steps is an assumption, not a measurement (§4.3.2.3).
    """
    if not 0.0 <= angle <= 90.0:
        raise ValueError(f"l'angle de dérapage doit être dans [0°, 90°] (reçu {angle})")
    return math.sin(math.radians(angle)) ** 2


# --------------------------------------------------------------------------
# Domaine de validité
# --------------------------------------------------------------------------


def _valider_h_plus(h_plus: float) -> None:
    if h_plus <= 0.0:
        raise ValueError(f"h⁺ doit être > 0 (reçu {h_plus})")


def _bornes_mach(type_asperite: TypeAsperite) -> tuple[float, float]:
    if type_asperite is TypeAsperite.MONTANTE:
        table = donnees.MARCHE_MONTANTE
    elif type_asperite is TypeAsperite.DESCENDANTE:
        table = donnees.MARCHE_DESCENDANTE
    else:
        table = donnees.ARETE_CARREE
    machs = sorted(table)
    return machs[0], machs[-1]


def verifier_domaine(
    type_asperite: TypeAsperite,
    h_plus: float,
    mach: float,
    immersion: float | None = None,
) -> list[Avertissement]:
    """List the extrapolations a given call is making.

    The correlations were measured over h⁺ = 10 to 2000 on steps immersed to
    h/δ ≤ 0.03. Outside that the functions still return a number — holding the
    nearest curve, extrapolating the straight line in log h⁺ — but it is an
    extrapolation and the caller should be told which one.

    Args:
        type_asperite: shape being evaluated.
        h_plus: roughness Reynolds number [-].
        mach: local Mach number [-].
        immersion: h/δ, when known.

    Returns:
        One :class:`Avertissement` per quantity out of domain; empty when the
        point sits inside the measured envelope.
    """
    avertissements: list[Avertissement] = []

    if not donnees.H_PLUS_MIN <= h_plus <= donnees.H_PLUS_MAX:
        cote = "sous" if h_plus < donnees.H_PLUS_MIN else "au-dessus de"
        avertissements.append(
            Avertissement(
                grandeur="h+",
                valeur=h_plus,
                domaine=(donnees.H_PLUS_MIN, donnees.H_PLUS_MAX),
                message=(
                    f"h⁺ = {h_plus:.3g} est {cote} la plage mesurée "
                    f"[{donnees.H_PLUS_MIN:.0f}, {donnees.H_PLUS_MAX:.0f}] : la droite "
                    "CDe/Cfe = A·log₁₀(h⁺) + B est extrapolée."
                ),
            )
        )

    # Le seuil vaut jusqu'à M = 1,4 : entre 0,8 et 1,4 le résultat est un
    # mélange des droites M = 0,8 et M = 1,4, et la première est en cause.
    if (
        type_asperite is TypeAsperite.MONTANTE
        and mach < 1.4
        and donnees.H_PLUS_MIN <= h_plus < donnees.H_PLUS_MIN_MONTANTE_SUBSONIQUE
    ):
        avertissements.append(
            Avertissement(
                grandeur="h+",
                valeur=h_plus,
                domaine=(donnees.H_PLUS_MIN_MONTANTE_SUBSONIQUE, donnees.H_PLUS_MAX),
                message=(
                    f"h⁺ = {h_plus:.3g} : les droites subsoniques de la marche montante "
                    f"(Figure 4.23) ne sont tracées qu'à partir de h⁺ ≈ "
                    f"{donnees.H_PLUS_MIN_MONTANTE_SUBSONIQUE:.0f}, et c'est la droite "
                    "M = 0,8 qui sert aussi de borne basse au mélange transsonique. Plus "
                    "bas, leur forte pente les fait passer sous celles de la marche "
                    "descendante : artefact d'extrapolation, pas une mesure."
                ),
            )
        )

    mach_min, mach_max = _bornes_mach(type_asperite)
    if not mach_min <= mach <= mach_max:
        cote = "sous" if mach < mach_min else "au-dessus de"
        avertissements.append(
            Avertissement(
                grandeur="Mach",
                valeur=mach,
                domaine=(mach_min, mach_max),
                message=(
                    f"M = {mach:.3g} est {cote} la plage tabulée "
                    f"[{mach_min:g}, {mach_max:g}] pour une aspérité « {type_asperite.value} » : "
                    "la courbe la plus proche est maintenue constante."
                ),
            )
        )

    if immersion is not None and immersion > donnees.H_SUR_DELTA_MAX:
        avertissements.append(
            Avertissement(
                grandeur="h/delta",
                valeur=immersion,
                domaine=(0.0, donnees.H_SUR_DELTA_MAX),
                message=(
                    f"h/δ = {immersion:.3g} dépasse {donnees.H_SUR_DELTA_MAX:g} : l'aspérité n'est "
                    "plus noyée dans la région interne de la couche limite et la corrélation "
                    "en h⁺ perd son fondement."
                ),
            )
        )

    return avertissements
