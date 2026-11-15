"""Ce qu'on compare et selon quel critère : la spécification d'un test d'intégration.

Elle se construit depuis des arguments Python (:func:`construire_specification`)
ou depuis un fichier YAML (:func:`specification_depuis_dict`), et refuse tout ce
qui rendrait la comparaison ambiguë : une colonne à la fois entrée et sortie,
une tolérance pour une sortie non déclarée, une clé inconnue (``rtl:`` garderait
silencieusement la tolérance par défaut).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Union

from cfd_validation.core.tolerance import (
    ATOL_DEFAUT,
    ORIGINE_DECLAREE,
    ORIGINE_DEFAUT,
    RTOL_DEFAUT,
    Tolerance,
)

__all__ = [
    "ALIGNEMENTS",
    "ALIGNEMENT_ENTREES",
    "ALIGNEMENT_POSITION",
    "ErreurSpecification",
    "SpecTolerance",
    "Specification",
    "construire_specification",
    "lire_tolerance",
    "specification_depuis_dict",
]

#: Apparier les lignes sur la valeur de leurs entrées (l'ordre peut différer).
ALIGNEMENT_ENTREES = "entrees"
#: Apparier les lignes par leur rang (les entrées sont alors vérifiées ligne à ligne).
ALIGNEMENT_POSITION = "position"
ALIGNEMENTS = (ALIGNEMENT_ENTREES, ALIGNEMENT_POSITION)

#: Ce qu'on accepte pour décrire une tolérance.
SpecTolerance = Union[Tolerance, Mapping[str, Any], "tuple[float, float]"]

_CLES_TOLERANCE = ("rtol", "atol", "justification")
_CLES_FICHIER = (
    "identifiant",
    "description",
    "entrees",
    "sorties",
    "alignement",
    "chiffres_cle",
    "tolerances",
    "metadonnees",
    "renommage_test",
)
_CLES_TOLERANCES = ("defaut", "sorties")


class ErreurSpecification(ValueError):
    """La spécification du test est incohérente ou incomplète."""


@dataclass(frozen=True)
class Specification:
    """Colonnes d'entrée, colonnes de sortie, tolérance de chaque sortie, appariement."""

    entrees: tuple[str, ...]
    sorties: tuple[str, ...]
    tolerances: Mapping[str, Tolerance]
    alignement: str = ALIGNEMENT_ENTREES
    #: Chiffres significatifs auxquels arrondir les entrées avant de les apparier (None : exact).
    chiffres_cle: int | None = None
    renommage_test: Mapping[str, str] = field(default_factory=dict)

    def tolerance(self, sortie: str) -> Tolerance:
        return self.tolerances[sortie]


def _noms(valeur: str | Iterable[str], quoi: str) -> tuple[str, ...]:
    if isinstance(valeur, str):
        noms = tuple(n.strip() for n in valeur.split(",") if n.strip())
    else:
        noms = tuple(valeur)
    if not noms:
        raise ErreurSpecification(f"aucune colonne {quoi} déclarée")
    for n in noms:
        if not isinstance(n, str) or not n:
            raise ErreurSpecification(f"nom de colonne {quoi} invalide : {n!r}")
    doublons = sorted({n for n in noms if noms.count(n) > 1})
    if doublons:
        raise ErreurSpecification(f"colonnes {quoi} déclarées deux fois : {', '.join(doublons)}")
    return noms


def _nombre(valeur: Any, quoi: str) -> float:
    # YAML 1.1 lit « 1e-9 » (sans point) comme une chaîne : on l'accepte.
    if isinstance(valeur, bool):
        raise ErreurSpecification(f"{quoi} doit être un nombre, reçu {valeur!r}")
    try:
        return float(valeur)
    except (TypeError, ValueError):
        raise ErreurSpecification(f"{quoi} doit être un nombre, reçu {valeur!r}") from None


