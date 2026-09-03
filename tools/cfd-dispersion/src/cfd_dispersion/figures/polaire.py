"""Superposer une dispersion sur une polaire déjà tracée.

C'est le cas d'usage 2.3, et la fonction que l'on greffe sur les figures que
``cfd_plot.batch_plot`` produit déjà. Sur des axes portant une ou plusieurs
courbes, :func:`superposer_dispersion` ajoute :

- la **bande théorique** issue de la loi du coefficient ;
- les **courbes par tirage**, une par tirage du modèle ;
- un **remplissage min/max** (ou en percentile, ou en σ) ;
- les **lignes ±1σ, ±2σ, ±3σ**, étiquetées *sur* la courbe ;
- une **boîte de paramètres** disant quelle loi a produit tout cela.

Se rattacher à une courbe existante
-----------------------------------
``serie="KW"`` va chercher la couleur de la courbe intitulée ainsi sur les
axes : le remplissage la reprend en transparence et la moyenne dispersée en
plus sombre. La dispersion se lit alors comme appartenant à cette série-là,
sans légende supplémentaire, ce qui compte dès qu'il y en a trois sur la même
figure. À défaut, ``couleur=`` trace un faisceau autonome.

L'ordre de tracé n'est pas décoratif
------------------------------------
Les étiquettes ±kσ sont posées **en dernier**, après tout ce qui peut déplacer
les limites des axes : leur inclinaison est calculée en coordonnées
d'affichage, donc elle n'est juste que pour les axes tels qu'ils seront
finalement. Voir :func:`cfd_dispersion.figures._base.etiqueter_ligne`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from matplotlib.axes import Axes

from ..core.bande import BandeDispersion, bande_depuis_loi
from ..core.convention import ConventionArg, convention
from ..core.lois import LoiCoefficient
from ._base import (
    assombrir,
    boite_texte,
    couleur_de_serie,
    etiqueter_ligne,
    legende,
    remplir_entre,
    tracer_ligne,
)

__all__ = ["courbes_par_tirage", "superposer_dispersion"]

#: Assombrissement appliqué à la courbe dérivée par rapport à sa série.
_ASSOMBRISSEMENT = 0.25

#: Positions par défaut des étiquettes ±kσ le long de la courbe.
#:
#: Étalées sur la seconde moitié plutôt que groupées près du bord : les
#: courbes ±kσ se resserrent visuellement là où la bande est étroite, et
#: trois étiquettes posées au même endroit se chevauchent quel que soit le
#: décalage vertical. En les répartissant le long de la courbe, chacune
#: dispose de sa propre portion.
_FRACTIONS_SIGMA: tuple[float, ...] = (0.55, 0.72, 0.89)

#: Décalage de la branche basse par rapport à la branche haute.
_ECART_BRANCHES = 0.07


def courbes_par_tirage(
    df: pd.DataFrame,
    *,
    x: str,
    y: str,
    par: Sequence[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Regroupe une sortie de modèle en une courbe par tirage.

    Mille appels du modèle donnent un tableau à plat : une ligne par (tirage,
    point du balayage). Cette fonction le remet en forme — une ligne par
    tirage, une colonne par abscisse — qui est ce que
    :func:`superposer_dispersion` attend.

    Parameters
    ----------
    df:
        La sortie du modèle.
    x, y:
        Les colonnes d'abscisse et d'ordonnée.
    par:
        Les colonnes identifiant un tirage — typiquement les colonnes du
        tirage (``"Cm_alpha_Biais"``, …), ou un numéro de tirage.

    Returns
    -------
    (x commun, courbes)
        L'abscisse partagée, forme ``(npts,)``, et les courbes, forme
        ``(n_tirages, npts)``.

    Raises
    ------
    ValueError
        Si une colonne manque, ou si les tirages ne partagent pas la même
        abscisse — auquel cas les empiler donnerait un tableau dont les
        colonnes ne voudraient rien dire.
    """
    par = list(par)
    manquantes = [c for c in [x, y, *par] if c not in df.columns]
    if manquantes:
        raise ValueError(
            f"colonne(s) absente(s) du tableau : {manquantes} ; il porte {sorted(df.columns)}"
        )
    if not par:
        raise ValueError("par= doit nommer au moins une colonne identifiant le tirage")

    reference: np.ndarray | None = None
    courbes: list[np.ndarray] = []
    for _, groupe in df.groupby(par, sort=False):
        ordonne = groupe.sort_values(x)
        abscisse = ordonne[x].to_numpy(dtype=float)
        if reference is None:
            reference = abscisse
        elif abscisse.shape != reference.shape or not np.allclose(abscisse, reference):
            raise ValueError(
                "les tirages ne partagent pas la même abscisse ; les empiler donnerait "
                "un tableau dont les colonnes ne correspondraient pas au même point du "
                "balayage. Interpoler sur une abscisse commune au préalable."
            )
        courbes.append(ordonne[y].to_numpy(dtype=float))

    if reference is None:
        raise ValueError("tableau vide : aucun tirage à regrouper")
    return reference, np.vstack(courbes)


