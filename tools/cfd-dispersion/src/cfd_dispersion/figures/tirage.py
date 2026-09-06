"""Figures du tirage : les lois tirées, et ce qu'elles font au coefficient.

C'est la sortie graphique du premier cas d'usage. Par coefficient, trois
panneaux :

1. la loi théorique du **biais**, et la valeur qui en a été tirée ;
2. la même chose pour le **facteur d'échelle** ;
3. la loi du **coefficient dispersé** — les deux composantes combinées par la
   relation de reconstruction — et la valeur qu'y prend ce tirage.

Le troisième panneau est celui qui compte. Les deux premiers montrent que
chaque composante est bien tombée dans sa loi ; seul le troisième montre ce
que cela fait au coefficient, qui est la question posée. Il ne montre pas un
histogramme : la densité y est **calculée**, exactement quand la relation est
affine à nominal fixé, sinon lissée sur un gros tirage LHS — voir
:mod:`cfd_dispersion.core.combinaison`.

Chaque panneau porte ses lignes ±kσ, et le troisième un axe supérieur gradué
en **pourcentage du nominal** : la dispersion d'un coefficient se juge presque
toujours en relatif, et lire ce pourcentage sur une règle vaut mieux que le
calculer de tête à partir de l'axe du bas.

Tracer et écrire ne font qu'un appel : ``chemin=`` suffit, et le fichier part
en SVG par le gabarit d'export de cfd-plot ::

    figure_tirage("CN", lois["CN"], tirage, nominal=0.85, chemin=sortie / "CN")

:func:`figure_tirage_matrice` empile les coefficients à raison de **quatre par
figure** — au-delà, les panneaux deviennent des timbres-poste — et numérote
les fichiers ``_01``, ``_02``… d'elle-même.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from ..core.combinaison import LoiCombinee, loi_combinee
from ..core.convention import ConventionArg, convention
from ..core.loi import LoiDispersion
from ..core.lois import COMPOSANTES, LoiCoefficient
from ..core.tirage import Tirage
from ._base import (
    PROFIL_DEFAUT,
    boite_texte,
    enregistrer,
    legende,
    lignes_reference,
    nouvelle_figure,
    style,
    surtitre,
    titre,
    tracer_ligne,
)

__all__ = [
    "FORMATS_DEFAUT",
    "MAX_COEFFICIENTS_PAR_FIGURE",
    "MESSAGE_SANS_NOMINAL",
    "SIGMAS_DEFAUT",
    "FigureTirage",
    "axe_pourcentage",
    "figure_tirage",
    "figure_tirage_matrice",
    "tracer_loi",
    "tracer_loi_combinee",
    "tracer_sigmas",
]

#: Nombre de points d'échantillonnage de la densité théorique.
_N_GRILLE = 400

#: Multiples de σ marqués par une ligne de repère.
SIGMAS_DEFAUT: tuple[int, ...] = (1, 2, 3)

#: Format d'écriture par défaut. Le SVG est vectoriel : il se relit à la loupe
#: dans un dossier et se réimporte sans perte dans un rapport.
FORMATS_DEFAUT: tuple[str, ...] = ("svg",)

#: Au-delà, les panneaux ne sont plus lisibles : la matrice passe à la figure
#: suivante plutôt que de rétrécir.
MAX_COEFFICIENTS_PAR_FIGURE: int = 4


@dataclass(frozen=True)
class FigureTirage:
    """Une figure de tirage, et les fichiers qu'elle a écrits.

    Attributes
    ----------
    figure:
        La figure Matplotlib, encore ouverte — à l'appelant de la fermer.
    axes:
        Les axes : forme ``(3,)`` pour :func:`figure_tirage`, ``(n, 3)`` pour
        une page de :func:`figure_tirage_matrice`.
    fichiers:
        Les fichiers écrits, un par format demandé. Vide si aucun ``chemin``
        n'a été donné.
    coefficients:
        Les coefficients représentés, dans l'ordre des lignes.
    """

    figure: Figure
    axes: Any
    fichiers: tuple[Path, ...] = ()
    coefficients: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Panneaux
# ---------------------------------------------------------------------------


def tracer_loi(
    ax: Axes,
    loi: LoiDispersion,
    *,
    valeur: float | None = None,
    couleur: Any = "C0",
    label: str | None = None,
    sigmas: Sequence[int] | None = SIGMAS_DEFAUT,
) -> None:
    """Trace la densité théorique d'une loi, et éventuellement une valeur tirée.

    Une loi dégénérée n'a pas de densité : OpenTURNS rend une **masse** de
    probabilité, sans commune mesure avec la densité d'une loi continue. Elle
    est donc dessinée comme ce qu'elle est — un trait vertical à sa valeur —
    plutôt que sur une échelle qui n'aurait pas de sens.

    *sigmas* pose une ligne de repère à ``M ± kσ`` pour chaque k demandé, σ
    étant l'écart-type **exact** de la loi (celui d'une tronquée est plus petit
    que ``ET/2``). C'est ce qui donne l'échelle du panneau : sans ces lignes,
    une densité n'est qu'une bosse dont on ne sait pas si elle est large.
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
        _cadrer(ax, bas, haut, densite)
        tracer_sigmas(ax, loi.M_theorique, loi.ET_theorique, sigmas=sigmas)

    if valeur is not None:
        ax.axvline(
            float(valeur),
            color="C3",
            ls="--",
            lw=1.4,
            label=f"tiré : {float(valeur):.4g}",
            zorder=5,
        )
        _elargir(ax, float(valeur))

    # Les bornes du support : ce qui distingue visuellement une tronquée d'une
    # gaussienne pleine, et donc le premier contrôle de la validation.
    if loi.est_bornee and not loi.est_degeneree:
        for borne in loi.support():
            ax.axvline(borne, color="0.6", ls=":", lw=0.8, zorder=0)

    ax.set_ylabel("densité")


