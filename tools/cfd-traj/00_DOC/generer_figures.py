#!/usr/bin/env python3
"""Régénère les figures de la documentation dans 00_DOC/FIGURES/.

    python 00_DOC/generer_figures.py

Les figures sont versionnées ; ce script ne sert qu'à les reconstruire quand la
méthode ou le rendu changent. Il n'a pas besoin que le paquet soit installé :
il ajoute ``src/`` au chemin d'import lui-même.
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))

from cfd_traj.core.stats import quantile_bounds  # noqa: E402
from cfd_traj.core.symmetry import (  # noqa: E402
    SymmetryGroup,
    SymmetrySpec,
    azimuth_levels,
    fold_phi,
)
from cfd_traj.report._plotting_lib import get_plotting  # noqa: E402
from cfd_traj.report.figures import _finish  # noqa: E402

SORTIE = RACINE / "00_DOC" / "FIGURES"

BLEU = "#0B6FA4"
ROUGE = "#D1495B"
VERT = "#1B998B"
ORANGE = "#E07A1F"
GRIS = "#7A8B99"


def _style() -> None:
    plotting = get_plotting()
    if plotting is not None:
        plotting.use_style("paper")


def _save(fig, nom: str) -> Path:
    SORTIE.mkdir(parents=True, exist_ok=True)
    cible = SORTIE / nom
    fig.savefig(cible, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"écrit {cible.relative_to(RACINE)}")
    return cible


def figure_tube() -> None:
    """Pourquoi l'hyperrectangle min/max est le mauvais domaine."""
    _style()
    rng = np.random.default_rng(2026)

    # Un faisceau de trajectoires : le paramètre suit le Mach, avec dispersion.
    fig, ax = plt.subplots(figsize=(7.0, 4.4), constrained_layout=True)
    for _ in range(30):
        mach = np.linspace(0.3, 3.8, 200)
        pente = rng.normal(105.0, 8.0)
        offset = rng.normal(25.0, 12.0)
        ax.plot(mach, pente * mach + offset, color=GRIS, alpha=0.35, linewidth=0.8, zorder=1)

    x0, x1 = 0.3, 3.8
    y0, y1 = 0.0, 470.0
    ax.plot(
        [x0, x1, x1, x0, x0],
        [y0, y0, y1, y1, y0],
        color=ROUGE,
        linestyle="--",
        linewidth=1.6,
        zorder=4,
        label="hyperrectangle min/max",
    )

    bornes = np.linspace(0.3, 3.8, 8)
    for lo, hi in itertools.pairwise(bornes):
        milieu = 0.5 * (lo + hi)
        bas = 88.0 * milieu + 2.0
        haut = 122.0 * milieu + 52.0
        ax.plot([lo, hi], [bas, bas], color=BLEU, linewidth=2.2, zorder=5)
        ax.plot([lo, hi], [haut, haut], color=BLEU, linewidth=2.2, zorder=5)
    centres = 0.5 * (bornes[:-1] + bornes[1:])
    ax.fill_between(
        centres,
        88.0 * centres + 2.0,
        122.0 * centres + 52.0,
        color=BLEU,
        alpha=0.15,
        zorder=2,
        label="enveloppe conditionnelle",
    )

    ax.annotate(
        "coin jamais atteint",
        xy=(3.7, 450.0),
        xytext=(2.0, 430.0),
        arrowprops={"arrowstyle": "->", "color": ROUGE, "linewidth": 1.2},
        color=ROUGE,
        fontsize="small",
    )
    ax.annotate(
        "les vrais extrêmes\nsont ici, sur la frontière oblique",
        xy=(3.6, 490.0 * 0.86),
        xytext=(1.6, 320.0),
        arrowprops={"arrowstyle": "->", "color": BLEU, "linewidth": 1.2},
        color=BLEU,
        fontsize="small",
    )

    ax.set_ylim(-20.0, 500.0)
    _finish(ax, xlabel="Mach", ylabel="paramètre", title="Le tube réel dans l'hyperrectangle")
    ax.legend(loc="upper left", fontsize="small", framealpha=0.9)
    _save(fig, "01_tube_vs_hyperrectangle.png")