def superposer_dispersion(
    ax: Axes,
    x: Any,
    nominal: Any,
    *,
    loi: LoiCoefficient | None = None,
    tirages: Any = None,
    convention_: ConventionArg = None,
    serie: str | None = None,
    couleur: Any = None,
    remplissage: str | None = "minmax",
    sigmas: Sequence[float] = (1, 2, 3),
    etiquettes_sigma: bool = True,
    fractions_sigma: Sequence[float] = _FRACTIONS_SIGMA,
    boite_parametres: bool = True,
    position_boite: str = "lower right",
    max_tirages: int | None = 200,
    alpha_tirages: float = 0.06,
    montrer_moyenne: bool = True,
    label: str | None = None,
    n: int = 20_000,
    graine: int | None = None,
    methode: str = "mc",
    correle: bool = True,
    couverture: float | None = None,
    k: float | None = None,
) -> dict[str, Any]:
    """Ajoute la dispersion d'un coefficient sur des axes existants.

    Parameters
    ----------
    ax:
        Les axes, portant déjà la ou les courbes nominales.
    x, nominal:
        Le balayage et la courbe non dispersée.
    loi:
        La loi du coefficient. Donne la bande **théorique**.
    tirages:
        Les courbes réellement obtenues, forme ``(n_tirages, npts)`` — par
        exemple la sortie de :func:`courbes_par_tirage`. Peut être donnée avec
        *loi* : voir les deux se superposer est précisément l'intérêt.
    serie:
        Le libellé d'une courbe déjà tracée dont reprendre la couleur.
    couleur:
        La couleur, si aucune série n'est nommée.
    remplissage:
        ``"minmax"`` (défaut), ``"percentile"``, ``"sigma"``, ou None.
    sigmas:
        Les multiples de σ à tracer en lignes. Vide pour aucune.
    etiquettes_sigma:
        Étiqueter chaque ligne ±kσ sur la courbe elle-même.
    fractions_sigma:
        Où poser ces étiquettes le long de la courbe, une par σ.
    boite_parametres:
        Afficher la loi employée, la convention et l'effectif.
    max_tirages:
        Plafond de courbes individuelles dessinées. Au-delà, elles sont
        échantillonnées : mille courbes opaques ne montrent rien de plus que
        deux cents, et coûtent un fichier vectoriel dix fois plus lourd.
    montrer_moyenne:
        Tracer la moyenne dispersée, dans la teinte assombrie.
    n, graine, methode, correle, couverture, k:
        Passés à :func:`cfd_dispersion.core.bande.bande_depuis_loi`.

    Returns
    -------
    dict
        Les artistes créés : ``"bande"``, ``"moyenne"``, ``"tirages"``,
        ``"sigmas"``, ``"etiquettes"``, ``"boite"``, plus ``"couleur"`` et
        ``"objet_bande"`` (la :class:`BandeDispersion` construite, s'il y en a
        une).

    Raises
    ------
    ValueError
        Si ni *loi* ni *tirages* n'est fourni, si la série nommée n'existe pas,
        ou si les formes ne concordent pas.
    """
    if loi is None and tirages is None:
        raise ValueError("passer au moins loi= (bande théorique) ou tirages= (courbes obtenues)")

    x = np.asarray(x, dtype=float)
    nominal = np.asarray(nominal, dtype=float)
    if x.ndim != 1:
        raise ValueError(f"x doit être 1-D, reçu la forme {x.shape}")
    if nominal.shape != x.shape:
        raise ValueError(
            f"nominal porte {nominal.shape} valeurs pour {x.shape} abscisses ; "
            "les deux doivent correspondre"
        )

    teinte = _teinte(ax, serie=serie, couleur=couleur)
    teinte_sombre = assombrir(teinte, _ASSOMBRISSEMENT)
    prefixe = f"{label} " if label else ""

    artistes: dict[str, Any] = {
        "bande": None,
        "moyenne": None,
        "tirages": [],
        "sigmas": [],
        "etiquettes": [],
        "boite": None,
        "couleur": teinte,
        "objet_bande": None,
    }

    # --- le nuage : théorique, obtenu, ou les deux ---------------------
    bande: BandeDispersion | None = None
    if loi is not None:
        bande = bande_depuis_loi(
            x,
            nominal,
            loi=loi,
            convention_=convention_,
            n=n,
            intervalle="minmax" if remplissage is None else remplissage,
            couverture=couverture,
            k=k,
            correle=correle,
            graine=graine,
            methode=methode,
        )
        artistes["objet_bande"] = bande

    nuage = None if tirages is None else np.atleast_2d(np.asarray(tirages, dtype=float))
    if nuage is not None and nuage.shape[1] != x.size:
        raise ValueError(
            f"tirages a {nuage.shape[1]} colonnes pour {x.size} abscisses ; "
            "les deux doivent correspondre"
        )

    # --- 1. les courbes par tirage, tout au fond -----------------------
    if nuage is not None:
        artistes["tirages"] = _tracer_tirages(ax, x, nuage, teinte, max_tirages, alpha_tirages)

    # --- 2. le remplissage ---------------------------------------------
    reference = bande if bande is not None else _bande_depuis_nuage(x, nominal, nuage, remplissage)
    if remplissage is not None and reference is not None:
        artistes["bande"] = remplir_entre(
            ax,
            x,
            reference.bas,
            reference.haut,
            couleur=teinte,
            alpha=0.18,
            label=f"{prefixe}{reference.label}",
        )

    # --- 3. la moyenne dispersée, plus sombre que sa série -------------
    if montrer_moyenne and reference is not None:
        artistes["moyenne"] = tracer_ligne(
            ax,
            x,
            reference.moyenne,
            color=teinte_sombre,
            lw=1.4,
            marker="",
            label=f"{prefixe}moyenne dispersée",
            zorder=4,
        )

    # --- 4. les lignes ±kσ ---------------------------------------------
    if reference is not None and len(sigmas):
        artistes["sigmas"] = _tracer_sigmas(ax, x, reference, sigmas, teinte_sombre)

    # --- 5. la boîte de paramètres --------------------------------------
    if boite_parametres:
        artistes["boite"] = boite_texte(
            ax,
            _description(loi, reference, nuage, convention_),
            loc=position_boite,
            fontsize=6.5,
        )

    legende(ax, fontsize=7)

    # --- 6. les étiquettes, en tout dernier -----------------------------
    # Elles lisent la transformation courante des axes : tout artiste posé
    # après elles qui déplacerait les limites fausserait leur inclinaison.
    if etiquettes_sigma and reference is not None and len(sigmas):
        artistes["etiquettes"] = _etiqueter_sigmas(
            ax, x, reference, sigmas, fractions_sigma, teinte_sombre
        )

    return artistes


