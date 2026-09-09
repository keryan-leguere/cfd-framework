"""Les coefficients de sortie qui se **déduisent** de ceux qu'on tire.

La table de lois disperse ce que le modèle *consomme* ; le tableau rend ce
qu'il *produit*. Les deux listes ne coïncident pas toujours, et le décalage est
souvent une simple **relation linéaire** — un changement de repère, une somme
de contributions ::

    DICT_DISP_LAWS   CZ                 CX1, CX2
    sortie modèle    CN = -CZ           CA = CX1 + CX2

Sans rien de plus, ``CN`` et ``CA`` sont des colonnes sans loi : leur
histogramme se trace, mais rien ne dit ce qu'il aurait dû être. Ce module
comble exactement cela ::

    relations = charger_relations({"CN": "-CZ", "CA": "CX1 + CX2"})
    lois = lois_avec_relations(lois, relations, nominaux={"CX1": 0.02, "CX2": 0.01})

    lois["CN"].biais        # la loi du biais de CN, dérivée de celle de CZ
    lois["CA"].fe           # celle du facteur d'échelle de CA

Ce qui est dérivé, et comment
-----------------------------
Un coefficient n'a pas *une* loi mais **deux** — un biais additif et un facteur
d'échelle — et la relation ne les transforme pas de la même façon. Le facteur
d'échelle multiplie le nominal : deux contributions qui s'additionnent ne
partagent leur facteur qu'au prorata de ce qu'elles pèsent.

À nominal fixé, une relation de reconstruction s'écrit ``α·Biais + β·FE + cst``
(voir :func:`cfd_dispersion.core.combinaison.decomposition_affine`). En
écrivant que la cible reconstruite vaut la combinaison des sources
reconstruites, il vient, pour ``cible = Σ aᵢ·sourceᵢ + k`` ::

    Biais_cible = Σ  aᵢ·α(cᵢ)/α(c_cible) · Biais_i
    FE_cible    = Σ  aᵢ·β(cᵢ)/β(c_cible) · FE_i     + un décalage

Pour les trois conventions livrées, ``α ≡ 1`` et ``β ∝ c``, donc les poids du
biais sont les ``aᵢ`` eux-mêmes et ceux du facteur d'échelle sont les parts
``aᵢ·cᵢ/c_cible``. Le décalage est celui qui **laisse le tirage neutre neutre** :
un tirage qui ne disperse rien pour les sources ne doit rien disperser pour la
cible. L'égalité est ensuite **vérifiée** numériquement, jamais supposée : une
convention maison non affine est refusée plutôt que dérivée de travers.

Les nominaux, et quand on peut s'en passer
------------------------------------------
Les poids du facteur d'échelle font intervenir les valeurs nominales des
sources — ils changent donc d'un point de vol à l'autre, et les parcours
(:mod:`cfd_dispersion.figures.par_pdv`) dérivent les lois **par point de vol**.

Un cas s'en passe, et c'est le plus fréquent : une relation à **un seul terme
et sans constante**, ``CN = -CZ``. Le facteur d'échelle y est inchangé et le
biais suit le facteur, quel que soit le nominal. Le paquet le vérifie sur la
convention employée avant d'en profiter.

La loi dérivée n'est pas une loi de la table
--------------------------------------------
La somme de deux gaussiennes tronquées n'appartient à aucune des six familles :
une loi dérivée est donc une distribution OpenTURNS quelconque, portée par
:class:`LoiDerivee`, qui expose la même interface que
:class:`cfd_dispersion.core.loi.LoiDispersion` — ``pdf``, ``support``,
``plage_utile``, ``M_theorique``, ``ET_theorique`` — de sorte que figures,
validation et boîtes de paramètres ne distinguent pas les deux.

Un cas fait exception, et il est fréquent : une relation à un seul terme reste
**dans sa famille** (``-CZ`` d'une gaussienne ±3σ est une gaussienne ±3σ), et
rend alors une vraie :class:`LoiDispersion`, avec son type et son ``ET``.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Union

import numpy as np

from .alea import graine_temporaire, vers_numpy
from .combinaison import combinaison_lineaire
from .convention import Convention, ConventionArg, convention
from .loi import LoiComposante, LoiDispersion
from .lois import COMPOSANTES, JeuDeLois, LoiCoefficient

__all__ = [
    "LoiDerivee",
    "Relation",
    "RelationArg",
    "charger_relations",
    "composantes_derivees",
    "loi_derivee",
    "lois_avec_relations",
    "poids_derives",
]

#: Tolérance relative du contrôle de cohérence de la dérivation.
_TOL = 1e-9


# ---------------------------------------------------------------------------
# La relation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Relation:
    """Un coefficient de sortie, combinaison linéaire de coefficients tirés.

    Attributes
    ----------
    cible:
        Le nom du coefficient produit — celui de la colonne de sortie.
    termes:
        ``((source, poids), …)``, dans l'ordre d'écriture.
    constante:
        Le terme constant, non dispersé.

    Examples
    --------
    >>> Relation.depuis_texte("CN = -CZ")
    Relation(cible='CN', termes=(('CZ', -1.0),), constante=0.0)
    >>> str(Relation.depuis_texte("CA = CX1 + CX2"))
    'CA = CX1 + CX2'
    """

    cible: str
    termes: tuple[tuple[str, float], ...]
    constante: float = 0.0

    def __post_init__(self) -> None:
        if not self.cible:
            raise ValueError("une relation doit nommer son coefficient cible")
        if not self.termes:
            raise ValueError(
                f"la relation de {self.cible!r} n'a aucun terme : "
                "un coefficient constant n'a pas de loi à dériver"
            )
        vus: set[str] = set()
        for source, _ in self.termes:
            if source == self.cible:
                raise ValueError(
                    f"la relation de {self.cible!r} se réfère à elle-même — "
                    "une cible ne peut pas être l'une de ses propres sources"
                )
            if source in vus:
                raise ValueError(
                    f"la relation de {self.cible!r} nomme {source!r} deux fois ; "
                    "regrouper les termes (« CX1 + CX1 » s'écrit « 2*CX1 »)"
                )
            vus.add(source)
        object.__setattr__(self, "constante", float(self.constante))
        object.__setattr__(
            self, "termes", tuple((str(nom), float(poids)) for nom, poids in self.termes)
        )

    # -- lecture --------------------------------------------------------

    @property
    def sources(self) -> tuple[str, ...]:
        """Les coefficients tirés dont la cible dépend."""
        return tuple(nom for nom, _ in self.termes)

    @property
    def est_simple(self) -> bool:
        """Vrai pour ``cible = a·source`` : un terme, pas de constante.

        C'est le seul cas qui se dérive sans connaître les valeurs nominales.
        """
        return len(self.termes) == 1 and self.constante == 0.0

    @property
    def expression(self) -> str:
        """Le membre de droite, tel qu'il s'écrit : ``-CZ``, ``CX1 + CX2``."""
        morceaux = []
        for indice, (nom, poids) in enumerate(self.termes):
            signe = "-" if poids < 0 else ("" if indice == 0 else "+")
            grandeur = abs(poids)
            facteur = "" if grandeur == 1.0 else f"{grandeur:g}*"
            morceaux.append(f"{signe} {facteur}{nom}" if indice else f"{signe}{facteur}{nom}")
        if self.constante:
            morceaux.append(f"{'-' if self.constante < 0 else '+'} {abs(self.constante):g}")
        return " ".join(morceaux)

    def __str__(self) -> str:
        return f"{self.cible} = {self.expression}"

    def appliquer(self, valeurs: Mapping[str, Any]) -> Any:
        """La cible, calculée depuis les valeurs de ses sources.

        Accepte des scalaires comme des tableaux : un balayage entier se
        combine d'un coup.
        """
        manquants = sorted(nom for nom in self.sources if nom not in valeurs)
        if manquants:
            raise ValueError(
                f"la relation « {self} » demande {manquants}, absent(s) des valeurs fournies "
                f"({sorted(valeurs)})"
            )
        total: Any = self.constante
        for nom, poids in self.termes:
            total = total + poids * np.asarray(valeurs[nom], dtype=float)
        return total

    # -- écriture -------------------------------------------------------

    @classmethod
    def depuis_texte(cls, texte: str, *, cible: str | None = None) -> Relation:
        """Lit ``"CA = CX1 + CX2"``, ou ``"CX1 + CX2"`` avec *cible* donnée.

        La syntaxe admise est volontairement pauvre — sommes, différences,
        facteurs numériques, constante — parce qu'au-delà ce n'est plus une
        relation linéaire, et qu'une loi dérivée n'aurait plus de sens ::

            CN = -CZ
            CA = CX1 + CX2
            Cm = 0.5*Cm0 - 2 * Cm1 + 0.01
            CN = CZ/2
        """
        gauche, separateur, droite = texte.partition("=")
        if separateur:
            nom = gauche.strip()
            if cible is not None and nom != cible:
                raise ValueError(
                    f"la relation « {texte.strip()} » nomme {nom!r} là où {cible!r} est attendu"
                )
            membre = droite
        else:
            if cible is None:
                raise ValueError(
                    f"relation sans cible : « {texte.strip()} » — écrire « CIBLE = … », "
                    "ou passer la cible en clé du dictionnaire"
                )
            nom, membre = cible, texte
        termes, constante = _lire_expression(membre, cible=nom)
        return cls(cible=nom, termes=termes, constante=constante)


#: Ce qu'accepte :func:`charger_relations`.
RelationArg = Union[
    "Relation",
    str,
    Mapping[str, Any],
    Sequence[Union["Relation", str]],
    None,
]


def charger_relations(relations: RelationArg) -> dict[str, Relation]:
    """Normalise les écritures admises en ``{cible: Relation}``.

    Quatre formes, toutes équivalentes ::

        charger_relations({"CN": "-CZ", "CA": "CX1 + CX2"})
        charger_relations(["CN = -CZ", "CA = CX1 + CX2"])
        charger_relations({"CN": {"CZ": -1.0}})
        charger_relations(Relation("CN", (("CZ", -1.0),)))

    La troisième — un dictionnaire de poids — est celle qu'on écrit quand les
    coefficients sont nombreux et que la formule vient d'un calcul.
    """
    if relations is None:
        return {}
    if isinstance(relations, Relation):
        return {relations.cible: relations}
    if isinstance(relations, str):
        lue = Relation.depuis_texte(relations)
        return {lue.cible: lue}

    resultat: dict[str, Relation] = {}
    if isinstance(relations, Mapping):
        for cible, brut in relations.items():
            resultat[str(cible)] = _une_relation(brut, cible=str(cible))
        return resultat

    for brut in relations:
        lue = _une_relation(brut, cible=None)
        if lue.cible in resultat:
            raise ValueError(
                f"deux relations pour {lue.cible!r} : « {resultat[lue.cible]} » et « {lue} »"
            )
        resultat[lue.cible] = lue
    return resultat


def _une_relation(brut: Any, *, cible: str | None) -> Relation:
    """Une entrée de ``charger_relations``, quelle que soit son écriture."""
    if isinstance(brut, Relation):
        if cible is not None and brut.cible != cible:
            raise ValueError(f"la relation « {brut} » est rangée sous la clé {cible!r}")
        return brut
    if isinstance(brut, str):
        return Relation.depuis_texte(brut, cible=cible)
    if isinstance(brut, Mapping):
        if cible is None:
            raise ValueError("un dictionnaire de poids doit être rangé sous le nom de sa cible")
        constante = float(brut.get("", 0.0))
        termes = tuple(
            (str(nom), float(poids)) for nom, poids in brut.items() if str(nom) not in ("",)
        )
        return Relation(cible=cible, termes=termes, constante=constante)
    raise TypeError(
        f"relation illisible : {brut!r} ; attendu une chaîne « CIBLE = … », "
        "un dictionnaire {source: poids} ou une Relation"
    )


_JETON = re.compile(
    r"(?P<nombre>\d+(?:\.\d*)?(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)"
    r"|(?P<nom>[A-Za-z_][A-Za-z_0-9]*)"
    r"|(?P<op>[+\-*/·×])"
    r"|(?P<espace>\s+)"
)


def _lire_expression(membre: str, *, cible: str) -> tuple[tuple[tuple[str, float], ...], float]:
    """Découpe ``« 0.5*CX1 - CX2 + 0.01 »`` en termes et constante.

    Un analyseur à la main plutôt qu'un ``eval`` : la chaîne vient d'un
    fichier de configuration, et ``eval`` y exécuterait n'importe quoi.
    """
    jetons: list[tuple[str, str]] = []
    position = 0
    for trouve in _JETON.finditer(membre):
        if trouve.start() != position:
            raise ValueError(
                f"relation de {cible!r} illisible : caractère inattendu "
                f"{membre[position]!r} dans « {membre.strip()} »"
            )
        position = trouve.end()
        genre = trouve.lastgroup or ""
        if genre != "espace":
            jetons.append((genre, trouve.group()))
    if position != len(membre):
        raise ValueError(
            f"relation de {cible!r} illisible : caractère inattendu {membre[position]!r} "
            f"dans « {membre.strip()} »"
        )
    if not jetons:
        raise ValueError(f"relation de {cible!r} vide")

    termes: list[tuple[str, float]] = []
    constante = 0.0
    index = 0
    premier = True

    while index < len(jetons):
        signe = 1.0
        genre, texte = jetons[index]
        if genre == "op" and texte in "+-":
            signe = -1.0 if texte == "-" else 1.0
            index += 1
            if index >= len(jetons):
                raise ValueError(
                    f"relation de {cible!r} : « {membre.strip()} » finit sur un opérateur"
                )
        elif not premier:
            raise ValueError(
                f"relation de {cible!r} : il manque un « + » ou un « - » avant {texte!r}"
            )

        facteur, nom, index = _lire_terme(jetons, index, cible=cible, membre=membre)
        if nom is None:
            constante += signe * facteur
        else:
            termes.append((nom, signe * facteur))
        premier = False

    return tuple(termes), constante


def _lire_terme(
    jetons: Sequence[tuple[str, str]],
    index: int,
    *,
    cible: str,
    membre: str,
) -> tuple[float, str | None, int]:
    """Un produit de facteurs — au plus un nom — et l'indice qui suit.

    La multiplication s'écrit ``2*CX1``, ``2 CX1`` ou ``CX1*2`` indifféremment ;
    la division ne porte que sur un nombre. Deux noms multipliés entre eux sont
    refusés : la relation ne serait plus linéaire, et sa loi ne se dériverait
    plus.
    """
    facteur = 1.0
    nom: str | None = None
    operation = "*"
    premier = True

    while index < len(jetons):
        genre, texte = jetons[index]

        if genre == "op":
            if texte in "+-":
                break
            if premier:
                raise ValueError(
                    f"relation de {cible!r} : opérateur isolé dans « {membre.strip()} »"
                )
            operation = "/" if texte == "/" else "*"
            index += 1
            if index >= len(jetons) or jetons[index][0] == "op":
                raise ValueError(
                    f"relation de {cible!r} : « {membre.strip()} » finit sur un opérateur"
                )
            continue

        if genre == "nombre":
            valeur = float(texte)
            if operation == "/":
                if valeur == 0.0:
                    raise ValueError(
                        f"relation de {cible!r} : division par zéro dans « {membre.strip()} »"
                    )
                facteur /= valeur
            else:
                facteur *= valeur
        else:
            if operation == "/":
                raise ValueError(
                    f"relation de {cible!r} : division par {texte!r} — "
                    "une relation dérivable est linéaire en ses sources"
                )
            if nom is not None:
                raise ValueError(
                    f"relation de {cible!r} : {nom!r} et {texte!r} multipliés l'un par l'autre — "
                    "une relation dérivable est linéaire en ses sources"
                )
            nom = texte

        premier = False
        operation = "*"
        index += 1

    if premier:
        raise ValueError(f"relation de {cible!r} : terme vide dans « {membre.strip()} »")
    return facteur, nom, index


# ---------------------------------------------------------------------------
# La loi dérivée
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LoiDerivee:
    """La loi d'une composante **déduite** d'autres composantes tirées.

    Elle répond aux mêmes questions qu'une :class:`LoiDispersion` — densité,
    support, moments, plage de tracé — mais elle n'a pas de type : la
    combinaison linéaire de plusieurs lois n'appartient en général à aucune des
    six familles.

    Attributes
    ----------
    coefficient:
        Le coefficient cible.
    composante:
        ``"Biais"`` ou ``"FE"``.
    termes:
        ``((source, poids), …)`` de la combinaison, sur la composante.
    constante:
        Le décalage ajouté à la combinaison.
    distribution:
        La distribution OpenTURNS obtenue.

    Notes
    -----
    ``M`` et ``ET`` ne sont pas déclarés mais **relus** : ``M`` est la moyenne
    exacte, et ``ET`` la demi-étendue qu'il faudrait écrire dans une table pour
    obtenir cet écart-type, soit ``2σ`` — la convention ``σ = ET/2`` du paquet,
    appliquée à l'envers.
    """

    coefficient: str
    composante: str
    termes: tuple[tuple[str, float], ...]
    constante: float
    distribution: Any

    # -- description ----------------------------------------------------

    @property
    def expression(self) -> str:
        """La combinaison, telle qu'elle s'écrit : ``-CZ_Biais``."""
        morceaux = []
        for indice, (nom, poids) in enumerate(self.termes):
            signe = "-" if poids < 0 else ("" if indice == 0 else "+")
            grandeur = abs(poids)
            facteur = "" if math.isclose(grandeur, 1.0) else f"{grandeur:.4g}*"
            terme = f"{facteur}{nom}_{self.composante}"
            morceaux.append(f"{signe} {terme}" if indice else f"{signe}{terme}")
        if self.constante:
            morceaux.append(f"{'-' if self.constante < 0 else '+'} {abs(self.constante):.4g}")
        return " ".join(morceaux) if morceaux else f"{self.constante:.4g}"

    @property
    def label(self) -> str:
        """Libellé court, pour une colonne de tableau : ``dérivée``.

        L'expression n'y est pas : elle est parfois longue de trois termes, et
        une boîte de paramètres de figure partage sa largeur avec la légende.
        Les figures la lisent séparément, dans :attr:`expression`.
        """
        return "dérivée"

    @property
    def M(self) -> float:
        """Moyenne de la loi dérivée."""
        return self.M_theorique

    @property
    def ET(self) -> float:
        """La demi-étendue équivalente, ``2σ`` — voir les notes de la classe."""
        return 2.0 * self.ET_theorique

    @property
    def est_degeneree(self) -> bool:
        """Vrai si la composante dérivée est en fait déterministe."""
        return self.ET_theorique == 0.0

    @property
    def est_bornee(self) -> bool:
        """Vrai si le support est borné des deux côtés."""
        plage = self.distribution.getRange()
        return bool(plage.getFiniteLowerBound()[0] and plage.getFiniteUpperBound()[0])

    @property
    def sigma_nominal(self) -> float:
        """Sans objet pour une loi dérivée : elle n'a pas de σ *déclaré*."""
        return self.ET_theorique

    @property
    def M_theorique(self) -> float:
        """Moyenne exacte, calculée par OpenTURNS."""
        return float(self.distribution.getMean()[0])

    @property
    def ET_theorique(self) -> float:
        """Écart-type exact, calculé par OpenTURNS."""
        return float(self.distribution.getStandardDeviation()[0])

    # -- densité, quantiles, bornes --------------------------------------

    def support(self) -> tuple[float, float]:
        """Bornes du support, ``(-inf, +inf)`` du côté non borné."""
        plage = self.distribution.getRange()
        bas = float(plage.getLowerBound()[0])
        haut = float(plage.getUpperBound()[0])
        return (
            bas if plage.getFiniteLowerBound()[0] else -math.inf,
            haut if plage.getFiniteUpperBound()[0] else math.inf,
        )

    def plage_utile(self, *, k: float = 4.0, marge: float = 0.05) -> tuple[float, float]:
        """Bornes **finies** utilisables pour tracer la loi."""
        moyenne, sigma = self.M_theorique, self.ET_theorique
        if sigma == 0.0:
            demi = max(abs(moyenne), 1.0) * 0.1
            return (moyenne - demi, moyenne + demi)
        plage = self.distribution.getRange()
        bas = max(float(plage.getLowerBound()[0]), moyenne - k * sigma)
        haut = min(float(plage.getUpperBound()[0]), moyenne + k * sigma)
        largeur = haut - bas
        return (bas - marge * largeur, haut + marge * largeur)

    def pdf(self, x: object) -> np.ndarray:
        """Densité de probabilité aux abscisses *x*, forme ``(n,)``."""
        points = np.atleast_1d(np.asarray(x, dtype=float))
        return vers_numpy(self.distribution.computePDF([[float(v)] for v in points]))

    def cdf(self, x: object) -> np.ndarray:
        """Fonction de répartition aux abscisses *x*, forme ``(n,)``."""
        points = np.atleast_1d(np.asarray(x, dtype=float))
        return vers_numpy(self.distribution.computeCDF([[float(v)] for v in points]))

    def quantile(self, p: object) -> np.ndarray:
        """Quantiles aux probabilités *p*, forme ``(n,)``."""
        probas = np.atleast_1d(np.asarray(p, dtype=float))
        if np.any((probas < 0.0) | (probas > 1.0)):
            raise ValueError("les probabilités doivent être dans [0, 1]")
        return np.array([float(self.distribution.computeQuantile(float(v))[0]) for v in probas])

    def tirer(self, n: int, *, graine: int | None = None, methode: str = "mc") -> np.ndarray:
        """*n* réalisations de la loi dérivée, forme ``(n,)``.

        Le plan d'échantillonnage est celui d'une loi ordinaire ; ``methode``
        est accepté pour que la signature soit celle de
        :meth:`LoiDispersion.tirer`.
        """
        del methode
        with graine_temporaire(graine):
            return vers_numpy(self.distribution.getSample(int(n)))


