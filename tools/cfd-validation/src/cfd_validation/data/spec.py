"""Le dictionnaire ``TABLES`` : ce que l'utilisateur déclare, et sa validation.

Une déclaration décrit **où** est une table dans le code compilé et **comment**
la lire :

.. code-block:: python

    TABLES = {
        "CN": {
            "bloc":       "tab_cn",
            "tableau":    "tab_cn",
            "colonnes":   ["mach", "alpha", "delta", "CN"],
            "qoi":        ["CN"],
            "lignes":     "npt_cn",
            "constantes": {"altitude": 0.0, "beta": 0.0},
            "rtol": 1e-9, "atol": 1e-12,
        },
    }

Trois pièges se traitent ici, et nulle part ailleurs :

``lignes``
    Un tableau Fortran est dimensionné au maximum et un entier voisin dit
    combien de lignes sont réellement remplies. Sans cette clé, la queue de
    valeurs jamais écrites produit des échecs fantômes. On tolère son absence
    — le détecteur ``queue_non_renseignee`` la rattrape et nomme le remède —
    mais on ne la devine pas : rogner les lignes nulles de la fin supprimerait
    un nœud légitimement nul.

``orientation``
    ``TAB(NROWS, NCOLS)`` et ``TAB(NCOLS, NROWS)`` existent tous les deux. On
    infère par la dimension qui vaut ``len(colonnes)`` ; si les deux
    conviennent — tableau carré — on **exige** la déclaration plutôt que de
    tirer à pile ou face sur la lecture de toute une table.

clés inconnues
    Elles sont **refusées**, en listant les clés admises. Une clé mal
    orthographiée est silencieuse par nature : ``"rtl": 1e-3`` laisserait la
    tolérance par défaut et ferait passer une table fausse pour bonne.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cfd_validation.core.ecart import ATOL_DEFAUT, RTOL_DEFAUT

__all__ = [
    "CLES_ADMISES",
    "ErreurSpec",
    "SpecTable",
    "charger_fichier",
    "charger_tables",
]

#: Orientations admises. ``"lignes"`` : une ligne du tableau est un point.
ORIENTATIONS = ("lignes", "colonnes")

#: Les seules clés admises dans une sous-déclaration. Toute autre est refusée.
CLES_ADMISES = frozenset(
    {
        "bloc",
        "tableau",
        "colonnes",
        "qoi",
        "lignes",
        "constantes",
        "orientation",
        "rtol",
        "atol",
        "tolerances",
        "libelles",
        "unites",
    }
)


class ErreurSpec(ValueError):
    """Une déclaration de table est inutilisable.

    Hérite de :class:`ValueError` : un appelant qui ne connaît pas ce paquet
    attrape déjà la bonne chose. Le message nomme toujours la table fautive —
    une étude en porte vingt, et « clé inconnue » sans nom ne sert à rien.
    """


@dataclass(frozen=True)
class SpecTable:
    """La déclaration d'une table, validée.

    Ne construisez pas cet objet à la main : passez par :func:`charger_tables`,
    qui applique les valeurs par défaut et les refus.
    """

    nom: str
    bloc: str
    tableau: str
    colonnes: tuple[str, ...]
    qoi: tuple[str, ...]
    lignes: int | str | None = None
    constantes: Mapping[str, float] = field(default_factory=dict)
    orientation: str | None = None
    rtol: float = RTOL_DEFAUT
    atol: float = ATOL_DEFAUT
    tolerances: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    libelles: Mapping[str, str] = field(default_factory=dict)
    unites: Mapping[str, str] = field(default_factory=dict)

    @property
    def independantes(self) -> tuple[str, ...]:
        """Les colonnes qui décrivent *où* on est dans la table."""
        return tuple(colonne for colonne in self.colonnes if colonne not in self.qoi)

    @property
    def entrees_attendues(self) -> tuple[str, ...]:
        """Les colonnes que le modèle recevra : indépendantes, puis constantes."""
        return self.independantes + tuple(self.constantes)

    def tolerance(self, qoi: str) -> tuple[float, float]:
        """``(rtol, atol)`` pour une grandeur, surcharge par grandeur comprise."""
        return self.tolerances.get(qoi, (self.rtol, self.atol))

    def libelle(self, colonne: str) -> str:
        """Le nom affichable d'une colonne ; son nom brut à défaut."""
        return self.libelles.get(colonne, colonne)

    def unite(self, colonne: str) -> str:
        """L'unité d'une colonne ; ``"-"`` à défaut, comme le veut cfd-plot."""
        return self.unites.get(colonne, "-")


def charger_tables(declarations: Mapping[str, Mapping[str, Any]]) -> dict[str, SpecTable]:
    """Valide un dictionnaire ``TABLES`` et rend une spec par table.

    Raises
    ------
    ErreurSpec
        Dès la première déclaration inutilisable, en la nommant.
    """
    if not isinstance(declarations, Mapping):
        raise ErreurSpec(f"TABLES doit être un dictionnaire, reçu {type(declarations).__name__}")
    if not declarations:
        raise ErreurSpec("TABLES est vide : aucune table à contrôler.")
    return {nom: _une_table(nom, brut) for nom, brut in declarations.items()}


