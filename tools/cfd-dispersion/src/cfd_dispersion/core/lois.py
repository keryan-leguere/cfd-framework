"""Lecture d'une table de lois ``{coefficient: {Biais_*, FE_*}}``.

C'est le point d'entrée du paquet : la table telle que vous l'écrivez ::

    DICT_DISP_LAWS = {
        "Cm_alpha": {
            "Biais_Type": 5, "Biais_M": 0.0, "Biais_ET": 0.015,
            "FE_Type":    6, "FE_M":    0.0, "FE_ET":    0.10,
        },
        ...
    }

    lois = charger_lois(DICT_DISP_LAWS)

Chaque coefficient porte deux composantes indépendantes — un biais additif et
un facteur d'échelle — décrites par un type, une moyenne ``M`` et une
demi-étendue ``ET`` (voir :mod:`cfd_dispersion.core.loi` : ``ET`` n'est **pas**
un écart-type).

Indépendance
------------
Sans argument ``correlation``, les composantes sont tirées indépendamment les
unes des autres. C'est presque toujours ce qu'on veut, et presque jamais ce
qu'on a vérifié — deux coefficients issus du même recalage partagent une
erreur. L'hypothèse étant invisible sur une figure, elle est rendue explicite :
:attr:`JeuDeLois.independantes` est reportée dans chaque boîte de paramètres.

Pour la lever, passer une matrice ou un dictionnaire de corrélations ::

    lois = charger_lois(DICT, correlation={("Cm_alpha", "Cn_beta"): 0.6})

qui construit une ``ot.JointDistribution`` munie d'une copule normale.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union

import openturns as ot

from .loi import LoiDispersion

__all__ = [
    "CLES_ATTENDUES",
    "COMPOSANTES",
    "JeuDeLois",
    "LoiCoefficient",
    "charger_lois",
    "charger_lois_yaml",
]

#: Les deux composantes d'un coefficient, dans l'ordre où elles sont présentées.
COMPOSANTES: tuple[str, ...] = ("Biais", "FE")

#: Les six clés attendues pour chaque coefficient.
CLES_ATTENDUES: tuple[str, ...] = (
    "Biais_Type",
    "Biais_M",
    "Biais_ET",
    "FE_Type",
    "FE_M",
    "FE_ET",
)

Correlation = Union[Mapping[tuple[str, str], float], Sequence[Sequence[float]], None]


@dataclass(frozen=True)
class LoiCoefficient:
    """Les deux lois d'un coefficient : son biais et son facteur d'échelle."""

    nom: str
    biais: LoiDispersion
    fe: LoiDispersion

    def composante(self, nom: str) -> LoiDispersion:
        """Retourne la loi d'une composante, par son nom (``"Biais"``/``"FE"``)."""
        if nom == "Biais":
            return self.biais
        if nom == "FE":
            return self.fe
        raise ValueError(f"composante inconnue : {nom!r} ; attendu l'une de {list(COMPOSANTES)}")

    def __iter__(self) -> Iterator[tuple[str, LoiDispersion]]:
        """Itère ``("Biais", loi)`` puis ``("FE", loi)``."""
        yield "Biais", self.biais
        yield "FE", self.fe

    @property
    def resume(self) -> str:
        """Description compacte, pour une légende ou une boîte de paramètres."""
        return (
            f"Biais {self.biais.label} M={self.biais.M:g} ET={self.biais.ET:g} · "
            f"FE {self.fe.label} M={self.fe.M:g} ET={self.fe.ET:g}"
        )


