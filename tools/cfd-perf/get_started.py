# %% [markdown]
# # cfd-perf -- Get Started
# 
# Minimal notebook: define your mesh and pilot data, pick an optimization
# mode, and get scaling figures immediately.
# 
# ```bash
# cd tools/cfd-perf && pip install -e ".[dev]"
# ```

# %% [markdown]
# | Solver type          | Approx FLOP per cell per iteration |
# | -------------------- | ----------------------------------- |
# | SIMPLE (steady RANS) | 2,000 – 5,000                       |
# | PISO (transient)     | 3,000 – 8,000                       |
# | LES                  | 5,000 – 15,000                      |
# | Implicit + multigrid | 10,000 – 30,000                     |
# 
# 
# FLOPS for one core of the machine: 20 GFLOP/s
# 
# --> Time per ite for one core = (nb of cells * FLOP per cell) / FLOPS of the machine
# --> Time per ite = time above * cores

# %% [markdown]
# ## 1. Input parameters
# 
# Edit the cells below with your own mesh metadata and pilot measurements.

# %%
import json, tempfile
from pathlib import Path
import sys
print(sys.path)

PLOTTING_PATH = str(Path("../../scripts/post/plot").resolve())
if PLOTTING_PATH not in sys.path:
    sys.path.insert(0, PLOTTING_PATH)

# ---- Mesh metadata ----
mesh_data = {
    "num_cells": 200_000_000,
    "num_faces": 600_000_000,
    "cell_type_distribution": {"hex": 0.78, "prism": 0.14, "tet": 0.06, "pyramid": 0.02},
}

# ---- Pilot benchmark data ----
pilot_data = {
    "n_iterations": 20_000,
    "points": [
        {"cores":  8,  "time_per_iter_s": 12000, "peak_ram_total_gb": 140.0},
    ],
}

# ---- Optimization settings ----
MODE = "efficiency"          # "efficiency" or "deadline"
MAX_EFFICIENCY_LOSS = 0.5   # used when MODE == "efficiency"
DEADLINE_HOURS = 6.0         # used when MODE == "deadline"
CORES_MAX = 1024
STRIDE = 8

# Write temp files
workdir = Path(tempfile.mkdtemp(prefix="cfd_perf_gs_"))
mesh_path = workdir / "mesh.json"
pilot_path = workdir / "pilot.json"
mesh_path.write_text(json.dumps(mesh_data, indent=2))
pilot_path.write_text(json.dumps(pilot_data, indent=2))
print(f"Working directory: {workdir}")

# %% [markdown]
# ## 2. Run analysis & optimization
# 
# Nothing to edit below -- just run the cells.

# %%
from cfd_perf.benchmark.ingest import load_pilot
from cfd_perf.mesh.analyzer import analyze_mesh
from cfd_perf.models.strong_scaling import fit_beta
from cfd_perf.optimizer.selector import optimize
from cfd_perf.cli.console import print_optimization_result, print_fit_result
from cfd_perf.constraints.config import HardConstraints

pilot = load_pilot(pilot_path)
mesh = analyze_mesh(mesh_path, pilot_baseline=pilot.baseline)
params = fit_beta(pilot)
print_fit_result(params,pilot)

constraints = HardConstraints(min_cells_per_core=100_000, min_ram_per_core_gb=0.5)

opt_kwargs = dict(
    mode=MODE,
    cores_max=CORES_MAX,
    stride=STRIDE,
    constraints=constraints,
)
if MODE == "efficiency":
    opt_kwargs["max_efficiency_loss"] = MAX_EFFICIENCY_LOSS
else:
    opt_kwargs["deadline_hours"] = DEADLINE_HOURS

result = optimize(mesh, pilot, params, **opt_kwargs)
print_optimization_result(result)

# %% [markdown]
# ## 3. Scaling figures

# %%
#matplotlib inline
from cfd_perf.io.plotting import plot_scaling

plot_scaling(
    result,
    out=workdir / "scaling.png",
    pilot=pilot,
    mesh=mesh,
    params=params,
    title_suffix=f" -- {MODE}",
    show=True,
)

# %% [markdown]
# ## 4. Export artifacts

# %%
from cfd_perf.io.exporters import export_json, export_csv
from cfd_perf.io.slurm import export_slurm

export_json(result, workdir / "result.json")
export_csv(result, workdir / "result.csv")
export_slurm(result, workdir / "submit.sh", job_name="cfd_run", partition="compute")

print("Exported to:", workdir)
for f in sorted(workdir.iterdir()):
    print(f"  {f.name:30s}  {f.stat().st_size / 1024:.1f} kB")


