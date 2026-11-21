"""Encapsulation générique d'un code Fortran à phases (ENTRY) compilé par f2py.

Rien ici ne connaît le modèle aéro : pour un autre code, on écrit une
sous-classe de quatre lignes (voir ``modele_aero.py``)::

    class MonCode(ModeleF2py):
        BIBLIOTHEQUE = "moncode"            # module produit par construire.sh
        PHASES_INIT = ("monini",)           # appelées dans l'ordre, à l'init
        PHASE_CALCUL = "moncal"             # appelée à chaque point
        CONSTANTES = {"lref": 0.2}          # valeurs par défaut des args d'init

Les noms d'arguments ne sont écrits nulle part : ils sont lus dans la
docstring que f2py génère pour chaque phase (``bibliotheque.moncal.__doc__``),
en minuscules, dans l'ordre d'appel. Ce sont eux qui deviennent

- les attributs de l'objet (``modele.lref``, ``modele.mach``) ;
- les mots-clés de l'appel (``moncal(**arguments)``) ;
- les colonnes du DataFrame d'entrée, puis de sortie (``calculer_df``).

**Sondes** (``SONDES = ("probe",)``) : blocs COMMON que le code remplit en
cours de calcul pour la validation (une valeur lue dans une table, avant que le
code la transforme). Leurs variables réelles sont remises à NaN avant chaque
appel, puis rendues avec les sorties, sous leur nom f2py (``valid_tab_cx``) :
une sonde que l'appel n'a pas atteinte vaut NaN, jamais la valeur de l'appel
précédent. ``lire("aertab.tcx")`` rend une copie de n'importe quelle variable
de COMMON — les tables et leurs grilles, telles que le code les voit.

L'état Fortran (variables SAVE, COMMON) est **global au processus** : deux
objets sur la même bibliothèque partagent les mêmes constantes Fortran. Avant
chaque calcul, l'objet vérifie que la dernière initialisation faite sur la
bibliothèque est la sienne, et la refait sinon. C'est aussi ce qui permet à
une colonne d'argument d'init de varier d'une ligne à l'autre.

Python 3.9+, numpy, pandas.
"""

from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import math
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

import numpy as np
import pandas as pd

__all__ = [
    "Argument",
    "ErreurModele",
    "ModeleF2py",
    "Signature",
    "importer_bibliotheque",
]


class ErreurModele(RuntimeError):
    """Une phase Fortran a signalé une erreur, ou l'appel est mal formé."""


# --------------------------------------------------------------------------
# Signature d'une phase, lue dans la docstring f2py
# --------------------------------------------------------------------------

# « cx,cy,ierr = aercal(mach,alpha,[n]) » ou « aero() »
_LIGNE_APPEL = re.compile(r"^\s*(?:(?P<sorties>[\w,\s]+?)\s*=\s*)?(?P<nom>\w+)\((?P<entrees>.*)\)\s*$")
# « mach : input float » / « coef : rank-1 array('d') with bounds (6) »
_LIGNE_TYPE = re.compile(r"^\s*(?P<nom>\w+)\s*:\s*(?P<type>.+?)\s*$")
_SECTIONS = ("Parameters", "Other Parameters", "Returns")


@dataclass(frozen=True)
class Argument:
    """Un argument de phase tel que f2py le décrit."""

    nom: str
    type: str = ""          # texte f2py brut : « input float », « int »…
    optionnel: bool = False

    @property
    def tableau(self) -> bool:
        return "array" in self.type

    @property
    def entier(self) -> bool:
        return not self.tableau and re.search(r"\bint\b", self.type) is not None

    @property
    def reel(self) -> bool:
        return not self.tableau and re.search(r"\bfloat\b", self.type) is not None


