"""
cfd_plot.dispersion.curve — propagate a dispersion along a sweep.

:mod:`cfd_plot.dispersion.plots` answers "how is *one* dispersed quantity
distributed?".  This module answers the question that actually reaches a
deliverable: "what does my **polar** look like once the coefficients are
dispersed?".  It Monte-Carlo-samples a dispersion at every point of a sweep,
reduces the cloud to an envelope, and hands it to :func:`cfd_plot.plot_with_band`.

    from cfd_plot.dispersion import DispersionSpec, band_from_dispersion, plot_dispersion_band

    band = band_from_dispersion(
        alpha, CN_nominal,
        bias=DispersionSpec(disp_type=5, moy=0.0, var=0.02),
        scale=DispersionSpec(disp_type=6, moy=0.0, var=0.08),
    )
    fig, ax = plt.subplots()
    plot_dispersion_band(ax, band, label="CN")

Correlated vs independent
-------------------------
The distinction matters more than the choice of interval, and getting it wrong
is the classic way to publish a wrong envelope.

A calibration error on a coefficient is normally *the same error* at every
point of a sweep: one realisation shifts or tilts the whole curve coherently.
That is ``correlated=True`` (the default of :func:`band_from_dispersion`), and
its individual realisations are smooth curves.

Drawing an independent error per point instead — ``correlated=False``, and the
only option in :func:`band_from_quantities`, where each point carries its own
specs — models a per-point noise such as an unconverged residual.  Its
realisations are ragged.

The *envelope* comes out similar either way; what changes is what lies inside
it.  Only the correlated envelope can be read as "the true curve lies in
here", which is usually the claim being made.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np

from .. import plot_with_band
from .core import DispersionSpec, QuantityDispersion

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.lines import Line2D

Interval = Literal["percentile", "sigma"]

DEFAULT_N = 20_000


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DispersionBand:
    """A dispersed curve: its nominal, its mean, and an envelope around it.

    Attributes
    ----------
    x:
        Sweep abscissa, shape ``(npts,)``.
    nominal:
        The undispersed curve, shape ``(npts,)``.
    mean:
        Sample mean at each point, shape ``(npts,)``.  It differs from
        *nominal* whenever a dispersion component is off-centre
        (``moy != 0``) — that gap is the bias the analysis reveals.
    low, high:
        Envelope boundaries, shape ``(npts,)``.
    samples:
        The full cloud, shape ``(n, npts)``.  Row *i* is one realisation of
        the whole curve; keeping it lets you re-reduce the band at another
        level, or draw individual realisations, without resampling.
    interval:
        ``"percentile"`` or ``"sigma"`` — how the envelope was reduced.
    level:
        Coverage fraction for ``"percentile"``, or *k* for ``"sigma"``.
    correlated:
        Whether one draw was shared across the sweep (see the module
        docstring).
    """

    x: np.ndarray
    nominal: np.ndarray
    mean: np.ndarray
    low: np.ndarray
    high: np.ndarray
    samples: np.ndarray
    interval: Interval
    level: float
    correlated: bool

    @property
    def n_samples(self) -> int:
        """Number of Monte Carlo realisations."""
        return int(self.samples.shape[0])

    @property
    def std(self) -> np.ndarray:
        """Sample standard deviation at each point, shape ``(npts,)``."""
        return np.std(self.samples, axis=0)

    @property
    def half_width(self) -> np.ndarray:
        """Half the envelope height at each point, shape ``(npts,)``."""
        return 0.5 * (self.high - self.low)

    @property
    def label(self) -> str:
        """Human-readable envelope description, e.g. ``"95 %"`` or ``"±2σ"``."""
        if self.interval == "sigma":
            k = int(self.level) if float(self.level).is_integer() else self.level
            return f"±{k}σ"
        return f"{self.level * 100:.3g} %"

    def reduce(self, *, interval: Interval | None = None, level: float | None = None) -> DispersionBand:
        """Return the same cloud reduced to a different envelope.

        Cheap: no resampling, only the reduction is redone.  Use it to show a
        ±1σ and a ±3σ view of one analysis without paying for it twice.
        """
        interval = interval if interval is not None else self.interval
        if level is None:
            level = self.level if interval == self.interval else _default_level(interval)
        low, high = _reduce(self.samples, interval, level)
        return DispersionBand(
            x=self.x, nominal=self.nominal, mean=self.mean,
            low=low, high=high, samples=self.samples,
            interval=interval, level=level, correlated=self.correlated,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _default_level(interval: Interval) -> float:
    return 0.95 if interval == "percentile" else 2.0


def _reduce(samples: np.ndarray, interval: Interval, level: float) -> tuple[np.ndarray, np.ndarray]:
    """Collapse an ``(n, npts)`` cloud to ``(low, high)`` boundaries."""
    if interval == "percentile":
        if not 0.0 < level < 1.0:
            raise ValueError(f"coverage must lie in (0, 1), got {level!r}")
        tail = 50.0 * (1.0 - level)
        low, high = np.percentile(samples, [tail, 100.0 - tail], axis=0)
        return low, high

    if interval == "sigma":
        if level <= 0.0:
            raise ValueError(f"k must be > 0, got {level!r}")
        mean = np.mean(samples, axis=0)
        half = level * np.std(samples, axis=0)
        return mean - half, mean + half

    raise ValueError(f"interval={interval!r}; use 'percentile' or 'sigma'")


def _resolve_level(interval: Interval, coverage: float | None, k: float | None) -> float:
    """Pick the reduction level, rejecting the knob that does not apply."""
    if interval == "percentile":
        if k is not None:
            raise ValueError("k applies to interval='sigma'; pass coverage= instead")
        return coverage if coverage is not None else 0.95
    if interval == "sigma":
        if coverage is not None:
            raise ValueError("coverage applies to interval='percentile'; pass k= instead")
        return k if k is not None else 2.0
    raise ValueError(f"interval={interval!r}; use 'percentile' or 'sigma'")


def _build(
    x: np.ndarray,
    nominal: np.ndarray,
    samples: np.ndarray,
    *,
    interval: Interval,
    level: float,
    correlated: bool,
) -> DispersionBand:
    low, high = _reduce(samples, interval, level)
    return DispersionBand(
        x=x, nominal=nominal, mean=np.mean(samples, axis=0),
        low=low, high=high, samples=samples,
        interval=interval, level=level, correlated=correlated,
    )


def _as_sweep(x, nominal) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=float)
    nominal = np.asarray(nominal, dtype=float)
    if x.ndim != 1:
        raise ValueError(f"x must be 1-D, got shape {x.shape}")
    if nominal.shape != x.shape:
        raise ValueError(
            f"nominal has {nominal.shape} values for {x.shape} abscissae; they must match"
        )
    return x, nominal


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def band_from_dispersion(
    x,
    nominal,
    *,
    bias: DispersionSpec,
    scale: DispersionSpec,
    n: int = DEFAULT_N,
    interval: Interval = "percentile",
    coverage: float | None = None,
    k: float | None = None,
    correlated: bool = True,
    rng: np.random.Generator | None = None,
) -> DispersionBand:
    """Propagate one bias/scale dispersion pair along a whole sweep.

    The dispersion model is the one of :class:`QuantityDispersion`, applied
    pointwise to a *varying* nominal::

        sample[i, j] = (1 + scale_draw[i]) * nominal[j] + bias_draw[i]

    with the draw index *i* shared across the sweep when ``correlated=True``
    (see the module docstring — this is the physically usual case and the
    default).

    Parameters
    ----------
    x, nominal:
        The undispersed curve.  Both 1-D and the same length.
    bias, scale:
        The additive and multiplicative dispersion components, as in
        :class:`QuantityDispersion`.  A component you do not want is
        ``DispersionSpec(disp_type=1, moy=0, var=0)`` (the "Null" type).
    n:
        Monte Carlo sample count.
    interval:
        ``"percentile"`` (default) reduces the cloud to a coverage interval;
        ``"sigma"`` to mean ± *k*·σ.  Prefer percentiles for uniform or
        truncated components, whose tails are not Gaussian.
    coverage:
        Coverage fraction for ``interval="percentile"``.  Default ``0.95``.
    k:
        Sigma multiple for ``interval="sigma"``.  Default ``2.0``.
    correlated:
        Share one draw across the sweep.  See the module docstring.
    rng:
        Optional :class:`numpy.random.Generator` for reproducibility.  When
        *None*, the legacy global ``np.random`` state is used, so
        ``np.random.seed(...)`` still works.

    Returns
    -------
    DispersionBand
    """
    x, nominal = _as_sweep(x, nominal)
    level = _resolve_level(interval, coverage, k)
    npts = nominal.size

    if correlated:
        b = bias.draw(n, rng=rng)[:, None]
        s = scale.draw(n, rng=rng)[:, None]
    else:
        b = bias.draw(n * npts, rng=rng).reshape(n, npts)
        s = scale.draw(n * npts, rng=rng).reshape(n, npts)

    samples = (1.0 + s) * nominal[None, :] + b
    return _build(x, nominal, samples, interval=interval, level=level, correlated=correlated)


def band_from_quantities(
    x,
    quantities: Sequence[QuantityDispersion],
    *,
    n: int = DEFAULT_N,
    interval: Interval = "percentile",
    coverage: float | None = None,
    k: float | None = None,
    rng: np.random.Generator | None = None,
) -> DispersionBand:
    """Propagate a *per-point* dispersion along a sweep.

    Use this when each point of the sweep carries its own specs — a
    coefficient whose uncertainty grows past stall, say, or a table of
    per-flight-point tolerances.  The nominal curve is read from the
    quantities themselves.

    Sampling is necessarily **independent** point to point: the specs differ,
    so there is no shared draw to correlate through.  If your uncertainty is
    really one calibration error applying to the whole sweep, that is
    :func:`band_from_dispersion` with ``correlated=True`` instead — this
    function would understate how much the curve can shift as a whole.

    Parameters
    ----------
    x:
        Sweep abscissa, same length as *quantities*.
    quantities:
        One :class:`QuantityDispersion` per point, in the order of *x*.

    Returns
    -------
    DispersionBand
    """
    x = np.asarray(x, dtype=float)
    if x.ndim != 1:
        raise ValueError(f"x must be 1-D, got shape {x.shape}")
    if len(quantities) != x.size:
        raise ValueError(
            f"{len(quantities)} quantities for {x.size} abscissae; they must match"
        )

    level = _resolve_level(interval, coverage, k)
    nominal = np.array([float(q.nominal) for q in quantities])
    samples = np.column_stack([q.sample(n, rng=rng) for q in quantities])
    return _build(x, nominal, samples, interval=interval, level=level, correlated=False)


def plot_dispersion_band(
    ax: Axes,
    band: DispersionBand,
    *,
    label: str | None = None,
    band_label: str | None = None,
    color=None,
    show_nominal: bool = True,
    nominal_kwargs: dict | None = None,
    realisations: int = 0,
    realisation_kwargs: dict | None = None,
    band_alpha: float = 0.18,
    marker: str = "",
    **line_kwargs,
) -> dict[str, object]:
    """Draw a :class:`DispersionBand` on *ax*.

    The mean curve carries the envelope; the nominal is overlaid dashed so the
    bias introduced by off-centre components stays visible instead of being
    hidden by the very band that reports it.  When the dispersion is centred
    the two curves coincide, which is itself the useful confirmation.

    Parameters
    ----------
    label:
        Legend entry for the mean curve.
    band_label:
        Legend entry for the envelope.  Defaults to ``band.label``
        (``"95 %"``, ``"±2σ"``, …); pass ``""`` to keep it out of the legend.
    color:
        Colour of the mean curve and the envelope.  Defaults to the cycle.
    show_nominal:
        Overlay the undispersed curve.
    realisations:
        Draw this many individual realisations as faint "spaghetti" behind
        the band.  A dozen is usually enough to show whether realisations are
        smooth (correlated) or ragged (independent) — which is exactly the
        distinction a reader cannot get from the envelope alone.
    marker:
        Marker of the mean curve.  Off by default: a dispersed sweep is a
        model output, not a set of measurements.
    **line_kwargs
        Forwarded to :func:`cfd_plot.plot_with_band` for the mean curve.

    Returns
    -------
    dict
        ``{"line", "band", "nominal", "realisations"}`` — the artists drawn,
        with *nominal* ``None`` when not requested and *realisations* a
        possibly empty list.
    """
    if realisations < 0:
        raise ValueError(f"realisations must be >= 0, got {realisations}")

    if band_label is None:
        band_label = band.label

    # Spaghetti first so the band and the mean curve sit on top of it.
    drawn: list[Line2D] = []
    if realisations:
        rk: dict = dict(color="0.55", lw=0.6, alpha=0.35, zorder=1)
        rk.update(realisation_kwargs or {})
        for row in band.samples[: min(realisations, band.n_samples)]:
            drawn.extend(ax.plot(band.x, row, **rk))

    line, poly = plot_with_band(
        ax, band.x, band.mean,
        y_low=band.low, y_high=band.high,
        band_alpha=band_alpha,
        band_label=band_label or None,
        label=label,
        marker=marker,
        color=color,
        **line_kwargs,
    )

    nominal_line = None
    if show_nominal:
        nk: dict = dict(color=line.get_color(), ls="--", lw=1.0, marker="", zorder=line.get_zorder())
        nk.update(nominal_kwargs or {})
        (nominal_line,) = ax.plot(band.x, band.nominal, **nk)

    return {"line": line, "band": poly, "nominal": nominal_line, "realisations": drawn}


__all__ = [
    "DispersionBand",
    "band_from_dispersion",
    "band_from_quantities",
    "plot_dispersion_band",
]
