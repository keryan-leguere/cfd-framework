"""The conditional envelope: what the vehicle actually flies, band by band.

Knowing the min and max of every variable defines a hyperrectangle. That domain
is doubly defective. It is far too big -- it contains every unreachable cross
combination, maximum Mach together with the start-of-flight value of a
parameter, maximum incidence outside the phase where it occurs -- and in four
or five dimensions the real tube typically occupies a few percent of its
volume, so a plan spread over it wastes most of its budget on points the
vehicle never meets. And it is *wrong about the extremes*: the corners of the
hyperrectangle are reached by no trajectory, so a plan resting on them
describes the genuine extreme points, which lie on the oblique frontier of the
tube, worse rather than better.

The fix is to bound every variable *conditionally on the Mach band*. This
module builds that table -- roughly ten rows, readable line by line by a flight
mechanic in a design review, and directly translatable into computation cases.

Roles are honoured here: ``mecanique`` variables take their declared mechanical
range in every band (never the trajectory range, which would make the database
circular), ``phi_fold`` takes the levels imposed by the symmetry group, and
``ignore`` variables are absent.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from cfd_traj.core.sampling import place_levels
from cfd_traj.core.stats import Bounds, quantile_bounds
from cfd_traj.core.symmetry import SymmetrySpec, azimuth_levels
from cfd_traj.data.columns import ColumnSpec, Role
from cfd_traj.data.dataset import TrajectoryDataset
from cfd_traj.data.study import EnvelopeSpec
from cfd_traj.engine.bands import Band, BandSet

#: Name of the folded azimuth, whose levels come from the group, not from data.
PHI_COLUMN: str = "phi_fold"

#: Rows where the azimuth is undefined must not enter its quantiles.
PHI_DEFINED_COLUMN: str = "phi_defined"

#: The conditioning variable. Its bounds inside a band are the band itself, not
#: a quantile of the values it holds: the band edges are exact by construction,
#: and widening them by a margin would place nodes at a Mach number belonging
#: to no band at all, and would make adjacent bands overlap ambiguously.
MACH_COLUMN: str = "Mach"


@dataclass(frozen=True)
class VariableEnvelope:
    """Bounds and levels of one variable over one band."""

    spec: ColumnSpec
    bounds: Bounds
    levels: tuple[float, ...]

    @property
    def name(self) -> str:
        """Column name."""
        return self.spec.name

    @property
    def role(self) -> Role:
        """Role of the variable."""
        return self.spec.role


@dataclass(frozen=True)
class BandEnvelope:
    """Every variable's bounds over one band."""

    band: Band
    variables: tuple[VariableEnvelope, ...]
    n_points: int
    warnings: tuple[str, ...] = ()

    def get(self, name: str) -> VariableEnvelope | None:
        """One variable by name, or None."""
        return next((v for v in self.variables if v.name == name), None)

    def grid_variables(self) -> tuple[VariableEnvelope, ...]:
        """The variables that define the conditional box (phi excluded)."""
        return tuple(v for v in self.variables if v.spec.is_grid_axis and v.name != PHI_COLUMN)

    def axes(self) -> dict[str, tuple[float, float]]:
        """The conditional box, as an axis-name to bound-pair mapping."""
        return {v.name: (v.bounds.low, v.bounds.high) for v in self.grid_variables()}

    def contains(self, values: dict[str, float], *, tol: float = 1e-9) -> bool:
        """True when every named value falls inside this band's bounds."""
        for name, value in values.items():
            variable = self.get(name)
            if variable is None or variable.spec.role is Role.MECANIQUE:
                continue
            if not bool(variable.bounds.contains(np.asarray(value), tol=tol)):
                return False
        return True


@dataclass(frozen=True)
class Envelope:
    """The whole conditional envelope of a study."""

    bands: tuple[BandEnvelope, ...]
    band_set: BandSet
    specs: tuple[ColumnSpec, ...]
    spec: EnvelopeSpec
    symmetry: SymmetrySpec
    notes: tuple[str, ...] = ()

    @property
    def active_names(self) -> tuple[str, ...]:
        """Names of every variable carried by the envelope, in spec order."""
        return tuple(s.name for s in self.specs if s.is_active)

    @property
    def tested_names(self) -> tuple[str, ...]:
        """Variables the coverage check applies to (mechanical ones excluded)."""
        return tuple(s.name for s in self.specs if s.is_active and s.role is not Role.MECANIQUE)

    def band_of(self, mach: float) -> BandEnvelope | None:
        """The band envelope containing one Mach value, or None."""
        band = self.band_set.band_of(mach)
        return self.bands[band.index] if band is not None else None

    def table_rows(self) -> list[dict[str, object]]:
        """The envelope table: one row per (band, variable)."""
        rows: list[dict[str, object]] = []
        for band_env in self.bands:
            for variable in band_env.variables:
                rows.append(
                    {
                        "bande": band_env.band.index,
                        "mach_bas": band_env.band.mach_low,
                        "mach_haut": band_env.band.mach_high,
                        "n_points": band_env.n_points,
                        "variable": variable.name,
                        "role": str(variable.spec.role),
                        "echelle": str(variable.spec.scale),
                        "borne_basse": variable.bounds.low,
                        "quantile_bas": variable.bounds.q_low_value,
                        "mediane": variable.bounds.median,
                        "quantile_haut": variable.bounds.q_high_value,
                        "borne_haute": variable.bounds.high,
                        "n_niveaux": len(variable.levels),
                        "niveaux": " ".join(f"{x:.6g}" for x in variable.levels),
                    }
                )
        return rows


