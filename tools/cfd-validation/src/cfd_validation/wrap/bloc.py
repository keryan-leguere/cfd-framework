"""Lire une table dans un COMMON block Fortran exposé par f2py.

Le seul contrat exigé du module enveloppé est un accès par attribut ::

    module.<bloc>.<tableau>  ->  ndarray

C'est exactement ce que f2py produit pour un ``COMMON /TAB_CN/ TAB_CN``, et
c'est délibérément *tout* ce que ce paquet regarde. La conséquence est
structurante : un objet Python quelconque portant les mêmes attributs fait
l'affaire, donc la totalité du paquet se teste **sans compilateur**, sur un
faux module — de la même façon que l'adaptateur ``mock`` du framework bash
existe pour que les tests ne réclament pas OpenFOAM.

f2py met les noms en minuscules. On résout donc sans tenir compte de la casse,
et quand un nom manque on **liste ce que le module expose réellement** : c'est
la seule information utile à ce moment-là, et elle évite un aller-retour.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from cfd_validation.data.spec import SpecTable

__all__ = [
    "ErreurBloc",
    "blocs_exposes",
    "lire_table",
    "lire_tableau",
]


class ErreurBloc(ValueError):
    """Le module ne porte pas la table qu'on lui demande, ou pas sous cette forme."""


def blocs_exposes(module: Any) -> dict[str, tuple[str, ...]]:
    """Les COMMON blocks du module et, pour chacun, ses tableaux.

    Sert au message d'erreur et à ``cfd-validation inspecter`` — la première
    chose à faire devant un module inconnu est de regarder ce qu'il donne.
    """
    blocs: dict[str, tuple[str, ...]] = {}
    for nom in _membres(module):
        objet = getattr(module, nom, None)
        if objet is None or isinstance(objet, np.ndarray):
            continue
        # Un COMMON block f2py est **appelable** — il a le même type que les
        # routines — donc on ne peut pas l'en distinguer là-dessus. Ce qui les
        # sépare est ce qu'ils portent : un bloc porte des tableaux, une
        # routine ne porte qu'elle-même.
        membres = tuple(
            membre
            for membre in _membres(objet)
            if isinstance(getattr(objet, membre, None), np.ndarray)
        )
        if membres:
            blocs[nom] = membres
    return blocs


def lire_tableau(module: Any, spec: SpecTable) -> npt.NDArray[np.float64]:
    """Le tableau brut d'une table, orienté en lignes et rogné à sa longueur utile."""
    bloc = _attribut(module, spec.bloc, quoi="COMMON block", contexte=spec.nom)
    brut = _attribut(bloc, spec.tableau, quoi="tableau", contexte=spec.nom)
    if not isinstance(brut, np.ndarray):
        raise ErreurBloc(
            f"table « {spec.nom} » : {spec.bloc}.{spec.tableau} n'est pas un tableau "
            f"(type {type(brut).__name__})."
        )

    tableau = np.asarray(brut, dtype=np.float64)
    tableau = _orienter(tableau, spec)
    lignes = _lignes_utiles(module, bloc, spec, disponibles=tableau.shape[0])
    return np.ascontiguousarray(tableau[:lignes])


def lire_table(module: Any, spec: SpecTable) -> pd.DataFrame:
    """La table, en cadre de données nommé par ``colonnes``."""
    tableau = lire_tableau(module, spec)
    return pd.DataFrame(tableau, columns=list(spec.colonnes))


# ---------------------------------------------------------------------------
# Résolution des noms
# ---------------------------------------------------------------------------


def _membres(objet: Any) -> tuple[str, ...]:
    """Les attributs publics d'un objet, y compris ceux d'un objet f2py.

    ``dir()`` suffit pour un module d'extension comme pour un faux module en
    Python pur ; ``vars()`` le complète pour les objets qui n'exposent pas
    ``__dir__`` utilement.
    """
    noms: list[str] = []
    for source in (dir(objet), getattr(objet, "__dict__", {}) or {}):
        for nom in source:
            if not nom.startswith("_") and nom not in noms:
                noms.append(nom)
    return tuple(noms)


