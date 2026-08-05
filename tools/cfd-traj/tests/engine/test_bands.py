"""Cutting the Mach axis into bands."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_traj.data.study import BandSpec
from cfd_traj.engine.bands import Band, build_bands


class TestDeclaredEdges:
    def test_declared_edges_give_one_band_per_interval(self):
        spec = BandSpec(edges=(0.5, 0.8, 1.2, 2.0))

        band_set = build_bands(np.linspace(0.5, 2.0, 100), spec)

        assert len(band_set) == 3
        assert band_set.edges == (0.5, 0.8, 1.2, 2.0)
        assert not band_set.auto

    def test_points_outside_the_declared_edges_are_reported(self):
        spec = BandSpec(edges=(1.0, 2.0))

        band_set = build_bands(np.linspace(0.2, 3.0, 100), spec)

        assert any("hors des bornes" in n for n in band_set.notes)


class TestPartition:
    def test_every_point_lands_in_exactly_one_band(self):
        rng = np.random.default_rng(1)
        mach = rng.uniform(0.5, 3.0, 5_000)
        band_set = build_bands(mach, BandSpec(edges=(0.5, 0.9, 1.3, 2.1, 3.0)))

        counts = np.zeros(mach.size, dtype=int)
        for band in band_set.bands:
            counts += band.contains(mach).astype(int)

        assert np.all(counts == 1)

    def test_the_last_band_is_closed_on_the_right(self):
        band_set = build_bands(np.array([0.5, 2.0]), BandSpec(edges=(0.5, 1.0, 2.0)))

        assert int(band_set.index_of(np.asarray(2.0))) == 1

    def test_points_beyond_the_partition_report_minus_one(self):
        band_set = build_bands(np.linspace(1.0, 2.0, 10), BandSpec(edges=(1.0, 2.0)))

        assert int(band_set.index_of(np.asarray(0.5))) == -1
        assert int(band_set.index_of(np.asarray(2.5))) == -1

    def test_the_band_counts_add_up_to_the_lot(self):
        rng = np.random.default_rng(2)
        mach = rng.uniform(0.5, 3.0, 2_000)

        band_set = build_bands(mach, BandSpec(edges=(0.5, 1.0, 1.8, 3.0)))

        assert sum(b.n_points for b in band_set.bands) == mach.size

    def test_band_lookup_returns_the_band_object(self):
        band_set = build_bands(np.linspace(0.5, 2.0, 50), BandSpec(edges=(0.5, 1.0, 2.0)))

        assert band_set.band_of(0.7).index == 0
        assert band_set.band_of(5.0) is None


class TestAutomaticEdges:
    def test_the_partition_spans_the_observed_range(self):
        rng = np.random.default_rng(3)
        mach = rng.uniform(0.4, 3.2, 5_000)

        band_set = build_bands(mach, BandSpec(n_bands=8, min_points=10))

        assert band_set.auto
        assert band_set.edges[0] <= float(mach.min())
        assert band_set.edges[-1] >= float(mach.max())

    def test_the_edges_are_strictly_increasing(self):
        rng = np.random.default_rng(4)

        band_set = build_bands(rng.uniform(0.3, 3.0, 4_000), BandSpec(n_bands=8, min_points=10))

        assert list(band_set.edges) == sorted(band_set.edges)
        assert len(set(band_set.edges)) == len(band_set.edges)

    def test_the_transonic_window_gets_narrower_bands(self):
        rng = np.random.default_rng(5)
        mach = rng.uniform(0.4, 3.2, 20_000)

        band_set = build_bands(
            mach, BandSpec(n_bands=6, transonic=(0.9, 1.2), transonic_refinement=3, min_points=5)
        )

        widths = {b.index: b.mach_high - b.mach_low for b in band_set.bands}
        transonic = [w for i, w in widths.items() if 0.9 <= band_set.bands[i].mid <= 1.2]
        elsewhere = [w for i, w in widths.items() if not 0.9 <= band_set.bands[i].mid <= 1.2]
        assert min(elsewhere) > min(transonic)

    def test_the_partition_is_reproducible(self):
        rng = np.random.default_rng(6)
        mach = rng.uniform(0.4, 3.0, 3_000)

        first = build_bands(mach, BandSpec(n_bands=7, min_points=20))
        second = build_bands(mach, BandSpec(n_bands=7, min_points=20))

        assert first.edges == second.edges


class TestThinBands:
    def test_a_band_with_two_points_is_merged_and_reported(self):
        # A dense clump plus a pair of stragglers far away.
        mach = np.concatenate([np.full(500, 2.0) + np.linspace(0, 0.4, 500), [0.30, 0.31]])

        band_set = build_bands(mach, BandSpec(n_bands=8, min_points=30))

        assert any("fusionnée" in n for n in band_set.notes)
        assert all(b.n_points >= 2 for b in band_set.bands)

    def test_a_lot_too_small_for_any_band_collapses_to_one(self):
        mach = np.linspace(0.5, 2.0, 12)

        band_set = build_bands(mach, BandSpec(n_bands=8, min_points=100))

        assert len(band_set) == 1
        assert band_set.bands[0].n_points == 12

    def test_a_single_mach_value_still_gives_a_usable_band(self):
        band_set = build_bands(np.array([1.5]), BandSpec(n_bands=4, min_points=1))

        assert len(band_set) >= 1
        assert band_set.bands[0].mach_high > band_set.bands[0].mach_low

    def test_a_lot_where_every_mach_is_equal_does_not_divide_by_zero(self):
        band_set = build_bands(np.full(50, 1.2), BandSpec(n_bands=5, min_points=5))

        assert len(band_set) >= 1
        assert all(b.mach_high > b.mach_low for b in band_set.bands)


class TestBandObject:
    def test_the_label_uses_a_french_decimal_comma(self):
        assert Band(index=0, mach_low=0.8, mach_high=0.95).label == "M 0,80–0,95"

    def test_the_midpoint_is_the_average_of_the_bounds(self):
        assert Band(index=0, mach_low=1.0, mach_high=2.0).mid == 1.5

    def test_inverted_bounds_cannot_be_constructed(self):
        with pytest.raises(ValueError, match="inversées"):
            Band(index=0, mach_low=2.0, mach_high=1.0)


class TestFailures:
    def test_a_lot_with_no_usable_mach_is_refused(self):
        with pytest.raises(ValueError, match="Mach"):
            build_bands(np.full(10, np.nan), BandSpec())
