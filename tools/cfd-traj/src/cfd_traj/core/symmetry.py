"""Symmetry group of the configuration, and everything it buys.

After non-dimensionalisation, this is the layer that produces the largest
reduction of the design of experiments -- and the one that hides the most
expensive mistakes when a symmetry is assumed that the physics does not have.

The idea in one sentence: if an operation ``g`` of the configuration's symmetry
group leaves *both* the geometry and the boundary conditions (wind direction,
control-surface deflections) invariant, then the solution field is invariant
under ``g`` too, and the coefficients at the transformed attitude follow from
the original ones with no extra computation. Three consequences, all
implemented here:

1. **Folding.** The azimuth ``phi`` only has to be described over the group's
   fundamental domain: [0, 45] deg for C4v instead of the full turn.
2. **Parity.** A reflection about the wind plane preserves the in-plane
   components (CA, CN, Cm) and flips the out-of-plane ones (CY, Cn, Cl). When
   the wind plane *is* a mirror plane of the configuration, the out-of-plane
   components are identically zero -- not small: zero, by theorem. That is
   both a storage reduction and a free quality check.
3. **Mesh reduction.** Each node of the plan can be computed on a reduced
   domain (a sector, a half configuration) closed by symmetry conditions,
   instead of the full configuration.

The classic and costly trap this module exists to prevent: computing a *roll*
deflection on a half configuration. The deflections break the mirror the wind
plane would otherwise provide, the solver silently imposes a symmetry the
physics does not have, and the result is wrong with no error message.
Deflection sets are therefore classified here, once, and carried by every row
of the plan.

Schoenflies notation, restricted to what a body of revolution with fins can be:
``Cinfv`` (body of revolution), ``C4v`` (cruciform: 4-fold axis plus four
mirror planes), ``C4`` (4-fold axis only -- fins clocked away from any mirror,
or canted), ``Cs`` (a single mirror plane), ``C1`` (no symmetry at all).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from cfd_traj._compat import StrEnum


class SymmetryGroup(StrEnum):
    """Symmetry group of the configuration, in Schoenflies notation."""

    C4V = "C4v"
    C4 = "C4"
    CS = "Cs"
    C1 = "C1"
    CINFV = "Cinfv"


class CalcConfig(StrEnum):
    """Computational domain a case can legitimately be run on."""

    AXI_2D = "axisymetrique_2d"
    SECTEUR_45 = "secteur_45"
    QUART_90 = "quart_90_cyclique"
    DEMI = "demi_configuration"
    COMPLETE = "configuration_complete"


class DeflectionSymmetry(StrEnum):
    """What a set of control-surface deflections does to the wind-plane mirror."""

    NULLE = "nulle"
    SYMETRIQUE = "symetrique"
    ANTISYMETRIQUE = "antisymetrique"
    QUELCONQUE = "quelconque"


#: Cost of each domain relative to the full configuration. Rough but monotone;
#: what matters is the ordering and the order of magnitude, not the third digit.
RELATIVE_COST: Mapping[CalcConfig, float] = {
    CalcConfig.AXI_2D: 0.01,
    CalcConfig.SECTEUR_45: 0.125,
    CalcConfig.QUART_90: 0.25,
    CalcConfig.DEMI: 0.5,
    CalcConfig.COMPLETE: 1.0,
}

#: Preserved by a reflection about the wind plane.
IN_PLANE_COMPONENTS: tuple[str, ...] = ("CA", "CN", "Cm")

#: Sign-flipped by a reflection about the wind plane, hence zero when it is a mirror.
OUT_OF_PLANE_COMPONENTS: tuple[str, ...] = ("CY", "Cn", "Cl")

#: Azimuth period of each group, in degrees.
_PERIOD_DEG: Mapping[SymmetryGroup, float] = {
    SymmetryGroup.C4V: 90.0,
    SymmetryGroup.C4: 90.0,
    SymmetryGroup.CS: 360.0,
    SymmetryGroup.C1: 360.0,
    SymmetryGroup.CINFV: 360.0,
}

#: Fundamental domain of phi, in degrees. Closed on the right for the groups
#: that fold by a mirror, half-open for the ones that only rotate.
_DOMAIN_DEG: Mapping[SymmetryGroup, tuple[float, float]] = {
    SymmetryGroup.C4V: (0.0, 45.0),
    SymmetryGroup.C4: (0.0, 90.0),
    SymmetryGroup.CS: (0.0, 180.0),
    SymmetryGroup.C1: (0.0, 360.0),
    SymmetryGroup.CINFV: (0.0, 0.0),
}

#: Groups whose fundamental domain is closed on the right (mirror folding).
_CLOSED_DOMAIN: frozenset[SymmetryGroup] = frozenset(
    {SymmetryGroup.C4V, SymmetryGroup.CS, SymmetryGroup.CINFV}
)

#: Groups possessing at least one mirror plane containing the body axis.
_HAS_MIRROR: frozenset[SymmetryGroup] = frozenset(
    {SymmetryGroup.C4V, SymmetryGroup.CS, SymmetryGroup.CINFV}
)

#: Default number of azimuth levels. Three is enough for C4v: the in-plane
#: components develop in cos(4.phi), so 0 / 22.5 / 45 deg separates the mean
#: from the first harmonic, and the out-of-plane ones peak at 22.5 deg.
_DEFAULT_N_AZIMUTHS: Mapping[SymmetryGroup, int] = {
    SymmetryGroup.C4V: 3,
    SymmetryGroup.C4: 5,
    SymmetryGroup.CS: 5,
    SymmetryGroup.C1: 8,
    SymmetryGroup.CINFV: 1,
}

#: Domain a case at zero total incidence and neutral deflections can be run on.
_ZERO_INCIDENCE_CONFIG: Mapping[SymmetryGroup, CalcConfig] = {
    SymmetryGroup.CINFV: CalcConfig.AXI_2D,
    SymmetryGroup.C4V: CalcConfig.SECTEUR_45,
    SymmetryGroup.C4: CalcConfig.QUART_90,
    SymmetryGroup.CS: CalcConfig.DEMI,
    SymmetryGroup.C1: CalcConfig.COMPLETE,
}


@dataclass(frozen=True)
class SymmetrySpec:
    """The symmetry declaration of one study.

    ``reference_plane_deg`` shifts which body plane is called phi = 0. For a
    cruciform in an X attitude the natural choice is the vertical plane
    *between* two fins, which is also the one whose half-configuration cut does
    not slice a fin along its chord.
    """

    group: SymmetryGroup
    reference_plane_deg: float = 0.0
    n_azimuths: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.group, SymmetryGroup):
            raise ValueError(
                f"unknown symmetry group {self.group!r}; "
                f"valid values: {[g.value for g in SymmetryGroup]}"
            )
        if not np.isfinite(self.reference_plane_deg):
            raise ValueError(f"reference_plane_deg must be finite, got {self.reference_plane_deg}")
        if self.n_azimuths is not None and self.n_azimuths <= 0:
            raise ValueError(f"n_azimuths must be positive, got {self.n_azimuths}")

    @property
    def period_deg(self) -> float:
        """Azimuth period of the group, in degrees."""
        return _PERIOD_DEG[self.group]

    @property
    def fundamental_domain_deg(self) -> tuple[float, float]:
        """Bounds of the folded azimuth, in degrees."""
        return _DOMAIN_DEG[self.group]

    @property
    def domain_is_closed(self) -> bool:
        """True when the upper bound of the fundamental domain is attained."""
        return self.group in _CLOSED_DOMAIN

    @property
    def has_mirror(self) -> bool:
        """True when the group contains at least one mirror plane."""
        return self.group in _HAS_MIRROR

    @property
    def n_azimuth_levels(self) -> int:
        """Number of phi levels the plan will carry."""
        if self.group is SymmetryGroup.CINFV:
            return 1
        return self.n_azimuths if self.n_azimuths is not None else _DEFAULT_N_AZIMUTHS[self.group]


def fold_phi(phi_deg: ArrayLike, spec: SymmetrySpec) -> NDArray[np.float64]:
    """Fold phi into the group's fundamental domain.

    Idempotent and periodic by construction: ``fold(fold(x)) == fold(x)`` and
    ``fold(x + period) == fold(x)``.
    """
    phi = np.asarray(phi_deg, dtype=np.float64) - spec.reference_plane_deg
    if spec.group is SymmetryGroup.CINFV:
        return np.zeros_like(phi)

    period = spec.period_deg
    folded = np.mod(phi, period)
    if spec.group in (SymmetryGroup.C4V, SymmetryGroup.CS):
        half = period / 2.0
        folded = np.where(folded > half, period - folded, folded)
    return np.asarray(folded, dtype=np.float64)


def wind_plane_is_mirror(
    phi_folded_deg: ArrayLike, spec: SymmetrySpec, *, tol_deg: float = 1e-6
) -> NDArray[np.bool_]:
    """True where the plane containing the velocity is a mirror plane of the configuration."""
    phi = np.asarray(phi_folded_deg, dtype=np.float64)
    if spec.group is SymmetryGroup.CINFV:
        return np.ones(phi.shape, dtype=np.bool_)
    if spec.group in (SymmetryGroup.C4, SymmetryGroup.C1):
        return np.zeros(phi.shape, dtype=np.bool_)
    low, high = spec.fundamental_domain_deg
    return np.asarray(
        (np.abs(phi - low) <= tol_deg) | (np.abs(phi - high) <= tol_deg), dtype=np.bool_
    )


def classify_deflection(
    dl: float, dm: float, dn: float, *, tol: float = 1e-9
) -> DeflectionSymmetry:
    """Classify a deflection set by what it does to the wind-plane mirror.

    A reflection about the wind plane sends roll to -roll and yaw to -yaw while
    leaving pitch alone. A set is therefore *symmetric* (mirror preserved) when
    roll and yaw are both zero, and *antisymmetric* when pitch is zero but roll
    or yaw is not. Anything else preserves nothing.
    """
    roll = abs(dl) > tol
    pitch = abs(dm) > tol
    yaw = abs(dn) > tol
    if not (roll or pitch or yaw):
        return DeflectionSymmetry.NULLE
    if not roll and not yaw:
        return DeflectionSymmetry.SYMETRIQUE
    if not pitch:
        return DeflectionSymmetry.ANTISYMETRIQUE
    return DeflectionSymmetry.QUELCONQUE


def zero_components(
    phi_folded_deg: float,
    spec: SymmetrySpec,
    deflection: DeflectionSymmetry,
    *,
    tol_deg: float = 1e-6,
) -> tuple[str, ...]:
    """Coefficient components that are identically zero by theorem at this node."""
    if deflection not in (DeflectionSymmetry.NULLE, DeflectionSymmetry.SYMETRIQUE):
        return ()
    if not bool(wind_plane_is_mirror(np.asarray(phi_folded_deg), spec, tol_deg=tol_deg)):
        return ()
    return OUT_OF_PLANE_COMPONENTS


def calc_config(
    *,
    alpha_tot_deg: float,
    phi_folded_deg: float,
    spec: SymmetrySpec,
    deflection: DeflectionSymmetry,
    alpha_tol_deg: float = 1e-6,
) -> CalcConfig:
    """Smallest computational domain this case can legitimately be run on."""
    at_zero_incidence = abs(alpha_tot_deg) <= alpha_tol_deg

    if at_zero_incidence and deflection is DeflectionSymmetry.NULLE:
        # The wind is on the axis: the whole group survives, sectors are legal.
        return _ZERO_INCIDENCE_CONFIG[spec.group]

    if deflection in (DeflectionSymmetry.NULLE, DeflectionSymmetry.SYMETRIQUE) and bool(
        wind_plane_is_mirror(np.asarray(phi_folded_deg), spec)
    ):
        return CalcConfig.DEMI

    # Either the wind plane is not a mirror, or the deflections have destroyed
    # it. Nothing can be folded -- this is the roll-deflection trap.
    return CalcConfig.COMPLETE


def azimuth_levels(spec: SymmetrySpec) -> tuple[float, ...]:
    """Phi levels of the plan, spanning the fundamental domain of the group."""
    n = spec.n_azimuth_levels
    if spec.group is SymmetryGroup.CINFV:
        return (0.0,)
    low, high = spec.fundamental_domain_deg
    if n == 1:
        return (low,)
    if spec.domain_is_closed:
        levels = np.linspace(low, high, n)
    else:
        levels = np.linspace(low, high, n, endpoint=False)
    return tuple(float(x) for x in levels)


def relative_cost(config: CalcConfig) -> float:
    """Cost of one case on this domain, in full-configuration equivalents."""
    return RELATIVE_COST[config]
