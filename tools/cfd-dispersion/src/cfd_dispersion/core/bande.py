"""Propager une dispersion le long d'un balayage.

:mod:`cfd_dispersion.core.tirage` répond à « comment se distribue *une*
grandeur ? ». Ce module répond à la question qui atteint un livrable : « à quoi
ressemble ma **polaire** une fois les coefficients dispersés ? ». Il tire la
dispersion en chaque point du balayage, réduit le nuage à une enveloppe, et
garde le nuage complet pour qu'on puisse en tirer autre chose ensuite.

Corrélé ou indépendant
----------------------
La distinction compte plus que le choix de l'intervalle, et se tromper dessus
est la façon classique de publier une mauvaise enveloppe.

Une erreur de recalage sur un coefficient est normalement *la même erreur* en
tout point du balayage : une réalisation décale ou incline la courbe entière,
de façon cohérente. C'est ``correle=True``, le défaut, et ses réalisations
individuelles sont des courbes lisses.

Tirer au contraire une erreur indépendante par point — ``correle=False`` —
modélise un bruit point à point, un résidu mal convergé par exemple. Ses
réalisations sont hachées.

L'*enveloppe* sort semblable dans les deux cas ; ce qui change, c'est ce
qu'il y a dedans. Seule l'enveloppe corrélée se lit « la vraie courbe est
là-dedans », qui est pourtant l'affirmation qu'on croit faire.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Union

import numpy as np

from .alea import graine_temporaire
from .convention import Convention, ConventionArg, convention
from .loi import LoiDispersion
from .lois import LoiCoefficient

__all__ = [
    "INTERVALLES",
    "BandeDispersion",
    "ResumeDispersion",
    "bande_depuis_courbes",
    "bande_depuis_loi",
    "bande_depuis_points",
    "resume_dispersion",
]

#: Les réductions de nuage disponibles.
INTERVALLES: tuple[str, ...] = ("percentile", "sigma", "minmax")

#: Effectif Monte-Carlo par défaut.
N_DEFAUT = 20_000

Intervalle = str
Reel = Union[float, int]


# ---------------------------------------------------------------------------
# Le résultat
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BandeDispersion:
    """Une courbe dispersée : son nominal, sa moyenne, et une enveloppe.

    Attributes
    ----------
    x:
        Abscisse du balayage, forme ``(npts,)``.
    nominal:
        La courbe non dispersée, forme ``(npts,)``.
    moyenne:
        Moyenne empirique en chaque point, forme ``(npts,)``. Elle s'écarte du
        nominal dès qu'une composante est décentrée (``M != 0``) : cet écart
        est précisément le biais que l'analyse révèle.
    bas, haut:
        Bornes de l'enveloppe, forme ``(npts,)``.
    echantillons:
        Le nuage complet, forme ``(n, npts)``. La ligne *i* est une
        réalisation de la courbe entière ; le garder permet de re-réduire la
        bande à un autre niveau, ou de tracer des réalisations, sans retirer.
    intervalle:
        ``"percentile"``, ``"sigma"`` ou ``"minmax"``.
    niveau:
        Fraction de couverture pour ``"percentile"``, *k* pour ``"sigma"``,
        sans objet pour ``"minmax"``.
    correle:
        Si un même tirage a été partagé sur tout le balayage.
    convention:
        La relation de reconstruction employée.
    """

    x: np.ndarray
    nominal: np.ndarray
    moyenne: np.ndarray
    bas: np.ndarray
    haut: np.ndarray
    echantillons: np.ndarray
    intervalle: Intervalle
    niveau: float
    correle: bool
    convention: Convention

    @property
    def n_tirages(self) -> int:
        """Nombre de réalisations Monte-Carlo."""
        return int(self.echantillons.shape[0])

    @property
    def ecart_type(self) -> np.ndarray:
        """Écart-type empirique en chaque point, forme ``(npts,)``."""
        return np.std(self.echantillons, axis=0)

    @property
    def demi_largeur(self) -> np.ndarray:
        """Demi-hauteur de l'enveloppe en chaque point, forme ``(npts,)``."""
        return np.asarray(0.5 * (self.haut - self.bas), dtype=float)

    @property
    def label(self) -> str:
        """Description lisible de l'enveloppe : ``"95 %"``, ``"±2σ"``, ``"min/max"``."""
        if self.intervalle == "minmax":
            return "min/max"
        if self.intervalle == "sigma":
            k = int(self.niveau) if float(self.niveau).is_integer() else self.niveau
            return f"±{k}σ"
        return f"{self.niveau * 100:.3g} %"

    def reduire(
        self,
        *,
        intervalle: Intervalle | None = None,
        niveau: float | None = None,
    ) -> BandeDispersion:
        """Rend le même nuage réduit à une autre enveloppe.

        Bon marché : rien n'est retiré, seule la réduction est refaite. Sert à
        montrer un ±1σ et un ±3σ de la même analyse sans la payer deux fois.
        """
        intervalle = intervalle if intervalle is not None else self.intervalle
        if niveau is None:
            niveau = self.niveau if intervalle == self.intervalle else _niveau_defaut(intervalle)
        bas, haut = _reduire(self.echantillons, intervalle, niveau)
        return BandeDispersion(
            x=self.x,
            nominal=self.nominal,
            moyenne=self.moyenne,
            bas=bas,
            haut=haut,
            echantillons=self.echantillons,
            intervalle=intervalle,
            niveau=niveau,
            correle=self.correle,
            convention=self.convention,
        )

    def enveloppe_sigma(self, k: float) -> tuple[np.ndarray, np.ndarray]:
        """Les courbes ``moyenne ∓ k·σ``, sans reconstruire une bande entière.

        C'est ce qui alimente les lignes ±1σ, ±2σ, ±3σ d'une polaire dispersée.

        Raises
        ------
        ValueError
            Si *k* n'est pas strictement positif.
        """
        if k <= 0.0:
            raise ValueError(f"k doit être strictement positif, reçu {k!r}")
        demi = k * self.ecart_type
        return self.moyenne - demi, self.moyenne + demi


