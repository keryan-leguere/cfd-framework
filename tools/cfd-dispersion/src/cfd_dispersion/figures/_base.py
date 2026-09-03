"""Plomberie commune aux figures : cfd-plot si présent, Matplotlib sinon.

Toutes les figures du paquet passent par ici, pour deux raisons.

D'abord parce que ``cfd_plot`` est **optionnel** : le paquet doit rester
utilisable déployé seul (voir
:mod:`cfd_dispersion.report._plotting_lib`). Chaque primitive a donc une
version cfd-plot, qui donne le style maison, et une version Matplotlib nue qui
trace la même chose sans lui.

Ensuite parce que deux outils de tracé n'existent nulle part ailleurs et
servent partout ici : :func:`assombrir`, qui donne à une courbe dérivée la
teinte de la courbe dont elle dérive, et :func:`etiqueter_ligne`, qui pose une
étiquette *sur* une courbe.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
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
    "etiqueter_ligne",
    "legende",
    "nouvelle_figure",
    "remplir_entre",
    "style",
    "titre",
    "tracer_bande",
    "tracer_ligne",
]

#: Profil de style cfd-plot employé par défaut.
PROFIL_DEFAUT = "notebook"


# ---------------------------------------------------------------------------
# Primitives : cfd-plot quand il est là, Matplotlib sinon
# ---------------------------------------------------------------------------


@contextmanager
def style(profil: str = PROFIL_DEFAUT) -> Iterator[None]:
    """Applique un profil de style cfd-plot, de façon **locale**.

    ``style_context`` et non ``use_style`` : ce dernier modifie les rcParams
    globaux et laisserait l'appelant avec un style qu'il n'a pas demandé.
    """
    module = get_plotting()
    if module is None:
        yield
        return
    with module.style_context(profil):
        yield


def nouvelle_figure(
    nrows: int = 1,
    ncols: int = 1,
    *,
    figsize: tuple[float, float] | None = None,
    **kwargs: Any,
) -> tuple[Figure, Any]:
    """Crée une figure et sa grille d'axes."""
    module = get_plotting()
    if module is not None:
        return module.new_figure(nrows, ncols, figsize=figsize, **kwargs)  # type: ignore[no-any-return]
    return plt.subplots(nrows, ncols, figsize=figsize, **kwargs)


def tracer_ligne(ax: Axes, x: Any, y: Any, **kwargs: Any) -> Any:
    """Trace une courbe, avec le traitement de marqueur maison si disponible."""
    module = get_plotting()
    if module is not None:
        return module.plot_line(ax, x, y, **kwargs)
    kwargs.setdefault("marker", "")
    (ligne,) = ax.plot(x, y, **kwargs)
    return ligne


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
    """Trace une courbe centrale et son enveloppe."""
    module = get_plotting()
    if module is not None:
        return module.plot_with_band(  # type: ignore[no-any-return]
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
    kwargs.setdefault("marker", "")
    (ligne,) = ax.plot(x, y, **kwargs)
    polygone = ax.fill_between(
        x,
        y_bas,
        y_haut,
        alpha=alpha,
        color=couleur_bande if couleur_bande is not None else ligne.get_color(),
        label=label_bande,
        linewidth=0.0,
    )
    return ligne, polygone


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
    **kwargs: Any,
) -> Any:
    """Remplit la zone entre deux courbes."""
    module = get_plotting()
    if module is not None:
        _, polygones = module.fill_between_curves(
            ax, x, y1, y2, color=couleur, alpha=alpha, label=label, lines=lignes, **kwargs
        )
        return polygones[0] if polygones else None
    return ax.fill_between(
        x, y1, y2, color=couleur, alpha=alpha, label=label, linewidth=0.0, **kwargs
    )


def boite_texte(ax: Axes, texte: str, *, loc: str = "upper right", **kwargs: Any) -> Text:
    """Pose une boîte de texte ancrée dans un coin des axes."""
    module = get_plotting()
    if module is not None:
        return module.add_textbox(ax, texte, loc=loc, **kwargs)  # type: ignore[no-any-return]

    ancres = {
        "upper left": (0.02, 0.98, "left", "top"),
        "upper right": (0.98, 0.98, "right", "top"),
        "lower left": (0.02, 0.02, "left", "bottom"),
        "lower right": (0.98, 0.02, "right", "bottom"),
        "upper center": (0.5, 0.98, "center", "top"),
        "lower center": (0.5, 0.02, "center", "bottom"),
    }
    if loc not in ancres:
        raise ValueError(f"position inconnue : {loc!r} ; attendu l'une de {sorted(ancres)}")
    x, y, ha, va = ancres[loc]
    kwargs.setdefault(
        "bbox", {"boxstyle": "round", "facecolor": "white", "alpha": 0.85, "edgecolor": "0.7"}
    )
    return ax.text(x, y, texte, transform=ax.transAxes, ha=ha, va=va, **kwargs)


def legende(ax: Axes, **kwargs: Any) -> Any:
    """Construit la légende, s'il y a quelque chose à légender.

    Le garde-fou n'est pas superflu : ``superposer_dispersion`` appelle cette
    fonction sans savoir si l'appelant a étiqueté ses courbes, et Matplotlib
    comme cfd-plot émettent un ``UserWarning`` quand il n'y a rien à mettre
    dans la légende.
    """
    if not ax.get_legend_handles_labels()[0]:
        return None
    module = get_plotting()
    if module is not None:
        return module.make_legend(ax, **kwargs)
    return ax.legend(**kwargs)


def titre(ax: Axes, texte: str, **kwargs: Any) -> Any:
    """Pose le titre d'un panneau."""
    module = get_plotting()
    if module is not None:
        return module.set_title(ax, texte, **kwargs)
    return ax.set_title(texte, **kwargs)


def surtitre(fig: Figure, texte: str, **kwargs: Any) -> Any:
    """Pose le titre général d'une figure."""
    module = get_plotting()
    if module is not None:
        return module.set_suptitle(fig, texte, **kwargs)
    return fig.suptitle(texte, **kwargs)


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
        axes, ce qui fait apparaître la courbe comme interrompue par
        l'étiquette au lieu de passer dessous.

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

    kwargs.setdefault("bbox", {"facecolor": fond, "edgecolor": "none", "pad": 0.8})
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