# ---------------------------------------------------------------------------
# La dérivation
# ---------------------------------------------------------------------------


def loi_derivee(
    relation: Relation,
    lois: Mapping[str, LoiCoefficient],
    *,
    nominaux: Mapping[str, Any] | None = None,
    convention_: ConventionArg = None,
) -> LoiCoefficient:
    """Les deux lois du coefficient cible, déduites de celles de ses sources.

    Parameters
    ----------
    relation:
        La relation linéaire liant la cible aux coefficients tirés.
    lois:
        Le jeu de lois, qui doit porter chacune des sources.
    nominaux:
        ``{coefficient: valeur nominale}``. Nécessaires dès que la relation a
        plus d'un terme ou une constante : les poids du facteur d'échelle sont
        des **parts**, et une part dépend de ce que pèse chaque contribution.
        Une relation à un seul terme sans constante s'en passe.
    convention_:
        La relation de reconstruction. Défaut : ``"lineaire"``.

    Returns
    -------
    LoiCoefficient
        Les lois du biais et du facteur d'échelle de la cible. Chacune est une
        :class:`LoiDispersion` quand la combinaison reste dans sa famille — le
        cas d'un terme unique — et une :class:`LoiDerivee` sinon.

    Raises
    ------
    ValueError
        Si une source manque au jeu de lois, si les nominaux manquent là où ils
        sont nécessaires, si la convention n'est pas affine en (biais, FE), ou
        si le jeu de lois déclare une corrélation — une combinaison de lois
        corrélées ne se calcule pas ainsi.

    Examples
    --------
    >>> from cfd_dispersion import charger_lois
    >>> lois = charger_lois({"CZ": {"Biais_Type": 5, "Biais_M": 0.0,
    ...                            "Biais_ET": 0.02, "FE_Type": 6,
    ...                            "FE_M": 1.0, "FE_ET": 0.08}})
    >>> derivee = loi_derivee(Relation.depuis_texte("CN = -CZ"), lois)
    >>> derivee.biais.M, derivee.biais.ET
    (0.0, 0.02)
    >>> derivee.fe.ET
    0.08
    """
    manquantes = [nom for nom in relation.sources if nom not in lois]
    if manquantes:
        raise ValueError(
            f"la relation « {relation} » s'appuie sur {manquantes}, "
            f"absent(s) du jeu de lois ({sorted(lois)})"
        )
    if isinstance(lois, JeuDeLois) and not lois.independantes:
        raise ValueError(
            f"la relation « {relation} » ne se dérive pas d'un jeu de lois corrélé : "
            "la loi d'une somme de composantes dépendantes n'est pas leur combinaison. "
            "Dériver depuis les lois indépendantes, ou renoncer à la loi théorique de la cible."
        )

    reconstruction = convention(convention_)
    poids_biais, poids_fe, decalage_fe = _poids(relation, reconstruction, nominaux)

    composantes: list[LoiComposante] = []
    for composante, poids, decalage in (
        (COMPOSANTES[0], poids_biais, 0.0),
        (COMPOSANTES[1], poids_fe, decalage_fe),
    ):
        sources = tuple(
            (nom, poids[nom]) for nom, _ in relation.termes if poids.get(nom, 0.0) != 0.0
        )
        simple = _dans_la_famille(lois, sources, decalage, composante)
        if simple is not None:
            composantes.append(simple)
            continue
        distribution = combinaison_lineaire(
            [(facteur, lois[nom].composante(composante)) for nom, facteur in sources],
            decalage,
        )
        if distribution is None:  # pragma: no cover - OpenTURNS a refusé la combinaison
            raise ValueError(
                f"la loi de {relation.cible}_{composante} ne se combine pas "
                f"({relation}) — la calculer à la main, ou passer des lois explicites"
            )
        composantes.append(
            LoiDerivee(
                coefficient=relation.cible,
                composante=composante,
                termes=sources,
                constante=decalage,
                distribution=distribution,
            )
        )

    return LoiCoefficient(nom=relation.cible, biais=composantes[0], fe=composantes[1])


