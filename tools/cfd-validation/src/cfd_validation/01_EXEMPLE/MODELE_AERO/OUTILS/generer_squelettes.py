#!/usr/bin/env python3
"""Génère, depuis le module f2py compilé, les blocs à copier-coller pour un nouveau code.

    python OUTILS/generer_squelettes.py --module moncode --calcul moncal --init monini moncfg
    python OUTILS/generer_squelettes.py --module aerolib --depuis modele_aero:ModeleAero
    python OUTILS/generer_squelettes.py --module moncode            # liste les routines, puis s'arrête

Trois blocs, chacun précédé de l'endroit où le coller :

1. **l'en-tête de la classe** (``PYTHON/modele_<code>.py``) : ``BIBLIOTHEQUE``,
   ``PHASES_INIT``, ``PHASE_CALCUL``, ``SONDES`` ;
2. **les valeurs par défaut** (même classe) : ``DEFAUTS`` pour les arguments des
   phases d'init, ``DEFAUTS_CALCUL`` pour ceux du calcul — une ligne par
   argument, groupées par phase, avec son type f2py ; la validation les reprend
   telles quelles (``VALIDATION/tables_modele.py``) ;
3. **un fichier de points de vol** (``PYTHON/<nom>.yaml``) pour
   ``calcul_yaml.py`` en arguments Fortran : tous les arguments du calcul dans
   ``commun``, ceux de l'init en commentaire (facultatifs).

Rien n'est écrit à la main : noms, ordre et types viennent des docstrings que
f2py génère, comme pour ``ModeleF2py``. Les valeurs sont celles de la classe
donnée par ``--depuis`` quand elle en a ; sinon 0 ou 0.0 selon le type, marqués
``À RENSEIGNER`` (le décompte est affiché à la fin : un 0 oublié est plausible,
donc dangereux).

Avec ``--depuis``, la classe existante est aussi **vérifiée** contre le module :
phases, sondes, clés hors de leur phase, arguments sans valeur, entier donné en
réel. Code de sortie 1 si un problème est trouvé.

``--sortie DOSSIER`` écrit aussi les blocs dans ``classe.py`` et ``pdv.yaml``.
"""

from __future__ import annotations

import argparse
import importlib
import sys
import textwrap
from pathlib import Path
from typing import Any

ICI = Path(__file__).resolve().parent
PYTHON = ICI.parent / "PYTHON"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

from modele_f2py import Argument, ErreurModele, ModeleF2py, Signature, importer_bibliotheque  # noqa: E402

A_RENSEIGNER = "À RENSEIGNER"


# --------------------------------------------------------------------------
# Lecture du module
# --------------------------------------------------------------------------


def routines(module: Any) -> dict[str, Signature]:
    """Les routines exposées par f2py, avec leur signature (les COMMON exclus)."""
    trouvees: dict[str, Signature] = {}
    for nom in sorted(n for n in dir(module) if not n.startswith("_")):
        doc = (getattr(module, nom).__doc__ or "").strip()
        if not doc or " : " in doc.splitlines()[0]:  # « var : type » : un COMMON
            continue
        try:
            trouvees[nom] = Signature.depuis_doc(doc, nom)
        except ErreurModele:
            continue
    return trouvees


def communs(module: Any) -> dict[str, dict[str, str]]:
    """``{bloc: {variable: type f2py}}`` pour chaque COMMON du module."""
    blocs: dict[str, dict[str, str]] = {}
    for nom in sorted(n for n in dir(module) if not n.startswith("_")):
        doc = (getattr(module, nom).__doc__ or "").strip()
        if doc and " : " in doc.splitlines()[0]:
            blocs[nom] = dict(ligne.split(" : ", 1) for ligne in doc.splitlines() if " : " in ligne)
    return blocs


def blocs_de_sondes(blocs: dict[str, dict[str, str]]) -> list[str]:
    """Les COMMON candidats aux sondes : que des scalaires réels."""
    return [b for b, v in blocs.items() if v and all("scalar" in t and t.startswith(("'d'", "'f'")) for t in v.values())]


# --------------------------------------------------------------------------
# Blocs
# --------------------------------------------------------------------------


def _valeur_par_type(a: Argument) -> Any:
    return 0 if a.entier else 0.0


def _type(a: Argument) -> str:
    """« input float » → « float » : le type, sans l'intention f2py."""
    return a.type.replace("input ", "").strip() or "?"


def _litteral(v: Any) -> str:
    return repr(float(v)) if isinstance(v, float) else repr(v)