#: Hauteur d'axe rendue au sommet de la densité. Le reste revient à la boîte
#: de paramètres et à la légende, qui sinon recouvrent la bosse.
_PART_DENSITE: float = 0.62


def _cadrer(ax: Axes, bas: float, haut: float, densite: np.ndarray) -> None:
    """Borne les deux axes d'un panneau de densité.

    En x, la plage utile de la loi : la queue lointaine d'une gaussienne
    étalerait la bosse jusqu'à l'illisible. En y, un peu plus que le sommet —
    la boîte de paramètres et la légende occupent le haut du panneau, et sans
    cette réserve elles se posent sur la courbe.
    """
    ax.set_xlim(bas, haut)
    sommet = float(np.max(densite))
    ax.set_ylim(0.0, sommet / _PART_DENSITE if sommet > 0.0 else 1.0)


def _elargir(ax: Axes, valeur: float, *, marge: float = 0.05) -> None:
    """Élargit l'axe des x pour qu'une valeur repérée y tombe.

    Les panneaux bornent leur axe sur la plage utile de la loi — sinon la
    queue lointaine d'une gaussienne écraserait la bosse. Un tirage peut
    pourtant sortir de cette plage, et une valeur tirée invisible serait le
    contraire de ce que le panneau existe pour montrer.
    """
    bas, haut = ax.get_xlim()
    if bas <= valeur <= haut:
        return
    largeur = (haut - bas) or max(abs(valeur), 1.0)
    ax.set_xlim(min(bas, valeur - marge * largeur), max(haut, valeur + marge * largeur))


def tracer_sigmas(
    ax: Axes,
    centre: float,
    sigma: float,
    *,
    sigmas: Sequence[int] | None = SIGMAS_DEFAUT,
    etiquettes: bool = True,
) -> list[Any]:
    """Pose les lignes ±kσ autour de *centre*, et les étiquette.

    Les lignes passent par ``cfd_plot.add_reference_lines`` — c'est là que
    sont définis leur teinte, leur épaisseur et leur plan de profondeur. Seuls
    les multiples qui tombent dans les limites actuelles de l'axe sont tracés :
    une ligne 3σ hors champ ne se voit pas, mais élargirait l'axe et écraserait
    la densité qu'on vient lire.

    Doit donc être appelée une fois l'axe borné.
    """
    if not sigmas or sigma <= 0.0:
        return []

    bas, haut = ax.get_xlim()
    positions: list[float] = []
    etiquetage: list[tuple[float, str]] = []
    for k in sigmas:
        for signe in (-1, 1):
            x = centre + signe * k * sigma
            if bas < x < haut:
                positions.append(x)
                etiquetage.append((x, f"{signe * k:+d}σ"))

    artistes = lignes_reference(
        ax, verticales=positions, color="0.45", linestyle="-.", linewidth=0.7
    )

    if etiquettes:
        # Au pied de la ligne, et non en tête : le haut du panneau appartient
        # à la boîte de paramètres et à la légende, qui recouvriraient
        # l'étiquette — donc précisément le repère qu'on venait poser.
        for x, texte in etiquetage:
            ax.annotate(
                texte,
                (x, 0.0),
                xycoords=("data", "axes fraction"),
                textcoords="offset points",
                xytext=(0, 4),
                rotation=90,
                ha="center",
                va="bottom",
                fontsize=6,
                color="0.35",
                bbox={"facecolor": ax.get_facecolor(), "edgecolor": "none", "pad": 0.5},
            )
    return artistes