# ---------------------------------------------------------------------------
# Réduction du nuage
# ---------------------------------------------------------------------------


def _niveau_defaut(intervalle: Intervalle) -> float:
    return {"percentile": 0.95, "sigma": 2.0, "minmax": 1.0}[intervalle]


def _reduire(
    echantillons: np.ndarray, intervalle: Intervalle, niveau: float
) -> tuple[np.ndarray, np.ndarray]:
    """Réduit un nuage ``(n, npts)`` à des bornes ``(bas, haut)``."""
    if intervalle == "minmax":
        return np.min(echantillons, axis=0), np.max(echantillons, axis=0)

    if intervalle == "percentile":
        if not 0.0 < niveau < 1.0:
            raise ValueError(f"la couverture doit être dans (0, 1), reçu {niveau!r}")
        queue = 50.0 * (1.0 - niveau)
        bas, haut = np.percentile(echantillons, [queue, 100.0 - queue], axis=0)
        return bas, haut

    if intervalle == "sigma":
        if niveau <= 0.0:
            raise ValueError(f"k doit être strictement positif, reçu {niveau!r}")
        moyenne = np.mean(echantillons, axis=0)
        demi = niveau * np.std(echantillons, axis=0)
        return moyenne - demi, moyenne + demi

    raise ValueError(f"intervalle inconnu : {intervalle!r} ; attendu l'un de {list(INTERVALLES)}")


def _resoudre_niveau(intervalle: Intervalle, couverture: float | None, k: float | None) -> float:
    """Choisit le niveau de réduction, en refusant le réglage qui ne s'applique pas."""
    if intervalle == "minmax":
        if couverture is not None or k is not None:
            raise ValueError("intervalle='minmax' n'a pas de niveau ; retirer couverture= et k=")
        return 1.0
    if intervalle == "percentile":
        if k is not None:
            raise ValueError("k s'applique à intervalle='sigma' ; passer couverture= à la place")
        return couverture if couverture is not None else 0.95
    if intervalle == "sigma":
        if couverture is not None:
            raise ValueError(
                "couverture s'applique à intervalle='percentile' ; passer k= à la place"
            )
        return k if k is not None else 2.0
    raise ValueError(f"intervalle inconnu : {intervalle!r} ; attendu l'un de {list(INTERVALLES)}")


