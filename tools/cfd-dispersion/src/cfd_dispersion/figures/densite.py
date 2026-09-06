"""Ce qu'on a **obtenu**, superposé à ce qu'on avait **prescrit**.

Un panneau, une routine : l'histogramme d'un échantillon, son lissage à noyau,
et — quand on la connaît — la densité de la loi qui aurait dû le produire.

C'est le dessin de base de deux figures très différentes : la comparaison
Monte-Carlo (:mod:`cfd_dispersion.figures.monte_carlo`), qui juge un tirage
contre sa loi, et l'histogramme par point de vol
(:mod:`cfd_dispersion.figures.histogramme`), qui montre simplement ce que le
modèle a rendu. Elles le partagent plutôt que d'en tenir chacune une copie qui
dériverait de l'autre.

La loi est **facultative**, et c'est ce qui permet de tracer un coefficient dont
on n'a pas les lois : reste l'histogramme, qui est déjà la moitié de la
réponse.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import openturns as ot
from matplotlib.axes import Axes

from ..core.loi import LoiDispersion
from ._base import legende, tracer_ligne
from .tirage import SIGMAS_DEFAUT, tracer_loi

__all__ = ["N_CLASSES", "tracer_densite_realisee"]

#: Nombre de classes de l'histogramme.
N_CLASSES: int = 40

#: Nombre de points de la courbe lissée.
_N_GRILLE: int = 400


def tracer_densite_realisee(
    ax: Axes,
    echantillon: Any,
    *,
    loi: LoiDispersion | None = None,
    couleur: Any = "C0",
    couleur_realise: Any = "C3",
    label_prescrite: str = "prescrite",
    sigmas: Any = SIGMAS_DEFAUT,
    classes: int = N_CLASSES,
) -> None:
    """Trace un échantillon : histogramme, lissage à noyau, et loi prescrite.

    Parameters
    ----------
    ax:
        Les axes où dessiner.
    echantillon:
        Les valeurs obtenues, forme ``(n,)``.
    loi:
        La loi qui aurait dû les produire. **Facultative** : sans elle, seul
        l'obtenu est tracé — c'est le cas d'un coefficient que le modèle rend
        sans qu'aucune loi ne le décrive.
    couleur:
        Couleur de la loi prescrite.
    couleur_realise:
        Couleur de l'histogramme et de son lissage.
    sigmas:
        Les multiples de σ marqués sur la loi prescrite ; None pour aucun.
    classes:
        Nombre de classes de l'histogramme.
    """
    valeurs = np.asarray(echantillon, dtype=float).ravel()

    if loi is not None:
        tracer_loi(ax, loi, couleur=couleur, label=label_prescrite, sigmas=sigmas)

    if valeurs.size == 0:
        return

    if float(np.ptp(valeurs)) == 0.0:
        # Un échantillon constant n'a pas de densité : ni histogramme ni noyau
        # n'ont de sens, et `KernelSmoothing` échouerait sur une largeur nulle.
        ax.axvline(
            float(valeurs[0]),
            color=couleur_realise,
            lw=1.4,
            ls="--",
            label="réalisée (constante)",
        )
        legende(ax, loc="upper right", fontsize=7)
        return

    ax.hist(
        valeurs,
        bins=classes,
        density=True,
        color=couleur_realise,
        alpha=0.30,
        label=f"réalisée (n={valeurs.size})",
    )

    noyau = ot.KernelSmoothing().build(ot.Sample(valeurs.reshape(-1, 1)))
    grille = np.linspace(valeurs.min(), valeurs.max(), _N_GRILLE)
    densite = np.array(noyau.computePDF([[float(v)] for v in grille])).ravel()
    tracer_ligne(
        ax, grille, densite, color=couleur_realise, lw=1.2, marker="", label="lissage à noyau"
    )

    if loi is None:
        # Sans loi prescrite, personne n'a borné l'axe : l'histogramme le fait,
        # mais la courbe lissée peut déborder — on laisse Matplotlib cadrer sur
        # l'ensemble, en gardant de la place au-dessus pour les boîtes.
        ax.set_ylim(0.0, float(np.max(densite)) / 0.62)
        ax.set_ylabel("densité")

    legende(ax, loc="upper right", fontsize=7)
