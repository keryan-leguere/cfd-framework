#!/usr/bin/env python3
"""Test d'intégration du modèle aéro : ce code redonne-t-il les résultats obtenus dans un autre environnement ?

    cd ../../PYTHON && bash construire.sh     # une fois
    cd ../VALIDATION/04_INTEGRATION
    python 04_integration.py                   # REFERENCE/*.csv contre le module construit ici
    python 04_integration.py --defaut          # régression simulée sur Cm à |DM| = 20° : NON CONFORME

``REFERENCE/`` contient les CSV obtenus ailleurs (autre machine, autre
compilateur, ancienne chaîne de calcul), un fichier par campagne, avec les
en-têtes de l'outil qui les a écrits. Le script :

1. lit tous les CSV (``cfd_validation.lire_dossier``, relecture exacte) en
   ramenant chaque en-tête au nom du modèle (``normaliser_colonnes``, le
   seul morceau propre à ces fichiers) ;
2. rejoue chaque ligne avec le code d'ici
   (``ModeleAero.calcul_aero_elementaire``, entrées de la référence) ;
3. compare, ligne à ligne et sortie par sortie (``valider_integration``) :
   lignes appariées sur leurs entrées, campagne comprise — un échec se
   rattache donc aussi à son fichier.

Les CSV de l'exemple sont fabriqués par ``generer_reference.py``, avec le
même Fortran compilé en ``-O3 -ffast-math`` : quelques ULP d'écart, que la
tolérance déclarée (et justifiée) absorbe.

Code de retour : 0 conforme, 2 non conforme, 1 erreur.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from pathlib import Path

import pandas as pd

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))  # VALIDATION/ : tables_modele

from tables_modele import PYTHON, ModeleAero, charger_modele, metadonnees  # noqa: E402

from cfd_validation import ErreurLecture, lire_dossier, valider_integration  # noqa: E402

#: Colonnes du modèle (arguments Fortran) : les entrées, puis les sorties comparées.
ENTREES = ["mach", "alpha", "beta", "xg", "yg", "zg", "ipropu", "dm", "dn", "xref", "yref", "zref", "lref", "biaicx"]
SORTIES = ["cx", "cy", "cz", "cl", "cm", "cn", "ierr"]
#: Colonne ajoutée par lire_dossier : le fichier (la campagne) de chaque ligne.
CAMPAGNE = "campagne"

# -- le helper : en-têtes d'ailleurs → noms du modèle ------------------------------

#: Nom normalisé (sans unité, minuscules, « _ ») → nom du modèle, quand ils diffèrent.
ALIAS = {"propulsion": "ipropu", "biais_cx": "biaicx", "delta_m": "dm", "delta_n": "dn"}
#: Valeurs textuelles de la propulsion → l'entier attendu par AERCAL.
PROPULSION = {"ON": 1, "OFF": 0, "1": 1, "0": 0}


def nom_type(entete: str) -> str:
    """``"Alpha (deg)"``, ``"ALPHA [deg]"`` → ``"alpha"`` ; ``"DELTA_M [deg]"`` → ``"dm"``."""
    nom = re.sub(r"[(\[].*?[)\]]", "", str(entete)).strip().lower()  # l'unité entre () ou []
    nom = re.sub(r"[\s\-]+", "_", nom)
    return ALIAS.get(nom, nom)


def normaliser_colonnes(df: pd.DataFrame) -> pd.DataFrame:
    """En-têtes ramenés aux noms du modèle ; refuse une colonne inconnue ou en double."""
    noms = {c: nom_type(c) for c in df.columns}
    attendus = set(ENTREES) | set(SORTIES)
    inconnues = [f"« {c} » → {n}" for c, n in noms.items() if n not in attendus]
    if inconnues:
        raise ErreurLecture(f"colonne(s) sans équivalent dans le modèle : {', '.join(inconnues)} (compléter ALIAS)")
    doublons = sorted({n for n in noms.values() if list(noms.values()).count(n) > 1})
    if doublons:
        raise ErreurLecture(f"plusieurs en-têtes donnent {', '.join(doublons)}")
    df = df.rename(columns=noms)
    texte = df["ipropu"].astype(str).str.strip().str.upper()
    if not texte.isin(list(PROPULSION)).all():
        raise ErreurLecture(f"propulsion : valeurs {sorted(set(texte) - set(PROPULSION))} (attendu ON/OFF ou 0/1)")
    df["ipropu"] = texte.map(PROPULSION).astype("int64")
    return df


# -- le test ------------------------------------------------------------------------

#: Tolérances : quelques ULP entre deux compilations, rien de plus.
RTOL, ATOL = 1e-12, 1e-14
JUSTIFICATION = (
    "Même Fortran, autre compilation (-O3 -ffast-math contre -O2) : réassociation des sommes de "
    "l'interpolation et du transport des moments, écarts mesurés ≤ 1e-14 relatif (Cm près de zéro) ; "
    "1e-12 laisse un facteur 100, l'absolu 1e-14 couvre les sorties nulles par symétrie (CY, Cl, Cn à β = 0)."
)
#: Figures en SVG seul, comme celles des tests de table (le paquet sort PNG + PDF par défaut).
FORMATS = ("svg",)
TOLERANCES = {"ierr": {"rtol": 0.0, "atol": 0.0, "justification": "code de retour : identique ou rien"}}


def rejouer(modele: ModeleAero, *, defaut: bool = False) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """L'évaluateur : les entrées de la référence → les sorties du code d'ici.

    ``defaut`` (démonstration) : Cm décalé de 1e-9 aux braquages |DM| = 20°,
    comme le ferait une régression localisée dans la table des gouvernes.
    """
    def evaluer(reference: pd.DataFrame) -> pd.DataFrame:
        sortie = modele.calcul_aero_elementaire(reference[ENTREES])
        if defaut:
            sortie.loc[sortie["dm"].abs() >= 20.0, "cm"] += 1e-9
        return pd.concat([reference[[CAMPAGNE]], sortie[[*ENTREES, *SORTIES]]], axis=1)

    return evaluer


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--reference", type=Path, default=ICI / "REFERENCE", help="dossier des CSV de référence")
    p.add_argument("--defaut", action="store_true", help="régression simulée sur Cm à |DM| = 20° (NON CONFORME)")
    p.add_argument("--module", default="aerolib", help="module f2py à tester (défaut aerolib)")
    p.add_argument("--dossier", type=Path, default=PYTHON, help="où chercher le module")
    p.add_argument("--sortie", type=Path, default=None, help="dossier des pièces (défaut SORTIE/<scénario>)")
    p.add_argument("--sans-figures", action="store_true", help="ne pas tracer les figures")
    args = p.parse_args()

    try:
        reference = lire_dossier(args.reference, renommer=normaliser_colonnes, colonne_fichier=CAMPAGNE)
    except ErreurLecture as erreur:
        print(f"erreur : {erreur}", file=sys.stderr)
        return 1
    modele = charger_modele(args.module, args.dossier)
    if modele is None:
        return 1
    scenario = "defaut" if args.defaut else "nominal"
    test = rejouer(modele, defaut=args.defaut)(reference)
    fichiers = {f"référence {nom}": f"sha256 {sha[:16]}…" for nom, sha in reference.attrs["fichiers"].items()}
    res = valider_integration(
        reference, test,
        entrees=[CAMPAGNE, *ENTREES], sorties=SORTIES,
        rtol=RTOL, atol=ATOL, justification=JUSTIFICATION, tolerances=TOLERANCES,
        identifiant="VAL-INT-04",
        description="Le modèle construit ici redonne, cas par cas, les résultats obtenus dans un autre environnement.",
        metadonnees={**metadonnees(modele, scenario), **fichiers},
        sortie=args.sortie or ICI / "SORTIE" / scenario,
        figures=not args.sans_figures,
        formats=FORMATS,
        nettoyer=True,
    )
    return 0 if res.conforme else 2


if __name__ == "__main__":
    sys.exit(main())
