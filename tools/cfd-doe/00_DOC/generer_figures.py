#!/usr/bin/env python3
"""Génère les figures de 00_DOC/02_REMPLISSAGE.md dans 00_DOC/FIGURES/.

    pip install -e ../cfd-plot          # une fois
    python 00_DOC/generer_figures.py

Toutes les figures passent par ``cfd_plot`` (style, création, tracé, légende,
enregistrement). Les nombres affichés ne sont pas recopiés : ils viennent de
``compter_remplissage.py``, la même source que les tableaux du document.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import cfd_plot as cp
import matplotlib.pyplot as plt
import numpy as np

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
import compter_remplissage as cr  # noqa: E402

FIGURES = ICI / "FIGURES"
PROFIL = "notebook"
DPI = 130

# Palette Okabe-Ito de cfd-plot : lisible en cas de daltonisme.
_NOIR, _ORANGE, _CIEL, _VERT, _JAUNE, BLEU, VERMILLON, _ROSE = cp.palette_colors("okabe_ito")
ORANGE, VERT = _ORANGE, _VERT
GRIS = "0.55"


def enregistrer(fig: Any, nom: str) -> None:
    fichiers = cp.save_figure(fig, FIGURES / nom, formats=("png",), dpi=DPI)
    plt.close(fig)
    for f in fichiers:
        print(f"[ok] {f.relative_to(ICI.parent)}")


def points(
    ax: Any,
    xy: Sequence[tuple[float, float]],
    *,
    couleur: str,
    plein: bool = True,
    marker: str = "o",
    taille: float = 7.0,
    label: str | None = None,
) -> None:
    """Nuage de points par ``cfd_plot.plot_line`` : plein = calculé, creux = déduit."""
    if not xy:
        return
    x, y = zip(*xy)
    ligne = cp.plot_line(
        ax, x, y, linestyle="none", marker=marker, color=couleur, markersize=taille, label=label
    )
    if plein:
        ligne.set_markerfacecolor(couleur)


def cadre(
    ax: Any, xlabel: str, ylabel: str, xticks: Sequence[float], yticks: Sequence[float]
) -> None:
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_xticks(list(xticks))
    ax.set_yticks(list(yticks))
    dx, dy = 0.12 * (max(xticks) - min(xticks)), 0.12 * (max(yticks) - min(yticks))
    ax.set_xlim(min(xticks) - dx, max(xticks) + dx)
    ax.set_ylim(min(yticks) - dy, max(yticks) + dy)
    ax.grid(True, alpha=0.3)


# ---------------------------------------------------------------------------
# 1. Ce que les symétries épargnent
# ---------------------------------------------------------------------------


def figure_symetries() -> None:
    """Nœuds calculés et nœuds déduits, dans le plan (α, β) et sur le plan β = 0."""
    with cp.style_context(PROFIL):
        fig, (ax_ab, ax_plan) = cp.new_figure(1, 2, figsize=(12.0, 4.6))

        noeuds = [(a, b, 0.0, 0.0, 0.0) for a in cr.ALPHA for b in cr.BETA]
        calcules = [(p[0], p[1]) for p in noeuds if cr.est_calcule(p)]
        deduits = [(p[0], p[1]) for p in noeuds if not cr.est_calcule(p)]
        ax_ab.fill_between([0, 20], 0, 5, color=BLEU, alpha=0.10, lw=0)
        points(ax_ab, deduits, couleur=GRIS, plein=False, label="déduit par symétrie")
        points(ax_ab, calcules, couleur=BLEU, label="calculé")
        cp.add_reference_lines(ax_ab, hlines=[0.0], vlines=[0.0], color="0.3", lw=1.0, ls="--")
        cadre(ax_ab, "α (°)", "β (°)", cr.ALPHA, cr.BETA)
        cp.set_title(
            ax_ab, f"Plan (α, β), braquages nuls : {len(calcules)} calculs sur {len(noeuds)}"
        )
        cp.make_legend(ax_ab, loc="lower left", ncols=2)

        noeuds = [(10.0, 0.0, 0.0, dn, dl) for dn in cr.DN for dl in cr.DL]
        calcules = [(p[3], p[4]) for p in noeuds if cr.est_calcule(p)]
        deduits = [(p[3], p[4]) for p in noeuds if not cr.est_calcule(p)]
        points(ax_plan, deduits, couleur=GRIS, plein=False, label="déduit par le miroir V")
        points(ax_plan, calcules, couleur=BLEU, label="calculé")
        cadre(ax_plan, "δn (°)", "δl (°)", cr.DN, cr.DL)
        cp.set_title(
            ax_plan, f"Sur le plan β = 0 (α = 10°) : {len(calcules)} calculs sur {len(noeuds)}"
        )
        cp.make_legend(ax_plan, loc="lower left", ncols=2)
        ax_plan.set_ylim(-19, 13)
        ax_ab.set_ylim(-8.5, 6.2)
        enregistrer(fig, "remplissage_01_symetries")


# ---------------------------------------------------------------------------
# 2. Les plans, vus sur deux facteurs
# ---------------------------------------------------------------------------


def _lhs_maximin(n: int, graine: int = 7, essais: int = 400) -> list[tuple[float, float]]:
    """Hypercube latin en dimension 2, le meilleur de ``essais`` au sens maximin."""
    rng = np.random.default_rng(graine)
    centres = (np.arange(n) + 0.5) / n * 2.0 - 1.0
    meilleur, distance = None, -1.0
    for _ in range(essais):
        plan = np.column_stack([centres, rng.permutation(centres)])
        ecarts = plan[:, None, :] - plan[None, :, :]
        d = np.sqrt((ecarts**2).sum(-1))[np.triu_indices(n, 1)].min()
        if d > distance:
            meilleur, distance = plan, d
    assert meilleur is not None
    return [(float(x), float(y)) for x, y in meilleur]


def _halton(n: int) -> list[tuple[float, float]]:
    """Suite de Halton (bases 2 et 3), ramenée à [-1, 1]²."""

    def radical(i: int, base: int) -> float:
        valeur, facteur = 0.0, 1.0 / base
        while i > 0:
            valeur += facteur * (i % base)
            i //= base
            facteur /= base
        return valeur

    return [(2 * radical(i, 2) - 1, 2 * radical(i, 3) - 1) for i in range(1, n + 1)]


def figure_plans() -> None:
    """Six façons de placer des points, sur deux facteurs ramenés à [-1, 1]."""
    x9 = [i / 4 - 1 for i in range(9)]
    x5 = [i / 2 - 1 for i in range(5)]
    plans: list[tuple[str, list[tuple[float, float]], str]] = [
        ("Factoriel complet", [(x, y) for x in x9 for y in x5], BLEU),
        ("Étoile", [*((x, 0.0) for x in x9), *((0.0, y) for y in x5 if y)], BLEU),
        ("Composite centré", [(p[0], p[1]) for p in cr.composite_centre(2)], VERMILLON),
        ("Grille creuse (niveau 3)", [(p[0], p[1]) for p in cr.grille_creuse(2, 3)], VERMILLON),
        ("Hypercube latin", _lhs_maximin(20), VERT),
        ("Suite de Halton", _halton(20), VERT),
    ]
    with cp.style_context(PROFIL):
        fig, axes = cp.new_figure(2, 3, figsize=(12.0, 7.6), sharex=True, sharey=True)
        for ax, (titre, xy, couleur) in zip(axes.flat, plans):
            points(ax, xy, couleur=couleur, taille=6.0)
            cp.set_title(ax, f"{titre} : {len(xy)} points")
            ax.set_xlim(-1.18, 1.18)
            ax.set_ylim(-1.18, 1.18)
            ax.set_xticks([-1, 0, 1])
            ax.set_yticks([-1, 0, 1])
            ax.set_aspect("equal")
            ax.grid(True, alpha=0.3)
        for ax in axes[-1]:
            ax.set_xlabel("facteur 1")
        for ax in axes[:, 0]:
            ax.set_ylabel("facteur 2")
        enregistrer(fig, "remplissage_02_plans")


# ---------------------------------------------------------------------------
# 3. La décomposition dans le plan (δm, δn)
# ---------------------------------------------------------------------------


def figure_decomposition() -> None:
    """Ce qui est calculé, déduit et reconstruit dans le plan (δm, δn) à α fixé, β = 0."""
    noeuds = [(10.0, 0.0, dm, dn, 0.0) for dm in cr.DM for dn in cr.DN]
    sur_axes = [p for p in noeuds if p[2] == 0.0 or p[3] == 0.0]
    hors_axes = [(p[2], p[3]) for p in noeuds if p not in sur_axes]
    controle = [(20.0, 10.0), (-10.0, 20.0), (10.0, 10.0)]

    def trier(
        liste: list[tuple[float, ...]],
    ) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        calcules = [(p[2], p[3]) for p in liste if cr.est_calcule(p)]
        deduits = [(p[2], p[3]) for p in liste if not cr.est_calcule(p)]
        return calcules, deduits

    with cp.style_context(PROFIL):
        fig, axes = cp.new_figure(1, 3, figsize=(13.0, 4.9), sharey=True)

        calcules, deduits = trier(noeuds)
        points(axes[0], deduits, couleur=GRIS, plein=False, label="déduit par symétrie")
        points(axes[0], calcules, couleur=BLEU, label="calculé")
        cp.set_title(axes[0], f"Factoriel : {len(calcules)} calculs")

        calcules, deduits = trier(sur_axes)
        for ax, titre in (
            (axes[1], f"Ordre 1 : {len(calcules)} calculs"),
            (axes[2], f"Ordre 1 contrôlé : {len(calcules)} + {len(controle)}"),
        ):
            points(
                ax, hors_axes, couleur=GRIS, marker="x", taille=6.0, label="reconstruit par somme"
            )
            points(ax, deduits, couleur=GRIS, plein=False)
            points(ax, calcules, couleur=BLEU)
            cp.set_title(ax, titre)
        points(axes[2], controle, couleur=VERMILLON, marker="D", label="point de contrôle croisé")

        for ax in axes:
            cadre(ax, "δm (°)", "δn (°)", cr.DM, cr.DN)
            ax.set_aspect("equal")
        axes[1].set_ylabel("")
        axes[2].set_ylabel("")
        cp.make_figure_legend(fig, loc="outside lower center", bbox_to_anchor=None, ncol=4)
        enregistrer(fig, "remplissage_03_decomposition")


# ---------------------------------------------------------------------------
# 4. Ce que l'additivité voit, et ce qu'elle manque (modèle analytique factice)
# ---------------------------------------------------------------------------


def _sature(x: np.ndarray | float) -> np.ndarray | float:
    """Efficacité d'une gouverne en fonction de son incidence locale : sature vers 25°."""
    return 25.0 * np.tanh(np.asarray(x) / 25.0)