def _dans_la_famille(
    lois: Mapping[str, LoiCoefficient],
    sources: Sequence[tuple[str, float]],
    decalage: float,
    composante: str,
) -> LoiDispersion | None:
    """La loi transformée, quand ``a·X + b`` reste dans la famille de ``X``.

    Une seule source y suffit : mettre une loi à l'échelle et la translater ne
    change ni sa famille ni sa forme, seulement son centre et sa largeur. La
    garder comme :class:`LoiDispersion` n'est pas cosmétique — elle garde son
    type, son ``ET`` déclaré et ses bornes exactes, donc tout ce qu'un rapport
    ou une validation lit d'une loi de la table.
    """
    if len(sources) != 1:
        return None
    nom, facteur = sources[0]
    source = lois[nom].composante(composante)
    if not isinstance(source, LoiDispersion):
        return None
    if facteur == 0.0:
        return LoiDispersion(type_loi=2, M=decalage)
    if source.type_loi == 1:
        # La loi nulle est un Dirac en 0 quoi qu'en dise M : a·0 + b = b.
        return LoiDispersion(type_loi=1) if decalage == 0.0 else LoiDispersion(2, M=decalage)
    if source.type_loi == 2:
        return LoiDispersion(type_loi=2, M=facteur * source.M + decalage)
    return LoiDispersion(
        type_loi=source.type_loi,
        M=facteur * source.M + decalage,
        ET=abs(facteur) * source.ET,
    )


