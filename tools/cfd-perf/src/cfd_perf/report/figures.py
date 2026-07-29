"""Figures de scalabilité (sorties en français).

Rendu via la bibliothèque interne ``plotting`` (``scripts/post/plot``) quand
elle est disponible, avec repli sur Matplotlib nu sinon — cfd-perf doit rester
utilisable copié seul sur un calculateur isolé.

La figure répond, panneau par panneau, aux quatre questions derrière
« sur combien de cœurs lancer mon calcul ? » :

1. durée      -- combien de temps ?
2. gain       -- est-ce que je gagne vraiment quelque chose ?
3. efficacité -- est-ce que je gaspille l'allocation ?
4. coût       -- combien ça consomme ?

Chaque panneau trace le modèle en ligne dense passant par les points pilotes
*mesurés* : un ajustement qui ne suit pas les mesures se voit immédiatement,
au lieu d'être masqué par une polyligne grossière échantillonnée aux seuls
points candidats (le défaut que ce module corrige).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from matplotlib.axes import Axes
from matplotlib.axis import Axis
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, LogLocator

from cfd_perf.engine.recommend import Recommendation
from cfd_perf.report._plotting_lib import get_plotting

COULEUR_MODELE = "#0B6FA4"
COULEUR_PILOTE = "#D1495B"
COULEUR_CHOIX = "#1B998B"
COULEUR_IDEAL = "#9AA5B1"
COULEUR_INFAISABLE = "#D9534F"
COULEUR_EXTRAPOLATION = "#F0AD4E"
COULEUR_RETOURNEMENT = "#B07AA1"

_POINTS_DENSES = 400

VERDICT_FR = {
    "excellent": "excellent",
    "good": "bon",
    "marginal": "limite",
    "poor": "mauvais",
}


def _dense_cores(rec: Recommendation) -> npt.NDArray[np.int_]:
    lo = min(rec.candidates[0].cores, rec.pilot.core_range[0])
    hi = max(rec.candidates[-1].cores, rec.pilot.core_range[1])
    dense = np.unique(np.round(np.geomspace(lo, hi, _POINTS_DENSES)).astype(int))
    return cast("npt.NDArray[np.int_]", dense)


def _milliers(x: float, _pos: int = 0) -> str:
    """Format français : espace comme séparateur de milliers."""
    if x >= 1000 and x == int(x):
        return f"{int(x):,}".replace(",", " ")
    return f"{x:g}"


def _ticks_log_lisibles(axis: Axis) -> None:
    """Étiquettes d'axe log en clair (« 600 ») et non « 6 x 10^2 ».

    Matplotlib étiquette les graduations mineures en notation scientifique par
    défaut, illisible pour des nombres de cœurs comme pour des heures. On
    n'étiquette que les mineures ×2 et ×5 : tout étiqueter fait se chevaucher
    « 800 », « 900 » et « 1 000 » en fin de décade.
    """
    fmt = FuncFormatter(_milliers)
    axis.set_major_formatter(fmt)
    axis.set_minor_locator(LogLocator(base=10.0, subs=(2.0, 5.0), numticks=12))
    axis.set_minor_formatter(fmt)


def _zones(ax: Axes, rec: Recommendation) -> None:
    """Grise la zone infaisable et la zone extrapolée."""
    infaisables = [c.cores for c in rec.rejected]
    if infaisables:
        # En pratique les contraintes sont monotones : on grise depuis le
        # premier rejet au-delà de la recommandation jusqu'au bord droit.
        ref = rec.choice.cores if rec.choice else 0
        au_dela = [c for c in infaisables if c > ref]
        if au_dela:
            ax.axvspan(
                min(au_dela), ax.get_xlim()[1],
                color=COULEUR_INFAISABLE, alpha=0.07, zorder=0,
            )

    _lo, hi = rec.model.fitted_range
    droite = ax.get_xlim()[1]
    if hi < droite:
        ax.axvspan(hi, droite, color=COULEUR_EXTRAPOLATION, alpha=0.07, zorder=0)


def _ligne_choix(ax: Axes, rec: Recommendation) -> None:
    if rec.choice is None:
        return
    ax.axvline(
        rec.choice.cores,
        color=COULEUR_CHOIX,
        linestyle="--",
        linewidth=1.6,
        zorder=3,
        label=f"recommandé ({rec.choice.cores})",
    )


def _habiller(ax: Axes, xlabel: str, ylabel: str, titre: str) -> None:
    plotting = get_plotting()
    if plotting is not None:
        plotting.set_title(ax, titre, fontsize=11, fontweight="bold", loc="left", pad=8)
    else:
        ax.set_title(titre, fontsize=11, fontweight="bold", loc="left", pad=8)
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.grid(True, which="major", alpha=0.25, linewidth=0.6)
    ax.grid(True, which="minor", alpha=0.12, linewidth=0.4)
    ax.tick_params(labelsize=8)
    ax.tick_params(which="minor", labelsize=7)


def _tracer_modele(
    ax: Axes, x: npt.NDArray[Any], y: npt.NDArray[Any], label: str
) -> None:
    plotting = get_plotting()
    if plotting is not None:
        plotting.plot_line(
            ax, x, y, marker="", color=COULEUR_MODELE, linewidth=2, zorder=2, label=label
        )
    else:
        ax.plot(x, y, color=COULEUR_MODELE, linewidth=2, zorder=2, label=label)


def _tracer_pilote(ax: Axes, x: npt.NDArray[Any], y: npt.NDArray[Any]) -> None:
    ax.scatter(
        x, y, color=COULEUR_PILOTE, s=55, marker="D", zorder=5,
        edgecolors="white", linewidths=1.2, label="pilote (mesuré)",
    )


def _legende(ax: Axes, loc: str = "best") -> None:
    plotting = get_plotting()
    if plotting is not None:
        plotting.apply_oldschool_axes(ax, legend=False)
        plotting.make_legend(ax, loc=loc, fontsize=8)
    else:
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        ax.legend(fontsize=8, frameon=False, loc=cast(Any, loc))


def plot_recommendation(rec: Recommendation, *, title: str = "") -> Figure:
    """Construit la figure 4 panneaux pour une recommandation."""
    plotting = get_plotting()
    if plotting is not None:
        plotting.use_style("paper")

    model = rec.model
    pilot = rec.pilot
    n_iter = pilot.n_iterations

    dense = _dense_cores(rec)
    t_modele = np.array([model.time_per_iter(int(n)) for n in dense])
    duree_modele = t_modele * n_iter / 3600.0
    acc_modele = np.array([model.speedup(int(n)) for n in dense])
    eff_modele = np.array([model.efficiency(int(n)) * 100 for n in dense])
    cout_modele = duree_modele * dense

    p_nc = np.array([p.cores for p in pilot.points], dtype=float)
    p_t = np.array([p.time_per_iter_s for p in pilot.points])
    p_duree = p_t * n_iter / 3600.0
    t_ref = model.time_per_iter(model.ref_cores)
    p_acc = t_ref / p_t
    p_eff = p_acc / (p_nc / model.ref_cores) * 100
    p_cout = p_duree * p_nc

    if plotting is not None:
        fig, axes = cast(
            "tuple[Figure, Any]",
            plotting.new_figure(2, 2, figsize=(13, 8.5), constrained_layout=False),
        )
    else:
        fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    fig.subplots_adjust(left=0.07, right=0.98, top=0.87, bottom=0.09, hspace=0.34, wspace=0.24)

    q = model.quality
    entete = title or "Sur combien de cœurs lancer le calcul ?"
    if plotting is not None:
        plotting.set_suptitle(
            fig, entete, fontsize=14, fontweight="bold", x=0.07, ha="left", y=0.97
        )
    else:
        fig.suptitle(entete, fontsize=14, fontweight="bold", x=0.07, ha="left", y=0.97)

    fig.text(
        0.07,
        0.915,
        f"{model.describe()}     ajustement : {VERDICT_FR[q.verdict]} "
        f"({q.max_rel_err_pct:.1f} % d'erreur max, R²={q.r_squared:.4f}) "
        f"sur {q.n_points} points pilotes",
        fontsize=9,
        color="#555555",
        ha="left",
    )

    # -- 1. durée -----------------------------------------------------------
    ax = axes[0, 0]
    ax.set_xscale("log")
    ax.set_yscale("log")
    _tracer_modele(ax, dense, duree_modele, "modèle")
    _tracer_pilote(ax, p_nc, p_duree)
    _zones(ax, rec)
    _ligne_choix(ax, rec)
    nc_retournement = model.time_minimum_cores(int(dense.max()))
    if nc_retournement is not None:
        ax.axvline(
            nc_retournement, color=COULEUR_RETOURNEMENT, linestyle=":", linewidth=1.4,
            zorder=3, label=f"plus lent au-delà de {nc_retournement}",
        )
    _habiller(ax, "Cœurs", "Durée totale (h)", "1. Combien de temps ?")
    _ticks_log_lisibles(ax.xaxis)
    _ticks_log_lisibles(ax.yaxis)
    _legende(ax)

    # -- 2. accélération ----------------------------------------------------
    ax = axes[0, 1]
    ax.set_xscale("log")
    ideal = dense / model.ref_cores
    ax.plot(dense, ideal, color=COULEUR_IDEAL, linestyle="--", linewidth=1.4, zorder=1,
            label="idéal (linéaire)")
    _tracer_modele(ax, dense, acc_modele, "modèle")
    _tracer_pilote(ax, p_nc, p_acc)
    _zones(ax, rec)
    _ligne_choix(ax, rec)
    ax.set_ylim(0, max(float(acc_modele.max()), float(p_acc.max())) * 1.35)
    _habiller(ax, "Cœurs", f"Accélération vs {model.ref_cores} cœurs", "2. Quel gain réel ?")
    _ticks_log_lisibles(ax.xaxis)
    _legende(ax, loc="upper left")

    # -- 3. efficacité ------------------------------------------------------
    ax = axes[1, 0]
    ax.set_xscale("log")
    _tracer_modele(ax, dense, eff_modele, "modèle")
    _tracer_pilote(ax, p_nc, p_eff)
    seuil = 100 * (1 - rec.max_efficiency_loss)
    ax.axhline(seuil, color=COULEUR_CHOIX, linestyle=":", linewidth=1.4, zorder=3,
               label=f"seuil visé ({seuil:.0f} %)")
    _zones(ax, rec)
    _ligne_choix(ax, rec)
    ax.set_ylim(0, 110)
    _habiller(ax, "Cœurs", "Efficacité parallèle (%)", "3. Est-ce que je gaspille l'allocation ?")
    _ticks_log_lisibles(ax.xaxis)
    _legende(ax)

    # -- 4. coût ------------------------------------------------------------
    ax = axes[1, 1]
    ax.set_xscale("log")
    _tracer_modele(ax, dense, cout_modele, "modèle")
    _tracer_pilote(ax, p_nc, p_cout)
    _zones(ax, rec)
    _ligne_choix(ax, rec)
    if rec.choice is not None:
        texte = f"{_milliers(float(round(rec.choice.core_hours)))} h·cœur"
        if plotting is not None:
            plotting.annotate_point(
                ax, texte, xy=(rec.choice.cores, rec.choice.core_hours),
                offset=(14, 16), fontsize=8, color=COULEUR_CHOIX, fontweight="bold",
            )
        else:
            ax.annotate(
                texte, xy=(rec.choice.cores, rec.choice.core_hours),
                xytext=(14, 16), textcoords="offset points", fontsize=8,
                color=COULEUR_CHOIX, fontweight="bold",
                arrowprops={"arrowstyle": "->", "color": COULEUR_CHOIX, "linewidth": 1.0},
            )
    _habiller(ax, "Cœurs", "Coût (heures·cœur)", "4. Combien ça consomme ?")
    _ticks_log_lisibles(ax.xaxis)
    _legende(ax)

    _note_bas_de_page(fig, rec)
    return fig


def _note_bas_de_page(fig: Figure, rec: Recommendation) -> None:
    lo, hi = rec.model.fitted_range
    morceaux = [f"plage pilote {lo}–{hi} cœurs ; au-delà de {hi} le modèle extrapole (ambre)"]
    if rec.rejected:
        morceaux.append("rouge = contrainte matérielle non respectée")
    fig.text(0.07, 0.015, "   |   ".join(morceaux), fontsize=8, color="#777777", ha="left")


def save_recommendation_figure(
    rec: Recommendation,
    path: str | Path,
    *,
    title: str = "",
    dpi: int = 160,
) -> Path:
    """Génère et enregistre la figure. Renvoie le chemin écrit."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig = plot_recommendation(rec, title=title)

    plotting = get_plotting()
    if plotting is not None:
        suffix = out.suffix.lstrip(".") or "png"
        plotting.save_figure(
            fig, str(out.with_suffix("")), formats=(suffix,), dpi=dpi, report=False
        )
    else:
        fig.savefig(out, dpi=dpi, bbox_inches="tight", facecolor="white")

    plt.close(fig)
    return out
