"""The recommendation engine: how many cores should this job use?

Three strategies, matching the three ways engineers actually phrase the
question:

- ``EFFICIENCY``   "don't waste my allocation"  -> most cores still above an
  efficiency floor.
- ``DEADLINE``     "it must be done by Monday"  -> fewest cores that still
  make the deadline.
- ``FASTEST``      "I don't care what it costs" -> lowest wall-time.

All three search the same feasible set, so they are directly comparable and
the report can show what the other choices would have cost.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cfd_perf._compat import StrEnum
from cfd_perf.core import constraints as cons
from cfd_perf.core.model import ScalingModel
from cfd_perf.data.machine import Machine
from cfd_perf.data.mesh import Mesh
from cfd_perf.data.pilot import PilotSeries

DEFAULT_MAX_EFFICIENCY_LOSS = 0.30


class Strategy(StrEnum):
    """How to pick among feasible core counts."""

    EFFICIENCY = "efficiency"
    DEADLINE = "deadline"
    FASTEST = "fastest"


@dataclass(frozen=True)
class Candidate:
    """One core count with every predicted metric."""

    cores: int
    nodes: int
    time_per_iter_s: float
    runtime_hours: float
    speedup: float
    efficiency: float
    efficiency_loss: float
    core_hours: float
    cells_per_core: float
    ram_per_core_gb: float | None
    violations: tuple[cons.Violation, ...] = ()
    extrapolated: bool = False

    @property
    def is_feasible(self) -> bool:
        return not self.violations


@dataclass(frozen=True)
class Recommendation:
    """The answer, plus everything needed to justify and audit it."""

    strategy: Strategy
    choice: Candidate | None
    candidates: tuple[Candidate, ...]
    model: ScalingModel
    mesh: Mesh
    machine: Machine
    pilot: PilotSeries
    fastest: Candidate | None = None
    cheapest: Candidate | None = None
    max_efficiency_loss: float = DEFAULT_MAX_EFFICIENCY_LOSS
    deadline_hours: float | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def feasible(self) -> tuple[Candidate, ...]:
        return tuple(c for c in self.candidates if c.is_feasible)

    @property
    def rejected(self) -> tuple[Candidate, ...]:
        return tuple(c for c in self.candidates if not c.is_feasible)

    def rejection_summary(self) -> dict[str, int]:
        """Count of rejected candidates per violation code."""
        counts: dict[str, int] = {}
        for cand in self.rejected:
            for v in cand.violations:
                counts[v.code] = counts.get(v.code, 0) + 1
        return counts


def _evaluate(
    nc: int,
    *,
    model: ScalingModel,
    mesh: Mesh,
    machine: Machine,
    constraints: cons.Constraints,
    n_iterations: int,
) -> Candidate:
    runtime = model.runtime_hours(nc, n_iterations)
    core_hours = model.core_hours(nc, n_iterations)
    violations = cons.check(
        nc,
        mesh=mesh,
        machine=machine,
        constraints=constraints,
        runtime_hours=runtime,
        core_hours=core_hours,
    )
    return Candidate(
        cores=nc,
        nodes=machine.nodes_for(nc),
        time_per_iter_s=model.time_per_iter(nc),
        runtime_hours=runtime,
        speedup=model.speedup(nc),
        efficiency=model.efficiency(nc),
        efficiency_loss=model.efficiency_loss(nc),
        core_hours=core_hours,
        cells_per_core=mesh.cells_per_core(nc),
        ram_per_core_gb=mesh.ram_per_core_gb(nc),
        violations=tuple(violations),
        extrapolated=model.is_extrapolating(nc),
    )


def recommend(
    *,
    model: ScalingModel,
    mesh: Mesh,
    pilot: PilotSeries,
    machine: Machine | None = None,
    constraints: cons.Constraints | None = None,
    strategy: Strategy = Strategy.EFFICIENCY,
    max_efficiency_loss: float = DEFAULT_MAX_EFFICIENCY_LOSS,
    deadline_hours: float | None = None,
    cores_min: int | None = None,
    cores_max: int | None = None,
) -> Recommendation:
    """Recommend a core count.

    Raises
    ------
    ValueError
        If ``DEADLINE`` is requested without ``deadline_hours``, or if the
        search range is empty.
    """
    if strategy is Strategy.DEADLINE and deadline_hours is None:
        raise ValueError("deadline_hours est requis pour la stratégie « deadline »")
    if not 0.0 < max_efficiency_loss < 1.0:
        raise ValueError(
            f"max_efficiency_loss must be in (0, 1), got {max_efficiency_loss}"
        )

    mach = machine or Machine()
    cts = constraints or cons.Constraints()
    notes: list[str] = []

    lo = cores_min or pilot.baseline_cores
    hi = cores_max or _default_cores_max(mesh, mach, cts, pilot)
    if hi < lo:
        raise ValueError(f"empty core search range: cores_max={hi} < cores_min={lo}")

    counts = mach.candidate_core_counts(lo, hi)
    candidates = tuple(
        _evaluate(
            nc,
            model=model,
            mesh=mesh,
            machine=mach,
            constraints=cts,
            n_iterations=pilot.n_iterations,
        )
        for nc in counts
    )

    feasible = [c for c in candidates if c.is_feasible]

    choice: Candidate | None = None
    if feasible:
        if strategy is Strategy.EFFICIENCY:
            within = [c for c in feasible if c.efficiency_loss <= max_efficiency_loss]
            if within:
                choice = max(within, key=lambda c: c.cores)
            else:
                notes.append(
                    f"aucune configuration ne garde la perte d'efficacité sous "
                    f"{max_efficiency_loss:.0%} ; repli sur l'option réalisable la "
                    "plus efficace"
                )
                choice = max(feasible, key=lambda c: c.efficiency)
        elif strategy is Strategy.DEADLINE:
            assert deadline_hours is not None
            in_time = [c for c in feasible if c.runtime_hours <= deadline_hours]
            if in_time:
                choice = min(in_time, key=lambda c: c.cores)
            else:
                notes.append(
                    f"aucune configuration réalisable ne tient l'échéance de "
                    f"{deadline_hours:g} h ; l'option la plus rapide est proposée à la place"
                )
                choice = min(feasible, key=lambda c: c.runtime_hours)
        else:
            choice = min(feasible, key=lambda c: c.runtime_hours)

    fastest = min(feasible, key=lambda c: c.runtime_hours) if feasible else None
    cheapest = min(feasible, key=lambda c: c.core_hours) if feasible else None

    notes.extend(_advisories(model, choice, mach, hi))

    return Recommendation(
        strategy=strategy,
        choice=choice,
        candidates=candidates,
        model=model,
        mesh=mesh,
        machine=mach,
        pilot=pilot,
        fastest=fastest,
        cheapest=cheapest,
        max_efficiency_loss=max_efficiency_loss,
        deadline_hours=deadline_hours,
        notes=tuple(notes),
    )


def _advisories(
    model: ScalingModel,
    choice: Candidate | None,
    machine: Machine,
    cores_max: int,
) -> list[str]:
    notes: list[str] = []

    if not model.quality.is_trustworthy:
        notes.append(
            f"l'ajustement du modèle est {_VERDICT_FR.get(model.quality.verdict, model.quality.verdict)} "
            f"({model.quality.max_rel_err_pct:.1f} % d'erreur max vs pilote) ; "
            "traitez les chiffres ci-dessous comme indicatifs et ajoutez des points pilotes"
        )

    if choice is not None and choice.extrapolated:
        lo, hi = model.fitted_range
        notes.append(
            f"{choice.cores} cœurs est hors de la plage pilote ({lo}-{hi}) ; "
            "la prédiction est une extrapolation"
        )

    t_min = model.time_minimum_cores(cores_max)
    if t_min is not None and choice is not None and choice.cores > t_min:
        notes.append(
            f"au-delà de {t_min} cœurs ce cas devient *plus lent*, pas plus rapide "
            "(la communication domine)"
        )

    if choice is not None and machine.allocates_whole_nodes and not machine.is_full_nodes(
        choice.cores
    ):
        notes.append(
            f"{choice.cores} cœurs n'est pas un nombre entier de nœuds de "
            f"{machine.cores_per_node} cœurs ; vous serez facturé pour "
            f"{choice.nodes} nœuds complets"
        )

    return notes


_VERDICT_FR = {
    "excellent": "excellent",
    "good": "bon",
    "marginal": "limite",
    "poor": "mauvais",
}


def _default_cores_max(
    mesh: Mesh,
    machine: Machine,
    constraints: cons.Constraints,
    pilot: PilotSeries,
) -> int:
    """Widest core count worth searching when the user gives no ceiling.

    Bounded by the mesh (cells/core floor) and the machine, then given a
    little headroom past the pilot so the curve shows what lies beyond the
    measured range.
    """
    by_mesh = max(1, mesh.num_cells // constraints.min_cells_per_core)
    limit = by_mesh
    if machine.max_cores is not None:
        limit = min(limit, machine.max_cores)
    headroom = pilot.core_range[1] * 2
    return max(pilot.baseline_cores, min(limit, headroom))
