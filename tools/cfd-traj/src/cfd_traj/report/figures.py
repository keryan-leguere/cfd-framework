"""Figures Matplotlib, en français.

Trois figures, chacune répondant à une question qu'on se pose vraiment :

* **le nuage** — le tube réellement balayé se voit-il à l'intérieur de
  l'hyperrectangle min/max ? C'est l'argument visuel de toute la démarche ;
* **l'ACP** — combien de directions le nuage occupe-t-il vraiment ?
* **le plan** — où tombent les nœuds par rapport au nuage, et que coûtent-ils ?

Le rendu passe par ``cfd_plot`` quand il est installé, et retombe sur
Matplotlib nu sinon (voir :mod:`cfd_traj.report._plotting_lib`). ``cfd_plot``
n'expose pas d'aide au nuage de points : les ``scatter`` sont donc appelés
directement, le style restant cohérent puisque ``use_style`` agit sur les
rcParams.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from cfd_traj._compat import zip_strict
from cfd_traj.core.symmetry import CalcConfig
from cfd_traj.data.dataset import TrajectoryDataset
from cfd_traj.engine.coverage import CoverageResult
from cfd_traj.engine.doe import DoePlan
from cfd_traj.engine.envelope import Envelope
from cfd_traj.engine.inspect import Inspection
from cfd_traj.report._plotting_lib import get_plotting

COULEUR_NUAGE = "#7A8B99"
COULEUR_TUBE = "#0B6FA4"
COULEUR_RECTANGLE = "#D1495B"
COULEUR_NOEUD = "#1B998B"
COULEUR_COIN = "#E07A1F"
COULEUR_FAUTIF = "#D1495B"

#: Au-delà, le nuage est sous-échantillonné : un PNG ne montre pas un million
#: de points, il montre une tache.
MAX_POINTS = 20_000

#: Noms lisibles des configurations de calcul, pour les axes.
CONFIG_LABEL: dict[CalcConfig, str] = {
    CalcConfig.AXI_2D: "axisymétrique 2D",
    CalcConfig.SECTEUR_45: "secteur 45°",
    CalcConfig.QUART_90: "quart 90° cyclique",
    CalcConfig.DEMI: "demi-configuration",
    CalcConfig.COMPLETE: "configuration complète",
}


def _fr(x: float, _pos: int = 0) -> str:
    """Étiquette d'axe à la française."""
    text = f"{x:,.4g}".replace(",", " ")
    return text.replace(".", ",")


def _use_style(profile: str = "paper") -> None:
    plotting = get_plotting()
    if plotting is not None:
        plotting.use_style(profile)


def _finish(
    ax: Axes,
    *,
    xlabel: str,
    ylabel: str,
    title: str = "",
    numeric_x: bool = True,
    numeric_y: bool = True,
) -> None:
    """Habillage commun d'un axe.

    ``numeric_x`` / ``numeric_y`` valent False sur un axe catégoriel : le
    formateur numérique y écraserait les étiquettes de bande par des indices.
    """
    plotting = get_plotting()
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if title:
        if plotting is not None:
            plotting.set_title(ax, title)
        else:
            ax.set_title(title)
    if numeric_x:
        ax.xaxis.set_major_formatter(FuncFormatter(_fr))
    if numeric_y:
        ax.yaxis.set_major_formatter(FuncFormatter(_fr))
    if plotting is not None:
        plotting.apply_oldschool_axes(ax, legend=False)
    ax.grid(True, alpha=0.25, linewidth=0.6)


