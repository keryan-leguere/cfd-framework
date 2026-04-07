# %% [markdown]
# # cfd-perf Demo -- Steady RANS Strong-Scaling Estimator
# 
# Industrial-grade example: **20M-cell hex-dominant RANS mesh** with 7 pilot
# measurements showing realistic non-linear scaling degradation **and**
# communication-dominated slowdown at high core counts.
# 
# 1. Define mesh metadata and pilot benchmark data
# 2. Analyze the mesh and auto-fit the scaling model
# 3. Compare **beta** vs **empirical** scaling models
# 4. Run optimization in **efficiency**, **deadline** and **min_runtime** modes
# 5. Generate professional scaling plots
# 
# **Prerequisites**
# 
# ```bash
# cd tools/cfd-perf && pip install -e ".[dev]"
# ```

# %% [markdown]
# ## Mathematical formulation
# 
# ### Beta model (classical)
# 
# $$
# T(N_c) \;=\; T_0 \left[\; \frac{N_{c_0}}{N_c} \;+\; \beta\;\left(1 - \frac{N_{c_0}}{N_c}\right) \;\right]
# $$
# 
# Always monotonically decreasing -- cannot represent communication-dominated
# regime.
# 
# ### Empirical model (new)
# 
# Quadratic fit in log-space:
# 
# $$
# T(N_c) \;=\; a \,\ln(N_c)^2 \;+\; b \,\ln(N_c) \;+\; c
# $$
# 
# Can capture the **U-shaped** behaviour: time decreases, reaches a minimum,
# then rises again when MPI communication dominates solver work.  Requires
# >= 3 pilot points; falls back to beta model otherwise.
# 
# ### Optimization modes
# 
# | Mode | Objective | Selection rule |
# |:---|:---|:---|
# | **Efficiency** | eff. loss <= threshold | largest feasible Nc |
# | **Deadline** | runtime <= deadline | smallest feasible Nc |
# | **Min-runtime** | minimize total runtime | Nc with lowest predicted runtime |

# %%
import sys
from pathlib import Path

PLOTTING_PATH = str(Path("../../scripts/post/plot").resolve())
if PLOTTING_PATH not in sys.path:
    sys.path.insert(0, PLOTTING_PATH)

# %% [markdown]
# ## 1. Sample input data
# 
# 20M-cell hex-dominant mesh.  Seven pilot points that show the full
# lifecycle: good scaling at low core counts, flattening, then a clear
# uptick at 768 and 1024 cores where MPI latency dominates.

# %%
out_dir = Path("demo_output")
out_dir.mkdir(exist_ok=True)

mesh_data = {
    "num_cells": 20_000_000,
    "num_faces": 61_200_000,
    "cell_type_distribution": {"hex": 0.78, "prism": 0.14, "tet": 0.06, "pyramid": 0.02},
}

pilot_data = {
    "n_iterations": 12_000,
    "points": [
        {"cores":   48, "time_per_iter_s": 3.85, "peak_ram_total_gb": 142.0},
        {"cores":   96, "time_per_iter_s": 2.18, "peak_ram_total_gb": 142.0},
        {"cores":  192, "time_per_iter_s": 1.41, "peak_ram_total_gb": 143.0},
        {"cores":  384, "time_per_iter_s": 1.12, "peak_ram_total_gb": 144.0},
        {"cores":  576, "time_per_iter_s": 1.05, "peak_ram_total_gb": 145.0},
        {"cores":  768, "time_per_iter_s": 1.10, "peak_ram_total_gb": 146.0},
        {"cores": 1024, "time_per_iter_s": 1.28, "peak_ram_total_gb": 148.0},
    ],
}
n_iterations = pilot_data["n_iterations"]

# %% [markdown]
# ## 2. Analyze mesh

# %%
import cfd_perf
from cfd_perf.io.display import print_mesh_stats

pilot = cfd_perf.pilot_from_data(pilot_data, n_iterations=n_iterations)
mesh = cfd_perf.mesh_from_data(mesh_data, pilot_baseline=pilot.baseline)

print_mesh_stats(mesh)

# %% [markdown]
# ## 3. Fit scaling models -- beta vs empirical
# 
# With 7 pilot points the `auto` hint selects the empirical (quadratic-in-log)
# model, which can represent the communication-dominated uptick.

# %%
from cfd_perf.io.display import print_fit_result

params_beta = cfd_perf.fit_beta(pilot)
print("--- Beta model ---")
print_fit_result(params_beta, pilot)

