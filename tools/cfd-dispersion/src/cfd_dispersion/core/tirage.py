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

Pour appeler le modèle mille fois, :func:`tirer_lot` rend la **liste** de ces
tirages — une liste de ``DICT_DISP_DRAWN``, sur laquelle il n'y a plus qu'à
boucler ::

    for tirage in tirer_lot(lois, 1000, graine=42, methode="lhs"):
        resultats.append(mon_modele(tirage))

C'est la même chose qu'une boucle ``tirer(lois, graine=graine + i)``, à ceci
près que le lot est tiré **d'un coup** : c'est la seule façon d'honorer une
corrélation déclarée, et la seule où les plans LHS et Sobol apportent quelque
chose — ce qu'ils améliorent est le remplissage conjoint, qui n'existe pas à
l'échelle d'un tirage isolé.

Pour l'écrire à plat — un CSV, une statistique descriptive, un tableau de
colonnes ``"<coeff>_Biais"`` — :func:`tableau_des_tirages` rend le
``DataFrame`` correspondant, et :func:`tirer_tableau` fait les deux d'un coup.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
import pandas as pd

from .alea import graine_temporaire
from .convention import Convention, ConventionArg, convention
from .loi import METHODES
from .lois import COMPOSANTES, JeuDeLois

__all__ = ["Tirage", "tableau_des_tirages", "tirer", "tirer_lot", "tirer_tableau"]


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
        Le plan d'échantillonnage employé, ou None quand il n'est pas connu —
        le cas d'un tirage relu d'un tableau, qui ne dit pas comment il a été
        produit.
    numero:
        Le rang du tirage dans son lot, à partir de 0 — ou None pour un tirage
        isolé. C'est la colonne ``"tirage"`` que porte la sortie d'un modèle,
        et de quoi retrouver lequel des mille appels a produit une courbe.
    """

    valeurs: dict[str, dict[str, float]]
    convention: Convention
    graine: int | None = None
    methode: str | None = "mc"
    numero: int | None = None
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
        morceaux = [self.convention.formule]
        # Un tirage relu d'un tableau ne sait ni son plan ni sa graine : le
        # tableau ne les porte pas. Se taire vaut mieux qu'annoncer « plan mc,
        # graine libre » sur un tirage qui fut LHS et semé.
        if self.methode is not None:
            morceaux.append(f"plan {self.methode}")
            morceaux.append(f"graine {'libre' if self.graine is None else self.graine}")
        elif self.graine is not None:
            morceaux.append(f"graine {self.graine}")
        if self.numero is not None:
            morceaux.append(f"tirage {self.numero}")
        return " · ".join(morceaux)


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
    (unique,) = tirer_lot(lois, 1, graine=graine, convention_=convention_, methode=methode)
    # Sans numéro : un tirage isolé n'a pas de rang dans un lot, et un « 0 »
    # laisserait croire qu'il en a un.
    return replace(unique, numero=None)


def tirer_lot(
    lois: JeuDeLois,
    n: int,
    *,
    graine: int | None = None,
    convention_: ConventionArg = None,
    methode: str = "mc",
) -> list[Tirage]:
    """Tire *n* réalisations de toutes les lois, et les rend **une par une**.

    C'est la forme sous laquelle un modèle les consomme : chaque élément est un
    :class:`Tirage`, donc un ``Mapping`` ``{coeff: {"Biais": …, "FE": …}}`` qui
    se passe tel quel ::

        for tirage in tirer_lot(lois, 1000, graine=42, methode="lhs"):
            resultats.append(mon_modele(tirage))

    Le tirage passe par la loi **jointe** de toutes les composantes, et non par
    chaque loi séparément. Deux raisons : une corrélation déclarée n'est
    honorée que là, et les plans LHS et Sobol ne valent que sur l'ensemble des
    dimensions — c'est précisément le remplissage conjoint qu'ils améliorent.
    C'est aussi ce qui distingue cette fonction d'une boucle
    ``tirer(lois, graine=graine + i)`` : cette boucle-là donne bien *n* tirages
    Monte-Carlo indépendants, mais aucun plan ne peut y améliorer le
    remplissage, puisque chaque tirage ignore les autres.

    Parameters
    ----------
    lois:
        Le jeu de lois.
    n:
        Nombre de tirages, strictement positif.
    graine:
        Graine posée le temps du tirage, l'état global étant restauré ensuite.
        Elle vaut pour le lot entier, et chaque tirage porte en plus son
        :attr:`Tirage.numero`.
    convention_:
        La relation de reconstruction portée par les tirages. Défaut :
        ``"lineaire"``.
    methode:
        ``"mc"`` (défaut), ``"lhs"`` ou ``"sobol"``.

    Returns
    -------
    list[Tirage]
        *n* tirages, dans l'ordre, numérotés de 0 à ``n - 1``.

    See Also
    --------
    tableau_des_tirages : les mêmes tirages à plat, en ``DataFrame``.

    Examples
    --------
    >>> lot = tirer_lot(lois, 3, graine=42)          # doctest: +SKIP
    >>> lot[0]["Cm_alpha"]["Biais"]                  # doctest: +SKIP
    >>> lot[0].numero                                # doctest: +SKIP
    0
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

    valeurs = np.asarray(brut, dtype=float)
    relation = convention(convention_)
    # Les composantes sortent dans l'ordre de `lois.colonnes` : deux colonnes
    # par coefficient, biais puis FE. Les positions sont calculées une fois,
    # et non recherchées par nom à chaque ligne.
    positions = [(coeff, 2 * rang, 2 * rang + 1) for rang, coeff in enumerate(lois)]

    return [
        Tirage(
            valeurs={
                coeff: {
                    COMPOSANTES[0]: float(ligne[i_biais]),
                    COMPOSANTES[1]: float(ligne[i_fe]),
                }
                for coeff, i_biais, i_fe in positions
            },
            convention=relation,
            graine=graine,
            methode=methode,
            numero=numero,
        )
        for numero, ligne in enumerate(valeurs)
    ]


