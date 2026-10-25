"""YAML case file: one flight condition, one boundary layer, several excrescences.

A case is deliberately flat — there is no nesting beyond one level and no
expression language. Anything a case cannot express is a two-line Python
script against :mod:`cfd_aq.core`.

Unknown keys are **refused**, naming the ones that are accepted. A mistyped
``rayon_sur_h`` silently keeping its default would quietly change the answer
by tens of per cent, which is exactly the sort of error a drag budget never
catches.

Example::

    etude: "Jonction de panneau, extrados voilure"

    ecoulement:
      altitude: 11000          # m ; ou bien temperature + pression
      mach: 0.82               # ou vitesse_conventionnelle / _vraie / _equivalente
      # delta_isa: 15          # journée chaude (demande cfd-atm)
      # type_altitude: pression

    couche_limite:
      distance_bord_attaque: 10.0   # m ; ou bien cf, ou cisaillement_paroi

    surface_reference: 122.6   # m² (facultatif)
    amplification: 1.0         # m_d de Nash-Bradshaw (facultatif)

    asperites:
      - nom: "Marche de capot"
        type: montante
        hauteur: 0.0015
        envergure: 2.4
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from cfd_aq.core.atmosphere import PointAtmospherique, mach_depuis_vitesse
from cfd_aq.core.couche_limite import CoucheLimite, EtatLocal
from cfd_aq.core.marches import TypeAsperite
from cfd_aq.core.trainee import Asperite

__all__ = ["Cas", "CasError", "charger_cas"]

_CLES_RACINE = {
    "etude",
    "ecoulement",
    "couche_limite",
    "surface_reference",
    "amplification",
    "asperites",
}
_CLES_ECOULEMENT = {
    "mach",
    "vitesse_conventionnelle",
    "vitesse_vraie",
    "vitesse_equivalente",
    "altitude",
    "type_altitude",
    "delta_isa",
    "temperature",
    "pression",
    "gamma",
    "r_gaz",
    "prandtl",
}
_CLES_VITESSE = ("mach", "vitesse_conventionnelle", "vitesse_vraie", "vitesse_equivalente")
_CLES_COUCHE_LIMITE = {
    "distance_bord_attaque",
    "cf",
    "cisaillement_paroi",
    "temperature_paroi",
    "epaisseur",
}
_CLES_ASPERITE = {
    "nom",
    "type",
    "hauteur",
    "envergure",
    "t_sur_h",
    "rayon_sur_h",
    "angle_chanfrein",
    "angle_derapage",
}


class CasError(ValueError):
    """The case file is unusable, and the message says which key is at fault."""


@dataclass(frozen=True)
class Cas:
    """A validated case.

    Attributes:
        etude: free-form label for the report.
        etat: local flow state.
        couche_limite: the undisturbed boundary layer.
        asperites: the excrescences, paired with their names.
        surface_reference: S_ref [m²], or None.
        amplification: Nash–Bradshaw m_d, 1 by default.
    """

    etude: str
    etat: EtatLocal
    couche_limite: CoucheLimite
    asperites: list[tuple[str, Asperite]] = field(default_factory=list)
    surface_reference: float | None = None
    amplification: float = 1.0


def _refuser_cles_inconnues(bloc: Mapping[str, Any], admises: set[str], ou: str) -> None:
    inconnues = sorted(set(bloc) - admises)
    if inconnues:
        raise CasError(
            f"clé(s) inconnue(s) dans {ou} : {', '.join(inconnues)}. "
            f"Clés admises : {', '.join(sorted(admises))}."
        )


def _reel(bloc: Mapping[str, Any], cle: str, ou: str, defaut: float | None = None) -> float:
    if cle not in bloc:
        if defaut is None:
            raise CasError(f"clé « {cle} » absente de {ou}.")
        return defaut
    valeur = bloc[cle]
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        raise CasError(f"{ou} : « {cle} » doit être un nombre, reçu {valeur!r}.")
    return float(valeur)


def _lire_ecoulement(bloc: Mapping[str, Any]) -> EtatLocal:
    _refuser_cles_inconnues(bloc, _CLES_ECOULEMENT, "« ecoulement »")
    options = {
        cle: _reel(bloc, cle, "« ecoulement »")
        for cle in ("gamma", "r_gaz", "prandtl")
        if cle in bloc
    }

    vitesses = [cle for cle in _CLES_VITESSE if cle in bloc]
    if len(vitesses) != 1:
        raise CasError(
            "« ecoulement » : donner exactement une vitesse parmi "
            f"{', '.join(_CLES_VITESSE)} (reçu : {', '.join(vitesses) or 'aucune'})."
        )
    vitesse = {vitesses[0]: _reel(bloc, vitesses[0], "« ecoulement »")}

    a_altitude = "altitude" in bloc
    a_statiques = "temperature" in bloc or "pression" in bloc
    if a_altitude and a_statiques:
        raise CasError(
            "« ecoulement » : donner soit « altitude », soit « temperature » et « pression », "
            "pas les deux."
        )

    if a_altitude:
        try:
            return EtatLocal.atmosphere(
                _reel(bloc, "altitude", "« ecoulement »"),
                delta_isa=_reel(bloc, "delta_isa", "« ecoulement »", 0.0),
                type_altitude=str(bloc.get("type_altitude", "geometrique")),
                **vitesse,
                **options,
            )
        except RuntimeError as erreur:
            raise CasError(f"« ecoulement » : {erreur}") from erreur

    if not a_statiques:
        raise CasError(
            "« ecoulement » : il manque « altitude », ou bien « temperature » et « pression »."
        )
    for cle in ("delta_isa", "type_altitude"):
        if cle in bloc:
            raise CasError(
                f"« ecoulement » : « {cle} » n'a de sens qu'avec « altitude », pas avec "
                "« temperature » et « pression » donnés directement."
            )
    point = PointAtmospherique(
        temperature=_reel(bloc, "temperature", "« ecoulement »"),
        pression=_reel(bloc, "pression", "« ecoulement »"),
        modele="imposé",
        source="cas",
    )
    if "mach" in vitesse:
        return EtatLocal.depuis_point(point, vitesse["mach"], **options)
    try:
        mach = mach_depuis_vitesse(point, **vitesse)
    except RuntimeError as erreur:
        raise CasError(f"« ecoulement » : {erreur}") from erreur
    return EtatLocal.depuis_point(point, mach, **options)


def _lire_couche_limite(bloc: Mapping[str, Any], etat: EtatLocal) -> CoucheLimite:
    _refuser_cles_inconnues(bloc, _CLES_COUCHE_LIMITE, "« couche_limite »")
    t_paroi = bloc.get("temperature_paroi")
    t_paroi = None if t_paroi is None else _reel(bloc, "temperature_paroi", "« couche_limite »")
    epaisseur = bloc.get("epaisseur")
    epaisseur = None if epaisseur is None else _reel(bloc, "epaisseur", "« couche_limite »")

    fournis = [c for c in ("cisaillement_paroi", "cf", "distance_bord_attaque") if c in bloc]
    if len(fournis) != 1:
        raise CasError(
            "« couche_limite » : donner exactement une des clés « cisaillement_paroi », "
            f"« cf » ou « distance_bord_attaque » (reçu : {', '.join(fournis) or 'aucune'})."
        )
    cle = fournis[0]
    valeur = _reel(bloc, cle, "« couche_limite »")
    if cle == "cisaillement_paroi":
        return CoucheLimite.depuis_cisaillement(etat, valeur, t_paroi, epaisseur)
    if cle == "cf":
        return CoucheLimite.depuis_cf(etat, valeur, t_paroi, epaisseur)
    return CoucheLimite.plaque_plane(etat, valeur, t_paroi)


def _lire_asperite(bloc: Mapping[str, Any], rang: int) -> tuple[str, Asperite]:
    ou = f"« asperites »[{rang}]"
    _refuser_cles_inconnues(bloc, _CLES_ASPERITE, ou)
    nom = str(bloc.get("nom", f"aspérité {rang + 1}"))
    brut = bloc.get("type")
    if brut is None:
        raise CasError(f"{ou} : clé « type » absente.")
    try:
        type_asperite = TypeAsperite(str(brut).strip().lower())
    except ValueError:
        admis = ", ".join(t.value for t in TypeAsperite)
        raise CasError(f"{ou} : type « {brut} » inconnu. Types admis : {admis}.") from None

    return nom, Asperite(
        type_asperite=type_asperite,
        hauteur=_reel(bloc, "hauteur", ou),
        envergure=_reel(bloc, "envergure", ou),
        t_sur_h=_reel(bloc, "t_sur_h", ou, 1.0),
        rayon_sur_h=_reel(bloc, "rayon_sur_h", ou, 0.0),
        angle_chanfrein=_reel(bloc, "angle_chanfrein", ou, 90.0),
        angle_derapage=_reel(bloc, "angle_derapage", ou, 90.0),
    )


def charger_cas(chemin: Path) -> Cas:
    """Read and validate a YAML case file.

    Raises:
        CasError: the file is missing, is not a mapping, has an unknown key or
            a key of the wrong type. The message names the offending key.
    """
    chemin = Path(chemin)
    try:
        texte = chemin.read_text(encoding="utf-8")
    except OSError as erreur:
        raise CasError(f"impossible de lire « {chemin} » : {erreur}") from erreur

    try:
        brut = yaml.safe_load(texte)
    except yaml.YAMLError as erreur:
        raise CasError(f"YAML invalide dans « {chemin} » : {erreur}") from erreur

    if not isinstance(brut, dict):
        raise CasError(f"« {chemin} » doit contenir un dictionnaire YAML à la racine.")
    _refuser_cles_inconnues(brut, _CLES_RACINE, "la racine du fichier")

    for cle in ("ecoulement", "couche_limite", "asperites"):
        if cle not in brut:
            raise CasError(f"bloc « {cle} » absent du fichier.")
    for cle in ("ecoulement", "couche_limite"):
        if not isinstance(brut[cle], dict):
            raise CasError(f"le bloc « {cle} » doit être un dictionnaire.")

    etat = _lire_ecoulement(brut["ecoulement"])
    couche_limite = _lire_couche_limite(brut["couche_limite"], etat)

    asperites_brutes = brut["asperites"]
    if not isinstance(asperites_brutes, list) or not asperites_brutes:
        raise CasError("« asperites » doit être une liste non vide.")
    asperites = []
    for rang, bloc in enumerate(asperites_brutes):
        if not isinstance(bloc, dict):
            raise CasError(f"« asperites »[{rang}] doit être un dictionnaire.")
        try:
            asperites.append(_lire_asperite(bloc, rang))
        except ValueError as erreur:
            if isinstance(erreur, CasError):
                raise
            raise CasError(f"« asperites »[{rang}] : {erreur}") from erreur

    surface = brut.get("surface_reference")
    surface = None if surface is None else _reel(brut, "surface_reference", "la racine")

    return Cas(
        etude=str(brut.get("etude", chemin.stem)),
        etat=etat,
        couche_limite=couche_limite,
        asperites=asperites,
        surface_reference=surface,
        amplification=_reel(brut, "amplification", "la racine", 1.0),
    )