params_emp = cfd_perf.fit_scaling_model(pilot, model_hint="auto")
print("\n--- Empirical model (auto) ---")
print_fit_result(params_emp, pilot)

# %% [markdown]
# ## 4. Optimize -- Efficiency-driven (empirical model)

# %%
from cfd_perf.constraints.config import HardConstraints
from cfd_perf.io.display import print_optimization_result

constraints = HardConstraints(min_cells_per_core=15_000, min_ram_per_core_gb=0.1)

result_eff = cfd_perf.optimize(
    mesh, pilot, params_emp,
    mode="efficiency",
    max_efficiency_loss=0.70,
    cores_max=1024,
    stride=48,
    constraints=constraints,
)

print_optimization_result(result_eff)

# %% [markdown]
# ## 5. Optimize -- Deadline-driven (6 h wall-clock)

# %%
result_dl = cfd_perf.optimize(
    mesh, pilot, params_emp,
    mode="deadline",
    deadline_hours=6.0,
    cores_max=1024,
    stride=48,
    constraints=constraints,
)

print_optimization_result(result_dl)

# %% [markdown]
# ## 6. Optimize -- Min-runtime
# 
# Find the core count that minimizes total wall-clock time.  With the
# empirical model showing an uptick, this is no longer at the maximum
# core count.

# %%
result_mr = cfd_perf.optimize(
    mesh, pilot, params_emp,
    mode="min_runtime",
    cores_max=1024,
    stride=48,
    constraints=constraints,
)

print_optimization_result(result_mr)

# %% [markdown]
# ## 7. Scaling curves (plotting library)

# %%
#%matplotlib inline
import numpy as np
import matplotlib.pyplot as plt
from plotting import (
    use_style, new_figure, plot_line, make_legend,
    apply_oldschool_axes, add_reference_lines, add_textbox,
    annotate_point, set_suptitle, set_title,
)
from cfd_perf.optimizer.curve import build_scaling_curve
from cfd_perf.io.plotting import _compute_zones, _textbox_content, _format_runtime_mdh

_BLUE = "#0066CC"


def _full_curve_and_zones(result, pilot, mesh, params):
    """Build full scaling curve for all cores tested and pilot arrays."""
    nc0 = pilot.baseline_cores
    t0 = pilot.baseline_time_per_iter_s
    n_iter = pilot.n_iterations
    all_cores = sorted(
        set(c.cores for c in result.accepted) | set(r.cores for r in result.rejected)
    )
    if not all_cores:
        return None, None, None, None, None, None, None
    step = all_cores[1] - all_cores[0] if len(all_cores) >= 2 else 1
    nc_range = range(min(all_cores), max(all_cores) + 1, step)
    full = build_scaling_curve(nc_range, params, nc0, t0, n_iter, mesh)
    cores_all = np.array([c.cores for c in full])
    runtime_all = np.array([c.runtime_hours for c in full])
    eff_all = np.array([c.efficiency for c in full]) * 100
    rpc_all = np.array([c.ram_per_core_gb for c in full])

    accepted_cores = [c.cores for c in result.accepted]
    rejected_cores = [r.cores for r in result.rejected]

    pilot_nc = np.array([p.cores for p in pilot.points])
    pilot_runtime_h = np.array([p.time_per_iter_s * pilot.n_iterations / 3600 for p in pilot.points])
    pilot_eff = np.array([
        (t0 * nc0 / (p.time_per_iter_s * p.cores)) * 100 for p in pilot.points
    ])
    pilot_rpc = np.array([p.peak_ram_total_gb / p.cores for p in pilot.points])

    return (cores_all, runtime_all, eff_all, rpc_all,
            accepted_cores, rejected_cores,
            (pilot_nc, pilot_runtime_h, pilot_eff, pilot_rpc))


GREEN = "#009900"
RED = "#CC0000"
ZONE_ALPHA = 0.14


def _hline_label(ax, y_val, label, x_max):
    ax.axhline(y=y_val, color="C2", linewidth=0.9, linestyle=":", zorder=2)
    ax.text(x_max * 0.97, y_val, f"  {label}",
            ha="right", va="bottom", fontsize=7, color="C2", fontweight="bold", zorder=3)