def tracer_loi_combinee(
    ax: Axes,
    combinee: LoiCombinee,
    *,
    valeur: float | None = None,
    couleur: Any = "C2",
    sigmas: Sequence[int] | None = SIGMAS_DEFAUT,
    pourcentage: bool = True,
) -> None:
    """Trace la loi du coefficient dispersé, nominal et tirage repérés.

    Le panneau répond à « de combien mon coefficient peut-il bouger ». D'où,
    en plus de la densité : le nominal, la valeur effectivement tirée, les
    lignes ±kσ, et — quand le nominal n'est pas nul — un axe supérieur gradué
    en pourcentage d'écart au nominal.
    """
    bas, haut = combinee.plage_utile()

    if combinee.est_degeneree:
        ax.axvline(combinee.M_theorique, color=couleur, lw=2.0, label="masse")
        ax.set_ylim(0.0, 1.0)
        ax.set_yticks([])
        ax.set_xlim(bas, haut)
    else:
        grille = np.linspace(bas, haut, _N_GRILLE)
        densite = combinee.pdf(grille)
        tracer_ligne(ax, grille, densite, color=couleur, label="loi du coefficient", marker="")
        ax.fill_between(grille, 0.0, densite, color=couleur, alpha=0.15, linewidth=0.0)
        _cadrer(ax, bas, haut, densite)

    ax.axvline(
        combinee.nominal,
        color="0.35",
        ls="--",
        lw=1.2,
        label=f"nominal : {combinee.nominal:.4g}",
        zorder=4,
    )
    if valeur is not None:
        pourcent = combinee.pourcent(float(valeur))
        detail = "" if pourcent is None else f" ({pourcent:+.2f} %)"
        ax.axvline(
            float(valeur),
            color="C3",
            lw=1.6,
            label=f"dispersé : {float(valeur):.4g}{detail}",
            zorder=5,
        )
        _elargir(ax, float(valeur))

    bornes = combinee.bornes()
    if bornes is not None and not combinee.est_degeneree:
        for borne in bornes:
            ax.axvline(borne, color="0.6", ls=":", lw=0.8, zorder=0)

    tracer_sigmas(ax, combinee.M_theorique, combinee.ET_theorique, sigmas=sigmas)

    ax.set_xlabel(combinee.coefficient)
    ax.set_ylabel("densité")

    if pourcentage:
        axe_pourcentage(ax, combinee.nominal)


