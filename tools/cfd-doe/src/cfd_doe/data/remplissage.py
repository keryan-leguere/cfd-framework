"""Le fichier de remplissage : comment peupler les sous-domaines d'une étude.

Forme (tout est facultatif sauf ``etude``) ::

    etude: ETUDE_FUSEE.yaml          # chemin du fichier d'étude, ou son contenu
    repere: cartesien                # surcharge du repère de l'étude

    mach: [0.6, 0.8, 0.95, 1.05, 1.2, 1.5, 2.0, 3.0]
    parametres:
      moteur: {niveaux: [0, 0.5, 1], nominal: 0}       # discret: true → jamais continu

    niveaux:                         # grille de référence, variables du repère de travail
      alpha: {pas: 5}                # ou une liste, ou {n: 9}
      beta: {pas: 2.5}
      DM: [-20, -10, 0, 10, 20]

    plans:                           # autant de plans nommés qu'on veut, tous comparés
      complet: {type: factoriel}
      reduit: {type: factoriel, niveaux: {beta: [-5, 0, 5]}}
      ordre1: {type: decomposition, ordre: 1, controle: {fraction: 0.15}}
      lhs: {type: lhs, regle: 30, test: 0.15}
    retenu: ordre1                   # celui qui part dans doe.csv

    exclure:                         # points écartés de tous les plans
      - mach >= 2 and alpha > 10

    sortie: {dossier: DOE, csv: doe.csv, figures: true, tous_les_csv: false,
             formats: [png, pdf]}

Toute clé inconnue est **refusée**, avec la liste des clés admises, comme pour
le fichier d'étude : ``regles: 30`` ne doit pas retomber sur la valeur par
défaut sans rien dire.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from cfd_doe.core.intervalle import TOLERANCE, Intervalle
from cfd_doe.data.etude import REPERES, ErreurEtude, Etude, charger_etude, etude_depuis_dict
from cfd_doe.data.variables import VARIABLES_CARTESIENNES, VARIABLES_POLAIRES

__all__ = [
    "CLES_ADMISES",
    "FORMATS_FIGURES",
    "OPTIONS",
    "TYPES",
    "ErreurRemplissage",
    "Parametre",
    "PlanSpec",
    "Remplissage",
    "Sortie",
    "charger_remplissage",
    "remplissage_depuis_dict",
    "resoudre_niveaux",
]


class ErreurRemplissage(ErreurEtude):
    """Fichier de remplissage invalide."""


CLES_ADMISES: tuple[str, ...] = (
    "nom",
    "etude",
    "repere",
    "mach",
    "parametres",
    "niveaux",
    "plans",
    "retenu",
    "exclure",
    "sortie",
)

#: Options communes aux plans tirés (remplissage d'espace).
_TIRAGE = ("points_par_mach", "regle", "part_plans", "test", "graine", "essais", "decale_par_mach")

#: Type de plan → options admises (en plus de ``type``, ``exclure``, ``description``).
OPTIONS: dict[str, tuple[str, ...]] = {
    "factoriel": ("niveaux",),
    "etoile": ("niveaux",),
    "decomposition": (
        "ordre",
        "primaires",
        "increments_fonction_de",
        "increments",
        "couplages",
        "croiser",
        "controle",
        "niveaux",
    ),
    "composite_centre": ("fraction", "test", "graine"),
    "box_behnken": ("test", "graine"),
    "grille_creuse": ("niveau", "test", "graine"),
    "lhs": _TIRAGE,
    "halton": _TIRAGE,
    "sobol": _TIRAGE,
    "krigeage": (*_TIRAGE, "portee", "candidats"),
    "adaptatif": _TIRAGE,
    "multi_fidelite": (*_TIRAGE, "regle_hf", "points_hf_par_mach"),
}
TYPES: tuple[str, ...] = tuple(OPTIONS)
_COMMUNES = ("type", "exclure", "description")

#: Formats de figure admis.
FORMATS_FIGURES: tuple[str, ...] = ("png", "pdf", "svg")

#: Colonnes réservées du DOE : un paramètre ne peut pas porter ces noms.
_RESERVES = frozenset(
    {"mach", "id", "role", "table", "sous_domaine", "fidelite"}
    | set(VARIABLES_CARTESIENNES)
    | set(VARIABLES_POLAIRES)
)


@dataclass(frozen=True)
class Parametre:
    """Un paramètre indépendant (moteur, configuration…)."""

    nom: str
    niveaux: tuple[float, ...]
    nominal: float
    discret: bool = False

    @property
    def plage(self) -> Intervalle:
        """L'étendue des niveaux : le domaine du paramètre quand il est traité en continu."""
        return Intervalle(min(self.niveaux), max(self.niveaux))

    @property
    def continu(self) -> bool:
        """Peut-il être un facteur continu (plans structurés, remplissage d'espace) ?"""
        return not self.discret and not self.plage.est_point