def figure_marge() -> None:
    """Pourquoi la marge est absolue et non multiplicative."""
    _style()
    rng = np.random.default_rng(7)
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.0), constrained_layout=True)

    for ax, (titre, echantillon) in zip(
        axes,
        [
            ("Variable traversant zéro (braquage)", rng.normal(0.0, 6.0, 20_000)),
            ("Variable positive étalée (échelle log)", 10.0 ** rng.uniform(0.5, 2.6, 20_000)),
        ],
        strict=True,
    ):
        log = titre.startswith("Variable positive")
        bornes = quantile_bounds(echantillon, margin=0.10, log_scaled=log)

        ax.hist(echantillon, bins=80, color=GRIS, alpha=0.55, log=log)
        for valeur, couleur, etiquette in (
            (bornes.q_low_value, ORANGE, "quantiles 0,1 % / 99,9 %"),
            (bornes.q_high_value, ORANGE, None),
            (bornes.low, BLEU, "bornes après marge"),
            (bornes.high, BLEU, None),
        ):
            ax.axvline(valeur, color=couleur, linewidth=1.8, label=etiquette)
        if log:
            ax.set_xscale("log")
        _finish(ax, xlabel="valeur", ylabel="effectif", title=titre, numeric_x=not log)
        ax.legend(loc="upper right", fontsize="x-small", framealpha=0.9)

    _save(fig, "02_marge_absolue.png")


def figure_repliement() -> None:
    """Ce que chaque groupe de symétrie fait de l'azimut."""
    _style()
    brut = np.linspace(0.0, 360.0, 1000)
    groupes = [
        SymmetryGroup.CINFV,
        SymmetryGroup.C4V,
        SymmetryGroup.C4,
        SymmetryGroup.CS,
        SymmetryGroup.C1,
    ]

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), constrained_layout=True)

    ax = axes[0]
    for groupe, couleur in zip(groupes, (GRIS, BLEU, VERT, ORANGE, ROUGE), strict=True):
        spec = SymmetrySpec(group=groupe)
        ax.plot(brut, fold_phi(brut, spec), color=couleur, linewidth=1.8, label=str(groupe))
    _finish(ax, xlabel="φ brut [deg]", ylabel="φ replié [deg]", title="Repliement par groupe")
    ax.legend(loc="upper right", fontsize="small", framealpha=0.9, ncol=2)

    ax = axes[1]
    for i, groupe in enumerate(groupes):
        spec = SymmetrySpec(group=groupe)
        niveaux = azimuth_levels(spec)
        bas, haut = spec.fundamental_domain_deg
        ax.plot([bas, max(haut, 1.0)], [i, i], color=GRIS, linewidth=2.0, zorder=1)
        ax.scatter(niveaux, [i] * len(niveaux), s=42, color=BLEU, zorder=3, edgecolors="white")
        ax.text(365.0, i, f"{len(niveaux)} azimut(s)", va="center", fontsize="x-small", color="0.3")
    ax.set_yticks(range(len(groupes)))
    ax.set_yticklabels([str(g) for g in groupes], fontsize="small")
    ax.set_xlim(-10.0, 430.0)
    _finish(
        ax, xlabel="φ [deg]", ylabel="", title="Domaine fondamental et niveaux", numeric_y=False
    )

    _save(fig, "03_repliement_symetries.png")


def figure_couts() -> None:
    """Ce que chaque configuration de calcul coûte."""
    _style()
    from cfd_traj.core.symmetry import RELATIVE_COST, CalcConfig

    etiquettes = {
        CalcConfig.AXI_2D: "axisymétrique 2D",
        CalcConfig.SECTEUR_45: "secteur 45°",
        CalcConfig.QUART_90: "quart 90° cyclique",
        CalcConfig.DEMI: "demi-configuration",
        CalcConfig.COMPLETE: "configuration complète",
    }
    ordre = list(etiquettes)
    couts = [RELATIVE_COST[c] for c in ordre]

    fig, ax = plt.subplots(figsize=(7.0, 3.4), constrained_layout=True)
    positions = np.arange(len(ordre))
    ax.barh(positions, couts, height=0.6, color=BLEU, edgecolor="0.15", linewidth=0.7)
    for i, cout in enumerate(couts):
        ax.text(cout + 0.02, i, f"{cout:g}".replace(".", ","), va="center", fontsize="small")
    ax.set_yticks(positions)
    ax.set_yticklabels([etiquettes[c] for c in ordre], fontsize="small")
    ax.set_xlim(0.0, 1.15)
    _finish(
        ax,
        xlabel="coût relatif (équivalents configuration complète)",
        ylabel="",
        title="Ce que la symétrie fait gagner sur un cas",
        numeric_y=False,
    )
    _save(fig, "04_couts_configurations.png")


def main() -> int:
    """Régénère toutes les figures."""
    figure_tube()
    figure_marge()
    figure_repliement()
    figure_couts()
    return 0


if __name__ == "__main__":
    sys.exit(main())
