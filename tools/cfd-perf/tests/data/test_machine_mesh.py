"""Tests for the machine and mesh models."""

from __future__ import annotations

import pytest

from cfd_perf.data.machine import Machine
from cfd_perf.data.mesh import mesh_from_data


class TestMachine:
    def test_nodes_round_up(self):
        m = Machine(cores_per_node=48)
        assert m.nodes_for(48) == 1
        assert m.nodes_for(49) == 2
        assert m.nodes_for(96) == 2

    def test_is_full_nodes(self):
        m = Machine(cores_per_node=48)
        assert m.is_full_nodes(96)
        assert not m.is_full_nodes(100)

    def test_max_cores_from_max_nodes(self):
        assert Machine(cores_per_node=48, max_nodes=32).max_cores == 1536
        assert Machine(cores_per_node=48).max_cores is None

    def test_candidates_are_whole_nodes(self):
        m = Machine(cores_per_node=48)
        assert m.candidate_core_counts(48, 200) == [48, 96, 144, 192]

    def test_candidates_keep_a_partial_node_baseline(self):
        """The pilot baseline must stay on the curve even if it is not a full node."""
        m = Machine(cores_per_node=48)
        counts = m.candidate_core_counts(40, 100)
        assert counts[0] == 40
        assert 48 in counts and 96 in counts

    def test_candidates_every_count_on_a_serial_machine(self):
        assert Machine().candidate_core_counts(4, 8) == [4, 5, 6, 7, 8]

    def test_invalid_range_rejected(self):
        with pytest.raises(ValueError, match="nc_min <= nc_max"):
            Machine().candidate_core_counts(10, 5)

    def test_validation(self):
        with pytest.raises(ValueError, match="cores_per_node must be positive"):
            Machine(cores_per_node=0)
        with pytest.raises(ValueError, match="max_nodes must be positive"):
            Machine(max_nodes=-1)


class TestMesh:
    def test_memory_inferred_from_pilot(self, pilot):
        mesh = mesh_from_data(num_cells=20_000_000, pilot=pilot)
        assert mesh.mem_source == "measured (pilot)"
        assert mesh.total_ram_gb == pytest.approx(148.0, rel=1e-6)

    def test_user_value_takes_precedence(self, pilot):
        mesh = mesh_from_data(num_cells=20_000_000, mem_per_cell_bytes=8000, pilot=pilot)
        assert mesh.mem_source == "user"
        assert mesh.mem_per_cell_bytes == 8000

    def test_memory_unknown_without_data(self):
        mesh = mesh_from_data(num_cells=20_000_000)
        assert mesh.mem_source == "unknown"
        assert mesh.total_ram_gb is None
        assert mesh.ram_per_core_gb(48) is None

    def test_ram_per_core_splits_the_total(self, pilot):
        mesh = mesh_from_data(num_cells=20_000_000, pilot=pilot)
        assert mesh.ram_per_core_gb(148) == pytest.approx(mesh.total_ram_gb / 148)

    def test_cells_per_core(self):
        mesh = mesh_from_data(num_cells=20_000_000)
        assert mesh.cells_per_core(200) == 100_000

    def test_rejects_bad_geometry(self):
        with pytest.raises(ValueError, match="num_cells must be positive"):
            mesh_from_data(num_cells=0)
        with pytest.raises(ValueError, match="num_faces must be positive"):
            mesh_from_data(num_cells=10, num_faces=-1)

    def test_rejects_zero_cores(self):
        mesh = mesh_from_data(num_cells=20_000_000)
        with pytest.raises(ValueError, match="nc must be positive"):
            mesh.cells_per_core(0)
