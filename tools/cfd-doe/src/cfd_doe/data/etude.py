"""Le fichier d'étude : plages des variables, type de trajectoire, géométrie.

Forme ::

    etude:
      nom: FUSEE_ETUDIANTE
    trajectoire: 6DOF
    geometrie: cruciforme          # ou {type: n_ailettes, n_ailettes: 3}
    repere: auto                   # auto | cartesien | polaire
    limite_braquage: disque        # disque | carre (§7.6)
    variables:                     # degrés ; [bas, haut] ou une valeur
      alpha: [-20, 20]
      beta: [-5, 5]
      DL: [-10, 10]
      DM: [-20, 20]
      DN: [-20, 20]

Toute clé inconnue est **refusée**, avec la liste des clés admises : une faute
de frappe (``limite_braquages``) ne doit pas retomber silencieusement sur la
valeur par défaut.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

from cfd_doe.core.intervalle import Intervalle
from cfd_doe.data.geometries import Geometrie, resoudre_geometrie
from cfd_doe.data.trajectoires import (
    TRAJECTOIRES,
    Trajectoire,
    fabriquer_trajectoire,
    resoudre_trajectoire,
)
from cfd_doe.data.variables import VARIABLES

__all__ = [
    "CLES_ADMISES",
    "LIMITES_BRAQUAGE",
    "REPERES",
    "ErreurEtude",
    "Etude",
    "charger_etude",
    "etude_depuis_dict",
    "lire_plage",
]

CLES_ADMISES: tuple[str, ...] = (
    "etude",
    "trajectoire",
    "geometrie",
    "repere",
    "limite_braquage",
    "variables",
    "trajectoires",
)
REPERES: tuple[str, ...] = ("auto", "cartesien", "polaire")
LIMITES_BRAQUAGE: tuple[str, ...] = ("disque", "carre")

#: Au-delà, (α, β) n'ont plus de sens comme angles de vol (β = asin(v/V)).
ANGLE_MAX = 90.0


class ErreurEtude(ValueError):
    """Fichier ou paramètres d'étude invalides."""


@dataclass(frozen=True)
class Etude:
    """Ce que l'utilisateur demande."""

    nom: str
    trajectoire: Trajectoire
    geometrie: Geometrie
    plages: dict[str, Intervalle] = field(default_factory=dict)
    repere: str = "auto"
    limite_braquage: str = "disque"
    source: Path | None = None

    def avec(self, **changements: Any) -> Etude:
        """Copie modifiée (options de ligne de commande)."""
        return replace(self, **changements)


def lire_plage(nom: str, valeur: object) -> Intervalle:
    """``[bas, haut]`` ou une valeur seule → :class:`Intervalle`."""
    if isinstance(valeur, bool):
        raise ErreurEtude(f"{nom} : plage attendue, reçu {valeur!r}")
    if isinstance(valeur, (int, float)):
        bornes = [float(valeur), float(valeur)]
    elif isinstance(valeur, (list, tuple)) and len(valeur) == 2:
        try:
            bornes = [float(v) for v in valeur]
        except (TypeError, ValueError):
            raise ErreurEtude(f"{nom} : bornes non numériques {valeur!r}") from None
    else:
        raise ErreurEtude(f"{nom} : plage attendue sous la forme [bas, haut], reçu {valeur!r}")
    bas, haut = bornes
    if bas > haut:
        raise ErreurEtude(f"{nom} : borne basse {bas:g} > borne haute {haut:g}")
    if nom in ("alpha", "beta") and max(abs(bas), abs(haut)) >= ANGLE_MAX:
        raise ErreurEtude(f"{nom} : |{nom}| doit rester < {ANGLE_MAX:g}°")
    return Intervalle.ferme(bas, haut)


def _choix(cle: str, valeur: object, admis: tuple[str, ...]) -> str:
    texte = str(valeur).strip().lower()
    if texte not in admis:
        raise ErreurEtude(f"{cle} : {valeur!r} inconnu ; admis : {', '.join(admis)}")
    return texte


