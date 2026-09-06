"""Plomberie commune aux figures : tout passe par cfd-plot.

Toutes les figures du paquet se tracent avec ``cfd_plot``, et par ces
primitives-ci. Deux raisons.

D'abord le **format**. Police, tailles, marges, épaisseurs de trait, palette,
gabarit d'export : tout cela est défini dans cfd-plot, pour l'ensemble du
framework. Une figure de dispersion tracée en Matplotlib nu serait juste, et
détonnerait au milieu d'un dossier. Le tracé exige donc cfd-plot — voir
:mod:`cfd_dispersion.report._plotting_lib` — là où le calcul, lui, s'en passe.

Ensuite parce que deux outils de tracé n'existent nulle part ailleurs et
servent partout ici : :func:`assombrir`, qui donne à une courbe dérivée la
teinte de la courbe dont elle dérive, et :func:`etiqueter_ligne`, qui pose une
étiquette *sur* une courbe.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import matplotlib.colors as mcolors
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.text import Text

from ..report._plotting_lib import get_plotting

__all__ = [
    "PROFIL_DEFAUT",
    "assombrir",
    "boite_texte",
    "couleur_de_serie",
    "eclaircir",
    "enregistrer",
    "etiqueter_ligne",
    "legende",
    "lignes_reference",
    "nouvelle_figure",
    "remplir_entre",
    "style",
    "surtitre",
    "titre",
    "tracer_bande",
    "tracer_ligne",
]

#: Profil de style cfd-plot employé par défaut.
PROFIL_DEFAUT = "notebook"


# ---------------------------------------------------------------------------
# Primitives : cfd-plot, et rien d'autre
# ---------------------------------------------------------------------------


@contextmanager
def style(profil: str = PROFIL_DEFAUT) -> Iterator[None]:
    """Applique un profil de style cfd-plot, de façon **locale**.

    ``style_context`` et non ``use_style`` : ce dernier modifie les rcParams
    globaux et laisserait l'appelant avec un style qu'il n'a pas demandé.
    """
    with get_plotting().style_context(profil):
        yield


def nouvelle_figure(
    nrows: int = 1,
    ncols: int = 1,
    *,
    figsize: tuple[float, float] | None = None,
    **kwargs: Any,
) -> tuple[Figure, Any]:
    """Crée une figure et sa grille d'axes (``cfd_plot.new_figure``)."""
    return get_plotting().new_figure(nrows, ncols, figsize=figsize, **kwargs)  # type: ignore[no-any-return]


def tracer_ligne(ax: Axes, x: Any, y: Any, **kwargs: Any) -> Any:
    """Trace une courbe (``cfd_plot.plot_line``)."""
    return get_plotting().plot_line(ax, x, y, **kwargs)


def tracer_bande(
    ax: Axes,
    x: Any,
    y: Any,
    *,
    y_bas: Any,
    y_haut: Any,
    alpha: float = 0.15,
    couleur_bande: Any = None,
    label_bande: str | None = None,
    **kwargs: Any,
) -> tuple[Any, Any]:
    """Trace une courbe centrale et son enveloppe (``cfd_plot.plot_with_band``)."""
    return get_plotting().plot_with_band(  # type: ignore[no-any-return]
        ax,
        x,
        y,
        y_low=y_bas,
        y_high=y_haut,
        band_alpha=alpha,
        band_color=couleur_bande,
        band_label=label_bande,
        **kwargs,
    )


