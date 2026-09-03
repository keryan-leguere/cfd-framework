"""Figures du tirage : la loi théorique, la valeur tirée, la reconstruction.

C'est la sortie graphique du premier cas d'usage. Par coefficient, trois
panneaux :

1. la loi théorique du **biais**, et la valeur qui en a été tirée ;
2. la même chose pour le **facteur d'échelle** ;
3. la **reconstruction** : le nominal, le dispersé, et la relation employée.

Le troisième panneau est celui qui compte. Les deux premiers montrent que
chaque composante est bien tombée dans sa loi ; seul le troisième montre ce
que cela fait au coefficient, qui est la question posée.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from ..core.convention import ConventionArg, convention
from ..core.loi import LoiDispersion
from ..core.lois import COMPOSANTES, LoiCoefficient
from ..core.tirage import Tirage
from ._base import (
    PROFIL_DEFAUT,
    boite_texte,
    legende,
    nouvelle_figure,
    style,
    surtitre,
    titre,
    tracer_ligne,
)

__all__ = ["figure_tirage", "figure_tirage_matrice", "tracer_loi"]

#: Nombre de points d'échantillonnage de la densité théorique.
_N_GRILLE = 400


def tracer_loi(
    ax: Axes,
    loi: LoiDispersion,
    *,
    valeur: float | None = None,
    couleur: Any = "C0",
    label: str | None = None,
) -> None:
    """Trace la densité théorique d'une loi, et éventuellement une valeur tirée.

    Une loi dégénérée n'a pas de densité : OpenTURNS rend une **masse** de
    probabilité, sans commune mesure avec la densité d'une loi continue. Elle
    est donc dessinée comme ce qu'elle est — un trait vertical à sa valeur —
    plutôt que sur une échelle qui n'aurait pas de sens.
    """
    if loi.est_degeneree:
        ax.axvline(loi.M_theorique, color=couleur, lw=2.0, label=label or "masse")
        ax.set_ylim(0.0, 1.0)
        ax.set_yticks([])
        # `axvline` ne contraint pas l'axe des x : sans cela, Matplotlib
        # retombe sur (0, 1) et la masse se retrouve écrasée contre le bord.
        ax.set_xlim(*loi.plage_utile())
    else:
        bas, haut = loi.plage_utile()
        grille = np.linspace(bas, haut, _N_GRILLE)
        densite = loi.pdf(grille)
        tracer_ligne(ax, grille, densite, color=couleur, label=label, marker="")
        ax.fill_between(grille, 0.0, densite, color=couleur, alpha=0.15, linewidth=0.0)
        ax.set_ylim(bottom=0.0)

    if valeur is not None:
        ax.axvline(
            float(valeur),
            color="C3",
            ls="--",
            lw=1.4,
            label=f"tiré : {float(valeur):.4g}",
            zorder=5,
        )

    # Les bornes du support : ce qui distingue visuellement une tronquée d'une
    # gaussienne pleine, et donc le premier contrôle de la validation.
    if loi.est_bornee and not loi.est_degeneree:
        for borne in loi.support():
            ax.axvline(borne, color="0.6", ls=":", lw=0.8, zorder=0)

    ax.set_ylabel("densité")


def figure_tirage(
    coefficient: str,
    loi: LoiCoefficient,
    tirage: Tirage,
    *,
    nominal: Any,
    x: Any = None,
    convention_: ConventionArg = None,
    axes: Sequence[Axes] | None = None,
    profil: str = PROFIL_DEFAUT,
    figsize: tuple[float, float] | None = None,
) -> tuple[Figure, Any]:
    """Les trois panneaux d'un coefficient tiré.

    Parameters
    ----------
    coefficient:
        Le nom du coefficient, pour les titres.
    loi:
        Ses deux lois (biais et facteur d'échelle).
    tirage:
        Le tirage dont sont extraites les deux valeurs.
    nominal:
        La valeur nominale du coefficient — un scalaire, ou tout un balayage.
    x:
        L'abscisse, si *nominal* est un balayage. Sans elle, l'indice sert
        d'abscisse.
    convention_:
        La relation de reconstruction. Par défaut celle que porte le tirage.
    axes:
        Trois axes existants où dessiner, au lieu de créer une figure.
    profil:
        Profil de style cfd-plot.

    Returns
    -------
    (Figure, axes)

    Raises
    ------
    ValueError
        Si *axes* n'en contient pas exactement trois, ou si le coefficient est
        absent du tirage.
    """
    if coefficient not in tirage:
        raise ValueError(
            f"coefficient {coefficient!r} absent du tirage ; il porte {sorted(tirage)}"
        )

    relation = tirage.convention if convention_ is None else convention(convention_)
    valeurs = tirage[coefficient]

    with style(profil):
        if axes is None:
            figure, grille = nouvelle_figure(1, 3, figsize=figsize or (12.0, 3.6))
            trois = list(np.ravel(grille))
        else:
            trois = list(axes)
            if len(trois) != 3:
                raise ValueError(f"attendu 3 axes, reçu {len(trois)}")
            figure_ = trois[0].get_figure()
            assert figure_ is not None
            figure = figure_

        for panneau, composante in zip(trois[:2], COMPOSANTES):
            tracer_loi(
                panneau,
                loi.composante(composante),
                valeur=valeurs[composante],
                couleur="C0" if composante == "Biais" else "C1",
                label="loi théorique",
            )
            panneau.set_xlabel(composante)
            titre(panneau, f"{coefficient} — {composante}")
            boite_texte(
                panneau,
                _description_loi(loi.composante(composante)),
                loc="upper left",
                fontsize=7,
            )
            legende(panneau, loc="upper right", fontsize=7)

        _panneau_reconstruction(
            trois[2],
            coefficient,
            nominal=nominal,
            x=x,
            biais=valeurs["Biais"],
            fe=valeurs["FE"],
            relation=relation,
        )

        if axes is None:
            surtitre(figure, f"Tirage de {coefficient} — {tirage.resume}", fontsize=10)

    return figure, np.array(trois)


def _panneau_reconstruction(
    ax: Axes,
    coefficient: str,
    *,
    nominal: Any,
    x: Any,
    biais: float,
    fe: float,
    relation: Any,
) -> None:
    """Le troisième panneau : nominal, dispersé, et l'écart entre les deux."""
    nominal_ = np.atleast_1d(np.asarray(nominal, dtype=float))
    disperse = np.atleast_1d(relation(nominal_, biais, fe))

    if nominal_.size == 1:
        _reconstruction_scalaire(ax, coefficient, float(nominal_[0]), float(disperse[0]))
    else:
        abscisse = (
            np.arange(nominal_.size, dtype=float) if x is None else np.asarray(x, dtype=float)
        )
        tracer_ligne(ax, abscisse, nominal_, label="nominal", color="0.35", ls="--", marker="")
        tracer_ligne(ax, abscisse, disperse, label="dispersé", color="C3", marker="")
        ax.set_xlabel("x" if x is None else "")
        ax.set_ylabel(coefficient)
        legende(ax, loc="best", fontsize=7)

    ecart = float(np.mean(disperse - nominal_))
    reference = float(np.mean(np.abs(nominal_)))
    relatif = f"{100.0 * ecart / reference:+.2f} %" if reference > 0.0 else "—"
    boite_texte(
        ax,
        f"{relation.formule}\nbiais = {biais:.4g}\nFE = {fe:.4g}\n"
        f"écart moyen = {ecart:+.4g} ({relatif})",
        loc="upper left",
        fontsize=7,
    )
    titre(ax, f"{coefficient} — reconstruction")


def _reconstruction_scalaire(ax: Axes, coefficient: str, nominal: float, disperse: float) -> None:
    """Deux valeurs : un diagramme à barres se lit mieux que deux courbes d'un point."""
    positions = [0.0, 1.0]
    valeurs = (nominal, disperse)
    ax.bar(positions, list(valeurs), width=0.5, color=["0.6", "C3"])
    ax.set_xticks(positions)
    ax.set_xticklabels(["nominal", "dispersé"])
    ax.set_ylabel(coefficient)
    ax.axhline(0.0, color="0.4", lw=0.6, zorder=0)

    # Les étiquettes se posent à la pointe de chaque barre, vers l'extérieur.
    # Il faut ensuite leur faire de la place : sans cela elles sortent des
    # axes et se font rogner, ce qui est exactement le chiffre qu'on venait
    # lire. La boîte de paramètres occupe le haut à gauche, d'où la marge
    # haute plus généreuse.
    for position, valeur in zip(positions, valeurs):
        ax.annotate(
            f"{valeur:.4g}",
            (position, valeur),
            textcoords="offset points",
            xytext=(0, 5 if valeur >= 0 else -11),
            ha="center",
            va="bottom" if valeur >= 0 else "top",
            fontsize=7,
        )

    bas = min(0.0, *valeurs)
    haut = max(0.0, *valeurs)
    etendue = haut - bas or max(abs(haut), 1.0)
    # La marge est généreuse du côté où tombent les étiquettes — sous les
    # barres négatives, au-dessus des positives — et le haut en garde toujours
    # pour la boîte de paramètres.
    marge_bas = 0.28 if bas < 0.0 else 0.08
    # 0.62 et non 0.40 : la boîte de paramètres fait quatre lignes et descend
    # jusqu'au tiers supérieur des axes, juste au-dessus de la barre nominale.
    # Une marge trop courte lui fait recouvrir l'étiquette de cette barre —
    # c'est-à-dire le chiffre que le panneau existe pour donner.
    marge_haut = 0.62 if haut > 0.0 else 0.20
    ax.set_ylim(bas - marge_bas * etendue, haut + marge_haut * etendue)


def _description_loi(loi: LoiDispersion) -> str:
    """Le contenu de la boîte de paramètres d'un panneau de loi."""
    lignes = [loi.label, f"M = {loi.M:g}   ET = {loi.ET:g}"]
    if not loi.est_degeneree:
        lignes.append(f"σ = {loi.ET_theorique:.4g}")
        bas, haut = loi.support()
        if loi.est_bornee:
            lignes.append(f"support [{bas:.4g}, {haut:.4g}]")
        else:
            # Pas de « ℝ » : le glyphe manque des polices de figure et
            # s'y affiche en carré vide. Le rapport terminal, lui, le garde.
            lignes.append("support non borné")
    return "\n".join(lignes)


def figure_tirage_matrice(
    lois: Any,
    tirage: Tirage,
    *,
    nominaux: Any,
    x: Any = None,
    coefficients: Sequence[str] | None = None,
    convention_: ConventionArg = None,
    profil: str = PROFIL_DEFAUT,
    figsize: tuple[float, float] | None = None,
) -> tuple[Figure, Any]:
    """Une ligne de trois panneaux par coefficient.

    Parameters
    ----------
    lois:
        Le jeu de lois.
    tirage:
        Le tirage à illustrer.
    nominaux:
        ``{coefficient: valeur nominale}``.
    coefficients:
        Les coefficients à représenter, dans l'ordre voulu. Par défaut, tous
        ceux du jeu de lois.

    Returns
    -------
    (Figure, axes 2-D)
    """
    noms = list(coefficients) if coefficients is not None else list(lois)
    if not noms:
        raise ValueError("aucun coefficient à représenter")

    manquants = sorted(set(noms) - set(lois))
    if manquants:
        raise ValueError(f"coefficient(s) {manquants} absent(s) du jeu de lois")

    with style(profil):
        figure, grille = nouvelle_figure(len(noms), 3, figsize=figsize or (12.0, 3.4 * len(noms)))
        grille = np.atleast_2d(grille)

        for ligne, nom in zip(grille, noms):
            figure_tirage(
                nom,
                lois[nom],
                tirage,
                nominal=nominaux[nom],
                x=x,
                convention_=convention_,
                axes=list(ligne),
                profil=profil,
            )

        surtitre(figure, f"Tirage — {tirage.resume}", fontsize=10)

    return figure, grille
