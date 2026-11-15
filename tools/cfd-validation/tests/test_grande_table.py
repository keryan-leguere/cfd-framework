"""10 entrées × 15 sorties : le rapport doit rester lisible, au terminal comme dans le journal."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from conftest import glyphes_manquants_en_erreur
from rich.console import Console

from cfd_validation import valider_integration

ENTREES = [
    "Mach", "alpha", "beta", "altitude_km", "braquage_profondeur",
    "braquage_direction", "braquage_gauchissement", "reynolds", "rugosite_um", "configuration",
]
# CN et Cn, CM et Cm : des noms qui ne diffèrent que par la casse, comme en aéro.
SORTIES = ["CN", "CA", "CY", "Cl", "Cm", "Cn", "CM", "CN_alpha", "CX", "CZ", "Cmq", "Clp", "Cnr", "CD_frottement", "finesse"]


@pytest.fixture(scope="module")
def tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(0)
    n = 600
    ref = pd.DataFrame({
        "Mach": rng.choice([0.3, 0.8, 1.2, 2.0, 3.0], n),
        "alpha": rng.uniform(-5, 20, n),
        "beta": rng.choice([0.0, 4.0], n),
        "altitude_km": rng.uniform(0, 25, n),
        "braquage_profondeur": rng.choice(np.arange(-20.0, 21.0, 5.0), n),
        "braquage_direction": rng.choice([-10.0, 0.0, 10.0], n),
        "braquage_gauchissement": rng.choice([-5.0, 0.0, 5.0], n),
        "reynolds": rng.uniform(1e6, 5e7, n),
        "rugosite_um": rng.choice([0.0, 50.0], n),
        "configuration": rng.choice(["LISSE", "AILETTES", "EMPORTS"], n),
    })
    for k, s in enumerate(SORTIES):
        ref[s] = np.sin(np.radians(ref["alpha"]) * (k + 1)) + 0.01 * k * ref["braquage_profondeur"]
    test = ref.sample(frac=1.0, random_state=1).copy()
    test.loc[test["braquage_profondeur"] >= 15, "Cm"] *= 1.001
    return ref, test


def test_terminal_80_colonnes(tables: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    ref, test = tables
    console = Console(file=io.StringIO(), width=80, record=True, color_system=None)
    valider_integration(ref, test, ENTREES, SORTIES, rtol=1e-9, atol=1e-12, justification="J",
                        sortie=None, console=console)
    texte = console.export_text()
    assert max(len(ligne) for ligne in texte.splitlines()) <= 80
    tete = next(ligne for ligne in texte.splitlines() if ligne.strip().startswith("Réf."))
    # rien de rogné : statut, sortie et marge restent, avec l'entrée en cause
    for colonne in ("Statut", "Sortie", "Marge", "braquage_profondeur"):
        assert colonne in tete
    assert "Entrées non affichées faute de place" in texte
    assert "braquage_profondeur ∈ {15, 20}" in " ".join(texte.split())  # la phrase peut passer à la ligne
    # pas d'entrée coupée au milieu du nom dans la table d'attribution
    assert "braquage_gauchissement" in texte


def test_journal_complet(tables: tuple[pd.DataFrame, pd.DataFrame], tmp_path: Path) -> None:
    ref, test = tables
    valider_integration(ref, test, ENTREES, SORTIES, sortie=tmp_path, figures=False, afficher=False)
    lignes = (tmp_path / "integration.log").read_text(encoding="utf-8").splitlines()
    tete = next(ligne for ligne in lignes if ligne.strip().startswith("Réf.") and "ULP" in ligne)
    assert all(e in tete for e in ENTREES)  # toutes les entrées, aucune rognée
    assert sum(1 for ligne in lignes if ligne.strip().startswith(("CN ", "Cn "))) >= 4


def test_figures_noms_distincts_sans_la_casse(tables: tuple[pd.DataFrame, pd.DataFrame], tmp_path: Path) -> None:
    pytest.importorskip("cfd_plot")
    ref, test = tables
    test = test.copy()
    test.loc[test["Mach"] == 3.0, ["Cn", "CN"]] += 1.0  # CN et Cn en échec : deux figures 04
    with glyphes_manquants_en_erreur():
        res = valider_integration(ref, test, ENTREES, SORTIES, sortie=tmp_path, formats=("png",), afficher=False)
    noms = [p.name for p in res.fichiers if p.suffix == ".png"]
    assert len({n.lower() for n in noms}) == len(noms)  # Windows et macOS : pas d'écrasement
    assert "04_marges_01_CN.png" in noms and "04_marges_06_Cn.png" in noms
    assert "02_marges_par_sortie_02.png" in noms  # 15 sorties : deux pages de 12
    assert "03_repartition_marges_03.png" in noms  # 7 courbes par page


def test_figures_par_entree(tables: tuple[pd.DataFrame, pd.DataFrame], tmp_path: Path) -> None:
    pytest.importorskip("cfd_plot")
    ref, test = tables
    res = valider_integration(ref, test, ENTREES, SORTIES, sortie=tmp_path / "a", formats=("png",),
                              afficher=False, figures_par_entree="aucune")
    assert not any(p.name.startswith("04_") for p in res.fichiers)
    with pytest.raises(ValueError, match="par_entree"):
        valider_integration(ref, test, ENTREES, SORTIES, sortie=tmp_path / "b", afficher=False,
                            figures_par_entree="certaines")
