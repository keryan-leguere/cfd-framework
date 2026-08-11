"""Nozzle contour generation: conical and Rao-type bell.

Both generators return a :class:`NozzleContour` with the throat at x = 0, ready
to be fed to :meth:`cfd_nozzle.core.nozzle.Nozzle.flow_field` or exported for
meshing. The divergence loss coefficient λ = (1 + cos α)/2 comes out of the
contour, since it is a purely geometric property of the exit flow direction.

See ``00_DOC/04_GEOMETRIES.md``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "NozzleContour",
    "bell_contour",
    "conical_contour",
    "rao_angles",
]


@dataclass(frozen=True)
class NozzleContour:
    """An axisymmetric contour, throat at x = 0.

    Attributes:
        x: axial abscissa [m], increasing.
        r: local radius [m].
        area: local cross-sectional area π·r² [m²].
        divergence_lambda: λ = (1 + cos α)/2, the divergence loss coefficient.
        divergent_length: axial length of the divergent [m].
        label: French description used by the reports.
        theta_n_deg / theta_e_deg: bell inflection and exit angles, None for a
            cone.
    """

    x: NDArray[np.float64]
    r: NDArray[np.float64]
    area: NDArray[np.float64]
    divergence_lambda: float
    divergent_length: float
    label: str
    theta_n_deg: float | None = None
    theta_e_deg: float | None = None

    @property
    def throat_radius(self) -> float:
        """Radius at the throat [m]."""
        return float(np.min(self.r))

    @property
    def exit_radius(self) -> float:
        """Radius at the exit plane [m]."""
        return float(self.r[-1])

    @property
    def area_ratio(self) -> float:
        """ε = Ae/At deduced from the contour itself."""
        return (self.exit_radius / self.throat_radius) ** 2


def _convergent(
    throat_radius: float,
    half_angle_deg: float,
    chamber_ratio: float,
    upstream_radius_ratio: float,
    n: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Chamber cone plus the circular fillet running into the throat."""
    rt = throat_radius
    alpha = math.radians(half_angle_deg)
    fillet = upstream_radius_ratio * rt

    angles = np.linspace(-alpha, 0.0, max(n, 20))
    x_fillet = fillet * np.sin(angles)
    r_fillet = rt + fillet * (1.0 - np.cos(angles))

    x0, r0 = float(x_fillet[0]), float(r_fillet[0])
    chamber_radius = chamber_ratio * rt
    if chamber_radius <= r0:
        raise ValueError(
            f"le rayon de chambre ({chamber_radius:.4g} m) doit dépasser le rayon "
            f"au raccord amont ({r0:.4g} m) : augmenter --chambre"
        )
    length = (chamber_radius - r0) / math.tan(alpha)
    x_cone = np.linspace(x0 - length, x0, max(n, 20))
    r_cone = r0 + (x0 - x_cone) * math.tan(alpha)
    return (
        np.concatenate([x_cone[:-1], x_fillet]),
        np.concatenate([r_cone[:-1], r_fillet]),
    )


