"""L'ensemble des tirages d'un point de vol, en histogrammes.

La figure de tirage montre **un** tirage : ses deux composantes et le
coefficient qui en sort. Celle-ci montre **tous** les tirages d'un point de vol
à la fois, dans les mêmes trois panneaux :

1. le **biais** obtenu sur les n tirages, contre la loi qui le prescrivait ;
2. le **facteur d'échelle**, de même ;
3. le **coefficient**, tel que le modèle l'a rendu — contre la loi combinée,
   quand on la connaît.

C'est la vue qui répond à « qu'est-ce que ça a donné », là où la figure de
tirage répond à « qu'est-ce qu'un tirage fait à mon coefficient ».

Lois et sorties décalées
------------------------
La table de lois disperse ce que le modèle *consomme* ; le tableau rend ce
qu'il *produit*. Les deux listes ne coïncident pas toujours, et les deux cas
sont traités différemment — c'est même là que cette figure se distingue de
celle du tirage :

======================  ==============================  =======================
                        panneaux biais et FE            panneau coefficient
======================  ==============================  =======================
lois **et** sortie      prescrite + obtenue             obtenu + loi combinée
lois, pas de sortie     prescrite + obtenue             message : rien d'obtenu
sortie, pas de lois     message : aucune loi            **l'histogramme obtenu**
======================  ==============================  =======================

Le troisième cas est le seul que la figure de tirage ne peut pas traiter : sans
loi il n'y a pas de tirage à montrer, mais il y a bien un échantillon de
valeurs — et un histogramme est déjà la moitié de la réponse.

Une ligne par tirage
--------------------
L'histogramme suppose **une ligne par tirage** dans le point de vol. Si le
modèle a été appelé en croisé — sept incidences par tirage — chaque valeur
apparaît sept fois, et l'histogramme du coefficient mélange le balayage et la
dispersion. Le parcours le refuse plutôt que de le tracer, en nommant la
colonne qui manque au point de vol.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes

from ..core.combinaison import loi_combinee
from ..core.convention import Convention, ConventionArg, convention
from ..core.lois import COMPOSANTES, JeuDeLois, LoiCoefficient
from ..core.tableau import COLONNE_NUMERO
from ._base import PROFIL_DEFAUT, boite_texte, legende, nouvelle_figure, style, surtitre, titre
from ._base import tracer_ligne as _tracer_ligne
from .densite import tracer_densite_realisee
from .par_pdv import (
    NOM_MATRICE,
    _nominaux_du_point,
    _preparer,
    _repartir,
    _selectionner,
    _specifications,
    chemin_du_point_de_vol,
    etiquette_du_point_de_vol,
)
from .tirage import (
    FORMATS_DEFAUT,
    MAX_COEFFICIENTS_PAR_FIGURE,
    SIGMAS_DEFAUT,
    FigureTirage,
    _ecrire,
    _panneau_sans_loi,
    _situe,
    axe_pourcentage,
    tracer_sigmas,
)

__all__ = [
    "MESSAGE_SANS_SORTIE",
    "figure_histogramme",
    "figure_histogramme_matrice",
    "figures_histogramme_par_pdv",
]

#: Ce que dit le troisième panneau quand le modèle ne rend pas ce coefficient.
MESSAGE_SANS_SORTIE: str = (
    "Aucune valeur obtenue pour {coefficient}.\n\n"
    "Ce coefficient est dispersé — les deux panneaux de gauche le montrent —\n"
    "mais le modèle ne le rend pas : le tableau n'a pas de colonne à ce nom.\n"
    "C'est le cas d'une grandeur que le modèle consomme sans la publier.\n\n"
    "Pour l'obtenir : ajouter une colonne {coefficient} à la sortie du modèle."
)

#: Nombre de points de la densité prescrite tracée sur le panneau du coefficient.
_N_GRILLE = 400


def figure_histogramme(
    coefficient: str,
    loi: LoiCoefficient | None = None,
    *,
    biais: Any = None,
    fe: Any = None,
    valeurs: Any = None,
    nominal: Any = None,
    convention_: ConventionArg = None,
    chemin: Any = None,
    formats: Sequence[str] = FORMATS_DEFAUT,
    etiquette: str | None = None,
    sigmas: Sequence[int] | None = SIGMAS_DEFAUT,
    axes: Sequence[Axes] | None = None,
    profil: str = PROFIL_DEFAUT,
    figsize: tuple[float, float] | None = None,
) -> FigureTirage:
    """Les trois histogrammes d'un coefficient sur l'ensemble de ses tirages.

    Parameters
    ----------
    coefficient:
        Le nom du coefficient, pour les titres.
    loi:
        Ses deux lois, ou None si aucune ne le décrit — les deux premiers
        panneaux le disent alors, et le troisième reste utile.
    biais, fe:
        Les valeurs **obtenues** des deux composantes, une par tirage.
    valeurs:
        Le coefficient **obtenu**, une valeur par tirage : la colonne que le
        modèle a rendue.
    nominal:
        La valeur nominale du coefficient, qui situe l'histogramme et permet de
        tracer la loi combinée prescrite.
    convention_:
        La relation de reconstruction, pour cette loi combinée.
    chemin:
        Où écrire, **sans extension**. Donné, la figure est écrite : tracer et
        enregistrer ne font qu'un appel.
    etiquette:
        Ce qui situe la figure — le point de vol, typiquement.
    axes:
        Trois axes existants où dessiner, au lieu de créer une figure.

    Returns
    -------
    FigureTirage
        ``.figure``, ``.axes`` (forme ``(3,)``) et ``.fichiers``.

    Raises
    ------
    ValueError
        Si *axes* n'en contient pas exactement trois.
    """
    relation = convention(convention_)
    obtenues = {
        COMPOSANTES[0]: None if biais is None else np.asarray(biais, dtype=float).ravel(),
        COMPOSANTES[1]: None if fe is None else np.asarray(fe, dtype=float).ravel(),
    }
    rendues = None if valeurs is None else np.asarray(valeurs, dtype=float).ravel()

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
            titre(panneau, f"{coefficient} — {composante}")
            if loi is None:
                _panneau_sans_loi(panneau, coefficient, composante)
                continue
            tracer_densite_realisee(
                panneau,
                obtenues[composante] if obtenues[composante] is not None else [],
                loi=loi.composante(composante),
                couleur="C0" if composante == "Biais" else "C1",
                sigmas=sigmas,
            )
            panneau.set_xlabel(composante)

        _panneau_coefficient_obtenu(
            trois[2],
            coefficient,
            loi,
            valeurs=rendues,
            nominal=nominal,
            relation=relation,
            sigmas=sigmas,
        )

        if axes is None:
            effectif = 0 if rendues is None else rendues.size
            entete = f"Tirages de {coefficient}{_situe(etiquette)}"
            if effectif:
                entete = f"{entete} — {effectif} tirages"
            surtitre(figure, f"{entete} — {relation.formule}", fontsize=10)

        fichiers = _ecrire(figure, chemin, formats)

    return FigureTirage(
        figure=figure,
        axes=np.array(trois),
        fichiers=fichiers,
        coefficients=(coefficient,),
    )


def _panneau_coefficient_obtenu(
    ax: Axes,
    coefficient: str,
    loi: LoiCoefficient | None,
    *,
    valeurs: np.ndarray | None,
    nominal: Any,
    relation: Convention,
    sigmas: Sequence[int] | None,
) -> None:
    """Le troisième panneau : le coefficient obtenu, contre celui prescrit."""
    titre(ax, f"{coefficient} — coefficient obtenu")

    if valeurs is None or valeurs.size == 0:
        # Dispersé mais jamais rendu : le dire, plutôt qu'un panneau muet.
        ax.set_axis_off()
        ax.text(
            0.5,
            0.5,
            MESSAGE_SANS_SORTIE.format(coefficient=coefficient),
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=7.5,
            color="0.35",
            linespacing=1.5,
            bbox={
                "facecolor": ax.get_facecolor(),
                "edgecolor": "0.75",
                "boxstyle": "round,pad=0.6",
            },
        )
        return

    valeur_nominale = (
        None if nominal is None else float(np.asarray(nominal, dtype=float).reshape(-1)[0])
    )

    # La loi que le coefficient aurait dû suivre — connue seulement si on a et
    # les lois et le nominal, puisque le facteur d'échelle multiplie ce dernier.
    combinee = None
    if loi is not None and valeur_nominale is not None:
        combinee = loi_combinee(loi, valeur_nominale, convention_=relation)
        bas, haut = combinee.plage_utile()
        grille = np.linspace(
            min(bas, float(valeurs.min())), max(haut, float(valeurs.max())), _N_GRILLE
        )
        _tracer_ligne(
            ax,
            grille,
            combinee.pdf(grille),
            color="C2",
            lw=1.6,
            marker="",
            label="prescrite (combinée)",
        )

    tracer_densite_realisee(ax, valeurs, loi=None, couleur_realise="C3")

    if valeur_nominale is not None:
        ax.axvline(
            valeur_nominale,
            color="0.35",
            ls="--",
            lw=1.2,
            label=f"nominal : {valeur_nominale:.4g}",
            zorder=4,
        )

    ax.set_xlabel(coefficient)
    ax.set_ylabel("densité")
    ax.autoscale_view()
    if combinee is not None and not combinee.est_degeneree:
        tracer_sigmas(ax, combinee.M_theorique, combinee.ET_theorique, sigmas=sigmas)

    boite_texte(
        ax,
        _description_obtenu(coefficient, valeurs, valeur_nominale, combinee, relation),
        loc="upper left",
        fontsize=7,
    )
    legende(ax, loc="upper right", fontsize=7)

    if valeur_nominale is not None:
        axe_pourcentage(ax, valeur_nominale)


def _description_obtenu(
    coefficient: str,
    valeurs: np.ndarray,
    nominal: float | None,
    combinee: Any,
    relation: Convention,
) -> str:
    """La boîte du troisième panneau : obtenu contre prescrit, en clair."""
    moyenne = float(np.mean(valeurs))
    ecart_type = float(np.std(valeurs, ddof=1)) if valeurs.size > 1 else 0.0

    # Des lignes courtes : la boîte partage sa largeur avec la légende, et le
    # pourcentage — la seule lecture qui se retient — a sa ligne à lui.
    lignes = [relation.formule] if combinee is not None else ["aucune loi prescrite"]
    if nominal is not None:
        lignes.append(f"nominal = {nominal:.4g}")

    lignes.append(f"obtenu    M {moyenne:.4g}   σ {ecart_type:.3g}")
    if combinee is not None:
        lignes.append(f"prescrit  M {combinee.M_theorique:.4g}   σ {combinee.ET_theorique:.3g}")
    if nominal:
        lignes.append(f"σ obtenu = {100.0 * ecart_type / abs(nominal):.2f} % du nominal")
    return "\n".join(lignes)


def figure_histogramme_matrice(
    lois: JeuDeLois,
    *,
    obtenues: Mapping[str, Mapping[str, Any]],
    nominaux: Mapping[str, Any] | None = None,
    coefficients: Sequence[str] | None = None,
    convention_: ConventionArg = None,
    chemin: Any = None,
    formats: Sequence[str] = FORMATS_DEFAUT,
    etiquette: str | None = None,
    sigmas: Sequence[int] | None = SIGMAS_DEFAUT,
    max_par_figure: int = MAX_COEFFICIENTS_PAR_FIGURE,
    profil: str = PROFIL_DEFAUT,
    figsize: tuple[float, float] | None = None,
) -> list[FigureTirage]:
    """Une ligne de trois histogrammes par coefficient, quatre par figure.

    Parameters
    ----------
    lois:
        Le jeu de lois. Un coefficient demandé qui n'y figure pas est admis :
        sa ligne montre l'histogramme obtenu, et dit qu'aucune loi ne le décrit.
    obtenues:
        ``{coefficient: {"Biais": …, "FE": …, "valeurs": …}}`` — ce qui a été
        obtenu, tirage par tirage. Les clés manquantes sont traitées comme
        absentes.
    nominaux:
        ``{coefficient: valeur nominale}``, facultatif et incomplet admis.

    Returns
    -------
    list[FigureTirage]
        Une entrée par page.
    """
    noms = list(coefficients) if coefficients is not None else list(lois)
    if not noms:
        raise ValueError("aucun coefficient à représenter")
    if max_par_figure <= 0:
        raise ValueError(f"max_par_figure doit être strictement positif, reçu {max_par_figure!r}")

    pages = [noms[debut : debut + max_par_figure] for debut in range(0, len(noms), max_par_figure)]
    sorties: list[FigureTirage] = []

    for numero, page in enumerate(pages, start=1):
        with style(profil):
            figure, grille = nouvelle_figure(
                len(page), 3, figsize=figsize or (12.0, 3.6 * len(page))
            )
            grille = np.atleast_2d(grille)

            for ligne, nom in zip(grille, page):
                echantillons = obtenues.get(nom, {})
                figure_histogramme(
                    nom,
                    lois.get(nom),
                    biais=echantillons.get(COMPOSANTES[0]),
                    fe=echantillons.get(COMPOSANTES[1]),
                    valeurs=echantillons.get("valeurs"),
                    nominal=(nominaux or {}).get(nom),
                    convention_=convention_,
                    sigmas=sigmas,
                    axes=list(ligne),
                    profil=profil,
                )

            pagination = f"  ({numero}/{len(pages)})" if len(pages) > 1 else ""
            surtitre(figure, f"Tirages{_situe(etiquette)}{pagination}", fontsize=10)
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


# ---------------------------------------------------------------------------
# Le parcours
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _TravailHistogramme:
    """Un point de vol à tracer : ses échantillons, et rien qui ne se sérialise pas."""

    point: dict[str, Any]
    lois: JeuDeLois
    coefficients: tuple[str, ...]
    obtenues: dict[str, dict[str, Any]]
    nominaux: dict[str, Any]
    effectif: int
    dossier: Path
    etiquette: str
    formats: tuple[str, ...]
    par_coefficient: bool
    matrice: bool
    convention: Convention
    sigmas: tuple[int, ...] | None
    max_par_figure: int
    profil: str


def _executer_histogramme(travail: _TravailHistogramme) -> list[dict[str, Any]]:
    """Trace et écrit les histogrammes d'un point de vol ; rend leur inventaire."""
    import matplotlib

    matplotlib.use("Agg")

    inventaire: list[dict[str, Any]] = []
    commun = {**travail.point, "tirages": travail.effectif}

    if travail.par_coefficient:
        for nom in travail.coefficients:
            echantillons = travail.obtenues.get(nom, {})
            rendue = figure_histogramme(
                nom,
                travail.lois.get(nom),
                biais=echantillons.get(COMPOSANTES[0]),
                fe=echantillons.get(COMPOSANTES[1]),
                valeurs=echantillons.get("valeurs"),
                nominal=travail.nominaux.get(nom),
                convention_=travail.convention,
                chemin=travail.dossier / nom,
                formats=travail.formats,
                etiquette=travail.etiquette,
                sigmas=travail.sigmas,
                profil=travail.profil,
            )
            plt.close(rendue.figure)
            inventaire.extend(
                {**commun, "figure": nom, "fichier": fichier} for fichier in rendue.fichiers
            )

    if travail.matrice:
        pages = figure_histogramme_matrice(
            travail.lois,
            obtenues=travail.obtenues,
            nominaux=travail.nominaux,
            coefficients=list(travail.coefficients),
            convention_=travail.convention,
            chemin=travail.dossier / NOM_MATRICE,
            formats=travail.formats,
            etiquette=travail.etiquette,
            sigmas=travail.sigmas,
            max_par_figure=travail.max_par_figure,
            profil=travail.profil,
        )
        for page in pages:
            plt.close(page.figure)
            inventaire.extend(
                {**commun, "figure": NOM_MATRICE, "fichier": fichier} for fichier in page.fichiers
            )

    return inventaire


