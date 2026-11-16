"""Figures du domaine réduit (``cfd-doe domaine --figures``) : contenu lu, fichiers écrits."""

from __future__ import annotations

import importlib.util
import warnings
from pathlib import Path
from typing import Any

import pytest

from cfd_doe.cli.main import main
from cfd_doe.data.etude import ErreurEtude, Etude, etude_depuis_dict
from cfd_doe.paths import EXEMPLE_DIR
from cfd_doe.report import figures_domaine as fd

CFD_PLOT = importlib.util.find_spec("cfd_plot") is not None
EXEMPLE = str(EXEMPLE_DIR / "ETUDE_FUSEE.yaml")
PLEIN = {"alpha": [-20, 20], "beta": [-5, 5], "DL": [-10, 10], "DM": [-20, 20], "DN": [-20, 20]}


def _etude(traj: str = "6DOF", geo: Any = "cruciforme") -> Etude:
    return etude_depuis_dict({"trajectoire": traj, "geometrie": geo, "variables": dict(PLEIN)})


class TestLecture:
    """Ce que les figures disent vient des sous-domaines."""

    def test_deux_reperes_meme_en_vol_plan(self) -> None:
        c = fd.comparer_reperes(_etude("3DOF_TANGAGE"))
        assert c.polaire is not None and c.retenu == "cartesien"

    def test_cruciforme_6dof_interieur_tous_les_plans_une_partie(self) -> None:
        c = fd.comparer_reperes(_etude())
        assert c.polaire is not None
        morceaux = fd._morceaux(c.polaire)
        assert [m.lettre for m in morceaux] == ["A", "B", "C", "D"]
        assert [fd._tous(c.polaire, m) for m in morceaux] == [True, False, False, False]
        assert fd._nature(c.polaire, morceaux[0]).startswith("intérieur")
        assert fd._nature(c.polaire, morceaux[1]) == "plan αt dans ]0 ; 20,59]°, φa = 0°"
        assert fd._nature(c.polaire, morceaux[3]) == "axe αt = 0"
        assert fd._restrictions(c.polaire, morceaux[1].sous_domaines[1]) == ["δnB = 0", "δl ≥ 0"]

    def test_cartesien_quart_de_rectangle(self) -> None:
        c = fd.comparer_reperes(_etude())
        natures = [fd._nature(c.cartesien, m) for m in fd._morceaux(c.cartesien)]
        assert natures[0] == "intérieur α dans ]0 ; 20]°, β dans ]0 ; 5]°"
        assert natures[-1] == "origine α = 0, β = 0"

    def test_chaque_sous_domaine_dans_un_seul_morceau(self) -> None:
        c = fd.comparer_reperes(_etude(geo={"type": "n_ailettes", "n_ailettes": 3}))
        for r in (c.cartesien, c.polaire):
            assert r is not None
            numeros = [sd.numero for m in fd._morceaux(r) for sd in m.sous_domaines]
            assert sorted(numeros) == [sd.numero for sd in r.sous_domaines]

    def test_decoupe_convexe_d_un_demi_disque(self) -> None:
        c = fd.comparer_reperes(_etude())
        assert c.polaire is not None
        plan = fd._morceaux(c.polaire)[1].sous_domaines[0]  # δnB > 0
        region = fd._region(plan, "DMB", "DNB")
        assert region[:, 1].min() == pytest.approx(0.0, abs=1e-9)
        assert region[:, 1].max() == pytest.approx(20.0, abs=1e-6)


@pytest.mark.skipif(not CFD_PLOT, reason="cfd-plot non installé")
@pytest.mark.parametrize(
    ("options", "attendus"),
    [
        ([], {"domaine_reperes", "domaine_braquages"}),
        (["--traj", "3DOF_TANGAGE"], {"domaine_reperes", "domaine_braquages"}),
        (
            ["--traj", "4DOF", "--geometrie", "n_ailettes", "--n-ailettes", "3"],
            {"domaine_reperes", "domaine_braquages"},
        ),
        (["--traj", "3DOF_MASSE_PONCTUELLE"], {"domaine_reperes"}),
        (["--traj", "2DOF", "--geometrie", "revolution"], {"domaine_reperes"}),
    ],
)
def test_cli_ecrit_les_figures(
    tmp_path: Path, options: list[str], attendus: set[str], capsys: pytest.CaptureFixture[str]
) -> None:
    dossier = tmp_path / "F"
    with warnings.catch_warnings(record=True) as avertissements:
        warnings.simplefilter("always")
        assert main(["domaine", EXEMPLE, *options, "--figures", str(dossier)]) == 0
    assert not [w for w in avertissements if "Glyph" in str(w.message)]
    fichiers = {p.name for p in dossier.iterdir()}
    assert fichiers == {f"{n}.svg" for n in attendus}
    assert all(p.stat().st_size > 10_000 for p in dossier.iterdir())
    assert "domaine_reperes" in capsys.readouterr().out


def test_sans_angle_libre_les_figures_refusent(tmp_path: Path) -> None:
    pytest.importorskip("cfd_plot")
    with pytest.raises(ErreurEtude, match="pas de plan des angles"):
        fd.tracer_figures_domaine(_etude("1DOF"), tmp_path)


def test_sans_cfd_plot_le_rapport_reste(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from cfd_doe.report import figures

    def absent() -> None:
        raise figures.FiguresIndisponibles("figures indisponibles (cfd_plot manquant)")

    monkeypatch.setattr(figures, "_cfd_plot", absent)
    assert main(["domaine", EXEMPLE, "--figures", str(tmp_path / "F")]) == 0
    sortie = capsys.readouterr().out
    assert "Sous-domaines à calculer (8)" in sortie and "figures indisponibles" in sortie
