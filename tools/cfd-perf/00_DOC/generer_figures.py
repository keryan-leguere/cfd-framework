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
from matplotlib.ticker import FuncFormatter, NullFormatter

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))

from cfd_perf.core.model import fit_model  # noqa: E402
from cfd_perf.data.pilot import pilot_from_points  # noqa: E402
from cfd_perf.report._plotting_lib import get_plotting  # noqa: E402
from cfd_perf.report.figures import _milliers, _ticks_log_lisibles  # noqa: E402

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


def figure_decomposition(plotting) -> None:
    """Ce que « lancer sur N cœurs » fait au maillage : la décomposition.

    Le maillage est découpé en autant de sous-domaines que de rangs MPI. Le
    volume par rang se divise par Nc, mais la surface d'échange, elle, ne
    décroît que comme une puissance < 1 : c'est toute l'origine du terme de
    communication du modèle.
    """
    from matplotlib.patches import Rectangle

    n = 24  # côté du maillage, en mailles
    decoupes = [1, 2, 4, 8]  # k x k sous-domaines

    fig, axes = plotting.new_figure(1, 4, figsize=(14, 4.6), constrained_layout=False)
    fig.subplots_adjust(left=0.03, right=0.985, top=0.78, bottom=0.24, wspace=0.13)
    plotting.set_suptitle(
        fig, "Décomposition de domaine : un sous-domaine par cœur",
        fontsize=14, fontweight="bold", x=0.03, ha="left", y=0.97,
    )

    teintes = ["#DCE9F2", "#C3DAEA", "#EAF1F6", "#B0CEE2"]

    for ax, k in zip(axes, decoupes, strict=True):
        nc = k * k
        s = n // k                       # côté d'un sous-domaine, en mailles
        mailles_rang = s * s
        # Faces d'échange : (k-1) coupes dans chaque direction, n faces chacune.
        faces_int = 2 * (k - 1) * n
        faces_rang = faces_int / nc

        for j in range(k):
            for i in range(k):
                ax.add_patch(Rectangle(
                    (i * s, j * s), s, s,
                    facecolor=teintes[(i + j) % len(teintes)],
                    edgecolor="none", zorder=1,
                ))
        # Mailles (fines) puis interfaces entre sous-domaines (épaisses, rouges).
        for x in range(n + 1):
            ax.plot([x, x], [0, n], color="white", linewidth=0.5, zorder=2)
            ax.plot([0, n], [x, x], color="white", linewidth=0.5, zorder=2)
        for c in range(1, k):
            ax.plot([c * s, c * s], [0, n], color=ROUGE, linewidth=2.4, zorder=3)
            ax.plot([0, n], [c * s, c * s], color=ROUGE, linewidth=2.4, zorder=3)
        ax.add_patch(Rectangle((0, 0), n, n, facecolor="none",
                               edgecolor="#333333", linewidth=1.4, zorder=4))

        ax.set_xlim(-0.6, n + 0.6)
        ax.set_ylim(-0.6, n + 0.6)
        ax.set_aspect("equal")
        ax.set_axis_off()
        plotting.set_title(ax, f"{nc} cœur{'s' if nc > 1 else ''}",
                           fontsize=12, fontweight="bold", loc="left", pad=10)
        ax.text(
            0.5, -0.06,
            f"{mailles_rang} mailles/rang\n"
            + (f"{faces_rang:.0f} faces d'échange/rang" if k > 1 else "aucun échange"),
            transform=ax.transAxes, ha="center", va="top", fontsize=9,
            color="#444444",
        )
        if k > 1:
            ax.text(
                0.5, -0.20,
                "→ "
                + f"{faces_rang / mailles_rang:.2f}".replace(".", ",")
                + " face échangée par maille calculée",
                transform=ax.transAxes, ha="center", va="top", fontsize=9,
                color=ROUGE, fontweight="bold",
            )

    fig.text(
        0.03, 0.035,
        "Chaque doublement du nombre de cœurs divise le volume par rang par 2, "
        "mais ne divise sa surface d'échange que par √2 (2D) ou 2^(2/3) (3D).",
        fontsize=8.5, color="#777777", ha="left",
    )
    fig.text(
        0.03, 0.005,
        "Trait rouge = interface entre sous-domaines : à chaque itération, les "
        "mailles qui la bordent sont échangées en MPI.",
        fontsize=8.5, color=ROUGE, ha="left",
    )
    plotting.save_figure(fig, str(FIGURES / "03_decomposition"),
                         formats=("png",), dpi=150, report=False)
    print("  03_decomposition.png")


