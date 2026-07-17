"""Tests for hard-constraint checking."""

from __future__ import annotations

import pytest

from cfd_perf.core.constraints import Constraints, check
from cfd_perf.data.machine import Machine
from cfd_perf.data.mesh import mesh_from_data


def codes(violations):
    return {v.code for v in violations}


@pytest.fixture
def big_mesh(pilot):
    return mesh_from_data(num_cells=20_000_000, pilot=pilot)


class TestChecks:
    def test_feasible_configuration_has_no_violations(self, big_mesh, machine):
        v = check(
            192, mesh=big_mesh, machine=machine,
            constraints=Constraints(), runtime_hours=5.0, core_hours=960,
        )
        assert v == []

    def test_cells_per_core_floor(self, big_mesh, machine):
        v = check(
            4000, mesh=big_mesh, machine=machine,
            constraints=Constraints(min_cells_per_core=10_000),
            runtime_hours=1.0, core_hours=100,
        )
        assert "cells_per_core" in codes(v)

    def test_walltime_uses_the_stricter_of_user_and_machine(self, big_mesh):
        machine = Machine(cores_per_node=48, max_walltime_hours=24)
        v = check(
            48, mesh=big_mesh, machine=machine,
            constraints=Constraints(max_walltime_hours=6),
            runtime_hours=10.0, core_hours=480,
        )
        assert "walltime" in codes(v)

    def test_machine_walltime_applies_without_a_user_limit(self, big_mesh):
        machine = Machine(cores_per_node=48, max_walltime_hours=8)
        v = check(
            48, mesh=big_mesh, machine=machine, constraints=Constraints(),
            runtime_hours=10.0, core_hours=480,
        )
        assert "walltime" in codes(v)

    def test_core_hour_budget(self, big_mesh, machine):
        v = check(
            192, mesh=big_mesh, machine=machine,
            constraints=Constraints(max_core_hours=100),
            runtime_hours=5.0, core_hours=960,
        )
        assert "core_hours" in codes(v)

    def test_max_nodes(self, big_mesh):
        machine = Machine(cores_per_node=48, max_nodes=2)
        v = check(
            480, mesh=big_mesh, machine=machine, constraints=Constraints(),
            runtime_hours=1.0, core_hours=480,
        )
        assert "max_nodes" in codes(v)

    def test_node_ram_limit(self, big_mesh):
        """148 GB spread over one 8 GB node cannot fit."""
        machine = Machine(cores_per_node=48, ram_per_node_gb=8)
        v = check(
            48, mesh=big_mesh, machine=machine, constraints=Constraints(),
            runtime_hours=1.0, core_hours=48,
        )
        assert "node_ram" in codes(v)

    def test_node_ram_skipped_when_memory_unknown(self):
        mesh = mesh_from_data(num_cells=20_000_000)
        machine = Machine(cores_per_node=48, ram_per_node_gb=8)
        v = check(
            48, mesh=mesh, machine=machine, constraints=Constraints(),
            runtime_hours=1.0, core_hours=48,
        )
        assert "node_ram" not in codes(v)

    def test_ram_per_core_floor(self, big_mesh, machine):
        v = check(
            1536, mesh=big_mesh, machine=machine,
            constraints=Constraints(min_cells_per_core=1, min_ram_per_core_gb=1.0),
            runtime_hours=1.0, core_hours=1536,
        )
        assert "ram_per_core" in codes(v)

    def test_violations_carry_readable_detail(self, big_mesh, machine):
        v = check(
            4000, mesh=big_mesh, machine=machine,
            constraints=Constraints(min_cells_per_core=10_000),
            runtime_hours=1.0, core_hours=100,
        )
        assert any("cells/core" in x.detail for x in v)


class TestValidation:
    def test_rejects_non_positive_limits(self):
        with pytest.raises(ValueError, match="min_cells_per_core must be positive"):
            Constraints(min_cells_per_core=0)
        with pytest.raises(ValueError, match="max_core_hours must be positive"):
            Constraints(max_core_hours=-5)
