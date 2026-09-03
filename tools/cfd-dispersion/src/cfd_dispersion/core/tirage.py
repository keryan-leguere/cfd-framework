"""Tirer les lois : un tirage, ou un lot de tirages.

C'est le premier cas d'usage du paquet. On donne une table de lois, on récupère
un biais et un facteur d'échelle par coefficient ::

    lois = charger_lois(DICT_DISP_LAWS)
    tirage = tirer(lois, graine=42)

    tirage["Cm_alpha"]["Biais"]     # -> un flottant
    tirage.appliquer({"Cm_alpha": -2.5})   # -> le coefficient dispersé

:class:`Tirage` est un ``Mapping``, donc il se passe tel quel au modèle qui
attend un ``DICT_DISP_DRAWN`` — tout en portant la convention employée, la
graine et le plan d'échantillonnage, qui finissent dans les boîtes de
paramètres des figures.

Pour appeler le modèle mille fois, :func:`tirer_lot` rend directement un
``DataFrame`` d'une ligne par tirage.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .alea import graine_temporaire
from .convention import Convention, ConventionArg, convention
from .loi import METHODES
from .lois import COMPOSANTES, JeuDeLois

__all__ = ["Tirage", "tirer", "tirer_lot"]


@dataclass(frozen=True)
class Tirage(Mapping[str, "dict[str, float]"]):
    """Un tirage : une valeur de biais et de FE par coefficient.

    S'utilise comme le dictionnaire ``{coeff: {"Biais": …, "FE": …}}`` attendu
    par un modèle, mais garde en plus de quoi se décrire lui-même.

    Attributes
    ----------
    valeurs:
        ``{coefficient: {"Biais": float, "FE": float}}``.
    convention:
        La relation de reconstruction retenue.
    graine:
        La graine posée pour ce tirage, ou None.
    methode:
        Le plan d'échantillonnage employé.
    """

    valeurs: dict[str, dict[str, float]]
    convention: Convention
    graine: int | None = None
    methode: str = "mc"
    _cle: tuple[Any, ...] = field(default=(), repr=False, compare=False)

    # -- protocole Mapping ---------------------------------------------

    def __getitem__(self, cle: str) -> dict[str, float]:
        try:
            return self.valeurs[cle]
        except KeyError:
            raise KeyError(
                f"coefficient inconnu : {cle!r} ; ce tirage porte {sorted(self.valeurs)}"
            ) from None

    def __iter__(self) -> Iterator[str]:
        return iter(self.valeurs)

    def __len__(self) -> int:
        return len(self.valeurs)

    # -- reconstruction -------------------------------------------------

    def appliquer(
        self,
        coeffs: Mapping[str, object],
        *,
        convention_: ConventionArg = None,
    ) -> dict[str, np.ndarray]:
        """Applique le tirage à des valeurs nominales.

        Parameters
        ----------
        coeffs:
            ``{coefficient: valeur nominale}``. La valeur peut être un scalaire
            ou un tableau : un balayage entier se disperse d'un coup, avec le
            même tirage en tout point — le cas corrélé, qui est le cas physique
            usuel d'une erreur de recalage.
        convention_:
            Pour appliquer une autre relation que celle du tirage. Rare, et
            explicite quand cela arrive.

        Returns
        -------
        dict
            ``{coefficient: valeurs dispersées}``, un tableau par coefficient.

        Raises
        ------
        ValueError
            Si un coefficient demandé n'a pas été tiré.
        """
        relation = self.convention if convention_ is None else convention(convention_)

        inconnus = sorted(set(coeffs) - set(self.valeurs))
        if inconnus:
            raise ValueError(
                f"coefficient(s) {inconnus} absent(s) du tirage ; il porte {sorted(self.valeurs)}"
            )

        return {
            nom: relation(valeur, self.valeurs[nom]["Biais"], self.valeurs[nom]["FE"])
            for nom, valeur in coeffs.items()
        }

    # -- description ----------------------------------------------------

    def vers_dict(self) -> dict[str, dict[str, float]]:
        """Copie simple ``{coeff: {"Biais": …, "FE": …}}``, sans métadonnées."""
        return {coeff: dict(composantes) for coeff, composantes in self.valeurs.items()}

    def vers_serie(self) -> pd.Series:
        """Le tirage à plat : ``{"<coeff>_Biais": …, "<coeff>_FE": …}``."""
        plat = {
            f"{coeff}_{composante}": valeur
            for coeff, composantes in self.valeurs.items()
            for composante, valeur in composantes.items()
        }
        return pd.Series(plat, dtype=float)

    @property
    def resume(self) -> str:
        """Description compacte pour une boîte de paramètres."""
        graine = "libre" if self.graine is None else str(self.graine)
        return f"{self.convention.formule} · plan {self.methode} · graine {graine}"


def tirer(
    lois: JeuDeLois,
    *,
    graine: int | None = None,
    convention_: ConventionArg = None,
    methode: str = "mc",
) -> Tirage:
    """Tire une réalisation de chaque loi de *lois*.

    Parameters
    ----------
    lois:
        Le jeu de lois, tel que rendu par
        :func:`cfd_dispersion.core.lois.charger_lois`.
    graine:
        Graine posée le temps du tirage, l'état global étant restauré ensuite.
    convention_:
        La relation de reconstruction portée par le tirage. Défaut :
        ``"lineaire"``.
    methode:
        Plan d'échantillonnage. Sur un tirage unique il n'a guère d'effet ; il
        est accepté pour que ``tirer`` et :func:`tirer_lot` s'écrivent pareil.

    Returns
    -------
    Tirage

    Examples
    --------
    >>> lois = charger_lois(DICT_DISP_LAWS)          # doctest: +SKIP
    >>> t = tirer(lois, graine=42)                   # doctest: +SKIP
    >>> t["Cm_alpha"]["Biais"]                       # doctest: +SKIP
    """
    lot = tirer_lot(lois, 1, graine=graine, methode=methode)
    ligne = lot.iloc[0]

    valeurs: dict[str, dict[str, float]] = {
        coeff: {composante: float(ligne[f"{coeff}_{composante}"]) for composante in COMPOSANTES}
        for coeff in lois
    }
    return Tirage(
        valeurs=valeurs,
        convention=convention(convention_),
        graine=graine,
        methode=methode,
    )


def tirer_lot(
    lois: JeuDeLois,
    n: int,
    *,
    graine: int | None = None,
    methode: str = "mc",
) -> pd.DataFrame:
    """Tire *n* réalisations de toutes les lois d'un coup.

    Le tirage passe par la loi **jointe** de toutes les composantes, et non par
    chaque loi séparément. Deux raisons : une corrélation déclarée n'est
    honorée que là, et les plans LHS et Sobol ne valent que sur l'ensemble des
    dimensions — c'est précisément le remplissage conjoint qu'ils améliorent.

    Parameters
    ----------
    lois:
        Le jeu de lois.
    n:
        Nombre de tirages, strictement positif.
    graine:
        Graine posée le temps du tirage, l'état global étant restauré ensuite.
    methode:
        ``"mc"`` (défaut), ``"lhs"`` ou ``"sobol"``.

    Returns
    -------
    pandas.DataFrame
        ``n`` lignes, une colonne par composante (``"<coeff>_Biais"``,
        ``"<coeff>_FE"``, …) dans l'ordre de la table d'origine.
    """
    if n <= 0:
        raise ValueError(f"n doit être strictement positif, reçu {n!r}")
    if methode not in METHODES:
        raise ValueError(f"méthode inconnue : {methode!r} ; attendu l'une de {list(METHODES)}")

    jointe = lois.distribution_jointe()
    with graine_temporaire(graine):
        if methode == "mc":
            brut = jointe.getSample(n)
        elif methode == "lhs":
            brut = _lhs(jointe, n)
        else:
            brut = _sobol(jointe, n)

    return pd.DataFrame(np.asarray(brut, dtype=float), columns=list(lois.colonnes))


def _lhs(jointe: object, n: int) -> object:
    import openturns as ot

    return ot.LHSExperiment(jointe, n).generate()


def _sobol(jointe: object, n: int) -> object:
    import openturns as ot

    return ot.LowDiscrepancyExperiment(ot.SobolSequence(), jointe, n).generate()