def _attribut(objet: Any, nom: str, *, quoi: str, contexte: str) -> Any:
    """Un attribut, résolu sans tenir compte de la casse."""
    trouve = getattr(objet, nom, None)
    if trouve is not None:
        return trouve
    minuscule = nom.lower()
    for candidat in _membres(objet):
        if candidat.lower() == minuscule:
            return getattr(objet, candidat)
    raise ErreurBloc(
        f"table « {contexte} » : {quoi} « {nom} » introuvable. "
        f"Exposé(s) : {sorted(_membres(objet)) or '— rien —'}."
    )


# ---------------------------------------------------------------------------
# Forme du tableau
# ---------------------------------------------------------------------------


def _orienter(tableau: npt.NDArray[np.float64], spec: SpecTable) -> npt.NDArray[np.float64]:
    """Ramène le tableau à « une ligne = un point »."""
    attendues = len(spec.colonnes)

    if tableau.ndim == 1:
        if attendues != 1:
            raise ErreurBloc(
                f"table « {spec.nom} » : {spec.bloc}.{spec.tableau} est un vecteur de "
                f"{tableau.size} valeurs, mais {attendues} colonnes sont déclarées."
            )
        return tableau.reshape(-1, 1)

    if tableau.ndim != 2:
        raise ErreurBloc(
            f"table « {spec.nom} » : {spec.bloc}.{spec.tableau} a {tableau.ndim} dimensions. "
            "Ce contrôle lit une table « longue » : un tableau 2-D, une ligne par point."
        )

    hauteur, largeur = tableau.shape
    if spec.orientation == "lignes":
        oriente = tableau
    elif spec.orientation == "colonnes":
        oriente = tableau.T
    elif largeur == attendues and hauteur != attendues:
        oriente = tableau
    elif hauteur == attendues and largeur != attendues:
        oriente = tableau.T
    elif hauteur == attendues and largeur == attendues:
        raise ErreurBloc(
            f"table « {spec.nom} » : {spec.bloc}.{spec.tableau} est carré ({hauteur}×{largeur}) "
            f"et porte autant de colonnes que déclaré. Déclarez « orientation » "
            f"(« lignes » ou « colonnes ») : le deviner reviendrait à tirer au sort "
            "la lecture de toute la table."
        )
    else:
        raise ErreurBloc(
            f"table « {spec.nom} » : {spec.bloc}.{spec.tableau} est de forme "
            f"{hauteur}×{largeur}, et ni l'une ni l'autre dimension ne vaut les "
            f"{attendues} colonnes déclarées {list(spec.colonnes)}."
        )

    if oriente.shape[1] != attendues:  # pragma: no cover - couvert par les branches ci-dessus
        raise ErreurBloc(
            f"table « {spec.nom} » : après orientation, {oriente.shape[1]} colonnes "
            f"pour {attendues} déclarées."
        )
    return oriente


def _lignes_utiles(module: Any, bloc: Any, spec: SpecTable, *, disponibles: int) -> int:
    """Combien de lignes du tableau sont réellement renseignées."""
    if spec.lignes is None:
        return disponibles
    if isinstance(spec.lignes, int):
        valeur = spec.lignes
    else:
        valeur = _entier(module, bloc, spec.lignes, spec)
    if valeur <= 0:
        raise ErreurBloc(
            f"table « {spec.nom} » : « lignes » vaut {valeur}, "
            "donc la table serait vide. Le compteur a-t-il été initialisé ?"
        )
    if valeur > disponibles:
        raise ErreurBloc(
            f"table « {spec.nom} » : « lignes » vaut {valeur}, "
            f"mais le tableau n'en porte que {disponibles}."
        )
    return valeur


def _entier(module: Any, bloc: Any, nom: str, spec: SpecTable) -> int:
    """Un compteur, cherché d'abord dans le bloc puis sur le module."""
    brut: Any | None = None
    for source in (bloc, module):
        try:
            brut = _attribut(source, nom, quoi="compteur", contexte=spec.nom)
        except ErreurBloc:
            continue
        break
    if brut is None:
        raise ErreurBloc(
            f"table « {spec.nom} » : compteur « {nom} » introuvable, "
            f"ni dans le COMMON block « {spec.bloc} » ni sur le module."
        )
    tableau = np.asarray(brut)
    if tableau.size != 1:
        raise ErreurBloc(
            f"table « {spec.nom} » : le compteur « {nom} » porte {tableau.size} valeurs, "
            "attendu un entier."
        )
    return int(tableau.reshape(-1)[0])