def poids_derives(
    relation: Relation,
    *,
    nominaux: Mapping[str, Any] | None = None,
    convention_: ConventionArg = None,
) -> tuple[dict[str, float], dict[str, float], float]:
    """Les poids de la dérivation : ``(poids du biais, poids du FE, décalage)``.

    Ce que :func:`loi_derivee` applique aux lois et
    :func:`composantes_derivees` aux valeurs d'un tirage. Exposé parce qu'un
    parcours les applique aussi à des **colonnes entières** — les mille biais
    tirés d'un point de vol — et qu'un aller-retour par valeur y coûterait
    mille fois le calcul des poids.
    """
    return _poids(relation, convention(convention_), nominaux)


def composantes_derivees(
    relation: Relation,
    tirage: Mapping[str, Mapping[str, float]],
    *,
    nominaux: Mapping[str, Any] | None = None,
    convention_: ConventionArg = None,
) -> dict[str, float]:
    """Les valeurs **tirées** de la cible : ``{"Biais": …, "FE": …}``.

    Les mêmes poids que :func:`loi_derivee`, appliqués cette fois aux valeurs
    d'un tirage plutôt qu'aux lois. C'est ce qui permet à une figure de tirage
    de situer la cible sur sa loi dérivée, et au contrôle modèle / calcul de
    porter aussi sur la relation elle-même.
    """
    manquants = sorted(nom for nom in relation.sources if nom not in tirage)
    if manquants:
        raise ValueError(
            f"la relation « {relation} » demande le tirage de {manquants}, "
            f"absent(s) du tirage ({sorted(tirage)})"
        )
    poids_biais, poids_fe, decalage_fe = poids_derives(
        relation, nominaux=nominaux, convention_=convention_
    )
    return {
        COMPOSANTES[0]: sum(
            poids_biais[nom] * float(tirage[nom][COMPOSANTES[0]]) for nom in relation.sources
        ),
        COMPOSANTES[1]: decalage_fe
        + sum(poids_fe[nom] * float(tirage[nom][COMPOSANTES[1]]) for nom in relation.sources),
    }


