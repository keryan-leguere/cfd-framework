#!/usr/bin/env python3
"""Appeler le modèle aéro depuis un fichier YAML de points de vol ; résultat en CSV.

    python calcul_yaml.py exemple_pdv.yaml
    python calcul_yaml.py exemple_pdv.yaml --sortie /ailleurs/resultats.csv
    python calcul_yaml.py exemple_pdv.yaml --module aerolib_o3

Le fichier (voir ``exemple_pdv.yaml``) ::

    fonction: calcul_aero              # ou calcul_aero_elementaire (arguments Fortran)
    sortie: SORTIE/exemple_pdv.csv     # relatif au fichier YAML
    sondes: false                      # true : les sorties sondées (valid_tab_*) en plus
    commun:                            # valeurs communes à tous les blocs (facultatif)
      xg_mm: 1050.0
    pdv:                               # un bloc, ou une liste de blocs
      - nom: balayage_alpha            # facultatif : colonne « bloc » du CSV
        mach: [0.8, 1.2]               # une liste : chaque valeur
        alpha: {de: 0, a: 10, pas: 2}  # une plage : 0, 2, 4, 6, 8, 10
        beta: 0                        # un scalaire : constant

Chaque bloc est le **produit croisé** de ses clés (la dernière varie le plus
vite) ; les blocs sont mis bout à bout. Une plage s'écrit ``{de, a, pas}``
(bornes comprises, ``a`` atteint si l'écart est un multiple du pas) ou
``{de, a, n}`` (n valeurs régulières). Les noms de clés sont ceux de la
fonction appelée : ``ModeleAero.PARAMETRES`` pour ``calcul_aero``, les
arguments Fortran pour ``calcul_aero_elementaire`` — ceux des phases d'init
(``xref`` … ``lref``, ``biaicx``) facultatifs dans les deux cas : absents, ils
prennent ``ModeleAero.DEFAUTS``.

``sondes`` (booléen, défaut ``false``) : ``true`` ajoute au CSV les sorties
sondées (COMMON /PROBE/), et le code doit alors en avoir ; ``false`` ne les lit
pas, ce qui marche aussi sur un code pas encore sondé.
"""

from __future__ import annotations

import argparse
import itertools
import math
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np
import pandas as pd
import yaml
from modele_aero import ModeleAero
from modele_f2py import ErreurModele

FONCTIONS = ("calcul_aero", "calcul_aero_elementaire")
CLES = {"fonction", "sortie", "sondes", "commun", "pdv"}
CLES_PLAGE = ({"de", "a", "pas"}, {"de", "a", "n"})
#: Colonne du nom de bloc dans le CSV.
BLOC = "bloc"


class ErreurYaml(ValueError):
    """Le fichier de points de vol est mal formé ; le message dit où."""


class Pdv(NamedTuple):
    """Le fichier lu : quoi appeler, où écrire, avec ou sans sondes, et les points."""

    fonction: str
    sortie: Path
    df: pd.DataFrame
    sondes: bool = False


def valeurs(cle: str, spec: Any) -> list[Any]:
    """Un scalaire, une liste ou une plage → la liste des valeurs."""
    if isinstance(spec, list):
        if not spec:
            raise ErreurYaml(f"{cle} : liste vide")
        return spec
    if not isinstance(spec, Mapping):
        return [spec]
    if set(spec) not in CLES_PLAGE:
        raise ErreurYaml(f"{cle} : plage {dict(spec)} — écrire {{de, a, pas}} ou {{de, a, n}}")
    de, a = float(spec["de"]), float(spec["a"])
    if "n" in spec:
        n = int(spec["n"])
        if n < 1:
            raise ErreurYaml(f"{cle} : n = {n}, au moins 1")
        return np.linspace(de, a, n).tolist()
    pas = float(spec["pas"])
    if pas <= 0 or not math.isfinite(pas):
        raise ErreurYaml(f"{cle} : pas = {spec['pas']!r}, positif attendu")
    if a < de:
        raise ErreurYaml(f"{cle} : de = {de:g} > a = {a:g}")
    k = math.floor((a - de) / pas + 1e-9)  # bornes comprises, sans perdre « a » à l'arrondi près
    return [de + i * pas for i in range(k + 1)]


