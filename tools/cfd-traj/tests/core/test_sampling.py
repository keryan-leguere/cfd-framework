"""Level placement, corner enumeration, Latin hypercubes with rejection."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_traj.core.sampling import (
    MAX_CORNER_DIM,
    corner_points,
    empirical_support,
    lhs_with_rejection,
    maximin_lhs,
    place_levels,
    scale_to_bounds,
)


class TestPlaceLevels:
    def test_levels_span_the_interval_endpoints_included(self):
        assert place_levels(0.0, 10.0, 5) == (0.0, 2.5, 5.0, 7.5, 10.0)

    def test_a_single_level_sits_in_the_middle(self):
        assert place_levels(2.0, 8.0, 1) == (5.0,)

    def test_two_levels_are_exactly_the_bounds(self):
        assert place_levels(-3.0, 7.0, 2) == (-3.0, 7.0)

    def test_log_levels_have_a_constant_ratio(self):
        levels = np.array(place_levels(1.0, 1000.0, 4, log_scaled=True))

        ratios = levels[1:] / levels[:-1]
        assert np.allclose(ratios, ratios[0])

    def test_anchors_are_merged_sorted_and_deduplicated(self):
        levels = place_levels(0.0, 10.0, 3, anchors=(1.0, 5.0, 5.0))

        assert levels == (0.0, 1.0, 5.0, 10.0)
        assert list(levels) == sorted(levels)

    def test_anchors_outside_the_interval_are_dropped(self):
        assert place_levels(0.0, 1.0, 2, anchors=(-5.0, 42.0)) == (0.0, 1.0)

    def test_a_degenerate_interval_collapses_to_one_level(self):
        assert place_levels(3.0, 3.0, 4) == (3.0,)

    def test_a_non_positive_count_is_refused(self):
        with pytest.raises(ValueError, match="n must be positive"):
            place_levels(0.0, 1.0, 0)

    def test_inverted_bounds_are_refused(self):
        with pytest.raises(ValueError, match="inverted"):
            place_levels(1.0, 0.0, 3)


class TestCorners:
    def test_a_box_yields_all_its_vertices(self):
        axes = {"a": (0.0, 1.0), "b": (2.0, 3.0), "c": (-1.0, 1.0)}

        corners, notes = corner_points(axes)

        assert len(corners) == 2**3
        assert notes == ()
        assert len({tuple(sorted(c.items())) for c in corners}) == 8
        for corner in corners:
            for name, value in corner.items():
                assert value in axes[name]

    def test_no_axes_yields_one_empty_point(self):
        corners, notes = corner_points({})

        assert corners == ({},)
        assert notes == ()

    def test_a_high_dimension_box_falls_back_to_an_axial_skeleton(self):
        d = MAX_CORNER_DIM + 2
        axes = {f"x{i}": (0.0, 1.0) for i in range(d)}

        corners, notes = corner_points(axes)

        assert len(corners) == 2 + 2 * d
        assert len(notes) == 1
        assert "réduite" in notes[0]

    def test_skeleton_points_stay_inside_the_box(self):
        d = MAX_CORNER_DIM + 1
        axes = {f"x{i}": (float(i), float(i) + 2.0) for i in range(d)}

        corners, _ = corner_points(axes)

        for corner in corners:
            for name, value in corner.items():
                assert axes[name][0] <= value <= axes[name][1]


class TestMaximinLhs:
    def test_every_stratum_holds_exactly_one_point(self):
        n = 20
        design = maximin_lhs(n, 3, rng=np.random.default_rng(1))

        for j in range(3):
            strata = np.floor(design[:, j] * n).astype(int)
            assert sorted(strata) == list(range(n))

    def test_the_design_lives_in_the_unit_cube(self):
        design = maximin_lhs(30, 4, rng=np.random.default_rng(2))

        assert np.all(design >= 0.0)
        assert np.all(design <= 1.0)

    def test_the_same_seed_gives_the_same_design(self):
        a = maximin_lhs(15, 3, rng=np.random.default_rng(7))
        b = maximin_lhs(15, 3, rng=np.random.default_rng(7))

        assert np.array_equal(a, b)

    def test_different_seeds_give_different_designs(self):
        a = maximin_lhs(15, 3, rng=np.random.default_rng(7))
        b = maximin_lhs(15, 3, rng=np.random.default_rng(8))

        assert not np.array_equal(a, b)

    def test_the_swaps_never_worsen_the_minimum_distance(self):
        plain = maximin_lhs(25, 3, rng=np.random.default_rng(9), n_swaps=0)
        improved = maximin_lhs(25, 3, rng=np.random.default_rng(9), n_swaps=1_500)

        assert _min_distance(improved) >= _min_distance(plain)

    def test_zero_dimensions_gives_an_empty_design(self):
        assert maximin_lhs(5, 0, rng=np.random.default_rng(1)).shape == (5, 0)

    def test_a_non_positive_sample_count_is_refused(self):
        with pytest.raises(ValueError, match="n_samples"):
            maximin_lhs(0, 2, rng=np.random.default_rng(1))


class TestSupportAndRejection:
    def test_a_central_point_is_supported_and_a_distant_one_is_not(self):
        rng = np.random.default_rng(3)
        cloud = rng.normal(0.5, 0.05, (500, 2))
        support = empirical_support(cloud)

        assert bool(support(np.array([[0.5, 0.5]]))[0])
        assert not bool(support(np.array([[5.0, 5.0]]))[0])

    def test_an_empty_cloud_accepts_everything(self):
        support = empirical_support(np.zeros((0, 2)))

        assert support(np.array([[0.1, 0.9]])).all()

    def test_every_retained_point_passes_the_support_test(self):
        rng = np.random.default_rng(4)
        cloud = rng.uniform(0.2, 0.8, (1_000, 2))
        support = empirical_support(cloud)

        result = lhs_with_rejection(20, 2, support, rng=np.random.default_rng(5))

        assert result.n_accepted > 0
        assert support(result.design).all()

    def test_a_permissive_support_returns_the_requested_count(self):
        support = empirical_support(np.zeros((0, 3)))

        result = lhs_with_rejection(12, 3, support, rng=np.random.default_rng(6))

        assert result.n_accepted == 12

    def test_an_impossible_support_returns_nothing_without_raising(self):
        # A cloud far outside the unit cube: no candidate can ever be supported.
        support = empirical_support(np.full((50, 2), 100.0))

        result = lhs_with_rejection(10, 2, support, rng=np.random.default_rng(7), max_rounds=3)

        assert result.n_accepted == 0
        assert any("retenus" in note for note in result.notes)

    def test_a_sparse_cloud_grows_the_radius_and_says_so(self):
        rng = np.random.default_rng(8)
        cloud = rng.uniform(0.0, 1.0, (60, 5))
        support = empirical_support(cloud)

        result = lhs_with_rejection(10, 5, support, rng=np.random.default_rng(9), max_rounds=3)

        assert result.radius >= support.radius
        if result.radius > support.radius:
            assert any("rayon" in note for note in result.notes)

    def test_rejection_is_reproducible(self):
        cloud = np.random.default_rng(10).uniform(0.1, 0.9, (600, 2))
        support = empirical_support(cloud)

        first = lhs_with_rejection(15, 2, support, rng=np.random.default_rng(11))
        second = lhs_with_rejection(15, 2, support, rng=np.random.default_rng(11))

        assert np.array_equal(first.design, second.design)

    def test_zero_dimensions_short_circuits(self):
        result = lhs_with_rejection(
            5, 0, empirical_support(np.zeros((0, 0))), rng=np.random.default_rng(1)
        )

        assert result.n_accepted == 0
        assert result.rounds == 0


class TestScaling:
    def test_a_unit_design_maps_onto_physical_bounds(self):
        unit = np.array([[0.0, 0.5], [1.0, 1.0]])

        scaled = scale_to_bounds(unit, [(10.0, 20.0), (-1.0, 1.0)])

        assert np.allclose(scaled, [[10.0, 0.0], [20.0, 1.0]])

    def test_a_log_axis_maps_geometrically(self):
        unit = np.array([[0.0], [0.5], [1.0]])

        scaled = scale_to_bounds(unit, [(1.0, 100.0)], [True])

        assert np.allclose(scaled.ravel(), [1.0, 10.0, 100.0])

    def test_an_empty_design_passes_through(self):
        assert scale_to_bounds(np.zeros((0, 2)), [(0.0, 1.0), (0.0, 1.0)]).shape == (0, 2)


def _min_distance(design: np.ndarray) -> float:
    diff = design[:, None, :] - design[None, :, :]
    dist = np.sqrt((diff**2).sum(axis=-1))
    np.fill_diagonal(dist, np.inf)
    return float(dist.min())