def figures_histogramme_par_pdv(
    df: pd.DataFrame,
    *,
    points_de_vol: Mapping[str, Any],
    racine: Any,
    lois: JeuDeLois | None = None,
    reference: pd.DataFrame | None = None,
    coefficients: Sequence[str] | None = None,
    nominaux: Mapping[str, Any] | None = None,
    colonne_tirage: str = COLONNE_NUMERO,
    formats: Sequence[str] = FORMATS_DEFAUT,
    par_coefficient: bool = True,
    matrice: bool = True,
    convention_: ConventionArg = None,
    sigmas: Sequence[int] | None = SIGMAS_DEFAUT,
    max_par_figure: int = MAX_COEFFICIENTS_PAR_FIGURE,
    nettoyer: bool = False,
    n_jobs: int = 1,
    profil: str = PROFIL_DEFAUT,
) -> pd.DataFrame:
    """Écrit un histogramme par (point de vol × coefficient), sur **tous** les tirages.

    Le pendant de :func:`cfd_dispersion.figures.par_pdv.figures_tirage_par_pdv` :
    même dictionnaire de points de vol, même arborescence, même inventaire —
    mais une figure par coefficient et par point de vol, et non par tirage.

    Parameters
    ----------
    df:
        La sortie du modèle, dans l'une des deux formes admises.
    points_de_vol:
        ``{colonne: valeurs}``, la forme du ``flight_point_dict``.
    racine:
        Le dossier de sortie.
    lois, reference, nominaux, colonne_tirage, nettoyer, n_jobs:
        Comme pour le parcours des tirages.
    coefficients:
        Les coefficients à tracer. Par défaut ceux du jeu de lois ; un nom
        absent des lois est **admis** s'il est une colonne du tableau — son
        histogramme reste traçable, ce que la figure de tirage ne pouvait pas
        faire.

    Returns
    -------
    pandas.DataFrame
        Une ligne par fichier écrit : le point de vol, le nombre de tirages, la
        figure et le fichier.

    Raises
    ------
    ValueError
        Si un point de vol porte plusieurs lignes pour un même tirage — un
        appel croisé, où l'histogramme mélangerait le balayage et la
        dispersion — ou si un coefficient demandé n'est ni dans les lois ni
        dans le tableau.
    """
    if not points_de_vol:
        raise ValueError("points_de_vol est vide : aucun point de vol à parcourir")

    tableau, jeu = _preparer(df, lois, colonne_tirage)
    noms = list(coefficients) if coefficients is not None else list(jeu)
    inconnus = [nom for nom in noms if nom not in jeu and nom not in tableau.columns]
    if inconnus:
        raise ValueError(
            f"coefficient(s) {sorted(inconnus)} : ni loi ni colonne dans le tableau — "
            "rien à tracer d'eux"
        )

    specs = _specifications(points_de_vol, tableau)
    variables = [cle for cle, spec in specs.items() if len(spec["values"]) > 1]

    base = Path(racine)
    if nettoyer:
        from .par_pdv import _nettoyer

        _nettoyer(base)

    relation = convention(convention_)
    travaux: list[_TravailHistogramme] = []

    for combinaison in _produit(specs):
        point = dict(zip(specs, combinaison))
        lignes = _selectionner(tableau, point)
        if lignes.empty:
            continue

        _verifier_une_ligne_par_tirage(lignes, colonne_tirage, point, specs)

        travaux.append(
            _TravailHistogramme(
                point=point,
                lois=jeu,
                coefficients=tuple(noms),
                obtenues=_echantillons(lignes, noms),
                nominaux=_nominaux_du_point(
                    lignes,
                    noms,
                    nominaux,
                    _selectionner(reference, point) if reference is not None else None,
                    point=point,
                ),
                effectif=len(lignes),
                dossier=chemin_du_point_de_vol(base, point, specs, variables),
                etiquette=etiquette_du_point_de_vol(point, specs),
                formats=tuple(formats),
                par_coefficient=par_coefficient,
                matrice=matrice,
                convention=relation,
                sigmas=None if sigmas is None else tuple(sigmas),
                max_par_figure=max_par_figure,
                profil=profil,
            )
        )

    if not travaux:
        raise ValueError(
            "aucun point de vol demandé n'a de ligne dans le tableau ; "
            f"colonnes lues : {list(specs)} — vérifier les valeurs demandées"
        )

    inventaire = _repartir(travaux, n_jobs, _executer_histogramme)
    colonnes = [*specs, "tirages", "figure", "fichier"]
    return pd.DataFrame(inventaire, columns=colonnes if inventaire else None)


