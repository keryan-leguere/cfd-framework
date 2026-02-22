"""Tests for mesh adapters."""

import json
from pathlib import Path

import pytest

from cfd_perf.mesh.adapters import JsonMeshAdapter, get_adapter


@pytest.fixture()
def mesh_json(tmp_path: Path) -> Path:
    p = tmp_path / "mesh.json"
    p.write_text(json.dumps({
        "num_cells": 5_000_000,
        "num_faces": 15_000_000,
        "cell_type_distribution": {"hex": 0.85, "tet": 0.15},
    }))
    return p


class TestJsonMeshAdapter:
    def test_can_handle(self, mesh_json: Path) -> None:
        assert JsonMeshAdapter.can_handle(mesh_json)

    def test_cannot_handle_other(self, tmp_path: Path) -> None:
        assert not JsonMeshAdapter.can_handle(tmp_path / "mesh.cgns")

    def test_read(self, mesh_json: Path) -> None:
        adapter = JsonMeshAdapter()
        raw = adapter.read(mesh_json)
        assert raw.num_cells == 5_000_000
        assert raw.num_faces == 15_000_000
        assert raw.cell_type_distribution == {"hex": 0.85, "tet": 0.15}


class TestGetAdapter:
    def test_auto_detect_json(self, mesh_json: Path) -> None:
        adapter = get_adapter(mesh_json)
        assert isinstance(adapter, JsonMeshAdapter)

    def test_force_json(self, mesh_json: Path) -> None:
        adapter = get_adapter(mesh_json, adapter_name="json")
        assert isinstance(adapter, JsonMeshAdapter)

    def test_unknown_format_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="No mesh adapter found"):
            get_adapter(tmp_path / "mesh.cgns")
