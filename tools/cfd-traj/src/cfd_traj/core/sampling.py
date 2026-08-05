"""Placing points inside a conditional box: levels, corners, Latin hypercubes.

Three primitives, in increasing order of cleverness.

**Levels** span a bound pair with both endpoints included. Including the
endpoints is not cosmetic: the extreme levels of a band are what separate
interpolation from extrapolation on the sizing cases.

**Corners** are the vertices of the conditional box. They matter because a plan
built on the interior alone describes the extreme flight points badly -- and
those are on the oblique frontier of the real tube, not in the corners of the
global hyperrectangle, which is exactly why the box is rebuilt per band.

**Maximin Latin hypercube with rejection** is the alternative when the tensor
grid explodes past four or five grid axes. A plain Latin hypercube would fill
the conditional *box*, most of which the vehicle never visits; the rejection
step keeps only the candidates that have real trajectory points around them,
turning the box back into the tube.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

#: Past this many axes the 2**d vertex enumeration is replaced by an axial
#: skeleton: 2**11 corners would swamp any plan they were meant to bracket.
MAX_CORNER_DIM: int = 10

#: Normalised radius of the empirical-support ball, as a fraction of each
#: conditional bound width. Not exposed in the study file on purpose: it has no
#: standalone physical meaning, and exposing it would invite tuning it until
#: the coverage check passes.
SUPPORT_RADIUS: float = 0.15

#: Minimum number of trajectory points inside that ball for a candidate to be
#: considered "in the tube".
SUPPORT_K_MIN: int = 5

#: Below this first-round acceptance rate the local density has collapsed (the
#: curse of dimensionality on a small lot) and the radius is grown instead of
#: rejecting everything.
MIN_ACCEPTANCE_RATE: float = 0.05

#: Ceiling on that growth: past it, rejection would accept the whole box and
#: degenerate into a plain Latin hypercube, which is what we were avoiding.
MAX_SUPPORT_RADIUS: float = 0.60


def place_levels(
    low: float,
    high: float,
    n: int,
    *,
    log_scaled: bool = False,
    anchors: Sequence[float] = (),
) -> tuple[float, ...]:
    """``n`` levels spanning ``[low, high]``, both endpoints included.

    ``anchors`` are merged in and de-duplicated: they exist for levels that must
    be present for a physical reason (a regime change, a value the vehicle
    spends most of its time at) rather than for regularity.
    """
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    if high < low:
        raise ValueError(f"bounds are inverted: low={low}, high={high}")

    if n == 1:
        base = np.array([0.5 * (low + high)])
    elif log_scaled and low > 0.0:
        base = np.logspace(np.log10(low), np.log10(high), n)
    else:
        base = np.linspace(low, high, n)

    merged = np.concatenate([base, np.asarray(anchors, dtype=np.float64).ravel()])
    merged = merged[(merged >= low - 1e-12) & (merged <= high + 1e-12)]
    merged = np.clip(merged, low, high)
    unique = np.unique(np.round(merged, 12))
    return tuple(float(x) for x in unique)


def corner_points(
    axes: Mapping[str, tuple[float, float]],
) -> tuple[tuple[dict[str, float], ...], tuple[str, ...]]:
    """Vertices of the conditional box, with any notes about a reduced enumeration.

    Up to :data:`MAX_CORNER_DIM` axes, all ``2**d`` vertices. Beyond that, the
    two extreme vertices plus the ``2d`` axial extremes (one axis at a bound,
    the others at their midpoint) -- enough to bracket every axis individually
    without an unusable combinatorial blow-up.
    """
    names = tuple(axes)
    d = len(names)
    if d == 0:
        return ({},), ()

    if d <= MAX_CORNER_DIM:
        vertices = [
            dict(zip(names, combo, strict=True))
            for combo in itertools.product(*(axes[n] for n in names))
        ]
        return tuple(vertices), ()

    mids = {n: 0.5 * (axes[n][0] + axes[n][1]) for n in names}
    vertices = [
        {n: axes[n][0] for n in names},
        {n: axes[n][1] for n in names},
    ]
    for name in names:
        for side in (0, 1):
            point = dict(mids)
            point[name] = axes[name][side]
            vertices.append(point)

    note = (
        f"{d} axes de grille : énumération des coins réduite à "
        f"{len(vertices)} points (2 extrêmes + {2 * d} extrêmes axiaux) "
        f"au lieu de 2**{d}"
    )
    return tuple(vertices), (note,)


def maximin_lhs(
    n_samples: int, n_dim: int, *, rng: np.random.Generator, n_swaps: int = 2000
) -> NDArray[np.float64]:
    """Latin hypercube in ``[0, 1]**d``, improved by greedy maximin swaps.

    The Latin property (one point per stratum on every axis) is preserved by
    construction: swaps exchange two coordinates *within* one dimension.
    """
    if n_samples <= 0:
        raise ValueError(f"n_samples must be positive, got {n_samples}")
    if n_dim <= 0:
        return np.zeros((n_samples, 0), dtype=np.float64)

    design = np.empty((n_samples, n_dim), dtype=np.float64)
    for j in range(n_dim):
        strata = rng.permutation(n_samples)
        design[:, j] = (strata + rng.random(n_samples)) / n_samples

    if n_samples < 2:
        return design

    # The squared-distance matrix is maintained incrementally: a swap only
    # moves two points, so only their two rows and columns change. Rebuilding
    # the whole n x n matrix on each of the thousands of swaps is what makes a
    # naive implementation quadratically slower for no benefit.
    squared = _squared_distances(design)
    best = float(squared.min())

    for _ in range(n_swaps):
        j = int(rng.integers(n_dim))
        a, b = (int(x) for x in rng.choice(n_samples, size=2, replace=False))
        design[[a, b], j] = design[[b, a], j]

        saved_a = squared[a].copy()
        saved_b = squared[b].copy()
        _refresh_rows(squared, design, (a, b))

        candidate = float(squared.min())
        if candidate > best:
            best = candidate
        else:
            design[[a, b], j] = design[[b, a], j]
            squared[a, :] = squared[:, a] = saved_a
            squared[b, :] = squared[:, b] = saved_b
    return design


def _squared_distances(design: NDArray[np.float64]) -> NDArray[np.float64]:
    """Full squared-distance matrix, diagonal set to infinity."""
    diff = design[:, None, :] - design[None, :, :]
    squared = (diff**2).sum(axis=-1)
    np.fill_diagonal(squared, np.inf)
    return np.asarray(squared, dtype=np.float64)


def _refresh_rows(
    squared: NDArray[np.float64], design: NDArray[np.float64], rows: tuple[int, ...]
) -> None:
    """Recompute in place the rows and columns of the points that moved."""
    for i in rows:
        distances = ((design - design[i]) ** 2).sum(axis=1)
        distances[i] = np.inf
        squared[i, :] = distances
        squared[:, i] = distances
    for i in rows:
        squared[i, i] = np.inf


def _min_pairwise_distance(design: NDArray[np.float64]) -> float:
    """Smallest Euclidean distance between two rows."""
    return float(np.sqrt(_squared_distances(design).min()))


@dataclass(frozen=True)
class SupportTest:
    """The "is this point inside the tube?" predicate.

    Holds its own cloud so that the radius can be grown by rebuilding the test
    from the same data (see :func:`lhs_with_rejection`).
    """

    cloud: NDArray[np.float64]
    radius: float = SUPPORT_RADIUS
    k_min: int = SUPPORT_K_MIN

    @property
    def n_cloud(self) -> int:
        """Number of reference points backing the test."""
        return int(self.cloud.shape[0])

    def __call__(self, points: ArrayLike) -> NDArray[np.bool_]:
        pts = np.atleast_2d(np.asarray(points, dtype=np.float64))
        if self.cloud.shape[0] == 0:
            # No cloud to test against: accept, and let the caller's notes say so.
            return np.ones(pts.shape[0], dtype=np.bool_)
        counts = np.empty(pts.shape[0], dtype=np.int64)
        for i, point in enumerate(pts):
            dist = np.sqrt(((self.cloud - point) ** 2).sum(axis=1))
            counts[i] = int(np.count_nonzero(dist <= self.radius))
        return np.asarray(counts >= self.k_min, dtype=np.bool_)

    def with_radius(self, radius: float) -> SupportTest:
        """Same cloud, wider ball."""
        return SupportTest(cloud=self.cloud, radius=radius, k_min=self.k_min)


def empirical_support(
    cloud: ArrayLike, *, radius: float = SUPPORT_RADIUS, k_min: int = SUPPORT_K_MIN
) -> SupportTest:
    """Build the membership predicate of a normalised point cloud.

    ``cloud`` and the points later tested against it must both live in the same
    normalised space (each axis scaled to its own conditional width), so that a
    single radius means the same thing on every axis.
    """
    data = np.atleast_2d(np.asarray(cloud, dtype=np.float64))
    if data.size:
        data = data[np.all(np.isfinite(data), axis=1)]
    return SupportTest(
        cloud=np.ascontiguousarray(data, dtype=np.float64), radius=radius, k_min=k_min
    )


@dataclass(frozen=True)
class LhsResult:
    """Outcome of a rejection-sampled Latin hypercube."""

    design: NDArray[np.float64]
    n_requested: int
    rounds: int
    acceptance_rate: float
    radius: float
    notes: tuple[str, ...] = ()

    @property
    def n_accepted(self) -> int:
        """Number of points actually retained."""
        return int(self.design.shape[0])


def lhs_with_rejection(
    n_samples: int,
    n_dim: int,
    support: SupportTest,
    *,
    rng: np.random.Generator,
    oversample: int = 6,
    max_rounds: int = 20,
) -> LhsResult:
    """Latin hypercube in the unit cube, keeping only the points inside the tube.

    Never fails hard: if the support is too sparse the radius is grown (up to
    :data:`MAX_SUPPORT_RADIUS`), and if that still is not enough the shortfall
    is reported in the notes and the caller decides. Silently returning a
    thinner design than asked for is acceptable; silently returning a design
    that fills the whole box is not, which is why the radius growth is capped
    and reported.
    """
    if n_dim == 0:
        return LhsResult(
            design=np.zeros((0, 0), dtype=np.float64),
            n_requested=n_samples,
            rounds=0,
            acceptance_rate=1.0,
            radius=support.radius,
            notes=(),
        )

    notes: list[str] = []
    radius = support.radius
    accepted: list[NDArray[np.float64]] = []
    n_drawn = 0
    n_kept = 0
    rounds = 0

    while rounds < max_rounds and n_kept < n_samples:
        rounds += 1
        candidates = maximin_lhs(oversample * n_samples, n_dim, rng=rng)
        keep = support(candidates)
        n_drawn += candidates.shape[0]
        n_kept += int(keep.sum())
        if np.any(keep):
            accepted.append(candidates[keep])

        rate = n_kept / max(n_drawn, 1)
        if rounds == 1 and rate < MIN_ACCEPTANCE_RATE and radius < MAX_SUPPORT_RADIUS:
            radius = min(radius * 2.0, MAX_SUPPORT_RADIUS)
            support = support.with_radius(radius)
            notes.append(
                f"densité locale trop faible (taux d'acceptation {rate:.1%}) : "
                f"rayon de support élargi à {radius:.2f}"
            )

    pool = np.vstack(accepted) if accepted else np.zeros((0, n_dim), dtype=np.float64)
    design = _greedy_maximin_subset(pool, n_samples)

    if design.shape[0] < n_samples:
        notes.append(
            f"{design.shape[0]} points intérieurs retenus sur {n_samples} demandés "
            f"(le domaine réellement balayé est plus étroit que le pavé conditionnel)"
        )

    return LhsResult(
        design=design,
        n_requested=n_samples,
        rounds=rounds,
        acceptance_rate=n_kept / max(n_drawn, 1),
        radius=radius,
        notes=tuple(notes),
    )


def _greedy_maximin_subset(pool: NDArray[np.float64], n: int) -> NDArray[np.float64]:
    """Pick ``n`` well-spread rows: start from the most central, then farthest-first."""
    if pool.shape[0] <= n:
        return pool
    centre = pool.mean(axis=0)
    first = int(np.argmin(((pool - centre) ** 2).sum(axis=1)))
    chosen = [first]
    dist = np.sqrt(((pool - pool[first]) ** 2).sum(axis=1))
    for _ in range(n - 1):
        nxt = int(np.argmax(dist))
        chosen.append(nxt)
        dist = np.minimum(dist, np.sqrt(((pool - pool[nxt]) ** 2).sum(axis=1)))
    return np.asarray(pool[np.array(sorted(chosen))], dtype=np.float64)


def scale_to_bounds(
    unit: NDArray[np.float64],
    bounds: Sequence[tuple[float, float]],
    log_scaled: Sequence[bool] | None = None,
) -> NDArray[np.float64]:
    """Map a unit-cube design onto physical bounds, axis by axis."""
    out = np.array(unit, dtype=np.float64, copy=True)
    if out.size == 0:
        return out
    logs = tuple(log_scaled) if log_scaled is not None else (False,) * len(bounds)
    for j, ((low, high), use_log) in enumerate(zip(bounds, logs, strict=True)):
        if use_log and low > 0.0 and high > 0.0:
            out[:, j] = 10.0 ** (np.log10(low) + out[:, j] * (np.log10(high) - np.log10(low)))
        else:
            out[:, j] = low + out[:, j] * (high - low)
    return out