@dataclass(frozen=True)
class Signature:
    """Entrées et sorties d'une phase, dans l'ordre de la docstring f2py."""

    nom: str
    entrees: tuple[Argument, ...]
    sorties: tuple[Argument, ...]

    @property
    def noms_entrees(self) -> tuple[str, ...]:
        return tuple(a.nom for a in self.entrees)

    @property
    def noms_sorties(self) -> tuple[str, ...]:
        return tuple(a.nom for a in self.sorties)

    @classmethod
    def depuis_doc(cls, doc: str | None, nom: str = "?") -> Signature:
        """Lit la docstring générée par f2py.

        La première ligne donne les noms et l'ordre (« sorties = phase(entrées) »,
        les optionnelles entre crochets) ; les sections Parameters / Returns
        donnent les types.
        """
        if not doc or not doc.strip():
            raise ErreurModele(f"{nom} : pas de docstring f2py, signature illisible")
        lignes = doc.strip().splitlines()
        appel = _LIGNE_APPEL.match(lignes[0])
        if appel is None:
            raise ErreurModele(f"{nom} : première ligne de docstring inattendue : {lignes[0]!r}")

        texte_entrees = appel["entrees"]
        debut_opt = texte_entrees.find("[")
        obligatoires = texte_entrees if debut_opt < 0 else texte_entrees[:debut_opt]
        optionnels = "" if debut_opt < 0 else texte_entrees[debut_opt:]
        noms_obl = [n for n in re.split(r"[,\s\[\]]+", obligatoires) if n]
        noms_opt = [n for n in re.split(r"[,\s\[\]]+", optionnels) if n]
        noms_sorties = [n for n in re.split(r"[,\s]+", appel["sorties"] or "") if n]

        types: dict[str, str] = {}
        section = None
        for ligne in lignes[1:]:
            propre = ligne.strip()
            if propre in _SECTIONS:
                section = propre
                continue
            if section is None or not propre or set(propre) == {"-"}:
                continue
            m = _LIGNE_TYPE.match(ligne)
            if m and (section != "Returns" or m["nom"] in noms_sorties):
                types.setdefault(m["nom"], m["type"])

        entrees = tuple(Argument(n, types.get(n, ""), False) for n in noms_obl) + tuple(
            Argument(n, types.get(n, ""), True) for n in noms_opt
        )
        sorties = tuple(Argument(n, types.get(n, "")) for n in noms_sorties)
        return cls(appel["nom"], entrees, sorties)

    def __str__(self) -> str:
        entrees = ", ".join(a.nom + ("=…" if a.optionnel else "") for a in self.entrees)
        sorties = ", ".join(self.noms_sorties)
        return f"{sorties} = {self.nom}({entrees})" if sorties else f"{self.nom}({entrees})"


# --------------------------------------------------------------------------
# Chargement du module compilé
# --------------------------------------------------------------------------


def importer_bibliotheque(nom: str, dossier: str | Path | None = None) -> ModuleType:
    """Importe le module f2py ``nom`` depuis ``dossier`` (par défaut : sys.path).

    Le dossier est cherché directement (``nom.cpython-*.so``), sans toucher à
    ``sys.path`` : deux compilations du même code, sous deux noms, se chargent
    côte à côte.
    """
    if nom in sys.modules:
        return sys.modules[nom]
    if dossier is None:
        return importlib.import_module(nom)
    for suffixe in importlib.machinery.EXTENSION_SUFFIXES:
        chemin = Path(dossier) / f"{nom}{suffixe}"
        if chemin.is_file():
            spec = importlib.util.spec_from_file_location(nom, chemin)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            sys.modules[nom] = module
            spec.loader.exec_module(module)
            return module
    raise ModuleNotFoundError(
        f"module f2py « {nom} » introuvable dans {dossier} : le construire d'abord "
        f"(bash construire.sh {nom})"
    )


# --------------------------------------------------------------------------
# La classe
# --------------------------------------------------------------------------

# Dernière initialisation faite sur chaque bibliothèque (nom du module → arguments).
# L'état Fortran est global au processus : c'est lui qu'on suit, pas l'objet.
_INIT_COURANTE: dict[str, tuple[tuple[str, tuple[Any, ...]], ...]] = {}