def etude_depuis_dict(donnees: Mapping[str, Any], source: Path | None = None) -> Etude:
    """Valide et construit une :class:`Etude` depuis un dictionnaire (YAML lu)."""
    if not isinstance(donnees, Mapping):
        raise ErreurEtude("le fichier d'étude doit être un dictionnaire YAML")
    inconnues = sorted(set(donnees) - set(CLES_ADMISES))
    if inconnues:
        raise ErreurEtude(
            f"clé(s) inconnue(s) : {', '.join(inconnues)} ; "
            f"clés admises : {', '.join(CLES_ADMISES)}"
        )

    entete = donnees.get("etude") or {}
    if not isinstance(entete, Mapping):
        raise ErreurEtude("« etude » doit être un dictionnaire (nom, description)")
    autres = sorted(set(entete) - {"nom", "description"})
    if autres:
        raise ErreurEtude(f"etude : clé(s) inconnue(s) {autres} ; admises : nom, description")
    nom = str(entete.get("nom", source.stem if source else "ETUDE"))

    table = dict(TRAJECTOIRES)
    perso = donnees.get("trajectoires") or {}
    if not isinstance(perso, Mapping):
        raise ErreurEtude("« trajectoires » doit associer un nom à {efforts: [...]}")
    try:
        for nom_t, definition in perso.items():
            if not isinstance(definition, Mapping):
                raise ValueError(f"trajectoire {nom_t} : dictionnaire attendu")
            table[str(nom_t)] = fabriquer_trajectoire(str(nom_t), definition)
        if "trajectoire" not in donnees:
            raise ValueError(f"« trajectoire » manquante ; types admis : {', '.join(table)}")
        trajectoire = resoudre_trajectoire(str(donnees["trajectoire"]), table)

        geo = donnees.get("geometrie")
        if geo is None:
            raise ValueError("« geometrie » manquante")
        if isinstance(geo, Mapping):
            autres = sorted(set(geo) - {"type", "n_ailettes"})
            if autres:
                raise ValueError(
                    f"geometrie : clé(s) inconnue(s) {autres} ; admises : type, n_ailettes"
                )
            n = geo.get("n_ailettes")
            geometrie = resoudre_geometrie(str(geo.get("type", "")), None if n is None else int(n))
        else:
            geometrie = resoudre_geometrie(str(geo))
    except ValueError as erreur:
        raise ErreurEtude(str(erreur)) from None

    variables = donnees.get("variables") or {}
    if not isinstance(variables, Mapping):
        raise ErreurEtude("« variables » doit associer une variable à sa plage")
    hors = sorted(set(variables) - set(VARIABLES))
    if hors:
        raise ErreurEtude(
            f"variable(s) inconnue(s) : {', '.join(map(str, hors))} ; "
            f"variables admises : {', '.join(VARIABLES)}"
        )
    plages = {v: lire_plage(v, variables[v]) for v in VARIABLES if v in variables}

    return Etude(
        nom=nom,
        trajectoire=trajectoire,
        geometrie=geometrie,
        plages=plages,
        repere=_choix("repere", donnees.get("repere", "auto"), REPERES),
        limite_braquage=_choix(
            "limite_braquage", donnees.get("limite_braquage", "disque"), LIMITES_BRAQUAGE
        ),
        source=source,
    )


def charger_etude(chemin: str | Path) -> Etude:
    """Lit et valide un fichier d'étude YAML."""
    chemin = Path(chemin)
    try:
        texte = chemin.read_text(encoding="utf-8")
    except OSError as erreur:
        raise ErreurEtude(f"lecture impossible de {chemin} : {erreur.strerror}") from None
    try:
        donnees = yaml.safe_load(texte)
    except yaml.YAMLError as erreur:
        raise ErreurEtude(f"{chemin} : YAML invalide ({erreur})") from None
    return etude_depuis_dict(donnees or {}, source=chemin)