def tableau_des_tirages(tirages: Sequence[Tirage]) -> pd.DataFrame:
    """Met un lot de tirages à plat : une ligne par tirage, deux colonnes par coefficient.

    C'est la forme qui s'écrit en CSV, se décrit d'un ``describe()``, et se
    compare à une sortie de modèle — celle que :func:`tirer_lot` rendait
    autrefois. Les colonnes sont ``"<coeff>_Biais"`` et ``"<coeff>_FE"``, dans
    l'ordre de la table de lois d'origine.

    Parameters
    ----------
    tirages:
        Le lot, tel que rendu par :func:`tirer_lot`.

    Returns
    -------
    pandas.DataFrame

    Raises
    ------
    ValueError
        Si le lot est vide : les colonnes en dépendent, et un tableau sans
        colonnes ne dirait pas ce qui manque.
    """
    lot = list(tirages)
    if not lot:
        raise ValueError("lot vide : il n'y a pas de colonnes à en déduire")

    lignes = [
        {
            f"{coeff}_{composante}": valeur
            for coeff, composantes in tirage.valeurs.items()
            for composante, valeur in composantes.items()
        }
        for tirage in lot
    ]
    return pd.DataFrame(lignes, dtype=float)


def tirer_tableau(
    lois: JeuDeLois,
    n: int,
    *,
    graine: int | None = None,
    methode: str = "mc",
) -> pd.DataFrame:
    """Tire *n* réalisations et les rend **à plat**, en ``DataFrame``.

    Raccourci de ``tableau_des_tirages(tirer_lot(...))``, pour le cas où c'est
    le tableau qu'on veut d'emblée : un CSV, un ``describe()``, ou les colonnes
    ``"<coeff>_Biais"`` à recoller à une sortie de modèle.

    Pour appeler un modèle, c'est :func:`tirer_lot` qu'il faut : il rend les
    tirages un par un, sous la forme que le modèle attend.
    """
    return tableau_des_tirages(tirer_lot(lois, n, graine=graine, methode=methode))


def _lhs(jointe: object, n: int) -> object:
    import openturns as ot

    return ot.LHSExperiment(jointe, n).generate()


def _sobol(jointe: object, n: int) -> object:
    import openturns as ot

    return ot.LowDiscrepancyExperiment(ot.SobolSequence(), jointe, n).generate()