def _fixed_bounds(low: float, high: float, values: NDArray[np.float64]) -> Bounds:
    """Bounds imposed by construction rather than measured from the data."""
    return Bounds(
        low=low,
        high=max(high, low + 1e-12),
        q_low_value=low,
        q_high_value=high,
        median=0.5 * (low + high),
        q_low=0.0,
        q_high=1.0,
        margin=0.0,
        n_points=int(np.count_nonzero(np.isfinite(values))),
    )


def _variable_envelope(
    spec: ColumnSpec,
    values: NDArray[np.float64],
    envelope_spec: EnvelopeSpec,
    symmetry: SymmetrySpec,
    band: Band,
) -> tuple[VariableEnvelope, tuple[str, ...]]:
    """Bounds and levels of one variable over one band."""
    warnings: list[str] = []

    if spec.name == MACH_COLUMN:
        low, high = band.mach_low, band.mach_high
        return VariableEnvelope(
            spec=spec,
            bounds=_fixed_bounds(low, high, values),
            levels=place_levels(low, high, spec.n_levels),
        ), ()

    if spec.role is Role.MECANIQUE:
        assert spec.mechanical_range is not None  # guaranteed by ColumnSpec
        low, high = spec.mechanical_range
        return VariableEnvelope(
            spec=spec,
            bounds=_fixed_bounds(low, high, values),
            levels=place_levels(low, high, spec.n_levels),
        ), ()

    if spec.name == PHI_COLUMN:
        low, high = symmetry.fundamental_domain_deg
        return VariableEnvelope(
            spec=spec,
            bounds=_fixed_bounds(low, high, values),
            levels=azimuth_levels(symmetry),
        ), ()

    bounds = quantile_bounds(
        values,
        q_low=spec.q_low if spec.q_low is not None else envelope_spec.q_low,
        q_high=spec.q_high if spec.q_high is not None else envelope_spec.q_high,
        margin=spec.margin if spec.margin is not None else envelope_spec.margin,
        log_scaled=spec.log_scaled,
        physical_min=spec.physical_min,
    )
    warnings.extend(f"« {spec.name} » : {note}" for note in bounds.notes)

    if spec.role is Role.DISCRET:
        distinct = np.unique(values[np.isfinite(values)])
        levels = (
            tuple(float(x) for x in distinct)
            if 0 < distinct.size <= spec.n_levels
            else place_levels(bounds.low, bounds.high, spec.n_levels, log_scaled=bounds.log_scaled)
        )
    else:
        levels = place_levels(bounds.low, bounds.high, spec.n_levels, log_scaled=bounds.log_scaled)

    return VariableEnvelope(spec=spec, bounds=bounds, levels=levels), tuple(warnings)


def build_envelope(
    ds: TrajectoryDataset,
    *,
    band_set: BandSet,
    specs: Sequence[ColumnSpec],
    spec: EnvelopeSpec,
    symmetry: SymmetrySpec,
) -> Envelope:
    """Build the conditional envelope of a lot, band by band."""
    active = tuple(s for s in specs if s.is_active)
    mach = ds.values("Mach")
    band_index = band_set.index_of(mach)
    phi_defined = (
        ds.values(PHI_DEFINED_COLUMN).astype(bool)
        if PHI_DEFINED_COLUMN in ds.columns
        else np.ones(ds.n_rows, dtype=bool)
    )

    notes: list[str] = list(band_set.notes)
    outside = int(np.count_nonzero(band_index < 0))
    if outside:
        notes.append(f"{outside} point(s) hors des bandes de Mach, exclus de l'enveloppe")

    band_envelopes: list[BandEnvelope] = []
    for band in band_set.bands:
        mask = band_index == band.index
        warnings: list[str] = []
        variables: list[VariableEnvelope] = []

        for column in active:
            values = ds.values(column.name)[mask]
            if column.name == PHI_COLUMN:
                # An arbitrary azimuth at zero incidence must not shift the bounds.
                values = values[phi_defined[mask]]
            variable, variable_warnings = _variable_envelope(column, values, spec, symmetry, band)
            variables.append(variable)
            warnings.extend(variable_warnings)

        if int(mask.sum()) < 3:
            warnings.append(
                f"seulement {int(mask.sum())} point(s) dans cette bande : "
                f"bornes peu représentatives"
            )

        band_envelopes.append(
            BandEnvelope(
                band=band,
                variables=tuple(variables),
                n_points=int(mask.sum()),
                warnings=tuple(warnings),
            )
        )

    return Envelope(
        bands=tuple(band_envelopes),
        band_set=band_set,
        specs=tuple(specs),
        spec=spec,
        symmetry=symmetry,
        notes=tuple(notes),
    )
