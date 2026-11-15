"""Test d'intégration sur des tables factices : trois scénarios, trois verdicts.

Un « modèle aéro » analytique tient lieu de code Fortran. On l'exécute une fois
pour produire la **référence**, puis on fabrique trois **tests** qui imitent ce
que donne le même code exécuté ailleurs :

``identique``
    Même code, même compilateur, mais le workflow rend les cas dans le
    désordre. Attendu : CONFORME, identique bit pour bit.
``arrondi``
    Même code compilé autrement (``-O3``, autre libm) : chaque sortie bouge de
    quelques ULP. Attendu : CONFORME dans les tolérances, max ULP ≈ 4.
``regression``
    La branche supersonique du code intégré a une constante fausse (Cm faux
    de 0.2 % pour Mach ≥ 1.2), trois cas ont planté à Mach 2 (lignes absentes),
    un CA est rendu NaN. Attendu : NON CONFORME, échecs attribués à Mach.

Usage ::

    python 01_test_integration.py                  # les trois scénarios
    python 01_test_integration.py regression       # un seul
    python 01_test_integration.py --sortie DOSSIER --sans-figures

Chaque scénario écrit ses pièces dans ``SORTIE_INTEGRATION/<scénario>/`` et
les tables dans ``SORTIE_INTEGRATION/DONNEES/`` — de quoi essayer aussi la
ligne de commande :

    cfd-validation integration SORTIE_INTEGRATION/DONNEES/reference.csv \\
        SORTIE_INTEGRATION/DONNEES/test_regression.csv --config INTEGRATION.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from cfd_validation import valider_integration

ENTREES = ["Mach", "alpha", "beta", "configuration"]
SORTIES = ["CN", "CA", "Cm", "CY", "regime"]

# Tolérances propres à certaines sorties, chacune justifiée : c'est ce que le
# rapport reprend. Les autres sorties prennent la tolérance commune.
TOLERANCES = {
    "Cm": {
        "rtol": 1e-8,
        "atol": 1e-12,
        "justification": "Cm somme des moments de bras opposés : perte de chiffres par compensation",
    },
    "CY": {
        "rtol": 1e-9,
        "atol": 1e-14,
        "justification": "CY nul par symétrie à β = 0 : seul l'écart absolu a un sens",
    },
}
RTOL, ATOL = 1e-9, 1e-12
JUSTIFICATION = "Changement de compilateur ou d'options : quelques ULP attendus, 1e-9 laisse un facteur 10⁶"


def modele_aero(df: pd.DataFrame) -> pd.DataFrame:
    """Un modèle aérodynamique jouet, déterministe, régulier, avec une branche supersonique."""
    m = df["Mach"].to_numpy()
    a = np.radians(df["alpha"].to_numpy())
    b = np.radians(df["beta"].to_numpy())
    ailettes = (df["configuration"] == "AILETTES").to_numpy()
    beta_pg = np.sqrt(np.abs(1.0 - m**2)) + 0.15  # Prandtl-Glauert régularisé autour de Mach 1
    cn_alpha = np.where(m < 1.0, 2.0 / beta_pg, 4.0 / beta_pg) * (1.0 + 0.35 * ailettes)
    out = df.copy()
    out["CN"] = cn_alpha * np.sin(a) * np.cos(a) + 1.8 * np.sin(a) ** 2
    out["CA"] = 0.25 + 0.12 * m**2 * (m > 0.9) + 0.02 * ailettes - 0.05 * np.sin(a) ** 2
    bras = np.where(m < 1.0, -0.42, -0.31)
    out["Cm"] = bras * out["CN"] + 0.015 * np.sin(2 * a)
    out["CY"] = -cn_alpha * 0.6 * np.sin(b)
    out["regime"] = np.where(m < 0.8, "subsonique", np.where(m < 1.2, "transsonique", "supersonique"))
    return out


def plan_de_calcul() -> pd.DataFrame:
    """Plan croisé : 7 Mach × 11 incidences × 3 dérapages × 2 configurations = 462 cas."""
    grille = pd.MultiIndex.from_product(
        [
            [0.3, 0.6, 0.8, 0.95, 1.2, 1.5, 2.0],
            np.arange(-4.0, 17.0, 2.0),
            [0.0, 2.0, 4.0],
            ["LISSE", "AILETTES"],
        ],
        names=ENTREES,
    )
    return grille.to_frame(index=False)


def scenario_identique(ref: pd.DataFrame) -> pd.DataFrame:
    return ref.sample(frac=1.0, random_state=1).reset_index(drop=True)


def scenario_arrondi(ref: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(2)
    test = ref.copy()
    for c in ["CN", "CA", "Cm", "CY"]:
        x = test[c].to_numpy()
        # De 0 à 4 ULP dans un sens ou dans l'autre : ce que donne un autre compilateur.
        for _ in range(4):
            pas = rng.integers(-1, 2, x.size)
            x = np.where(pas > 0, np.nextafter(x, np.inf), np.where(pas < 0, np.nextafter(x, -np.inf), x))
        test[c] = np.where(ref[c].to_numpy() == 0.0, 0.0, x)
    return test


def scenario_regression(ref: pd.DataFrame) -> pd.DataFrame:
    test = scenario_arrondi(ref)
    supersonique = test["Mach"] >= 1.2
    test.loc[supersonique, "Cm"] *= 1.002  # constante fausse dans la branche supersonique
    plantes = (test["Mach"] == 2.0) & (test["alpha"] >= 12.0) & (test["beta"] == 4.0) & (test["configuration"] == "AILETTES")
    test = test[~plantes]
    test.loc[test.index[17], "CA"] = np.nan  # une sortie non initialisée
    return test.sample(frac=1.0, random_state=3).reset_index(drop=True)


SCENARIOS = {
    "identique": (scenario_identique, "Le workflow rend les cas dans le désordre, rien d'autre ne change."),
    "arrondi": (scenario_arrondi, "Même code, autre compilateur : quelques ULP sur chaque sortie."),
    "regression": (scenario_regression, "Branche supersonique fausse, trois cas plantés, un NaN."),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("scenarios", nargs="*", metavar="SCENARIO",
                        help=f"parmi {', '.join(SCENARIOS)} (défaut : tous)")
    parser.add_argument("--sortie", default="SORTIE_INTEGRATION", help="dossier des pièces")
    parser.add_argument("--sans-figures", action="store_true", help="ne pas tracer (plus rapide)")
    args = parser.parse_args(argv)
    inconnus = [s for s in args.scenarios if s not in SCENARIOS]
    if inconnus:
        parser.error(f"scénario(s) inconnu(s) : {', '.join(inconnus)} (parmi {', '.join(SCENARIOS)})")

    racine = Path(args.sortie)
    donnees = racine / "DONNEES"
    donnees.mkdir(parents=True, exist_ok=True)
    reference = modele_aero(plan_de_calcul())
    reference.to_csv(donnees / "reference.csv", index=False)

    verdicts = {}
    for nom in args.scenarios or list(SCENARIOS):
        fabrique, histoire = SCENARIOS[nom]
        test = fabrique(reference)
        test.to_csv(donnees / f"test_{nom}.csv", index=False)
        res = valider_integration(
            reference,
            test,
            entrees=ENTREES,
            sorties=SORTIES,
            tolerances=TOLERANCES,
            rtol=RTOL,
            atol=ATOL,
            justification=JUSTIFICATION,
            identifiant=f"INT-{nom.upper()}",
            metadonnees={"code": "modele_aero (factice)", "scenario": histoire},
            sortie=racine / nom,
            figures=not args.sans_figures,
            nettoyer=True,
        )
        verdicts[nom] = res.verdict
        print()

    for nom, verdict in verdicts.items():
        print(f"  {nom:<12} {verdict}")
    print(f"\nPièces dans {racine.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