@dataclass(frozen=True)
class PlanSpec:
    """Un plan demandé : un nom, un type, ses options."""

    nom: str
    type: str
    options: dict[str, Any] = field(default_factory=dict)
    exclure: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class Sortie:
    """Où écrire, et quoi."""

    dossier: Path = Path("DOE")
    csv: str = "doe.csv"
    figures: bool = True
    tous_les_csv: bool = False
    #: Formats des figures : PNG (300 dpi) pour l'écran, PDF ou SVG vectoriels pour un rapport.
    formats: tuple[str, ...] = ("png", "pdf")


@dataclass(frozen=True)
class Remplissage:
    """Ce que l'utilisateur demande pour peupler les sous-domaines."""

    nom: str
    etude: Etude
    mach: tuple[float, ...]
    parametres: tuple[Parametre, ...]
    niveaux: dict[str, Any]
    plans: tuple[PlanSpec, ...]
    retenu: str
    exclure: tuple[str, ...] = ()
    sortie: Sortie = field(default_factory=Sortie)
    source: Path | None = None

    @property
    def plan_retenu(self) -> PlanSpec:
        """Le plan qui part dans le fichier DOE."""
        return next(p for p in self.plans if p.nom == self.retenu)


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------


def _refuser(contexte: str, donnees: Mapping[str, Any], admises: Sequence[str]) -> None:
    inconnues = sorted(str(k) for k in set(donnees) - set(admises))
    if inconnues:
        raise ErreurRemplissage(
            f"{contexte} : clé(s) inconnue(s) {', '.join(inconnues)} ; "
            f"clés admises : {', '.join(admises)}"
        )


def _nombres(contexte: str, valeur: object) -> tuple[float, ...]:
    if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
        valeur = [valeur]
    if not isinstance(valeur, (list, tuple)) or not valeur:
        raise ErreurRemplissage(f"{contexte} : liste de nombres attendue, reçu {valeur!r}")
    try:
        nombres = sorted({float(v) for v in valeur if not isinstance(v, bool)})
    except (TypeError, ValueError):
        raise ErreurRemplissage(f"{contexte} : valeurs non numériques {valeur!r}") from None
    if len(nombres) != len(valeur):
        raise ErreurRemplissage(f"{contexte} : valeurs en double ou non numériques {valeur!r}")
    return tuple(nombres)


def _parametre(nom: str, definition: object) -> Parametre:
    if not nom.isidentifier():
        raise ErreurRemplissage(
            f"paramètre « {nom} » : le nom doit être un identifiant (lettres, chiffres, _)"
        )
    if nom in _RESERVES:
        raise ErreurRemplissage(f"paramètre « {nom} » : nom réservé à une colonne du DOE")
    if not isinstance(definition, Mapping):
        definition = {"niveaux": definition}
    _refuser(f"paramètre {nom}", definition, ("niveaux", "nominal", "discret"))
    if "niveaux" not in definition:
        raise ErreurRemplissage(f"paramètre {nom} : « niveaux » manquant")
    niveaux = _nombres(f"paramètre {nom}, niveaux", definition["niveaux"])
    brut: Any = definition.get("nominal", niveaux[0])
    nominal = float(brut)
    if not any(abs(nominal - x) <= TOLERANCE for x in niveaux):
        raise ErreurRemplissage(
            f"paramètre {nom} : le nominal {nominal:g} doit être un de ses niveaux {list(niveaux)}"
        )
    return Parametre(nom, niveaux, nominal, bool(definition.get("discret", False)))


def _conditions(contexte: str, valeur: object) -> tuple[str, ...]:
    if valeur is None:
        return ()
    if isinstance(valeur, str):
        valeur = [valeur]
    if not isinstance(valeur, (list, tuple)) or not all(isinstance(v, str) for v in valeur):
        raise ErreurRemplissage(f"{contexte} : liste de conditions (texte) attendue")
    return tuple(valeur)


