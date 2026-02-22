"""Tests for mesh analyzer."""

import json
from pathlib import Path

import pytest

from cfd_perf.benchmark.models import PilotPoint
from cfd_perf.mesh.analyzer import analyze_mesh


@pytest.fixture()
def mesh_json(tmp_path: Path) -> Path:
    p = tmp_path / "mesh.json"
    p.write_text(json.dumps({"num_cells": 2_000_000, "num_faces": 6_000_000}))
    return p


class TestAnalyzeMesh:
    def test_basic(self, mesh_json: Path) -> None:
        stats = analyze_mesh(mesh_json)
        assert stats.num_cells == 2_000_000
        assert stats.num_faces == 6_000_000
        assert stats.estimated_mem_per_cell_bytes is None

    def test_user_mem_per_cell(self, mesh_json: Path) -> None:
        stats = analyze_mesh(mesh_json, user_mem_per_cell_bytes=1500.0)
        assert stats.estimated_mem_per_cell_bytes == 1500.0

    def test_infer_from_pilot(self, mesh_json: Path) -> None:
        pilot = PilotPoint(cores=64, time_per_iter_s=1.0, peak_ram_total_gb=32.0)
        stats = analyze_mesh(mesh_json, pilot_baseline=pilot)
        expected = (32.0 * (1 << 30)) / 2_000_000
        assert stats.estimated_mem_per_cell_bytes == pytest.approx(expected, rel=1e-9)

    def test_user_wins_over_pilot(self, mesh_json: Path) -> None:
        pilot = PilotPoint(cores=64, time_per_iter_s=1.0, peak_ram_total_gb=32.0)
        stats = analyze_mesh(mesh_json, pilot_baseline=pilot, user_mem_per_cell_bytes=999.0)
        assert stats.estimated_mem_per_cell_bytes == 999.0
