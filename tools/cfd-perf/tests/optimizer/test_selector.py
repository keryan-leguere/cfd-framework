"""Tests for the optimization selector."""

import pytest

from cfd_perf.benchmark.models import PilotPoint, PilotSeries
from cfd_perf.constraints.config import HardConstraints
from cfd_perf.mesh.models import MeshStats
from cfd_perf.models.parameters import ModelParameters
from cfd_perf.optimizer.selector import optimize

GB = 1 << 30


def _make_mesh(num_cells: int = 10_000_000, total_ram_gb: float = 256.0) -> MeshStats:
    mem_per_cell = total_ram_gb * GB / num_cells
    return MeshStats(
        num_cells=num_cells,
        num_faces=num_cells * 3,
        estimated_mem_per_cell_bytes=mem_per_cell,
    )


def _make_pilot(nc0: int = 64, t0: float = 1.0, n_iter: int = 5000) -> PilotSeries:
    return PilotSeries(
        points=(PilotPoint(cores=nc0, time_per_iter_s=t0, peak_ram_total_gb=32.0),),
        n_iterations=n_iter,
    )


class TestEfficiencyMode:
    def test_picks_largest_feasible(self) -> None:
        mesh = _make_mesh()
        pilot = _make_pilot()
        params = ModelParameters(beta=0.25, beta_source="fixed")
        result = optimize(
            mesh, pilot, params,
            mode="efficiency",
            max_efficiency_loss=0.30,
            cores_max=512,
            stride=64,
        )
        assert result.optimal is not None
        assert result.optimal.efficiency_loss <= 0.30
        for c in result.accepted:
            assert c.efficiency_loss <= 0.30
        if len(result.accepted) > 1:
            assert result.optimal.cores == max(c.cores for c in result.accepted)

    def test_no_feasible_returns_none(self) -> None:
        """Impossible combination: tight efficiency + small mesh => nothing passes."""
        mesh = _make_mesh(num_cells=100_000, total_ram_gb=256.0)
        pilot = _make_pilot()
        params = ModelParameters(beta=0.25, beta_source="fixed")
        result = optimize(
            mesh, pilot, params,
            mode="efficiency",
            max_efficiency_loss=0.01,
            cores_max=4096,
            stride=64,
            constraints=HardConstraints(min_cells_per_core=100_000, min_ram_per_core_gb=2.0),
        )
        # 100k cells / 64 cores = 1562 cells/core < 100k limit => all rejected
        assert result.optimal is None
        assert len(result.rejected) > 0


class TestDeadlineMode:
    def test_picks_smallest_feasible(self) -> None:
        mesh = _make_mesh(num_cells=100_000_000, total_ram_gb=512.0)
        pilot = _make_pilot(nc0=64, t0=1.0, n_iter=5000)
        params = ModelParameters(beta=0.25, beta_source="fixed")
        result = optimize(
            mesh, pilot, params,
            mode="deadline",
            deadline_hours=1.0,
            cores_max=1024,
            stride=64,
            constraints=HardConstraints(min_cells_per_core=100_000, min_ram_per_core_gb=0.5),
        )
        assert result.optimal is not None
        assert result.optimal.runtime_hours <= 1.0
        if len(result.accepted) > 1:
            assert result.optimal.cores == min(c.cores for c in result.accepted)

    def test_impossible_deadline(self) -> None:
        mesh = _make_mesh()
        pilot = _make_pilot(t0=10.0, n_iter=100_000)
        params = ModelParameters(beta=0.25, beta_source="fixed")
        result = optimize(
            mesh, pilot, params,
            mode="deadline",
            deadline_hours=0.001,
            cores_max=512,
            stride=64,
        )
        assert result.optimal is None
        assert len(result.rejected) > 0