class JeuDeLois(Mapping[str, LoiCoefficient]):
    """Un ensemble de lois, indexé par nom de coefficient.

    Se comporte comme un dictionnaire ordonné — l'ordre est celui de la table
    d'origine, pour que figures et tableaux suivent l'ordre que vous avez
    écrit — et porte en plus l'éventuelle structure de corrélation.
    """

    def __init__(
        self,
        lois: Mapping[str, LoiCoefficient],
        *,
        correlation: Correlation = None,
    ) -> None:
        self._lois: dict[str, LoiCoefficient] = dict(lois)
        self._correlation = correlation

    # -- protocole Mapping ---------------------------------------------

    def __getitem__(self, cle: str) -> LoiCoefficient:
        try:
            return self._lois[cle]
        except KeyError:
            raise KeyError(
                f"coefficient inconnu : {cle!r} ; la table en contient {sorted(self._lois)}"
            ) from None

    def __iter__(self) -> Iterator[str]:
        return iter(self._lois)

    def __len__(self) -> int:
        return len(self._lois)

    def __repr__(self) -> str:
        return f"JeuDeLois({list(self._lois)!r}, independantes={self.independantes})"

    # -- structure de dépendance ---------------------------------------

    @property
    def independantes(self) -> bool:
        """Vrai si aucune corrélation n'a été déclarée entre composantes."""
        return self._correlation is None

    @property
    def colonnes(self) -> tuple[str, ...]:
        """Les noms de colonnes d'un lot tiré : ``("<coeff>_Biais", "<coeff>_FE", …)``."""
        return tuple(f"{coeff}_{composante}" for coeff in self._lois for composante in COMPOSANTES)

    def composantes(self) -> tuple[tuple[str, str, LoiDispersion], ...]:
        """Aplatit le jeu en ``(coefficient, composante, loi)``, dans l'ordre."""
        return tuple(
            (coeff, nom, loi) for coeff, loi_coeff in self._lois.items() for nom, loi in loi_coeff
        )

    def distribution_jointe(self) -> ot.Distribution:
        """La loi jointe de toutes les composantes, dans l'ordre de :attr:`colonnes`.

        Sans corrélation déclarée, c'est une ``JointDistribution`` à copule
        indépendante — construite quand même, car c'est elle qui permet les
        plans LHS et Sobol sur l'ensemble des composantes à la fois, là où
        ils apportent réellement quelque chose.
        """
        marginales = [loi.distribution for _, _, loi in self.composantes()]
        if self._correlation is None:
            return ot.JointDistribution(marginales)

        matrice = self._matrice_correlation()
        try:
            copule = ot.NormalCopula(matrice)
        except Exception as erreur:
            raise ValueError(
                "la matrice de corrélation demandée n'est pas définie positive, "
                "donc aucune loi jointe ne la réalise : "
                f"{self._decrire_correlation()}. Vérifier que les corrélations "
                "croisées ne dépassent pas ce que les corrélations internes "
                f"autorisent (détail OpenTURNS : {erreur})"
            ) from erreur
        return ot.JointDistribution(marginales, copule)

    def _decrire_correlation(self) -> str:
        """Rend la corrélation demandée lisible dans un message d'erreur."""
        noms = [f"{coeff}_{comp}" for coeff, comp, _ in self.composantes()]
        matrice = self._matrice_correlation()
        paires = [
            f"({noms[i]}, {noms[j]}) = {matrice[i, j]:g}"
            for i in range(len(noms))
            for j in range(i + 1, len(noms))
            if matrice[i, j] != 0.0
        ]
        return ", ".join(paires) if paires else "aucune paire non nulle"

    def _matrice_correlation(self) -> ot.CorrelationMatrix:
        """Construit la matrice de corrélation des composantes."""
        composantes = self.composantes()
        noms = [f"{coeff}_{comp}" for coeff, comp, _ in composantes]
        dim = len(noms)
        matrice = ot.CorrelationMatrix(dim)

        correlation = self._correlation
        if correlation is None:  # pragma: no cover - garanti par l'appelant
            return matrice

        if isinstance(correlation, Mapping):
            index = {nom: i for i, nom in enumerate(noms)}
            for cle, rho in correlation.items():
                a, b = cle
                for ia, ib in _paires_ciblees(str(a), str(b), index):
                    if ia == ib:
                        continue
                    _verifier_rho(rho, noms[ia], noms[ib])
                    matrice[ia, ib] = float(rho)
            return matrice

        lignes = [list(ligne) for ligne in correlation]
        if len(lignes) != dim or any(len(ligne) != dim for ligne in lignes):
            raise ValueError(
                f"la matrice de corrélation doit être {dim}×{dim} "
                f"(une entrée par composante : {noms}), reçu {len(lignes)} ligne(s)"
            )
        for i in range(dim):
            for j in range(i + 1, dim):
                _verifier_rho(lignes[i][j], noms[i], noms[j])
                matrice[i, j] = float(lignes[i][j])
        return matrice