def _lignes_defauts(attribut: str, signatures: list[Signature], valeurs: dict[str, Any],
                    deja: set[str], commentaire: str) -> tuple[list[str], int]:
    """``ATTRIBUT = {...}`` groupé par phase ; rend les lignes et le nombre de valeurs à renseigner."""
    lignes = [f"    #: {commentaire}", f"    {attribut}: ClassVar[dict[str, Any]] = {{"]
    manquantes = 0
    for s in signatures:
        lignes.append(f"        # {s}")
        for a in s.entrees:
            if a.nom in deja:
                lignes.append(f"        # {a.nom} : déjà dans une phase précédente")
                continue
            deja.add(a.nom)
            if a.optionnel:
                lignes.append(f"        # {a.nom} : dimension déduite par f2py, pas de valeur")
                continue
            if a.tableau:
                lignes.append(f"        # {a.nom} : tableau ({a.type}), pas de colonne possible")
                continue
            if a.nom in valeurs:
                v, note = valeurs[a.nom], ""
            else:
                v, note = _valeur_par_type(a), f"  {A_RENSEIGNER}"
                manquantes += 1
            lignes.append(f"        {a.nom!r}: {_litteral(v)},  # {_type(a)}{note}")
    lignes.append("    }")
    return lignes, manquantes


def bloc_classe(nom_module: str, init: list[Signature], calcul: Signature, sondes: list[str],
                valeurs: dict[str, Any]) -> tuple[str, int]:
    """En-tête de classe et valeurs par défaut ; rend le texte et le nombre de valeurs à renseigner."""
    deja: set[str] = set()
    lignes = [
        f"    BIBLIOTHEQUE: ClassVar[str] = {nom_module!r}",
        f"    PHASES_INIT: ClassVar[tuple[str, ...]] = {tuple(s.nom for s in init)!r}",
        f"    PHASE_CALCUL: ClassVar[str] = {calcul.nom!r}",
        f"    SONDES: ClassVar[tuple[str, ...]] = {tuple(sondes)!r}"
        + ("" if sondes else "  # aucun COMMON de scalaires réels : code pas encore sondé"),
        "",
    ]
    l_init, m_init = _lignes_defauts(
        "DEFAUTS", init, valeurs, deja,
        "Phases d'init : prises par les calculs quand la colonne est absente.")
    l_calc, m_calc = _lignes_defauts(
        "DEFAUTS_CALCUL", [calcul], valeurs, deja,
        "Phase de calcul : jamais utilisées pour calculer ; le point de la validation.")
    return "\n".join([*lignes, *l_init, "", *l_calc]) + "\n", m_init + m_calc


def bloc_yaml(nom_module: str, init: list[Signature], calcul: Signature, valeurs: dict[str, Any]) -> str:
    """Un fichier de points de vol complet pour calcul_yaml.py, en arguments Fortran."""
    def val(a: Argument) -> str:
        if a.nom not in valeurs:
            return f"{_litteral(_valeur_par_type(a))}    # {A_RENSEIGNER}"
        v = valeurs[a.nom]
        return repr(float(v)) if isinstance(v, float) else str(v)

    scalaires = [a for a in calcul.entrees if not a.optionnel and not a.tableau]
    lignes = [
        f"# Points de vol de {nom_module} : python calcul_yaml.py <ce fichier>",
        "# (généré par OUTILS/generer_squelettes.py — valeurs à ajuster)",
        "fonction: calcul_aero_elementaire   # arguments Fortran tels quels",
        "sortie: SORTIE/pdv.csv",
        "sondes: false                       # true : sorties sondées en plus",
        "",
        "commun:",
        f"  # {calcul.nom}({', '.join(calcul.noms_entrees)}) : tous obligatoires",
        *(f"  {a.nom}: {val(a)}" for a in scalaires),
    ]
    init_scal = [a for s in init for a in s.entrees if not a.optionnel and not a.tableau]
    if init_scal:
        lignes.append(f"  # {', '.join(s.nom for s in init)} : facultatifs (DEFAUTS du modèle si absents)")
        lignes += [f"  # {a.nom}: {val(a)}" for a in dict((a.nom, a) for a in init_scal).values()]
    premier = scalaires[0].nom if scalaires else "x"
    second = scalaires[1].nom if len(scalaires) > 1 else premier
    lignes += [
        "",
        "pdv:",
        "  - nom: point_de_reference       # les valeurs de « commun » seules",
        "",
        f"  - nom: balayage_{premier}",
        f"    {premier}: {{de: 0, a: 1, n: 5}}    # une plage en n points (ou {{de, a, pas}}) — bornes à ajuster",
        f"    # {second}: [0.0, 1.0]           # une liste ; le bloc est le produit croisé",
    ]
    return "\n".join(lignes) + "\n"


# --------------------------------------------------------------------------
# Vérification d'une classe existante
# --------------------------------------------------------------------------