def _construire(
    x: np.ndarray,
    nominal: np.ndarray,
    echantillons: np.ndarray,
    *,
    intervalle: Intervalle,
    niveau: float,
    correle: bool,
    relation: Convention,
) -> BandeDispersion:
    bas, haut = _reduire(echantillons, intervalle, niveau)
    return BandeDispersion(
        x=x,
        nominal=nominal,
        moyenne=np.mean(echantillons, axis=0),
        bas=bas,
        haut=haut,
        echantillons=echantillons,
        intervalle=intervalle,
        niveau=niveau,
        correle=correle,
        convention=relation,
    )


def _comme_balayage(x: object, nominal: object) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=float)
    nominal = np.asarray(nominal, dtype=float)
    if x.ndim != 1:
        raise ValueError(f"x doit être 1-D, reçu la forme {x.shape}")
    if nominal.shape != x.shape:
        raise ValueError(
            f"nominal porte {nominal.shape} valeurs pour {x.shape} abscisses ; "
            "les deux doivent correspondre"
        )
    return x, nominal


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------


def bande_depuis_loi(
    x: object,
    nominal: object,
    *,
    loi: LoiCoefficient | None = None,
    biais: LoiDispersion | None = None,
    fe: LoiDispersion | None = None,
    convention_: ConventionArg = None,
    n: int = N_DEFAUT,
    intervalle: Intervalle = "percentile",
    couverture: float | None = None,
    k: float | None = None,
    correle: bool = True,
    graine: int | None = None,
    methode: str = "mc",
) -> BandeDispersion:
    """Propage une loi de coefficient le long de tout un balayage.

    Le modèle de dispersion est celui de la convention retenue, appliqué point
    par point à un nominal *variable* ::

        echantillon[i, j] = convention(nominal[j], biais[i], fe[i])

    l'indice de tirage *i* étant partagé sur tout le balayage quand
    ``correle=True`` (cas physique usuel, et défaut — voir la docstring du
    module).

    Parameters
    ----------
    x, nominal:
        La courbe non dispersée. Toutes deux 1-D et de même longueur.
    loi:
        La :class:`~cfd_dispersion.core.lois.LoiCoefficient` du coefficient.
        Alternativement, passer *biais* et *fe* séparément.
    biais, fe:
        Les deux composantes, si l'on n'a pas de ``LoiCoefficient`` sous la main.
    convention_:
        La relation de reconstruction. Défaut : ``"lineaire"``.
    n:
        Effectif Monte-Carlo.
    intervalle:
        ``"percentile"`` (défaut) réduit le nuage à un intervalle de
        couverture ; ``"sigma"`` à moyenne ± *k*·σ ; ``"minmax"`` à l'enveloppe
        extrême. Préférer les percentiles pour les composantes uniformes ou
        tronquées, dont les queues ne sont pas gaussiennes.
    couverture:
        Fraction de couverture pour ``intervalle="percentile"``. Défaut ``0.95``.
    k:
        Multiple de σ pour ``intervalle="sigma"``. Défaut ``2.0``.
    correle:
        Partager un même tirage sur tout le balayage.
    graine:
        Graine posée le temps du tirage, l'état global étant restauré ensuite.
    methode:
        Plan d'échantillonnage : ``"mc"``, ``"lhs"`` ou ``"sobol"``.

    Returns
    -------
    BandeDispersion
    """
    if loi is None and (biais is None or fe is None):
        raise ValueError("passer soit loi=, soit biais= et fe=")
    if loi is not None and (biais is not None or fe is not None):
        raise ValueError("passer loi= ou (biais=, fe=), pas les deux")
    if loi is not None:
        biais, fe = loi.biais, loi.fe
    assert biais is not None and fe is not None

    x, nominal = _comme_balayage(x, nominal)
    relation = convention(convention_)
    niveau = _resoudre_niveau(intervalle, couverture, k)
    npts = nominal.size

    with graine_temporaire(graine):
        if correle:
            b = biais.tirer(n, methode=methode)[:, None]
            f = fe.tirer(n, methode=methode)[:, None]
        else:
            b = biais.tirer(n * npts, methode=methode).reshape(n, npts)
            f = fe.tirer(n * npts, methode=methode).reshape(n, npts)

    echantillons = relation(nominal[None, :], b, f)
    return _construire(
        x,
        nominal,
        echantillons,
        intervalle=intervalle,
        niveau=niveau,
        correle=correle,
        relation=relation,
    )