def _cm(alpha: float, dm: np.ndarray | float) -> np.ndarray | float:
    """Tangage factice : la gouverne voit l'incidence locale α + δm."""
    return -0.020 * alpha - 0.030 * _sature(alpha + np.asarray(dm))


def _cl(alpha: float, dm: float, dn: np.ndarray | float) -> np.ndarray | float:
    """Roulis induit factice : n'existe que si tangage et lacet sont braqués ensemble."""
    return 4e-5 * alpha * dm * np.asarray(dn)


def figure_additivite() -> None:
    """Pourquoi les incréments dépendent de α, et ce que l'ordre 1 ne peut pas voir."""
    fin = np.linspace(-20, 20, 81)
    niveaux = np.array(cr.DM)
    with cp.style_context(PROFIL):
        fig, (ax_cm, ax_cl) = cp.new_figure(1, 2, figsize=(12.0, 4.8))

        for alpha, couleur in ((0.0, BLEU), (10.0, ORANGE), (20.0, VERMILLON)):
            cp.plot_line(
                ax_cm, fin, _cm(alpha, fin), marker="", color=couleur, label=f"α = {alpha:g}°"
            )
            etoile = _cm(alpha, 0.0) + (_cm(0.0, niveaux) - _cm(0.0, 0.0))
            cp.plot_line(ax_cm, niveaux, etoile, marker="x", linestyle="--", color=couleur, lw=1.0)
            points(ax_cm, list(zip(niveaux, _cm(alpha, niveaux))), couleur=couleur)
        cp.plot_line(
            ax_cm, [], [], marker="o", linestyle="none", color="0.3", label="incrément tabulé en α"
        )
        cp.plot_line(
            ax_cm,
            [],
            [],
            marker="x",
            linestyle="--",
            color="0.3",
            lw=1.0,
            label="incrément pris à α = 0",
        )
        ax_cm.set_xlabel("δm (°)")
        ax_cm.set_ylabel("Cm")
        ax_cm.set_xticks(cr.DM)
        ax_cm.grid(True, alpha=0.3)
        cp.set_title(ax_cm, "L'incrément de tangage doit dépendre de α")
        cp.make_legend(ax_cm, loc="upper right", fontsize="small")

        alpha, dm = 10.0, 20.0
        cp.plot_line(
            ax_cl, fin, _cl(alpha, dm, fin), marker="", color=_NOIR, label="calcul complet"
        )
        cp.plot_line(
            ax_cl,
            niveaux,
            np.zeros_like(niveaux),
            marker="o",
            linestyle="--",
            color=BLEU,
            label="ordre 1 : ΔC_m + ΔC_n",
        )
        cp.plot_line(
            ax_cl,
            niveaux,
            _cl(alpha, dm, niveaux),
            marker="D",
            linestyle="none",
            color=VERMILLON,
            label="ordre 2 : + ΔC_mn",
        )
        ax_cl.set_xlabel("δn (°)")
        ax_cl.set_ylabel("Cl")
        ax_cl.set_xticks(cr.DN)
        ax_cl.grid(True, alpha=0.3)
        cp.set_title(ax_cl, "Roulis induit à α = 10°, δm = 20° : une interaction pure")
        cp.make_legend(ax_cl, loc="upper left", fontsize="small")
        enregistrer(fig, "remplissage_04_additivite")