def _produit(specs: Mapping[str, Mapping[str, Any]]) -> Any:
    """Le produit cartésien des valeurs de points de vol."""
    from itertools import product

    return product(*(specs[cle]["values"] for cle in specs))


def _echantillons(lignes: pd.DataFrame, coefficients: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Ce qui a été obtenu, coefficient par coefficient.

    Trois tableaux par coefficient — le biais, le facteur d'échelle et le
    coefficient lui-même — et les clés simplement absentes quand la colonne
    n'existe pas. C'est ce qui permet aux figures de traiter séparément « pas
    de loi » et « pas de sortie ».
    """
    obtenues: dict[str, dict[str, Any]] = {}
    for nom in coefficients:
        echantillons: dict[str, Any] = {}
        for composante in COMPOSANTES:
            colonne = f"{nom}_{composante}"
            if colonne in lignes.columns:
                echantillons[composante] = lignes[colonne].to_numpy(dtype=float)
        if nom in lignes.columns:
            echantillons["valeurs"] = lignes[nom].to_numpy(dtype=float)
        obtenues[nom] = echantillons
    return obtenues


def _verifier_une_ligne_par_tirage(
    lignes: pd.DataFrame,
    colonne: str,
    point: Mapping[str, Any],
    specs: Mapping[str, Mapping[str, Any]],
) -> None:
    """Refuse un point de vol qui porte plusieurs lignes par tirage.

    C'est le piège du croisement, sous une autre forme : sur sept incidences,
    chaque tirage donne sept lignes, et l'histogramme du coefficient
    mélangerait alors la dispersion et le balayage. Un histogramme faux se lit
    comme un vrai — d'où le refus.
    """
    if colonne not in lignes.columns:
        return
    par_tirage = lignes.groupby(colonne).size()
    if par_tirage.max() <= 1:
        return

    # Les colonnes qui distinguent les lignes D'UN MÊME tirage : ce sont
    # celles-là qui manquent au point de vol, et elles seules. Les coefficients
    # varient d'un tirage à l'autre, pas à l'intérieur d'un tirage.
    fautif = par_tirage.idxmax()
    doublons = lignes[lignes[colonne] == fautif]
    exclues = {*specs, colonne}
    candidates = sorted(
        str(nom) for nom in doublons.columns if nom not in exclues and _varie(doublons[nom])
    )
    raise ValueError(
        f"le point de vol {dict(point)} porte jusqu'à {int(par_tirage.max())} lignes "
        f"par tirage : l'histogramme mélangerait la dispersion et le balayage. "
        f"Ajouter la colonne de balayage aux points de vol (candidates : {candidates})"
    )


def _varie(colonne: pd.Series) -> bool:
    """Vrai si la colonne prend plus d'une valeur — sans jamais lever."""
    try:
        return bool(colonne.nunique() > 1)
    except TypeError:  # pragma: no cover - colonne non comparable
        return False
