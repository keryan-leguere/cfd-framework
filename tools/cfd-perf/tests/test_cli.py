"""End-to-end CLI tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from cfd_perf.cli.main import main

EXAMPLE = Path(__file__).resolve().parents[1] / "01_EXEMPLE" / "ONERA_M6_CRUISE.yaml"


class TestRun:
    def test_shipped_example_runs_successfully(self, capsys):
        assert main(["run", str(EXAMPLE)]) == 0
        out = capsys.readouterr().out
        assert "Réponse" in out
        assert "cœurs" in out

    def test_writes_a_figure(self, tmp_path, capsys):
        fig = tmp_path / "scaling.png"
        assert main(["run", str(EXAMPLE), "--figure", str(fig)]) == 0
        assert fig.is_file() and fig.stat().st_size > 10_000
        assert "Figure écrite" in capsys.readouterr().out

    @pytest.mark.parametrize("strategy", ["efficiency", "fastest"])
    def test_every_strategy_runs(self, strategy):
        assert main(["run", str(EXAMPLE), "--strategy", strategy]) == 0

    def test_deadline_strategy_with_the_deadline_flag(self, capsys):
        assert main(["run", str(EXAMPLE), "--strategy", "deadline", "--deadline", "6"]) == 0
        assert "Réponse" in capsys.readouterr().out

    def test_deadline_strategy_without_a_deadline_hints_at_the_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["run", str(EXAMPLE), "--strategy", "deadline"])
        assert exc.value.code == 1
        assert "--deadline" in capsys.readouterr().err

    def test_cores_max_override(self, capsys):
        assert main(["run", str(EXAMPLE), "--cores-max", "192", "-v"]) == 0
        assert "Réponse" in capsys.readouterr().out

    def test_verbose_prints_the_curve(self, capsys):
        main(["run", str(EXAMPLE), "-v"])
        assert "Courbe de scalabilité" in capsys.readouterr().out

    def test_forcing_the_amdahl_model(self, capsys):
        assert main(["run", str(EXAMPLE), "--model", "amdahl"]) == 0
        assert "amdahl" in capsys.readouterr().out

    def test_missing_file_exits_cleanly(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["run", "/nonexistent/study.yaml"])
        assert exc.value.code == 1
        assert "introuvable" in capsys.readouterr().err

    def test_invalid_study_exits_cleanly_without_a_traceback(self, tmp_path, capsys):
        bad = tmp_path / "bad.yaml"
        bad.write_text("study: {name: t}\nmesh: {}\n")
        with pytest.raises(SystemExit) as exc:
            main(["run", str(bad)])
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "Erreur" in err
        assert "Traceback" not in err


class TestCheck:
    def test_valid_study_passes(self, capsys):
        assert main(["check", str(EXAMPLE)]) == 0
        assert "valide" in capsys.readouterr().out

    def test_invalid_study_fails(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("study: {name: t, n_iterations: 10}\nmesh: {num_cells: 100}\n")
        with pytest.raises(SystemExit):
            main(["check", str(bad)])


class TestExample:
    def test_copies_a_runnable_example(self, tmp_path, capsys):
        dest = tmp_path / "work"
        assert main(["example", "--output", str(dest)]) == 0
        study = next(dest.glob("*.yaml"))
        assert main(["run", str(study)]) == 0

    def test_refuses_to_overwrite_a_non_empty_directory(self, tmp_path):
        dest = tmp_path / "work"
        dest.mkdir()
        (dest / "keep.txt").write_text("mine")
        with pytest.raises(SystemExit):
            main(["example", "--output", str(dest)])
        assert (dest / "keep.txt").read_text() == "mine"


class TestModuleEntryPoint:
    """``python -m cfd_perf`` doit valoir la commande ``cfd-perf``.

    C'est la voie d'accès des installations sans script console (sources
    atteintes par PYTHONPATH), documentée dans le README.
    """

    def test_runs_the_shipped_example(self, tmp_path):
        src = Path(__file__).resolve().parents[1] / "src"
        env = {**os.environ, "PYTHONPATH": str(src), "HOME": str(tmp_path)}
        proc = subprocess.run(
            [sys.executable, "-m", "cfd_perf", "run", str(EXAMPLE)],
            capture_output=True, text=True, env=env,
        )
        assert proc.returncode == 0, proc.stderr
        assert "Réponse" in proc.stdout


class TestParser:
    def test_no_command_is_an_error(self):
        with pytest.raises(SystemExit):
            main([])

    def test_unknown_strategy_rejected_by_the_parser(self):
        with pytest.raises(SystemExit):
            main(["run", str(EXAMPLE), "--strategy", "cheapest"])