def axe_pourcentage(ax: Axes, nominal: float) -> Any:
    """Ajoute l'axe supérieur en pourcentage d'écart au nominal.

    Rien si le nominal est nul : un écart relatif y est indéfini, et un axe
    muet vaut mieux qu'un axe faux.
    """
    if nominal == 0.0:
        return None

    reference = abs(nominal)

    def vers_pourcent(valeur: Any) -> Any:
        return 100.0 * (np.asarray(valeur, dtype=float) - nominal) / reference

    def depuis_pourcent(pourcent: Any) -> Any:
        return nominal + np.asarray(pourcent, dtype=float) * reference / 100.0

    secondaire = ax.secondary_xaxis("top", functions=(vers_pourcent, depuis_pourcent))
    secondaire.set_xlabel("écart au nominal [%]", fontsize=7)
    secondaire.tick_params(labelsize=6)
    return secondaire


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def figure_tirage(
    coefficient: str,
    loi: LoiCoefficient,
    tirage: Tirage,
    *,
    nominal: Any = None,
    chemin: Any = None,
    formats: Sequence[str] = FORMATS_DEFAUT,
    x: Any = None,
    reference: float | None = None,
    convention_: ConventionArg = None,
    etiquette: str | None = None,
    sigmas: Sequence[int] | None = SIGMAS_DEFAUT,
    axes: Sequence[Axes] | None = None,
    profil: str = PROFIL_DEFAUT,
    figsize: tuple[float, float] | None = None,
) -> FigureTirage:
    """Les trois panneaux d'un coefficient tiré — et son fichier.

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
        **Facultative** : sans elle, les deux panneaux de composantes sont
        tracés et le troisième reste vide, en le disant. La loi du coefficient
        dispersé n'est pas calculable sans son nominal, puisque le facteur
        d'échelle le multiplie.
    chemin:
        Où écrire la figure, **sans extension**. Donné, la figure est écrite
        immédiatement : tracer et enregistrer ne font qu'un appel. Omis, rien
        n'est écrit et l'appelant garde la figure.
    formats:
        Les formats d'écriture. SVG par défaut.
    x:
        L'abscisse, si *nominal* est un balayage. Sert à nommer le point de
        référence.
    reference:
        Le point du balayage où calculer la loi du coefficient. Une abscisse
        si *x* est donné, un indice sinon. Par défaut, le milieu du balayage.
    convention_:
        La relation de reconstruction. Par défaut celle que porte le tirage.
    etiquette:
        Ce qui situe la figure — le point de vol, typiquement. Repris dans le
        titre général : un fichier sorti de son dossier doit encore dire d'où
        il vient.
    sigmas:
        Les multiples de σ marqués sur chaque panneau ; None pour aucun.
    axes:
        Trois axes existants où dessiner, au lieu de créer une figure.
    profil:
        Profil de style cfd-plot.

    Returns
    -------
    FigureTirage
        ``.figure``, ``.axes`` (forme ``(3,)``) et ``.fichiers``.

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
            figure, grille = nouvelle_figure(1, 3, figsize=figsize or (12.0, 3.8))
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
                sigmas=sigmas,
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

        _panneau_coefficient(
            trois[2],
            coefficient,
            loi,
            nominal=nominal,
            x=x,
            reference=reference,
            biais=valeurs["Biais"],
            fe=valeurs["FE"],
            relation=relation,
            sigmas=sigmas,
        )

        if axes is None:
            surtitre(
                figure,
                f"Tirage de {coefficient}{_situe(etiquette)} — {tirage.resume}",
                fontsize=10,
            )

        fichiers = _ecrire(figure, chemin, formats)

    return FigureTirage(
        figure=figure,
        axes=np.array(trois),
        fichiers=fichiers,
        coefficients=(coefficient,),
    )


def _situe(etiquette: str | None) -> str:
    """L'étiquette de situation, prête à s'insérer dans un titre."""
    return "" if not etiquette else f" — {etiquette}"


def _ecrire(figure: Figure, chemin: Any, formats: Sequence[str]) -> tuple[Path, ...]:
    """Écrit la figure si un chemin est donné, et rend les fichiers écrits."""
    if chemin is None:
        return ()
    Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    return tuple(enregistrer(figure, chemin, formats=tuple(formats)))


def _panneau_coefficient(
    ax: Axes,
    coefficient: str,
    loi: LoiCoefficient,
    *,
    nominal: Any,
    x: Any,
    reference: float | None,
    biais: float,
    fe: float,
    relation: Any,
    sigmas: Sequence[int] | None,
) -> None:
    """Le troisième panneau : la loi du coefficient, biais et FE combinés."""
    if nominal is None:
        _panneau_sans_nominal(ax, coefficient)
        return

    valeur_nominale, situation = _point_de_reference(nominal, x, reference)
    combinee = loi_combinee(loi, valeur_nominale, convention_=relation)
    disperse = float(np.asarray(relation(valeur_nominale, biais, fe), dtype=float).reshape(-1)[0])

    tracer_loi_combinee(ax, combinee, valeur=disperse, sigmas=sigmas)
    titre(ax, f"{coefficient} — coefficient dispersé")
    boite_texte(
        ax,
        _description_combinaison(combinee, disperse=disperse, situation=situation),
        loc="upper left",
        fontsize=7,
    )
    legende(ax, loc="upper right", fontsize=7)


#: Ce que dit le troisième panneau quand il n'a pas de quoi être tracé.
MESSAGE_SANS_NOMINAL: str = (
    "Pas de valeur nominale pour {coefficient}.\n\n"
    "La loi du coefficient dispersé se calcule en un point : le facteur\n"
    "d'échelle multiplie le nominal, donc sans lui la dispersion n'a\n"
    "pas d'échelle. Les deux panneaux de gauche restent valables tels\n"
    "quels — ce sont les lois des composantes, elles ne dépendent de rien.\n\n"
    "Pour l'obtenir : nominal=<valeur de {coefficient}>,\n"
    'ou nominaux={{"{coefficient}": …}} en matrice.'
)


def _panneau_sans_nominal(ax: Axes, coefficient: str) -> None:
    """Le troisième panneau, laissé vide et expliqué.

    Un panneau blanc sans un mot se lit comme un bogue. Un panneau blanc qui
    dit ce qui lui manque, et ce qu'il faudrait lui donner, se lit comme une
    réponse — et les deux premiers panneaux, eux, restent entièrement lisibles.

    Les axes sont éteints plutôt que laissés vides : une graduation de 0 à 1
    sous un message d'absence ferait croire à une grandeur tracée.
    """
    titre(ax, f"{coefficient} — coefficient dispersé")
    ax.set_axis_off()
    ax.text(
        0.5,
        0.5,
        MESSAGE_SANS_NOMINAL.format(coefficient=coefficient),
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=7.5,
        color="0.35",
        linespacing=1.5,
        bbox={"facecolor": ax.get_facecolor(), "edgecolor": "0.75", "boxstyle": "round,pad=0.6"},
    )


def _point_de_reference(nominal: Any, x: Any, reference: float | None) -> tuple[float, str]:
    """Ramène un nominal éventuellement balayé à **une** valeur, et la nomme.

    La loi du coefficient dispersé n'existe qu'en un point : le facteur
    d'échelle multiplie le nominal, donc la largeur de la loi change le long
    d'un balayage. Plutôt que de moyenner des lois qui ne sont pas les mêmes,
    le panneau en montre une, et dit laquelle.
    """
    valeurs = np.atleast_1d(np.asarray(nominal, dtype=float))
    if valeurs.size == 1:
        return float(valeurs[0]), ""

    abscisses = None if x is None else np.atleast_1d(np.asarray(x, dtype=float))
    if abscisses is not None and abscisses.size != valeurs.size:
        raise ValueError(
            f"x et nominal doivent avoir la même longueur, reçu {abscisses.size} et {valeurs.size}"
        )

    if reference is None:
        indice = int(valeurs.size // 2)
    elif abscisses is not None:
        indice = int(np.argmin(np.abs(abscisses - float(reference))))
    else:
        indice = int(min(max(int(reference), 0), valeurs.size - 1))

    if abscisses is None:
        return float(valeurs[indice]), f"point {indice + 1}/{valeurs.size} du balayage"
    return float(valeurs[indice]), f"à x = {abscisses[indice]:.4g}"


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


def _description_combinaison(
    combinee: LoiCombinee,
    *,
    disperse: float,
    situation: str,
) -> str:
    """La boîte du troisième panneau : la relation, les nombres, l'écart."""
    # Le biais et le FE tirés ne sont pas repris ici : ils sont déjà lus sur
    # les deux premiers panneaux. La boîte partage sa largeur avec la légende,
    # et une ligne trop longue passe dessous.
    lignes = [combinee.convention.formule]
    if situation:
        lignes.append(situation)

    sigma = combinee.ET_theorique
    sigma_relatif = combinee.pourcent(combinee.M_theorique + sigma)
    detail_sigma = "" if sigma_relatif is None else f" ({abs(sigma_relatif):.2f} %)"
    lignes.append(f"σ = {sigma:.3g}{detail_sigma}")

    ecart = disperse - combinee.nominal
    pourcent = combinee.pourcent(disperse)
    detail_ecart = "" if pourcent is None else f" ({pourcent:+.2f} %)"
    lignes.append(f"écart = {ecart:+.3g}{detail_ecart}")
    lignes.append(combinee.methode_courte)
    return "\n".join(lignes)


