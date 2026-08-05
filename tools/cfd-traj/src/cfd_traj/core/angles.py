"""Conversion between wind angles (alpha, beta) and aeroballistic angles (alpha_tot, phi).

A trajectory is logged in wind angles because that is what the flight-mechanics
code produces, but the flow does not see them separately: what it sees is the
*direction* of the velocity vector relative to the body, which is one angle off
the body axis (the total incidence ``alpha_tot``) plus one azimuth around it
(the aerodynamic roll ``phi``). Working in (alpha_tot, phi) is what makes the
symmetry reduction of :mod:`cfd_traj.core.symmetry` possible at all — a mirror
plane of the configuration acts on phi, not on (alpha, beta).

Conventions. Body axes are x forward, y right, z down; ``alpha`` is the
incidence in the x-z plane and ``beta`` the sideslip, both in degrees. The unit
velocity direction is then::

    v = (cos a . cos b,  sin b,  sin a . cos b)

from which the two aeroballistic angles follow directly::

    alpha_tot = atan2( hypot(sin b, sin a . cos b),  cos a . cos b )
    phi       = atan2( sin b,  sin a . cos b )

These are algebraically the classical relations ``tan(alpha_tot).cos(phi) =
tan(a)`` and ``tan(alpha_tot).sin(phi) = tan(b)/cos(a)`` — divide numerator and
denominator by ``cos a . cos b`` to see it — but the ``atan2`` form is
uniformly accurate. The tangent form blows up as ``a`` approaches 90 degrees,
and the ``arccos(cos a . cos b)`` form loses half its significant digits near
``alpha_tot = 0``, which is exactly the most-flown part of the domain.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

#: Beyond this, the input is not a trajectory, it is a data error. Wind angles
#: this large also make the body-axis parametrisation singular.
ALPHA_MAX_DEG: float = 89.9

#: Below this, alpha_tot is treated as zero and phi as geometrically undefined.
ANGLE_TOL_DEG: float = 1e-9


class AngleError(ValueError):
    """Wind angles outside the range this parametrisation can describe."""


def _check_range(alpha_deg: NDArray[np.float64], beta_deg: NDArray[np.float64]) -> None:
    """Reject wind angles too close to the parametrisation's singularity.

    NaN is deliberately allowed through: a missing row is a data-quality issue
    reported by the dataset layer, not a modelling error.
    """
    for name, values in (("alpha", alpha_deg), ("beta", beta_deg)):
        bad = np.abs(values) > ALPHA_MAX_DEG
        if np.any(bad):
            worst = float(np.nanmax(np.abs(values[bad])))
            raise AngleError(
                f"{name} = {worst:.3f} deg exceeds the +/-{ALPHA_MAX_DEG} deg limit; "
                f"this is a data error, not a flight condition"
            )


def velocity_direction(alpha_deg: ArrayLike, beta_deg: ArrayLike) -> NDArray[np.float64]:
    """Unit velocity vector in body axes, shape ``(..., 3)`` = (x fwd, y right, z down)."""
    a = np.deg2rad(np.asarray(alpha_deg, dtype=np.float64))
    b = np.deg2rad(np.asarray(beta_deg, dtype=np.float64))
    return np.stack(
        [np.cos(a) * np.cos(b), np.sin(b), np.sin(a) * np.cos(b)],
        axis=-1,
    )


def total_incidence(alpha_deg: ArrayLike, beta_deg: ArrayLike) -> NDArray[np.float64]:
    """Total incidence ``alpha_tot`` in degrees, in [0, 180]."""
    a_deg = np.asarray(alpha_deg, dtype=np.float64)
    b_deg = np.asarray(beta_deg, dtype=np.float64)
    _check_range(a_deg, b_deg)
    a = np.deg2rad(a_deg)
    b = np.deg2rad(b_deg)
    transverse = np.hypot(np.sin(b), np.sin(a) * np.cos(b))
    axial = np.cos(a) * np.cos(b)
    return np.asarray(np.rad2deg(np.arctan2(transverse, axial)), dtype=np.float64)


def aerodynamic_roll(alpha_deg: ArrayLike, beta_deg: ArrayLike) -> NDArray[np.float64]:
    """Aerodynamic roll ``phi`` in degrees, wrapped into [0, 360).

    Returns 0 where the angle is geometrically undefined (alpha = beta = 0);
    use :func:`is_roll_defined` to tell that case apart from a genuine phi = 0.
    """
    a_deg = np.asarray(alpha_deg, dtype=np.float64)
    b_deg = np.asarray(beta_deg, dtype=np.float64)
    _check_range(a_deg, b_deg)
    a = np.deg2rad(a_deg)
    b = np.deg2rad(b_deg)
    phi = np.rad2deg(np.arctan2(np.sin(b), np.sin(a) * np.cos(b)))
    return np.asarray(np.mod(phi, 360.0), dtype=np.float64)


def is_roll_defined(
    alpha_deg: ArrayLike, beta_deg: ArrayLike, *, tol_deg: float = ANGLE_TOL_DEG
) -> NDArray[np.bool_]:
    """False where alpha == beta == 0 and the azimuth of the velocity has no meaning.

    At zero total incidence the velocity is on the body axis and every azimuth
    describes the same flow, so phi is a free parameter rather than a datum.
    Keeping the distinction explicit stops those rows from polluting the phi
    quantiles with an arbitrary value.
    """
    a = np.abs(np.asarray(alpha_deg, dtype=np.float64))
    b = np.abs(np.asarray(beta_deg, dtype=np.float64))
    return np.asarray((a > tol_deg) | (b > tol_deg), dtype=np.bool_)


def to_aeroballistic(
    alpha_deg: ArrayLike, beta_deg: ArrayLike, *, tol_deg: float = ANGLE_TOL_DEG
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.bool_]]:
    """Return ``(alpha_tot_deg, phi_deg, phi_defined)`` — the single call the dataset uses."""
    alpha_tot = total_incidence(alpha_deg, beta_deg)
    phi = aerodynamic_roll(alpha_deg, beta_deg)
    defined = is_roll_defined(alpha_deg, beta_deg, tol_deg=tol_deg)
    phi = np.where(defined, phi, 0.0)
    return alpha_tot, phi, defined


def from_aeroballistic(
    alpha_tot_deg: ArrayLike, phi_deg: ArrayLike
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Exact inverse of :func:`to_aeroballistic`: return ``(alpha_deg, beta_deg)``."""
    at = np.deg2rad(np.asarray(alpha_tot_deg, dtype=np.float64))
    ph = np.deg2rad(np.asarray(phi_deg, dtype=np.float64))
    sin_b = np.sin(at) * np.sin(ph)
    beta = np.arcsin(np.clip(sin_b, -1.0, 1.0))
    alpha = np.arctan2(np.sin(at) * np.cos(ph), np.cos(at))
    return np.rad2deg(alpha), np.rad2deg(beta)