def lire_tolerance(spec: SpecTolerance, *, base: Tolerance, quoi: str) -> Tolerance:
    """Une :class:`Tolerance` depuis un objet, un dict ``{rtol, atol, justification}`` ou ``(rtol, atol)``.

    Les champs absents d'un dict sont pris dans ``base``.
    """
    if isinstance(spec, Tolerance):
        return spec
    if isinstance(spec, Mapping):
        inconnues = sorted(set(spec) - set(_CLES_TOLERANCE))
        if inconnues:
            raise ErreurSpecification(
                f"{quoi} : clé(s) inconnue(s) {', '.join(inconnues)} "
                f"(admises : {', '.join(_CLES_TOLERANCE)})"
            )
        rtol = _nombre(spec["rtol"], f"{quoi}.rtol") if "rtol" in spec else base.rtol
        atol = _nombre(spec["atol"], f"{quoi}.atol") if "atol" in spec else base.atol
        justification = spec.get("justification", base.justification)
        if justification is not None:
            justification = str(justification).strip() or None
    elif isinstance(spec, (tuple, list)) and len(spec) == 2:
        rtol = _nombre(spec[0], f"{quoi}[rtol]")
        atol = _nombre(spec[1], f"{quoi}[atol]")
        justification = base.justification
    else:
        raise ErreurSpecification(
            f"{quoi} : attendu Tolerance, dict {{rtol, atol, justification}} ou (rtol, atol), "
            f"reçu {spec!r}"
        )
    try:
        return Tolerance(rtol=rtol, atol=atol, justification=justification, origine=ORIGINE_DECLAREE)
    except (TypeError, ValueError) as erreur:
        raise ErreurSpecification(f"{quoi} : {erreur}") from None


def construire_specification(
    entrees: str | Iterable[str],
    sorties: str | Iterable[str],
    *,
    tolerances: Mapping[str, SpecTolerance] | None = None,
    rtol: float | None = None,
    atol: float | None = None,
    justification: str | None = None,
    alignement: str = ALIGNEMENT_ENTREES,
    chiffres_cle: int | None = None,
    renommage_test: Mapping[str, str] | None = None,
) -> Specification:
    """Valide et assemble la spécification.

    Parameters
    ----------
    entrees, sorties
        Noms de colonnes (liste, ou chaîne séparée par des virgules).
    tolerances
        Tolérance propre à certaines sorties : ``{"Cm": {"rtol": 1e-6, "justification": "…"}}``.
    rtol, atol, justification
        Tolérance commune des autres sorties. Sans ``rtol`` ni ``atol``, c'est la
        tolérance par défaut, signalée comme telle dans le rapport.
    alignement
        ``"entrees"`` (défaut) : apparier sur la valeur des entrées ;
        ``"position"`` : apparier par rang, entrées vérifiées.
    chiffres_cle
        Arrondir les entrées à ce nombre de chiffres significatifs avant
        appariement — quand l'autre environnement les écrit tronquées.
    renommage_test
        ``{nom dans le test: nom dans la référence}``, appliqué au test d'abord.
    """
    e = _noms(entrees, "d'entrée")
    s = _noms(sorties, "de sortie")
    communes = sorted(set(e) & set(s))
    if communes:
        raise ErreurSpecification(f"colonnes à la fois entrée et sortie : {', '.join(communes)}")
    if alignement not in ALIGNEMENTS:
        raise ErreurSpecification(
            f"alignement inconnu : {alignement!r} (admis : {', '.join(ALIGNEMENTS)})"
        )
    if chiffres_cle is not None and (
        isinstance(chiffres_cle, bool) or not isinstance(chiffres_cle, int) or not 1 <= chiffres_cle <= 17
    ):
        raise ErreurSpecification(f"chiffres_cle doit être un entier de 1 à 17, reçu {chiffres_cle!r}")

    if rtol is None and atol is None:
        commune = Tolerance(RTOL_DEFAUT, ATOL_DEFAUT, justification, origine=ORIGINE_DEFAUT)
    else:
        commune = lire_tolerance(
            {
                "rtol": RTOL_DEFAUT if rtol is None else rtol,
                "atol": ATOL_DEFAUT if atol is None else atol,
                "justification": justification,
            },
            base=Tolerance(),
            quoi="tolérance commune",
        )

    propres = dict(tolerances or {})
    inconnues = sorted(set(propres) - set(s))
    if inconnues:
        raise ErreurSpecification(
            f"tolérance déclarée pour une colonne qui n'est pas une sortie : {', '.join(inconnues)}"
        )
    par_sortie = {
        nom: lire_tolerance(propres[nom], base=commune, quoi=f"tolérance de {nom}")
        if nom in propres
        else commune
        for nom in s
    }

    renommage = dict(renommage_test or {})
    for ancien, nouveau in renommage.items():
        if not isinstance(ancien, str) or not isinstance(nouveau, str):
            raise ErreurSpecification(f"renommage_test : noms attendus, reçu {ancien!r} → {nouveau!r}")
    return Specification(
        entrees=e,
        sorties=s,
        tolerances=par_sortie,
        alignement=alignement,
        chiffres_cle=chiffres_cle,
        renommage_test=renommage,
    )