# ---------------------------------------------------------------------------
# 5. Le coût de chaque méthode
# ---------------------------------------------------------------------------

#: Méthode → (libellé court, famille).
_FAMILLES = {
    "factoriel complet, sans symétrie": ("factoriel\nsans symétrie", "grille"),
    "factoriel complet": ("factoriel\ncomplet", "grille"),
    "factoriel à niveaux inégaux": ("factoriel\nniveaux inégaux", "grille"),
    "décomposition ordre 2": ("décomposition\nordre 2", "décomposition"),
    "grille creuse niveau 3": ("grille creuse\nniveau 3", "modèle"),
    "décomposition ordre 1": ("décomposition\nordre 1", "décomposition"),
    "remplissage d'espace 30·d": ("remplissage\nd'espace 30·d", "modèle"),
    "adaptatif": ("adaptatif", "modèle"),
    "grille creuse niveau 2": ("grille creuse\nniveau 2", "modèle"),
    "composite centré": ("composite\ncentré", "modèle"),
    "Box-Behnken": ("Box-\nBehnken", "modèle"),
    "étoile": ("étoile", "grille"),
}
_COULEUR_FAMILLE = {"grille": BLEU, "décomposition": ORANGE, "modèle": VERT}
_LEGENDE_FAMILLE = {
    "grille": "sur grille : la CFD est la table",
    "décomposition": "décomposition : tables à sommer",
    "modèle": "métamodèle entre CFD et table",
}


