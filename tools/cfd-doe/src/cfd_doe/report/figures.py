"""Figures du remplissage, tracées avec ``cfd-plot``.

Quatre familles, écrites en PNG dans le dossier de sortie :

- ``domaine.png`` : ce que les symétries épargnent — nœuds calculés, déduits,
  hors domaine — dans le plan de l'écoulement puis dans celui des braquages ;
- ``plan_<nom>.png`` : un plan, projeté sur chaque couple de facteurs, à un
  Mach ; les rôles (calcul, contrôle, test) se lisent à la couleur ;
- ``comparaison_calculs.png`` : le nombre de calculs de chaque plan ;
- ``comparaison_plans.png`` : tous les plans dans la même projection.

``cfd-plot`` est un paquet frère de ce dépôt, pas une dépendance : sans lui,
:func:`tracer_figures` lève :class:`FiguresIndisponibles` et le reste de la
commande (rapport, fichier DOE) n'est pas affecté. ::

    pip install -e ../cfd-plot
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from functools import lru_cache
from itertools import product
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from cfd_doe.data.format import formater_nombre
from cfd_doe.engine.remplissage import (
    ROLE_CALCUL,
    ROLE_CONTROLE,
    ROLE_TEST,
    Contexte,
    PlanDOE,
    PointDOE,
    Resultat,
)

__all__ = ["FiguresIndisponibles", "tracer_figures"]

PROFIL = "notebook"
DPI = 150

# Okabe-Ito : lisible en cas de daltonisme.
BLEU, ORANGE, VERT, VERMILLON, GRIS = "#0072B2", "#E69F00", "#009E73", "#D55E00", "0.55"
_COULEUR_ROLE = {ROLE_CALCUL: BLEU, ROLE_CONTROLE: VERMILLON, ROLE_TEST: VERT}
_NOM_ROLE = {ROLE_CALCUL: "calcul", ROLE_CONTROLE: "contrôle", ROLE_TEST: "test"}
_MARQUEUR_ROLE = {ROLE_CALCUL: "o", ROLE_CONTROLE: "D", ROLE_TEST: "^"}
_COULEUR_TABLE = {"oui": BLEU, "oui, par somme": ORANGE, "non": VERT}
_LEGENDE_TABLE = {
    "oui": "sur grille : la CFD est la table",
    "oui, par somme": "décomposition : tables à sommer",
    "non": "métamodèle entre CFD et table",
}


class FiguresIndisponibles(RuntimeError):
    """``cfd-plot`` (ou Matplotlib) n'est pas installé."""


@lru_cache(maxsize=1)
def _cfd_plot() -> ModuleType:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import cfd_plot
    except ImportError as erreur:
        raise FiguresIndisponibles(
            f"figures indisponibles ({erreur.name} manquant) : pip install -e ../cfd-plot"
        ) from None
    return cast(ModuleType, cfd_plot)


def _n(x: int) -> str:
    return f"{x:,}".replace(",", chr(0x202F))


def _fichier(nom: str) -> str:
    return re.sub(r"[^0-9A-Za-z_-]+", "_", nom).strip("_") or "plan"


def _enregistrer(fig: Any, chemin: Path) -> Path:
    import matplotlib.pyplot as plt

    (fichier,) = _cfd_plot().save_figure(fig, chemin, formats=("png",), dpi=DPI)
    plt.close(fig)
    return Path(fichier)


def _nuage(
    ax: Any,
    xy: Sequence[tuple[float, float]],
    *,
    couleur: str,
    plein: bool = True,
    marker: str = "o",
    taille: float = 6.0,
    label: str | None = None,
    alpha: float = 1.0,
) -> None:
    if not xy:
        return
    x, y = zip(*xy)
    ligne = _cfd_plot().plot_line(
        ax,
        x,
        y,
        linestyle="none",
        marker=marker,
        color=couleur,
        markersize=taille,
        label=label,
        alpha=alpha,
    )
    if plein:
        ligne.set_markerfacecolor(couleur)


def _axe(c: Contexte, nom: str) -> str:
    unite = " (°)" if nom in c.boite else ""
    return f"{c.symbole(nom)}{unite}"


def _marges(ax: Any, c: Contexte, x: str, y: str, plages: dict[str, tuple[float, float]]) -> None:
    for nom, fixer in ((x, ax.set_xlim), (y, ax.set_ylim)):
        bas, haut = plages[nom]
        marge = 0.08 * (haut - bas or 1.0)
        fixer(bas - marge, haut + marge)
    ax.set_xlabel(_axe(c, x))
    ax.set_ylabel(_axe(c, y))
    ax.grid(True, alpha=0.3)


