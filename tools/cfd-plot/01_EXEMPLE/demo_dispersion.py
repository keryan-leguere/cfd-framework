"""
demo_dispersion.py — Runnable showcase for the ``dispersion`` package.

Run from ``tools/cfd-plot``::

    PYTHONPATH=. python demo_dispersion.py

Output PNGs are written to ``demo_output/``.

Sections
--------
A  Cm_alpha dashboard + CDF         (canonical aerodynamic coefficient example)
B  Multi-quantity PDF matrix        (CL, CD, Cm_alpha, Cn_beta)
C  Distribution shape gallery       (types 1–6 side-by-side)
D  Dispersed polar                  (a dispersion propagated along an alpha sweep)
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from cfd_plot import (
    make_legend,
    new_figure,
    print_file_report,
    save_figure,
    set_suptitle,
    set_title,
    style_context,
    use_style,
)
from cfd_plot.dispersion import (
    DispersionSpec,
    QuantityDispersion,
    band_from_dispersion,
    plot_dispersion_band,
    plot_dispersion_cdf,
    plot_dispersion_dashboard,
    plot_dispersion_matrix,
    plot_dispersion_type,
)

# ---------------------------------------------------------------------------
# Global style + reproducibility
# ---------------------------------------------------------------------------

use_style("notebook")
RNG = np.random.default_rng(0)

OUT_DIR = Path(__file__).with_name("demo_output")
OUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Quantity definitions
# ---------------------------------------------------------------------------

Cm_alpha = QuantityDispersion(
    name="Cm_alpha",
    nominal=-2.5,
    bias=DispersionSpec(disp_type=5, moy=0.0, var=0.015),
    scale=DispersionSpec(disp_type=6, moy=0.0, var=0.10),
)

CL = QuantityDispersion(
    name="CL",
    nominal=0.82,
    bias=DispersionSpec(disp_type=3, moy=0.0, var=0.02),
    scale=DispersionSpec(disp_type=6, moy=0.0, var=0.08),
)

CD = QuantityDispersion(
    name="CD",
    nominal=0.045,
    bias=DispersionSpec(disp_type=4, moy=0.0, var=0.008),
    scale=DispersionSpec(disp_type=5, moy=0.0, var=0.12),
)

Cn_beta = QuantityDispersion(
    name="Cn_beta",
    nominal=0.18,
    bias=DispersionSpec(disp_type=3, moy=0.0, var=0.01),
    scale=DispersionSpec(disp_type=3, moy=0.0, var=0.06),
)

# ---------------------------------------------------------------------------
# A — Cm_alpha dashboard + CDF
# ---------------------------------------------------------------------------

print("A: Cm_alpha dashboard …")
fig_dash, _ = plot_dispersion_dashboard(Cm_alpha, n=50_000, rng=RNG)
save_figure(fig_dash, OUT_DIR / "A1_Cm_alpha_dashboard", formats=("png",), report=False)
plt.close(fig_dash)

print("A: Cm_alpha CDF …")
fig_cdf, _ = plot_dispersion_cdf(Cm_alpha, n=50_000, rng=RNG)
save_figure(fig_cdf, OUT_DIR / "A2_Cm_alpha_cdf", formats=("png",), report=False)
plt.close(fig_cdf)

# ---------------------------------------------------------------------------
# B — Multi-quantity PDF matrix
# ---------------------------------------------------------------------------

print("B: multi-quantity matrix …")
fig_mat, _ = plot_dispersion_matrix(
    [CL, CD, Cm_alpha, Cn_beta], n=30_000, ncols=2, share_x=False, rng=RNG
)
save_figure(fig_mat, OUT_DIR / "B_matrix", formats=("png",), report=False)
plt.close(fig_mat)

# ---------------------------------------------------------------------------
# C — Distribution shape gallery (2 × 3, types 1–6)
# ---------------------------------------------------------------------------

print("C: type shape gallery …")

type_specs = [
    DispersionSpec(disp_type=1, moy=0.0,  var=0.0),
    DispersionSpec(disp_type=2, moy=0.5,  var=0.0),
    DispersionSpec(disp_type=3, moy=0.0,  var=1.0),
    DispersionSpec(disp_type=4, moy=0.0,  var=1.0),
    DispersionSpec(disp_type=5, moy=0.0,  var=1.0),
    DispersionSpec(disp_type=6, moy=0.0,  var=1.0),
]

with style_context("notebook"):
    fig_gal, axes_gal = plt.subplots(2, 3, figsize=(13, 6))
    for ax, spec in zip(axes_gal.ravel(), type_specs, strict=True):
        plot_dispersion_type(spec, ax=ax)
    set_suptitle(fig_gal, "Dispersion type shapes — types 1 to 6", fontsize=12)

save_figure(fig_gal, OUT_DIR / "C_type_gallery", formats=("png",), report=False)
plt.close(fig_gal)

# ---------------------------------------------------------------------------
# D — A dispersion propagated along an alpha sweep
# ---------------------------------------------------------------------------
# The sections above characterise *one* coefficient. This is what the analysis
# is usually for: what the polar itself looks like once CN is dispersed.

print("D: dispersed polar …")

alpha_sweep = np.linspace(-4.0, 16.0, 21)
CN_nominal = 0.11 * alpha_sweep + 0.004 * alpha_sweep**2

band = band_from_dispersion(
    alpha_sweep, CN_nominal,
    bias=DispersionSpec(disp_type=5, moy=0.0, var=0.02),    # additive, sigma = 0.01
    scale=DispersionSpec(disp_type=6, moy=0.0, var=0.10),   # multiplicative, sigma = 5 %
    n=20000,
    rng=RNG,
)

print(f"   envelope: {band.label}, {band.n_samples} samples")
print(f"   half-width at alpha=16°: {band.half_width[-1]:.4f}")

fig_band, ax_band = new_figure(figsize=(8, 5))
# realisations= draws individual sampled curves: with the default
# correlated=True they are smooth, because one error tilts the whole polar.
plot_dispersion_band(ax_band, band, label="CN (mean)", realisations=15)
ax_band.set(xlabel="alpha [deg]", ylabel="CN [-]")
set_title(ax_band, "Dispersed polar — 95 % envelope")
make_legend(ax_band, loc="upper left")

save_figure(fig_band, OUT_DIR / "D_dispersed_polar", formats=("png",), report=False)
plt.close(fig_band)

# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------

pngs = sorted(p for p in OUT_DIR.glob("*.png") if p.stem.startswith(("A", "B", "C", "D")))
print()
print_file_report(pngs, title="demo_dispersion — output files")