class ModeleF2py:
    """Un code Fortran à phases, appelé comme une fonction de Python ou sur un DataFrame.

    Paramètres
    ----------
    bibliotheque
        Le module f2py, ou son nom (importé depuis ``dossier``). Défaut :
        ``BIBLIOTHEQUE`` de la sous-classe.
    dossier
        Où chercher le module par son nom. Défaut : ``DOSSIER`` de la
        sous-classe, sinon ``sys.path``.
    **constantes
        Arguments des phases d'init (``lref=0.25``), qui priment sur
        ``CONSTANTES``. Chacun devient un attribut de l'objet ; un nom qui n'est
        l'argument d'aucune phase d'init est refusé.
    """

    BIBLIOTHEQUE: ClassVar[str] = ""
    DOSSIER: ClassVar[str | Path | None] = None
    PHASES_INIT: ClassVar[tuple[str, ...]] = ()
    PHASE_CALCUL: ClassVar[str] = ""
    CONSTANTES: ClassVar[Mapping[str, Any]] = {}
    # Sortie entière qui signale une erreur de phase d'init (None : pas de contrôle).
    SORTIE_ERREUR_INIT: ClassVar[str | None] = "ierr"
    # Blocs COMMON de sondes, lus après chaque calcul (voir le module).
    SONDES: ClassVar[tuple[str, ...]] = ()

    def __init__(
        self,
        bibliotheque: ModuleType | str | None = None,
        dossier: str | Path | None = None,
        **constantes: Any,
    ) -> None:
        if isinstance(bibliotheque, ModuleType):
            self.bibliotheque = bibliotheque
        else:
            nom = bibliotheque or self.BIBLIOTHEQUE
            if not nom:
                raise ErreurModele(f"{type(self).__name__} : aucune bibliothèque f2py désignée")
            self.bibliotheque = importer_bibliotheque(nom, dossier if dossier is not None else self.DOSSIER)
        if not self.PHASE_CALCUL:
            raise ErreurModele(f"{type(self).__name__} : PHASE_CALCUL non défini")

        self.signatures_init = tuple(self._signature(p) for p in self.PHASES_INIT)
        self.signature_calcul = self._signature(self.PHASE_CALCUL)
        self.resultat: dict[str, Any] = {}
        self.sondes = self._sondes()

        valeurs = {**self.CONSTANTES, **constantes}
        inconnues = sorted(set(valeurs) - set(self.arguments_init))
        if inconnues:
            raise ErreurModele(
                f"{', '.join(inconnues)} : pas un argument des phases d'init "
                f"({', '.join(self.arguments_init) or 'aucun'})"
            )
        for nom, valeur in valeurs.items():
            setattr(self, nom, valeur)
        self.initialiser()

    # -- description -------------------------------------------------------

    def _signature(self, phase: str) -> Signature:
        fonction = getattr(self.bibliotheque, phase, None)
        if fonction is None:
            disponibles = sorted(n for n in dir(self.bibliotheque) if not n.startswith("_"))
            raise ErreurModele(
                f"{self.bibliotheque.__name__} n'a pas de phase « {phase} » ({', '.join(disponibles)})"
            )
        return Signature.depuis_doc(fonction.__doc__, phase)

    def _common(self, bloc: str) -> tuple[Any, dict[str, str]]:
        """Le bloc COMMON ``bloc`` et ses variables ``{nom: type f2py}`` (docstring du bloc)."""
        objet = getattr(self.bibliotheque, bloc, None)
        doc = getattr(objet, "__doc__", None) or ""
        variables = {m["nom"]: m["type"] for m in map(_LIGNE_TYPE.match, doc.splitlines()) if m}
        if objet is None or not variables:
            communs = sorted(n for n in dir(self.bibliotheque) if not n.startswith("_")
                             and " : " in (getattr(self.bibliotheque, n).__doc__ or "").strip().split("\n")[0])
            raise ErreurModele(
                f"{self.bibliotheque.__name__} n'a pas de COMMON « {bloc} » (COMMON : {', '.join(communs) or 'aucun'})"
            )
        return objet, variables

    def _sondes(self) -> dict[str, tuple[Any, bool]]:
        """``{variable: (bloc, réelle)}`` pour chaque bloc de ``SONDES``."""
        sondes: dict[str, tuple[Any, bool]] = {}
        for bloc in self.SONDES:
            objet, variables = self._common(bloc)
            for nom, type_ in variables.items():
                if "array" in type_:
                    raise ErreurModele(f"sonde {bloc}.{nom} : tableau ({type_}), une sonde est un scalaire")
                sondes[nom] = (objet, type_.startswith(("'d'", "'f'")))
        doublons = sorted(set(sondes) & set(self.signature_calcul.noms_sorties))
        if doublons:
            raise ErreurModele(f"sonde(s) homonyme(s) d'une sortie de {self.PHASE_CALCUL} : {', '.join(doublons)}")
        return sondes

    def lire(self, chemin: str) -> np.ndarray:
        """Copie d'une variable de COMMON : ``lire("aertab.tcx")``.

        Un tableau garde la forme et l'ordre des indices du Fortran : ``TCX(NM, NA)``
        donne un tableau ``(NM, NA)``, ``[i, j]`` étant ``TCX(I+1, J+1)``.
        """
        bloc, _, variable = chemin.lower().partition(".")
        objet, variables = self._common(bloc)
        if variable not in variables:
            raise ErreurModele(f"COMMON {bloc} : pas de variable « {variable} » ({', '.join(variables)})")
        return np.array(getattr(objet, variable), copy=True)

    @property
    def arguments_init(self) -> tuple[str, ...]:
        """Entrées des phases d'init, dans l'ordre d'appel, sans doublon."""
        return tuple(dict.fromkeys(n for s in self.signatures_init for n in s.noms_entrees))

    @property
    def arguments_calcul(self) -> tuple[str, ...]:
        return self.signature_calcul.noms_entrees

    @property
    def colonnes_entree(self) -> tuple[str, ...]:
        """Colonnes reconnues par ``calculer_df`` : init puis calcul, dans l'ordre des phases."""
        return tuple(dict.fromkeys(self.arguments_init + self.arguments_calcul))

    def decrire(self) -> str:
        """Les phases telles que f2py les expose, et les constantes en vigueur."""
        lignes = [f"Bibliothèque {self.bibliotheque.__name__}"]
        for s in self.signatures_init:
            lignes.append(f"  init    {s}")
        lignes.append(f"  calcul  {self.signature_calcul}")
        if self.sondes:
            lignes.append(f"  sondes  {', '.join(self.sondes)}")
        if self.arguments_init:
            valeurs = ", ".join(f"{n}={getattr(self, n, '?')!r}" for n in self.arguments_init)
            lignes.append(f"  constantes : {valeurs}")
        return "\n".join(lignes)

    def __repr__(self) -> str:
        valeurs = ", ".join(f"{n}={getattr(self, n, '?')!r}" for n in self.arguments_init)
        return f"{type(self).__name__}({self.bibliotheque.__name__}, {valeurs})"

    # -- appels ------------------------------------------------------------

    def _arguments(self, signature: Signature) -> dict[str, Any]:
        """Les mots-clés de l'appel, pris dans les attributs de l'objet."""
        args: dict[str, Any] = {}
        manquants = []
        for a in signature.entrees:
            if hasattr(self, a.nom):
                args[a.nom] = getattr(self, a.nom)
            elif not a.optionnel:
                manquants.append(a.nom)
        if manquants:
            raise ErreurModele(f"{signature.nom} : argument(s) non renseigné(s) : {', '.join(manquants)}")
        return args

    @staticmethod
    def _nommer(signature: Signature, brut: Any) -> dict[str, Any]:
        """Associe la valeur rendue par f2py aux noms de sortie."""
        noms = signature.noms_sorties
        if not noms:
            return {}
        valeurs = (brut,) if len(noms) == 1 else tuple(brut)
        return dict(zip(noms, valeurs))

    def _cle_init(self) -> tuple[tuple[str, tuple[Any, ...]], ...]:
        return tuple((s.nom, tuple(self._arguments(s).values())) for s in self.signatures_init)

    def initialiser(self) -> dict[str, dict[str, Any]]:
        """Appelle les phases d'init dans l'ordre, avec les attributs courants.

        Rend les sorties de chaque phase ; lève ``ErreurModele`` si l'une signale
        une erreur (``verifier_init``).
        """
        rendus: dict[str, dict[str, Any]] = {}
        _INIT_COURANTE.pop(self.bibliotheque.__name__, None)
        for s in self.signatures_init:
            sorties = self._nommer(s, getattr(self.bibliotheque, s.nom)(**self._arguments(s)))
            self.verifier_init(s, sorties)
            rendus[s.nom] = sorties
        _INIT_COURANTE[self.bibliotheque.__name__] = self._cle_init()
        return rendus

    def verifier_init(self, signature: Signature, sorties: Mapping[str, Any]) -> None:
        """Lève ``ErreurModele`` si la phase d'init a échoué. À surcharger au besoin.

        Par défaut : la sortie ``SORTIE_ERREUR_INIT`` (``ierr``), si la phase en a
        une, doit valoir 0.
        """
        nom = self.SORTIE_ERREUR_INIT
        if nom is not None and nom in sorties and int(sorties[nom]) != 0:
            args = ", ".join(f"{k}={v!r}" for k, v in self._arguments(signature).items())
            raise ErreurModele(f"{signature.nom}({args}) : {nom} = {int(sorties[nom])}")

    def _assurer_init(self) -> None:
        if _INIT_COURANTE.get(self.bibliotheque.__name__) != self._cle_init():
            self.initialiser()

    def calculer(self, **point: Any) -> dict[str, Any]:
        """Un point : les mots-clés deviennent des attributs, puis la phase de calcul est appelée.

        Rend ``{sortie: valeur}`` (aussi gardé dans ``self.resultat``). Un argument
        d'init passé ici déclenche une nouvelle initialisation.
        """
        inconnus = sorted(set(point) - set(self.colonnes_entree))
        if inconnus:
            raise ErreurModele(
                f"{', '.join(inconnus)} : pas un argument du modèle ({', '.join(self.colonnes_entree)})"
            )
        for nom, valeur in point.items():
            setattr(self, nom, valeur)
        self._assurer_init()
        s = self.signature_calcul
        for nom, (bloc, reelle) in self.sondes.items():
            if reelle:
                setattr(bloc, nom, np.nan)
        self.resultat = self._nommer(s, getattr(self.bibliotheque, s.nom)(**self._arguments(s)))
        for nom, (bloc, _) in self.sondes.items():
            self.resultat[nom] = np.asarray(getattr(bloc, nom)).item()
        return self.resultat

    # -- DataFrame ---------------------------------------------------------

    def calculer_df(self, entrees: pd.DataFrame) -> pd.DataFrame:
        """Une ligne par point : rend le DataFrame d'entrée augmenté des sorties.

        Colonnes lues : celles qui portent le nom d'un argument (``colonnes_entree``).
        Les arguments de calcul sont obligatoires ; ceux d'init sont facultatifs
        (absents : la valeur de l'attribut ; présents : réinitialisation à chaque
        changement de valeur). Les autres colonnes sont recopiées telles quelles.
        Les sorties sont ajoutées dans l'ordre de la docstring, puis les sondes ;
        une sortie tableau devient ``nom_1 … nom_n``.
        """
        s = self.signature_calcul
        tableaux = [a.nom for a in s.entrees if a.tableau]
        if tableaux:
            raise ErreurModele(f"{s.nom} : entrée(s) tableau, pas de colonne possible : {', '.join(tableaux)}")
        manquantes = [a.nom for a in s.entrees if not a.optionnel and a.nom not in entrees.columns]
        if manquantes:
            raise ErreurModele(
                f"colonne(s) absente(s) : {', '.join(manquantes)} "
                f"(attendues : {', '.join(self.colonnes_entree)})"
            )
        lues = [n for n in self.colonnes_entree if n in entrees.columns]
        types = {a.nom: a for sig in (*self.signatures_init, s) for a in sig.entrees}
        sauvegarde = {n: getattr(self, n) for n in self.arguments_init if hasattr(self, n)}

        colonnes: dict[str, list[Any]] = {}
        try:
            for numero, valeurs in enumerate(zip(*(entrees[n].tolist() for n in lues))):
                point = {n: _convertir(types[n], v, numero) for n, v in zip(lues, valeurs)}
                for nom, valeur in _aplatir(self.calculer(**point)).items():
                    colonnes.setdefault(nom, []).append(valeur)
        finally:
            for nom, valeur in sauvegarde.items():
                setattr(self, nom, valeur)

        if not colonnes:  # DataFrame vide : colonnes de sortie quand même
            colonnes = {n: [] for n in (*s.noms_sorties, *self.sondes)}
        doublons = sorted(set(colonnes) & set(entrees.columns))
        if doublons:
            raise ErreurModele(f"colonne(s) de sortie déjà présentes en entrée : {', '.join(doublons)}")
        sortie = entrees.copy()
        for nom, liste in colonnes.items():
            dtype = "float64" if self.sondes.get(nom, (None, False))[1] else _dtype(s, nom)
            sortie[nom] = pd.Series(liste, index=entrees.index, dtype=dtype)
        return sortie