def _plages(c: Contexte) -> dict[str, tuple[float, float]]:
    plages = {v: (c.boite[v].bas, c.boite[v].haut) for v in c.variables}
    plages.update({p.nom: (p.plage.bas, p.plage.haut) for p in c.parametres})
    return plages


def _mach(c: Contexte) -> float | None:
    return c.machs[0] if c.machs else None


def _a_ce_mach(plan: PlanDOE, mach: float | None) -> list[PointDOE]:
    if mach is None:
        return list(plan.points)
    return [p for p in plan.points if p.valeurs["mach"] == mach]


def _titre_mach(mach: float | None) -> str:
    return "" if mach is None else f" à Mach {formater_nombre(mach)}"


# ---------------------------------------------------------------------------
# 1. Le domaine
# ---------------------------------------------------------------------------


def _classer(
    c: Contexte, noeuds: Sequence[dict[str, float]], x: str, y: str
) -> dict[str, list[tuple[float, float]]]:
    classes: dict[str, list[tuple[float, float]]] = {"calcule": [], "deduit": [], "hors": []}
    for noeud in noeuds:
        complet = {**c.reference, **noeud}
        if c.placer(complet) is not None:
            classes["calcule"].append((noeud[x], noeud[y]))
        elif c.replier(complet) is not None:
            classes["deduit"].append((noeud[x], noeud[y]))
        else:
            classes["hors"].append((noeud[x], noeud[y]))
    return classes


def _panneau_domaine(
    ax: Any, c: Contexte, x: str, y: str, fixes: dict[str, float], titre: str
) -> None:
    cp = _cfd_plot()
    noeuds = [{**fixes, x: a, y: b} for a, b in product(c.niveaux[x], c.niveaux[y])]
    classes = _classer(c, noeuds, x, y)
    _nuage(ax, classes["hors"], couleur=GRIS, marker="x", taille=5.0, label="hors domaine")
    _nuage(ax, classes["deduit"], couleur=GRIS, plein=False, label="déduit par symétrie")
    _nuage(ax, classes["calcule"], couleur=BLEU, label="calculé")
    _marges(ax, c, x, y, _plages(c))
    cp.set_title(ax, f"{titre} : {len(classes['calcule'])} calculs sur {len(noeuds)} nœuds")


def figure_domaine(resultat: Resultat, dossier: Path) -> Path:
    """Nœuds calculés et déduits : plan de l'écoulement, puis plan des braquages."""
    c = resultat.contexte
    cp = _cfd_plot()
    libres = c.libres
    panneaux: list[tuple[str, str, dict[str, float], str]] = []
    if len(libres) >= 2:
        x, y = libres[0], libres[1]
        panneaux.append(
            (x, y, {}, f"Plan ({c.symbole(x)}, {c.symbole(y)}), le reste à la référence")
        )
    if len(libres) >= 4:
        u, v = libres[-2], libres[-1]
        ecoulement = [
            dict(zip(libres[:2], n)) for n in product(c.niveaux[libres[0]], c.niveaux[libres[1]])
        ]

        def calcules(fixes: dict[str, float]) -> int:
            noeuds = [{**fixes, u: a, v: b} for a, b in product(c.niveaux[u], c.niveaux[v])]
            return len(_classer(c, noeuds, u, v)["calcule"])

        comptes = [(calcules(f), f) for f in ecoulement]
        plein = max(comptes, key=lambda t: t[0])
        reduits = [t for t in comptes if 0 < t[0] < plein[0]]

        def ou(fixes: dict[str, float]) -> str:
            return ", ".join(f"{c.symbole(k)} = {formater_nombre(x)}°" for k, x in fixes.items())

        if plein[0]:
            panneaux.append((u, v, plein[1], f"({c.symbole(u)}, {c.symbole(v)}) à {ou(plein[1])}"))
        if reduits:
            choisi = max(reduits, key=lambda t: t[0])
            panneaux.append((u, v, choisi[1], f"Sur une symétrie, {ou(choisi[1])}"))
    if not panneaux:
        x = libres[0]
        panneaux.append((x, x, {}, f"Niveaux de {c.symbole(x)}"))

    with cp.style_context(PROFIL):
        fig, axes = cp.new_figure(
            1, len(panneaux), figsize=(6.2 * len(panneaux), 5.0), squeeze=False
        )
        for ax, (x, y, fixes, titre) in zip(axes[0], panneaux):
            _panneau_domaine(ax, c, x, y, fixes, titre)
        cp.make_figure_legend(fig, loc="outside lower center", bbox_to_anchor=None, ncol=3)
        etude = c.reduction.etude
        cp.set_suptitle(
            fig,
            f"{etude.nom} — {len(c.sous_domaines)} sous-domaines, groupe {c.reduction.groupe} : "
            "ce que les symétries épargnent",
        )
        return _enregistrer(fig, dossier / "domaine")