def _thin(values: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Indices d'un sous-échantillon lisible."""
    n = values.shape[0]
    if n <= MAX_POINTS:
        return np.arange(n)
    return np.sort(rng.choice(n, MAX_POINTS, replace=False))


def _pick_ordinate(envelope: Envelope) -> str:
    """La variable la plus parlante face au Mach : une générique si possible."""
    reserved = {"Mach", "phi_fold", "Re_ref"}
    for spec in envelope.specs:
        if (
            spec.is_active
            and spec.is_grid_axis
            and spec.name not in reserved
            and spec.name != "alpha_tot"
        ):
            return spec.name
    return "alpha_tot"


# --- nuage et enveloppe ----------------------------------------------------


def plot_envelope(
    ds: TrajectoryDataset, envelope: Envelope, *, title: str = "", ordinate: str = ""
) -> Figure:
    """Le nuage, le tube conditionnel et l'hyperrectangle min/max qu'il remplace."""
    _use_style()
    name = ordinate or _pick_ordinate(envelope)
    rng = np.random.default_rng(0)

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.6), constrained_layout=True)
    mach = ds.values("Mach")
    values = ds.values(name)
    keep = _thin(mach, rng)

    ax = axes[0]
    ax.scatter(
        mach[keep],
        values[keep],
        s=3,
        c=COULEUR_NUAGE,
        alpha=0.35,
        linewidths=0,
        zorder=1,
        label="points de trajectoire",
    )

    finite = np.isfinite(mach) & np.isfinite(values)
    if finite.any():
        x0, x1 = float(mach[finite].min()), float(mach[finite].max())
        y0, y1 = float(values[finite].min()), float(values[finite].max())
        ax.plot(
            [x0, x1, x1, x0, x0],
            [y0, y0, y1, y1, y0],
            color=COULEUR_RECTANGLE,
            linestyle="--",
            linewidth=1.4,
            zorder=3,
            label="hyperrectangle min/max",
        )

    lows, highs, centres = [], [], []
    for band in envelope.bands:
        variable = band.get(name)
        if variable is None:
            continue
        centres.append(band.band.mid)
        lows.append(variable.bounds.low)
        highs.append(variable.bounds.high)
        ax.plot(
            [band.band.mach_low, band.band.mach_high],
            [variable.bounds.low] * 2,
            color=COULEUR_TUBE,
            linewidth=2.0,
            zorder=4,
        )
        ax.plot(
            [band.band.mach_low, band.band.mach_high],
            [variable.bounds.high] * 2,
            color=COULEUR_TUBE,
            linewidth=2.0,
            zorder=4,
        )
    if centres:
        ax.fill_between(
            centres,
            lows,
            highs,
            color=COULEUR_TUBE,
            alpha=0.12,
            zorder=2,
            label="enveloppe conditionnelle",
        )

    _finish(ax, xlabel="Mach", ylabel=name, title="Le tube réel dans l'hyperrectangle")
    ax.legend(loc="best", fontsize="small", framealpha=0.9)

    ax = axes[1]
    widths_band = [h - low for low, h in zip_strict(lows, highs)] if lows else []
    if finite.any() and widths_band:
        global_width = y1 - y0
        ratios = [w / global_width if global_width > 0 else 1.0 for w in widths_band]
        ax.bar(
            range(len(ratios)),
            ratios,
            color=COULEUR_TUBE,
            edgecolor="0.15",
            linewidth=0.7,
            zorder=2,
        )
        ax.axhline(1.0, color=COULEUR_RECTANGLE, linestyle="--", linewidth=1.4, zorder=3)
        ax.set_xticks(range(len(ratios)))
        ax.set_xticklabels(
            [b.band.label for b in envelope.bands], rotation=45, ha="right", fontsize="x-small"
        )
    _finish(
        ax,
        xlabel="bande de Mach",
        ylabel=f"largeur de {name} / largeur globale",
        title="Ce que le conditionnement fait gagner",
        numeric_x=False,
    )

    if title:
        plotting = get_plotting()
        if plotting is not None:
            plotting.set_suptitle(fig, title)
        else:
            fig.suptitle(title)
    return fig


# --- analyse en composantes principales ------------------------------------


def plot_inspection(inspection: Inspection, *, title: str = "") -> Figure:
    """Éboulis des valeurs propres et carte des corrélations."""
    _use_style()
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.6), constrained_layout=True)

    ax = axes[0]
    if inspection.pca is not None and inspection.pca.explained_variance_ratio.size:
        pca = inspection.pca
        index = np.arange(1, pca.explained_variance_ratio.size + 1)
        ax.bar(
            index, pca.explained_variance_ratio, color=COULEUR_TUBE, edgecolor="0.15", linewidth=0.7
        )
        ax.plot(index, pca.cumulative, color=COULEUR_COIN, marker="o", markersize=4, linewidth=1.6)
        ax.axhline(pca.threshold, color=COULEUR_RECTANGLE, linestyle="--", linewidth=1.2)
        ax.axvline(pca.intrinsic_dimension, color=COULEUR_NOEUD, linestyle=":", linewidth=1.6)
        ax.set_xticks(index)
        ax.set_ylim(0.0, 1.05)
        subtitle = f"dimension intrinsèque : {pca.intrinsic_dimension} / {pca.n_used}"
    else:
        ax.text(0.5, 0.5, "ACP indisponible", ha="center", va="center", transform=ax.transAxes)
        subtitle = "ACP indisponible"
    _finish(
        ax,
        xlabel="composante principale",
        ylabel="variance expliquée",
        title=subtitle,
        numeric_x=False,
    )

    ax = axes[1]
    names = inspection.correlation_names
    if names:
        image = ax.imshow(inspection.correlation, cmap="RdBu_r", vmin=-1.0, vmax=1.0)
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, rotation=45, ha="right", fontsize="x-small")
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize="x-small")
        fig.colorbar(image, ax=ax, shrink=0.85, label="corrélation")
    ax.set_title("Corrélations")
    ax.grid(False)

    if title:
        fig.suptitle(title)
    return fig


# --- plan ------------------------------------------------------------------


