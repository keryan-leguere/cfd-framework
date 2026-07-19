"""Matplotlib figures for cfd-atm, built on the in-house ``plotting`` package
when available (falling back to plain Matplotlib otherwise).

Three figures illustrate the airspeed-reconstruction subtlety documented in
``00_DOC/02_GRANDEURS_VITESSE.md``:

- diagram A : iso-Vc on Mach vs **geometric** altitude — the temperature model
  shifts the curves (via the hydrostatic pressure law);
- diagram B : iso-Vc (single, temperature-invariant) + iso-TAS (per model) on
  Mach vs **pressure** altitude;
- the temperature profiles themselves.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from numpy.typing import NDArray

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from cfd_atm.core import airspeed, isa
from cfd_atm.core.altitudes import pressure_altitude
from cfd_atm.core.atmosphere import AtmosphereModel
from cfd_atm.core.constants import R_AIR
from cfd_atm.core.isa import geopotential_from_pressure
from cfd_atm.report import units
from cfd_atm.report._plotting_lib import get_plotting

_plotting = get_plotting()

# Value families and grids (SI internally).
_CAS_KT = (150.0, 250.0, 350.0)
_TAS_KT = (300.0, 500.0)
_Z_MAX_FT = 45000.0
_MODEL_COLORS = {
    "ISA": "#1f77b4",
    "chaud": "#e03a3e",
    "froid": "#2ca02c",
    "custom": "#9467bd",
}


def _use_style(profile: str) -> None:
    if _plotting is not None:
        _plotting.use_style(profile)


def _plot(ax: Any, x: Any, y: Any, **kwargs: Any) -> Any:
    if _plotting is not None:
        return _plotting.plot_line(ax, x, y, marker="", **kwargs)
    return ax.plot(x, y, **kwargs)[0]


def _save(fig: Any, base: Path) -> list[Path]:
    if _plotting is not None:
        return list(_plotting.save_figure(fig, str(base), formats=("png", "svg")))
    png = base.with_suffix(".png")
    fig.savefig(png, dpi=150, bbox_inches="tight")
    return [png]


def _title(ax: Any, text: str) -> None:
    if _plotting is not None:
        _plotting.set_title(ax, text, loc="left")
    else:
        ax.set_title(text, loc="left")


def _legend_line(color: str, *, linestyle: Any = "-", lw: float = 1.6, label: str = "") -> Any:
    from matplotlib.lines import Line2D

    return Line2D([0], [0], color=color, lw=lw, linestyle=linestyle, label=label)


def _temperature_at_pressure_altitude(
    model: AtmosphereModel, zp: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Temperature (K) at each pressure altitude, in the altimetric sense."""
    p = isa.isa_pressure(zp)
    h = geopotential_from_pressure(p)
    return model.temperature(h)


def _build_models(
    delta_plus: float, delta_moins: float, custom: AtmosphereModel | None
) -> dict[str, AtmosphereModel]:
    models: dict[str, AtmosphereModel] = {
        "ISA": AtmosphereModel.isa(),
        "chaud": AtmosphereModel.isa_offset(delta_plus),
        "froid": AtmosphereModel.isa_offset(delta_moins),
    }
    if custom is not None:
        models["custom"] = custom
    return models


# --- Diagram A : iso-Vc vs geometric altitude ------------------------------


def diagramme_A(sortie: Path, models: dict[str, AtmosphereModel]) -> list[Path]:
    """iso-Vc on Mach vs geometric altitude; the models diverge."""
    _use_style("paper")
    fig, ax = plt.subplots(figsize=(8, 6))
    z_ft = np.linspace(0.0, _Z_MAX_FT, 250)
    z_m = z_ft * units.METRES_PER_FOOT

    linestyles = ["-", "--", ":", "-."]
    cas_ls = {cas: linestyles[i % len(linestyles)] for i, cas in enumerate(_CAS_KT)}

    for name, model in models.items():
        p = model.pressure_at_geometric(z_m)
        color = _MODEL_COLORS.get(name, "#555555")
        for cas_kt in _CAS_KT:
            cas = units.knots_to_mps(cas_kt)
            mach = airspeed.mach_from_cas(cas, p)
            _plot(ax, mach, z_ft, color=color, linestyle=cas_ls[cas_kt], linewidth=1.4)

    ax.set_xlabel("Nombre de Mach M")
    ax.set_ylabel("Altitude géométrique z (ft)")
    ax.set_xlim(left=0.0)
    ax.grid(True, alpha=0.3)
    _title(ax, "Diagramme A — iso-Vc vs altitude géométrique")
    ax.text(
        0.02,
        0.02,
        "Les modèles de T° divergent :\nla pression à z fixé dépend du profil.",
        transform=ax.transAxes,
        fontsize=8,
        va="bottom",
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.8, "edgecolor": "0.7"},
    )

    model_handles = [
        _legend_line(_MODEL_COLORS.get(n, "#555555"), label=m.label) for n, m in models.items()
    ]
    cas_handles = [
        _legend_line("0.3", linestyle=cas_ls[c], lw=1.4, label=f"Vc = {c:.0f} kt") for c in _CAS_KT
    ]
    leg1 = ax.legend(handles=model_handles, title="Modèle T°", loc="upper right", fontsize=8)
    ax.add_artist(leg1)
    ax.legend(handles=cas_handles, title="iso-Vc", loc="lower right", fontsize=8)

    return _save(fig, sortie / "diagramme_A_isoVc_altitude_geometrique")