def specification_depuis_dict(contenu: Mapping[str, Any]) -> tuple[Specification, dict[str, Any]]:
    """Spécification depuis le contenu d'un fichier YAML ; renvoie aussi les champs descriptifs.

    Format ::

        identifiant: INT-01
        description: "Le code intégré au workflow restitue la référence."
        entrees: [Mach, alpha, beta]
        sorties: [CN, CA, Cm]
        alignement: entrees          # ou position
        tolerances:
          defaut: {rtol: 1.0e-9, atol: 1.0e-12, justification: "…"}
          sorties:
            Cm: {rtol: 1.0e-6, justification: "…"}
        metadonnees: {code: "aero v3.2", commit: "abc123"}

    Les champs descriptifs (``identifiant``, ``description``, ``metadonnees``)
    sont renvoyés à part, pour le rapport.
    """
    if not isinstance(contenu, Mapping):
        raise ErreurSpecification("le fichier de configuration doit être un dictionnaire YAML")
    inconnues = sorted(set(contenu) - set(_CLES_FICHIER))
    if inconnues:
        raise ErreurSpecification(
            f"clé(s) inconnue(s) : {', '.join(inconnues)} (admises : {', '.join(_CLES_FICHIER)})"
        )
    for requise in ("entrees", "sorties"):
        if requise not in contenu:
            raise ErreurSpecification(f"clé « {requise} » manquante")
    tol = contenu.get("tolerances") or {}
    if not isinstance(tol, Mapping):
        raise ErreurSpecification("« tolerances » doit être un dictionnaire")
    inconnues = sorted(set(tol) - set(_CLES_TOLERANCES))
    if inconnues:
        raise ErreurSpecification(
            f"tolerances : clé(s) inconnue(s) {', '.join(inconnues)} "
            f"(admises : {', '.join(_CLES_TOLERANCES)})"
        )
    defaut = tol.get("defaut") or {}
    if not isinstance(defaut, Mapping):
        raise ErreurSpecification("tolerances.defaut doit être un dictionnaire {rtol, atol, justification}")
    inconnues = sorted(set(defaut) - set(_CLES_TOLERANCE))
    if inconnues:
        raise ErreurSpecification(
            f"tolerances.defaut : clé(s) inconnue(s) {', '.join(inconnues)} "
            f"(admises : {', '.join(_CLES_TOLERANCE)})"
        )
    spec = construire_specification(
        contenu["entrees"],
        contenu["sorties"],
        tolerances=tol.get("sorties") or None,
        rtol=_nombre(defaut["rtol"], "tolerances.defaut.rtol") if "rtol" in defaut else None,
        atol=_nombre(defaut["atol"], "tolerances.defaut.atol") if "atol" in defaut else None,
        justification=defaut.get("justification"),
        alignement=str(contenu.get("alignement", ALIGNEMENT_ENTREES)),
        chiffres_cle=contenu.get("chiffres_cle"),
        renommage_test=contenu.get("renommage_test"),
    )
    meta = contenu.get("metadonnees") or {}
    if not isinstance(meta, Mapping):
        raise ErreurSpecification("« metadonnees » doit être un dictionnaire")
    descriptif = {
        "identifiant": contenu.get("identifiant"),
        "description": contenu.get("description"),
        "metadonnees": {str(k): str(v) for k, v in meta.items()},
    }
    return spec, descriptif
