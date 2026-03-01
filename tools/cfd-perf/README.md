# cfd-perf -- CFD Performance & Scaling Estimator

Solver-agnostic CPU scaling estimator for steady RANS CFD simulations.
Predicts runtime, parallel efficiency, and memory usage vs core count,
then selects an optimal launch configuration under efficiency-loss or
deadline constraints.

## Install

```bash
pip install -e ".[dev]"
```

## Quick start (Python API)

Define mesh and pilot data in memory (dict or pandas DataFrame), then call the package:

```python
from pathlib import Path
import pandas as pd
import cfd_perf
from cfd_perf.constraints.config import HardConstraints

# Mesh: dict or one-row DataFrame
mesh_data = {
    "num_cells": 20_000_000,
    "num_faces": 61_200_000,
    "cell_type_distribution": {"hex": 0.78, "prism": 0.14, "tet": 0.06, "pyramid": 0.02},
}

# Pilot: DataFrame or dict with "points" + n_iterations
pilot_df = pd.DataFrame([
    {"cores": 48, "time_per_iter_s": 3.85, "peak_ram_total_gb": 142.0},
    {"cores": 96, "time_per_iter_s": 2.18, "peak_ram_total_gb": 142.0},
])
n_iterations = 12_000

pilot = cfd_perf.pilot_from_data(pilot_df, n_iterations=n_iterations)
mesh = cfd_perf.mesh_from_data(mesh_data, pilot_baseline=pilot.baseline)
params = cfd_perf.fit_beta(pilot)

result = cfd_perf.optimize(
    mesh, pilot, params,
    mode="efficiency",
    max_efficiency_loss=0.25,
    cores_max=1024,
    constraints=HardConstraints(min_cells_per_core=100_000, min_ram_per_core_gb=0.5),
)

# Output: scaling figure only (no JSON/CSV/SLURM exports)
cfd_perf.plot_scaling(
    result,
    out=Path("demo_output/scaling.png"),
    pilot=pilot,
    mesh=mesh,
    params=params,
    show=True,
)
```

**Backward compatibility:** You can still load from JSON files with `load_pilot(path)` and `analyze_mesh(path, ...)` if you prefer file-based input.

## Dependencies

- **Required**: `numpy`, `pandas`, `matplotlib`
- **Dev**: `pytest`, `ruff`, `mypy`
