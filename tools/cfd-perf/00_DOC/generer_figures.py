#!/usr/bin/env python3
"""Génère les figures illustrant la documentation.

    python 00_DOC/generer_figures.py

Écrit dans ``00_DOC/FIGURES/``. Les figures sont versionnées : ce script ne
sert qu'à les régénérer si le modèle ou les données d'exemple changent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))

from cfd_perf.core.model import fit_model  # noqa: E402
from cfd_perf.data.pilot import pilot_from_points  # noqa: E402
from cfd_perf.report._plotting_lib import get_plotting  # noqa: E402
from cfd_perf.report.figures import _ticks_log_lisibles  # noqa: E402

FIGURES = Path(__file__).resolve().parent / "FIGURES"

# Mesures pilotes réelles (20 M mailles, RANS, calculateur isolé).
PILOTE = [
    {"cores": 48, "time_per_iter_s": 3.85, "peak_ram_total_gb": 142.0},
    {"cores": 96, "time_per_iter_s": 2.18, "peak_ram_total_gb": 142.0},
    {"cores": 192, "time_per_iter_s": 1.41, "peak_ram_total_gb": 143.0},
    {"cores": 384, "time_per_iter_s": 1.12, "peak_ram_total_gb": 144.0},
    {"cores": 576, "time_per_iter_s": 1.05, "peak_ram_total_gb": 145.0},
    {"cores": 768, "time_per_iter_s": 1.10, "peak_ram_total_gb": 146.0},
    {"cores": 1024, "time_per_iter_s": 1.28, "peak_ram_total_gb": 148.0},
]

BLEU = "#0B6FA4"
ROUGE = "#D1495B"
VERT = "#1B998B"
ORANGE = "#E8871E"
GRIS = "#9AA5B1"


def figure_termes_modele(plotting) -> None:
    """Décomposition du modèle en ses trois contributions physiques."""
    pilote = pilot_from_points(PILOTE, n_iterations=12_000)
    m = fit_model(pilote)

    nc = np.geomspace(48, 1400, 400)
    serie = np.full_like(nc, m.t_serial)
    para = m.t_parallel / nc
    comm = m.t_comm * nc**m.gamma
    total = serie + para + comm

    fig, ax = plotting.new_figure(figsize=(9, 5.5), constrained_layout=False)
    fig.subplots_adjust(left=0.10, right=0.97, top=0.84, bottom=0.13)
    plotting.set_suptitle(
        fig, "Les trois contributions au temps par itération",
        fontsize=14, fontweight="bold", x=0.07, ha="left", y=0.97,
    )

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.plot(nc, para, color=VERT, linestyle="--", linewidth=1.8,
            label=r"$t_{par}/N_c$ — se divise (on gagne)")
    ax.plot(nc, serie, color=GRIS, linestyle=":", linewidth=1.8,
            label=r"$t_{ser}$ — plancher d'Amdahl")
    ax.plot(nc, comm, color=ORANGE, linestyle="-.", linewidth=1.8,
            label=rf"$t_{{comm}} \cdot N_c^{{{m.gamma:.2f}}}$ — MPI (on perd)")
    ax.plot(nc, total, color=BLEU, linewidth=2.4, label="total $T(N_c)$")

    p_nc = np.array([p["cores"] for p in PILOTE], dtype=float)
    p_t = np.array([p["time_per_iter_s"] for p in PILOTE])
    ax.scatter(p_nc, p_t, color=ROUGE, s=60, marker="D", zorder=5,
               edgecolors="white", linewidths=1.2, label="pilote (mesuré)")

    nc_min = m.time_minimum_cores(1400)
    if nc_min is not None:
        ax.axvline(nc_min, color=ROUGE, linestyle="--", linewidth=1.4)
        ax.annotate(
            f"croisement : {nc_min} cœurs\nau-delà, MPI l'emporte",
            xy=(nc_min, m.time_per_iter(nc_min)), xytext=(-175, -85),
            textcoords="offset points", fontsize=9, color=ROUGE, fontweight="bold",
            arrowprops={"arrowstyle": "->", "color": ROUGE},
        )

    ax.set_xlabel("Cœurs")
    ax.set_ylabel("Temps par itération (s)")
    ax.grid(True, which="major", alpha=0.25)
    _ticks_log_lisibles(ax.xaxis)
    plotting.apply_oldschool_axes(ax, legend=False)
    plotting.make_legend(ax, loc="upper right", fontsize=8)

    fig.text(
        0.07, 0.015,
        "Le minimum de la courbe est l'endroit exact où le gain de parallélisme "
        "est mangé par le coût de communication.",
        fontsize=8, color="#777777", ha="left",
    )
    plotting.save_figure(fig, str(FIGURES / "01_termes_modele"),
                         formats=("png",), dpi=150, report=False)
    print("  01_termes_modele.png")


def figure_strategies(plotting) -> None:
    """Ce que chaque stratégie choisit sur la même courbe."""
    from cfd_perf.data.machine import Machine
    from cfd_perf.data.mesh import mesh_from_data
    from cfd_perf.engine.recommend import Strategy, recommend

    pilote = pilot_from_points(PILOTE, n_iterations=12_000)
    m = fit_model(pilote)
    maillage = mesh_from_data(num_cells=20_000_000, pilot=pilote)
    machine = Machine(name="cluster-a", cores_per_node=48, max_nodes=32)

    choix = {}
    for strat, kw in (
        (Strategy.EFFICIENCY, {"max_efficiency_loss": 0.30}),
        (Strategy.DEADLINE, {"deadline_hours": 4.5}),
        (Strategy.FASTEST, {}),
    ):
        rec = recommend(
            model=m, mesh=maillage, pilot=pilote, machine=machine,
            strategy=strat, cores_max=1536, **kw,
        )
        choix[strat] = rec.choice

    nc = np.geomspace(48, 1536, 400)
    duree = np.array([m.runtime_hours(float(n), 12_000) for n in nc])
    cout = duree * nc

    fig, axes = plotting.new_figure(1, 2, figsize=(13, 5), constrained_layout=False)
    fig.subplots_adjust(left=0.07, right=0.98, top=0.84, bottom=0.13, wspace=0.24)
    plotting.set_suptitle(
        fig, "Trois questions, trois réponses différentes",
        fontsize=14, fontweight="bold", x=0.07, ha="left", y=0.97,
    )

    couleurs = {
        Strategy.EFFICIENCY: VERT,
        Strategy.DEADLINE: ORANGE,
        Strategy.FASTEST: ROUGE,
    }
    libelles = {
        Strategy.EFFICIENCY: "efficacité (≤30 % de perte)",
        Strategy.DEADLINE: "échéance (≤4,5 h)",
        Strategy.FASTEST: "le plus rapide",
    }

    for ax, y, titre, ylabel in (
        (axes[0], duree, "Durée totale", "Durée totale (h)"),
        (axes[1], cout, "Coût", "Coût (heures·cœur)"),
    ):
        ax.set_xscale("log")
        ax.plot(nc, y, color=BLEU, linewidth=2.2, label="modèle")
        for strat, cand in choix.items():
            if cand is None:
                continue
            valeur = (
                cand.runtime_hours if ylabel.startswith("Durée") else cand.core_hours
            )
            ax.axvline(cand.cores, color=couleurs[strat], linestyle="--", linewidth=1.6,
                       label=f"{libelles[strat]} → {cand.cores} cœurs")
            ax.scatter([cand.cores], [valeur], color=couleurs[strat], s=70, zorder=6,
                       edgecolors="white", linewidths=1.2)
        plotting.set_title(ax, titre, fontsize=11, fontweight="bold", loc="left", pad=8)
        ax.set_xlabel("Cœurs")
        ax.set_ylabel(ylabel)
        ax.grid(True, which="major", alpha=0.25)
        _ticks_log_lisibles(ax.xaxis)
        plotting.apply_oldschool_axes(ax, legend=False)
        plotting.make_legend(ax, loc="upper left", fontsize=8)

    fig.text(
        0.07, 0.015,
        "Même courbe, même contraintes : seule la question posée change la réponse.",
        fontsize=8, color="#777777", ha="left",
    )
    plotting.save_figure(fig, str(FIGURES / "02_strategies"),
                         formats=("png",), dpi=150, report=False)
    print("  02_strategies.png")


def main() -> int:
    plotting = get_plotting()
    if plotting is None:
        print(
            "ERREUR : bibliothèque 'plotting' introuvable.\n"
            "Exportez CFD_FRAMEWORK ou lancez ce script depuis le dépôt.",
            file=sys.stderr,
        )
        return 1

    FIGURES.mkdir(parents=True, exist_ok=True)
    plotting.use_style("paper")

    print(f"Génération des figures dans {FIGURES} :")
    figure_termes_modele(plotting)
    figure_strategies(plotting)
    print("Terminé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