# ---------------------------------------------------------------------------
# 2. Un plan, projeté sur chaque couple de facteurs
# ---------------------------------------------------------------------------


def _dimensions(c: Contexte, points: Sequence[PointDOE]) -> list[str]:
    """Les colonnes qui varient dans ces points (hors Mach)."""
    candidats = [*c.libres, *(p.nom for p in c.parametres)]
    return [d for d in candidats if len({round(p.valeurs[d], 9) for p in points}) > 1]


def _tracer_roles(
    ax: Any, points: Sequence[PointDOE], x: str, y: str, taille: float, legende: bool
) -> None:
    # Les calculs d'abord, les contrôles et tests par-dessus.
    for role in (ROLE_CALCUL, ROLE_TEST, ROLE_CONTROLE):
        for fidelite in sorted({p.fidelite for p in points if p.role == role}):
            choisis = [p for p in points if p.role == role and p.fidelite == fidelite]
            label = _NOM_ROLE[role] + (f" {fidelite}" if fidelite else "")
            _nuage(
                ax,
                [(p.valeurs[x], p.valeurs[y]) for p in choisis],
                couleur=ORANGE if fidelite == "HF" and role == ROLE_CALCUL else _COULEUR_ROLE[role],
                marker=_MARQUEUR_ROLE[role],
                # Creux : un contrôle recouvre souvent un calcul en projection.
                plein=fidelite != "BF" and role != ROLE_CONTROLE,
                taille=taille
                + (
                    2.5
                    if role == ROLE_CONTROLE
                    else 1.0
                    if role == ROLE_TEST or fidelite == "HF"
                    else 0.0
                ),
                label=label if legende else None,
                alpha=0.85,
            )


def figure_plan(plan: PlanDOE, c: Contexte, dossier: Path) -> Path | None:
    """Matrice des projections d'un plan, à un Mach."""
    cp = _cfd_plot()
    mach = _mach(c)
    points = _a_ce_mach(plan, mach)
    dims = _dimensions(c, points)
    if len(dims) < 2:
        return None
    plages = _plages(c)
    k = len(dims) - 1
    with cp.style_context(PROFIL):
        cote = max(2.3, min(3.4, 13.0 / k))
        fig, axes = cp.new_figure(k, k, figsize=(cote * k + 0.6, cote * k + 0.9), squeeze=False)
        premier = True
        for i in range(k):
            for j in range(k):
                ax = axes[i][j]
                if j > i:
                    ax.set_visible(False)
                    continue
                x, y = dims[j], dims[i + 1]
                _tracer_roles(ax, points, x, y, 3.2 if len(points) > 150 else 4.5, premier)
                premier = False
                _marges(ax, c, x, y, plages)
                if i < k - 1:
                    ax.set_xlabel("")
                    ax.tick_params(labelbottom=False)
                if j > 0:
                    ax.set_ylabel("")
                    ax.tick_params(labelleft=False)
        cp.make_figure_legend(fig, loc="outside lower center", bbox_to_anchor=None, ncol=4)
        ailleurs = f", {_n(plan.compter())} en tout" if mach is not None else ""
        cp.set_suptitle(
            fig,
            f"{plan.nom} — {plan.titre} : {_n(len(points))} calculs{_titre_mach(mach)}{ailleurs}",
        )
        return _enregistrer(fig, dossier / f"plan_{_fichier(plan.nom)}")


# ---------------------------------------------------------------------------
# 3. Comparaisons
# ---------------------------------------------------------------------------


