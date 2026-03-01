"""Tests for mesh analyzer."""

import json
from pathlib import Path

import pandas as pd
import pytest

from cfd_perf.benchmark.models import PilotPoint
from cfd_perf.mesh.analyzer import analyze_mesh, mesh_from_data


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


class TestMeshFromData:
    def test_from_dict_basic(self) -> None:
        data = {"num_cells": 2_000_000, "num_faces": 6_000_000}
        stats = mesh_from_data(data)
        assert stats.num_cells == 2_000_000
        assert stats.num_faces == 6_000_000
        assert stats.estimated_mem_per_cell_bytes is None

    def test_from_dict_with_cell_dist(self) -> None:
        data = {
            "num_cells": 1_000_000,
            "num_faces": 3_000_000,
            "cell_type_distribution": {"hex": 0.8, "tet": 0.2},
        }
        stats = mesh_from_data(data)
        assert stats.cell_type_distribution == {"hex": 0.8, "tet": 0.2}

    def test_from_dict_pilot_baseline(self) -> None:
        data = {"num_cells": 2_000_000, "num_faces": 6_000_000}
        pilot = PilotPoint(cores=64, time_per_iter_s=1.0, peak_ram_total_gb=32.0)
        stats = mesh_from_data(data, pilot_baseline=pilot)
        expected = (32.0 * (1 << 30)) / 2_000_000
        assert stats.estimated_mem_per_cell_bytes == pytest.approx(expected, rel=1e-9)

    def test_from_dict_user_mem(self) -> None:
        data = {"num_cells": 1_000_000, "num_faces": 3_000_000}
        stats = mesh_from_data(data, user_mem_per_cell_bytes=1200.0)
        assert stats.estimated_mem_per_cell_bytes == 1200.0

    def test_from_dataframe(self) -> None:
        df = pd.DataFrame([{"num_cells": 5_000_000, "num_faces": 15_000_000}])
        stats = mesh_from_data(df)
        assert stats.num_cells == 5_000_000
        assert stats.num_faces == 15_000_000

    def test_from_dataframe_empty_raises(self) -> None:
        df = pd.DataFrame(columns=["num_cells", "num_faces"])
        with pytest.raises(ValueError, match="at least one row"):
            mesh_from_data(df)

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(TypeError, match="dict or pandas DataFrame"):
            mesh_from_data([1, 2, 3])  # type: ignore[arg-type]