class TestMinRuntimeMode:
    def test_picks_lowest_runtime_with_beta(self) -> None:
        """With the beta model, min_runtime == max cores (monotonically decreasing)."""
        mesh = _make_mesh()
        pilot = _make_pilot()
        params = ModelParameters(beta=0.25, beta_source="fixed")
        result = optimize(
            mesh, pilot, params,
            mode="min_runtime",
            cores_max=512,
            stride=64,
        )
        assert result.optimal is not None
        for c in result.accepted:
            assert c.runtime_hours >= result.optimal.runtime_hours - 1e-9

    def test_picks_minimum_with_empirical_uptick(self) -> None:
        """With U-shaped empirical data, min_runtime should be interior, not max cores."""
        from cfd_perf.models.strong_scaling import fit_scaling_model

        pilot = PilotSeries(
            points=(
                PilotPoint(cores=48,   time_per_iter_s=3.85, peak_ram_total_gb=142.0),
                PilotPoint(cores=96,   time_per_iter_s=2.18, peak_ram_total_gb=142.0),
                PilotPoint(cores=192,  time_per_iter_s=1.41, peak_ram_total_gb=143.0),
                PilotPoint(cores=384,  time_per_iter_s=1.12, peak_ram_total_gb=144.0),
                PilotPoint(cores=576,  time_per_iter_s=1.05, peak_ram_total_gb=145.0),
                PilotPoint(cores=768,  time_per_iter_s=1.10, peak_ram_total_gb=146.0),
                PilotPoint(cores=1024, time_per_iter_s=1.28, peak_ram_total_gb=148.0),
            ),
            n_iterations=12_000,
        )
        mesh = _make_mesh(num_cells=20_000_000, total_ram_gb=148.0)
        params = fit_scaling_model(pilot, model_hint="empirical")
        result = optimize(
            mesh, pilot, params,
            mode="min_runtime",
            cores_max=1024,
            stride=48,
            constraints=HardConstraints(min_cells_per_core=15_000, min_ram_per_core_gb=0.1),
        )
        assert result.optimal is not None
        assert result.optimal.cores < 1024
        for c in result.accepted:
            assert c.runtime_hours >= result.optimal.runtime_hours - 1e-9

    def test_min_runtime_candidate_always_populated(self) -> None:
        mesh = _make_mesh()
        pilot = _make_pilot()
        params = ModelParameters(beta=0.25, beta_source="fixed")
        result = optimize(
            mesh, pilot, params,
            mode="efficiency",
            max_efficiency_loss=0.30,
            cores_max=512,
            stride=64,
        )
        assert result.min_runtime_candidate is not None
        for c in result.accepted:
            assert c.runtime_hours >= result.min_runtime_candidate.runtime_hours - 1e-9

    def test_min_runtime_candidate_none_when_no_accepted(self) -> None:
        mesh = _make_mesh(num_cells=100_000, total_ram_gb=256.0)
        pilot = _make_pilot()
        params = ModelParameters(beta=0.25, beta_source="fixed")
        result = optimize(
            mesh, pilot, params,
            mode="efficiency",
            max_efficiency_loss=0.01,
            cores_max=4096,
            stride=64,
            constraints=HardConstraints(min_cells_per_core=100_000, min_ram_per_core_gb=2.0),
        )
        assert result.min_runtime_candidate is None


class TestMetadata:
    def test_model_kind_in_metadata(self) -> None:
        from cfd_perf.models.strong_scaling import fit_scaling_model

        pilot = PilotSeries(
            points=(
                PilotPoint(cores=48,  time_per_iter_s=3.85, peak_ram_total_gb=142.0),
                PilotPoint(cores=96,  time_per_iter_s=2.18, peak_ram_total_gb=142.0),
                PilotPoint(cores=192, time_per_iter_s=1.41, peak_ram_total_gb=143.0),
            ),
            n_iterations=5000,
        )
        mesh = _make_mesh(num_cells=20_000_000, total_ram_gb=142.0)
        params = fit_scaling_model(pilot, model_hint="auto")
        result = optimize(
            mesh, pilot, params,
            mode="min_runtime",
            cores_max=512,
            stride=48,
        )
        assert result.metadata["model_kind"] == "empirical"


class TestRejectedReasons:
    def test_reasons_populated(self) -> None:
        mesh = _make_mesh(num_cells=500_000)
        pilot = _make_pilot()
        params = ModelParameters(beta=0.25, beta_source="fixed")
        result = optimize(
            mesh, pilot, params,
            mode="efficiency",
            max_efficiency_loss=0.50,
            cores_max=256,
            stride=1,
            constraints=HardConstraints(min_cells_per_core=100_000),
        )
        rejected_cores = {r.cores for r in result.rejected}
        for r in result.rejected:
            assert len(r.reasons) > 0
        high_core_rejected = [r for r in result.rejected if r.cores > 5]
        if high_core_rejected:
            assert any("cells_per_core" in r.reasons for r in high_core_rejected)
