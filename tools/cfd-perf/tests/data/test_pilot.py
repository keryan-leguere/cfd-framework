"""Tests for pilot ingest and validation."""

from __future__ import annotations

import pytest

from cfd_perf.data.pilot import PilotPoint, PilotSeries, pilot_from_points


class TestPilotPoint:
    def test_rejects_non_positive_cores(self):
        with pytest.raises(ValueError, match="cores must be positive"):
            PilotPoint(cores=0, time_per_iter_s=1.0)

    def test_rejects_non_positive_time(self):
        with pytest.raises(ValueError, match="time_per_iter_s must be positive"):
            PilotPoint(cores=48, time_per_iter_s=0.0)

    def test_error_names_the_offending_core_count(self):
        with pytest.raises(ValueError, match="at 48 cores"):
            PilotPoint(cores=48, time_per_iter_s=-1.0)

    def test_ram_is_optional(self):
        p = PilotPoint(cores=48, time_per_iter_s=1.0)
        assert p.peak_ram_total_gb is None

    def test_rejects_non_positive_ram_when_given(self):
        with pytest.raises(ValueError, match="peak_ram_total_gb"):
            PilotPoint(cores=48, time_per_iter_s=1.0, peak_ram_total_gb=0.0)


class TestIngest:
    def test_sorts_by_core_count(self):
        series = pilot_from_points(
            [
                {"cores": 192, "time_per_iter_s": 1.4},
                {"cores": 48, "time_per_iter_s": 3.9},
                {"cores": 96, "time_per_iter_s": 2.2},
            ],
            n_iterations=1000,
        )
        assert [p.cores for p in series.points] == [48, 96, 192]
        assert series.baseline_cores == 48

    def test_rejects_duplicate_core_counts(self):
        with pytest.raises(ValueError, match="duplicate pilot core counts"):
            pilot_from_points(
                [
                    {"cores": 48, "time_per_iter_s": 3.9},
                    {"cores": 48, "time_per_iter_s": 4.0},
                ],
                n_iterations=1000,
            )

    def test_missing_key_names_the_point_and_the_key(self):
        with pytest.raises(ValueError, match=r"point #2 is missing.*time_per_iter_s"):
            pilot_from_points(
                [
                    {"cores": 48, "time_per_iter_s": 3.9},
                    {"cores": 96},
                ],
                n_iterations=1000,
            )

    def test_empty_input_rejected(self):
        with pytest.raises(ValueError, match="at least one point"):
            pilot_from_points([], n_iterations=1000)

    def test_rejects_non_positive_iterations(self):
        with pytest.raises(ValueError, match="n_iterations must be positive"):
            pilot_from_points([{"cores": 48, "time_per_iter_s": 1.0}], n_iterations=0)


class TestSeriesProperties:
    def test_peak_ram_uses_the_maximum_not_the_baseline(self, pilot):
        """Sizing on the baseline would under-provision: RAM creeps up."""
        assert pilot.peak_ram_total_gb == 148.0

    def test_peak_ram_is_none_when_unmeasured(self):
        series = pilot_from_points(
            [
                {"cores": 48, "time_per_iter_s": 3.9},
                {"cores": 96, "time_per_iter_s": 2.2},
            ],
            n_iterations=1000,
        )
        assert series.peak_ram_total_gb is None

    def test_core_range(self, pilot):
        assert pilot.core_range == (48, 1024)

    def test_unsorted_construction_rejected(self):
        with pytest.raises(ValueError, match="sorted by ascending core count"):
            PilotSeries(
                points=(
                    PilotPoint(cores=96, time_per_iter_s=2.2),
                    PilotPoint(cores=48, time_per_iter_s=3.9),
                ),
                n_iterations=1000,
            )


class TestWarnings:
    def test_clean_series_has_no_span_or_count_warnings(self, pilot):
        issues = " ".join(pilot.warnings())
        assert "point(s) pilote(s)" not in issues
        assert "ne couvre que" not in issues

    def test_too_few_points_warns(self):
        series = pilot_from_points(
            [
                {"cores": 48, "time_per_iter_s": 3.9},
                {"cores": 512, "time_per_iter_s": 1.1},
            ],
            n_iterations=1000,
        )
        assert any("point(s) pilote(s)" in w for w in series.warnings())

    def test_narrow_span_warns(self):
        series = pilot_from_points(
            [
                {"cores": 48, "time_per_iter_s": 3.9},
                {"cores": 64, "time_per_iter_s": 3.2},
                {"cores": 96, "time_per_iter_s": 2.4},
                {"cores": 128, "time_per_iter_s": 2.0},
            ],
            n_iterations=1000,
        )
        assert any("ne couvre que" in w for w in series.warnings())

    def test_no_improvement_at_baseline_warns(self):
        series = pilot_from_points(
            [
                {"cores": 48, "time_per_iter_s": 2.0},
                {"cores": 96, "time_per_iter_s": 2.4},
                {"cores": 192, "time_per_iter_s": 3.0},
                {"cores": 384, "time_per_iter_s": 4.0},
            ],
            n_iterations=1000,
        )
        assert any("ne s'améliore pas" in w for w in series.warnings())

    def test_missing_ram_warns(self):
        series = pilot_from_points(
            [
                {"cores": 48, "time_per_iter_s": 3.9},
                {"cores": 96, "time_per_iter_s": 2.2},
                {"cores": 192, "time_per_iter_s": 1.4},
                {"cores": 384, "time_per_iter_s": 1.1},
            ],
            n_iterations=1000,
        )
        assert any("peak_ram_total_gb" in w for w in series.warnings())
