"""cfd-perf -- how many CPUs should I launch my CFD simulation on?

Typical use::

    from cfd_perf import load_study, fit_model, recommend

    study = load_study("STUDY.yaml")
    model = fit_model(study.pilot)
    rec = recommend(model=model, mesh=study.mesh, pilot=study.pilot,
                    machine=study.machine, constraints=study.constraints)
    print(rec.choice.cores)
"""

from __future__ import annotations

from cfd_perf.core.checkpoint import (
    expected_utilization,
    mtbf_to_failure_rate,
    mtbf_years_to_failure_rate,
    optimal_interval,
    survival_probability,
)
from cfd_perf.core.constraints import Constraints, Violation
from cfd_perf.core.model import FitQuality, ModelKind, ScalingModel, fit_model
from cfd_perf.data.machine import Machine
from cfd_perf.data.mesh import Mesh, mesh_from_data
from cfd_perf.data.pilot import PilotPoint, PilotSeries, pilot_from_points
from cfd_perf.data.study import Objective, Study, StudyError, load_study, parse_study
from cfd_perf.engine.recommend import (
    Candidate,
    Recommendation,
    Strategy,
    recommend,
)

__version__ = "1.0.0"

__all__ = [
    "Candidate",
    "Constraints",
    "FitQuality",
    "Machine",
    "Mesh",
    "ModelKind",
    "Objective",
    "PilotPoint",
    "PilotSeries",
    "Recommendation",
    "ScalingModel",
    "Strategy",
    "Study",
    "StudyError",
    "Violation",
    "expected_utilization",
    "fit_model",
    "load_study",
    "mesh_from_data",
    "mtbf_to_failure_rate",
    "mtbf_years_to_failure_rate",
    "optimal_interval",
    "parse_study",
    "pilot_from_points",
    "recommend",
    "survival_probability",
]
