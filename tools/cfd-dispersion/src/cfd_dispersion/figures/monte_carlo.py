"""Comparer la loi prescrite à celle que le modèle a réellement tirée.

C'est le cas d'usage 2.1. Le modèle a été appelé mille fois par point de vol ;
on regroupe sa sortie et, pour chaque point de vol et chaque coefficient, on
superpose la loi demandée et celle qu'on a obtenue — plus un verdict, pour ne
pas s'en remettre à l'œil sur mille histogrammes.

Trois panneaux, comme au tirage : le biais, le facteur d'échelle, et la
reconstruction. La différence est qu'à chaque loi théorique se superpose
maintenant la densité empirique du modèle — le troisième panneau confronte donc
la loi **prescrite du coefficient dispersé**, biais et FE combinés (voir
:mod:`cfd_dispersion.core.combinaison`), à l'histogramme réellement obtenu.
C'est là que se voit ce qu'une erreur sur une composante fait à la grandeur
livrée : les deux courbes ne se superposent pas.

Histogramme ou diagramme quantile-quantile
------------------------------------------
``qq=True`` remplace la densité empirique par un diagramme quantile-quantile.
Un histogramme se lit bien au centre et mal dans les queues, alors que c'est
précisément dans les queues qu'une loi tronquée dérape — le défaut que le
contrôle de support attrape et que Kolmogorov–Smirnov laisse parfois passer.
Le QQ montre l'écart des queues à l'échelle où il se produit.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from ..core.combinaison import loi_combinee
from ..core.convention import ConventionArg, convention
from ..core.loi import LoiDispersion
from ..core.lois import COMPOSANTES, JeuDeLois, LoiCoefficient
from ..core.validation import Verdict, valider
from ..report.theme import COULEUR_VERDICT
from ._base import (
    PROFIL_DEFAUT,
    boite_texte,
    legende,
    nouvelle_figure,
    style,
    surtitre,
    titre,
    tracer_bande,
    tracer_ligne,
)
from .densite import tracer_densite_realisee
from .tirage import axe_pourcentage, tracer_sigmas

__all__ = ["figure_comparaison", "figures_par_pdv"]

_N_GRILLE = 400
_N_BINS = 40


def figure_comparaison(
    echantillons: Mapping[str, Any],
    loi: LoiCoefficient,
    *,
    coefficient: str | None = None,
    verdicts: Mapping[str, Verdict] | None = None,
    nominal: Any = None,
    x: Any = None,
    convention_: ConventionArg = None,
    pdv_label: str = "",
    qq: bool = False,
    axes: Sequence[Axes] | None = None,
    profil: str = PROFIL_DEFAUT,
    figsize: tuple[float, float] | None = None,
) -> tuple[Figure, Any]:
    """Superpose loi prescrite et loi réalisée, pour un coefficient.

    Parameters
    ----------
    echantillons:
        ``{"Biais": tableau, "FE": tableau}`` — la sortie du modèle pour ce
        coefficient à ce point de vol.
    loi:
        Les deux lois prescrites.
    coefficient:
        Nom du coefficient. Par défaut celui que porte *loi*.
    verdicts:
        ``{"Biais": Verdict, "FE": Verdict}``. Calculés si absents.
    nominal:
        Valeur nominale du coefficient, pour le panneau de reconstruction.
        Sans elle, ce panneau montre la distribution des deux composantes
        recombinées sur un nominal unitaire.
    x:
        Abscisse, si *nominal* est un balayage.
    pdv_label:
        Le point de vol, pour le titre général.
    qq:
        Remplacer la densité empirique par un diagramme quantile-quantile.
    axes:
        Trois axes existants où dessiner.

    Returns
    -------
    (Figure, axes)
    """
    nom = coefficient if coefficient is not None else loi.nom
    manquantes = [c for c in COMPOSANTES if c not in echantillons]
    if manquantes:
        raise ValueError(
            f"échantillon(s) manquant(s) pour {nom!r} : {manquantes} ; attendu {list(COMPOSANTES)}"
        )

    tableaux = {
        composante: np.asarray(echantillons[composante], dtype=float).ravel()
        for composante in COMPOSANTES
    }
    if verdicts is None:
        verdicts = {
            composante: valider(
                tableaux[composante],
                loi.composante(composante),
                coefficient=nom,
                composante=composante,
            )
            for composante in COMPOSANTES
        }

    relation = convention(convention_)

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
            couleur = "C0" if composante == "Biais" else "C1"
            if qq:
                _panneau_qq(panneau, tableaux[composante], loi.composante(composante), couleur)
            else:
                _panneau_densite(panneau, tableaux[composante], loi.composante(composante), couleur)
            panneau.set_xlabel(composante)
            titre(panneau, f"{nom} — {composante}")
            _boite_verdict(panneau, verdicts[composante])

        _panneau_reconstruction(
            trois[2],
            nom,
            loi,
            biais=tableaux["Biais"],
            fe=tableaux["FE"],
            nominal=nominal,
            x=x,
            relation=relation,
        )

        if axes is None:
            entete = f"{nom} — loi prescrite contre loi réalisée"
            if pdv_label:
                entete = f"{entete} — {pdv_label}"
            surtitre(figure, entete, fontsize=10)

    return figure, np.array(trois)


def _panneau_densite(ax: Axes, echantillon: np.ndarray, loi: LoiDispersion, couleur: Any) -> None:
    """Loi théorique, histogramme empirique, et lissage à noyau.

    Le dessin est celui de :func:`cfd_dispersion.figures.densite.tracer_densite_realisee`,
    partagé avec l'histogramme par point de vol : deux figures, un seul panneau
    de densité, qui ne peuvent donc pas diverger.
    """
    tracer_densite_realisee(ax, echantillon, loi=loi, couleur=couleur)


def _panneau_qq(ax: Axes, echantillon: np.ndarray, loi: LoiDispersion, couleur: Any) -> None:
    """Diagramme quantile-quantile : l'accord des queues, à leur échelle."""
    if echantillon.size == 0:
        return

    tries = np.sort(echantillon)
    # Positions de Hazen : (i - 0.5)/n évite les probabilités 0 et 1, dont les
    # quantiles seraient infinis pour une loi non bornée.
    probas = (np.arange(1, tries.size + 1) - 0.5) / tries.size
    theoriques = loi.quantile(probas)

    ax.scatter(theoriques, tries, s=6, color=couleur, alpha=0.5, label="quantiles")
    bas = float(min(theoriques.min(), tries.min()))
    haut = float(max(theoriques.max(), tries.max()))
    ax.plot([bas, haut], [bas, haut], color="0.4", ls="--", lw=1.0, label="accord parfait")
    ax.set_ylabel("quantiles réalisés")
    ax.set_xlabel("quantiles prescrits")
    # En bas à droite, et non « best » : un nuage quantile-quantile suit la
    # diagonale, donc les deux coins hors-diagonale sont libres — et celui du
    # haut à gauche est pris par la boîte de verdict, que Matplotlib ne voit
    # pas puisqu'elle est posée après.
    legende(ax, loc="lower right", fontsize=7)