def _milliers(n: int) -> str:
    """Entier à la française, espace fine insécable entre les milliers."""
    return f"{n:,}".replace(",", chr(0x202F))


def figure_decomptes() -> None:
    """Total de calculs par méthode, échelle logarithmique."""
    decomptes = cr.decomptes()
    with cp.style_context(PROFIL):
        fig, ax = cp.new_figure(figsize=(12.5, 5.6))
        rangs = {m: i for i, m in enumerate(decomptes)}
        for famille, couleur in _COULEUR_FAMILLE.items():
            membres = [m for m in decomptes if _FAMILLES[m][1] == famille]
            barres = cp.plot_bar(
                ax,
                [rangs[m] for m in membres],
                [decomptes[m][1] for m in membres],
                color=couleur,
                label=_LEGENDE_FAMILLE[famille],
                width=0.72,
            )
            for barre, m in zip(barres, membres):
                if m in cr.ESTIMEES:
                    barre.set_hatch("///")
                    barre.set_alpha(0.75)
                texte = ("≈ " if m in cr.ESTIMEES else "") + _milliers(decomptes[m][1])
                ax.annotate(
                    texte,
                    (barre.get_x() + barre.get_width() / 2, barre.get_height()),
                    xytext=(0, 4),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize="small",
                )
        ax.set_yscale("log")
        ax.set_ylim(60, 3e5)
        ax.set_xticks(list(rangs.values()))
        ax.set_xticklabels([_FAMILLES[m][0] for m in decomptes], fontsize="small")
        ax.set_ylabel("calculs CFD (8 Mach, 3 régimes moteur)")
        ax.grid(True, axis="y", alpha=0.3)
        cp.set_title(ax, "Nombre de calculs par méthode — hachuré : ordre de grandeur")
        cp.make_legend(ax, loc="upper right")
        enregistrer(fig, "remplissage_05_decomptes")


