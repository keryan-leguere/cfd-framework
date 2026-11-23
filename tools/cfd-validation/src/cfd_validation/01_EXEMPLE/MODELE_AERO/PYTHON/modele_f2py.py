"""Encapsulation générique d'un code Fortran à phases (ENTRY) compilé par f2py.

Rien ici ne connaît le modèle aéro. Une sous-classe désigne le module et ses
phases (voir ``modele_aero.py``)::

    class MonCode(ModeleF2py):
        BIBLIOTHEQUE = "moncode"            # module produit par construire.sh
        PHASES_INIT = ("monini", "moncfg")  # appelées dans l'ordre, avant le calcul (sans code de retour)
        PHASE_CALCUL = "moncal"             # appelée à chaque point

et ajoute par-dessus ce qui est propre au code (conversions, sorties en plus).

Les noms d'arguments ne sont écrits nulle part : ils sont lus dans la
docstring que f2py génère pour chaque phase (``bibliotheque.moncal.__doc__``),
en minuscules, dans l'ordre d'appel. Ce sont eux qui deviennent les colonnes
du DataFrame d'entrée de ``calcul_elementaire`` — **tous**, ceux des phases
d'init compris : l'objet ne garde aucune valeur d'argument, il n'y a pas de
constante cachée. Les phases d'init sont rappelées quand une ligne change
leurs valeurs.

**Sondes** (``SONDES = ("probe",)``) : blocs COMMON que le code remplit en
cours de calcul pour la validation (une valeur lue dans une table, avant que le
code la transforme). Leurs variables réelles sont remises à NaN avant chaque
appel, puis rendues avec les sorties, sous leur nom f2py (``valid_tab_cx``) :
une sonde que l'appel n'a pas atteinte vaut NaN, jamais la valeur de l'appel
précédent. Les sondes sont **facultatives** : un code pas encore sondé n'a pas
de bloc, et ``sondes=`` à la construction dit quoi en faire — ``None`` (défaut)
lit les blocs de ``SONDES`` présents et ignore les absents (avertissement,
liste dans ``sondes_absentes``) ; ``True`` les exige tous (erreur sinon) ;
``False`` n'en lit aucun. ``lire("aertab.tcx")`` rend une copie de n'importe quelle variable
de COMMON — les tables et leurs grilles, telles que le code les voit.

**Valeurs par défaut** (facultatives, déclarées par la sous-classe) :
``DEFAUTS`` pour les arguments des phases d'init — ``completer_init`` en
remplit les colonnes absentes, à la sous-classe de l'appeler dans ses
calculs — et ``DEFAUTS_CALCUL`` pour ceux de la phase de calcul, **jamais
utilisés pour calculer** : un point de référence (« là où une table ne pilote
pas l'argument ») que la validation reprend par ``defauts_complets()``. Une
clé qui n'est pas un argument de la bonne phase est refusée à la construction.
``calcul_elementaire`` lui-même n'en prend aucune.

L'état Fortran (variables SAVE, COMMON) est **global au processus** : deux
objets sur la même bibliothèque partagent le même état. La dernière
initialisation faite sur chaque bibliothèque est suivie au niveau du module,
et refaite dès qu'un point en demande une autre.

Python 3.9+, numpy, pandas.
"""

