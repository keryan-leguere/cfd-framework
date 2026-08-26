#!/usr/bin/env python3
"""Balayage en altitude : quel ε choisir pour une trajectoire ?

Une tuyère de rapport de section fixe n'est adaptée qu'à UNE pression
ambiante. Ce script montre le compromis : pour plusieurs ε, il calcule la
poussée et l'Isp du niveau de la mer jusqu'au vide, repère l'altitude
d'adaptation et signale le décollement probable (critère de Summerfield).

    python balayage_altitude.py [RÉPERTOIRE_SORTIE]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from cfd_nozzle import GAS_LIBRARY, Nozzle
from cfd_nozzle._compat import zip_strict
from cfd_nozzle.core.nozzle import SEPARATION_RATIO, Regime


# Atmosphère ISA simplifiée (troposphère + stratosphère basse), suffisante
# pour situer un point de fonctionnement. Pour un modèle complet, voir le
# package frère cfd-atm.
def pression_isa(altitude_m: float) -> float:
    """Pression statique ISA [Pa] à l'altitude géopotentielle donnée [m]."""
    if altitude_m < 11000.0:
        return float(101325.0 * (1.0 - 2.25577e-5 * altitude_m) ** 5.25588)
    return float(22632.0 * np.exp(-(altitude_m - 11000.0) / 6341.62))


def main(argv: list[str]) -> int:
    sortie = Path(argv[1]) if len(argv) > 1 else Path("SORTIE")
    sortie.mkdir(parents=True, exist_ok=True)

    gaz = GAS_LIBRARY["lox_rp1"]
    p0, t0 = 100e5, 3500.0
    aire_col = 0.25 * np.pi * 0.20**2
    altitudes = np.linspace(0.0, 30000.0, 60)

    lignes = ["# altitude [m]  pa [Pa]  " + "  ".join(f"F_eps{e:g} [kN]" for e in (8, 16, 30))]
    print(f"{'ε':>5} {'alt. adaptation':>16} {'F(0 m)':>12} {'F(vide)':>12} {'Isp(vide)':>11}")
    print("-" * 62)

    resultats = {}
    for eps in (8.0, 16.0, 30.0):
        tuyere = Nozzle(aire_col, eps, gaz, eta_cstar=0.96, lambda_div=0.985)
        poussees, isp = [], []
        altitude_adaptee = None
        decollement_max = None
        for altitude in altitudes:
            etat = tuyere.solve(p0, t0, float(pression_isa(float(altitude))))
            poussees.append(etat.thrust)
            isp.append(etat.isp)
            if altitude_adaptee is None and etat.regime in (
                Regime.ADAPTED,
                Regime.UNDEREXPANDED,
            ):
                altitude_adaptee = altitude
            if etat.pressure_ratio_exit < SEPARATION_RATIO:
                decollement_max = altitude
        etat_vide = tuyere.solve(p0, t0, 1.0)
        resultats[eps] = np.array(poussees)
        adaptee = f"{altitude_adaptee:,.0f} m" if altitude_adaptee is not None else "> 30 km"
        print(
            f"{eps:5.0f} {adaptee:>16} {poussees[0] * 1e-3:11.2f} kN "
            f"{etat_vide.thrust * 1e-3:9.2f} kN {etat_vide.isp:10.1f} s"
        )
        if decollement_max is not None:
            print(
                f"      [!] décollement probable (pe/pa < {SEPARATION_RATIO}) "
                f"jusqu'à {decollement_max:,.0f} m"
            )

    for altitude, pa in zip_strict(altitudes, [pression_isa(float(a)) for a in altitudes]):
        i = int(np.argmin(np.abs(altitudes - altitude)))
        lignes.append(
            f"{altitude:10.1f} {pa:12.2f} "
            + "  ".join(f"{resultats[e][i] * 1e-3:12.4f}" for e in (8.0, 16.0, 30.0))
        )
    fichier = sortie / "balayage_altitude.dat"
    fichier.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print(f"\n[ok] Données écrites : {fichier}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
