"""Building the design of experiments from the conditional envelope.

A full tensor grid over every parameter is out of reach: ten levels on five
dimensions is ten million cases. What makes the plan affordable is that it is
built **band by band**, so the levels of each band sit between *that band's*
conditional bounds and the unreachable cross combinations are simply never
generated; and that each node is assigned the **smallest computational domain
its symmetry allows**, so the plan is costed in full-configuration equivalents
rather than in raw case counts.

Two placement methods. ``tensoriel`` is the primary one -- an anisotropic
tensor product of the per-band levels, with the corners of the conditional box
included explicitly because they are what separates strict interpolation from
extrapolation on the sizing cases. ``lhs`` is the alternative for when the
tensor grid explodes past four or five grid axes: a maximin Latin hypercube
rejected onto the band's own point cloud, so it fills the tube rather than the
box. The corners are added unconditionally to *both*.

The node count is computed before anything is allocated. A plan that would
exceed ``noeuds_max`` stops there and says so: materialising two hundred
thousand nodes to then report that there are too many of them helps nobody.
"""

from __future__ import annotations

import enum
import itertools
from dataclasses import dataclass

import numpy as np
import pandas as pd

from cfd_traj.core.sampling import (
    corner_points,
    empirical_support,
    lhs_with_rejection,
    scale_to_bounds,
)
from cfd_traj.core.symmetry import (
    CalcConfig,
    SymmetrySpec,
    calc_config,
    relative_cost,
    zero_components,
)
from cfd_traj.data.columns import DEFLECTION_COLUMNS, Role
from cfd_traj.data.dataset import TrajectoryDataset
from cfd_traj.data.plan_io import plan_columns
from cfd_traj.data.study import DeflectionSet, DoeMethod, DoeSpec
from cfd_traj.engine.envelope import PHI_COLUMN, BandEnvelope, Envelope

#: Column carrying the total incidence, needed to pick the computational domain.
ALPHA_COLUMN: str = "alpha_tot"


class PlanTooLarge(ValueError):
    """The requested plan exceeds the declared node ceiling."""

    def __init__(self, requested: int, ceiling: int) -> None:
        self.requested = requested
        self.ceiling = ceiling
        super().__init__(
            f"le plan demanderait {requested} nœuds pour un plafond de {ceiling} "
            f"(« doe.noeuds_max »)"
        )


class NodeOrigin(enum.StrEnum):
    """Why a node is in the plan."""

    GRILLE = "grille"
    COIN = "coin"
    LHS = "lhs"


@dataclass(frozen=True)
class DoeNode:
    """One computation case."""

    node_id: str
    band_index: int
    mach_low: float
    mach_high: float
    values: dict[str, float]
    deflection: DeflectionSet
    origin: NodeOrigin
    calc_config: CalcConfig
    relative_cost: float
    zero_components: tuple[str, ...]

    @property
    def is_corner(self) -> bool:
        """True for the vertices of the conditional box."""
        return self.origin is NodeOrigin.COIN

    def as_row(self) -> dict[str, object]:
        """One tidy row of the plan CSV."""
        return {
            "node_id": self.node_id,
            "bande": self.band_index,
            "mach_bas": self.mach_low,
            "mach_haut": self.mach_high,
            **self.values,
            "braquage": self.deflection.name,
            "dl": self.deflection.dl,
            "dm": self.deflection.dm,
            "dn": self.deflection.dn,
            "configuration": str(self.calc_config),
            "cout_relatif": self.relative_cost,
            "composantes_nulles": " ".join(self.zero_components),
            "origine": str(self.origin),
        }


@dataclass(frozen=True)
class DoePlan:
    """A whole design of experiments."""

    nodes: tuple[DoeNode, ...]
    envelope: Envelope
    method: DoeMethod
    seed: int
    variable_names: tuple[str, ...]
    notes: tuple[str, ...] = ()

    @property
    def n_nodes(self) -> int:
        """Number of computation cases."""
        return len(self.nodes)

    @property
    def total_cost(self) -> float:
        """Cost of the plan, in full-configuration equivalents."""
        return float(sum(n.relative_cost for n in self.nodes))

    @property
    def naive_cost(self) -> float:
        """What the plan would cost with every case on the full configuration."""
        return float(self.n_nodes)

    @property
    def saving(self) -> float:
        """Fraction of the naive cost saved by the symmetry reduction."""
        return 0.0 if self.n_nodes == 0 else 1.0 - self.total_cost / self.naive_cost

    def cost_by_config(self) -> dict[CalcConfig, tuple[int, float]]:
        """Case count and cost for each computational domain."""
        out: dict[CalcConfig, tuple[int, float]] = {}
        for node in self.nodes:
            count, cost = out.get(node.calc_config, (0, 0.0))
            out[node.calc_config] = (count + 1, cost + node.relative_cost)
        return out

    def nodes_of_band(self, index: int) -> tuple[DoeNode, ...]:
        """Every node of one band."""
        return tuple(n for n in self.nodes if n.band_index == index)

    def column_names(self) -> tuple[str, ...]:
        """Column order of the plan CSV."""
        return plan_columns(self.variable_names)

    def to_frame(self) -> pd.DataFrame:
        """The plan as a tidy frame."""
        frame = pd.DataFrame([n.as_row() for n in self.nodes])
        if frame.empty:
            return pd.DataFrame(columns=list(self.column_names()))
        return frame[list(self.column_names())]

    def to_yaml_payload(self) -> dict[str, object]:
        """The plan grouped by band, for the YAML export."""
        return {
            "methode": str(self.method),
            "graine": self.seed,
            "n_noeuds": self.n_nodes,
            "cout_total": round(self.total_cost, 4),
            "bandes": [
                {
                    "indice": band.band.index,
                    "mach": [band.band.mach_low, band.band.mach_high],
                    "noeuds": [n.as_row() for n in self.nodes_of_band(band.band.index)],
                }
                for band in self.envelope.bands
            ],
        }


