"""Rendu terminal, journal, figures et pièces de valider_integration."""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from conftest import glyphes_manquants_en_erreur
from rich.console import Console

from cfd_validation import valider_integration
from cfd_validation.report.figures import _etiquette_marge

ENTREES = ["Mach", "alpha", "conf"]
SORTIES = ["CN", "Cm", "regime"]


def _regression(reference: pd.DataFrame) -> pd.DataFrame:
    test = reference.drop(index=[0]).copy()
    test.loc[test["Mach"] == 2.0, "Cm"] *= 1.01
    return test


def _console() -> Console:
    return Console(file=io.StringIO(), width=120, record=True, color_system=None)


def test_terminal_sans_fichier(reference: pd.DataFrame) -> None:
    console = _console()
    res = valider_integration(reference, _regression(reference), ENTREES, SORTIES, sortie=None, console=console, lignes_max=3)
    texte = console.export_text()
    assert "Verdict INT-01 : NON CONFORME" in texte
    assert "Mach ∈ {2}" in texte
    assert "autre(s) ligne(s) en échec" in texte
    assert "tolérance par défaut" in texte  # aucune tolérance déclarée : on le dit
    assert res.fichiers == ()


def test_pieces_et_journal(reference: pd.DataFrame, tmp_path: Path) -> None:
    res = valider_integration(
        reference, _regression(reference), ENTREES, SORTIES,
        rtol=1e-9, atol=1e-12, justification="J", sortie=tmp_path / "out", figures=False,
        afficher=False, identifiant="INT-42", metadonnees={"commit": "abc"},
    )
    out = tmp_path / "out"
    noms = {p.name for p in res.fichiers}
    assert noms == {"lignes.csv", "ecarts.csv", "resume.json", "integration.log"}
    journal = (out / "integration.log").read_text(encoding="utf-8")
    assert "INT-42" in journal and "commit" in journal and "abc" in journal
    assert "Toutes les lignes" in journal
    assert all(not ligne.endswith(" ") for ligne in journal.splitlines())
    # toutes les lignes de référence figurent au journal, l'absente comprise
    assert journal.count("absente du test") >= 1
    for nom in ("lignes.csv", "ecarts.csv", "resume.json"):
        assert nom in journal
    resume = json.loads((out / "resume.json").read_text(encoding="utf-8"))
    assert resume["identifiant"] == "INT-42" and resume["conforme"] is False
    lignes = pd.read_csv(out / "lignes.csv")
    assert len(lignes) == len(reference)


def test_nettoyer_refuse_un_depot(tmp_path: Path, reference: pd.DataFrame) -> None:
    depot = tmp_path / "a" / "b" / "depot"
    (depot / ".git").mkdir(parents=True)
    with pytest.raises(ValueError, match="refus"):
        valider_integration(reference, reference, ENTREES, SORTIES, sortie=depot, nettoyer=True, figures=False, afficher=False)


def test_etiquettes_de_marge() -> None:
    assert [_etiquette_marge(v) for v in (0.0, 1.0, -1.0, 1e3, -1e5)] == ["$0$", "$1$", "$-1$", "$10^{3}$", "$-10^{5}$"]


def test_figures(reference: pd.DataFrame, tmp_path: Path) -> None:
    pytest.importorskip("cfd_plot")
    with glyphes_manquants_en_erreur():
        res = valider_integration(reference, _regression(reference), ENTREES, SORTIES, sortie=tmp_path,
                                  formats=("png",), afficher=False)
    figures = sorted(p.name for p in res.fichiers if p.suffix == ".png")
    assert figures == [
        "01_synthese_sorties.png",
        "02_marges_par_sortie.png",
        "03_repartition_marges.png",
        "04_marges_02_Cm.png",  # seule Cm est en échec : pas de figure par entrée pour CN
        "05_taux_echec_par_entree.png",
        "06_liaison_entrees_sorties.png",
    ]
    assert all(p.stat().st_size > 10_000 for p in res.fichiers if p.suffix == ".png")


def test_figures_conforme_sans_liaison(reference: pd.DataFrame, tmp_path: Path) -> None:
    pytest.importorskip("cfd_plot")
    test = reference.copy()
    test["CN"] = np.nextafter(test["CN"].to_numpy(), np.inf)
    res = valider_integration(reference, test, ENTREES, SORTIES, sortie=tmp_path, formats=("png",), afficher=False)
    noms = {p.name for p in res.fichiers}
    assert "06_liaison_entrees_sorties.png" not in noms  # aucun échec : rien à attribuer
    assert not any(n.startswith("04_") for n in noms)  # aucune sortie en échec
    assert {"01_synthese_sorties.png", "02_marges_par_sortie.png"} <= noms
