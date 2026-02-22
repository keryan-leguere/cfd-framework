"""Tests for the memory model."""

import pytest

from cfd_perf.mesh.models import MeshStats
from cfd_perf.models.memory import ram_per_core_gb, total_ram_gb

GB = 1 << 30


class TestTotalRamGb:
    def test_known_mem_per_cell(self) -> None:
        mesh = MeshStats(num_cells=1_000_000, num_faces=3_000_000, estimated_mem_per_cell_bytes=2048.0)
        expected = 2048.0 * 1_000_000 / GB
        assert total_ram_gb(mesh) == pytest.approx(expected)

    def test_unknown_returns_none(self) -> None:
        mesh = MeshStats(num_cells=1_000_000, num_faces=3_000_000)
        assert total_ram_gb(mesh) is None


class TestRamPerCoreGb:
    def test_divides_evenly(self) -> None:
        mesh = MeshStats(num_cells=1_000_000, num_faces=3_000_000, estimated_mem_per_cell_bytes=2048.0)
        total = 2048.0 * 1_000_000 / GB
        assert ram_per_core_gb(mesh, 10) == pytest.approx(total / 10)

    def test_unknown_returns_none(self) -> None:
        mesh = MeshStats(num_cells=1_000_000, num_faces=3_000_000)
        assert ram_per_core_gb(mesh, 10) is None