def plot_plan(
    plan: DoePlan, ds: TrajectoryDataset | None = None, *, title: str = "", ordinate: str = ""
) -> Figure:
    """Les nœuds du plan posés sur le nuage, et le coût par configuration."""
    _use_style()
    name = ordinate or _pick_ordinate(plan.envelope)
    rng = np.random.default_rng(0)

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.6), constrained_layout=True)

    ax = axes[0]
    if ds is not None:
        mach = ds.values("Mach")
        values = ds.values(name)
        keep = _thin(mach, rng)
        ax.scatter(
            mach[keep],
            values[keep],
            s=3,
            c=COULEUR_NUAGE,
            alpha=0.25,
            linewidths=0,
            zorder=1,
            label="trajectoires",
        )

    ordinary = [n for n in plan.nodes if not n.is_corner]
    corners = [n for n in plan.nodes if n.is_corner]
    for nodes, colour, label, size in (
        (ordinary, COULEUR_NOEUD, "nœuds", 18),
        (corners, COULEUR_COIN, "coins du domaine", 26),
    ):
        if not nodes:
            continue
        xs = [n.values.get("Mach", np.nan) for n in nodes]
        ys = [n.values.get(name, np.nan) for n in nodes]
        ax.scatter(
            xs,
            ys,
            s=size,
            c=colour,
            marker="o",
            edgecolors="white",
            linewidths=0.5,
            zorder=3 if colour == COULEUR_NOEUD else 4,
            label=label,
        )
    _finish(ax, xlabel="Mach", ylabel=name, title=f"{plan.n_nodes} cas de calcul")
    ax.legend(loc="best", fontsize="small", framealpha=0.9)

    ax = axes[1]
    breakdown = plan.cost_by_config()
    labels = [CONFIG_LABEL[c] for c in breakdown]
    costs = [cost for _, cost in breakdown.values()]
    counts = [count for count, _ in breakdown.values()]
    positions = np.arange(len(labels))
    # Grouped, not stacked: on the full configuration the two are equal, and
    # overlaying them would hide one bar entirely.
    height = 0.38
    ax.barh(
        positions + height / 2,
        counts,
        height=height,
        color=COULEUR_NUAGE,
        edgecolor="0.15",
        linewidth=0.7,
        label="cas",
    )
    ax.barh(
        positions - height / 2,
        costs,
        height=height,
        color=COULEUR_NOEUD,
        edgecolor="0.15",
        linewidth=0.7,
        label="coût",
    )
    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontsize="x-small")
    _finish(
        ax,
        xlabel="cas et équivalents configuration complète",
        ylabel="",
        title=f"économie {100.0 * plan.saving:.0f} %".replace(".", ","),
        numeric_y=False,
    )
    ax.legend(loc="lower right", fontsize="small", framealpha=0.9)

    if title:
        fig.suptitle(title)
    return fig


# --- couverture ------------------------------------------------------------


def plot_coverage(result: CoverageResult, *, title: str = "") -> Figure:
    """Taux de couverture par bande, et variables fautives."""
    _use_style()
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.6), constrained_layout=True)

    ax = axes[0]
    positions = np.arange(len(result.bands))
    rates = [b.rate for b in result.bands]
    colours = [COULEUR_NOEUD if r >= 1.0 else COULEUR_FAUTIF for r in rates]
    ax.bar(positions, rates, color=colours, edgecolor="0.15", linewidth=0.7)
    ax.axhline(1.0, color=COULEUR_TUBE, linestyle="--", linewidth=1.2)
    ax.set_xticks(positions)
    ax.set_xticklabels(
        [b.band.label for b in result.bands], rotation=45, ha="right", fontsize="x-small"
    )
    ax.set_ylim(min([*rates, 0.9]) - 0.01, 1.005)
    _finish(
        ax,
        xlabel="bande de Mach",
        ylabel="taux de couverture",
        title=f"couverture globale {100.0 * result.rate:.2f} %".replace(".", ","),
        numeric_x=False,
    )

    ax = axes[1]
    failures = result.failures_by_variable()
    if failures:
        names = list(failures)
        counts = [failures[n] for n in names]
        ax.barh(
            np.arange(len(names)),
            counts,
            height=0.6,
            color=COULEUR_FAUTIF,
            edgecolor="0.15",
            linewidth=0.7,
        )
        ax.set_yticks(np.arange(len(names)))
        ax.set_yticklabels(names, fontsize="x-small")
        # A single category would otherwise stretch its bar over the whole axis.
        ax.set_ylim(-0.6, len(names) - 0.4)
    else:
        ax.text(
            0.5, 0.5, "aucun point hors bornes", ha="center", va="center", transform=ax.transAxes
        )
    _finish(ax, xlabel="points hors bornes", ylabel="", title="Variables fautives", numeric_y=False)

    if title:
        fig.suptitle(title)
    return fig


# --- écriture --------------------------------------------------------------


def save_figure(fig: Figure, path: str | Path, *, dpi: int = 160) -> Path:
    """Écrit une figure et rend le chemin produit."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    plotting = get_plotting()
    suffix = out.suffix.lstrip(".") or "png"
    if plotting is not None:
        plotting.save_figure(
            fig, str(out.with_suffix("")), formats=(suffix,), dpi=dpi, report=False
        )
    else:
        fig.savefig(out, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out
