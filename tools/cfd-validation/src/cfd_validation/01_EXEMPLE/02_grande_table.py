"""Test d'intégration à grande échelle : 10 entrées, 15 sorties, 3 000 cas.

Le même déroulé que ``01_test_integration.py``, sur une table qui ressemble à
une vraie base aérodynamique : six variables de vol et de gouverne, le
Reynolds, la rugosité, une configuration (texte), et quinze coefficients —
dont ``CN`` et ``Cn``, ``CM`` et ``Cm``, qui ne diffèrent que par la casse.

Le test imite le code intégré à un workflow :

- toutes les sorties bougent d'un ULP (autre compilateur) : dans la tolérance ;
- ``Cm`` et ``Cm_alpha`` sont faux de 0.1 % dès que ``braquage_profondeur ≥ 15``
  (une branche du code de gouverne) : hors tolérance ;
- 20 cas à Mach 3 en configuration ``EMPORTS`` ont planté : absents du test.

Attendu : NON CONFORME, et l'attribution désigne ``braquage_profondeur ∈ {15, 20}``
parmi dix entrées. Ce qu'il faut regarder :

- au terminal, la table des lignes ne garde que les entrées qui tiennent en
  largeur, les plus liées aux échecs d'abord, et nomme les autres ;
- ``integration.log`` a toutes les colonnes, sans rien rogner ;
- ``FIGURES/01_synthese_sorties`` : une ligne par sortie, les deux en échec
  sautent aux yeux ; ``04_marges_*`` n'existe que pour ces deux-là ;
  ``04_marges_01_CN`` et ``04_marges_06_Cn`` ne s'écrasent pas, même sous Windows.

Usage ::

    python 02_grande_table.py                    # rapport, journal, figures
    python 02_grande_table.py --sans-figures     # quelques secondes
    python 02_grande_table.py --figures-entrees toutes   # figure 04 pour les 15 sorties
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from cfd_validation import valider_integration

ENTREES = [
    "Mach",
    "alpha",
    "beta",
    "altitude_km",
    "braquage_profondeur",
    "braquage_direction",
    "braquage_gauchissement",
    "reynolds",
    "rugosite_um",
    "configuration",
]
SORTIES = [
    "CN", "CA", "CY", "Cl", "Cm", "Cn", "CM", "CN_alpha",
    "Cm_alpha", "CX", "CZ", "Cmq", "Clp", "Cnr", "CD_frottement",
]
N_CAS = 3000

TOLERANCES = {
    "CY": {"atol": 1e-14, "justification": "CY nul par symétrie à β = 0 : seul l'écart absolu a un sens"},
    "Cn": {"atol": 1e-14, "justification": "Cn nul par symétrie à β = 0 et braquage de direction nul"},
    "Cm": {"rtol": 1e-8, "justification": "Cm somme de moments de bras opposés : perte de chiffres par compensation"},
}
RTOL, ATOL = 1e-9, 1e-12
JUSTIFICATION = "Changement de compilateur ou d'options : quelques ULP attendus, 1e-9 laisse un facteur 10⁶"


def plan_de_calcul(n: int = N_CAS, graine: int = 0) -> pd.DataFrame:
    """Un plan tiré au hasard : entrées discrètes (niveaux) et continues (classes de quantiles)."""
    rng = np.random.default_rng(graine)
    return pd.DataFrame(
        {
            "Mach": rng.choice([0.3, 0.6, 0.8, 0.95, 1.2, 1.5, 2.0, 3.0], n),
            "alpha": rng.uniform(-5.0, 20.0, n),
            "beta": rng.choice([0.0, 2.0, 4.0, 8.0], n),
            "altitude_km": rng.uniform(0.0, 25.0, n),
            "braquage_profondeur": rng.choice(np.arange(-20.0, 21.0, 5.0), n),
            "braquage_direction": rng.choice([-10.0, 0.0, 10.0], n),
            "braquage_gauchissement": rng.choice([-5.0, 0.0, 5.0], n),
            "reynolds": rng.uniform(1e6, 5e7, n),
            "rugosite_um": rng.choice([0.0, 10.0, 50.0], n),
            "configuration": rng.choice(["LISSE", "AILETTES", "EMPORTS"], n),
        }
    )


def modele_aero(plan: pd.DataFrame) -> pd.DataFrame:
    """Quinze coefficients jouets, réguliers, chacun sensible à quelques entrées."""
    m = plan["Mach"].to_numpy()
    a = np.radians(plan["alpha"].to_numpy())
    b = np.radians(plan["beta"].to_numpy())
    dm = np.radians(plan["braquage_profondeur"].to_numpy())
    dn = np.radians(plan["braquage_direction"].to_numpy())
    dl = np.radians(plan["braquage_gauchissement"].to_numpy())
    re = plan["reynolds"].to_numpy()
    k = plan["rugosite_um"].to_numpy()
    emports = (plan["configuration"] == "EMPORTS").to_numpy()
    ailettes = (plan["configuration"] == "AILETTES").to_numpy()
    pg = np.sqrt(np.abs(1.0 - m**2)) + 0.15
    cn_a = (2.0 / pg) * (1.0 + 0.3 * ailettes)

    out = plan.copy()
    out["CN"] = cn_a * np.sin(a) * np.cos(a) + 1.6 * np.sin(a) ** 2 + 0.4 * dm
    out["CA"] = 0.22 + 0.1 * m**2 * (m > 0.9) + 0.04 * emports - 0.05 * np.sin(a) ** 2
    out["CY"] = -0.6 * cn_a * np.sin(b) + 0.15 * dn
    out["Cl"] = -0.05 * np.sin(b) * np.sin(a) + 0.08 * dl
    out["Cm"] = -0.35 * out["CN"] + 0.012 * np.sin(2 * a) - 0.9 * dm
    out["Cn"] = 0.08 * np.sin(b) - 0.12 * dn
    out["CM"] = out["Cm"] - 0.02 * emports  # moment au CDG des emports : à ne pas confondre avec Cm
    out["CN_alpha"] = cn_a + 3.2 * np.sin(2 * a)
    out["Cm_alpha"] = -0.35 * out["CN_alpha"] + 0.024 * np.cos(2 * a)
    out["CX"] = -out["CA"] * np.cos(a) + out["CN"] * np.sin(a)
    out["CZ"] = -out["CN"] * np.cos(a) - out["CA"] * np.sin(a)
    out["Cmq"] = -8.0 - 2.0 * m - 1.5 * ailettes
    out["Clp"] = -0.4 - 0.05 * m
    out["Cnr"] = -0.2 - 0.03 * m - 0.05 * emports
    out["CD_frottement"] = 0.074 / (re**0.2) * (1.0 + 0.002 * k)
    return out


def test_integre(reference: pd.DataFrame) -> pd.DataFrame:
    """Le même modèle « exécuté dans le workflow » : désordre, arrondi, régression, plantages."""
    test = reference.sample(frac=1.0, random_state=1).copy()
    for s in SORTIES:
        test[s] = np.nextafter(test[s].to_numpy(), np.inf)  # 1 ULP : un autre compilateur
    gouverne = test["braquage_profondeur"] >= 15.0
    test.loc[gouverne, "Cm"] *= 1.001  # la branche « grand braquage » a une constante fausse
    test.loc[gouverne, "Cm_alpha"] *= 1.001
    plantes = test.index[(test["Mach"] == 3.0) & (test["configuration"] == "EMPORTS")][:20]
    return test.drop(index=plantes).reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sortie", default="SORTIE_INTEGRATION", help="dossier des pièces")
    parser.add_argument("--sans-figures", action="store_true", help="ne pas tracer (quelques secondes)")
    parser.add_argument("--figures-entrees", choices=("echecs", "toutes", "aucune"), default="echecs",
                        help="figures « marge selon chaque entrée » : sorties en échec (défaut), toutes, aucune")
    args = parser.parse_args(argv)

    racine = Path(args.sortie)
    donnees = racine / "DONNEES"
    donnees.mkdir(parents=True, exist_ok=True)
    reference = modele_aero(plan_de_calcul())
    test = test_integre(reference)
    reference.to_csv(donnees / "reference_grande.csv", index=False)
    test.to_csv(donnees / "test_grande.csv", index=False)

    res = valider_integration(
        reference,
        test,
        entrees=ENTREES,
        sorties=SORTIES,
        tolerances=TOLERANCES,
        rtol=RTOL,
        atol=ATOL,
        justification=JUSTIFICATION,
        identifiant="INT-GRANDE",
        metadonnees={"code": "modele_aero 10 × 15 (factice)", "cas": str(N_CAS)},
        sortie=racine / "grande_table",
        figures=not args.sans_figures,
        figures_par_entree=args.figures_entrees,
        nettoyer=True,
    )
    print(f"\n  grande_table  {res.verdict}")
    print(f"\nPièces dans {(racine / 'grande_table').resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