def figure_surface_volume(plotting) -> None:
    """Pourquoi il existe un plancher de mailles par cœur.

    Sous-domaine cubique de *m* mailles : côté m^(1/3), donc 6·m^(2/3) mailles
    de bord. La part de bord vaut 6/m^(1/3) — elle explose quand m diminue.
    """
    mailles_totales = 20_000_000
    plancher = 10_000

    nc = np.geomspace(1, 8192, 400)
    mailles_rang = mailles_totales / nc

    m = np.geomspace(2e2, 3e6, 400)
    part_bord = np.minimum(6.0 / m ** (1 / 3), 1.0)

    fig, axes = plotting.new_figure(1, 2, figsize=(13, 5), constrained_layout=False)
    fig.subplots_adjust(left=0.07, right=0.98, top=0.82, bottom=0.15, wspace=0.24)
    plotting.set_suptitle(
        fig, "Le volume se divise, la surface non : le plancher de mailles par cœur",
        fontsize=14, fontweight="bold", x=0.07, ha="left", y=0.97,
    )

    ax = axes[0]
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.plot(nc, mailles_rang, color=BLEU, linewidth=2.4,
            label="mailles par rang = 20 M / $N_c$")
    ax.axhline(plancher, color=ROUGE, linestyle="--", linewidth=1.8,
               label=f"plancher {plancher:,} mailles/cœur".replace(",", " "))
    nc_plancher = mailles_totales / plancher
    ax.axvline(nc_plancher, color=GRIS, linestyle=":", linewidth=1.6)
    ax.annotate(
        f"{nc_plancher:.0f} cœurs\n= la limite du maillage",
        xy=(nc_plancher, plancher), xytext=(28, 78), textcoords="offset points",
        fontsize=9, color=ROUGE, fontweight="bold",
        arrowprops={"arrowstyle": "->", "color": ROUGE},
    )
    plotting.set_title(ax, "Un maillage de 20 M de mailles", fontsize=11,
                       fontweight="bold", loc="left", pad=8)
    ax.set_xlabel("Cœurs")
    ax.set_ylabel("Mailles par rang")
    ax.grid(True, which="major", alpha=0.25)
    _ticks_log_lisibles(ax.xaxis)
    plotting.apply_oldschool_axes(ax, legend=False)
    plotting.make_legend(ax, loc="upper right", fontsize=8)

    ax = axes[1]
    ax.set_xscale("log")
    ax.plot(m, 100 * part_bord, color=ORANGE, linewidth=2.4,
            label=r"part de bord $= 6/m^{1/3}$ (sous-domaine cubique)")
    ax.axvline(plancher, color=ROUGE, linestyle="--", linewidth=1.8)
    y_plancher = 100 * 6.0 / plancher ** (1 / 3)
    ax.scatter([plancher], [y_plancher], color=ROUGE, s=70, zorder=6,
               edgecolors="white", linewidths=1.2)
    ax.annotate(
        f"à {plancher:,} mailles/cœur,\n{y_plancher:.0f} % des mailles sont sur "
        "une interface".replace(",", " "),
        xy=(plancher, y_plancher), xytext=(35, 45), textcoords="offset points",
        fontsize=9, color=ROUGE, fontweight="bold",
        arrowprops={"arrowstyle": "->", "color": ROUGE},
    )
    for repere, txt in ((1_000_000, "confortable"), (100_000, "raisonnable")):
        ax.scatter([repere], [100 * 6.0 / repere ** (1 / 3)], color=VERT, s=45,
                   zorder=6, edgecolors="white", linewidths=1.0)
        ax.annotate(txt, xy=(repere, 100 * 6.0 / repere ** (1 / 3)),
                    xytext=(-8, 16), textcoords="offset points", fontsize=8,
                    color=VERT, ha="center")
    plotting.set_title(ax, "Un sous-domaine trop petit n'est plus que du bord",
                       fontsize=11, fontweight="bold", loc="left", pad=8)
    ax.set_xlabel("Mailles par rang $m$")
    ax.set_ylabel("Mailles de bord (%)")
    ax.set_ylim(0, 100)
    ax.grid(True, which="major", alpha=0.25)
    # Décades seulement : sur trois décades et demie, étiqueter aussi les
    # graduations mineures fait se chevaucher « 10 000 » et « 20 000 ».
    ax.xaxis.set_major_formatter(FuncFormatter(_milliers))
    ax.xaxis.set_minor_formatter(NullFormatter())
    plotting.apply_oldschool_axes(ax, legend=False)
    plotting.make_legend(ax, loc="upper right", fontsize=8)

    fig.text(
        0.07, 0.015,
        "Le plancher par défaut de cfd-perf (min_cells_per_core = 10 000) est ce "
        "point : en dessous, on paie surtout des halos.",
        fontsize=8, color="#777777", ha="left",
    )
    plotting.save_figure(fig, str(FIGURES / "04_surface_volume"),
                         formats=("png",), dpi=150, report=False)
    print("  04_surface_volume.png")