def bande_depuis_points(
    x: object,
    nominal: object,
    lois: Sequence[LoiCoefficient],
    *,
    convention_: ConventionArg = None,
    n: int = N_DEFAUT,
    intervalle: Intervalle = "percentile",
    couverture: float | None = None,
    k: float | None = None,
    graine: int | None = None,
    methode: str = "mc",
) -> BandeDispersion:
    """Propage une dispersion **propre à chaque point** du balayage.

    À employer quand chaque point porte ses propres lois — un coefficient dont
    l'incertitude croît après le décrochage, ou une table de tolérances par
    point de vol.

    L'échantillonnage est nécessairement **indépendant** d'un point à l'autre :
    les lois diffèrent, il n'y a pas de tirage commun à corréler. Si votre
    incertitude est en réalité une erreur de recalage valant pour tout le
    balayage, c'est :func:`bande_depuis_loi` avec ``correle=True`` qu'il faut —
    cette fonction-ci sous-estimerait de combien la courbe entière peut se
    décaler.

    Parameters
    ----------
    x, nominal:
        La courbe non dispersée, 1-D et de même longueur que *lois*.
    lois:
        Une :class:`~cfd_dispersion.core.lois.LoiCoefficient` par point, dans
        l'ordre de *x*.

    Returns
    -------
    BandeDispersion
    """
    x, nominal = _comme_balayage(x, nominal)
    if len(lois) != x.size:
        raise ValueError(
            f"{len(lois)} loi(s) pour {x.size} abscisses ; les deux doivent correspondre"
        )

    relation = convention(convention_)
    niveau = _resoudre_niveau(intervalle, couverture, k)

    with graine_temporaire(graine):
        colonnes = [
            relation(valeur, loi.biais.tirer(n, methode=methode), loi.fe.tirer(n, methode=methode))
            for valeur, loi in zip(nominal, lois)
        ]

    echantillons = np.column_stack(colonnes)
    return _construire(
        x,
        nominal,
        echantillons,
        intervalle=intervalle,
        niveau=niveau,
        correle=False,
        relation=relation,
    )


def bande_depuis_courbes(
    x: object,
    nominal: object,
    courbes: object,
    *,
    intervalle: Intervalle = "minmax",
    couverture: float | None = None,
    k: float | None = None,
    convention_: ConventionArg = None,
    correle: bool = True,
) -> BandeDispersion:
    """Fabrique une bande à partir de courbes **déjà obtenues**, sans retirer.

    Les deux autres constructeurs tirent : celui-ci prend le nuage tel quel.
    C'est ce qu'il faut quand les courbes viennent du modèle — la sortie de
    :func:`cfd_dispersion.courbes_par_tirage` — et non d'un tirage du paquet.

    Parameters
    ----------
    x:
        L'abscisse du balayage, forme ``(npts,)``.
    nominal:
        La courbe non dispersée, forme ``(npts,)``.
    courbes:
        Le nuage, forme ``(n_tirages, npts)``.
    intervalle:
        ``"minmax"`` (défaut), ``"percentile"`` ou ``"sigma"``.
    couverture, k:
        Le niveau, selon l'intervalle choisi.
    convention_:
        La relation employée, pour mémoire — elle ne sert qu'à décrire la
        bande, les courbes étant déjà reconstruites.
    correle:
        Si un même tirage a été partagé sur tout le balayage. Vrai par défaut :
        c'est le cas d'un modèle appelé en croisé.

    Returns
    -------
    BandeDispersion

    Raises
    ------
    ValueError
        Si les formes ne concordent pas, ou si le niveau ne s'applique pas à
        l'intervalle demandé.
    """
    abscisse = np.asarray(x, dtype=float)
    courbe = np.asarray(nominal, dtype=float)
    nuage = np.atleast_2d(np.asarray(courbes, dtype=float))

    if abscisse.ndim != 1:
        raise ValueError(f"x doit être 1-D, reçu la forme {abscisse.shape}")
    if courbe.shape != abscisse.shape:
        raise ValueError(
            f"nominal porte {courbe.shape} valeurs pour {abscisse.shape} abscisses ; "
            "les deux doivent correspondre"
        )
    if nuage.shape[1] != abscisse.size:
        raise ValueError(
            f"les courbes ont {nuage.shape[1]} colonnes pour {abscisse.size} abscisses ; "
            "les deux doivent correspondre"
        )

    return _construire(
        abscisse,
        courbe,
        nuage,
        intervalle=intervalle,
        niveau=_resoudre_niveau(intervalle, couverture, k),
        correle=correle,
        relation=convention(convention_),
    )