def _resoudre(nom: str, index: Mapping[str, int]) -> tuple[dict[str, int], bool]:
    """Résout un nom en ``({composante: indice}, explicite)``.

    *explicite* dit si le nom désignait une composante précise
    (``"Cm_alpha_Biais"``) plutôt qu'un coefficient entier (``"Cm_alpha"``).
    """
    if nom in index:
        return {nom.rsplit("_", 1)[1]: index[nom]}, True

    trouve = {n.rsplit("_", 1)[1]: i for n, i in index.items() if n.rsplit("_", 1)[0] == nom}
    if not trouve:
        raise ValueError(
            f"corrélation portant sur {nom!r}, qui n'est ni un coefficient ni une "
            f"composante de la table ; attendu l'un de {sorted(index)}"
        )
    return trouve, False


def _verifier_rho(rho: object, a: str, b: str) -> None:
    """Refuse une corrélation hors de [-1, 1], en nommant la paire fautive."""
    try:
        valeur = float(rho)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError(f"corrélation ({a}, {b}) : attendu un nombre, reçu {rho!r}") from None
    if not -1.0 <= valeur <= 1.0:
        raise ValueError(f"corrélation ({a}, {b}) = {rho!r} hors de [-1, 1]")


def _paires_ciblees(a: str, b: str, index: Mapping[str, int]) -> list[tuple[int, int]]:
    """Les paires d'indices auxquelles s'applique une corrélation ``(a, b)``.

    Nommer deux **coefficients** corrèle leurs composantes de même nature —
    biais avec biais, FE avec FE — et non les quatre croisements. Ce n'est pas
    une commodité : appliquer un même ρ aux quatre paires en laissant les
    couples internes à zéro produit une matrice non définie positive dès deux
    coefficients, qu'aucune loi jointe ne réalise. La règle retenue est aussi
    la lecture physique : deux coefficients issus du même recalage partagent
    l'erreur de recalage, pas le lien entre le biais de l'un et l'échelle de
    l'autre.

    Nommer explicitement les deux composantes (``"CN_Biais"``, ``"CA_FE"``)
    cible cette seule paire, croisée ou non.
    """
    cibles_a, explicite_a = _resoudre(a, index)
    cibles_b, explicite_b = _resoudre(b, index)

    if explicite_a and explicite_b:
        (ia,), (ib,) = cibles_a.values(), cibles_b.values()
        return [(ia, ib)]

    communes = sorted(set(cibles_a) & set(cibles_b))
    if not communes:
        raise ValueError(
            f"corrélation ({a!r}, {b!r}) : aucune composante de même nature en commun ; "
            "nommer explicitement les deux composantes pour croiser un biais et un FE"
        )
    return [(cibles_a[comp], cibles_b[comp]) for comp in communes]


def charger_lois(
    table: Mapping[str, Mapping[str, Any]], *, correlation: Correlation = None
) -> JeuDeLois:
    """Construit un :class:`JeuDeLois` depuis une table ``{coeff: {…}}``.

    Parameters
    ----------
    table:
        Un dictionnaire par coefficient, portant les six clés
        :data:`CLES_ATTENDUES`.
    correlation:
        Optionnel. Soit une matrice pleine sur les composantes (dans l'ordre de
        :attr:`JeuDeLois.colonnes`), soit un dictionnaire ``{(a, b): rho}`` où
        *a* et *b* désignent une composante (``"Cm_alpha_Biais"``) ou un
        coefficient entier (``"Cm_alpha"``, ses deux composantes).

    Raises
    ------
    ValueError
        Table vide, clé manquante ou superflue, valeur non numérique, loi
        invalide. Le message nomme toujours le coefficient **et** la clé.

    Examples
    --------
    >>> lois = charger_lois({"CN": {"Biais_Type": 4, "Biais_M": 0.0, "Biais_ET": 0.01,
    ...                            "FE_Type": 6, "FE_M": 0.0, "FE_ET": 0.05}})
    >>> lois["CN"].fe.label
    'Gaussienne ±2σ'
    """
    if not table:
        raise ValueError("la table de lois est vide")

    lois: dict[str, LoiCoefficient] = {}
    for coeff, specification in table.items():
        lois[coeff] = _lire_coefficient(str(coeff), specification)

    jeu = JeuDeLois(lois, correlation=correlation)
    if correlation is not None:
        # Construit la matrice tout de suite : une corrélation mal écrite doit
        # échouer au chargement, pas mille tirages plus tard.
        jeu.distribution_jointe()
    return jeu


