"""Tests for the recommendation engine."""

from __future__ import annotations

import pytest

from cfd_perf.core.constraints import Constraints
from cfd_perf.core.model import fit_model
from cfd_perf.data.machine import Machine
from cfd_perf.engine.recommend import Strategy, recommend


@pytest.fixture
def model(pilot):
    return fit_model(pilot)


def _rec(model, mesh, pilot, machine=None, **kw):
    return recommend(model=model, mesh=mesh, pilot=pilot, machine=machine, **kw)


class TestStrategies:
    def test_efficiency_respects_the_loss_ceiling(self, model, mesh, pilot, machine):
        rec = _rec(
            model, mesh, pilot, machine,
            strategy=Strategy.EFFICIENCY, max_efficiency_loss=0.30, cores_max=1536,
        )
        assert rec.choice is not None
        assert rec.choice.efficiency_loss <= 0.30

    def test_efficiency_picks_the_largest_core_count_within_budget(
        self, model, mesh, pilot, machine
    ):
        rec = _rec(
            model, mesh, pilot, machine,
            strategy=Strategy.EFFICIENCY, max_efficiency_loss=0.30, cores_max=1536,
        )
        within = [
            c for c in rec.feasible if c.efficiency_loss <= 0.30
        ]
        assert rec.choice.cores == max(c.cores for c in within)

    def test_fastest_minimises_walltime(self, model, mesh, pilot, machine):
        rec = _rec(model, mesh, pilot, machine, strategy=Strategy.FASTEST, cores_max=1536)
        assert rec.choice is not None
        assert rec.choice.runtime_hours == min(c.runtime_hours for c in rec.feasible)

    def test_fastest_does_not_run_past_the_time_minimum(self, model, mesh, pilot, machine):
        """Beyond the U-turn more cores are slower, so never pick past it."""
        rec = _rec(model, mesh, pilot, machine, strategy=Strategy.FASTEST, cores_max=1536)
        turn = model.time_minimum_cores(1536)
        assert turn is not None
        # allow one node of rounding either side
        assert rec.choice.cores <= turn + machine.cores_per_node

    def test_deadline_picks_the_fewest_cores_that_make_it(self, model, mesh, pilot, machine):
        rec = _rec(
            model, mesh, pilot, machine,
            strategy=Strategy.DEADLINE, deadline_hours=6.0, cores_max=1536,
        )
        assert rec.choice is not None
        assert rec.choice.runtime_hours <= 6.0
        in_time = [c for c in rec.feasible if c.runtime_hours <= 6.0]
        assert rec.choice.cores == min(c.cores for c in in_time)

    def test_deadline_requires_a_deadline(self, model, mesh, pilot):
        with pytest.raises(ValueError, match="deadline_hours est requis"):
            _rec(model, mesh, pilot, strategy=Strategy.DEADLINE)

    def test_impossible_deadline_is_reported_not_silently_met(
        self, model, mesh, pilot, machine
    ):
        rec = _rec(
            model, mesh, pilot, machine,
            strategy=Strategy.DEADLINE, deadline_hours=0.01, cores_max=1536,
        )
        assert any("échéance" in n for n in rec.notes)
        assert rec.choice.runtime_hours > 0.01

    def test_efficiency_ceiling_impossible_is_reported(self, model, mesh, pilot, machine):
        rec = _rec(
            model, mesh, pilot, machine,
            strategy=Strategy.EFFICIENCY,
            max_efficiency_loss=0.001,
            cores_min=500,
            cores_max=1536,
        )
        assert any("efficacité" in n for n in rec.notes)

    def test_invalid_efficiency_loss_rejected(self, model, mesh, pilot):
        with pytest.raises(ValueError, match="must be in"):
            _rec(model, mesh, pilot, max_efficiency_loss=1.5)


class TestNodeRounding:
    def test_only_whole_nodes_are_offered(self, model, mesh, pilot, machine):
        rec = _rec(model, mesh, pilot, machine, cores_max=1536)
        extra = [
            c.cores for c in rec.candidates
            if c.cores % machine.cores_per_node != 0 and c.cores != pilot.baseline_cores
        ]
        assert not extra, f"non-whole-node candidates offered: {extra}"

    def test_node_count_is_reported(self, model, mesh, pilot, machine):
        rec = _rec(model, mesh, pilot, machine, cores_max=1536)
        assert rec.choice.nodes == rec.choice.cores // machine.cores_per_node

    def test_single_core_machine_offers_every_count(self, model, mesh, pilot):
        rec = _rec(model, mesh, pilot, Machine(), cores_min=48, cores_max=60)
        assert [c.cores for c in rec.candidates] == list(range(48, 61))