def _convertir(argument: Argument, valeur: Any, numero: int) -> Any:
    """Valeur de cellule → type attendu par f2py ; refuse un entier non entier."""
    if argument.entier:
        if isinstance(valeur, float) and not (math.isfinite(valeur) and valeur.is_integer()):
            raise ErreurModele(f"ligne {numero} : {argument.nom} = {valeur!r} n'est pas un entier")
        return int(valeur)
    if argument.reel:
        return float(valeur)
    return valeur


def _aplatir(sorties: Mapping[str, Any]) -> dict[str, Any]:
    """Une sortie tableau devient nom_1 … nom_n ; un scalaire numpy devient Python."""
    plat: dict[str, Any] = {}
    for nom, valeur in sorties.items():
        if isinstance(valeur, np.ndarray) and valeur.ndim > 0:
            for k, v in enumerate(valeur.ravel().tolist(), start=1):
                plat[f"{nom}_{k}"] = v
        else:
            plat[nom] = valeur.item() if isinstance(valeur, np.generic) else valeur
    return plat


def _dtype(signature: Signature, nom: str) -> str | None:
    """int64 pour une sortie entière, float64 pour une réelle, sinon déduit (tableau aplati)."""
    for a in signature.sorties:
        if a.nom == nom:
            return "int64" if a.entier else "float64" if a.reel else None
    return None