def _teinte(ax: Axes, *, serie: str | None, couleur: Any) -> Any:
    """La couleur de base : celle d'une série existante, ou celle demandée."""
    if serie is not None and couleur is not None:
        raise ValueError("passer serie= ou couleur=, pas les deux")
    if serie is not None:
        return couleur_de_serie(ax, serie)
    if couleur is not None:
        return couleur
    return "C0"


def _tracer_tirages(
    ax: Axes,
    x: np.ndarray,
    nuage: np.ndarray,
    teinte: Any,
    max_tirages: int | None,
    alpha: float,
) -> list[Any]:
    """Les courbes individuelles, en faisceau translucide au fond."""
    total = nuage.shape[0]
    if max_tirages is not None and total > max_tirages:
        # Un pas régulier plutôt qu'un tirage au sort : le sous-ensemble est
        # alors reproductible sans dépendre d'un générateur.
        indices = np.linspace(0, total - 1, max_tirages).round().astype(int)
        choisies = nuage[np.unique(indices)]
    else:
        choisies = nuage

    lignes = []
    for i, courbe in enumerate(choisies):
        (ligne,) = ax.plot(
            x,
            courbe,
            color=teinte,
            lw=0.5,
            alpha=alpha,
            zorder=1,
            label=f"{total} tirages" if i == 0 else "_nolegend_",
        )
        lignes.append(ligne)
    return lignes