def _plan(nom: str, definition: object) -> PlanSpec:
    if isinstance(definition, str):
        definition = {"type": definition}
    if definition is None:
        definition = {"type": nom}
    if not isinstance(definition, Mapping):
        raise ErreurRemplissage(f"plan {nom} : dictionnaire attendu ({{type: …}})")
    genre = str(definition.get("type", nom)).strip().lower()
    if genre not in OPTIONS:
        raise ErreurRemplissage(
            f"plan {nom} : type « {genre} » inconnu ; types admis : {', '.join(TYPES)}"
        )
    _refuser(f"plan {nom} ({genre})", definition, (*_COMMUNES, *OPTIONS[genre]))
    options = {k: v for k, v in definition.items() if k not in _COMMUNES}
    return PlanSpec(
        nom=str(nom),
        type=genre,
        options=options,
        exclure=_conditions(f"plan {nom}, exclure", definition.get("exclure")),
        description=str(definition.get("description", "")),
    )


def remplissage_depuis_dict(
    donnees: Mapping[str, Any], source: Path | None = None, etude: Etude | None = None
) -> Remplissage:
    """Valide et construit un :class:`Remplissage` depuis un dictionnaire (YAML lu).

    ``etude`` : une étude déjà chargée, qui remplace la clé ``etude`` (tests,
    ligne de commande).
    """
    if not isinstance(donnees, Mapping):
        raise ErreurRemplissage("le fichier de remplissage doit être un dictionnaire YAML")
    _refuser("remplissage", donnees, CLES_ADMISES)

    if etude is None:
        reference = donnees.get("etude")
        if isinstance(reference, Mapping):
            etude = etude_depuis_dict(reference, source)
        elif isinstance(reference, str):
            chemin = Path(reference)
            if not chemin.is_absolute() and source is not None:
                chemin = source.parent / chemin
            etude = charger_etude(chemin)
        else:
            raise ErreurRemplissage(
                "« etude » manquante : chemin du fichier d'étude cfd-doe, ou son contenu"
            )
    if "repere" in donnees:
        repere = str(donnees["repere"]).strip().lower()
        if repere not in REPERES:
            raise ErreurRemplissage(f"repere : {repere!r} inconnu ; admis : {', '.join(REPERES)}")
        etude = etude.avec(repere=repere)

    mach = _nombres("mach", donnees["mach"]) if donnees.get("mach") is not None else ()
    if any(m < 0 for m in mach):
        raise ErreurRemplissage("mach : valeurs négatives")

    bruts = donnees.get("parametres") or {}
    if not isinstance(bruts, Mapping):
        raise ErreurRemplissage("« parametres » doit associer un nom à {niveaux: […]}")
    parametres = tuple(_parametre(str(nom), d) for nom, d in bruts.items())

    niveaux = donnees.get("niveaux") or {}
    if not isinstance(niveaux, Mapping):
        raise ErreurRemplissage("« niveaux » doit associer une variable à ses niveaux")
    admises = (*VARIABLES_CARTESIENNES, *VARIABLES_POLAIRES)
    hors = sorted(str(v) for v in set(niveaux) - set(admises))
    if hors:
        raise ErreurRemplissage(
            f"niveaux : variable(s) inconnue(s) {', '.join(hors)} ; "
            f"admises : {', '.join(dict.fromkeys(admises))}"
        )

    bruts = donnees.get("plans")
    if bruts is None:
        bruts = {genre: {"type": genre} for genre in TYPES}
    if not isinstance(bruts, Mapping) or not bruts:
        raise ErreurRemplissage("« plans » doit associer un nom de plan à {type: …}")
    plans = tuple(_plan(str(nom), d) for nom, d in bruts.items())

    noms = [p.nom for p in plans]
    defaut = "decomposition" if "decomposition" in noms else noms[0]
    retenu = str(donnees.get("retenu", defaut))
    if retenu not in noms:
        raise ErreurRemplissage(f"retenu : « {retenu} » n'est pas un des plans ({', '.join(noms)})")

    brute = donnees.get("sortie") or {}
    if not isinstance(brute, Mapping):
        raise ErreurRemplissage("« sortie » doit être un dictionnaire")
    _refuser("sortie", brute, ("dossier", "csv", "figures", "tous_les_csv", "formats"))
    formats = brute.get("formats", ["png", "pdf"])
    if isinstance(formats, str):
        formats = [formats]
    if not isinstance(formats, (list, tuple)) or not formats:
        raise ErreurRemplissage("sortie.formats : une liste parmi png, pdf, svg")
    inconnus = sorted({str(f) for f in formats} - set(FORMATS_FIGURES))
    if inconnus:
        raise ErreurRemplissage(
            f"sortie.formats : {', '.join(inconnus)} inconnu(s) ; admis : {', '.join(FORMATS_FIGURES)}"
        )
    sortie = Sortie(
        dossier=Path(str(brute.get("dossier", "DOE"))),
        csv=str(brute.get("csv", "doe.csv")),
        figures=bool(brute.get("figures", True)),
        tous_les_csv=bool(brute.get("tous_les_csv", False)),
        formats=tuple(dict.fromkeys(str(f) for f in formats)),
    )

    return Remplissage(
        nom=str(donnees.get("nom", source.stem if source else etude.nom)),
        etude=etude,
        mach=mach,
        parametres=parametres,
        niveaux=dict(niveaux),
        plans=plans,
        retenu=retenu,
        exclure=_conditions("exclure", donnees.get("exclure")),
        sortie=sortie,
        source=source,
    )


