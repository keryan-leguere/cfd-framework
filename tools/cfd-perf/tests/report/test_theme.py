"""Le rapport doit rester lisible là où le gras ne l'est pas.

Beaucoup de terminaux rendent le gras par une couleur « bright » plus claire ;
sur un fond clair, un titre ou une réponse en gras devient délavé, voire
invisible. Ces tests verrouillent la règle : aucune séquence ANSI de gras
(SGR 1) ne doit sortir du rapport, sauf demande explicite via CFD_PERF_GRAS.
"""

from __future__ import annotations

import importlib
import io
import re

import pytest
from rich.console import Console

from cfd_perf.cli.main import main
from cfd_perf.core.model import fit_model
from cfd_perf.data.study import load_study
from cfd_perf.engine.recommend import recommend
from cfd_perf.paths import EXEMPLE_DIR
from cfd_perf.report import theme
from cfd_perf.report.console import print_report

EXAMPLE = EXEMPLE_DIR / "ONERA_M6_CRUISE.yaml"

_SGR = re.compile(r"\x1b\[([0-9;]*)m")


def parametres_sgr(texte: str) -> set[str]:
    """Tous les paramètres SGR présents dans *texte* (« 1 » = gras)."""
    trouves: set[str] = set()
    for sequence in _SGR.findall(texte):
        trouves.update(p for p in sequence.split(";") if p)
    return trouves


def rendu_couleur(largeur: int = 100) -> Console:
    """Console qui émet réellement les codes ANSI, comme un vrai terminal."""
    return Console(
        file=io.StringIO(), force_terminal=True, color_system="truecolor", width=largeur
    )


@pytest.fixture
def consoles_cli(monkeypatch):
    """Remplace les Consoles du CLI par des Consoles couleur capturées."""
    from cfd_perf.cli import main as cli_main

    sortie, erreurs = rendu_couleur(), rendu_couleur()
    monkeypatch.setattr(cli_main, "console", sortie)
    monkeypatch.setattr(cli_main, "err_console", erreurs)
    return sortie.file, erreurs.file


@pytest.fixture
def recommandation():
    study = load_study(EXAMPLE)
    model = fit_model(study.pilot)
    rec = recommend(
        model=model,
        mesh=study.mesh,
        pilot=study.pilot,
        machine=study.machine,
        constraints=study.constraints,
    )
    return rec, study


class TestPasDeGras:
    def test_le_rapport_complet_nemet_aucun_gras(self, recommandation):
        rec, study = recommandation
        con = rendu_couleur()
        print_report(rec, study, verbose=True, con=con)
        sortie = con.file.getvalue()

        assert "1" not in parametres_sgr(sortie)
        assert "36" in parametres_sgr(sortie), "les titres doivent rester colorés"

    def test_les_commandes_du_cli_nemettent_aucun_gras(self, consoles_cli, tmp_path):
        sortie, _ = consoles_cli
        assert main(["check", str(EXAMPLE)]) == 0
        assert main(["run", str(EXAMPLE), "-v"]) == 0
        assert main(["example", "--output", str(tmp_path / "ex")]) == 0

        params = parametres_sgr(sortie.getvalue())
        assert params, "le test serait vide sans codes ANSI"
        assert "1" not in params

    def test_les_erreurs_nemettent_aucun_gras(self, consoles_cli):
        _, erreurs = consoles_cli
        with pytest.raises(SystemExit):
            main(["run", "/introuvable/etude.yaml"])

        params = parametres_sgr(erreurs.getvalue())
        assert params, "le test serait vide sans codes ANSI"
        assert "1" not in params


class TestReglageUtilisateur:
    def test_cfd_perf_gras_reactive_le_gras(self, monkeypatch):
        monkeypatch.setenv(theme.ENV_GRAS, "1")
        recharge = importlib.reload(theme)
        try:
            assert recharge.gras_actif() is True
            assert recharge.TITRE.startswith("bold ")
            assert recharge.ACCENT.startswith("bold ")
        finally:
            monkeypatch.delenv(theme.ENV_GRAS)
            importlib.reload(theme)

    def test_le_gras_est_desactive_par_defaut(self, monkeypatch):
        monkeypatch.delenv(theme.ENV_GRAS, raising=False)
        recharge = importlib.reload(theme)
        assert recharge.gras_actif() is False
        assert "bold" not in " ".join(
            [recharge.TITRE, recharge.ACCENT, recharge.OK, recharge.ATTENTION, recharge.ERREUR]
        )