def bloc_vers_df(bloc: Mapping[str, Any], commun: Mapping[str, Any], numero: int) -> pd.DataFrame:
    """Un bloc de points de vol → le produit croisé de ses clés."""
    if not isinstance(bloc, Mapping):
        raise ErreurYaml(f"pdv[{numero}] : un dictionnaire de clés est attendu")
    tout = {**commun, **bloc}
    nom = str(tout.pop("nom", f"pdv_{numero + 1}"))
    cles = list(tout)
    listes = [valeurs(f"pdv[{numero}].{c}", tout[c]) for c in cles]
    df = pd.DataFrame(list(itertools.product(*listes)), columns=cles)
    df.insert(0, BLOC, nom)
    return df


def lire_pdv(chemin: Path) -> Pdv:
    """Le fichier YAML → fonction, fichier CSV de sortie, DataFrame des points, sondes ou non."""
    contenu = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    if not isinstance(contenu, Mapping):
        raise ErreurYaml(f"{chemin} : un dictionnaire est attendu à la racine")
    inconnues = sorted(set(contenu) - CLES)
    if inconnues:
        raise ErreurYaml(f"clé(s) inconnue(s) : {', '.join(inconnues)} (attendues : {', '.join(sorted(CLES))})")
    fonction = contenu.get("fonction", "calcul_aero")
    if fonction not in FONCTIONS:
        raise ErreurYaml(f"fonction : {fonction!r}, attendue parmi {', '.join(FONCTIONS)}")
    sondes = contenu.get("sondes", False)
    if not isinstance(sondes, bool):
        raise ErreurYaml(f"sondes : {sondes!r}, true ou false attendu")
    if "pdv" not in contenu:
        raise ErreurYaml("clé « pdv » absente : les points de vol à calculer")
    blocs = contenu["pdv"] if isinstance(contenu["pdv"], list) else [contenu["pdv"]]
    commun = contenu.get("commun") or {}
    if not isinstance(commun, Mapping):
        raise ErreurYaml("commun : un dictionnaire de clés est attendu")
    df = pd.concat([bloc_vers_df(b, commun, i) for i, b in enumerate(blocs)], ignore_index=True)
    sortie = Path(contenu.get("sortie", chemin.with_suffix(".csv").name))
    if not sortie.is_absolute():
        sortie = chemin.resolve().parent / sortie
    return Pdv(fonction, sortie, df, sondes)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("fichier", type=Path, help="fichier YAML des points de vol")
    p.add_argument("--sortie", type=Path, default=None, help="CSV de sortie (défaut : clé « sortie » du YAML)")
    p.add_argument("--module", default=None, help="module f2py (défaut aerolib)")
    p.add_argument("--dossier", type=Path, default=None, help="où chercher le module")
    args = p.parse_args(argv)
    try:
        fonction, sortie, df, sondes = lire_pdv(args.fichier)
        # sondes demandées : COMMON /PROBE/ exigé ; sinon pas lu du tout
        modele = ModeleAero(args.module, dossier=args.dossier, sondes=sondes)
        resultat = getattr(modele, fonction)(df, csv=args.sortie or sortie)
    except (ErreurYaml, ErreurModele, OSError, yaml.YAMLError) as erreur:
        print(f"erreur : {erreur}", file=sys.stderr)
        return 1
    except ModuleNotFoundError as erreur:
        print(f"{erreur}\n  → bash construire.sh", file=sys.stderr)
        return 1
    print(f"{args.fichier.name} : {len(df)} points, {df[BLOC].nunique()} bloc(s), {fonction}"
          + (f", {len(modele.sondes)} sondes" if sondes else ", sans sondes"))
    if "ierr" in resultat:
        print("  ierr :", resultat["ierr"].value_counts().sort_index().to_dict())
    print(f"  → {args.sortie or sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