def _discrete_levels(band: BandEnvelope) -> dict[str, tuple[float, ...]]:
    """Discrete factors and their levels, applied by superposition, not by grid."""
    return {v.name: v.levels for v in band.variables if v.spec.role is Role.DISCRET}


def _grid_points(band: BandEnvelope) -> list[dict[str, float]]:
    """The tensor product of the band's grid-axis levels."""
    variables = band.grid_variables()
    if not variables:
        return [{}]
    names = [v.name for v in variables]
    return [
        dict(zip(names, combo, strict=True))
        for combo in itertools.product(*(v.levels for v in variables))
    ]


def _lhs_points(
    band: BandEnvelope, doe: DoeSpec, ds: TrajectoryDataset | None, rng: np.random.Generator
) -> tuple[list[dict[str, float]], tuple[str, ...]]:
    """Latin-hypercube points inside the band's own cloud."""
    variables = band.grid_variables()
    if not variables:
        return [{}], ()

    names = [v.name for v in variables]
    bounds = [(v.bounds.low, v.bounds.high) for v in variables]
    logs = [v.bounds.log_scaled for v in variables]

    cloud = np.zeros((0, len(names)), dtype=np.float64)
    if ds is not None:
        mask = band.band.contains(ds.values("Mach"))
        raw = ds.matrix(names)[mask]
        widths = np.array([max(hi - lo, 1e-12) for lo, hi in bounds])
        lows = np.array([lo for lo, _ in bounds])
        cloud = (raw - lows) / widths
        cloud = cloud[np.all(np.isfinite(cloud), axis=1)]

    support = empirical_support(cloud)
    result = lhs_with_rejection(doe.n_lhs_per_band, len(names), support, rng=rng)
    scaled = scale_to_bounds(result.design, bounds, logs)

    notes = tuple(f"bande {band.band.index} : {note}" for note in result.notes)
    return [dict(zip(names, row, strict=True)) for row in scaled], notes


def _theoretical_count(envelope: Envelope, doe: DoeSpec, symmetry: SymmetrySpec) -> int:
    """Node count the plan would reach, computed before anything is allocated."""
    n_phi = len(azimuth_levels_of(envelope, symmetry))
    n_deflections = len(doe.deflections)
    total = 0
    for band in envelope.bands:
        if doe.method is DoeMethod.TENSORIEL:
            per_band = 1
            for variable in band.grid_variables():
                per_band *= max(len(variable.levels), 1)
        else:
            per_band = doe.n_lhs_per_band
        if doe.include_corners:
            axes = band.axes()
            per_band += 2 ** len(axes) if len(axes) <= 10 else 2 + 2 * len(axes)
        total += per_band * n_phi * n_deflections
    return total


def azimuth_levels_of(envelope: Envelope, symmetry: SymmetrySpec) -> tuple[float, ...]:
    """The azimuth levels of the plan, from the envelope or the group."""
    for band in envelope.bands:
        variable = band.get(PHI_COLUMN)
        if variable is not None:
            return variable.levels
    from cfd_traj.core.symmetry import azimuth_levels

    return azimuth_levels(symmetry)