# --- Diagram B : iso-Vc + iso-TAS vs pressure altitude ---------------------


def diagramme_B(sortie: Path, models: dict[str, AtmosphereModel]) -> list[Path]:
    """iso-Vc (single) + iso-TAS (per model) on Mach vs pressure altitude."""
    _use_style("paper")
    fig, ax = plt.subplots(figsize=(8, 6))
    zp_ft = np.linspace(0.0, _Z_MAX_FT, 250)
    zp_m = zp_ft * units.METRES_PER_FOOT
    p = isa.isa_pressure(zp_m)

    # iso-Vc: temperature-invariant, drawn once in grey.
    for cas_kt in _CAS_KT:
        cas = units.knots_to_mps(cas_kt)
        mach = airspeed.mach_from_cas(cas, p)
        line = _plot(ax, mach, zp_ft, color="0.35", linestyle="-", linewidth=1.3)
        ax.annotate(
            f"Vc {cas_kt:.0f} kt",
            xy=(float(mach[-1]), zp_ft[-1]),
            fontsize=7,
            color="0.35",
            ha="center",
            va="bottom",
        )
        del line

    # iso-TAS: temperature-dependent, one colour per model.
    tas_ls = {tas: ("--" if i == 0 else ":") for i, tas in enumerate(_TAS_KT)}
    for name, model in models.items():
        if name == "custom":
            continue
        t = _temperature_at_pressure_altitude(model, zp_m)
        color = _MODEL_COLORS.get(name, "#555555")
        for tas_kt in _TAS_KT:
            tas = units.knots_to_mps(tas_kt)
            mach = airspeed.mach_from_tas(tas, t)
            _plot(ax, mach, zp_ft, color=color, linestyle=tas_ls[tas_kt], linewidth=1.4)

    ax.set_xlabel("Nombre de Mach M")
    ax.set_ylabel("Altitude-pression zp (ft)")
    ax.set_xlim(left=0.0)
    ax.grid(True, alpha=0.3)
    _title(ax, "Diagramme B — iso-Vc (fixes) et iso-TAS (selon T°)")

    handles = [_legend_line("0.35", lw=1.3, label="iso-Vc (indép. de T°)")]
    handles += [
        _legend_line(_MODEL_COLORS.get(n, "#555555"), label=f"iso-TAS {m.label}")
        for n, m in models.items()
        if n != "custom"
    ]
    handles += [
        _legend_line("0.3", linestyle=tas_ls[t], lw=1.4, label=f"TAS {t:.0f} kt") for t in _TAS_KT
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=7.5)

    return _save(fig, sortie / "diagramme_B_isoVc_isoTAS_altitude_pression")


# --- T, p, rho profiles of every model -------------------------------------


def diagramme_modeles_atmosphere(sortie: Path, models: dict[str, AtmosphereModel]) -> list[Path]:
    """T, p, rho versus altitude for every model (ISA-reference style, overlaid)."""
    _use_style("paper")
    fig, axes = plt.subplots(1, 3, figsize=(12, 5), sharey=True)
    z_ft = np.linspace(0.0, _Z_MAX_FT, 300)
    h_m = z_ft * units.METRES_PER_FOOT  # treated as geopotential altitude

    for name, model in models.items():
        color = _MODEL_COLORS.get(name, "#555555")
        t_k = model.temperature(h_m)
        p_pa = model.pressure_geopotential(h_m)
        rho = p_pa / (R_AIR * t_k)
        _plot(axes[0], t_k - 273.15, z_ft, color=color, linewidth=1.6, label=model.label)
        _plot(axes[1], p_pa / 100.0, z_ft, color=color, linewidth=1.6, label=model.label)
        _plot(axes[2], rho, z_ft, color=color, linewidth=1.6, label=model.label)

    axes[0].set_xlabel("Température T (°C)")
    axes[0].set_ylabel("Altitude géopotentielle H (ft)")
    axes[1].set_xlabel("Pression p (hPa)")
    axes[2].set_xlabel("Densité ρ (kg/m³)")
    for ax in axes:
        ax.grid(True, alpha=0.3)
    axes[0].legend(loc="upper right", fontsize=8, title="Modèle (ISA±ΔT = décalage T° constant)")
    fig.suptitle(
        "Profils atmosphériques par modèle — ISA, ISA±35 (±35 K), profil custom",
        fontweight="bold",
    )
    return _save(fig, sortie / "modeles_T_p_rho")