@dataclass(frozen=True)
class ResumeDispersion:
    """Ce qu'une bande donne à retenir, en quatre nombres.

    Une enveloppe se regarde ; elle se raconte mal. Ces quatre nombres sont ce
    qu'on recopie dans un compte rendu : combien de tirages, de combien le
    coefficient peut bouger, où il bouge le plus, et si la dispersion le
    déplace en moyenne.

    Attributes
    ----------
    n_tirages, npts:
        L'effectif, et la longueur du balayage.
    enveloppe:
        La plus grande hauteur d'enveloppe rencontrée le long du balayage.
    enveloppe_x:
        L'abscisse où elle est atteinte — la question qui suit toujours.
    enveloppe_relative:
        La même, en pourcentage du nominal en ce point. None si le nominal y
        est nul.
    sigma:
        Le plus grand écart-type rencontré, et sa version relative.
    ecart_moyen:
        Le plus grand écart entre la moyenne dispersée et le nominal : il est
        nul quand les lois sont centrées, et c'est un biais dès qu'il ne
        l'est pas.
    """

    n_tirages: int
    npts: int
    enveloppe: float
    enveloppe_x: float
    enveloppe_relative: float | None
    sigma: float
    sigma_relative: float | None
    ecart_moyen: float

    @property
    def lignes(self) -> tuple[str, ...]:
        """Le résumé en lignes courtes, pour une boîte de figure."""
        relative = "" if self.enveloppe_relative is None else f" ({self.enveloppe_relative:.2f} %)"
        sigma_relative = "" if self.sigma_relative is None else f" ({self.sigma_relative:.2f} %)"
        return (
            f"enveloppe max {self.enveloppe:.4g}{relative} à x = {self.enveloppe_x:.4g}",
            f"σ max {self.sigma:.3g}{sigma_relative}",
            f"écart moyen/nominal max {self.ecart_moyen:+.3g}",
        )

    @property
    def resume(self) -> str:
        """Le même résumé sur une ligne, pour un terminal."""
        return " · ".join(self.lignes)


def resume_dispersion(bande: BandeDispersion) -> ResumeDispersion:
    """Réduit une bande aux nombres qu'on recopie dans un compte rendu.

    Parameters
    ----------
    bande:
        La bande, théorique ou obtenue.

    Returns
    -------
    ResumeDispersion

    Examples
    --------
    >>> resume_dispersion(bande).resume            # doctest: +SKIP
    'enveloppe max 0.062 (7.30 %) à x = 8 · σ max 0.021 (2.47 %) · …'
    """
    hauteur = np.asarray(bande.haut - bande.bas, dtype=float)
    indice = int(np.argmax(hauteur))
    nominal = float(bande.nominal[indice])

    # Le plus grand écart moyenne/nominal, avec son signe : un biais a un sens.
    ecarts = np.asarray(bande.moyenne - bande.nominal, dtype=float)
    ecart_moyen = float(ecarts[int(np.argmax(np.abs(ecarts)))])

    ecarts_type = np.asarray(bande.ecart_type, dtype=float)
    indice_sigma = int(np.argmax(ecarts_type))
    nominal_sigma = float(bande.nominal[indice_sigma])

    return ResumeDispersion(
        n_tirages=bande.n_tirages,
        npts=int(bande.x.size),
        enveloppe=float(hauteur[indice]),
        enveloppe_x=float(bande.x[indice]),
        enveloppe_relative=(
            None if nominal == 0.0 else 100.0 * float(hauteur[indice]) / abs(nominal)
        ),
        sigma=float(ecarts_type[indice_sigma]),
        sigma_relative=(
            None
            if nominal_sigma == 0.0
            else 100.0 * float(ecarts_type[indice_sigma]) / abs(nominal_sigma)
        ),
        ecart_moyen=ecart_moyen,
    )