def _lire_coefficient(coeff: str, specification: Mapping[str, Any]) -> LoiCoefficient:
    """Lit les six clés d'un coefficient et en fait un :class:`LoiCoefficient`."""
    if not isinstance(specification, Mapping):
        raise ValueError(
            f"coefficient {coeff!r} : attendu un dictionnaire de six clés, "
            f"reçu un {type(specification).__name__}"
        )

    manquantes = [cle for cle in CLES_ATTENDUES if cle not in specification]
    if manquantes:
        raise ValueError(f"coefficient {coeff!r} : clé(s) manquante(s) {manquantes}")

    superflues = sorted(set(specification) - set(CLES_ATTENDUES))
    if superflues:
        raise ValueError(
            f"coefficient {coeff!r} : clé(s) inconnue(s) {superflues} ; "
            f"attendu exactement {list(CLES_ATTENDUES)}"
        )

    composantes = {}
    for prefixe in COMPOSANTES:
        # `LoiDispersion` valide le triplet mais ne sait pas de quel
        # coefficient il vient : sans ce rattrapage, une table de trente
        # coefficients rendrait « type de loi inconnu : 9 » et rien de plus.
        try:
            composantes[prefixe] = LoiDispersion(
                type_loi=_entier(coeff, f"{prefixe}_Type", specification[f"{prefixe}_Type"]),
                M=_reel(coeff, f"{prefixe}_M", specification[f"{prefixe}_M"]),
                ET=_reel(coeff, f"{prefixe}_ET", specification[f"{prefixe}_ET"]),
            )
        except ValueError as erreur:
            message = str(erreur)
            if message.startswith("coefficient "):
                raise
            raise ValueError(f"coefficient {coeff!r}, {prefixe} : {message}") from None
    return LoiCoefficient(nom=coeff, biais=composantes["Biais"], fe=composantes["FE"])


def _entier(coeff: str, cle: str, valeur: Any) -> int:
    try:
        entier = int(valeur)
    except (TypeError, ValueError):
        raise ValueError(
            f"coefficient {coeff!r}, clé {cle!r} : attendu un entier, reçu {valeur!r}"
        ) from None
    if entier != valeur:
        raise ValueError(f"coefficient {coeff!r}, clé {cle!r} : attendu un entier, reçu {valeur!r}")
    return entier


def _reel(coeff: str, cle: str, valeur: Any) -> float:
    try:
        return float(valeur)
    except (TypeError, ValueError):
        raise ValueError(
            f"coefficient {coeff!r}, clé {cle!r} : attendu un nombre, reçu {valeur!r}"
        ) from None


def charger_lois_yaml(chemin: str | Path, *, correlation: Correlation = None) -> JeuDeLois:
    """Charge une table de lois depuis un fichier YAML.

    Le fichier contient la table directement, ou sous une clé ``lois:`` — les
    deux formes sont acceptées, la seconde permettant d'y ranger aussi des
    métadonnées d'étude.
    """
    import yaml

    chemin = Path(chemin)
    if not chemin.is_file():
        raise ValueError(f"fichier de lois introuvable : {chemin}")

    contenu = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    if not isinstance(contenu, Mapping):
        raise ValueError(f"{chemin} : attendu une table de lois, reçu {type(contenu).__name__}")

    table = contenu.get("lois", contenu)
    if not isinstance(table, Mapping):
        raise ValueError(f"{chemin} : la clé 'lois' doit contenir une table de coefficients")

    correlation = correlation if correlation is not None else contenu.get("correlation")
    if isinstance(correlation, Mapping):
        correlation = {_paire(cle): valeur for cle, valeur in correlation.items()}
    return charger_lois(table, correlation=correlation)


def _paire(cle: Any) -> tuple[str, str]:
    """Lit une clé de corrélation YAML : ``"a,b"`` ou ``[a, b]``."""
    if isinstance(cle, str):
        morceaux = [m.strip() for m in cle.split(",")]
    else:
        morceaux = [str(m).strip() for m in cle]
    if len(morceaux) != 2:
        raise ValueError(f"clé de corrélation {cle!r} : attendu deux noms séparés par une virgule")
    return (morceaux[0], morceaux[1])