from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import math
import re
import sys
import warnings
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
    "ecrire_csv",
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
    """Un code Fortran à phases, appelé sur un DataFrame qui porte **tous** ses arguments.

    Paramètres
    ----------
    bibliotheque
        Le module f2py, ou son nom (importé depuis ``dossier``). Défaut :
        ``BIBLIOTHEQUE`` de la sous-classe.
    dossier
        Où chercher le module par son nom. Défaut : ``DOSSIER`` de la
        sous-classe, sinon ``sys.path``.
    sondes
        ``None`` : les blocs de ``SONDES`` présents dans le module, les absents
        ignorés avec un avertissement (code pas encore sondé) ; ``True`` : tous
        exigés ; ``False`` : aucune sonde lue ni rendue.

    L'objet ne garde aucune valeur d'argument : construire l'objet charge le
    module et lit les signatures, rien de plus. Les phases d'init sont
    appelées par le calcul, avec les valeurs de la ligne.
    """

    BIBLIOTHEQUE: ClassVar[str] = ""
    DOSSIER: ClassVar[str | Path | None] = None
    PHASES_INIT: ClassVar[tuple[str, ...]] = ()
    PHASE_CALCUL: ClassVar[str] = ""
    # Blocs COMMON de sondes, lus après chaque calcul (voir le module).
    SONDES: ClassVar[tuple[str, ...]] = ()
    # Valeurs par défaut (voir le module) : init, complétées par completer_init ;
    # calcul, jamais utilisées pour calculer (point de référence de la validation).
    DEFAUTS: ClassVar[Mapping[str, Any]] = {}
    DEFAUTS_CALCUL: ClassVar[Mapping[str, Any]] = {}

    def __init__(
        self,
        bibliotheque: ModuleType | str | None = None,
        dossier: str | Path | None = None,
        *,
        sondes: bool | None = None,
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
        self.sondes_absentes: tuple[str, ...] = ()
        self.sondes = self._sondes(sondes)
        self._types = {a.nom: a for s in (*self.signatures_init, self.signature_calcul) for a in s.entrees}
        for attribut, phase, admis in (("DEFAUTS", "d'init", self.arguments_init),
                                       ("DEFAUTS_CALCUL", f"de {self.PHASE_CALCUL}", self.arguments_calcul)):
            intrus = sorted(set(getattr(self, attribut)) - set(admis))
            if intrus:
                raise ErreurModele(
                    f"{type(self).__name__}.{attribut} : {', '.join(intrus)} n'est pas un argument "
                    f"des phases {phase} ({', '.join(admis) or 'aucun'})"
                )

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

    def _sondes(self, mode: bool | None) -> dict[str, tuple[Any, bool]]:
        """``{variable: (bloc, réelle)}`` pour chaque bloc de ``SONDES`` retenu (voir ``sondes=``)."""
        sondes: dict[str, tuple[Any, bool]] = {}
        if mode is False:
            return sondes
        absents = []
        for bloc in self.SONDES:
            try:
                objet, variables = self._common(bloc)
            except ErreurModele:
                if mode:  # exigées : l'erreur dit quels COMMON existent
                    raise
                absents.append(bloc)
                continue
            for nom, type_ in variables.items():
                if "array" in type_:
                    raise ErreurModele(f"sonde {bloc}.{nom} : tableau ({type_}), une sonde est un scalaire")
                sondes[nom] = (objet, type_.startswith(("'d'", "'f'")))
        if absents:
            self.sondes_absentes = tuple(absents)
            warnings.warn(
                f"{self.bibliotheque.__name__} : pas de COMMON de sondes {', '.join(absents)} "
                "(code pas encore sondé ?) — calcul sans ces sondes",
                stacklevel=3,
            )
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
        """Colonnes lues par ``calcul_elementaire`` : init puis calcul, dans l'ordre des phases."""
        return tuple(dict.fromkeys(self.arguments_init + self.arguments_calcul))

    @property
    def colonnes_obligatoires(self) -> tuple[str, ...]:
        """Les arguments non optionnels pour f2py (les dimensions ``[n]`` qu'il déduit ne le sont pas)."""
        return tuple(n for n in self.colonnes_entree if not self._types[n].optionnel)

    @property
    def colonnes_sortie(self) -> tuple[str, ...]:
        """Sorties de la phase de calcul, puis sondes."""
        return (*self.signature_calcul.noms_sorties, *self.sondes)

    @classmethod
    def defauts_complets(cls) -> dict[str, Any]:
        """``DEFAUTS`` puis ``DEFAUTS_CALCUL`` : une valeur par argument, sans charger le module."""
        return {**cls.DEFAUTS, **cls.DEFAUTS_CALCUL}

    @property
    def defauts(self) -> dict[str, Any]:
        """``defauts_complets()`` dans l'ordre des colonnes ; erreur s'il manque un argument obligatoire."""
        complets = self.defauts_complets()
        manquants = [n for n in self.colonnes_obligatoires if n not in complets]
        if manquants:
            raise ErreurModele(
                f"{type(self).__name__} : pas de valeur par défaut pour {', '.join(manquants)} "
                "(DEFAUTS pour l'init, DEFAUTS_CALCUL pour le calcul)"
            )
        return {n: complets[n] for n in self.colonnes_entree if n in complets}

    def completer_init(self, entrees: pd.DataFrame) -> pd.DataFrame:
        """Arguments des phases d'init absents, ou vides sur une ligne : la valeur de ``DEFAUTS``."""
        df = entrees.copy()
        for nom in self.arguments_init:
            if nom in self.DEFAUTS:
                df[nom] = df[nom].fillna(self.DEFAUTS[nom]) if nom in df.columns else self.DEFAUTS[nom]
        return df

    def decrire(self) -> str:
        """Les phases telles que f2py les expose."""
        lignes = [f"Bibliothèque {self.bibliotheque.__name__}"]
        for s in self.signatures_init:
            lignes.append(f"  init    {s}")
        lignes.append(f"  calcul  {self.signature_calcul}")
        if self.sondes:
            lignes.append(f"  sondes  {', '.join(self.sondes)}")
        return "\n".join(lignes)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.bibliotheque.__name__})"

    # -- appels ------------------------------------------------------------

    @staticmethod
    def _nommer(signature: Signature, brut: Any) -> dict[str, Any]:
        """Associe la valeur rendue par f2py aux noms de sortie."""
        noms = signature.noms_sorties
        if not noms:
            return {}
        valeurs = (brut,) if len(noms) == 1 else tuple(brut)
        return dict(zip(noms, valeurs))

    @staticmethod
    def _arguments(signature: Signature, point: Mapping[str, Any]) -> dict[str, Any]:
        """Les mots-clés d'une phase, pris dans le point (les optionnels absents sont laissés à f2py)."""
        manquants = [a.nom for a in signature.entrees if not a.optionnel and a.nom not in point]
        if manquants:
            raise ErreurModele(f"{signature.nom} : argument(s) non renseigné(s) : {', '.join(manquants)}")
        return {a.nom: point[a.nom] for a in signature.entrees if a.nom in point}

    def _initialiser(self, point: Mapping[str, Any]) -> None:
        """Toutes les phases d'init, dans l'ordre, si l'une a changé d'arguments depuis la dernière init.

        Toutes, et pas seulement celle qui change : une phase peut remettre à
        zéro ce qu'une autre a posé, l'ordre d'appel est celui de ``PHASES_INIT``.
        """
        cle = tuple((s.nom, tuple(self._arguments(s, point).values())) for s in self.signatures_init)
        nom = self.bibliotheque.__name__
        if _INIT_COURANTE.get(nom) == cle:
            return
        _INIT_COURANTE.pop(nom, None)
        for s in self.signatures_init:  # pas de code de retour : une init refusée se lit au calcul
            getattr(self.bibliotheque, s.nom)(**self._arguments(s, point))
        _INIT_COURANTE[nom] = cle

    def calcul_point(self, **point: Any) -> dict[str, Any]:
        """Un point : ``{argument: valeur}`` pour tous les arguments, init compris.

        Les phases d'init sont appelées si leurs arguments diffèrent de la
        dernière init faite sur la bibliothèque, puis la phase de calcul. Rend
        ``{sortie: valeur}``, sondes comprises.
        """
        inconnus = sorted(set(point) - set(self.colonnes_entree))
        if inconnus:
            raise ErreurModele(
                f"{', '.join(inconnus)} : pas un argument du modèle ({', '.join(self.colonnes_entree)})"
            )
        self._initialiser(point)
        s = self.signature_calcul
        args = self._arguments(s, point)
        for nom, (bloc, reelle) in self.sondes.items():
            if reelle:
                setattr(bloc, nom, np.nan)
        resultat = self._nommer(s, getattr(self.bibliotheque, s.nom)(**args))
        for nom, (bloc, _) in self.sondes.items():
            resultat[nom] = np.asarray(getattr(bloc, nom)).item()
        return resultat

    # -- DataFrame ---------------------------------------------------------

    def calcul_elementaire(self, entrees: pd.DataFrame, *, csv: str | Path | None = None) -> pd.DataFrame:
        """Une ligne par point, **tous** les arguments Fortran en colonnes : rend l'entrée augmentée des sorties.

        Colonnes lues : ``colonnes_entree`` (init puis calcul), toutes
        obligatoires sauf les dimensions que f2py déduit. Les phases d'init sont
        rappelées quand une ligne change leurs valeurs : un DataFrame à constantes
        fixes ne les appelle qu'une fois. Les autres colonnes sont recopiées
        telles quelles. Les sorties sont ajoutées dans l'ordre de la docstring,
        puis les sondes ; une sortie tableau devient ``nom_1 … nom_n``.

        ``csv`` : écrit aussi le résultat dans ce fichier (``ecrire_csv``).
        """
        s = self.signature_calcul
        tableaux = [n for n in self.colonnes_entree if self._types[n].tableau]
        if tableaux:
            raise ErreurModele(f"entrée(s) tableau, pas de colonne possible : {', '.join(tableaux)}")
        manquantes = [n for n in self.colonnes_obligatoires if n not in entrees.columns]
        if manquantes:
            raise ErreurModele(
                f"colonne(s) absente(s) : {', '.join(manquantes)} "
                f"(attendues : {', '.join(self.colonnes_obligatoires)})"
            )
        doublons = sorted(set(self.colonnes_sortie) & set(entrees.columns))
        if doublons:
            raise ErreurModele(f"colonne(s) de sortie déjà présentes en entrée : {', '.join(doublons)}")
        lues = [n for n in self.colonnes_entree if n in entrees.columns]

        colonnes: dict[str, list[Any]] = {}
        for numero, valeurs in enumerate(zip(*(entrees[n].tolist() for n in lues))):
            point = {n: _convertir(self._types[n], v, numero) for n, v in zip(lues, valeurs)}
            for nom, valeur in _aplatir(self.calcul_point(**point)).items():
                colonnes.setdefault(nom, []).append(valeur)

        if not colonnes:  # DataFrame vide : colonnes de sortie quand même
            colonnes = {n: [] for n in self.colonnes_sortie}
        sortie = entrees.copy()
        for nom, liste in colonnes.items():
            dtype = "float64" if self.sondes.get(nom, (None, False))[1] else _dtype(s, nom)
            sortie[nom] = pd.Series(liste, index=entrees.index, dtype=dtype)
        if csv is not None:
            ecrire_csv(sortie, csv)
        return sortie


def ecrire_csv(df: pd.DataFrame, chemin: str | Path) -> Path:
    """Le DataFrame en CSV, relisible sans perte, dossier créé au besoin.

    Les réels sont écrits par ``repr`` (le défaut de pandas) : le plus court
    texte qui redonne le même double — ``0.8``, pas ``0.80000000000000004``.
    Relire avec ``pd.read_csv(…, float_precision="round_trip")`` avant pandas 3
    (son lecteur rapide par défaut peut se tromper d'un ULP) ; le défaut suffit après.

    L'index est écrit seulement s'il porte quelque chose (pas le 0, 1, 2… par
    défaut) : un ``set_index("cas")`` se retrouve en première colonne.
    """
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(chemin, index=not isinstance(df.index, pd.RangeIndex))
    return chemin


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