def plot_demo(result, pilot, mesh, params, title_suffix=""):
    use_style("paper")

    out = _full_curve_and_zones(result, pilot, mesh, params)
    if out[0] is None:
        plt.show()
        return
    cores_all, runtime_all, eff_all, rpc_all, accepted_cores, rejected_cores, pilot_data = out
    pilot_nc, pilot_runtime_h, pilot_eff, pilot_rpc = pilot_data

    fig, axes = new_figure(1, 3, figsize=(16, 4.8), constrained_layout=False)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.82, bottom=0.14, wspace=0.28)
    set_suptitle(fig, f"Strong-Scaling Analysis  ({result.mode} mode){title_suffix}", fontsize=12)

    nc_opt = result.optimal.cores if result.optimal else None
    opt = result.optimal
    mrc = result.min_runtime_candidate
    meta = result.metadata

    x_max = max(cores_all) * 1.05

    target_eff_pct = (1.0 - meta["max_efficiency_loss"]) * 100 if "max_efficiency_loss" in meta else None
    target_deadline_h = meta.get("deadline_hours")

    green_span, red_span, boundary = _compute_zones(result, accepted_cores, rejected_cores, x_max)

    def draw_zones(ax):
        ax.axvspan(*green_span, alpha=ZONE_ALPHA, color=GREEN, zorder=0, label="accepted")
        if red_span[1] > red_span[0]:
            ax.axvspan(*red_span, alpha=ZONE_ALPHA, color=RED, zorder=0, label="rejected")
        if boundary > 0:
            ax.axvline(x=boundary, color="0.15", linewidth=1.8, linestyle="-", zorder=1)

    if result.mode == "efficiency" and target_eff_pct is not None:
        nc_at_target = np.interp(target_eff_pct, eff_all[::-1], cores_all[::-1].astype(float))
        h_eff = target_eff_pct
        h_runtime = float(np.interp(nc_at_target, cores_all, runtime_all))
        h_ram = float(np.interp(nc_at_target, cores_all, rpc_all))
        lbl_eff = f"target: {target_eff_pct:.0f}%"
        lbl_rt = f"{h_runtime:.1f} h"
        lbl_ram = f"{h_ram:.1f} GB"
    elif result.mode == "deadline" and target_deadline_h is not None:
        nc_at_target = np.interp(target_deadline_h, runtime_all[::-1], cores_all[::-1].astype(float))
        h_runtime = target_deadline_h
        h_eff = float(np.interp(nc_at_target, cores_all, eff_all))
        h_ram = float(np.interp(nc_at_target, cores_all, rpc_all))
        lbl_rt = f"target: {target_deadline_h:.0f} h"
        lbl_eff = f"{h_eff:.1f}%"
        lbl_ram = f"{h_ram:.1f} GB"
    else:
        h_runtime = h_eff = h_ram = None
        lbl_rt = lbl_eff = lbl_ram = ""

    # Runtime
    ax = axes[0]
    set_title(ax, "Runtime")
    ax.set_xlim(0, x_max)
    draw_zones(ax)
    plot_line(ax, cores_all, runtime_all, marker="o", label="predicted", markersize=4)
    ax.scatter(pilot_nc, pilot_runtime_h, marker="D", s=70, color="C4", edgecolors="black", linewidths=0.8, zorder=5, label="pilot")
    if opt:
        add_reference_lines(ax, vlines=[nc_opt], color="C2", linewidth=1.0, linestyle="--")
        annotate_point(ax, f"opt: {nc_opt} cores\n{_format_runtime_mdh(opt.runtime_hours)}",
                       xy=(nc_opt, opt.runtime_hours), offset=(40, 25))
    if mrc is not None and (opt is None or mrc.cores != opt.cores):
        add_reference_lines(ax, vlines=[mrc.cores], color=_BLUE, linewidth=1.0, linestyle="--")
        annotate_point(ax, f"min: {mrc.cores} cores\n{_format_runtime_mdh(mrc.runtime_hours)}",
                       xy=(mrc.cores, mrc.runtime_hours), offset=(-60, -30))
    if h_runtime is not None:
        _hline_label(ax, h_runtime, lbl_rt, x_max)
    ax.set_xlabel("Cores"); ax.set_ylabel("Total runtime (h)")
    add_textbox(ax, _textbox_content(meta), loc="center right", fontsize=7)
    apply_oldschool_axes(ax, legend=False)
    make_legend(ax, loc="upper right", fontsize=7)

    # Efficiency
    ax = axes[1]
    set_title(ax, "Parallel efficiency")
    ax.set_xlim(0, x_max)
    draw_zones(ax)
    plot_line(ax, cores_all, eff_all, marker="s", label="efficiency", markersize=4)
    ax.scatter(pilot_nc, pilot_eff, marker="D", s=70, color="C4", edgecolors="black", linewidths=0.8, zorder=5, label="pilot")
    if opt:
        add_reference_lines(ax, vlines=[nc_opt], color="C2", linewidth=1.0, linestyle="--")
        annotate_point(ax, f"opt: {nc_opt} cores\n{opt.efficiency * 100:.1f}%",
                      xy=(nc_opt, opt.efficiency * 100), offset=(40, 25))
    if h_eff is not None:
        _hline_label(ax, h_eff, lbl_eff, x_max)
    ax.set_xlabel("Cores"); ax.set_ylabel("Parallel efficiency (%)")
    ax.set_ylim(0, 105)
    ax.yaxis.set_major_locator(plt.MultipleLocator(10))
    ax.yaxis.set_minor_locator(plt.MultipleLocator(5))
    apply_oldschool_axes(ax, legend=False)
    make_legend(ax, loc="upper right", fontsize=7)

    # Memory / core
    ax = axes[2]
    set_title(ax, "RAM per core")
    ax.set_xlim(0, x_max)
    draw_zones(ax)
    plot_line(ax, cores_all, rpc_all, marker="^", label="RAM / core", markersize=4)
    ax.scatter(pilot_nc, pilot_rpc, marker="D", s=70, color="C4", edgecolors="black", linewidths=0.8, zorder=5, label="pilot")
    if opt:
        add_reference_lines(ax, vlines=[nc_opt], color="C2", linewidth=1.0, linestyle="--")
        annotate_point(ax, f"opt: {nc_opt} cores\n{opt.ram_per_core_gb:.1f} GB",
                      xy=(nc_opt, opt.ram_per_core_gb), offset=(40, 25))
    if h_ram is not None:
        _hline_label(ax, h_ram, lbl_ram, x_max)
    ax.set_xlabel("Cores"); ax.set_ylabel("RAM per core (GB)")
    apply_oldschool_axes(ax, legend=False)
    make_legend(ax, loc="upper right", fontsize=7)

    plt.show()