def verifier_classe(classe: type[ModeleF2py], module: Any) -> list[str]:
    """Ce qui ne va pas entre la classe et le module ; liste vide si tout va."""
    try:
        modele = classe(module, sondes=True)
    except ErreurModele as erreur:
        return [str(erreur)]
    problemes = []
    complets = classe.defauts_complets()
    manquants = [n for n in modele.colonnes_obligatoires if n not in complets]
    if manquants:
        problemes.append(f"sans valeur par défaut : {', '.join(manquants)}")
    types = {a.nom: a for s in (*modele.signatures_init, modele.signature_calcul) for a in s.entrees}
    for nom, v in complets.items():
        a = types.get(nom)
        if a is not None and a.entier and isinstance(v, float) and not v.is_integer():
            problemes.append(f"{nom} : entier pour f2py, {v!r} donné")
    sondes_possibles = blocs_de_sondes(communs(module))
    if not classe.SONDES and sondes_possibles:
        problemes.append(f"SONDES vide, mais le module a des COMMON de sondes : {', '.join(sondes_possibles)}")
    return problemes


# --------------------------------------------------------------------------


def _charger_classe(spec: str) -> type[ModeleF2py]:
    nom_module, _, nom_classe = spec.partition(":")
    if not nom_classe:
        raise SystemExit(f"--depuis {spec!r} : écrire module:Classe (ex. modele_aero:ModeleAero)")
    classe = getattr(importlib.import_module(nom_module), nom_classe)
    if not (isinstance(classe, type) and issubclass(classe, ModeleF2py)):
        raise SystemExit(f"{spec} n'est pas une sous-classe de ModeleF2py")
    return classe


def _titre(texte: str) -> str:
    return f"# {'-' * 4} {texte} {'-' * max(4, 72 - len(texte))}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--module", required=True, help="module f2py (celui de construire.sh)")
    p.add_argument("--dossier", type=Path, default=PYTHON, help="où chercher le module (défaut PYTHON/)")
    p.add_argument("--calcul", help="phase de calcul (défaut : celle de --depuis)")
    p.add_argument("--init", nargs="*", default=None, help="phases d'init, dans l'ordre d'appel")
    p.add_argument("--depuis", help="classe existante module:Classe — ses phases et valeurs, et sa vérification")
    p.add_argument("--sortie", type=Path, help="écrire aussi classe.py et pdv.yaml dans ce dossier")
    args = p.parse_args(argv)

    try:
        module = importer_bibliotheque(args.module, args.dossier)
    except ModuleNotFoundError as erreur:
        print(f"erreur : {erreur}", file=sys.stderr)
        return 1
    disponibles = routines(module)
    classe = _charger_classe(args.depuis) if args.depuis else None
    calcul = args.calcul or (classe.PHASE_CALCUL if classe else None)
    init = args.init if args.init is not None else list(classe.PHASES_INIT) if classe else []
    if not calcul:
        print(f"Routines de {args.module} — choisir --calcul (et --init, dans l'ordre d'appel) :")
        for s in disponibles.values():
            print(f"  {s}")
        return 1
    inconnues = [n for n in (calcul, *init) if n not in disponibles]
    if inconnues:
        print(f"erreur : {', '.join(inconnues)} : pas une routine de {args.module} "
              f"({', '.join(disponibles)})", file=sys.stderr)
        return 1

    blocs = communs(module)
    sondes = list(classe.SONDES) if classe else blocs_de_sondes(blocs)
    valeurs = classe.defauts_complets() if classe else {}
    sig_init = [disponibles[n] for n in init]
    texte_classe, a_renseigner = bloc_classe(args.module, sig_init, disponibles[calcul], sondes, valeurs)
    texte_yaml = bloc_yaml(args.module, sig_init, disponibles[calcul], valeurs)

    print(_titre("1-2. PYTHON/modele_<code>.py, dans la classe (sous-classe de ModeleF2py)"))
    print("#   imports : from typing import Any, ClassVar")
    print(texte_classe)
    print(_titre("3. PYTHON/<nom>.yaml, fichier entier (python calcul_yaml.py <nom>.yaml)"))
    print(texte_yaml)
    if blocs:
        print(_titre("COMMON du module (tables : lire(\"bloc.var\") dans tables_modele.py)"))
        for b, variables in blocs.items():
            texte = f"{b} : " + ", ".join(f"{v} {t}" for v, t in variables.items())
            print(textwrap.fill(texte, 100, initial_indent="#   ", subsequent_indent="#       "))
        print()

    if args.sortie:
        args.sortie.mkdir(parents=True, exist_ok=True)
        (args.sortie / "classe.py").write_text(texte_classe, encoding="utf-8")
        (args.sortie / "pdv.yaml").write_text(texte_yaml, encoding="utf-8")
        print(f"écrit {args.sortie / 'classe.py'} et {args.sortie / 'pdv.yaml'}")

    code = 0
    if a_renseigner:
        print(f"{a_renseigner} valeur(s) à renseigner (marquées « {A_RENSEIGNER} »)", file=sys.stderr)
    if classe is not None:
        problemes = verifier_classe(classe, module)
        for probleme in problemes:
            print(f"✗ {args.depuis} : {probleme}", file=sys.stderr)
        if not problemes:
            print(f"✓ {args.depuis} cohérente avec {args.module}", file=sys.stderr)
        code = 1 if problemes else 0
    return code


if __name__ == "__main__":
    sys.exit(main())