def charger_fichier(chemin: str | Path) -> dict[str, SpecTable]:
    """Charge un ``TABLES.yaml`` et le valide.

    Le fichier porte le dictionnaire à sa racine, ou sous une clé ``tables``.
    """
    import yaml

    chemin = Path(chemin)
    try:
        contenu = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    except FileNotFoundError as erreur:
        raise ErreurSpec(f"fichier de tables introuvable : {chemin}") from erreur
    except yaml.YAMLError as erreur:
        raise ErreurSpec(f"{chemin} n'est pas un YAML valide : {erreur}") from erreur

    if isinstance(contenu, Mapping) and "tables" in contenu:
        contenu = contenu["tables"]
    if not isinstance(contenu, Mapping):
        raise ErreurSpec(
            f"{chemin} doit porter un dictionnaire de tables, "
            "à sa racine ou sous la clé « tables »."
        )
    return charger_tables(contenu)


# ---------------------------------------------------------------------------
# Validation d'une déclaration
# ---------------------------------------------------------------------------


def _une_table(nom: str, brut: Mapping[str, Any]) -> SpecTable:
    """Valide une sous-déclaration et en fait une :class:`SpecTable`."""
    if not isinstance(brut, Mapping):
        raise ErreurSpec(f"table « {nom} » : la déclaration doit être un dictionnaire.")

    inconnues = sorted(set(brut) - CLES_ADMISES)
    if inconnues:
        raise ErreurSpec(
            f"table « {nom} » : clé(s) inconnue(s) {inconnues}. "
            f"Clés admises : {sorted(CLES_ADMISES)}."
        )

    colonnes = _colonnes(nom, brut)
    qoi = _qoi(nom, brut, colonnes)
    independantes = [colonne for colonne in colonnes if colonne not in qoi]
    if not independantes:
        raise ErreurSpec(
            f"table « {nom} » : toutes les colonnes sont des QOI. "
            "Il en faut au moins une pour dire où l'on est dans la table."
        )

    bloc = _texte(nom, brut, "bloc", obligatoire=True)
    constantes = _constantes(nom, brut, colonnes)
    rtol = _reel(nom, brut, "rtol", RTOL_DEFAUT)
    atol = _reel(nom, brut, "atol", ATOL_DEFAUT)

    return SpecTable(
        nom=nom,
        bloc=bloc,
        tableau=_texte(nom, brut, "tableau", obligatoire=False) or bloc,
        colonnes=colonnes,
        qoi=qoi,
        lignes=_lignes(nom, brut),
        constantes=constantes,
        orientation=_orientation(nom, brut),
        rtol=rtol,
        atol=atol,
        tolerances=_tolerances(nom, brut, qoi, rtol, atol),
        libelles=_correspondance(nom, brut, "libelles", colonnes, constantes),
        unites=_correspondance(nom, brut, "unites", colonnes, constantes),
    )


def _texte(nom: str, brut: Mapping[str, Any], cle: str, *, obligatoire: bool) -> str:
    valeur = brut.get(cle)
    if valeur is None:
        if obligatoire:
            raise ErreurSpec(f"table « {nom} » : la clé « {cle} » est obligatoire.")
        return ""
    if not isinstance(valeur, str) or not valeur.strip():
        raise ErreurSpec(f"table « {nom} » : « {cle} » doit être un nom non vide, reçu {valeur!r}.")
    return valeur.strip()


def _colonnes(nom: str, brut: Mapping[str, Any]) -> tuple[str, ...]:
    brutes = brut.get("colonnes")
    if brutes is None:
        raise ErreurSpec(f"table « {nom} » : la clé « colonnes » est obligatoire.")
    if isinstance(brutes, str) or not isinstance(brutes, (list, tuple)):
        raise ErreurSpec(
            f"table « {nom} » : « colonnes » doit être une liste de noms, reçu {brutes!r}."
        )
    colonnes = tuple(str(colonne) for colonne in brutes)
    if not colonnes:
        raise ErreurSpec(f"table « {nom} » : « colonnes » est vide.")
    doublons = sorted({c for c in colonnes if colonnes.count(c) > 1})
    if doublons:
        raise ErreurSpec(f"table « {nom} » : colonne(s) en double {doublons}.")
    return colonnes


def _qoi(nom: str, brut: Mapping[str, Any], colonnes: tuple[str, ...]) -> tuple[str, ...]:
    brutes = brut.get("qoi")
    if brutes is None:
        # La dernière colonne : c'est ainsi que se range une table longue, la
        # valeur après ses entrées.
        return (colonnes[-1],)
    if isinstance(brutes, str):
        brutes = [brutes]
    if not isinstance(brutes, (list, tuple)) or not brutes:
        raise ErreurSpec(f"table « {nom} » : « qoi » doit être un nom ou une liste non vide.")
    qoi = tuple(str(grandeur) for grandeur in brutes)
    absentes = [grandeur for grandeur in qoi if grandeur not in colonnes]
    if absentes:
        raise ErreurSpec(
            f"table « {nom} » : QOI {absentes} absente(s) de « colonnes » {list(colonnes)}."
        )
    return qoi