def _boite_verdict(ax: Axes, verdict: Verdict) -> None:
    """La boîte qui dit si le tirage suit sa loi, et sinon pourquoi."""
    etat = "VALIDÉ" if verdict.valide else f"REJETÉ — {verdict.motif}"
    lignes = [etat, f"n = {verdict.n}"]
    if np.isfinite(verdict.ks_p):
        lignes.append(f"KS D={verdict.ks_D:.3f} p={verdict.ks_p:.3f}")
    lignes.append(f"M  {verdict.M_empirique:.4g} / {verdict.M_theorique:.4g}")
    lignes.append(f"ET {verdict.ET_empirique:.4g} / {verdict.ET_theorique:.4g}")
    if verdict.hors_support:
        lignes.append(f"hors support : {verdict.hors_support}")

    boite_texte(
        ax,
        "\n".join(lignes),
        loc="upper left",
        fontsize=6.5,
        color=COULEUR_VERDICT[verdict.valide],
    )


def _panneau_reconstruction(
    ax: Axes,
    coefficient: str,
    loi: LoiCoefficient,
    *,
    biais: np.ndarray,
    fe: np.ndarray,
    nominal: Any,
    x: Any,
    relation: Any,
) -> None:
    """Ce que la dispersion fait au coefficient lui-même."""
    valeur = 1.0 if nominal is None else nominal
    nominal_ = np.atleast_1d(np.asarray(valeur, dtype=float))

    if nominal_.size == 1:
        disperse = relation(float(nominal_[0]), biais, fe)
        if float(np.ptp(disperse)) > 0.0:
            ax.hist(
                disperse,
                bins=_N_BINS,
                density=True,
                color="C2",
                alpha=0.35,
                label=f"dispersé (n={disperse.size})",
            )
        ax.axvline(float(np.mean(disperse)), color="C3", lw=1.2, label="moyenne dispersée")
        # Le nominal passe au-dessus : quand la dispersion est centrée les deux
        # traits coïncident, et c'est précisément la confirmation qu'on vient
        # chercher — encore faut-il qu'elle reste visible.
        ax.axvline(float(nominal_[0]), color="0.25", ls="--", lw=1.4, label="nominal", zorder=6)
        ax.set_xlabel(coefficient)
        ax.set_ylabel("densité")

        # La loi que le coefficient dispersé devrait suivre, superposée à celle
        # qu'il suit. L'histogramme seul ne dit pas s'il est trop large : les
        # deux panneaux précédents jugent chaque composante, celui-ci juge leur
        # combinaison, qui est la grandeur livrée.
        combinee = loi_combinee(loi, float(nominal_[0]), convention_=relation)
        if not combinee.est_degeneree:
            grille = np.linspace(*combinee.plage_utile(), _N_GRILLE)
            tracer_ligne(
                ax,
                grille,
                combinee.pdf(grille),
                color="C2",
                lw=1.6,
                marker="",
                label="prescrite (combinée)",
            )
            # Les lignes ±kσ lisent les limites courantes : il faut donc que
            # l'autoscale ait tenu compte de tout ce qui précède.
            ax.autoscale_view()
            tracer_sigmas(ax, combinee.M_theorique, combinee.ET_theorique)
        axe_pourcentage(ax, combinee.nominal)
    else:
        abscisse = (
            np.arange(nominal_.size, dtype=float) if x is None else np.asarray(x, dtype=float)
        )
        nuage = relation(nominal_[None, :], biais[:, None], fe[:, None])
        moyenne = nuage.mean(axis=0)
        tracer_bande(
            ax,
            abscisse,
            moyenne,
            y_bas=np.percentile(nuage, 2.5, axis=0),
            y_haut=np.percentile(nuage, 97.5, axis=0),
            alpha=0.20,
            couleur_bande="C2",
            label_bande="95 %",
            color="C2",
            marker="",
            label="moyenne dispersée",
        )
        tracer_ligne(ax, abscisse, nominal_, color="0.35", ls="--", marker="", label="nominal")
        ax.set_ylabel(coefficient)

    legende(ax, loc="upper right", fontsize=7)
    titre(ax, f"{coefficient} — reconstruction")
    boite_texte(ax, relation.formule, loc="lower left", fontsize=7)


