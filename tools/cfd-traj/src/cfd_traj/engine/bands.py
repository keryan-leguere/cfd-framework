"""Cutting the Mach axis into bands.

Mach comes first among the parameters because it organises everything else: it
sets the aerodynamic regime, and along a trajectory it drags altitude, Reynolds
and any altitude-driven parameter with it. Every other variable is then bounded
*conditionally* on the band, which is what turns a hugely oversized
hyperrectangle into the tube the vehicle actually flies.

Bands are either declared explicitly in the study file -- the usual case once
the regimes are understood -- or built automatically, tightened around the
transonic crossing where the coefficients move fastest. A band holding too few
points cannot support a meaningful quantile, so it is merged into its neighbour
and the merge is reported rather than silently producing bounds built on five
samples.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import ArrayLike, NDArray

from cfd_traj._compat import pairwise
from cfd_traj.data.study import BandSpec

#: Widened by this fraction of its own width so that the extreme Mach values of
#: the lot fall strictly inside the outer bands rather than on their edge.
EDGE_PADDING: float = 1e-6


@dataclass(frozen=True)
class Band:
    """One Mach band and how many trajectory points fell in it."""

    index: int
    mach_low: float
    mach_high: float
    n_points: int = 0
    is_last: bool = False

    def __post_init__(self) -> None:
        if self.mach_high <= self.mach_low:
            raise ValueError(
                f"bande {self.index} : bornes inversées ({self.mach_low}, {self.mach_high})"
            )

    @property
    def mid(self) -> float:
        """Centre of the band."""
        return 0.5 * (self.mach_low + self.mach_high)

    @property
    def label(self) -> str:
        """French label with a decimal comma, for the reports."""
        low = f"{self.mach_low:.2f}".replace(".", ",")
        high = f"{self.mach_high:.2f}".replace(".", ",")
        return f"M {low}–{high}"

    def contains(self, mach: ArrayLike) -> NDArray[np.bool_]:
        """Half-open membership ``[low, high)``, closed on the last band."""
        values = np.asarray(mach, dtype=np.float64)
        if self.is_last:
            return np.asarray(
                (values >= self.mach_low) & (values <= self.mach_high), dtype=np.bool_
            )
        return np.asarray((values >= self.mach_low) & (values < self.mach_high), dtype=np.bool_)


@dataclass(frozen=True)
class BandSet:
    """The full partition of the Mach axis."""

    bands: tuple[Band, ...]
    edges: tuple[float, ...]
    auto: bool
    notes: tuple[str, ...] = ()

    def __len__(self) -> int:
        return len(self.bands)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.bands)

    @property
    def mach_range(self) -> tuple[float, float]:
        """Extent covered by the partition."""
        return (self.edges[0], self.edges[-1])

    def index_of(self, mach: ArrayLike) -> NDArray[np.int_]:
        """Band index of each Mach value; ``-1`` outside the partition."""
        values = np.asarray(mach, dtype=np.float64)
        out = np.full(values.shape, -1, dtype=np.int_)
        for band in self.bands:
            out = np.where(band.contains(values), band.index, out)
        return out

    def band_of(self, mach: float) -> Band | None:
        """The band containing one Mach value, or None."""
        index = int(self.index_of(np.asarray(mach)))
        return self.bands[index] if index >= 0 else None


def _auto_edges(mach: NDArray[np.float64], spec: BandSpec) -> tuple[float, ...]:
    """Even bands over the observed range, subdivided across the transonic window."""
    low = float(np.min(mach))
    high = float(np.max(mach))
    if high <= low:
        return (low, low + max(abs(low), 1.0) * 1e-3)

    edges = list(np.linspace(low, high, spec.n_bands + 1))
    t_low, t_high = spec.transonic
    refined: list[float] = []
    for a, b in pairwise(edges):
        refined.append(a)
        overlaps = b > t_low and a < t_high
        if overlaps and spec.transonic_refinement > 1:
            refined.extend(np.linspace(a, b, spec.transonic_refinement + 1)[1:-1])
    refined.append(edges[-1])
    return tuple(float(x) for x in np.unique(np.round(refined, 12)))


def _merge_thin_bands(
    edges: tuple[float, ...], mach: NDArray[np.float64], min_points: int
) -> tuple[tuple[float, ...], list[str]]:
    """Drop the internal edges that would leave a band too thin to bound.

    Walks left to right, absorbing each under-populated band into the one
    growing on its left. The last band, having no right-hand neighbour, is
    absorbed backwards instead.
    """
    notes: list[str] = []
    if len(edges) <= 2:
        return edges, notes

    kept = [edges[0]]
    running = 0
    for a, b, is_last in _windows(edges):
        count = int(np.count_nonzero((mach >= a) & ((mach <= b) if is_last else (mach < b))))
        running += count
        if running >= min_points or is_last:
            kept.append(b)
            running = 0
        else:
            notes.append(f"bande M {a:.2f}–{b:.2f} : {count} point(s), fusionnée avec sa voisine")

    if len(kept) >= 3:
        last_count = int(np.count_nonzero(mach >= kept[-2]))
        if last_count < min_points:
            notes.append(
                f"bande M {kept[-2]:.2f}–{kept[-1]:.2f} : {last_count} point(s), "
                f"fusionnée avec sa voisine"
            )
            kept.pop(-2)

    return tuple(kept), notes


def _windows(edges: tuple[float, ...]):  # type: ignore[no-untyped-def]
    """Yield ``(low, high, is_last)`` for each interval of an edge list."""
    pairs = list(pairwise(edges))
    for i, (a, b) in enumerate(pairs):
        yield a, b, i == len(pairs) - 1


def build_bands(mach: ArrayLike, spec: BandSpec) -> BandSet:
    """Partition the Mach axis, from declared edges or automatically."""
    values = np.asarray(mach, dtype=np.float64).ravel()
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        raise ValueError("aucune valeur de Mach exploitable pour construire les bandes")

    notes: list[str] = []
    auto = spec.edges is None

    if spec.edges is not None:
        edges = tuple(float(x) for x in spec.edges)
        outside = int(np.count_nonzero((finite < edges[0]) | (finite > edges[-1])))
        if outside:
            notes.append(
                f"{outside} point(s) de trajectoire hors des bornes déclarées "
                f"[{edges[0]:g}, {edges[-1]:g}]"
            )
    else:
        edges = _auto_edges(finite, spec)
        pad = EDGE_PADDING * max(edges[-1] - edges[0], 1.0)
        edges = (edges[0] - pad, *edges[1:-1], edges[-1] + pad)
        edges, merge_notes = _merge_thin_bands(edges, finite, spec.min_points)
        notes.extend(merge_notes)

    bands: list[Band] = []
    pairs = list(pairwise(edges))
    for i, (low, high) in enumerate(pairs):
        is_last = i == len(pairs) - 1
        empty = Band(index=i, mach_low=low, mach_high=high, is_last=is_last)
        count = int(np.count_nonzero(empty.contains(finite)))
        bands.append(replace(empty, n_points=count))

    return BandSet(bands=tuple(bands), edges=edges, auto=auto, notes=tuple(notes))