def _lignes(nom: str, brut: Mapping[str, Any]) -> int | str | None:
    valeur = brut.get("lignes")
    if valeur is None:
        return None
    if isinstance(valeur, bool):
        raise ErreurSpec(
            f"table « {nom} » : « lignes » doit être un entier ou un nom, pas un booléen."
        )
    if isinstance(valeur, int):
        if valeur <= 0:
            raise ErreurSpec(
                f"table « {nom} » : « lignes » doit être strictement positif, reçu {valeur}."
            )
        return valeur
    if isinstance(valeur, str) and valeur.strip():
        return valeur.strip()
    raise ErreurSpec(
        f"table « {nom} » : « lignes » doit être un entier, ou le nom d'un entier "
        f"du même COMMON block, reçu {valeur!r}."
    )


def _orientation(nom: str, brut: Mapping[str, Any]) -> str | None:
    valeur = brut.get("orientation")
    if valeur is None:
        return None
    if valeur not in ORIENTATIONS:
        raise ErreurSpec(
            f"table « {nom} » : « orientation » vaut {valeur!r}, "
            f"attendu l'un de {list(ORIENTATIONS)}."
        )
    return str(valeur)


def _constantes(nom: str, brut: Mapping[str, Any], colonnes: tuple[str, ...]) -> dict[str, float]:
    valeur = brut.get("constantes") or {}
    if not isinstance(valeur, Mapping):
        raise ErreurSpec(
            f"table « {nom} » : « constantes » doit être un dictionnaire colonne → valeur."
        )
    collisions = sorted(set(valeur) & set(colonnes))
    if collisions:
        raise ErreurSpec(
            f"table « {nom} » : {collisions} est à la fois une colonne de la table et une "
            "constante. La table fait foi : retirez-la des constantes."
        )
    sorties: dict[str, float] = {}
    for colonne, contenu in valeur.items():
        try:
            sorties[str(colonne)] = float(contenu)
        except (TypeError, ValueError) as erreur:
            raise ErreurSpec(
                f"table « {nom} » : la constante « {colonne} » vaut {contenu!r}, attendu un nombre."
            ) from erreur
    return sorties


def _reel(nom: str, brut: Mapping[str, Any], cle: str, defaut: float) -> float:
    valeur = brut.get(cle, defaut)
    try:
        reel = float(valeur)
    except (TypeError, ValueError) as erreur:
        raise ErreurSpec(
            f"table « {nom} » : « {cle} » vaut {valeur!r}, attendu un nombre."
        ) from erreur
    if reel < 0.0:
        raise ErreurSpec(f"table « {nom} » : « {cle} » doit être positif, reçu {reel}.")
    return reel


def _tolerances(
    nom: str,
    brut: Mapping[str, Any],
    qoi: tuple[str, ...],
    rtol: float,
    atol: float,
) -> dict[str, tuple[float, float]]:
    valeur = brut.get("tolerances") or {}
    if not isinstance(valeur, Mapping):
        raise ErreurSpec(
            f"table « {nom} » : « tolerances » doit être un dictionnaire "
            "QOI → {{rtol: …, atol: …}}."
        )
    sorties: dict[str, tuple[float, float]] = {}
    for grandeur, contenu in valeur.items():
        if grandeur not in qoi:
            raise ErreurSpec(
                f"table « {nom} » : tolérance déclarée pour « {grandeur} », "
                f"qui n'est pas une QOI ({list(qoi)})."
            )
        if not isinstance(contenu, Mapping):
            raise ErreurSpec(
                f"table « {nom} » : la tolérance de « {grandeur} » doit être "
                "un dictionnaire {{rtol: …, atol: …}}."
            )
        inconnues = sorted(set(contenu) - {"rtol", "atol"})
        if inconnues:
            raise ErreurSpec(
                f"table « {nom} » : tolérance de « {grandeur} », clé(s) inconnue(s) {inconnues}."
            )
        sorties[str(grandeur)] = (
            _reel(nom, contenu, "rtol", rtol),
            _reel(nom, contenu, "atol", atol),
        )
    return sorties


def _correspondance(
    nom: str,
    brut: Mapping[str, Any],
    cle: str,
    colonnes: tuple[str, ...],
    constantes: Mapping[str, float],
) -> dict[str, str]:
    valeur = brut.get(cle) or {}
    if not isinstance(valeur, Mapping):
        raise ErreurSpec(f"table « {nom} » : « {cle} » doit être un dictionnaire colonne → texte.")
    connues = set(colonnes) | set(constantes)
    inconnues = sorted(set(map(str, valeur)) - connues)
    if inconnues:
        raise ErreurSpec(
            f"table « {nom} » : « {cle} » désigne {inconnues}, "
            f"qui n'est ni une colonne ni une constante ({sorted(connues)})."
        )
    return {str(colonne): str(texte) for colonne, texte in valeur.items()}
