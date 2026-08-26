"""Statistics of the trajectory cloud: robust bounds, principal components, correlations.

Two jobs, both feeding the envelope.

**Robust bounds.** The min and max of a Monte-Carlo lot are carried by a single
extreme draw and move noticeably from one lot to the next; an extreme quantile
does not. Bounds are therefore built on quantiles (0.1% / 99.9% by default)
widened by an outward margin, which absorbs a future change of the dispersion
laws and, more importantly, guarantees that every trajectory point falls in
*strict interpolation* inside the final database rather than on its boundary --
the sizing cases live precisely near the bounds, and a point on the boundary of
the computed domain is an extrapolated point at the first deviation.

The margin is **absolute, proportional to the inter-quantile width**, not
multiplicative on the quantile as one might first write it. A multiplicative
margin does nothing for a variable whose low quantile is near zero, and
actually *shrinks* the domain of a variable whose low bound is negative (a
control deflection, say). Proportional-to-width is the only translation-
invariant choice. For a log-scaled variable the margin is applied in log space,
where it *is* multiplicative in physical space -- so the intuitive behaviour is
recovered exactly where it makes sense.

**Principal components.** Along a trajectory, Mach, Reynolds and any
altitude-driven parameter move together, all three driven by the time-altitude
pair. A PCA of the standardised cloud shows how many directions actually carry
the variance: an intrinsic dimension well below the number of active variables
confirms that conditioning on Mach captures the dominant correlations. If it
does not drop, some strong correlation is escaping the conditioning and the
report says so.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import ArrayLike, NDArray

from cfd_traj._compat import zip_strict

#: A degenerate (zero-width) sample still gets a usable interval this wide,
#: relative to its own magnitude, so downstream level placement never divides
#: by zero.
DEGENERATE_HALF_WIDTH: float = 1e-6

#: A log scale is only meaningful over a wide positive range.
LOG_DECADES_THRESHOLD: float = 100.0


@dataclass(frozen=True)
class Bounds:
    """Conditional bounds of one variable over one band."""

    low: float
    high: float
    q_low_value: float
    q_high_value: float
    median: float
    q_low: float
    q_high: float
    margin: float
    n_points: int
    degenerate: bool = False
    log_scaled: bool = False
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.high < self.low:
            raise ValueError(f"bounds are inverted: low={self.low}, high={self.high}")

    @property
    def width(self) -> float:
        """Width of the interval, always non-negative."""
        return self.high - self.low

    def contains(self, x: ArrayLike, *, tol: float = 1e-9) -> NDArray[np.bool_]:
        """Elementwise membership, with a relative tolerance on each bound."""
        values = np.asarray(x, dtype=np.float64)
        lo_tol = tol * max(1.0, abs(self.low))
        hi_tol = tol * max(1.0, abs(self.high))
        return np.asarray(
            (values >= self.low - lo_tol) & (values <= self.high + hi_tol), dtype=np.bool_
        )


def quantile_bounds(
    values: ArrayLike,
    *,
    q_low: float = 0.001,
    q_high: float = 0.999,
    margin: float = 0.05,
    log_scaled: bool = False,
    physical_min: float | None = None,
) -> Bounds:
    """Robust bounds of a sample: extreme quantiles widened by an outward margin.

    Guarantees ``low <= q_low_value <= median <= q_high_value <= high``.
    NaN values are ignored. An empty or all-NaN sample yields a degenerate
    interval centred on zero rather than an exception: one bad band must not
    stop the study.
    """
    if not 0.0 <= q_low < q_high <= 1.0:
        raise ValueError(f"quantiles must satisfy 0 <= q_low < q_high <= 1, got {q_low}, {q_high}")
    if margin < 0.0:
        raise ValueError(f"margin must be non-negative, got {margin}")

    raw = np.asarray(values, dtype=np.float64).ravel()
    finite = raw[np.isfinite(raw)]
    notes: list[str] = []

    if finite.size == 0:
        return Bounds(
            low=-DEGENERATE_HALF_WIDTH,
            high=DEGENERATE_HALF_WIDTH,
            q_low_value=float("nan"),
            q_high_value=float("nan"),
            median=float("nan"),
            q_low=q_low,
            q_high=q_high,
            margin=margin,
            n_points=0,
            degenerate=True,
            log_scaled=False,
            notes=("aucune valeur finie",),
        )

    use_log = log_scaled
    if use_log and np.any(finite <= 0.0):
        use_log = False
        notes.append("échelle log demandée mais valeurs négatives ou nulles : repli en linéaire")

    work = np.log10(finite) if use_log else finite

    lo_q = float(np.quantile(work, q_low))
    hi_q = float(np.quantile(work, q_high))
    med = float(np.median(work))
    span = hi_q - lo_q

    degenerate = span <= 0.0
    if degenerate:
        half = max(margin, DEGENERATE_HALF_WIDTH) * max(abs(hi_q), 1.0)
        low_w, high_w = lo_q - half, hi_q + half
        notes.append("variable constante sur cette bande")
    else:
        low_w, high_w = lo_q - margin * span, hi_q + margin * span

    if use_log:
        low, high = 10.0**low_w, 10.0**high_w
        lo_val, hi_val, median = 10.0**lo_q, 10.0**hi_q, 10.0**med
    else:
        low, high = low_w, high_w
        lo_val, hi_val, median = lo_q, hi_q, med

    if physical_min is not None and low < physical_min:
        low = physical_min
        if high < low:
            high = low + DEGENERATE_HALF_WIDTH

    return Bounds(
        low=float(low),
        high=float(high),
        q_low_value=float(lo_val),
        q_high_value=float(hi_val),
        median=float(median),
        q_low=q_low,
        q_high=q_high,
        margin=margin,
        n_points=int(finite.size),
        degenerate=degenerate,
        log_scaled=use_log,
        notes=tuple(notes),
    )


def suggest_log_scale(values: ArrayLike) -> bool:
    """True when a variable is positive and spans enough decades to deserve a log scale."""
    finite = np.asarray(values, dtype=np.float64).ravel()
    finite = finite[np.isfinite(finite)]
    if finite.size == 0 or np.any(finite <= 0.0):
        return False
    lo = float(np.min(finite))
    hi = float(np.max(finite))
    return lo > 0.0 and hi / lo >= LOG_DECADES_THRESHOLD


@dataclass(frozen=True)
class PcaResult:
    """Principal component analysis of the standardised cloud."""

    names: tuple[str, ...]
    mean: NDArray[np.float64]
    scale: NDArray[np.float64]
    explained_variance_ratio: NDArray[np.float64]
    cumulative: NDArray[np.float64]
    components: NDArray[np.float64]
    scores: NDArray[np.float64]
    intrinsic_dimension: int
    threshold: float
    n_rows: int
    dropped: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default=())

    @property
    def n_used(self) -> int:
        """Number of variables that actually entered the decomposition."""
        return len(self.names)


def pca(
    matrix: ArrayLike,
    names: Sequence[str],
    *,
    log_mask: Sequence[bool] | None = None,
    threshold: float = 0.95,
) -> PcaResult:
    """Standardised PCA by SVD. No scikit-learn: numpy is enough and always present.

    Rows containing a NaN are dropped, as are constant columns (they carry no
    variance and would divide by zero on standardisation); both are reported.
    Component signs are normalised so that the largest loading of each axis is
    positive, which makes biplots comparable from one lot to the next.
    """
    if not 0.0 < threshold <= 1.0:
        raise ValueError(f"threshold must be in (0, 1], got {threshold}")

    data = np.atleast_2d(np.asarray(matrix, dtype=np.float64))
    names = tuple(names)
    if data.shape[1] != len(names):
        raise ValueError(f"matrix has {data.shape[1]} columns but {len(names)} names were given")

    notes: list[str] = []
    if log_mask is not None:
        mask = np.asarray(log_mask, dtype=bool)
        if mask.size != data.shape[1]:
            raise ValueError("log_mask length does not match the number of columns")
        data = data.copy()
        for j in np.flatnonzero(mask):
            column = data[:, j]
            positive = np.isfinite(column) & (column > 0)
            data[:, j] = np.where(positive, np.log10(np.where(positive, column, 1.0)), np.nan)

    keep_rows = np.all(np.isfinite(data), axis=1)
    data = data[keep_rows]
    n_rows = int(data.shape[0])

    std = data.std(axis=0, ddof=0) if n_rows > 0 else np.zeros(len(names))
    keep_cols = std > 0.0
    dropped = tuple(n for n, k in zip_strict(names, keep_cols) if not k)
    if dropped:
        notes.append(f"variable(s) constante(s) écartée(s) : {', '.join(dropped)}")

    kept_names = tuple(n for n, k in zip_strict(names, keep_cols) if k)
    data = data[:, keep_cols]
    p = data.shape[1]

    if n_rows < 2 or p == 0:
        notes.append("effectif insuffisant pour une ACP")
        empty = np.zeros((0,), dtype=np.float64)
        return PcaResult(
            names=kept_names,
            mean=np.zeros(p),
            scale=np.ones(p),
            explained_variance_ratio=empty,
            cumulative=empty,
            components=np.zeros((0, p)),
            scores=np.zeros((n_rows, 0)),
            intrinsic_dimension=0,
            threshold=threshold,
            n_rows=n_rows,
            dropped=dropped,
            notes=tuple(notes),
        )

    mean = data.mean(axis=0)
    scale = data.std(axis=0, ddof=0)
    standardised = (data - mean) / scale

    _, singular, vt = np.linalg.svd(standardised, full_matrices=False)
    eigenvalues = singular**2 / (n_rows - 1)
    total = float(eigenvalues.sum())
    ratio = eigenvalues / total if total > 0 else np.zeros_like(eigenvalues)
    cumulative = np.cumsum(ratio)

    # Sign normalisation: make the dominant loading of every axis positive.
    signs = np.sign(vt[np.arange(vt.shape[0]), np.argmax(np.abs(vt), axis=1)])
    signs[signs == 0] = 1.0
    components = vt * signs[:, None]
    scores = standardised @ components.T

    reached = np.flatnonzero(cumulative >= threshold - 1e-12)
    intrinsic = int(reached[0]) + 1 if reached.size else int(components.shape[0])

    return PcaResult(
        names=kept_names,
        mean=mean,
        scale=scale,
        explained_variance_ratio=ratio,
        cumulative=cumulative,
        components=components,
        scores=scores,
        intrinsic_dimension=intrinsic,
        threshold=threshold,
        n_rows=n_rows,
        dropped=dropped,
        notes=tuple(notes),
    )


def correlation_matrix(
    matrix: ArrayLike, names: Sequence[str]
) -> tuple[NDArray[np.float64], tuple[str, ...]]:
    """Pearson correlation of the columns, NaN rows dropped.

    Constant columns keep a correlation of 0 with everything and 1 with
    themselves, rather than producing NaN that would poison the display.
    """
    data = np.atleast_2d(np.asarray(matrix, dtype=np.float64))
    names = tuple(names)
    if data.shape[1] != len(names):
        raise ValueError(f"matrix has {data.shape[1]} columns but {len(names)} names were given")

    data = data[np.all(np.isfinite(data), axis=1)]
    p = len(names)
    out = np.eye(p, dtype=np.float64)
    if data.shape[0] < 2:
        return out, names

    std = data.std(axis=0, ddof=0)
    usable = std > 0.0
    if usable.sum() >= 2:
        sub = np.corrcoef(data[:, usable], rowvar=False)
        idx = np.flatnonzero(usable)
        out[np.ix_(idx, idx)] = np.nan_to_num(sub, nan=0.0)
    np.fill_diagonal(out, 1.0)
    return out, names


def spearman(x: ArrayLike, y: ArrayLike) -> float:
    """Spearman rank correlation, NaN-tolerant. Returns 0 when it is undefined."""
    a = np.asarray(x, dtype=np.float64).ravel()
    b = np.asarray(y, dtype=np.float64).ravel()
    if a.size != b.size:
        raise ValueError(f"lengths differ: {a.size} vs {b.size}")
    keep = np.isfinite(a) & np.isfinite(b)
    a, b = a[keep], b[keep]
    if a.size < 3:
        return 0.0
    from scipy.stats import spearmanr

    rho = spearmanr(a, b).statistic
    return 0.0 if not np.isfinite(rho) else float(rho)
