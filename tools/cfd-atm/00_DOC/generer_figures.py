#!/usr/bin/env python3
"""Régénère les figures illustratives des documents (dossier ``FIGURES/``).

À relancer uniquement quand le modèle ou les constantes changent. Les figures
sont versionnées dans le dépôt. Installer ``cfd-plot`` (``pip install -e
tools/cfd-plot``) pour bénéficier du style maison ; sinon Matplotlib brut.

    python3 00_DOC/generer_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent / "src"))

from cfd_atm.core import isa  # noqa: E402
from cfd_atm.core.airspeed import airspeeds  # noqa: E402
from cfd_atm.core.atmosphere import AtmosphereModel  # noqa: E402
from cfd_atm.report import units  # noqa: E402
from cfd_atm.report._plotting_lib import get_plotting  # noqa: E402

_plotting = get_plotting()
FIGURES = ICI / "FIGURES"


def _style() -> None:
    if _plotting is not None:
        _plotting.use_style("paper")


def _plot(ax, x, y, **kw):  # type: ignore[no-untyped-def]
    if _plotting is not None:
        return _plotting.plot_line(ax, x, y, marker="", **kw)
    return ax.plot(x, y, **kw)[0]


def _save(fig, base: Path) -> None:  # type: ignore[no-untyped-def]
    if _plotting is not None:
        _plotting.save_figure(fig, str(base), formats=("png",))
    else:
        fig.savefig(base.with_suffix(".png"), dpi=150, bbox_inches="tight")


def figure_atmosphere_isa() -> None:
    """T, p, rho de l'ISA en fonction de l'altitude géopotentielle."""
    _style()
    fig, axes = plt.subplots(1, 3, figsize=(11, 4.2))
    h = np.linspace(0.0, 47000.0, 400)
    h_km = h / 1000.0
    _plot(axes[0], isa.isa_temperature(h), h_km, color="#e03a3e")
    axes[0].set_xlabel("Température T (K)")
    axes[0].set_ylabel("Altitude géopotentielle H (km)")
    _plot(axes[1], isa.isa_pressure(h) / 1000.0, h_km, color="#1f77b4")
    axes[1].set_xlabel("Pression p (kPa)")
    _plot(axes[2], isa.isa_density(h), h_km, color="#2ca02c")
    axes[2].set_xlabel("Densité ρ (kg/m³)")
    for ax in axes:
        ax.grid(True, alpha=0.3)
    fig.suptitle("Atmosphère standard internationale (ISA)", fontweight="bold")
    _save(fig, FIGURES / "01_atmosphere_ISA")


def figure_grandeurs_vitesse() -> None:
    """Les quatre vitesses vs altitude, à Mach constant (divergence)."""
    _style()
    fig, ax = plt.subplots(figsize=(6.5, 5))
    model = AtmosphereModel.isa()
    zp_ft = np.linspace(0.0, 45000.0, 200)
    mach = 0.78
    cas, eas, tas = [], [], []
    for zp in zp_ft:
        st = model.state_from_pressure_altitude(units.feet_to_metres(zp))
        s = airspeeds(st.p, st.t, mach=mach)
        cas.append(units.mps_to_knots(s.cas))
        eas.append(units.mps_to_knots(s.eas))
        tas.append(units.mps_to_knots(s.tas))
    _plot(ax, cas, zp_ft, color="#1f77b4", label="Vc (CAS)")
    _plot(ax, eas, zp_ft, color="#2ca02c", label="EAS")
    _plot(ax, tas, zp_ft, color="#e03a3e", label="TAS")
    ax.set_xlabel("Vitesse Vc / EAS / TAS (kt)")
    ax.set_ylabel("Altitude-pression zp (ft)")
    ax.set_title(f"Vitesses à Mach {mach} constant (ISA)", loc="left")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", fontsize=9)
    _save(fig, FIGURES / "02_grandeurs_vitesse")


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    figure_atmosphere_isa()
    figure_grandeurs_vitesse()
    print(f"Figures écrites dans {FIGURES}")


if __name__ == "__main__":
    main()
