"""Chaîne complète, de bout en bout.

Chaque étape consomme la sortie de la précédente, exactement comme un
utilisateur les enchaîne.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from cfd_traj.cli.main import EXIT_ACTION_REQUIRED, EXIT_OK, main

RACINE = Path(__file__).resolve().parents[1]
EXEMPLE = RACINE / "01_EXEMPLE"


def _pipeline(tmp_path: Path, *, methode: str = "lhs", n_parametres: int = 2, **etude) -> dict:
    """generer → inspecter → analyser → doe → couverture."""
    traj = tmp_path / "TRAJ"
    assert (
        main(
            [
                "generer",
                "--sortie",
                str(traj),
                "--n-tirs",
                "6",
                "--graine",
                "3",
                "--n-parametres",
                str(n_parametres),
            ]
        )
        == EXIT_OK
    )

    # The default ceiling is deliberately conservative; these tests exercise the
    # chain, not the guard, which has its own test in test_cli.py.
    study = traj / "ETUDE.yaml"
    substitutions = {"noeuds_max__2000": "noeuds_max: 200000", **etude}
    text = study.read_text()
    for old, new in substitutions.items():
        text = text.replace(old.replace("__", ": "), new)
    study.write_text(text)

    assert main(["inspecter", str(traj)]) == EXIT_OK
    assert main(["analyser", str(study), "--csv", str(tmp_path / "ENV.csv")]) == EXIT_OK

    plan = tmp_path / "PLAN.csv"
    assert main(["doe", str(study), "--methode", methode, "--sortie", str(plan)]) == EXIT_OK

    code = main(["couverture", str(study), "--csv", str(tmp_path / "HORS.csv")])
    assert code in (EXIT_OK, EXIT_ACTION_REQUIRED)

    return {
        "plan": pd.read_csv(plan),
        "enveloppe": pd.read_csv(tmp_path / "ENV.csv"),
        "code_couverture": code,
        "etude": study,
        "trajectoires": traj,
    }


class TestFullPipeline:
    def test_the_whole_chain_runs_and_produces_a_costed_plan(self, tmp_path, capsys):
        result = _pipeline(tmp_path)
        capsys.readouterr()

        plan = result["plan"]
        assert len(plan) > 0
        assert plan["cout_relatif"].sum() < len(plan)
        assert not result["enveloppe"].empty

    def test_the_tensor_method_also_runs_end_to_end(self, tmp_path, capsys):
        result = _pipeline(tmp_path, methode="tensoriel", n_parametres=1)
        capsys.readouterr()

        assert len(result["plan"]) > 0
        assert "tensoriel" not in result["plan"].columns

    def test_a_full_range_envelope_covers_everything(self, tmp_path, capsys):
        result = _pipeline(
            tmp_path,
            **{
                "quantile_bas__0.001": "quantile_bas: 0.0",
                "quantile_haut__0.999": "quantile_haut: 1.0",
            },
        )
        capsys.readouterr()

        assert result["code_couverture"] == EXIT_OK

    @pytest.mark.parametrize("n_parametres", [0, 1, 5])
    def test_any_number_of_generic_columns_survives_the_chain(self, tmp_path, capsys, n_parametres):
        result = _pipeline(tmp_path, n_parametres=n_parametres)
        capsys.readouterr()

        for i in range(n_parametres):
            assert f"PARA{i + 1}" in result["plan"].columns
        assert len(result["plan"]) > 0

    @pytest.mark.parametrize("groupe", ["Cinfv", "C4v", "C4", "Cs", "C1"])
    def test_every_symmetry_group_runs_the_chain(self, tmp_path, capsys, groupe):
        result = _pipeline(tmp_path, **{"groupe__C4v": f"groupe: {groupe}"})
        capsys.readouterr()

        assert len(result["plan"]) > 0
        assert set(result["plan"]["configuration"]) <= {
            "axisymetrique_2d",
            "secteur_45",
            "quart_90_cyclique",
            "demi_configuration",
            "configuration_complete",
        }

    def test_the_symmetry_gain_shrinks_as_the_group_shrinks(self, tmp_path, capsys):
        # Cinfv folds every azimuth onto one; C1 folds nothing. The mean cost
        # per case must grow monotonically as symmetry is given up.
        couts = {}
        for groupe in ("Cinfv", "C4v", "C1"):
            directory = tmp_path / groupe
            directory.mkdir()
            result = _pipeline(directory, **{"groupe__C4v": f"groupe: {groupe}"})
            couts[groupe] = result["plan"]["cout_relatif"].mean()
        capsys.readouterr()

        assert couts["Cinfv"] < couts["C4v"] < couts["C1"]
        assert couts["C1"] == pytest.approx(1.0)


class TestDeterminism:
    def test_two_identical_runs_produce_identical_plans(self, tmp_path, capsys):
        first = _pipeline(tmp_path / "a", methode="lhs")
        second = _pipeline(tmp_path / "b", methode="lhs")
        capsys.readouterr()

        pd.testing.assert_frame_equal(first["plan"], second["plan"])

    def test_the_generated_lot_is_byte_identical(self, tmp_path, capsys):
        for name in ("a", "b"):
            main(
                [
                    "generer",
                    "--sortie",
                    str(tmp_path / name),
                    "--n-tirs",
                    "3",
                    "--graine",
                    "55",
                ]
            )
        capsys.readouterr()

        left = sorted((tmp_path / "a").glob("tir_*.csv"))
        right = sorted((tmp_path / "b").glob("tir_*.csv"))
        assert [p.read_bytes() for p in left] == [p.read_bytes() for p in right]


class TestShippedExample:
    def test_the_example_study_analyses(self, capsys):
        assert main(["analyser", str(EXEMPLE / "ETUDE.yaml")]) == EXIT_OK
        capsys.readouterr()

    def test_the_example_produces_its_plan(self, tmp_path, capsys):
        target = tmp_path / "PLAN.csv"

        assert main(["doe", str(EXEMPLE / "ETUDE.yaml"), "--sortie", str(target)]) == EXIT_OK
        capsys.readouterr()

        plan = pd.read_csv(target)
        assert len(plan) > 100
        assert plan["cout_relatif"].sum() < len(plan)

    def test_the_example_coverage_is_all_but_complete(self, capsys):
        code = main(["couverture", str(EXEMPLE / "ETUDE.yaml")])
        out = capsys.readouterr().out

        assert code in (EXIT_OK, EXIT_ACTION_REQUIRED)
        assert "99," in out or "100," in out

    def test_a_copy_of_the_example_runs_from_anywhere(self, tmp_path, capsys, monkeypatch):
        destination = tmp_path / "EX"
        assert main(["example", "--output", str(destination)]) == EXIT_OK
        monkeypatch.chdir(tmp_path)

        assert main(["doe", str(destination / "ETUDE.yaml")]) == EXIT_OK
        capsys.readouterr()
        assert (destination / "SORTIE" / "PLAN.csv").exists()

    @pytest.mark.slow
    def test_the_example_script_runs(self, tmp_path):
        destination = tmp_path / "EX"
        main(["example", "--output", str(destination)])
        env = {
            **os.environ,
            "PATH": f"{RACINE / '.venv' / 'bin'}{os.pathsep}{os.environ['PATH']}",
        }

        proc = subprocess.run(
            ["bash", str(destination / "RUN_EXEMPLE.sh")],
            capture_output=True,
            text=True,
            env=env,
        )

        assert proc.returncode == 0, proc.stderr
        assert list((destination / "SORTIE").glob("*.png"))


class TestModuleEntryPoint:
    def test_python_dash_m_runs_the_shipped_example(self, tmp_path):
        env = {
            **os.environ,
            "PYTHONPATH": str(RACINE / "src"),
            "HOME": str(tmp_path),
        }

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "cfd_traj",
                "doe",
                str(EXEMPLE / "ETUDE.yaml"),
                "--sortie",
                str(tmp_path / "PLAN.csv"),
            ],
            capture_output=True,
            text=True,
            env=env,
        )

        assert proc.returncode == 0, proc.stderr
        assert "équivalents configuration complète" in proc.stdout
        assert "Traceback" not in proc.stderr
