"""Matplotlib figures, built on the in-house ``cfd_plot`` package.

``cfd-plot`` is the framework's figure library: it carries the house style,
the marker and line conventions, and ``save_figure``. cfd-aq routes every
primitive through it — the new figure, each curve, the reference lines, the
save — and falls back to plain Matplotlib when it is absent, so the package
stays deployable on its own. :func:`sortie_graphique` says which of the two
is in use.

Four figures, all labelled in French:

- the three geometries, with the notation the correlations use (h, t, r, θ, α);
- the drag ratio against the roughness Reynolds number, which is the form the
  AGARDograph plots its raw data in (Figures 4.23, 4.28, 4.34);
- the drag ratio against Mach number at a fixed h⁺, where the transonic
  behaviour the three shapes do *not* share becomes visible;
- the shape corrections — rounding, chamfer, ridge thickness, sweep.

They are drawn from the package's own tables, so they double as a visual
check that the digitisation reproduces the source plots. To superpose them on
the scans themselves, see ``00_DOC/verifier_numerisation.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.patches import Arc, Polygon

from cfd_aq.core import donnees, marches
from cfd_aq.report._plotting_lib import get_plotting

__all__ = [
    "enregistrer",
    "sortie_graphique",
    "tracer_corrections",
    "tracer_effet_mach",
    "tracer_geometries",
    "tracer_rapports",
]

_plotting = get_plotting()

# Sept teintes : la Figure 4.28 porte sept Mach, la 4.33 six.
_COULEURS = (
    "#1f77b4",
    "#d62728",
    "#2ca02c",
    "#9467bd",
    "#ff7f0e",
    "#17becf",
    "#8c564b",
)
_PAROI = "#1b1b1b"
_METAL = "#c8d6e5"


def sortie_graphique() -> str:
    """Which backend the figures go through: ``"cfd-plot"`` or ``"matplotlib"``."""
    return "cfd-plot" if _plotting is not None else "matplotlib"


# --- passerelle vers cfd-plot ---------------------------------------------


def _nouvelle_figure(nrows: int = 1, ncols: int = 1, **kwargs: Any) -> tuple[Figure, Any]:
    if _plotting is not None:
        figure, axes = _plotting.new_figure(nrows, ncols, profile="paper", **kwargs)
        return figure, axes
    figure, axes = plt.subplots(nrows, ncols, **kwargs)
    return figure, axes


def _tracer(axe: Any, x: Any, y: Any, **kwargs: Any) -> Any:
    """One curve. ``marker=""`` by default: these are 200-point analytic lines."""
    kwargs.setdefault("marker", "")
    if _plotting is not None:
        return _plotting.plot_line(axe, x, y, **kwargs)
    return axe.plot(x, y, **kwargs)[0]


def _lignes_reference(axe: Any, **kwargs: Any) -> None:
    if _plotting is not None:
        _plotting.add_reference_lines(axe, **kwargs)
        return
    for y in kwargs.get("hlines") or []:
        axe.axhline(y, color="0.4", linewidth=0.8, linestyle="--", zorder=0)
    for x in kwargs.get("vlines") or []:
        axe.axvline(x, color="0.4", linewidth=0.8, linestyle="--", zorder=0)


def enregistrer(figure: Figure, chemin: Path, dpi: int | None = None) -> Path:
    """Write ``figure`` to ``chemin``, creating the parent directory.

    ``dpi`` overrides the style's own resolution — cfd-plot's "paper" profile
    is sized for print, which is four times more than a README needs.
    """
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    if _plotting is not None:
        # save_figure compose le nom avec Path.with_suffix : on lui donne la
        # base sans extension pour qu'il ne mange pas un morceau du nom.
        ecrits = _plotting.save_figure(
            figure,
            chemin.with_suffix(""),
            formats=(chemin.suffix.lstrip(".") or "png",),
            dpi=dpi,
        )
        plt.close(figure)
        return Path(ecrits[0])
    figure.savefig(chemin, dpi=dpi or 150, bbox_inches="tight")
    plt.close(figure)
    return chemin


# --- les géométries -------------------------------------------------------


def _hachures_paroi(axe: Any, x0: float, x1: float, y: float, vers_le_bas: bool = True) -> None:
    """The hatched ground line of an aerodynamics sketch."""
    axe.plot([x0, x1], [y, y], color=_PAROI, linewidth=1.8, zorder=3)
    pas = (x1 - x0) / 26.0
    sens = -1.0 if vers_le_bas else 1.0
    x = x0
    while x < x1:
        axe.plot(
            [x, x + pas * 0.6],
            [y, y + sens * pas * 0.6],
            color=_PAROI,
            linewidth=0.7,
            zorder=3,
        )
        x += pas


def tracer_geometries() -> Figure:
    """The three shapes and the three corrections, with their symbols.

    Top row: a forward step raises the surface, a rearward one lowers it, a
    ridge does both within a short distance — and that last one is not the sum
    of the other two (§4.3.2.1). Bottom row: the edge treatments the
    correlations correct for, and the sweep angle.
    """
    figure, axes = _nouvelle_figure(2, 3, figsize=(13.0, 7.0))

    def fleche_ecoulement(axe: Any, x0: float, y: float) -> None:
        axe.annotate(
            "",
            xy=(x0 + 0.22, y),
            xytext=(x0, y),
            arrowprops={"arrowstyle": "->", "color": _PAROI, "linewidth": 1.3},
        )
        axe.text(x0 + 0.11, y + 0.045, "écoulement", ha="center", fontsize=8)

    def cote(
        axe: Any, x: float, y0: float, y1: float, texte: str, couleur: str, a_gauche: bool = True
    ) -> None:
        axe.annotate(
            "",
            xy=(x, y1),
            xytext=(x, y0),
            arrowprops={"arrowstyle": "<->", "color": couleur, "linewidth": 1.4},
            zorder=8,
        )
        axe.text(
            x - 0.035 if a_gauche else x + 0.035,
            0.5 * (y0 + y1),
            texte,
            color=couleur,
            ha="right" if a_gauche else "left",
            va="center",
            fontsize=13,
            zorder=8,
        )

    # --- 1. marche montante ---
    axe = axes[0, 0]
    _hachures_paroi(axe, 0.0, 1.0, 0.0)
    axe.add_patch(
        Polygon(
            [(0.5, 0.0), (1.0, 0.0), (1.0, 0.30), (0.5, 0.30)],
            closed=True,
            facecolor=_METAL,
            edgecolor=_PAROI,
            linewidth=1.8,
            zorder=4,
        )
    )
    cote(axe, 0.46, 0.0, 0.30, "h", _COULEURS[1])
    fleche_ecoulement(axe, 0.08, 0.17)
    axe.set_title("Marche montante\n§4.3.1.1 — Fig. 4.23, 4.25")

    # --- 2. marche descendante ---
    axe = axes[0, 1]
    axe.add_patch(
        Polygon(
            [(0.0, 0.0), (0.5, 0.0), (0.5, 0.30), (0.0, 0.30)],
            closed=True,
            facecolor=_METAL,
            edgecolor=_PAROI,
            linewidth=1.8,
            zorder=4,
        )
    )
    _hachures_paroi(axe, 0.5, 1.0, 0.0)
    axe.plot([0.0, 0.5], [0.30, 0.30], color=_PAROI, linewidth=1.8, zorder=5)
    cote(axe, 0.55, 0.0, 0.30, "h", _COULEURS[1], a_gauche=False)
    fleche_ecoulement(axe, 0.12, 0.42)
    axe.set_title("Marche descendante\n§4.3.1.2 — Fig. 4.28, 4.30")

    # --- 3. arête ---
    axe = axes[0, 2]
    _hachures_paroi(axe, 0.0, 1.0, 0.0)
    axe.add_patch(
        Polygon(
            [(0.42, 0.0), (0.70, 0.0), (0.70, 0.30), (0.42, 0.30)],
            closed=True,
            facecolor=_METAL,
            edgecolor=_PAROI,
            linewidth=1.8,
            zorder=4,
        )
    )
    cote(axe, 0.38, 0.0, 0.30, "h", _COULEURS[1])
    axe.annotate(
        "",
        xy=(0.70, 0.38),
        xytext=(0.42, 0.38),
        arrowprops={"arrowstyle": "<->", "color": _COULEURS[2], "linewidth": 1.4},
    )
    axe.text(0.56, 0.43, "t", color=_COULEURS[2], ha="center", fontsize=13)
    fleche_ecoulement(axe, 0.06, 0.17)
    axe.set_title("Arête\n§4.3.2 — Fig. 4.34, 4.38, 4.40")

    # --- 4. arrondi ---
    axe = axes[1, 0]
    _hachures_paroi(axe, 0.0, 1.0, 0.0)
    rayon = 0.14
    arrondi = [(0.5, 0.0), (1.0, 0.0), (1.0, 0.30), (0.5 + rayon, 0.30)]
    arrondi += [
        (0.5 + rayon - rayon * np.cos(t), 0.30 - rayon + rayon * np.sin(t))
        for t in np.linspace(np.pi / 2, 0.0, 24)
    ]
    axe.add_patch(
        Polygon(arrondi, closed=True, facecolor=_METAL, edgecolor=_PAROI, linewidth=1.8, zorder=4)
    )
    axe.add_patch(
        Arc(
            (0.5 + rayon, 0.30 - rayon),
            2 * rayon,
            2 * rayon,
            theta1=90.0,
            theta2=180.0,
            color=_COULEURS[0],
            linewidth=1.2,
            linestyle=":",
            zorder=6,
        )
    )
    axe.annotate(
        "",
        xy=(0.5 + rayon, 0.30),
        xytext=(0.5 + rayon, 0.30 - rayon),
        arrowprops={"arrowstyle": "<->", "color": _COULEURS[0], "linewidth": 1.3},
        zorder=8,
    )
    axe.text(
        0.5 + rayon + 0.03,
        0.30 - rayon / 2,
        "r",
        color=_COULEURS[0],
        ha="left",
        va="center",
        fontsize=13,
        zorder=8,
    )
    axe.plot(
        [0.5 + rayon, 0.5 + rayon],
        [0.30 - rayon, 0.30],
        color=_COULEURS[0],
        linewidth=0.8,
        linestyle=":",
        zorder=7,
    )
    cote(axe, 0.46, 0.0, 0.30, "h", _COULEURS[1])
    fleche_ecoulement(axe, 0.08, 0.17)
    axe.set_title("Arrondi d'arête, r/h\néq. 4(28) et 4(34) — Fig. 4.26(a), 4.32")

    # --- 5. chanfrein ---
    axe = axes[1, 1]
    _hachures_paroi(axe, 0.0, 1.0, 0.0)
    theta = np.radians(40.0)
    pied = 0.5 - 0.30 / np.tan(theta)
    axe.add_patch(
        Polygon(
            [(pied, 0.0), (1.0, 0.0), (1.0, 0.30), (0.5, 0.30)],
            closed=True,
            facecolor=_METAL,
            edgecolor=_PAROI,
            linewidth=1.8,
            zorder=4,
        )
    )
    axe.add_patch(
        Arc(
            (pied, 0.0),
            0.26,
            0.26,
            theta1=0.0,
            theta2=40.0,
            color=_COULEURS[0],
            linewidth=1.4,
            zorder=6,
        )
    )
    axe.text(pied + 0.17, 0.04, "θ", color=_COULEURS[0], fontsize=14, zorder=8)
    axe.plot([pied, 1.0], [0.0, 0.0], color=_COULEURS[0], linewidth=1.0, linestyle=":", zorder=5)
    cote(axe, 0.58, 0.0, 0.30, "h", _COULEURS[1], a_gauche=False)
    fleche_ecoulement(axe, 0.02, 0.45)
    axe.set_title("Chanfrein, θ\néq. 4(29) et 4(33) — Fig. 4.26(b), 4.33")

    # --- 6. dérapage (vue de dessus) ---
    axe = axes[1, 2]
    alpha = np.radians(55.0)
    longueur = 0.30
    centre = (0.50, 0.24)
    axe.plot(
        [centre[0] - longueur * np.cos(alpha), centre[0] + longueur * np.cos(alpha)],
        [centre[1] - longueur * np.sin(alpha), centre[1] + longueur * np.sin(alpha)],
        color=_PAROI,
        linewidth=4.0,
        solid_capstyle="butt",
        zorder=4,
    )
    axe.annotate(
        "",
        xy=(centre[0] + 0.30, centre[1]),
        xytext=(centre[0] - 0.40, centre[1]),
        arrowprops={"arrowstyle": "->", "color": _COULEURS[3], "linewidth": 1.5},
    )
    axe.add_patch(
        Arc(centre, 0.34, 0.34, theta1=0.0, theta2=55.0, color=_COULEURS[0], linewidth=1.4)
    )
    axe.text(centre[0] + 0.20, centre[1] + 0.05, "α", color=_COULEURS[0], fontsize=14)
    axe.text(centre[0] - 0.38, centre[1] + 0.05, "écoulement", color=_COULEURS[3], fontsize=8)
    axe.text(
        centre[0] + longueur * np.cos(alpha) + 0.04,
        centre[1] + longueur * np.sin(alpha),
        "aspérité",
        fontsize=8,
        va="center",
    )
    axe.set_title("Dérapage, α (vue de dessus)\néq. 4(30), 4(35), 4(41) — Fig. 4.45")

    for axe in axes.flat:
        axe.set_xlim(0.0, 1.0)
        axe.set_ylim(-0.14, 0.64)
        axe.set_aspect("equal")
        axe.axis("off")
    figure.suptitle("Géométries et corrections — AGARD-AG-264 §4.3")
    return figure


# --- les corrélations -----------------------------------------------------


def tracer_rapports(machs: Sequence[float] = (0.2, 0.8, 1.4, 2.0)) -> Figure:
    """CDe/Cfe against h⁺ for the three shapes, one panel each."""
    h_plus = np.logspace(np.log10(donnees.H_PLUS_MIN), np.log10(donnees.H_PLUS_MAX), 200)
    figure, axes = _nouvelle_figure(1, 3, figsize=(13.0, 4.2), sharey=True)
    panneaux = (
        ("Marche montante", marches.ratio_marche_montante),
        ("Marche descendante", marches.ratio_marche_descendante),
        ("Arête carrée (t = h)", marches.ratio_arete),
    )
    for axe, (titre, fonction) in zip(axes, panneaux):
        for couleur, mach in zip(_COULEURS, machs):
            _tracer(
                axe,
                h_plus,
                [fonction(float(x), mach) for x in h_plus],
                color=couleur,
                label=f"M = {mach:g}",
            )
        axe.set_xscale("log")
        axe.set_title(titre)
        axe.set_xlabel("h⁺ = u$_τ$·h/ν$_w$")
        axe.grid(True, which="both", alpha=0.3)
    axes[0].set_ylabel("CDe / Cfe")
    axes[0].legend(loc="upper left", fontsize="small")
    figure.suptitle("Traînée d'aspérité — AGARD-AG-264 §4.3")
    return figure


def tracer_effet_mach(h_plus: float = 1000.0) -> Figure:
    """CDe/Cfe against Mach number at a fixed h⁺.

    The three shapes behave differently through the transonic range: the
    forward step rises then plateaus, the rearward step peaks near M = 1.15
    and falls, the ridge peaks hardest of all (PC₃ reaches 1.59).
    """
    machs = np.linspace(0.2, 2.8, 400)
    figure, axe = _nouvelle_figure(figsize=(7.5, 4.6))
    courbes = (
        ("Marche montante", marches.ratio_marche_montante),
        ("Marche descendante", marches.ratio_marche_descendante),
        ("Arête carrée", marches.ratio_arete),
    )
    for couleur, (nom, fonction) in zip(_COULEURS, courbes):
        _tracer(axe, machs, [fonction(h_plus, float(m)) for m in machs], color=couleur, label=nom)
    _tracer(
        axe,
        machs,
        [
            marches.ratio_marche_montante(h_plus, float(m))
            + marches.ratio_marche_descendante(h_plus, float(m))
            for m in machs
        ],
        color="#555555",
        linestyle="--",
        label="Somme des deux marches",
    )
    _lignes_reference(axe, vlines=[1.0])
    axe.set_xlabel("Nombre de Mach local")
    axe.set_ylabel("CDe / Cfe")
    axe.set_title(f"Effet du Mach à h⁺ = {h_plus:g}")
    axe.grid(True, alpha=0.3)
    axe.legend(loc="upper left", fontsize="small")
    return figure


def tracer_corrections() -> Figure:
    """The four shape corrections, on one sheet."""
    figure, axes = _nouvelle_figure(2, 2, figsize=(11.0, 7.5))

    r_sur_h = np.linspace(0.0, 0.8, 100)
    for couleur, mach in zip(_COULEURS, sorted(donnees.ARRONDI_MONTANTE)):
        _tracer(
            axes[0, 0],
            r_sur_h,
            [marches.facteur_arrondi_montante(float(x), mach) for x in r_sur_h],
            color=couleur,
            label=f"M = {mach:g}",
        )
    axes[0, 0].set_title("Arrondi, marche montante — (1 − E)")
    axes[0, 0].set_xlabel("r/h")
    axes[0, 0].legend(fontsize="small")

    angles = np.linspace(0.0, 90.0, 181)
    for couleur, mach in zip(_COULEURS, sorted(donnees.CHANFREIN_MONTANTE)):
        _tracer(
            axes[0, 1],
            angles,
            [marches.facteur_chanfrein_montante(float(a), mach) for a in angles],
            color=couleur,
            label=f"M = {mach:g}",
        )
    axes[0, 1].set_title("Chanfrein, marche montante — (1 − E)")
    axes[0, 1].set_xlabel("θ [°]")
    axes[0, 1].legend(fontsize="small")

    for couleur, mach in zip(_COULEURS, sorted(donnees.CHANFREIN_DESCENDANTE)):
        _tracer(
            axes[1, 0],
            angles,
            [marches.facteur_chanfrein_descendante(float(a), mach) for a in angles],
            color=couleur,
            label=f"M = {mach:g}",
        )
    _lignes_reference(axes[1, 0], hlines=[1.0])
    axes[1, 0].set_title("Chanfrein, marche descendante — (1 − G)")
    axes[1, 0].set_xlabel("θ [°]")
    axes[1, 0].legend(fontsize="small")

    t_sur_h = np.linspace(0.0, 5.0, 200)
    _tracer(
        axes[1, 1],
        t_sur_h,
        [marches.facteur_epaisseur_arete(float(x)) for x in t_sur_h],
        color=_COULEURS[0],
        label="T(t/h), arête",
    )
    _tracer(
        axes[1, 1],
        angles / 90.0 * 5.0,
        [marches.facteur_derapage(float(a)) for a in angles],
        color=_COULEURS[1],
        linestyle="--",
        label="sin²α (α de 0 à 90°)",
    )
    _lignes_reference(axes[1, 1], hlines=[1.0])
    axes[1, 1].set_title("Épaisseur d'arête et dérapage")
    axes[1, 1].set_xlabel("t/h   —   α mis à l'échelle")
    axes[1, 1].legend(fontsize="small")

    for axe in axes.flat:
        axe.set_ylabel("facteur multiplicatif")
        axe.grid(True, alpha=0.3)
    figure.suptitle("Corrections de forme — AGARD-AG-264, Figures 4.26, 4.33, 4.40, 4.45")
    return figure