# ---------------------------------------------------------------------------
# 6. Avec n paramètres
# ---------------------------------------------------------------------------


def figure_parametres() -> None:
    """Croissance du coût avec le nombre de paramètres indépendants."""
    tableau = cr.par_nombre_de_parametres()
    styles = {
        "factoriel complet": (BLEU, "o", "-"),
        "décomposition ordre 1": (ORANGE, "s", "-"),
        "grille creuse niveau 2": (VERT, "^", "-"),
        "remplissage d'espace 30·d": (VERT, "D", "--"),
    }
    with cp.style_context(PROFIL):
        fig, ax = cp.new_figure(figsize=(8.6, 5.2))
        n = list(range(len(next(iter(tableau.values())))))
        for methode, totaux in tableau.items():
            couleur, marker, trait = styles[methode]
            cp.plot_line(
                ax, n, totaux, marker=marker, linestyle=trait, color=couleur, label=methode
            )
            ax.annotate(
                _milliers(totaux[-1]),
                (n[-1], totaux[-1]),
                xytext=(8, 0),
                textcoords="offset points",
                va="center",
                fontsize="small",
                color=couleur,
            )
        ax.set_yscale("log")
        ax.set_xticks(n)
        ax.set_xlim(-0.15, n[-1] + 0.55)
        ax.set_xlabel("nombre de paramètres indépendants (3 niveaux chacun)")
        ax.set_ylabel("calculs CFD (8 Mach)")
        ax.grid(True, which="both", axis="y", alpha=0.3)
        cp.set_title(ax, "Ce que coûte un paramètre de plus")
        cp.make_legend(ax, loc="upper left", fontsize="small")
        enregistrer(fig, "remplissage_06_parametres")


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    figure_symetries()
    figure_plans()
    figure_decomposition()
    figure_additivite()
    figure_decomptes()
    figure_parametres()


if __name__ == "__main__":
    main()