def build_plan(
    envelope: Envelope,
    *,
    doe: DoeSpec,
    symmetry: SymmetrySpec,
    ds: TrajectoryDataset | None = None,
) -> DoePlan:
    """Build the plan. Raises :class:`PlanTooLarge` before allocating anything."""
    requested = _theoretical_count(envelope, doe, symmetry)
    if requested > doe.max_nodes:
        raise PlanTooLarge(requested, doe.max_nodes)

    phi_levels = azimuth_levels_of(envelope, symmetry)
    notes: list[str] = []
    nodes: list[DoeNode] = []

    # The three deflection columns are carried by the deflection block
    # (« braquage », dl, dm, dn) at the end of every row, so they must not also
    # appear among the variable columns -- a plan with two « dl » columns is
    # not readable by anything. Any *other* mechanical column is a genuine
    # variable and keeps its place, sampled over its declared range.
    variable_names = tuple(
        name
        for name in envelope.active_names
        if name not in DEFLECTION_COLUMNS and any(b.get(name) is not None for b in envelope.bands)
    )

    for band in envelope.bands:
        rng = np.random.default_rng(doe.seed + 1000 * (band.band.index + 1))

        if doe.method is DoeMethod.TENSORIEL:
            interior = [(p, NodeOrigin.GRILLE) for p in _grid_points(band)]
        else:
            points, lhs_notes = _lhs_points(band, doe, ds, rng)
            interior = [(p, NodeOrigin.LHS) for p in points]
            notes.extend(lhs_notes)

        if doe.include_corners:
            corners, corner_notes = corner_points(band.axes())
            interior.extend((dict(c), NodeOrigin.COIN) for c in corners)
            notes.extend(f"bande {band.band.index} : {n}" for n in corner_notes)

        deduped = _dedupe(interior)
        discrete = _discrete_levels(band)
        counter = 0

        for point, origin in deduped:
            for phi in phi_levels:
                for deflection in doe.deflections:
                    values = dict(point)
                    values[PHI_COLUMN] = float(phi)
                    _apply_discrete(values, discrete, doe.discrete_fraction, counter)
                    alpha_tot = float(values.get(ALPHA_COLUMN, 0.0))
                    config = calc_config(
                        alpha_tot_deg=alpha_tot,
                        phi_folded_deg=float(phi),
                        spec=symmetry,
                        deflection=deflection.symmetry,
                    )
                    nodes.append(
                        DoeNode(
                            node_id=f"B{band.band.index:02d}-N{counter:04d}",
                            band_index=band.band.index,
                            mach_low=band.band.mach_low,
                            mach_high=band.band.mach_high,
                            values=_ordered(values, variable_names),
                            deflection=deflection,
                            origin=origin,
                            calc_config=config,
                            relative_cost=relative_cost(config),
                            zero_components=zero_components(
                                float(phi), symmetry, deflection.symmetry
                            ),
                        )
                    )
                    counter += 1

        notes.extend(f"bande {band.band.index} : {w}" for w in band.warnings)

    return DoePlan(
        nodes=tuple(nodes),
        envelope=envelope,
        method=doe.method,
        seed=doe.seed,
        variable_names=variable_names,
        notes=tuple(notes),
    )


def _dedupe(
    points: list[tuple[dict[str, float], NodeOrigin]], *, tol: float = 1e-9
) -> list[tuple[dict[str, float], NodeOrigin]]:
    """Drop duplicated points, promoting any duplicate that is also a corner.

    Corners very often coincide with grid points, because the tensor grid
    includes its own endpoints and those endpoints *are* the conditional
    bounds. Keeping the first occurrence but upgrading its origin to ``coin``
    means the plan reports how many of its nodes bracket the domain, whichever
    placement method produced them -- otherwise the tensor method would always
    report zero corners while in fact containing them all.
    """
    seen: dict[tuple[float, ...], int] = {}
    out: list[tuple[dict[str, float], NodeOrigin]] = []
    for point, origin in points:
        key = tuple(round(point[k] / max(tol, 1e-12)) * tol for k in sorted(point))
        if key in seen:
            if origin is NodeOrigin.COIN:
                existing, _ = out[seen[key]]
                out[seen[key]] = (existing, NodeOrigin.COIN)
            continue
        seen[key] = len(out)
        out.append((point, origin))
    return out


def _apply_discrete(
    values: dict[str, float],
    discrete: dict[str, tuple[float, ...]],
    fraction: float,
    counter: int,
) -> None:
    """Give a deterministic share of the nodes the second level of each factor.

    A discrete factor is applied by superposition on a subset of the plan, not
    by multiplying the grid: doubling the whole plan to answer "does the
    boundary-layer state matter?" would be a poor use of the budget.
    """
    for name, levels in discrete.items():
        if not levels:
            continue
        if len(levels) == 1 or fraction <= 0.0:
            values[name] = float(levels[0])
            continue
        period = max(round(1.0 / fraction), 1)
        values[name] = float(levels[-1] if counter % period == period - 1 else levels[0])


def _ordered(values: dict[str, float], names: tuple[str, ...]) -> dict[str, float]:
    """Reorder a node's values to the plan's column order, filling gaps with NaN."""
    return {name: float(values.get(name, np.nan)) for name in names}