plot_demo(result_eff, pilot, mesh, params_emp, " -- efficiency (empirical)")
plot_demo(result_dl, pilot, mesh, params_emp, " -- deadline 6 h (empirical)")
plot_demo(result_mr, pilot, mesh, params_emp, " -- min_runtime (empirical)")

# %% [markdown]
# ## 8. Pilot data overlay -- beta vs empirical
# 
# Compare both models against the measured pilot points.

# %%
from cfd_perf.models.strong_scaling import time_per_iter, predict_time_per_iter

use_style("paper")
fig, ax = new_figure(figsize=(8, 5))

nc0 = pilot.baseline_cores
t0 = pilot.baseline_time_per_iter_s

nc_dense = np.arange(nc0, 1100, 1)
t_beta = np.array([time_per_iter(int(nc), nc0, t0, params_beta.beta) for nc in nc_dense])
t_emp = np.array([predict_time_per_iter(int(nc), nc0, t0, params_emp) for nc in nc_dense])

plot_line(ax, nc_dense, t_beta, marker="", linestyle="-",
          label=f"beta model (beta={params_beta.beta:.4f})")
plot_line(ax, nc_dense, t_emp, marker="", linestyle="--",
          label="empirical model (quadratic-in-log)")

pilot_nc = np.array([p.cores for p in pilot.points])
pilot_t = np.array([p.time_per_iter_s for p in pilot.points])
plot_line(ax, pilot_nc, pilot_t, marker="D", linestyle="",
          label="pilot measurements", markersize=7)

ax.set_xlabel("Cores")
ax.set_ylabel("Time per iteration (s)")
add_textbox(ax, "20M cells / steady RANS\n7 pilot points", loc="upper right", fontsize=8)
apply_oldschool_axes(ax)
plt.show()

# %% [markdown]
# ## 9. Scaling figures (output)

# %%
from cfd_perf.io.plotting import plot_scaling

plot_scaling(result_eff, out_dir / "scaling_efficiency.png", pilot=pilot, mesh=mesh, params=params_emp)
plot_scaling(result_dl, out_dir / "scaling_deadline.png", pilot=pilot, mesh=mesh, params=params_emp)
plot_scaling(result_mr, out_dir / "scaling_min_runtime.png", pilot=pilot, mesh=mesh, params=params_emp)
print("Figures saved to:", out_dir)