def figure_scalabilite_forte(plotting) -> None:
    """Le vocabulaire de la scalabilité forte, sur les mesures de l'exemple."""
    pilote = pilot_from_points(PILOTE, n_iterations=12_000)
    m = fit_model(pilote)

    nc_ref = 48
    t_ref = m.time_per_iter(nc_ref)
    nc = np.geomspace(nc_ref, 1536, 400)
    accel = np.array([t_ref / m.time_per_iter(float(x)) for x in nc])
    ideal = nc / nc_ref
    efficacite = 100 * accel / ideal
    nc_min = m.time_minimum_cores(1536)

    fig, axes = plotting.new_figure(1, 2, figsize=(13, 5), constrained_layout=False)
    fig.subplots_adjust(left=0.07, right=0.98, top=0.82, bottom=0.15, wspace=0.24)
    plotting.set_suptitle(
        fig, "Scalabilité forte : accélération et efficacité",
        fontsize=14, fontweight="bold", x=0.07, ha="left", y=0.97,
    )

    p_nc = np.array([p["cores"] for p in PILOTE], dtype=float)
    p_accel = np.array([PILOTE[0]["time_per_iter_s"] / p["time_per_iter_s"] for p in PILOTE])

    ax = axes[0]
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.plot(nc, ideal, color=GRIS, linestyle="--", linewidth=1.8,
            label="idéal : ×2 de cœurs = ×2 de vitesse")
    ax.plot(nc, accel, color=BLEU, linewidth=2.4, label="réel (modèle ajusté)")
    ax.scatter(p_nc, p_accel, color=ROUGE, s=55, marker="D", zorder=5,
               edgecolors="white", linewidths=1.2, label="pilote (mesuré)")
    if nc_min is not None:
        ax.axvline(nc_min, color="#B07AA1", linestyle=":", linewidth=1.8,
                   label=f"minimum de durée : {nc_min} cœurs")
    ax.annotate("l'écart à la\ndroite grise\n= ce qui est perdu",
                xy=(300, t_ref / m.time_per_iter(300.0)), xytext=(-40, 70),
                textcoords="offset points", fontsize=9, color="#666666",
                ha="center", arrowprops={"arrowstyle": "->", "color": "#666666"})
    plotting.set_title(ax, "Accélération vs 48 cœurs", fontsize=11,
                       fontweight="bold", loc="left", pad=8)
    ax.set_xlabel("Cœurs")
    ax.set_ylabel("Accélération")
    ax.grid(True, which="major", alpha=0.25)
    _ticks_log_lisibles(ax.xaxis)
    _ticks_log_lisibles(ax.yaxis)
    plotting.apply_oldschool_axes(ax, legend=False)
    plotting.make_legend(ax, loc="upper left", fontsize=8)

    ax = axes[1]
    ax.set_xscale("log")
    ax.plot(nc, efficacite, color=BLEU, linewidth=2.4, label="efficacité")
    ax.axhline(100, color=GRIS, linestyle="--", linewidth=1.6, label="idéal (100 %)")
    ax.axhline(70, color=VERT, linestyle="-.", linewidth=1.8,
               label="seuil par défaut (30 % de perte)")
    ax.fill_between(nc, efficacite, 100, color=ORANGE, alpha=0.13)
    ax.annotate("gaspillé", xy=(430, 86), fontsize=11, color=ORANGE,
                fontweight="bold", ha="center")
    if nc_min is not None:
        ax.axvline(nc_min, color="#B07AA1", linestyle=":", linewidth=1.8)
        ax.annotate("au-delà :\nplus lent ET plus cher",
                    xy=(nc_min, 22), xytext=(-118, 0), textcoords="offset points",
                    fontsize=9, color="#B07AA1", fontweight="bold",
                    arrowprops={"arrowstyle": "->", "color": "#B07AA1"})
    plotting.set_title(ax, "Efficacité : la part des cœurs qui sert vraiment",
                       fontsize=11, fontweight="bold", loc="left", pad=8)
    ax.set_xlabel("Cœurs")
    ax.set_ylabel("Efficacité (%)")
    ax.set_ylim(0, 112)
    ax.grid(True, which="major", alpha=0.25)
    _ticks_log_lisibles(ax.xaxis)
    plotting.apply_oldschool_axes(ax, legend=False)
    plotting.make_legend(ax, loc="lower left", fontsize=8)

    fig.text(
        0.07, 0.015,
        "Aucune de ces deux courbes ne dit à elle seule « lancez ici » : c'est le "
        "croisement avec vos contraintes qui décide.",
        fontsize=8, color="#777777", ha="left",
    )
    plotting.save_figure(fig, str(FIGURES / "05_scalabilite_forte"),
                         formats=("png",), dpi=150, report=False)
    print("  05_scalabilite_forte.png")


def main() -> int:
    plotting = get_plotting()
    if plotting is None:
        print(
            "ERREUR : paquet « cfd-plot » introuvable.\n"
            "Installez-le : pip install ../cfd-plot",
            file=sys.stderr,
        )
        return 1

    FIGURES.mkdir(parents=True, exist_ok=True)
    plotting.use_style("paper")

    print(f"Génération des figures dans {FIGURES} :")
    figure_termes_modele(plotting)
    figure_strategies(plotting)
    figure_decomposition(plotting)
    figure_surface_volume(plotting)
    figure_scalabilite_forte(plotting)
    print("Terminé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