# --- Reading the pressure altitude from the geopotential altitude ----------


def diagramme_lecture_zp(
    sortie: Path, models: dict[str, AtmosphereModel], *, h_entree_ft: float = 30000.0
) -> list[Path]:
    """Show how to read the pressure altitude ``zp`` from a geopotential altitude.

    Altitude ``H`` is on the y-axis. Entering at a fixed ``H`` (horizontal line)
    meets a non-ISA model curve at its pressure ``p(H)``; a vertical
    constant-pressure segment drops to the ISA curve, and the horizontal line
    there reads ``zp`` on the y-axis — the ISA altitude of that same pressure.
    """
    _use_style("paper")
    fig, ax = plt.subplots(figsize=(8.5, 7))
    alt_ft = np.linspace(0.0, _Z_MAX_FT, 300)
    h_m = alt_ft * units.METRES_PER_FOOT

    for name, model in models.items():
        color = _MODEL_COLORS.get(name, "#555555")
        lw = 2.2 if name == "ISA" else 1.4
        _plot(ax, model.pressure_geopotential(h_m) / 100.0, alt_ft, color=color, linewidth=lw, label=model.label)

    ax.set_xscale("log")
    ax.set_xlabel("Pression p (hPa)")
    ax.set_ylabel("Altitude géopotentielle H, zp (ft)")
    ax.set_ylim(0.0, _Z_MAX_FT)
    p_left = float(isa.isa_pressure(_Z_MAX_FT * units.METRES_PER_FOOT)) / 100.0
    ax.set_xlim(p_left * 0.9, 1100.0)
    ax.grid(True, which="both", alpha=0.25)

    # Common entry: the geopotential altitude H (grey horizontal guide).
    h0_m = h_entree_ft * units.METRES_PER_FOOT
    ax.axhline(h_entree_ft, color="0.45", linestyle=":", linewidth=1.0, zorder=1)
    ax.annotate(
        f"entrée : H = {h_entree_ft:,.0f} ft",
        xy=(1080.0, h_entree_ft),
        fontsize=8,
        color="0.3",
        ha="right",
        va="bottom",
    )

    # For each non-ISA model: vertical constant-pressure segment H -> ISA, then
    # a horizontal line reads zp on the y-axis.
    for name in ("chaud", "froid", "custom"):
        if name not in models:
            continue
        model = models[name]
        color = _MODEL_COLORS.get(name, "#555555")
        p0 = float(model.pressure_geopotential(h0_m))  # Pa
        zp_ft = float(pressure_altitude(p0)) / units.METRES_PER_FOOT
        p0_hpa = p0 / 100.0
        # vertical constant-pressure segment from the model point to the ISA curve
        ax.plot([p0_hpa, p0_hpa], [h_entree_ft, zp_ft], color=color, linestyle=":", linewidth=1.1)
        ax.plot([p0_hpa], [h_entree_ft], marker="o", color=color, markersize=5)  # model point (H)
        # horizontal read-off line: from the ISA point to the y-axis
        ax.plot([p_left * 0.9, p0_hpa], [zp_ft, zp_ft], color=color, linestyle="--", linewidth=1.3)
        ax.plot([p0_hpa], [zp_ft], marker="s", color=color, markersize=5)  # ISA point (zp)
        ax.annotate(
            f"zp = {zp_ft:,.0f} ft  ({model.label})",
            xy=(p_left * 0.95, zp_ft),
            xytext=(3, 3),
            textcoords="offset points",
            fontsize=8,
            color=color,
            ha="left",
            va="bottom",
        )

    _title(ax, "Lecture de l'altitude-pression zp depuis l'altitude géopotentielle H")
    ax.legend(loc="lower left", fontsize=8, title="Modèle T°")
    return _save(fig, sortie / "lecture_altitude_pression")


def generer_diagrammes(
    sortie: Path,
    *,
    custom: AtmosphereModel | None = None,
    delta_plus: float = 35.0,
    delta_moins: float = -35.0,
) -> list[Path]:
    """Generate every figure into ``sortie`` and return the written paths."""
    sortie.mkdir(parents=True, exist_ok=True)
    models = _build_models(delta_plus, delta_moins, custom)
    written: list[Path] = []
    written += diagramme_A(sortie, models)
    written += diagramme_B(sortie, models)
    written += diagramme_modeles_atmosphere(sortie, models)
    written += diagramme_lecture_zp(sortie, models)
    return written
