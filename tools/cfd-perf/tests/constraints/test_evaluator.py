"""Tests for hard constraint evaluator."""

from cfd_perf.constraints.config import HardConstraints
from cfd_perf.constraints.evaluator import check_hard_constraints
from cfd_perf.mesh.models import MeshStats

GB = 1 << 30


class TestCheckHardConstraints:
    def test_all_pass(self) -> None:
        mem_per_cell = 128.0 * GB / 10_000_000  # 128 GB total => 2 GB/core at 64 cores
        mesh = MeshStats(
            num_cells=10_000_000,
            num_faces=30_000_000,
            estimated_mem_per_cell_bytes=mem_per_cell,
        )
        hc = HardConstraints(min_cells_per_core=100_000, min_ram_per_core_gb=2.0)
        violations = check_hard_constraints(nc=64, mesh=mesh, constraints=hc)
        assert violations == []

    def test_cells_per_core_violated(self) -> None:
        mem_per_cell = 100.0 * GB / 500_000  # 100 GB total => 10 GB/core at 10 cores
        mesh = MeshStats(num_cells=500_000, num_faces=1_500_000, estimated_mem_per_cell_bytes=mem_per_cell)
        hc = HardConstraints(min_cells_per_core=100_000, min_ram_per_core_gb=2.0)
        violations = check_hard_constraints(nc=4, mesh=mesh, constraints=hc)
        assert violations == []
        violations = check_hard_constraints(nc=6, mesh=mesh, constraints=hc)
        assert "cells_per_core" in violations

    def test_ram_per_core_violated(self) -> None:
        mem_per_cell = 2.0 * GB / 1_000_000  # exactly 2 GB total for 1M cells
        mesh = MeshStats(num_cells=1_000_000, num_faces=3_000_000, estimated_mem_per_cell_bytes=mem_per_cell)
        hc = HardConstraints(min_ram_per_core_gb=2.0)
        violations = check_hard_constraints(nc=1, mesh=mesh, constraints=hc)
        assert violations == []
        violations = check_hard_constraints(nc=2, mesh=mesh, constraints=hc)
        assert "ram_per_core" in violations

    def test_unknown_mem_skips_ram_check(self) -> None:
        mesh = MeshStats(num_cells=1_000_000, num_faces=3_000_000)
        hc = HardConstraints(min_ram_per_core_gb=2.0)
        violations = check_hard_constraints(nc=64, mesh=mesh, constraints=hc)
        assert "ram_per_core" not in violations

    def test_boundary_exact(self) -> None:
        mem_per_cell = 20.0 * GB / 1_000_000  # 20 GB total => 2 GB/core at 10 cores
        mesh = MeshStats(num_cells=1_000_000, num_faces=3_000_000, estimated_mem_per_cell_bytes=mem_per_cell)
        hc = HardConstraints(min_cells_per_core=100_000, min_ram_per_core_gb=2.0)
        violations = check_hard_constraints(nc=10, mesh=mesh, constraints=hc)
        assert violations == []