def remplir_entre(
    ax: Axes,
    x: Any,
    y1: Any,
    y2: Any,
    *,
    couleur: Any = None,
    alpha: float = 0.15,
    label: str | None = None,
    lignes: bool = False,
    options_lignes: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Remplit la zone entre deux courbes (``cfd_plot.fill_between_curves``).

    *lignes* trace en plus les deux bords. Ils sortent opaques là où le
    remplissage est transparent, et *options_lignes* permet de les assombrir :
    un bord de la teinte exacte du remplissage ne se voit pas.

    Returns
    -------
    Le polygone, ou ``(polygone, bords)`` quand *lignes* est vrai.
    """
    bords, polygones = get_plotting().fill_between_curves(
        ax,
        x,
        y1,
        y2,
        color=couleur,
        alpha=alpha,
        label=label,
        lines=lignes,
        line_kwargs=options_lignes,
        **kwargs,
    )
    polygone = polygones[0] if polygones else None
    return (polygone, list(bords)) if lignes else polygone


def lignes_reference(
    ax: Axes,
    *,
    horizontales: Sequence[float] | None = None,
    verticales: Sequence[float] | None = None,
    **kwargs: Any,
) -> list[Any]:
    """Trace des droites de repère (``cfd_plot.add_reference_lines``).

    C'est par là que passent les lignes ±kσ des figures de tirage : une ligne
    de repère a son épaisseur, sa teinte et son plan de profondeur définis
    dans cfd-plot, comme le reste du format.
    """
    return get_plotting().add_reference_lines(  # type: ignore[no-any-return]
        ax,
        hlines=list(horizontales) if horizontales is not None else None,
        vlines=list(verticales) if verticales is not None else None,
        **kwargs,
    )


def boite_texte(ax: Axes, texte: str, *, loc: str = "upper right", **kwargs: Any) -> Text:
    """Pose une boîte de texte ancrée dans un coin (``cfd_plot.add_textbox``)."""
    return get_plotting().add_textbox(ax, texte, loc=loc, **kwargs)  # type: ignore[no-any-return]


def legende(ax: Axes, **kwargs: Any) -> Any:
    """Construit la légende, s'il y a quelque chose à légender.

    Le garde-fou n'est pas superflu : ``superposer_dispersion`` appelle cette
    fonction sans savoir si l'appelant a étiqueté ses courbes, et Matplotlib
    comme cfd-plot émettent un ``UserWarning`` quand il n'y a rien à mettre
    dans la légende.
    """
    if not ax.get_legend_handles_labels()[0]:
        return None
    return get_plotting().make_legend(ax, **kwargs)


def titre(ax: Axes, texte: str, **kwargs: Any) -> Any:
    """Pose le titre d'un panneau (``cfd_plot.set_title``)."""
    return get_plotting().set_title(ax, texte, **kwargs)


def surtitre(fig: Figure, texte: str, **kwargs: Any) -> Any:
    """Pose le titre général d'une figure (``cfd_plot.set_suptitle``)."""
    return get_plotting().set_suptitle(fig, texte, **kwargs)


#: Extensions de figure reconnues, pour tolérer un chemin déjà suffixé.
EXTENSIONS_FIGURE: frozenset[str] = frozenset({"png", "svg", "pdf", "eps", "jpg", "jpeg", "emf"})


def enregistrer(
    fig: Figure,
    chemin: Any,
    *,
    formats: Sequence[str] = ("png",),
    **kwargs: Any,
) -> list[Path]:
    """Écrit une figure (``cfd_plot.save_figure``), et rend les fichiers écrits.

    *chemin* est donné **sans extension** : un fichier est écrit par format
    demandé. Passer par ici plutôt que par ``Figure.savefig`` n'est pas une
    coquetterie — c'est ce qui donne au fichier le DPI, les marges et le fond
    du profil de style, donc ce qui fait qu'il s'imprime comme les autres
    figures du dossier.

    Un point dans le nom est admis, et c'est la raison d'être de cette
    fonction. ``save_figure`` compose son fichier avec ``Path.with_suffix``,
    qui remplace tout ce qui suit le **dernier** point : un nom aussi banal que
    ``CN_Mach0.85`` y perd son ``.85``, et toute une série de points de vol
    s'écrase silencieusement dans un seul fichier. Un suffixe factice est donc
    ajouté avant l'appel, pour que ce soit lui que ``with_suffix`` remplace.
    """
    base = Path(chemin)
    if base.suffix.lstrip(".").lower() in EXTENSIONS_FIGURE:
        base = base.with_suffix("")
    base = base.with_name(base.name + ".figure")
    return get_plotting().save_figure(fig, base, formats=tuple(formats), **kwargs)  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Couleurs
# ---------------------------------------------------------------------------


def assombrir(couleur: Any, facteur: float = 0.25) -> tuple[float, float, float]:
    """Assombrit une couleur de *facteur* (0 = inchangée, 1 = noire).

    Sert à donner à une courbe dérivée la teinte de celle dont elle dérive :
    l'enveloppe de dispersion d'une série garde sa couleur, la moyenne
    dispersée la reprend en plus sombre. L'œil rattache alors les deux sans
    qu'aucune légende ne l'explique.
    """
    if not 0.0 <= facteur <= 1.0:
        raise ValueError(f"facteur doit être dans [0, 1], reçu {facteur!r}")
    r, v, b = mcolors.to_rgb(couleur)
    echelle = 1.0 - facteur
    return (r * echelle, v * echelle, b * echelle)


def eclaircir(couleur: Any, facteur: float = 0.35) -> tuple[float, float, float]:
    """Éclaircit une couleur de *facteur* (0 = inchangée, 1 = blanche).

    Le pendant d':func:`assombrir`, et il sert au faisceau des courbes par
    tirage : elles doivent se lire comme la texture du fond, sous les lignes
    qui, elles, portent l'information — l'enveloppe, les ±kσ, la moyenne. À
    teinte égale, cent courbes empilées deviennent plus sombres que ce qu'elles
    sont censées soutenir.
    """
    if not 0.0 <= facteur <= 1.0:
        raise ValueError(f"facteur doit être dans [0, 1], reçu {facteur!r}")
    r, v, b = mcolors.to_rgb(couleur)
    return (
        r + (1.0 - r) * facteur,
        v + (1.0 - v) * facteur,
        b + (1.0 - b) * facteur,
    )


def couleur_de_serie(ax: Axes, label: str) -> Any:
    """Retrouve la couleur d'une courbe déjà tracée, par son libellé.

    C'est ainsi qu'une superposition de dispersion se rattache visuellement à
    la série qu'elle décrit, sans que l'appelant ait à répéter la couleur.

    Raises
    ------
    ValueError
        Si aucune courbe ne porte ce libellé ; le message liste ceux présents.
    """
    disponibles = []
    for ligne in ax.get_lines():
        courant = ligne.get_label()
        if courant == label:
            return ligne.get_color()
        if not str(courant).startswith("_"):
            disponibles.append(str(courant))
    raise ValueError(
        f"aucune courbe intitulée {label!r} sur ces axes ; "
        f"libellés présents : {disponibles or 'aucun'}"
    )


# ---------------------------------------------------------------------------
# Étiquetage sur la courbe
# ---------------------------------------------------------------------------


def etiqueter_ligne(
    ax: Axes,
    x: Any,
    y: Any,
    texte: str,
    *,
    fraction: float = 0.85,
    couleur: Any = None,
    taille: float = 7.0,
    fond: Any = None,
    fond_alpha: float = 0.6,
    **kwargs: Any,
) -> Text:
    """Pose une étiquette **sur** une courbe, inclinée comme elle.

    Matplotlib n'offre pas d'équivalent public de ``clabel`` en dehors des
    contours : cette fonction le fait à la main pour les lignes ±kσ d'une
    polaire dispersée, où une légende séparée obligerait à compter les courbes
    pour savoir laquelle est laquelle.

    L'inclinaison est calculée en coordonnées **d'affichage**, pas en
    coordonnées de données. C'est ce qui fait qu'elle suit la pente réellement
    tracée, y compris sur un axe logarithmique ou avec des échelles x et y sans
    rapport — où l'angle en unités de données n'a aucun sens visuel.

    Comme elle lit la transformation courante des axes, elle doit être appelée
    **en dernier**, une fois posés tous les artistes susceptibles de déplacer
    les limites. Sinon l'inclinaison est juste pour des axes qui n'existent
    plus.

    Parameters
    ----------
    ax:
        Les axes portant la courbe.
    x, y:
        La courbe, 1-D et de même longueur.
    texte:
        L'étiquette.
    fraction:
        Position le long de la courbe, de 0 (début) à 1 (fin). Décaler cette
        valeur d'une courbe à l'autre évite que des étiquettes voisines se
        superposent.
    couleur:
        Couleur du texte.
    taille:
        Taille de police.
    fond:
        Couleur du cartouche derrière le texte. Par défaut celle du fond des
        axes, ce qui détache l'étiquette de ce qu'il y a dessous.
    fond_alpha:
        Opacité de ce cartouche. Translucide par défaut : un cartouche opaque
        perce un trou blanc dans le faisceau qu'on venait regarder, alors
        qu'une étiquette lisible n'a pas besoin d'effacer ce qu'elle couvre.
        1.0 rend le fond plein, 0.0 le supprime.

    Returns
    -------
    matplotlib.text.Text
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.shape != y.shape:
        raise ValueError(f"x et y doivent avoir la même forme, reçu {x.shape} et {y.shape}")
    if x.size < 2:
        raise ValueError("il faut au moins deux points pour étiqueter une courbe")
    if not 0.0 <= fraction <= 1.0:
        raise ValueError(f"fraction doit être dans [0, 1], reçu {fraction!r}")

    indice = round(fraction * (x.size - 1))
    indice = min(max(indice, 0), x.size - 1)

    # Le voisin sert à mesurer la pente ; au bord, on prend celui de l'autre côté.
    voisin = indice + 1 if indice + 1 < x.size else indice - 1

    transformation = ax.transData
    (xa, ya), (xb, yb) = transformation.transform([(x[indice], y[indice]), (x[voisin], y[voisin])])
    if voisin < indice:
        xa, ya, xb, yb = xb, yb, xa, ya

    angle = float(np.degrees(np.arctan2(yb - ya, xb - xa)))
    # Une étiquette ne se lit pas à l'envers : on la retourne plutôt que de
    # laisser le texte tête en bas sur une courbe descendante raide.
    if angle > 90.0:
        angle -= 180.0
    elif angle < -90.0:
        angle += 180.0

    if fond is None:
        fond = ax.get_facecolor()

    kwargs.setdefault(
        "bbox",
        {"facecolor": fond, "edgecolor": "none", "pad": 0.8, "alpha": fond_alpha},
    )
    return ax.text(
        float(x[indice]),
        float(y[indice]),
        texte,
        rotation=angle,
        rotation_mode="anchor",
        ha="center",
        va="center",
        fontsize=taille,
        color=couleur,
        **kwargs,
    )