def figures_par_pdv(
    df: pd.DataFrame,
    lois: JeuDeLois,
    *,
    par: Sequence[str] = (),
    unique_par: Sequence[str] = (),
    coefficients: Sequence[str] | None = None,
    nominaux: Mapping[str, Any] | None = None,
    colonnes: Mapping[tuple[str, str], str] | None = None,
    convention_: ConventionArg = None,
    qq: bool = False,
    profil: str = PROFIL_DEFAUT,
    seulement: Sequence[Mapping[str, Any]] | None = None,
) -> Iterator[tuple[dict[str, Any], str, Figure]]:
    """Produit une figure par (point de vol × coefficient).

    C'est le pilote du cas d'usage 2.1 : il regroupe la sortie du modèle et
    rend un générateur, pour qu'un millier de figures ne soit jamais toutes en
    mémoire à la fois.

    Parameters
    ----------
    df:
        La sortie du modèle.
    lois:
        Les lois prescrites.
    par:
        Colonnes définissant un point de vol.
    unique_par:
        Colonnes identifiant un tirage — ``("tirage",)`` sur un modèle appelé
        en croisé, où le même tirage revient une fois par point du balayage.
        Les doublons sont retirés dans chaque groupe : sans cela l'histogramme
        est juste, mais l'effectif affiché et le verdict ne le sont pas.
    coefficients:
        Les coefficients à traiter. Par défaut, tous.
    nominaux:
        ``{coefficient: valeur nominale}`` pour le panneau de reconstruction.
    seulement:
        Ne traiter que ces points de vol, sous la forme rendue par
        :func:`cfd_dispersion.figures.synthese.pdv_rejetes` — c'est ainsi
        qu'on ne trace que les cas rejetés.

    Yields
    ------
    (clés du point de vol, coefficient, figure)
    """
    noms = list(coefficients) if coefficients is not None else list(lois)
    manquants = sorted(set(noms) - set(lois))
    if manquants:
        raise ValueError(f"coefficient(s) {manquants} absent(s) du jeu de lois")

    par = tuple(par)
    correspondance = {
        (coeff, composante): f"{coeff}_{composante}" for coeff in noms for composante in COMPOSANTES
    }
    if colonnes:
        correspondance.update(colonnes)

    absentes = sorted({c for c in correspondance.values() if c not in df.columns})
    if absentes:
        raise ValueError(f"colonne(s) absente(s) du tableau : {absentes}")

    unique_par = tuple(unique_par)
    inconnues = [cle for cle in unique_par if cle not in df.columns]
    if inconnues:
        raise ValueError(
            f"colonne(s) d'identifiant de tirage absente(s) : {inconnues} ; "
            f"le tableau porte {sorted(df.columns)}"
        )

    retenus = None if seulement is None else [dict(cle) for cle in seulement]

    for cles, groupe in _grouper(df, par):
        if retenus is not None and cles not in retenus:
            continue
        if unique_par:
            groupe = groupe.drop_duplicates(subset=list(unique_par))
        etiquette = ", ".join(
            f"{cle}={valeur:g}" if isinstance(valeur, (int, float)) else f"{cle}={valeur}"
            for cle, valeur in cles.items()
        )
        for nom in noms:
            echantillons = {
                composante: groupe[correspondance[(nom, composante)]].to_numpy()
                for composante in COMPOSANTES
            }
            figure, _ = figure_comparaison(
                echantillons,
                lois[nom],
                coefficient=nom,
                nominal=None if nominaux is None else nominaux.get(nom),
                convention_=convention_,
                pdv_label=etiquette,
                qq=qq,
                profil=profil,
            )
            yield cles, nom, figure


def _grouper(df: pd.DataFrame, par: tuple[str, ...]) -> list[tuple[dict[str, Any], pd.DataFrame]]:
    """Groupe *df* par *par*, en rendant les clés sous forme de dictionnaire."""
    if not par:
        return [({}, df)]

    absentes = [cle for cle in par if cle not in df.columns]
    if absentes:
        raise ValueError(f"colonne(s) de groupement absente(s) : {absentes}")

    groupes: list[tuple[dict[str, Any], pd.DataFrame]] = []
    for valeurs, groupe in df.groupby(list(par), sort=False):
        if not isinstance(valeurs, tuple):
            valeurs = (valeurs,)
        groupes.append((dict(zip(par, valeurs)), groupe))
    return groupes
