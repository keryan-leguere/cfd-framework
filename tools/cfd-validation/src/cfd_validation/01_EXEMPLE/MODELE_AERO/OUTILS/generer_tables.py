#!/usr/bin/env python3
"""Génère SOURCES/aero_tables.f, les tables en dur du modèle aéro factice.

Les valeurs viennent de formules analytiques simples (DOC/01_SOURCES.md §4),
arrondies à 4 décimales : c'est ce fichier Fortran, pas ce script, qui fait foi
pour le code. Le script n'existe que pour que les tables soient reproductibles.

    python3 OUTILS/generer_tables.py            # réécrit SOURCES/aero_tables.f
    python3 OUTILS/generer_tables.py --verifier # code 1 si le fichier a dérivé

Bibliothèque standard seulement (3.9+).
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Callable

ICI = Path(__file__).resolve().parent
CIBLE = ICI.parent / "SOURCES" / "aero_tables.f"

# Grilles (carrées : 7 × 7 pour chaque coefficient).
MACH = [0.3, 0.6, 0.8, 0.95, 1.1, 1.5, 2.0]
ALPHA = [-20.0, -10.0, -5.0, 0.0, 5.0, 10.0, 20.0]  # degrés
BETA = [-10.0, -5.0, -2.0, 0.0, 2.0, 5.0, 10.0]  # degrés
MACH_PROPU = [0.4, 0.6, 0.8, 1.0, 1.2, 1.5, 1.8]  # plus étroite que MACH : voulu

# Table 5D des gouvernes, en angles polaires (carrée : 5⁵ = 3 125 nœuds).
MACH_GOUV = [0.3, 0.6, 1.0, 1.5, 2.0]  # même plage que MACH
ALPHAT = [0.0, 5.0, 10.0, 15.0, 20.0]  # incidence totale, degrés
PHIA = [-180.0, -90.0, 0.0, 90.0, 180.0]  # azimut aérodynamique, degrés
DM = [-20.0, -10.0, 0.0, 10.0, 20.0]  # braquage de tangage, degrés
DN = [-20.0, -10.0, 0.0, 10.0, 20.0]  # braquage de lacet, degrés


def pic(m: float) -> float:
    """Bosse transsonique centrée sur Mach 1."""
    return math.exp(-(((m - 1.0) / 0.25) ** 2))


def cx(m: float, a: float) -> float:
    return -(0.28 + 0.22 * pic(m) + 0.9 * math.sin(a) ** 2)


def cz(m: float, a: float) -> float:
    s = math.sin(a)
    return -((2.2 + 0.8 * pic(m)) * s * math.cos(a) + 1.2 * s * abs(s))


def cm(m: float, a: float) -> float:
    s = math.sin(a)
    return -(0.9 + 0.4 * pic(m)) * s * math.cos(a) - 0.5 * s * abs(s)


def cy(m: float, b: float) -> float:
    return -(2.2 + 0.8 * pic(m)) * math.sin(b)


def cl(m: float, b: float) -> float:
    return -(0.05 + 0.02 * pic(m)) * math.sin(b)


def cn(m: float, b: float) -> float:
    return (0.9 + 0.4 * pic(m)) * math.sin(b)


def dcx_propu(m: float) -> float:
    return 0.08 + 0.05 * math.exp(-(((m - 1.0) / 0.4) ** 2))


def dcm_gouv(m: float, at: float, phi: float, dm: float, dn: float) -> float:
    """Incrément de Cm des gouvernes ; at, phi en radians, dm, dn en degrés.

    Indépendant de phi à alphaT = 0 (phi n'y est pas défini) : sin(at) facteur
    de tout terme en phi.
    """
    k = 0.012 * (1.0 - 0.3 * pic(m))
    return -k * (dm * (1.0 + 0.4 * math.sin(at) * math.cos(phi)) + 0.5 * dn * math.sin(at) * math.sin(phi))


def _r(v: float) -> float:
    v = round(v, 4)
    return 0.0 if v == 0.0 else v  # pas de « -0.0000D0 »


def _lit(v: float) -> str:
    return f"{_r(v):.4f}D0"


def _data(nom: str, valeurs: list[float]) -> list[str]:
    """Un DATA en format fixe, 4 valeurs par ligne de suite (colonne 72 tenue)."""
    lignes = [f"      DATA {nom} /"]
    morceaux = [valeurs[i : i + 4] for i in range(0, len(valeurs), 4)]
    for k, bloc in enumerate(morceaux):
        fin = " /" if k == len(morceaux) - 1 else ","
        lignes.append("     &  " + ", ".join(f"{_lit(v):>10s}" for v in bloc) + fin)
    return lignes


def _table(nom: str, f: Callable[[float, float], float], grille2: list[float], nom2: str) -> list[str]:
    """Table NM × N2, une colonne (Mach variable) par DATA : ordre mémoire Fortran."""
    out = [f"C     {nom}(Mach, {nom2})"]
    for j, x2 in enumerate(grille2, start=1):
        out.append(f"C     {nom2} = {x2:g} deg")
        vals = [f(m, math.radians(x2)) for m in MACH]
        out += _data(f"({nom}(I,{j}),I=1,NM)", vals)
    return out


def _table_gouv() -> list[str]:
    """TDCMG(Mach, alphaT, phiA, DM, DN) : un DATA par tranche (phiA, DM, DN), ordre Fortran."""
    out = ["C     TDCMG(Mach, alphaT, phiA, DM, DN)"]
    for n, dn in enumerate(DN, start=1):
        for m_, dm in enumerate(DM, start=1):
            for k, phi in enumerate(PHIA, start=1):
                out.append(f"C     phiA = {phi:g}, DM = {dm:g}, DN = {dn:g} deg")
                vals = [dcm_gouv(m, math.radians(at), math.radians(phi), dm, dn) for at in ALPHAT for m in MACH_GOUV]
                out += _data(f"((TDCMG(I,J,{k},{m_},{n}),I=1,NMG),J=1,NAT)", vals)
    return out


def generer() -> str:
    lignes: list[str] = [
        "C" + "-" * 70,
        "C     AERO_TABLES.F -- tables aerodynamiques en dur (BLOCK DATA)",
        "C",
        "C     FICHIER GENERE par OUTILS/generer_tables.py : ne pas editer",
        "C     a la main, modifier les formules et regenerer.",
        "C",
        "C     Tables carrees NM x NA (CX, CZ, CM) et NM x NB (CY, CL, CN),",
        "C     coefficients au point de reference des moments (fixe par",
        "C     AERINI), axes corps FRD, angles en degres.",
        "C     Table propulsive 1D : DCX(Mach).",
        "C     Table des gouvernes 5D : DCMG(Mach, alphaT, phiA, DM, DN).",
        "C" + "-" * 70,
        "      BLOCK DATA AERTBD",
        "      IMPLICIT NONE",
        "      INCLUDE 'aero_dim.inc'",
        "      INTEGER I, J",
        "C",
        "C     Grilles",
    ]
    lignes += _data("TMACH", MACH)
    lignes += _data("TALPHA", ALPHA)
    lignes += _data("TBETA", BETA)
    lignes += _data("TMACHP", MACH_PROPU)
    lignes.append("C")
    lignes += _table("TCX", cx, ALPHA, "alpha")
    lignes.append("C")
    lignes += _table("TCZ", cz, ALPHA, "alpha")
    lignes.append("C")
    lignes += _table("TCM", cm, ALPHA, "alpha")
    lignes.append("C")
    lignes += _table("TCY", cy, BETA, "beta")
    lignes.append("C")
    lignes += _table("TCL", cl, BETA, "beta")
    lignes.append("C")
    lignes += _table("TCN", cn, BETA, "beta")
    lignes += ["C", "C     Propulsion : increment de CX (effet de jet sur le culot)"]
    lignes += _data("TDCXP", [dcx_propu(m) for m in MACH_PROPU])
    lignes += ["C", "C     Gouvernes : increment de CM, angles polaires"]
    lignes += _data("TMACHG", MACH_GOUV)
    lignes += _data("TALFT", ALPHAT)
    lignes += _data("TPHIA", PHIA)
    lignes += _data("TDMG", DM)
    lignes += _data("TDNG", DN)
    lignes += _table_gouv()
    lignes.append("      END")
    trop = [x for x in lignes if len(x) > 72]
    assert not trop, f"lignes au-delà de la colonne 72 : {trop}"
    return "\n".join(lignes) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--verifier", action="store_true", help="comparer sans écrire (code 1 si différent)")
    args = p.parse_args()
    texte = generer()
    if args.verifier:
        if not CIBLE.exists() or CIBLE.read_text() != texte:
            print(f"{CIBLE} a dérivé : relancer sans --verifier", file=sys.stderr)
            return 1
        print(f"{CIBLE} à jour")
        return 0
    CIBLE.write_text(texte)
    print(f"écrit {CIBLE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
