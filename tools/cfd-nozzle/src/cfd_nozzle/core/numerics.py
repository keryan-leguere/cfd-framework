"""Scalar root finding and maximisation, without SciPy.

cfd-nozzle inverts several strictly monotonic but non-invertible relations
(A/A* → M, ν → M, p02/p01 → M1) and locates one maximum (the θ-β-M detachment
limit). Those are one-dimensional problems on a known bracket, so a guarded
bisection and a golden-section search are enough — and they keep the package
dependent on NumPy alone, like its sibling ``cfd-atm``.
"""

from __future__ import annotations

import math
from collections.abc import Callable

__all__ = ["find_root", "maximise"]


def find_root(
    f: Callable[[float], float],
    a: float,
    b: float,
    *,
    tol: float = 1e-12,
    max_iter: int = 200,
) -> float:
    """Return the zero of ``f`` bracketed by ``[a, b]``.

    Bisection (guaranteed convergence) is combined with a secant step (speed),
    the secant candidate being accepted only when it falls inside the central
    80 % of the current bracket. Without that guard the iteration stalls on the
    very stiff relations of compressible flow — A/A* as M → 0, for instance.

    Raises:
        ValueError: if ``f`` does not change sign over the bracket.
    """
    fa, fb = f(a), f(b)
    if fa == 0.0:
        return a
    if fb == 0.0:
        return b
    if fa * fb > 0.0:
        raise ValueError(
            f"pas de changement de signe sur [{a:g}, {b:g}] : "
            f"f(a) = {fa:g}, f(b) = {fb:g} — solution hors bornes ?"
        )
    for _ in range(max_iter):
        middle = 0.5 * (a + b)
        low, high = min(a, b), max(a, b)
        span = high - low
        if fb != fa:
            secant = b - fb * (b - a) / (fb - fa)
            x = secant if (low + 0.1 * span) <= secant <= (high - 0.1 * span) else middle
        else:
            x = middle
        fx = f(x)
        if fx == 0.0 or abs(b - a) < tol * max(1.0, abs(x)):
            return x
        if fa * fx < 0.0:
            b, fb = x, fx
        else:
            a, fa = x, fx
    return 0.5 * (a + b)


def maximise(
    f: Callable[[float], float],
    a: float,
    b: float,
    *,
    samples: int = 200,
    refine: int = 60,
) -> tuple[float, float]:
    """Return ``(x, f(x))`` at the maximum of a unimodal ``f`` over ``[a, b]``.

    A coarse sweep isolates the bracket, then a golden-section search refines
    it. Used for the maximum deflection of an oblique shock.
    """
    step = (b - a) / (samples - 1)
    xs = [a + i * step for i in range(samples)]
    ys = [f(x) for x in xs]
    k = max(range(samples), key=ys.__getitem__)
    low = xs[max(k - 1, 0)]
    high = xs[min(k + 1, samples - 1)]

    phi = (math.sqrt(5.0) - 1.0) / 2.0
    c, d = high - phi * (high - low), low + phi * (high - low)
    for _ in range(refine):
        if f(c) > f(d):
            high, d = d, c
            c = high - phi * (high - low)
        else:
            low, c = c, d
            d = low + phi * (high - low)
    x = 0.5 * (low + high)
    return x, f(x)
