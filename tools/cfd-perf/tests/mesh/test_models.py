"""Tests for mesh data models."""

import pytest

from cfd_perf.mesh.models import MeshStats


class TestMeshStats:
    def test_valid(self) -> None:
        ms = MeshStats(num_cells=1_000_000, num_faces=3_000_000)
        assert ms.num_cells == 1_000_000
        assert ms.num_faces == 3_000_000
        assert ms.cell_type_distribution is None
        assert ms.estimated_mem_per_cell_bytes is None

    def test_with_optionals(self) -> None:
        ms = MeshStats(
            num_cells=500_000,
            num_faces=1_500_000,
            cell_type_distribution={"hex": 0.9, "tet": 0.1},
            estimated_mem_per_cell_bytes=2048.0,
        )
        assert ms.cell_type_distribution == {"hex": 0.9, "tet": 0.1}
        assert ms.estimated_mem_per_cell_bytes == 2048.0

    def test_zero_cells_rejected(self) -> None:
        with pytest.raises(ValueError, match="num_cells must be positive"):
            MeshStats(num_cells=0, num_faces=100)

    def test_negative_faces_rejected(self) -> None:
        with pytest.raises(ValueError, match="num_faces must be positive"):
            MeshStats(num_cells=100, num_faces=-1)
