"""Coverage: replaying every trajectory point through the finished envelope.

This is the closing check of the method. For each instant of each shot, find
the Mach band and verify that every active variable falls inside that band's
bounds. A point outside is a point the final database would have to
*extrapolate*, and the sizing cases live precisely there.

One honest caveat, and it is the reason this command measures instead of
promising. With the default quantiles (0.1% / 99.9%) about 0.2% of the points
are outside the quantiles by construction, and the 5% margin reabsorbs them *in
general*, not *always*. Only with ``quantile_bas = 0``, ``quantile_haut = 1``
is 100% coverage of the very lot that built the envelope a theorem. So the
result is a measured rate plus a **named list** of the offending shots and
instants, sorted by how far out they are -- a bare percentage is not actionable.

Mechanical variables are excluded from the rate by definition: their declared
range is a superset of anything the trajectory does. They get their own check
instead, and a trajectory value outside a declared mechanical range is a *study
file* error, reported separately.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cfd_traj.data.columns import Role
from cfd_traj.data.dataset import TrajectoryDataset
from cfd_traj.engine.bands import Band
from cfd_traj.engine.envelope import PHI_COLUMN, PHI_DEFINED_COLUMN, Envelope

#: Relative tolerance on each bound, so that a point sitting exactly on a bound
#: counts as covered rather than failing on floating-point noise.
BOUND_TOLERANCE: float = 1e-9


@dataclass(frozen=True)
class Offender:
    """One trajectory point outside the envelope, and by how much."""

    shot: str
    row: int
    time: float
    mach: float
    variable: str
    value: float
    bound: float
    side: str
    excess: float

    def as_row(self) -> dict[str, object]:
        """One row of the offenders CSV."""
        return {
            "tir": self.shot,
            "ligne": self.row,
            "temps": self.time,
            "mach": self.mach,
            "variable": self.variable,
            "valeur": self.value,
            "borne": self.bound,
            "cote": self.side,
            "exces": self.excess,
        }


@dataclass(frozen=True)
class BandCoverage:
    """Coverage of one Mach band."""

    band: Band
    n_points: int
    n_inside: int
    failures_by_variable: dict[str, int]

    @property
    def rate(self) -> float:
        """Fraction of the band's points that fall inside the envelope."""
        return 1.0 if self.n_points == 0 else self.n_inside / self.n_points


@dataclass(frozen=True)
class CoverageResult:
    """Coverage of a whole lot against an envelope."""

    bands: tuple[BandCoverage, ...]
    n_points: int
    n_inside: int
    n_out_of_bands: int
    n_skipped_nan: int
    offenders: tuple[Offender, ...]
    mechanical_violations: tuple[Offender, ...]
    notes: tuple[str, ...] = ()

    @property
    def rate(self) -> float:
        """Overall coverage rate."""
        return 1.0 if self.n_points == 0 else self.n_inside / self.n_points

    @property
    def is_complete(self) -> bool:
        """True only when every point is strictly inside and none fell outside the bands."""
        return self.rate >= 1.0 and self.n_out_of_bands == 0

    def failures_by_variable(self) -> dict[str, int]:
        """Total failures per variable, across every band."""
        out: dict[str, int] = {}
        for band in self.bands:
            for name, count in band.failures_by_variable.items():
                out[name] = out.get(name, 0) + count
        return {k: v for k, v in sorted(out.items(), key=lambda kv: -kv[1]) if v}