def lois_avec_relations(
    lois: JeuDeLois,
    relations: RelationArg,
    *,
    nominaux: Mapping[str, Any] | None = None,
    convention_: ConventionArg = None,
) -> JeuDeLois:
    """Le jeu de lois, **augmenté** des coefficients que les relations déduisent.

    Les lois d'origine sont conservées telles quelles ; les cibles sont
    ajoutées à la suite, dans l'ordre des relations. Une cible qui porte déjà
    ses propres lois est refusée : deux lois pour un même coefficient, l'une
    déclarée et l'autre dérivée, ne peuvent pas être toutes deux la bonne.
    """
    lues = charger_relations(relations)
    if not lues:
        return lois

    augmentees = dict(lois)
    for cible, relation in lues.items():
        if cible in lois:
            raise ValueError(
                f"{cible!r} a déjà ses lois dans la table : la relation « {relation} » "
                "en donnerait de secondes. Retirer l'une des deux."
            )
        augmentees[cible] = loi_derivee(relation, lois, nominaux=nominaux, convention_=convention_)
    return JeuDeLois(augmentees, correlation=None)


def _poids(
    relation: Relation,
    reconstruction: Convention,
    nominaux: Mapping[str, Any] | None,
) -> tuple[dict[str, float], dict[str, float], float]:
    """Les poids de chaque composante, et le décalage du facteur d'échelle.

    Deux chemins, et le second n'est qu'un raccourci du premier :

    1. **avec les nominaux** — la voie générale. La décomposition affine de la
       convention est mesurée en chaque nominal de source et au nominal de la
       cible, et les poids en découlent (voir l'en-tête du module) ;
    2. **sans nominaux** — réservé à ``cible = a·source``. Les poids valent
       alors ``a`` pour le biais et ``1`` pour le facteur d'échelle, ce qui est
       *vérifié* sur la convention avant d'être employé.

    Dans les deux cas la dérivation obtenue est confrontée à la relation elle-
    même sur quelques tirages fictifs : une convention qui ne se prêterait pas
    à ce découpage est refusée, et non dérivée de travers.
    """
    if nominaux is None or any(nom not in nominaux for nom in relation.sources):
        return _poids_sans_nominaux(relation, reconstruction, nominaux)

    valeurs = {
        nom: float(np.asarray(nominaux[nom], dtype=float).reshape(-1)[0])
        for nom in relation.sources
    }
    cible = float(np.asarray(relation.appliquer(valeurs), dtype=float).reshape(-1)[0])

    a_cible, b_cible, _ = _decomposition(reconstruction, cible, relation)
    if a_cible == 0.0 or b_cible == 0.0:
        raise ValueError(
            f"la convention {reconstruction.nom!r} annule une composante au nominal "
            f"{cible:g} de {relation.cible!r} : la relation « {relation} » ne s'y dérive pas"
        )

    poids_biais: dict[str, float] = {}
    poids_fe: dict[str, float] = {}
    for nom, facteur in relation.termes:
        a_source, b_source, _ = _decomposition(reconstruction, valeurs[nom], relation)
        poids_biais[nom] = facteur * a_source / a_cible
        poids_fe[nom] = facteur * b_source / b_cible

    neutre = _facteur_neutre_de(reconstruction)
    decalage_fe = _sans_epsilon(neutre * (1.0 - sum(poids_fe.values())), neutre)

    _verifier(relation, reconstruction, valeurs, cible, poids_biais, poids_fe, decalage_fe)
    return poids_biais, poids_fe, decalage_fe


