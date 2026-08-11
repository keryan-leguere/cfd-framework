"""Minimum-length nozzle design by the method of characteristics (MOC).

Compatibility equations
-----------------------
For a steady, isentropic, irrotational supersonic flow, with δ = 0 (planar) or
δ = 1 (axisymmetric) and y the distance to the axis:

    along C⁻, of slope dy/dx = tan(θ − μ):
        d(θ + ν) = + δ · sin μ · sin θ / sin(θ − μ) · dy/y

    along C⁺, of slope dy/dx = tan(θ + μ):
        d(θ − ν) = − δ · sin μ · sin θ / sin(θ + μ) · dy/y

In planar flow (δ = 0) the Riemann invariants K⁻ = θ + ν and K⁺ = θ − ν are
constant. In axisymmetric flow they are **not**: the source term is precisely
what distinguishes the two geometries, and ignoring it is the classic way to
get a wrong bell.

Consequence for the wall
------------------------
In planar flow the region between the last throat characteristic and the wall
is a simple wave — the state is constant along each C⁺, which hands you the
wall points directly. That property is lost in axisymmetric flow, where a wall
supplies only *one* boundary condition (the angle) for *two* unknowns (θ, ν),
so the design problem is ill-posed as such. Hence the classical inverse method
used here:

1. **Kernel** — centred expansion at the sharp throat corner, computed with the
   interior-point and axis-point unit processes alone (no wall needed). θ_max is
   adjusted by bisection until the last axis point reaches exactly M_exit; in
   planar flow this recovers the exact θ_max = ν_e/2.
2. **Exit characteristic** — issued from that axis point, it carries uniform
   flow (θ = 0, M = M_e). That is a valid solution because the source term
   vanishes identically when θ = 0.
3. **Straightening region** — a Goursat problem posed on those two intersecting
   characteristics, fully determined without knowing the wall.
4. **Wall** — the streamline issued from the throat corner, traced through that
   field up to the exit characteristic.

Limits: sharp-cornered throat (centred expansion) and a straight sonic line at
the throat. The real transonic flow there is curved (Sauer correction); a final
design must start from a transonic initial line and a throat fillet.

Validated envelope
------------------
The contour is checked against the ε that A/A*(M_exit) prescribes — the two
must agree, since the design fixes the exit Mach number. Measured departure at
n_char = 40, γ = 1.4:

===============  ==================  ====================
M_exit           planar              axisymmetric
===============  ==================  ====================
1.4 – 2.4        < 0.01 %            < 0.02 %
3.0              0.06 %              0.02 %
4.0              0.32 %              0.03 %
5.0              0.88 %              mesh degenerates
===============  ==================  ====================

Both branches converge monotonically with ``n_char``. Beyond M_exit ≈ 4 in
axisymmetric flow the straightening region grows long enough for the marching
error to degenerate the mesh, and :func:`moc_nozzle` raises a RuntimeError
saying so rather than returning a wrong contour.

See ``00_DOC/04_GEOMETRIES.md``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from cfd_nozzle.core.isentropic import area_ratio, mach_angle
from cfd_nozzle.core.numerics import find_root
from cfd_nozzle.core.shocks import mach_from_prandtl_meyer, nu_max, prandtl_meyer

__all__ = [
    "MOCPoint",
    "MOCResult",
    "check_axisymmetric_compatibility",
    "moc_nozzle",
]

_AXIS_TOL = 1e-12

PointKind = Literal["axis", "internal", "wall", "corner", "exit"]


@dataclass(frozen=True)
class MOCPoint:
    """One node of the characteristics mesh."""

    x: float
    y: float
    theta: float  # flow angle [rad]
    nu: float  # Prandtl-Meyer function [rad]
    mach: float
    mu: float  # Mach angle [rad]
    kind: PointKind


@dataclass(frozen=True)
class MOCResult:
    """Outcome of a minimum-length design.

    Attributes:
        wall_x / wall_y: the divergent contour, throat corner at x = 0.
        wall_points: the same wall, as mesh nodes.
        points: every node computed, for plotting.
        kernel: kernel nodes keyed by ``(i, j)`` — j = 1 on the axis, j = i
            nearest the corner, i numbering the C⁻ lines of the fan.
        transition: the Goursat mesh of the straightening region, ``[k][j]``.
        area_ratio: ε obtained from the contour, (ye/yt)² or ye/yt in planar.
        area_ratio_theory: the ε that A/A*(M_exit) prescribes — the two agreeing
            is the design's self-consistency check.
    """

    wall_x: NDArray[np.float64]
    wall_y: NDArray[np.float64]
    wall_points: list[MOCPoint]
    points: list[MOCPoint]
    kernel: dict[tuple[int, int], MOCPoint]
    transition: list[list[MOCPoint]]
    axisymmetric: bool
    gamma: float
    mach_exit: float
    n_char: int
    y_throat: float
    theta_max_deg: float
    length: float
    y_exit: float
    area_ratio: float
    area_ratio_theory: float
    n_transition: int

    @property
    def area_ratio_error(self) -> float:
        """Relative departure from the theoretical ε [-]."""
        return abs(self.area_ratio / self.area_ratio_theory - 1.0)

    @property
    def label(self) -> str:
        """French description of the geometry."""
        return "axisymétrique" if self.axisymmetric else "plane"


def _nu_inverse(nu: float, gamma: float, guess: float = 0.0) -> float:
    """Invert ν → M by Newton, falling back to bisection. Hot MOC inner loop."""
    if nu <= 0.0:
        return 1.0
    if nu >= nu_max(gamma):
        raise ValueError(
            f"ν = {math.degrees(nu):.3f}° dépasse ν_max = {math.degrees(nu_max(gamma)):.3f}°"
        )
    mach = guess if guess > 1.0000001 else 1.0 + math.sqrt(max(nu, 1e-9))
    for _ in range(60):
        residual = prandtl_meyer(mach, gamma) - nu
        if abs(residual) < 1e-13:
            return mach
        # dν/dM = √(M²−1) / (M · (1 + (γ−1)/2 · M²))
        slope = math.sqrt(mach * mach - 1.0) / (mach * (1.0 + 0.5 * (gamma - 1.0) * mach * mach))
        if slope <= 1e-14:
            break
        updated = mach - residual / slope
        if updated <= 1.0 or not math.isfinite(updated):
            break
        if abs(updated - mach) < 1e-14:
            return updated
        mach = updated
    return mach_from_prandtl_meyer(nu, gamma)


def _make_point(
    x: float, y: float, theta: float, nu: float, gamma: float, kind: PointKind, guess: float = 0.0
) -> MOCPoint:
    mach = _nu_inverse(nu, gamma, guess)
    return MOCPoint(x, y, theta, nu, mach, mach_angle(mach), kind)


def _source_minus(p: MOCPoint, delta: float) -> float:
    """Source coefficient along C⁻: d(θ+ν) = S⁻ · dy."""
    if delta == 0.0 or p.y <= _AXIS_TOL:
        return 0.0
    return delta * math.sin(p.mu) * math.sin(p.theta) / (p.y * math.sin(p.theta - p.mu))


def _source_plus(p: MOCPoint, delta: float) -> float:
    """Source coefficient along C⁺: d(θ−ν) = S⁺ · dy."""
    if delta == 0.0 or p.y <= _AXIS_TOL:
        return 0.0
    return -delta * math.sin(p.mu) * math.sin(p.theta) / (p.y * math.sin(p.theta + p.mu))


def _average_source(sa: float, ya: float, sb: float, yb: float) -> float:
    """Average the two end-of-arc source coefficients.

    On the axis the term is indeterminate (0/0); the off-axis value is then
    kept alone, which amounts to a one-sided scheme.
    """
    if ya <= _AXIS_TOL:
        return sb
    if yb <= _AXIS_TOL:
        return sa
    return 0.5 * (sa + sb)


def _intersect(
    x1: float, y1: float, s1: float, x2: float, y2: float, s2: float
) -> tuple[float, float]:
    """Intersection of two lines given as (point, slope)."""
    if abs(s1 - s2) < 1e-14 or not (math.isfinite(s1) and math.isfinite(s2)):
        raise ValueError("caractéristiques quasi parallèles : maillage dégénéré")
    x = ((y2 - s2 * x2) - (y1 - s1 * x1)) / (s1 - s2)
    return x, y1 + s1 * (x - x1)


# --- unit processes -------------------------------------------------------


def _interior_point(
    p_plus: MOCPoint, p_minus: MOCPoint, gamma: float, delta: float, iterations: int = 4
) -> MOCPoint:
    """Interior node: ``p_plus`` upstream on C⁺, ``p_minus`` upstream on C⁻.

    Predictor-corrector: slopes and source terms are averaged between the two
    ends of each characteristic arc.
    """
    theta = 0.5 * (p_plus.theta + p_minus.theta)
    nu = 0.5 * (p_plus.nu + p_minus.nu)
    mach = _nu_inverse(nu, gamma, 0.5 * (p_plus.mach + p_minus.mach))
    mu = mach_angle(mach)
    x = y = 0.0
    for _ in range(iterations):
        slope_minus = math.tan(0.5 * ((p_minus.theta - p_minus.mu) + (theta - mu)))
        slope_plus = math.tan(0.5 * ((p_plus.theta + p_plus.mu) + (theta + mu)))
        x, y = _intersect(p_minus.x, p_minus.y, slope_minus, p_plus.x, p_plus.y, slope_plus)
        current = MOCPoint(x, y, theta, nu, mach, mu, "internal")
        source_minus = _average_source(
            _source_minus(p_minus, delta), p_minus.y, _source_minus(current, delta), y
        )
        source_plus = _average_source(
            _source_plus(p_plus, delta), p_plus.y, _source_plus(current, delta), y
        )
        k_minus = (p_minus.theta + p_minus.nu) + source_minus * (y - p_minus.y)
        k_plus = (p_plus.theta - p_plus.nu) + source_plus * (y - p_plus.y)
        theta, nu = 0.5 * (k_minus + k_plus), max(0.5 * (k_minus - k_plus), 1e-10)
        mach = _nu_inverse(nu, gamma, mach)
        mu = mach_angle(mach)
    return MOCPoint(x, y, theta, nu, mach, mu, "internal")


def _axis_point(p_minus: MOCPoint, gamma: float, delta: float, iterations: int = 4) -> MOCPoint:
    """Axis node (θ = 0 by symmetry) reached by the C⁻ issued from ``p_minus``."""
    theta = 0.0
    nu = p_minus.theta + p_minus.nu
    mach = _nu_inverse(nu, gamma, p_minus.mach)
    mu = mach_angle(mach)
    x = 0.0
    source = _source_minus(p_minus, delta)  # indeterminate on the axis: one-sided
    for _ in range(iterations):
        slope = math.tan(0.5 * ((p_minus.theta - p_minus.mu) + (theta - mu)))
        x = p_minus.x + (0.0 - p_minus.y) / slope
        nu = max((p_minus.theta + p_minus.nu) + source * (0.0 - p_minus.y), 1e-10)
        mach = _nu_inverse(nu, gamma, mach)
        mu = mach_angle(mach)
    return MOCPoint(x, 0.0, 0.0, nu, mach, mu, "axis")


#: Grading exponent of the expansion fan, θ_i = θ_max·(i/n)^FAN_EXPONENT.
#:
#: A uniform fan (exponent 1) is singular at the sonic corner: the first
#: characteristic leaves at μ → 90°, and the abscissa at which it meets the
#: axis behaves like θ^(1/3), so its derivative is infinite at θ = 0. Refining a
#: uniform fan therefore *destroys* the near-axis mesh instead of improving it —
#: in axisymmetric flow, where the source term is ~1/y, the run then diverges
#: outright. Clustering the fan towards the large angles restores a clean
#: first-order convergence; the exponent 3 exactly compensates the θ^(1/3) law
#: and spreads the first axis points evenly.
FAN_EXPONENT = 3.0


def _kernel(
    theta_max: float,
    n_char: int,
    y_throat: float,
    gamma: float,
    delta: float,
    fan_exponent: float = FAN_EXPONENT,
) -> dict[tuple[int, int], MOCPoint]:
    """Centred expansion fan at the throat corner.

    ``grid[(i, j)]`` is the j-th point of the i-th C⁻ line; j = 1 sits on the
    axis and j = i is the one nearest the corner.
    """
    grid: dict[tuple[int, int], MOCPoint] = {}
    for i in range(1, n_char + 1):
        theta_i = theta_max * (i / n_char) ** fan_exponent
        corner = _make_point(0.0, y_throat, theta_i, theta_i, gamma, "corner")
        for j in range(i, 0, -1):
            p_minus = corner if j == i else grid[(i, j + 1)]
            if j == 1:
                grid[(i, 1)] = _axis_point(p_minus, gamma, delta)
            else:
                grid[(i, j)] = _interior_point(grid[(i - 1, j - 1)], p_minus, gamma, delta)
    return grid


def moc_nozzle(
    mach_exit: float,
    n_char: int = 30,
    y_throat: float = 1.0,
    gamma: float = 1.4,
    *,
    axisymmetric: bool = True,
    fan_exponent: float = FAN_EXPONENT,
    max_lines: int = 4000,
) -> MOCResult:
    """Design a minimum-length nozzle contour by the method of characteristics.

    Args:
        mach_exit: target exit Mach number, uniform and axial at the exit.
        n_char: number of characteristics in the expansion fan. Accuracy grows
            with it, cost grows as its square.
        y_throat: throat radius (axisymmetric) or half-height (planar).
        gamma: ratio of specific heats.
        axisymmetric: True for a body of revolution (δ = 1), False for a planar
            nozzle (δ = 0).
        fan_exponent: grading of the expansion fan, see :data:`FAN_EXPONENT`.
            Leave it alone unless you are studying the discretisation itself.
        max_lines: safety cap on the straightening region.

    Raises:
        ValueError: on an unusable input, or when θ_max cannot be bracketed.
        RuntimeError: if the wall streamline fails to reach the exit
            characteristic within ``max_lines``.
    """
    if mach_exit <= 1.0:
        raise ValueError(f"M_sortie doit être > 1 (reçu {mach_exit})")
    if n_char < 3:
        raise ValueError(f"n_char doit être ≥ 3 (reçu {n_char})")
    if not y_throat > 0.0:
        raise ValueError(f"y_col doit être > 0 (reçu {y_throat})")

    delta = 1.0 if axisymmetric else 0.0
    nu_exit = prandtl_meyer(mach_exit, gamma)

    # --- 1) kernel: θ_max tuned so the last axis point reaches M_exit --------
    def axis_residual(theta_max: float) -> float:
        """ν reached on the axis, minus the target. Monotonic in θ_max.

        Too much corner turning drives the kernel past ν_max, where the gas
        would have expanded to vacuum: that is reported as +∞ rather than an
        exception, so the bracketing below reads it as « trop ouvert » and
        backs off instead of giving up.
        """
        try:
            grid = _kernel(theta_max, n_char, y_throat, gamma, delta, fan_exponent)
        except ValueError:
            return math.inf
        return grid[(n_char, 1)].nu - nu_exit

    if delta == 0.0:
        theta_max = 0.5 * nu_exit  # exact result in planar flow
    else:
        # ν_e/2 is the planar answer and an upper bound: the axisymmetric source
        # term accelerates the axis, so less corner turning is needed. In
        # practice θ_max lands near 0.23·ν_e, hence the low end of the bracket.
        low, high = 0.15 * nu_exit, 0.5 * nu_exit
        f_low = axis_residual(low)
        for _ in range(20):  # the low end must under-expand
            if math.isfinite(f_low) and f_low < 0.0:
                break
            low *= 0.5
            f_low = axis_residual(low)
        f_high = axis_residual(high)
        for _ in range(40):  # the high end must over-expand, without blowing up
            if math.isfinite(f_high) and f_high > 0.0:
                break
            if math.isfinite(f_high):  # not open enough: push the bracket out
                low, f_low = high, f_high
                high = min(high * 1.25, 0.99 * nu_max(gamma))
            else:  # kernel blew up: back off towards the low end
                high = 0.5 * (low + high)
            f_high = axis_residual(high)
        if not (math.isfinite(f_low) and math.isfinite(f_high) and f_low * f_high <= 0.0):
            raise ValueError(
                f"impossible d'encadrer θ_max pour M_sortie = {mach_exit:g} et γ = {gamma:g} : "
                "réduire M_sortie ou augmenter n_char"
            )
        theta_max = find_root(axis_residual, low, high, tol=1e-12)

    def _out_of_envelope(exc: Exception, where: str) -> RuntimeError:
        """Turn a ν overflow into a statement about the design envelope.

        A raw « ν dépasse ν_max » says nothing useful to whoever asked for a
        contour: the mesh has degenerated, which happens on very long
        divergents — beyond roughly M_sortie = 4 in axisymmetric flow with
        γ = 1.4.
        """
        return RuntimeError(
            f"le maillage des caractéristiques dégénère ({where} ; "
            f"M_sortie = {mach_exit:g}, "
            f"{'axisymétrique' if delta else 'plane'}, n_char = {n_char}) : ce point est "
            f"hors du domaine validé de la méthode — concevoir à un M_sortie plus faible, "
            f"ou passer par une géométrie galbée (bell_contour). Cause : {exc}"
        )

    try:
        grid = _kernel(theta_max, n_char, y_throat, gamma, delta, fan_exponent)
    except ValueError as exc:
        raise _out_of_envelope(exc, "noyau de détente") from exc
    exit_axis = grid[(n_char, 1)]  # axis point closing the kernel

    # --- 2) exit characteristic: uniform flow (θ = 0) ------------------------
    mu_exit = mach_angle(mach_exit)
    last_line: list[MOCPoint] = [grid[(n_char, k)] for k in range(1, n_char + 1)]
    last_line.append(_make_point(0.0, y_throat, theta_max, theta_max, gamma, "corner"))
    count = len(last_line)  # = n_char + 1
    spacing = float(
        np.mean(
            [
                math.hypot(
                    last_line[k].x - last_line[k - 1].x, last_line[k].y - last_line[k - 1].y
                )
                for k in range(1, count)
            ]
        )
    )

    # --- 3) straightening region: a Goursat problem --------------------------
    # transition[k][j]: C⁺ number k (issued from last_line[k]) crossed with C⁻
    # number j seeded on the exit characteristic; k = 0 is the exit
    # characteristic itself.
    transition: list[list[MOCPoint]] = [[last_line[k]] for k in range(count)]

    # --- 4) wall = streamline issued from the throat corner ------------------
    wall: list[MOCPoint] = [last_line[count - 1]]
    exit_slope = math.tan(mu_exit)

    def below_exit_characteristic(x: float, y: float) -> bool:
        return y <= exit_axis.y + exit_slope * (x - exit_axis.x) + 1e-12

    j = 0
    finished = False
    while not finished and j < max_lines:
        j += 1
        transition[0].append(
            MOCPoint(
                exit_axis.x + j * spacing * math.cos(mu_exit),
                exit_axis.y + j * spacing * math.sin(mu_exit),
                0.0,
                nu_exit,
                mach_exit,
                mu_exit,
                "exit",
            )
        )
        for k in range(1, count):
            try:
                transition[k].append(
                    _interior_point(transition[k][j - 1], transition[k - 1][j], gamma, delta)
                )
            except ValueError as exc:
                raise _out_of_envelope(exc, "région de redressement") from exc

        # Intersect the streamline with C⁻ number j.
        #
        # The crossing is located by a sign change of the signed distance to
        # the wall ray, walking the polyline from the top down: the topmost
        # node sits above the ray, the one on the exit characteristic below.
        # Locating it by a sign change rather than by a per-segment parametric
        # solve matters — the wall direction is itself refined below, and a
        # refinement step used to be able to push the parameter out of its
        # segment, which silently discarded a perfectly valid crossing and cut
        # the contour short.
        current = wall[-1]
        hit: MOCPoint | None = None
        theta_wall = current.theta
        for _ in range(3):
            slope = math.tan(theta_wall)

            def offset(p: MOCPoint, slope: float = slope, origin: MOCPoint = current) -> float:
                return (p.y - origin.y) - slope * (p.x - origin.x)

            crossing: tuple[int, float] | None = None
            for k in range(count - 1, 0, -1):
                f_upper, f_lower = offset(transition[k][j]), offset(transition[k - 1][j])
                if f_upper == 0.0:
                    crossing = (k, 0.0)
                    break
                if f_upper * f_lower < 0.0:
                    crossing = (k, f_upper / (f_upper - f_lower))
                    break
            if crossing is None:
                hit = None
                break
            k, t = crossing
            upper, lower = transition[k][j], transition[k - 1][j]
            t = min(max(t, 0.0), 1.0)
            theta_hit = upper.theta + t * (lower.theta - upper.theta)
            try:
                hit = _make_point(
                    upper.x + t * (lower.x - upper.x),
                    upper.y + t * (lower.y - upper.y),
                    theta_hit,
                    max(upper.nu + t * (lower.nu - upper.nu), 1e-10),
                    gamma,
                    "wall",
                )
            except ValueError as exc:
                raise _out_of_envelope(exc, "tracé de la paroi") from exc
            theta_wall = 0.5 * (current.theta + theta_hit)
        if hit is not None and hit.x < current.x - 1e-12:
            hit = None

        # Has the streamline reached the exit characteristic? Either the point
        # found lies below it, or no C⁻ crosses it any more.
        if hit is None or below_exit_characteristic(hit.x, hit.y):
            theta_end = current.theta if hit is None else hit.theta
            slope = math.tan(0.5 * (current.theta + theta_end))
            x_wall, y_wall = _intersect(
                current.x, current.y, slope, exit_axis.x, exit_axis.y, exit_slope
            )
            if x_wall < current.x - 1e-9:
                raise RuntimeError("le tracé de la ligne de courant diverge")
            wall.append(_make_point(x_wall, y_wall, 0.0, nu_exit, gamma, "wall"))
            finished = True
        else:
            wall.append(hit)

    if not finished:
        raise RuntimeError(
            "la ligne de courant n'a pas rejoint la caractéristique de sortie : "
            "augmenter max_lines"
        )

    wall_x = np.array([w.x for w in wall], dtype=np.float64)
    wall_y = np.array([w.y for w in wall], dtype=np.float64)
    ratio = (wall_y[-1] / y_throat) ** (2.0 if axisymmetric else 1.0)
    points = list(grid.values()) + [p for line in transition for p in line]
    return MOCResult(
        wall_x=wall_x,
        wall_y=wall_y,
        wall_points=wall,
        points=points,
        kernel=grid,
        transition=transition,
        axisymmetric=axisymmetric,
        gamma=gamma,
        mach_exit=mach_exit,
        n_char=n_char,
        y_throat=y_throat,
        theta_max_deg=math.degrees(theta_max),
        length=float(wall_x[-1]),
        y_exit=float(wall_y[-1]),
        area_ratio=float(ratio),
        area_ratio_theory=area_ratio(mach_exit, gamma),
        n_transition=j,
    )


def check_axisymmetric_compatibility(
    mach: float = 2.0, phi_deg: float = 12.0, gamma: float = 1.4
) -> dict[str, float]:
    """Validate the compatibility relations against the spherical source flow.

    The conical source flow is an exact solution of the axisymmetric equations:
    θ = φ (the polar angle) and A/A* = (r/r*)², whence dν = 2·tan μ · dr/r and,
    along C±, r·dφ/dr = ±tan μ. Substituting those into the compatibility
    relations must return residuals at machine precision — which is the cheapest
    way to prove the δ = 1 source term is written correctly.

    Returns:
        The C⁻ and C⁺ residuals, both expected to be ~0.
    """
    phi = math.radians(phi_deg)
    mu = mach_angle(mach)
    tan_mu = math.tan(mu)
    residuals: dict[str, float] = {}
    for sign, name in ((-1.0, "C-"), (+1.0, "C+")):
        # relative variations taken for dr/r = 1
        d_theta = sign * tan_mu
        d_nu = 2.0 * tan_mu
        left = d_theta - sign * d_nu  # d(θ − sign·ν)
        dy_over_y = 1.0 + (1.0 / math.tan(phi)) * d_theta
        right = -sign * math.sin(mu) * math.sin(phi) / math.sin(phi + sign * mu) * dy_over_y
        residuals[f"résidu {name}"] = left - right
    return residuals