def charger_remplissage(chemin: str | Path) -> Remplissage:
    """Lit et valide un fichier de remplissage YAML."""
    chemin = Path(chemin)
    try:
        texte = chemin.read_text(encoding="utf-8")
    except OSError as erreur:
        raise ErreurRemplissage(f"lecture impossible de {chemin} : {erreur.strerror}") from None
    try:
        donnees = yaml.safe_load(texte)
    except yaml.YAMLError as erreur:
        raise ErreurRemplissage(f"{chemin} : YAML invalide ({erreur})") from None
    return remplissage_depuis_dict(donnees, chemin)


# ---------------------------------------------------------------------------
# Niveaux d'une variable
# ---------------------------------------------------------------------------

#: Nombre de niveaux d'une variable dont le fichier ne dit rien.
N_DEFAUT = 5


def resoudre_niveaux(
    nom: str,
    spec: object,
    boite: Intervalle,
    *,
    symetrique: bool,
    reference: float,
) -> tuple[tuple[float, ...], tuple[str, ...]]:
    """Les niveaux d'une variable sur sa boîte, et les ajustements faits.

    ``spec`` : une liste de valeurs, ``{pas: p}`` (multiples de ``p`` comptés
    depuis la référence), ``{n: k}`` (``k`` niveaux régulièrement espacés) ou
    ``None`` (``{n: 5}``).

    Deux ajustements, signalés : pour une variable qu'une symétrie retourne,
    les niveaux sont complétés par leurs opposés (sinon l'image d'un nœud
    tomberait hors grille) ; la valeur de référence est ajoutée si elle manque
    (les incréments d'une décomposition se mesurent par rapport à elle).
    """
    notes: list[str] = []
    if spec is None:
        spec = {"n": N_DEFAUT}
        notes.append(f"{nom} : niveaux non précisés, {N_DEFAUT} niveaux réguliers")
    if isinstance(spec, Mapping):
        _refuser(f"niveaux de {nom}", spec, ("pas", "n", "valeurs"))
        if len(spec) != 1:
            raise ErreurRemplissage(f"niveaux de {nom} : une seule clé parmi pas, n, valeurs")
        if "valeurs" in spec:
            valeurs = list(_nombres(f"niveaux de {nom}", spec["valeurs"]))
        elif "pas" in spec:
            pas = float(spec["pas"])
            if pas <= 0:
                raise ErreurRemplissage(f"niveaux de {nom} : pas strictement positif attendu")
            k_bas = int((boite.bas - reference) / pas - 1e-9)
            k_haut = int((boite.haut - reference) / pas + 1e-9)
            valeurs = [reference + k * pas for k in range(k_bas, k_haut + 1)]
        else:
            n = int(spec["n"])
            if n < 1:
                raise ErreurRemplissage(f"niveaux de {nom} : n ≥ 1 attendu")
            if n == 1:
                valeurs = [reference]
            else:
                valeurs = [boite.bas + i * boite.largeur / (n - 1) for i in range(n)]
    else:
        valeurs = list(_nombres(f"niveaux de {nom}", spec))

    hors = [v for v in valeurs if not boite.contient(v, 1e-6)]
    if hors:
        raise ErreurRemplissage(
            f"niveaux de {nom} : {', '.join(f'{v:g}' for v in hors)} hors du domaine "
            f"[{boite.bas:g} ; {boite.haut:g}]"
        )

    def unique(liste: list[float]) -> list[float]:
        garde: list[float] = []
        for v in sorted(liste):
            if not garde or abs(v - garde[-1]) > 1e-9:
                garde.append(round(v, 10) + 0.0)
        return garde

    valeurs = unique(valeurs)
    if symetrique:
        complet = unique([*valeurs, *(-v for v in valeurs)])
        if len(complet) != len(valeurs):
            notes.append(
                f"{nom} : niveaux complétés par leurs opposés (une symétrie retourne {nom})"
            )
            valeurs = complet
    if not any(abs(v - reference) <= 1e-9 for v in valeurs):
        notes.append(f"{nom} : niveau de référence {reference:g} ajouté")
        valeurs = unique([*valeurs, reference])
    return tuple(valeurs), tuple(notes)