def _sans_epsilon(valeur: float, echelle: float) -> float:
    """Ramène à zéro un décalage qui n'est que de l'erreur d'arrondi.

    ``1 - (0.7097 + 0.2903)`` ne fait pas zéro en virgule flottante, et ce
    ``1.1e-16`` finirait écrit dans la boîte de paramètres d'une figure, où il
    ressemble à un décalage voulu.
    """
    return 0.0 if abs(valeur) <= 1e-12 * (1.0 + abs(echelle)) else valeur


def _poids_sans_nominaux(
    relation: Relation,
    reconstruction: Convention,
    nominaux: Mapping[str, Any] | None,
) -> tuple[dict[str, float], dict[str, float], float]:
    """Le raccourci sans nominaux, et son refus quand il ne s'applique pas."""
    if not relation.est_simple:
        absents = sorted(nom for nom in relation.sources if nominaux is None or nom not in nominaux)
        raise ValueError(
            f"la relation « {relation} » demande les valeurs nominales de {absents} : "
            "le facteur d'échelle multiplie le nominal, donc les poids sont des parts "
            "et une part dépend de ce que pèse chaque contribution. "
            "Passer nominaux={…}, ou une référence au parcours qui les y lira."
        )

    nom, facteur = relation.termes[0]
    # Le raccourci suppose que multiplier un coefficient par a revient à
    # multiplier son biais par a en laissant son facteur d'échelle intact. Vrai
    # des trois conventions livrées ; vérifié plutôt que supposé.
    for nominal in (0.7, -1.3):
        for biais, fe in ((0.03, 1.1), (-0.02, 0.8)):
            attendu = facteur * float(
                np.asarray(reconstruction(nominal, biais, fe), dtype=float).reshape(-1)[0]
            )
            obtenu = float(
                np.asarray(
                    reconstruction(facteur * nominal, facteur * biais, fe), dtype=float
                ).reshape(-1)[0]
            )
            echelle = 1.0 + abs(attendu)
            if abs(obtenu - attendu) > _TOL * echelle:
                raise ValueError(
                    f"la convention {reconstruction.nom!r} ne se met pas à l'échelle : "
                    f"la relation « {relation} » ne se dérive qu'avec les valeurs "
                    "nominales. Passer nominaux={…}."
                )
    return {nom: facteur}, {nom: 1.0}, 0.0


