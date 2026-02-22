"""Tests for the CLI entry-point argument parsing and dispatch."""

import json
from pathlib import Path

import pytest

from cfd_perf.cli.main import main


@pytest.fixture()
def mesh_json(tmp_path: Path) -> Path:
    p = tmp_path / "mesh.json"
    p.write_text(json.dumps({"num_cells": 2_000_000, "num_faces": 6_000_000}))
    return p


@pytest.fixture()
def pilot_json(tmp_path: Path) -> Path:
    p = tmp_path / "pilot.json"
    p.write_text(json.dumps({
        "n_iterations": 5000,
        "points": [
            {"cores": 64, "time_per_iter_s": 1.0, "peak_ram_total_gb": 32.0},
        ],
    }))
    return p


class TestAnalyze:
    def test_runs_json(self, mesh_json: Path, capsys: pytest.CaptureFixture[str]) -> None:
        main(["analyze", str(mesh_json), "--json"])
        out = json.loads(capsys.readouterr().out)
        assert out["num_cells"] == 2_000_000

    def test_with_pilot_json(self, mesh_json: Path, pilot_json: Path, capsys: pytest.CaptureFixture[str]) -> None:
        main(["analyze", str(mesh_json), "--pilot", str(pilot_json), "--json"])
        out = json.loads(capsys.readouterr().out)
        assert out["estimated_mem_per_cell_bytes"] is not None

    def test_rich_output(self, mesh_json: Path, capsys: pytest.CaptureFixture[str]) -> None:
        main(["analyze", str(mesh_json)])
        out = capsys.readouterr().out
        assert "Mesh Analysis" in out
        assert "2,000,000" in out


class TestFit:
    def test_runs_default_json(self, pilot_json: Path, capsys: pytest.CaptureFixture[str]) -> None:
        main(["fit", str(pilot_json), "--json"])
        out = json.loads(capsys.readouterr().out)
        assert out["beta"] == 0.25
        assert out["beta_source"] == "fixed"

    def test_beta_fixed_json(self, pilot_json: Path, capsys: pytest.CaptureFixture[str]) -> None:
        main(["fit", str(pilot_json), "--beta-fixed", "0.3", "--json"])
        out = json.loads(capsys.readouterr().out)
        assert out["beta"] == 0.3

    def test_rich_output(self, pilot_json: Path, capsys: pytest.CaptureFixture[str]) -> None:
        main(["fit", str(pilot_json)])
        out = capsys.readouterr().out
        assert "Scaling Model Fit" in out


class TestOptimize:
    def test_efficiency_mode_json(
        self, mesh_json: Path, pilot_json: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main([
            "optimize",
            "--mesh", str(mesh_json),
            "--pilot", str(pilot_json),
            "--max-loss", "0.30",
            "--cores-max", "256",
            "--json",
        ])
        out = json.loads(capsys.readouterr().out)
        assert out["mode"] == "efficiency"

    def test_deadline_mode_json(
        self, mesh_json: Path, pilot_json: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main([
            "optimize",
            "--mesh", str(mesh_json),
            "--pilot", str(pilot_json),
            "--deadline", "6h",
            "--cores-max", "256",
            "--json",
        ])
        out = json.loads(capsys.readouterr().out)
        assert out["mode"] == "deadline"

    def test_mutually_exclusive(self, mesh_json: Path, pilot_json: Path) -> None:
        with pytest.raises(SystemExit):
            main([
                "optimize",
                "--mesh", str(mesh_json),
                "--pilot", str(pilot_json),
                "--max-loss", "0.3",
                "--deadline", "6h",
            ])

    def test_rich_output(
        self, mesh_json: Path, pilot_json: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main([
            "optimize",
            "--mesh", str(mesh_json),
            "--pilot", str(pilot_json),
            "--max-loss", "0.30",
            "--cores-max", "256",
        ])
        out = capsys.readouterr().out
        assert "Optimization Result" in out or "Optimal Configuration" in out
