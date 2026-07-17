"""Study definition: one YAML file describing a sizing question.

A single self-documenting file is what makes this shareable across a
department -- it can be committed next to the case, diffed, and reviewed.

Schema::

    study:
      name: "ONERA M6 - cruise"
      n_iterations: 12000

    mesh:
      num_cells: 20000000
      num_faces: 61200000                # optional
      mem_per_cell_bytes: 7600           # optional; else inferred from pilot
      cell_type_distribution:            # optional, documentation only
        hex: 0.78

    machine:                             # optional
      name: "cluster-a"
      cores_per_node: 48
      ram_per_node_gb: 192
      max_nodes: 32
      max_walltime_hours: 24

    constraints:                         # optional
      min_cells_per_core: 10000
      min_ram_per_core_gb: 0.5
      max_core_hours: 200000

    objective:                           # optional
      strategy: efficiency               # efficiency | deadline | fastest
      max_efficiency_loss: 0.30
      deadline_hours: 12                 # required for strategy: deadline
      cores_max: 2048

    pilot:
      - {cores: 48,  time_per_iter_s: 3.85, peak_ram_total_gb: 142}
      - {cores: 96,  time_per_iter_s: 2.18, peak_ram_total_gb: 142}
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cfd_perf.core.constraints import Constraints
from cfd_perf.data.machine import Machine
from cfd_perf.data.mesh import Mesh, mesh_from_data
from cfd_perf.data.pilot import PilotSeries, pilot_from_points
from cfd_perf.engine.recommend import DEFAULT_MAX_EFFICIENCY_LOSS, Strategy


class StudyError(ValueError):
    """A study file that cannot be understood.

    Carries the offending file path so the CLI can point at it directly.
    """

    def __init__(self, message: str, *, path: Path | None = None) -> None:
        self.path = path
        super().__init__(f"{path}: {message}" if path else message)


@dataclass(frozen=True)
class Objective:
    """What the user is optimising for."""

    strategy: Strategy = Strategy.EFFICIENCY
    max_efficiency_loss: float = DEFAULT_MAX_EFFICIENCY_LOSS
    deadline_hours: float | None = None
    cores_min: int | None = None
    cores_max: int | None = None


@dataclass(frozen=True)
class Study:
    """A fully parsed and validated sizing study."""

    name: str
    mesh: Mesh
    pilot: PilotSeries
    machine: Machine
    constraints: Constraints
    objective: Objective


def _section(data: dict[str, Any], key: str, path: Path | None) -> dict[str, Any]:
    value = data.get(key) or {}
    if not isinstance(value, dict):
        raise StudyError(f"la section « {key} » doit être une table, obtenu {type(value).__name__}", path=path)
    return value


def _require(section: dict[str, Any], key: str, where: str, path: Path | None) -> Any:
    if key not in section:
        raise StudyError(f"« {where} » : clé requise « {key} » manquante", path=path)
    return section[key]


def parse_study(data: dict[str, Any], *, path: Path | None = None) -> Study:
    """Build a Study from an already-loaded mapping."""
    if not isinstance(data, dict):
        raise StudyError(f"le niveau supérieur doit être une table, obtenu {type(data).__name__}", path=path)

    unknown = set(data) - {"study", "mesh", "machine", "constraints", "objective", "pilot"}
    if unknown:
        raise StudyError(f"section(s) de niveau supérieur inconnue(s) : {sorted(unknown)}", path=path)

    study_sec = _section(data, "study", path)
    mesh_sec = _section(data, "mesh", path)
    machine_sec = _section(data, "machine", path)
    cons_sec = _section(data, "constraints", path)
    obj_sec = _section(data, "objective", path)

    raw_pilot = data.get("pilot")
    if not raw_pilot:
        raise StudyError(
            "la section « pilot » est requise et doit lister au moins une mesure", path=path
        )
    if not isinstance(raw_pilot, list):
        raise StudyError(f"la section « pilot » doit être une liste, obtenu {type(raw_pilot).__name__}", path=path)

    n_iterations = int(_require(study_sec, "n_iterations", "study", path))

    try:
        pilot = pilot_from_points(raw_pilot, n_iterations=n_iterations)
    except (ValueError, TypeError, KeyError) as exc:
        raise StudyError(str(exc), path=path) from exc

    try:
        mesh = mesh_from_data(
            num_cells=int(_require(mesh_sec, "num_cells", "mesh", path)),
            num_faces=_opt_int(mesh_sec.get("num_faces")),
            cell_type_distribution=mesh_sec.get("cell_type_distribution"),
            mem_per_cell_bytes=_opt_float(mesh_sec.get("mem_per_cell_bytes")),
            pilot=pilot,
        )
        machine = Machine(
            name=str(machine_sec.get("name", "generic")),
            cores_per_node=int(machine_sec.get("cores_per_node", 1)),
            ram_per_node_gb=_opt_float(machine_sec.get("ram_per_node_gb")),
            max_nodes=_opt_int(machine_sec.get("max_nodes")),
            max_walltime_hours=_opt_float(machine_sec.get("max_walltime_hours")),
        )
        constraints = Constraints(
            min_cells_per_core=int(cons_sec.get("min_cells_per_core", 10_000)),
            min_ram_per_core_gb=_opt_float(cons_sec.get("min_ram_per_core_gb")),
            max_walltime_hours=_opt_float(cons_sec.get("max_walltime_hours")),
            max_core_hours=_opt_float(cons_sec.get("max_core_hours")),
        )
    except (ValueError, TypeError) as exc:
        raise StudyError(str(exc), path=path) from exc

    strategy_raw = str(obj_sec.get("strategy", Strategy.EFFICIENCY.value))
    try:
        strategy = Strategy(strategy_raw)
    except ValueError:
        valid = ", ".join(s.value for s in Strategy)
        raise StudyError(
            f"objective.strategy « {strategy_raw} » inconnue ; valeurs valides : {valid}", path=path
        ) from None

    deadline = _opt_float(obj_sec.get("deadline_hours"))
    if strategy is Strategy.DEADLINE and deadline is None:
        raise StudyError(
            "objective.strategy vaut « deadline » mais objective.deadline_hours n'est pas défini", path=path
        )

    objective = Objective(
        strategy=strategy,
        max_efficiency_loss=float(
            obj_sec.get("max_efficiency_loss", DEFAULT_MAX_EFFICIENCY_LOSS)
        ),
        deadline_hours=deadline,
        cores_min=_opt_int(obj_sec.get("cores_min")),
        cores_max=_opt_int(obj_sec.get("cores_max")),
    )

    return Study(
        name=str(study_sec.get("name", "unnamed study")),
        mesh=mesh,
        pilot=pilot,
        machine=machine,
        constraints=constraints,
        objective=objective,
    )


def load_study(path: str | Path) -> Study:
    """Load and validate a study YAML file."""
    p = Path(path)
    if not p.is_file():
        raise StudyError("fichier introuvable", path=p)
    try:
        data = yaml.safe_load(p.read_text())
    except yaml.YAMLError as exc:
        raise StudyError(f"YAML invalide : {exc}", path=p) from exc
    if data is None:
        raise StudyError("fichier vide", path=p)
    return parse_study(data, path=p)


def _opt_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _opt_float(value: Any) -> float | None:
    return None if value is None else float(value)
