"""Conditions écrites par l'utilisateur, évaluées sans ``eval``.

Un fichier de remplissage peut exclure des points : ``mach >= 2 and alpha > 10``.
L'expression est analysée (``ast``) et seul un sous-ensemble inoffensif est
admis : comparaisons, ``and`` / ``or`` / ``not``, arithmétique, ``abs``,
``min``, ``max``, nombres et noms de colonnes. Tout le reste — appels, attributs,
indices — est refusé à la lecture du fichier, pas à l'exécution.
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable, Mapping
from typing import Any

__all__ = ["Condition", "compiler"]

Condition = Callable[[Mapping[str, float]], bool]

_BINAIRES: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_COMPARAISONS: dict[type, Callable[[Any, Any], bool]] = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}
_FONCTIONS: dict[str, Callable[..., Any]] = {"abs": abs, "min": min, "max": max}


def compiler(texte: str, noms: frozenset[str]) -> Condition:
    """Compile ``texte`` en une fonction ``point -> bool``.

    ``noms`` : les colonnes utilisables. Un nom inconnu ou une construction non
    admise lève ``ValueError`` avec le texte fautif.
    """
    try:
        arbre = ast.parse(texte.strip(), mode="eval")
    except SyntaxError as erreur:
        raise ValueError(f"condition illisible : « {texte} » ({erreur.msg})") from None
    _verifier(arbre.body, texte, noms)

    def condition(point: Mapping[str, float]) -> bool:
        return bool(_evaluer(arbre.body, point))

    return condition


def _verifier(noeud: ast.AST, texte: str, noms: frozenset[str]) -> None:
    if isinstance(noeud, ast.Name):
        if noeud.id not in noms and noeud.id not in _FONCTIONS:
            admis = ", ".join(sorted(noms))
            raise ValueError(f"« {texte} » : nom inconnu « {noeud.id} » ; admis : {admis}")
        return
    if isinstance(noeud, ast.Constant):
        if not isinstance(noeud.value, (int, float)) or isinstance(noeud.value, bool):
            raise ValueError(f"« {texte} » : seules les constantes numériques sont admises")
        return
    if isinstance(noeud, ast.Call):
        if (
            not isinstance(noeud.func, ast.Name)
            or noeud.func.id not in _FONCTIONS
            or noeud.keywords
        ):
            raise ValueError(f"« {texte} » : fonctions admises : {', '.join(_FONCTIONS)}")
        for argument in noeud.args:
            _verifier(argument, texte, noms)
        return
    structures = (ast.BoolOp, ast.UnaryOp, ast.Compare, ast.BinOp)
    if isinstance(noeud, ast.BinOp) and type(noeud.op) not in _BINAIRES:
        raise ValueError(f"« {texte} » : opérateur non admis")
    if isinstance(noeud, ast.UnaryOp) and not isinstance(noeud.op, (ast.Not, ast.USub, ast.UAdd)):
        raise ValueError(f"« {texte} » : opérateur non admis")
    if isinstance(noeud, ast.Compare) and any(type(op) not in _COMPARAISONS for op in noeud.ops):
        raise ValueError(f"« {texte} » : comparaison non admise")
    if not isinstance(noeud, structures):
        raise ValueError(f"« {texte} » : construction non admise ({type(noeud).__name__})")
    for enfant in ast.iter_child_nodes(noeud):
        if not isinstance(enfant, (ast.operator, ast.boolop, ast.unaryop, ast.cmpop)):
            _verifier(enfant, texte, noms)


def _evaluer(noeud: ast.AST, point: Mapping[str, float]) -> Any:
    if isinstance(noeud, ast.Constant):
        return noeud.value
    if isinstance(noeud, ast.Name):
        return point[noeud.id]
    if isinstance(noeud, ast.BoolOp):
        valeurs = (_evaluer(v, point) for v in noeud.values)
        return all(valeurs) if isinstance(noeud.op, ast.And) else any(valeurs)
    if isinstance(noeud, ast.UnaryOp):
        valeur = _evaluer(noeud.operand, point)
        if isinstance(noeud.op, ast.Not):
            return not valeur
        return -valeur if isinstance(noeud.op, ast.USub) else valeur
    if isinstance(noeud, ast.BinOp):
        return _BINAIRES[type(noeud.op)](_evaluer(noeud.left, point), _evaluer(noeud.right, point))
    if isinstance(noeud, ast.Compare):
        gauche = _evaluer(noeud.left, point)
        for op, droite_noeud in zip(noeud.ops, noeud.comparators):
            droite = _evaluer(droite_noeud, point)
            if not _COMPARAISONS[type(op)](gauche, droite):
                return False
            gauche = droite
        return True
    assert isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name)
    return _FONCTIONS[noeud.func.id](*(_evaluer(a, point) for a in noeud.args))