def _bande_depuis_nuage(
    x: np.ndarray, nominal: np.ndarray, nuage: np.ndarray | None, remplissage: str | None
) -> BandeDispersion | None:
    """Fabrique une bande à partir de courbes déjà obtenues, sans retirer."""
    if nuage is None:
        return None
    from ..core.bande import _construire, _resoudre_niveau

    intervalle = remplissage or "minmax"
    return _construire(
        x,
        nominal,
        nuage,
        intervalle=intervalle,
        niveau=_resoudre_niveau(intervalle, None, None),
        correle=True,
        relation=convention(None),
    )


def _tracer_sigmas(
    ax: Axes, x: np.ndarray, bande: BandeDispersion, sigmas: Sequence[float], teinte: Any
) -> list[Any]:
    """Les lignes moyenne ± kσ, en trait fin discontinu."""
    styles = ["--", "-.", ":"]
    lignes = []
    for i, k in enumerate(sigmas):
        bas, haut = bande.enveloppe_sigma(float(k))
        style_ = styles[i % len(styles)]
        for courbe in (bas, haut):
            (ligne,) = ax.plot(
                x,
                courbe,
                color=teinte,
                ls=style_,
                lw=0.8,
                alpha=0.8,
                zorder=3,
                label="_nolegend_",
            )
            lignes.append(ligne)
    return lignes


def _etiqueter_sigmas(
    ax: Axes,
    x: np.ndarray,
    bande: BandeDispersion,
    sigmas: Sequence[float],
    fractions: Sequence[float],
    teinte: Any,
) -> list[Any]:
    """Les étiquettes ±kσ, posées sur les courbes qu'elles nomment.

    Une légende obligerait à compter les courbes pour savoir laquelle est
    laquelle ; l'étiquette sur la courbe dit directement laquelle est laquelle.
    """
    etiquettes = []
    for i, k in enumerate(sigmas):
        bas, haut = bande.enveloppe_sigma(float(k))
        fraction = fractions[i % len(fractions)] if len(fractions) else 0.85
        valeur = int(k) if float(k).is_integer() else k
        # La branche basse est décalée le long de la courbe : à la même
        # abscisse, +kσ et −kσ se chevauchent dès que la bande est étroite,
        # et une bande est étroite précisément là où elle est intéressante.
        for courbe, signe, decalage in ((haut, "+", 0.0), (bas, "−", -_ECART_BRANCHES)):
            etiquettes.append(
                etiqueter_ligne(
                    ax,
                    x,
                    courbe,
                    f"{signe}{valeur}σ",
                    fraction=min(max(fraction + decalage, 0.0), 1.0),
                    couleur=teinte,
                    taille=6.5,
                    zorder=6,
                )
            )
    return etiquettes


def _description(
    loi: LoiCoefficient | None,
    bande: BandeDispersion | None,
    nuage: np.ndarray | None,
    convention_: ConventionArg,
) -> str:
    """Le contenu de la boîte de paramètres.

    Elle nomme la loi effectivement tirée, sa convention et son effectif : une
    figure ne doit jamais pouvoir cacher quelle dispersion l'a produite.
    """
    lignes: list[str] = []
    if loi is not None:
        for composante, composante_loi in loi:
            lignes.append(
                f"{composante} : {composante_loi.label}  "
                f"M={composante_loi.M:g} ET={composante_loi.ET:g}"
            )
    relation = bande.convention if bande is not None else convention(convention_)
    lignes.append(relation.formule)
    if bande is not None and loi is not None:
        lignes.append(f"n = {bande.n_tirages} · {'corrélé' if bande.correle else 'indépendant'}")
    if nuage is not None:
        lignes.append(f"{nuage.shape[0]} tirages du modèle")
    return "\n".join(lignes)