def _decomposition(
    reconstruction: Convention,
    nominal: float,
    relation: Relation,
) -> tuple[float, float, float]:
    """``(α, β, cst)`` de la convention en un nominal, ou un refus explicite."""
    from .combinaison import decomposition_affine

    poids = decomposition_affine(reconstruction, nominal)
    if poids is None:
        raise ValueError(
            f"la convention {reconstruction.nom!r} n'est pas affine en (biais, FE) : "
            f"la relation « {relation} » ne s'en dérive pas. Donner les lois de "
            f"{relation.cible!r} à la main."
        )
    return poids


def _facteur_neutre_de(reconstruction: Convention) -> float:
    """Le facteur d'échelle qui ne disperse rien, résolu depuis la convention."""
    from .tirage import _facteur_neutre

    return _facteur_neutre(reconstruction)


def _verifier(
    relation: Relation,
    reconstruction: Convention,
    valeurs: Mapping[str, float],
    cible: float,
    poids_biais: Mapping[str, float],
    poids_fe: Mapping[str, float],
    decalage_fe: float,
) -> None:
    """Confronte la dérivation à la relation sur quelques tirages fictifs.

    Le découpage en (biais, facteur d'échelle) n'est exact que si la convention
    est affine en ces deux composantes — ce que la décomposition a déjà mesuré
    — mais le vérifier de bout en bout coûte six évaluations et ferme la porte
    aux conventions qui passeraient le premier contrôle sans passer celui-ci.
    """
    neutre = _facteur_neutre_de(reconstruction)
    essais = (
        {
            nom: (0.01 * (indice + 1), neutre + 0.05 * (indice + 1))
            for indice, nom in enumerate(relation.sources)
        },
        {
            nom: (-0.02 * (indice + 1), neutre - 0.03 * (indice + 1))
            for indice, nom in enumerate(relation.sources)
        },
    )
    for essai in essais:
        attendu = relation.constante + sum(
            facteur
            * float(
                np.asarray(
                    reconstruction(valeurs[nom], essai[nom][0], essai[nom][1]), dtype=float
                ).reshape(-1)[0]
            )
            for nom, facteur in relation.termes
        )
        biais = sum(poids_biais[nom] * essai[nom][0] for nom in relation.sources)
        fe = decalage_fe + sum(poids_fe[nom] * essai[nom][1] for nom in relation.sources)
        obtenu = float(np.asarray(reconstruction(cible, biais, fe), dtype=float).reshape(-1)[0])
        echelle = 1.0 + abs(attendu)
        if abs(obtenu - attendu) > 1e-8 * echelle:
            raise ValueError(
                f"la dérivation de « {relation} » ne redonne pas la relation sous la "
                f"convention {reconstruction.nom!r} ({obtenu:.6g} au lieu de {attendu:.6g}) : "
                f"donner les lois de {relation.cible!r} à la main."
            )