def figure_comparaison_calculs(resultat: Resultat, dossier: Path) -> Path:
    """Nombre de calculs par plan ; contrôles et tests empilés sur les calculs."""
    cp = _cfd_plot()
    c = resultat.contexte
    plans = resultat.plans
    retenu = c.remplissage.retenu
    echelle_log = max(p.compter() for p in plans) > 30 * max(1, min(p.compter() for p in plans))
    with cp.style_context(PROFIL):
        fig, ax = cp.new_figure(figsize=(max(7.5, 1.15 * len(plans) + 3.0), 5.6))
        vus: set[str] = set()
        for i, plan in enumerate(plans):
            couleur = _COULEUR_TABLE[plan.table_directe]
            label = None if plan.table_directe in vus else _LEGENDE_TABLE[plan.table_directe]
            vus.add(plan.table_directe)
            (barre,) = cp.plot_bar(
                ax, [i], [max(plan.compter(), 1)], color=couleur, label=label, width=0.7
            )
            if plan.nom == retenu:
                barre.set_linewidth(2.6)
            complements = [
                f"{_n(plan.compter(role))} {_NOM_ROLE[role]}"
                for role in (ROLE_CONTROLE, ROLE_TEST)
                if plan.compter(role)
            ]
            texte = _n(plan.compter()) + ("\ndont " + ", ".join(complements) if complements else "")
            ax.annotate(
                texte,
                (i, max(plan.compter(), 1)),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize="small",
            )
        ax.set_xticks(range(len(plans)))
        ax.set_xticklabels(
            [p.nom + ("\n(retenu)" if p.nom == retenu else "") for p in plans],
            rotation=30 if len(plans) > 6 else 0,
            ha="right" if len(plans) > 6 else "center",
        )
        haut = max(p.compter() for p in plans)
        if echelle_log:
            ax.set_yscale("log")
            ax.set_ylim(max(1, min(p.compter() for p in plans)) / 2, haut * 6)
        else:
            ax.set_ylim(0, haut * 1.22)
        conditions = f"{len(c.machs)} Mach" if c.machs else "une condition"
        ax.set_ylabel(f"calculs CFD ({conditions})")
        ax.grid(True, axis="y", alpha=0.3)
        cp.set_title(ax, f"Nombre de calculs par plan — plan retenu : {retenu} (contour épais)")
        cp.make_legend(ax, loc="upper right", fontsize="small")
        return _enregistrer(fig, dossier / "comparaison_calculs")


def figure_comparaison_plans(resultat: Resultat, dossier: Path) -> Path | None:
    """Tous les plans dans la même projection, à un Mach."""
    cp = _cfd_plot()
    c = resultat.contexte
    if len(c.libres) < 2:
        return None
    x = c.libres[0]
    y = c.libres[2] if len(c.libres) >= 3 else c.libres[1]
    mach = _mach(c)
    plans = resultat.plans
    colonnes = min(4, len(plans))
    lignes = math.ceil(len(plans) / colonnes)
    plages = _plages(c)
    with cp.style_context(PROFIL):
        fig, axes = cp.new_figure(
            lignes,
            colonnes,
            figsize=(3.6 * colonnes + 0.4, 3.5 * lignes + 0.9),
            squeeze=False,
            sharex=True,
            sharey=True,
        )
        libelles: set[str] = set()
        for ax, plan in zip(axes.flat, plans):
            points = _a_ce_mach(plan, mach)
            nouveaux = {
                _NOM_ROLE[p.role] + (f" {p.fidelite}" if p.fidelite else "") for p in points
            }
            _tracer_roles(ax, points, x, y, 3.6, legende=not nouveaux <= libelles)
            libelles |= nouveaux
            _marges(ax, c, x, y, plages)
            cp.set_title(ax, f"{plan.nom} : {_n(len(points))}", fontsize="medium")
        for ax in list(axes.flat)[len(plans) :]:
            ax.set_visible(False)
        for ligne in axes:
            for ax in ligne[1:]:
                ax.set_ylabel("")
        # Abscisses sur le dernier panneau visible de chaque colonne, pas sur une case vide.
        for j in range(colonnes):
            visibles = [axes[i][j] for i in range(lignes) if i * colonnes + j < len(plans)]
            for ax in visibles[:-1]:
                ax.set_xlabel("")
            visibles[-1].tick_params(labelbottom=True)
        cp.make_figure_legend(fig, loc="outside lower center", bbox_to_anchor=None, ncol=5)
        cp.set_suptitle(
            fig,
            f"Les plans projetés sur ({c.symbole(x)}, {c.symbole(y)}){_titre_mach(mach)} — "
            "nombre de calculs à ce Mach",
        )
        return _enregistrer(fig, dossier / "comparaison_plans")


def tracer_figures(resultat: Resultat, dossier: Path) -> list[Path]:
    """Écrit toutes les figures dans ``dossier`` ; renvoie les fichiers écrits."""
    _cfd_plot()
    dossier.mkdir(parents=True, exist_ok=True)
    fichiers: list[Path | None] = [figure_domaine(resultat, dossier)]
    fichiers += [figure_plan(plan, resultat.contexte, dossier) for plan in resultat.plans]
    if len(resultat.plans) > 1:
        fichiers += [
            figure_comparaison_calculs(resultat, dossier),
            figure_comparaison_plans(resultat, dossier),
        ]
    return [f for f in fichiers if f is not None]
