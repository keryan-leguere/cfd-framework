# cfd-perf -- CFD Performance & Scaling Estimator

Solver-agnostic CPU scaling estimator for steady RANS CFD simulations.
Predicts runtime, parallel efficiency, and memory usage vs core count,
then selects an optimal launch configuration under efficiency-loss,
deadline, or minimum-runtime constraints.

## Install

```bash
pip install -e ".[dev]"
```

## Scaling models

| Model | Pilot points | Behaviour |
|:---|:---|:---|
| **beta** | 1-2 | Classical single-parameter law. Always monotonically decreasing -- cannot represent communication-dominated regime. |
| **empirical** | >= 3 | Quadratic fit in log-space. Can capture the U-shaped curve where time per iteration starts rising again at high core counts. |
| **auto** (default) | any | Selects empirical when >= 3 points, beta otherwise. |

## Optimization modes

| Mode | Selection rule |
|:---|:---|
| **efficiency** | Largest feasible core count within a max efficiency-loss threshold. |
| **deadline** | Smallest feasible core count finishing within a deadline. |
| **min_runtime** | Core count with the lowest predicted total runtime (useful when the curve has a minimum). |

## Quick start (Python API)

```python
from pathlib import Path
import pandas as pd
import cfd_perf
from cfd_perf.constraints.config import HardConstraints

mesh_data = {
    "num_cells": 20_000_000,
    "num_faces": 61_200_000,
    "cell_type_distribution": {"hex": 0.78, "prism": 0.14, "tet": 0.06, "pyramid": 0.02},
}

pilot_df = pd.DataFrame([
    {"cores":  48, "time_per_iter_s": 3.85, "peak_ram_total_gb": 142.0},
    {"cores":  96, "time_per_iter_s": 2.18, "peak_ram_total_gb": 142.0},
    {"cores": 192, "time_per_iter_s": 1.41, "peak_ram_total_gb": 143.0},
    {"cores": 384, "time_per_iter_s": 1.12, "peak_ram_total_gb": 144.0},
    {"cores": 576, "time_per_iter_s": 1.05, "peak_ram_total_gb": 145.0},
    {"cores": 768, "time_per_iter_s": 1.10, "peak_ram_total_gb": 146.0},
])
n_iterations = 12_000

pilot = cfd_perf.pilot_from_data(pilot_df, n_iterations=n_iterations)
mesh = cfd_perf.mesh_from_data(mesh_data, pilot_baseline=pilot.baseline)

# Auto-selects empirical model when >= 3 pilot points
params = cfd_perf.fit_scaling_model(pilot)

# Find the fastest feasible core count
result = cfd_perf.optimize(
    mesh, pilot, params,
    mode="min_runtime",
    cores_max=1024,
    constraints=HardConstraints(min_cells_per_core=15_000, min_ram_per_core_gb=0.1),
)

cfd_perf.plot_scaling(
    result,
    out=Path("demo_output/scaling.png"),
    pilot=pilot,
    mesh=mesh,
    params=params,
    show=True,
)
```

**Backward compatibility:** `fit_beta(pilot)` still works and always returns the
single-beta model.  Existing input files for the CLI work unchanged; add
`scaling_model = auto|beta|empirical` to opt into the new model.

## Dependencies

- **Required**: `numpy`, `pandas`, `matplotlib`
- **Dev**: `pytest`, `ruff`, `mypy`