def figure_tirage_matrice(
    lois: Any,
    tirage: Tirage,
    *,
    nominaux: Any = None,
    chemin: Any = None,
    formats: Sequence[str] = FORMATS_DEFAUT,
    x: Any = None,
    reference: float | None = None,
    coefficients: Sequence[str] | None = None,
    convention_: ConventionArg = None,
    etiquette: str | None = None,
    sigmas: Sequence[int] | None = SIGMAS_DEFAUT,
    max_par_figure: int = MAX_COEFFICIENTS_PAR_FIGURE,
    profil: str = PROFIL_DEFAUT,
    figsize: tuple[float, float] | None = None,
) -> list[FigureTirage]:
    """Une ligne de trois panneaux par coefficient, **quatre par figure**.

    Au-delà de *max_par_figure* coefficients, la matrice passe à la figure
    suivante : une page de dix lignes ne se lit plus, et une figure de dossier
    doit rester lisible à la taille où elle est imprimée. Les fichiers sont
    alors numérotés — ``polaire_01.svg``, ``polaire_02.svg`` — et une seule
    page garde le nom tel quel.

    Parameters
    ----------
    lois:
        Le jeu de lois.
    tirage:
        Le tirage à illustrer.
    nominaux:
        ``{coefficient: valeur nominale}``. **Facultatif**, et incomplet est
        admis : les coefficients absents gardent leurs deux premiers panneaux,
        et le troisième dit ce qui lui manque.
    chemin:
        Où écrire, **sans extension ni numéro** : la numérotation est ajoutée
        s'il y a plus d'une page.
    formats:
        Les formats d'écriture. SVG par défaut.
    coefficients:
        Les coefficients à représenter, dans l'ordre voulu. Par défaut, tous
        ceux du jeu de lois.
    max_par_figure:
        Nombre maximal de coefficients par figure.

    Returns
    -------
    list[FigureTirage]
        Une entrée par page, dans l'ordre.

    Raises
    ------
    ValueError
        Si la liste de coefficients est vide, si l'un d'eux est absent du jeu
        de lois, ou si *max_par_figure* n'est pas strictement positif.
    """
    noms = list(coefficients) if coefficients is not None else list(lois)
    if not noms:
        raise ValueError("aucun coefficient à représenter")
    if max_par_figure <= 0:
        raise ValueError(f"max_par_figure doit être strictement positif, reçu {max_par_figure!r}")

    manquants = sorted(set(noms) - set(lois))
    if manquants:
        raise ValueError(f"coefficient(s) {manquants} absent(s) du jeu de lois")

    pages = [noms[debut : debut + max_par_figure] for debut in range(0, len(noms), max_par_figure)]
    sorties: list[FigureTirage] = []

    for numero, page in enumerate(pages, start=1):
        with style(profil):
            figure, grille = nouvelle_figure(
                len(page), 3, figsize=figsize or (12.0, 3.6 * len(page))
            )
            grille = np.atleast_2d(grille)

            for ligne, nom in zip(grille, page):
                figure_tirage(
                    nom,
                    lois[nom],
                    tirage,
                    nominal=(nominaux or {}).get(nom),
                    x=x,
                    reference=reference,
                    convention_=convention_,
                    sigmas=sigmas,
                    axes=list(ligne),
                    profil=profil,
                )

            pagination = f"  ({numero}/{len(pages)})" if len(pages) > 1 else ""
            surtitre(
                figure,
                f"Tirage{_situe(etiquette)} — {tirage.resume}{pagination}",
                fontsize=10,
            )

            fichiers = _ecrire(figure, _chemin_de_page(chemin, numero, len(pages)), formats)

        sorties.append(
            FigureTirage(
                figure=figure,
                axes=grille,
                fichiers=fichiers,
                coefficients=tuple(page),
            )
        )

    return sorties


def _chemin_de_page(chemin: Any, numero: int, total: int) -> Any:
    """Numérote le chemin d'une page, s'il y en a plusieurs."""
    if chemin is None or total == 1:
        return chemin
    base = Path(chemin)
    return base.with_name(f"{base.name}_{numero:02d}")