def check_coverage(
    ds: TrajectoryDataset, *, envelope: Envelope, max_offenders: int = 20
) -> CoverageResult:
    """Replay a lot through an envelope and report what falls outside."""
    mach = ds.values("Mach")
    time = ds.values("time")
    shots = ds.shot_labels()
    band_index = envelope.band_set.index_of(mach)
    phi_defined = (
        ds.values(PHI_DEFINED_COLUMN).astype(bool)
        if PHI_DEFINED_COLUMN in ds.columns
        else np.ones(ds.n_rows, dtype=bool)
    )

    tested = [
        s
        for s in envelope.specs
        if s.is_active and s.role is not Role.MECANIQUE and s.name in ds.columns
    ]
    mechanical = [
        s
        for s in envelope.specs
        if s.role is Role.MECANIQUE and s.name in ds.columns and s.mechanical_range is not None
    ]

    notes: list[str] = []
    if not tested:
        notes.append("aucune variable testable : la couverture est vide de sens")

    inside_all = np.zeros(ds.n_rows, dtype=bool)
    skipped_nan = np.zeros(ds.n_rows, dtype=bool)
    offenders: list[Offender] = []
    band_results: list[BandCoverage] = []

    for band_env in envelope.bands:
        mask = band_index == band_env.band.index
        n_points = int(mask.sum())
        if n_points == 0:
            band_results.append(
                BandCoverage(band=band_env.band, n_points=0, n_inside=0, failures_by_variable={})
            )
            continue

        ok = np.ones(n_points, dtype=bool)
        nan_here = np.zeros(n_points, dtype=bool)
        failures: dict[str, int] = {}

        for spec in tested:
            variable = band_env.get(spec.name)
            if variable is None:
                continue
            values = ds.values(spec.name)[mask]
            finite = np.isfinite(values)
            nan_here |= ~finite

            within = variable.bounds.contains(values, tol=BOUND_TOLERANCE)
            if spec.name == PHI_COLUMN:
                # An undefined azimuth sits at 0, which is in every domain.
                within |= ~phi_defined[mask]
            within |= ~finite

            bad = ~within
            if np.any(bad):
                failures[spec.name] = int(bad.sum())
                offenders.extend(
                    _offenders_for(
                        spec.name,
                        variable.bounds.low,
                        variable.bounds.high,
                        variable.bounds.width,
                        values,
                        bad,
                        shots[mask],
                        time[mask],
                        mach[mask],
                        np.flatnonzero(mask),
                    )
                )
            ok &= within

        inside_all[mask] = ok
        skipped_nan[mask] = nan_here
        band_results.append(
            BandCoverage(
                band=band_env.band,
                n_points=n_points,
                n_inside=int(ok.sum()),
                failures_by_variable=failures,
            )
        )

    violations: list[Offender] = []
    for spec in mechanical:
        assert spec.mechanical_range is not None
        low, high = spec.mechanical_range
        values = ds.values(spec.name)
        bad = np.isfinite(values) & ((values < low) | (values > high))
        if np.any(bad):
            violations.extend(
                _offenders_for(
                    spec.name,
                    low,
                    high,
                    high - low,
                    values,
                    bad,
                    shots,
                    time,
                    mach,
                    np.arange(ds.n_rows),
                )
            )

    in_bands = band_index >= 0
    n_points = int(in_bands.sum())
    n_inside = int((inside_all & in_bands).sum())
    n_outside_bands = int((~in_bands).sum())
    if n_outside_bands:
        notes.append(
            f"{n_outside_bands} point(s) hors des bandes de Mach : "
            f"ils ne sont couverts par aucune bande"
        )

    offenders.sort(key=lambda o: -o.excess)
    violations.sort(key=lambda o: -o.excess)

    return CoverageResult(
        bands=tuple(band_results),
        n_points=n_points,
        n_inside=n_inside,
        n_out_of_bands=n_outside_bands,
        n_skipped_nan=int((skipped_nan & in_bands).sum()),
        offenders=tuple(offenders[:max_offenders]),
        mechanical_violations=tuple(violations[:max_offenders]),
        notes=tuple(notes),
    )


def _offenders_for(
    name: str,
    low: float,
    high: float,
    width: float,
    values: np.ndarray,
    bad: np.ndarray,
    shots: np.ndarray,
    time: np.ndarray,
    mach: np.ndarray,
    row_indices: np.ndarray,
) -> list[Offender]:
    """Build the offender records for one variable."""
    scale = max(width, 1e-12)
    out: list[Offender] = []
    for i in np.flatnonzero(bad):
        value = float(values[i])
        below = value < low
        bound = low if below else high
        out.append(
            Offender(
                shot=str(shots[i]),
                row=int(row_indices[i]),
                time=float(time[i]),
                mach=float(mach[i]),
                variable=name,
                value=value,
                bound=float(bound),
                side="bas" if below else "haut",
                excess=abs(value - bound) / scale,
            )
        )
    return out