class TestConstraints:
    def test_cells_per_core_floor_rejects_high_core_counts(self, model, mesh, pilot):
        rec = _rec(
            model, mesh, pilot,
            constraints=Constraints(min_cells_per_core=100_000),
            cores_max=1024,
        )
        # 20M cells / 100k = 200 cores maximum
        assert all(c.cores <= 200 for c in rec.feasible)
        assert "cells_per_core" in rec.rejection_summary()

    def test_walltime_limit_rejects_low_core_counts(self, model, mesh, pilot, machine):
        rec = _rec(
            model, mesh, pilot, machine,
            constraints=Constraints(max_walltime_hours=6.0),
            cores_max=1536,
        )
        assert all(c.runtime_hours <= 6.0 for c in rec.feasible)
        assert "walltime" in rec.rejection_summary()

    def test_core_hour_budget_is_enforced(self, model, mesh, pilot, machine):
        rec = _rec(
            model, mesh, pilot, machine,
            constraints=Constraints(max_core_hours=1000),
            cores_max=1536,
        )
        assert all(c.core_hours <= 1000 for c in rec.feasible)

    def test_max_nodes_caps_the_search(self, model, mesh, pilot):
        machine = Machine(cores_per_node=48, max_nodes=4)
        rec = _rec(model, mesh, pilot, machine, cores_max=1536)
        assert all(c.nodes <= 4 for c in rec.feasible)

    def test_no_feasible_configuration_returns_none_not_a_crash(self, model, mesh, pilot):
        rec = _rec(
            model, mesh, pilot,
            constraints=Constraints(max_core_hours=0.001),
            cores_max=200,
        )
        assert rec.choice is None
        assert rec.feasible == ()
        assert len(rec.rejected) > 0

    def test_every_rejection_carries_a_reason(self, model, mesh, pilot, machine):
        rec = _rec(
            model, mesh, pilot, machine,
            constraints=Constraints(min_cells_per_core=100_000),
            cores_max=1536,
        )
        for cand in rec.rejected:
            assert cand.violations
            for v in cand.violations:
                assert v.code and v.detail


class TestAdvisories:
    def test_extrapolation_is_flagged(self, model, mesh, pilot, machine):
        rec = _rec(
            model, mesh, pilot, machine,
            strategy=Strategy.FASTEST, cores_min=1200, cores_max=1536,
        )
        assert rec.choice.extrapolated
        assert any("extrapolat" in n for n in rec.notes)

    def test_no_extrapolation_note_inside_pilot_range(self, model, mesh, pilot, machine):
        rec = _rec(
            model, mesh, pilot, machine,
            strategy=Strategy.EFFICIENCY, max_efficiency_loss=0.3, cores_max=1024,
        )
        assert not rec.choice.extrapolated
        assert not any("extrapolat" in n for n in rec.notes)


class TestAlternatives:
    def test_fastest_and_cheapest_are_reported(self, model, mesh, pilot, machine):
        rec = _rec(model, mesh, pilot, machine, cores_max=1536)
        assert rec.fastest is not None
        assert rec.cheapest is not None
        assert rec.fastest.runtime_hours <= rec.choice.runtime_hours
        assert rec.cheapest.core_hours <= rec.choice.core_hours

    def test_cheapest_uses_fewer_cores_than_fastest(self, model, mesh, pilot, machine):
        rec = _rec(model, mesh, pilot, machine, cores_max=1536)
        assert rec.cheapest.cores < rec.fastest.cores


class TestSearchRange:
    def test_empty_range_raises(self, model, mesh, pilot):
        with pytest.raises(ValueError, match="empty core search range"):
            _rec(model, mesh, pilot, cores_min=500, cores_max=100)

    def test_default_range_is_bounded_by_the_mesh(self, model, mesh, pilot):
        rec = _rec(model, mesh, pilot, constraints=Constraints(min_cells_per_core=100_000))
        assert max(c.cores for c in rec.candidates) <= 20_000_000 // 100_000