def conical_contour(
    throat_radius: float,
    area_ratio: float,
    half_angle_deg: float = 15.0,
    *,
    convergent_half_angle_deg: float = 30.0,
    chamber_ratio: float = 2.5,
    upstream_radius_ratio: float = 1.5,
    downstream_radius_ratio: float = 0.4,
    n: int = 400,
) -> NozzleContour:
    """Conical nozzle: fillet then straight cone of half-angle ``half_angle_deg``.

    The 15° cone is the classical compromise: opening further shortens the
    nozzle but costs divergence loss, since λ = (1 + cos α)/2.
    """
    if not throat_radius > 0.0:
        raise ValueError(f"le rayon au col doit être > 0 (reçu {throat_radius})")
    if area_ratio < 1.0:
        raise ValueError(f"ε doit être ≥ 1 (reçu {area_ratio})")
    if not 0.0 < half_angle_deg < 90.0:
        raise ValueError(f"le demi-angle doit être dans ]0, 90[° (reçu {half_angle_deg})")

    rt = float(throat_radius)
    re = rt * math.sqrt(area_ratio)
    alpha = math.radians(half_angle_deg)
    fillet = downstream_radius_ratio * rt

    x_conv, r_conv = _convergent(
        rt, convergent_half_angle_deg, chamber_ratio, upstream_radius_ratio, n // 5
    )

    angles = np.linspace(0.0, alpha, max(n // 5, 20))
    x_fillet = fillet * np.sin(angles)
    r_fillet = rt + fillet * (1.0 - np.cos(angles))
    x1, r1 = float(x_fillet[-1]), float(r_fillet[-1])
    if re <= r1:
        raise ValueError(f"ε = {area_ratio:.4g} est trop faible pour ce raccord aval")
    cone_length = (re - r1) / math.tan(alpha)
    x_cone = np.linspace(x1, x1 + cone_length, max(n // 2, 40))
    r_cone = r1 + (x_cone - x1) * math.tan(alpha)

    x = np.concatenate([x_conv[:-1], x_fillet[:-1], x_cone])
    r = np.concatenate([r_conv[:-1], r_fillet[:-1], r_cone])
    return NozzleContour(
        x=x,
        r=r,
        area=math.pi * r**2,
        divergence_lambda=0.5 * (1.0 + math.cos(alpha)),
        divergent_length=float(x[-1]),
        label=f"conique {half_angle_deg:.1f}°",
    )


# Smoothed Rao charts for an 80 %-length bell: inflection angle θn just after
# the throat, and exit angle θe. Interpolated in ε.
_RAO_EPS = np.array([4.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 100.0])
_RAO_THETA_N = np.array([19.5, 20.5, 22.5, 23.3, 24.0, 24.6, 25.0, 25.5, 26.0, 27.4])
_RAO_THETA_E = np.array([16.0, 14.2, 11.4, 10.2, 9.5, 9.0, 8.6, 8.1, 7.7, 6.5])


def rao_angles(area_ratio: float, pct_length: float = 80.0) -> tuple[float, float]:
    """Rao bell angles ``(theta_n, theta_e)`` in degrees.

    A smoothed reading of the classical charts, with a linear empirical
    correction away from the 80 % length they are tabulated at: a shorter bell
    must open faster at the throat (θn up) and has less length left to
    straighten the flow, so it ends up less aligned at the exit (θe up too).
    Both corrections therefore carry the *same* sign against the length. Good
    enough to explore a design space — verify a final design against a real
    Rao / MOC contour.
    """
    if area_ratio < 1.0:
        raise ValueError(f"ε doit être ≥ 1 (reçu {area_ratio})")
    theta_n = float(np.interp(area_ratio, _RAO_EPS, _RAO_THETA_N))
    theta_e = float(np.interp(area_ratio, _RAO_EPS, _RAO_THETA_E))
    k = (pct_length - 80.0) / 80.0
    return theta_n * (1.0 - 0.55 * k), theta_e * (1.0 - 1.10 * k)


def bell_contour(
    throat_radius: float,
    area_ratio: float,
    pct_length: float = 80.0,
    *,
    theta_n_deg: float | None = None,
    theta_e_deg: float | None = None,
    convergent_half_angle_deg: float = 30.0,
    chamber_ratio: float = 2.5,
    upstream_radius_ratio: float = 1.5,
    n: int = 400,
) -> NozzleContour:
    """Rao-type bell: throat arc then a quadratic Bézier (parabolic) skirt.

    ``pct_length`` is the length as a percentage of the 15° cone of the same ε
    — the standard way of quoting a bell. The Bézier control point is the
    intersection of the two tangents, which is what makes the curve leave the
    throat arc at θn and reach the exit at θe.
    """
    if not throat_radius > 0.0:
        raise ValueError(f"le rayon au col doit être > 0 (reçu {throat_radius})")
    if area_ratio <= 1.0:
        raise ValueError(f"ε doit être > 1 pour un galbe (reçu {area_ratio})")
    if not 0.0 < pct_length <= 150.0:
        raise ValueError(f"le pourcentage de longueur doit être dans ]0, 150] (reçu {pct_length})")

    rt = float(throat_radius)
    re = rt * math.sqrt(area_ratio)
    default_n, default_e = rao_angles(area_ratio, pct_length)
    theta_n = math.radians(default_n if theta_n_deg is None else theta_n_deg)
    theta_e = math.radians(default_e if theta_e_deg is None else theta_e_deg)
    if not 0.0 < theta_n < 0.5 * math.pi:
        raise ValueError("θn doit être dans ]0, 90[°")
    if not 0.0 <= theta_e < 0.5 * math.pi:
        raise ValueError("θe doit être dans [0, 90[°")

    cone_length = (re - rt) / math.tan(math.radians(15.0))
    length = pct_length / 100.0 * cone_length

    # Throat arc of radius 0.382·Rt, from 0 to θn (Rao's standard value).
    arc_radius = 0.382 * rt
    angles = np.linspace(0.0, theta_n, max(n // 6, 20))
    x_arc = arc_radius * np.sin(angles)
    r_arc = rt + arc_radius * (1.0 - np.cos(angles))
    nx, ny = float(x_arc[-1]), float(r_arc[-1])
    ex, ey = length, re
    if ex <= nx:
        raise ValueError(
            f"galbe trop court ({pct_length:.0f} %) pour ε = {area_ratio:.4g} : "
            "l'arc de col dépasse déjà la longueur demandée"
        )

    slope_n, slope_e = math.tan(theta_n), math.tan(theta_e)
    if abs(slope_n - slope_e) < 1e-9:
        raise ValueError("θn et θe sont trop proches : la parabole dégénère en droite")
    qx = ((ey - slope_e * ex) - (ny - slope_n * nx)) / (slope_n - slope_e)
    qy = ny + slope_n * (qx - nx)
    if not nx <= qx <= ex:
        raise ValueError(
            "le point de contrôle du galbe tombe hors du segment col-sortie : "
            f"θn = {math.degrees(theta_n):.2f}°, θe = {math.degrees(theta_e):.2f}° et "
            f"une longueur de {pct_length:.0f} % sont incompatibles"
        )

    t = np.linspace(0.0, 1.0, max(n // 2, 60))
    x_bell = (1 - t) ** 2 * nx + 2 * t * (1 - t) * qx + t**2 * ex
    r_bell = (1 - t) ** 2 * ny + 2 * t * (1 - t) * qy + t**2 * ey

    x_conv, r_conv = _convergent(
        rt, convergent_half_angle_deg, chamber_ratio, upstream_radius_ratio, n // 6
    )

    x = np.concatenate([x_conv[:-1], x_arc[:-1], x_bell])
    r = np.concatenate([r_conv[:-1], r_arc[:-1], r_bell])
    return NozzleContour(
        x=x,
        r=r,
        area=math.pi * r**2,
        divergence_lambda=0.5 * (1.0 + math.cos(theta_e)),
        divergent_length=float(length),
        label=f"galbée Rao {pct_length:.0f} %",
        theta_n_deg=math.degrees(theta_n),
        theta_e_deg=math.degrees(theta_e),
    )
