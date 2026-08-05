"""Understanding a lot before reducing it.

Three things the engineer needs before trusting any plan built on the data:
what is *in* the files (statistics, missing values, consistency between shots),
how the variables move together (correlations), and how many directions the
cloud really occupies (principal components).

That last one is the interesting diagnostic. Along a trajectory Mach, Reynolds
and any altitude-driven parameter are all driven by the same time-altitude
pair, so a five-variable cloud routinely has an intrinsic dimension of two or
three. When it does, conditioning on Mach is capturing the dominant
correlations and the method is on solid ground. When the intrinsic dimension
equals the number of variables, some strong correlation is escaping the
conditioning, and the report says which pair to look at.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from cfd_traj.core.stats import PcaResult, correlation_matrix, pca
from cfd_traj.data.columns import ColumnSpec, Role
from cfd_traj.data.dataset import TrajectoryDataset

#: Below this many active variables a PCA carries no information.
MIN_PCA_VARIABLES: int = 2


@dataclass(frozen=True)
class ColumnStats:
    """Descriptive statistics of one column."""

    name: str
    role: Role
    scale: str
    unit: str
    count: int
    n_nan: int
    n_unique: int
    minimum: float
    q05: float
    median: float
    q95: float
    maximum: float
    mean: float
    std: float

    def as_row(self) -> dict[str, object]:
        """One row of the statistics CSV."""
        return {
            "variable": self.name,
            "role": str(self.role),
            "echelle": self.scale,
            "unite": self.unit,
            "n_valeurs": self.count,
            "n_manquantes": self.n_nan,
            "n_distinctes": self.n_unique,
            "min": self.minimum,
            "q05": self.q05,
            "mediane": self.median,
            "q95": self.q95,
            "max": self.maximum,
            "moyenne": self.mean,
            "ecart_type": self.std,
        }


@dataclass(frozen=True)
class Inspection:
    """Everything ``cfd-traj inspecter`` reports."""

    n_shots: int
    n_rows: int
    n_dropped_rows: int
    time_span: tuple[float, float]
    mach_range: tuple[float, float]
    stats: tuple[ColumnStats, ...]
    correlation: NDArray[np.float64]
    correlation_names: tuple[str, ...]
    pca: PcaResult | None
    consistency: tuple[str, ...] = ()

    @property
    def n_variables(self) -> int:
        """Number of variables that entered the correlation matrix."""
        return len(self.correlation_names)

    def strongest_pairs(self, k: int = 5) -> list[tuple[str, str, float]]:
        """The ``k`` most correlated distinct pairs, strongest first."""
        pairs: list[tuple[str, str, float]] = []
        n = len(self.correlation_names)
        for i in range(n):
            for j in range(i + 1, n):
                pairs.append(
                    (
                        self.correlation_names[i],
                        self.correlation_names[j],
                        float(self.correlation[i, j]),
                    )
                )
        pairs.sort(key=lambda p: -abs(p[2]))
        return pairs[:k]

    @property
    def dimension_is_reduced(self) -> bool:
        """True when the cloud occupies fewer directions than it has variables."""
        return self.pca is not None and self.pca.intrinsic_dimension < self.pca.n_used


def _column_stats(spec: ColumnSpec, values: NDArray[np.float64]) -> ColumnStats:
    """Descriptive statistics of one column, NaN-tolerant."""
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        nan = float("nan")
        return ColumnStats(
            name=spec.name,
            role=spec.role,
            scale=str(spec.scale),
            unit=spec.unit,
            count=0,
            n_nan=int(values.size),
            n_unique=0,
            minimum=nan,
            q05=nan,
            median=nan,
            q95=nan,
            maximum=nan,
            mean=nan,
            std=nan,
        )
    return ColumnStats(
        name=spec.name,
        role=spec.role,
        scale=str(spec.scale),
        unit=spec.unit,
        count=int(finite.size),
        n_nan=int(values.size - finite.size),
        n_unique=int(np.unique(finite).size),
        minimum=float(finite.min()),
        q05=float(np.quantile(finite, 0.05)),
        median=float(np.median(finite)),
        q95=float(np.quantile(finite, 0.95)),
        maximum=float(finite.max()),
        mean=float(finite.mean()),
        std=float(finite.std()),
    )


def _consistency_notes(ds: TrajectoryDataset) -> list[str]:
    """Facts about the lot that deserve a yellow line in the report."""
    notes: list[str] = list(ds.notes)

    non_monotone = [s.name for s in ds.shots if not s.time_is_monotone]
    if non_monotone:
        notes.append(
            f"{len(non_monotone)} tir(s) à temps non strictement croissant : "
            f"{', '.join(non_monotone[:5])}"
        )

    with_nan = [s.name for s in ds.shots if s.n_nan_rows]
    if with_nan:
        notes.append(
            f"{len(with_nan)} tir(s) contenant des valeurs manquantes : {', '.join(with_nan[:5])}"
        )

    lengths = np.array([s.n_rows for s in ds.shots], dtype=np.float64)
    if lengths.size >= 3 and lengths.std() > 0:
        odd = [s.name for s in ds.shots if abs(s.n_rows - lengths.mean()) > 3.0 * lengths.std()]
        if odd:
            notes.append(f"tir(s) de longueur atypique : {', '.join(odd[:5])}")

    return notes


def inspect(
    ds: TrajectoryDataset,
    *,
    specs: Sequence[ColumnSpec],
    pca_threshold: float = 0.95,
    with_pca: bool = True,
) -> Inspection:
    """Describe a lot: statistics, correlations, intrinsic dimension."""
    active = [s for s in specs if s.is_active and s.name in ds.columns]
    stats = tuple(_column_stats(s, ds.values(s.name)) for s in active)

    analysed = [s for s in active if s.role is not Role.MECANIQUE]
    names = tuple(s.name for s in analysed)
    matrix = ds.matrix(names) if names else np.zeros((ds.n_rows, 0))
    correlation, correlation_names = correlation_matrix(matrix, names)

    result: PcaResult | None = None
    if with_pca and len(names) >= MIN_PCA_VARIABLES:
        result = pca(
            matrix,
            names,
            log_mask=[s.log_scaled for s in analysed],
            threshold=pca_threshold,
        )

    return Inspection(
        n_shots=ds.n_shots,
        n_rows=ds.n_rows,
        n_dropped_rows=ds.n_dropped_rows,
        time_span=ds.time_span,
        mach_range=ds.mach_range,
        stats=stats,
        correlation=correlation,
        correlation_names=correlation_names,
        pca=result,
        consistency=tuple(_consistency_notes(ds)),
    )
