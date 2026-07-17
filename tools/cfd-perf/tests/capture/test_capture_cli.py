"""Tests de bout en bout du sous-commande `cfd-perf capture` (adaptateur mock)."""

from __future__ import annotations

import glob

import matplotlib
import pytest

matplotlib.use("Agg")

from cfd_perf.cli.main import main
from cfd_perf.data.study import load_study


@pytest.fixture
def case(tmp_path):
    d = tmp_path / "AILE_M6"
    d.mkdir()
    return d


def _submit(case, coeurs="4 8 16"):
    return main(["capture", "--coeurs", coeurs, "--adaptateur", "mock", "--case-dir", str(case)])


class TestSubmit:
    def test_submit_writes_manifest_and_run_dirs(self, case, capsys):
        assert _submit(case) == 0
        out = capsys.readouterr().out
        assert "soumis" in out
        assert (case / "PILOTE" / "manifest.json").is_file()
        assert len(glob.glob(str(case / "PILOTE" / "mock_*"))) == 3

    def test_submit_without_coeurs_fails_cleanly(self, case, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["capture", "--adaptateur", "mock", "--case-dir", str(case)])
        assert exc.value.code == 1
        assert "--coeurs" in capsys.readouterr().err

    def test_unknown_adapter_fails_cleanly(self, case, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["capture", "--coeurs", "4", "--adaptateur", "nope", "--case-dir", str(case)])
        assert exc.value.code == 1
        assert "introuvable" in capsys.readouterr().err

    def test_missing_case_dir_fails_cleanly(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["capture", "--coeurs", "4", "--case-dir", str(tmp_path / "absent")])
        assert exc.value.code == 1
        assert "introuvable" in capsys.readouterr().err


class TestCollect:
    def test_collect_generates_valid_study(self, case, capsys):
        _submit(case)
        capsys.readouterr()
        code = main(["capture", "--collect", "--case-dir", str(case), "--no-run",
                     "--cores-per-node", "4"])
        assert code == 0
        out = capsys.readouterr().out
        assert "Étude générée" in out

        study_path = case / "ETUDE.yaml"
        assert study_path.is_file()
        study = load_study(study_path)
        assert len(study.pilot.points) == 3
        assert [p.cores for p in study.pilot.points] == [4, 8, 16]

    def test_collect_then_recommend_prints_french_report(self, case, capsys):
        _submit(case)
        capsys.readouterr()
        code = main(["capture", "--collect", "--case-dir", str(case), "--cores-per-node", "4"])
        assert code == 0
        out = capsys.readouterr().out
        assert "Réponse" in out
        assert "cœurs" in out

    def test_collect_writes_figure(self, case, tmp_path):
        _submit(case)
        fig = tmp_path / "scal.png"
        code = main(["capture", "--collect", "--case-dir", str(case),
                     "--cores-per-node", "4", "--figure", str(fig)])
        assert code == 0
        assert fig.is_file() and fig.stat().st_size > 10_000

    def test_collect_before_submit_fails_cleanly(self, case, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["capture", "--collect", "--case-dir", str(case)])
        assert exc.value.code == 1
        assert "manifeste introuvable" in capsys.readouterr().err

    def test_num_cells_and_n_iterations_overrides(self, case, capsys):
        _submit(case)
        capsys.readouterr()
        main(["capture", "--collect", "--case-dir", str(case), "--no-run",
              "--num-cells", "9000000", "--n-iterations", "20000", "--cores-per-node", "4"])
        study = load_study(case / "ETUDE.yaml")
        assert study.mesh.num_cells == 9_000_000
        assert study.pilot.n_iterations == 20_000


class TestPending:
    def test_unfinished_run_reports_and_exits_nonzero(self, case, capsys):
        _submit(case)
        capsys.readouterr()
        # Simule un run non terminé en supprimant son log.
        logs = glob.glob(str(case / "PILOTE" / "mock_8_*" / "run.log"))
        assert logs
        for log in logs:
            import os

            os.remove(log)
        code = main(["capture", "--collect", "--case-dir", str(case), "--no-run"])
        assert code == 3
        out = capsys.readouterr().out
        assert "cours" in out.lower()
        assert not (case / "ETUDE.yaml").exists()
