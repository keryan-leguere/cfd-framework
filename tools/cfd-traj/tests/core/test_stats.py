"""Robust bounds, principal components, correlations."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_traj.core.stats import (
    Bounds,
    correlation_matrix,
    pca,
    quantile_bounds,
    spearman,
    suggest_log_scale,
)


class TestQuantileBounds:
    def test_bounds_bracket_the_quantiles_which_bracket_the_median(self):
        rng = np.random.default_rng(1)
        for _ in range(500):
            sample = rng.normal(rng.uniform(-100, 100), rng.uniform(0.1, 50), 200)

            b = quantile_bounds(sample)

            assert b.low <= b.q_low_value <= b.median <= b.q_high_value <= b.high

    def test_a_wider_margin_gives_a_strictly_wider_interval(self):
        rng = np.random.default_rng(2)
        sample = rng.normal(0, 1, 5_000)

        narrow = quantile_bounds(sample, margin=0.05)
        wide = quantile_bounds(sample, margin=0.10)

        assert wide.low < narrow.low
        assert wide.high > narrow.high

    def test_a_looser_quantile_gives_a_wider_interval(self):
        rng = np.random.default_rng(3)
        sample = rng.normal(0, 1, 5_000)

        tight = quantile_bounds(sample, q_low=0.01, q_high=0.99, margin=0.0)
        loose = quantile_bounds(sample, q_low=0.001, q_high=0.999, margin=0.0)

        assert loose.low <= tight.low
        assert loose.high >= tight.high

    def test_full_quantiles_without_margin_reproduce_the_extremes_exactly(self):
        rng = np.random.default_rng(4)
        sample = rng.normal(0, 1, 1_000)

        b = quantile_bounds(sample, q_low=0.0, q_high=1.0, margin=0.0)

        assert b.low == pytest.approx(float(sample.min()), rel=0, abs=0)
        assert b.high == pytest.approx(float(sample.max()), rel=0, abs=0)

    def test_a_constant_sample_still_yields_a_usable_interval(self):
        b = quantile_bounds(np.full(100, 3.5))

        assert b.degenerate
        assert b.width > 0.0
        assert b.low <= 3.5 <= b.high

    def test_a_single_point_does_not_raise(self):
        b = quantile_bounds([7.0])

        assert b.n_points == 1
        assert b.degenerate
        assert b.width > 0.0

    def test_an_empty_sample_is_reported_rather_than_raised(self):
        b = quantile_bounds([])

        assert b.n_points == 0
        assert b.degenerate
        assert b.notes

    def test_a_log_margin_is_multiplicative_in_physical_space(self):
        rng = np.random.default_rng(5)
        sample = 10.0 ** rng.uniform(0.0, 3.0, 20_000)

        b = quantile_bounds(sample, log_scaled=True, margin=0.1)

        assert b.log_scaled
        assert b.high / b.q_high_value == pytest.approx(b.q_low_value / b.low, rel=1e-9)

    def test_a_log_scale_falls_back_to_linear_on_non_positive_values(self):
        b = quantile_bounds([-1.0, 0.0, 1.0, 2.0], log_scaled=True)

        assert not b.log_scaled
        assert any("linéaire" in note for note in b.notes)

    def test_a_physical_floor_clips_the_lower_bound_only(self):
        rng = np.random.default_rng(6)
        sample = rng.uniform(0.0, 1.0, 2_000)

        free = quantile_bounds(sample, margin=0.2)
        clipped = quantile_bounds(sample, margin=0.2, physical_min=0.0)

        assert free.low < 0.0
        assert clipped.low == 0.0
        assert clipped.high == free.high

    def test_nan_values_are_ignored(self):
        rng = np.random.default_rng(7)
        clean = rng.normal(0, 1, 1_000)
        dirty = np.concatenate([clean, np.full(100, np.nan)])

        assert quantile_bounds(dirty).low == pytest.approx(quantile_bounds(clean).low)
        assert quantile_bounds(dirty).n_points == 1_000

    def test_membership_uses_the_bounds(self):
        b = quantile_bounds(np.linspace(0.0, 10.0, 101), q_low=0.0, q_high=1.0, margin=0.0)

        assert b.contains([0.0, 5.0, 10.0]).all()
        assert not b.contains([-0.5, 10.5]).any()

    @pytest.mark.parametrize(("lo", "hi"), [(0.5, 0.5), (0.9, 0.1), (-0.1, 0.5), (0.1, 1.5)])
    def test_invalid_quantiles_are_refused(self, lo, hi):
        with pytest.raises(ValueError, match="quantiles"):
            quantile_bounds([1.0, 2.0], q_low=lo, q_high=hi)

    def test_a_negative_margin_is_refused(self):
        with pytest.raises(ValueError, match="margin"):
            quantile_bounds([1.0, 2.0], margin=-0.1)

    def test_inverted_bounds_cannot_be_constructed(self):
        with pytest.raises(ValueError, match="inverted"):
            Bounds(
                low=1.0,
                high=0.0,
                q_low_value=0.0,
                q_high_value=1.0,
                median=0.5,
                q_low=0.0,
                q_high=1.0,
                margin=0.0,
                n_points=2,
            )


class TestLogSuggestion:
    def test_a_wide_positive_range_suggests_a_log_scale(self):
        assert suggest_log_scale(np.logspace(0, 3, 100))

    def test_a_narrow_range_does_not(self):
        assert not suggest_log_scale(np.linspace(1.0, 5.0, 100))

    def test_values_crossing_zero_never_suggest_a_log_scale(self):
        assert not suggest_log_scale(np.linspace(-1000.0, 1000.0, 100))


class TestPca:
    def test_a_rank_two_cloud_has_intrinsic_dimension_two(self):
        rng = np.random.default_rng(11)
        u = rng.normal(0, 1, 800)
        v = rng.normal(0, 1, 800)
        matrix = np.column_stack([u, v, 2.0 * u - 3.0 * v])

        result = pca(matrix, ["u", "v", "w"])

        assert result.intrinsic_dimension == 2
        assert result.explained_variance_ratio[2] < 1e-12

    def test_the_variance_ratios_sum_to_one_and_accumulate(self):
        rng = np.random.default_rng(12)
        result = pca(rng.normal(0, 1, (500, 4)), list("abcd"))

        assert float(result.explained_variance_ratio.sum()) == pytest.approx(1.0, abs=1e-12)
        assert np.all(np.diff(result.cumulative) >= -1e-15)
        assert float(result.cumulative[-1]) == pytest.approx(1.0, abs=1e-12)

    def test_the_components_are_orthonormal(self):
        rng = np.random.default_rng(13)
        result = pca(rng.normal(0, 1, (600, 4)), list("abcd"))

        gram = result.components @ result.components.T
        assert np.allclose(gram, np.eye(gram.shape[0]), atol=1e-10)

    def test_the_scores_reconstruct_the_standardised_data(self):
        rng = np.random.default_rng(14)
        matrix = rng.normal(0, 1, (300, 3))

        result = pca(matrix, list("abc"))

        standardised = (matrix - result.mean) / result.scale
        assert np.allclose(result.scores @ result.components, standardised, atol=1e-10)

    def test_component_signs_are_reproducible_under_a_row_permutation(self):
        rng = np.random.default_rng(15)
        matrix = rng.normal(0, 1, (400, 3))
        shuffled = matrix[rng.permutation(400)]

        first = pca(matrix, list("abc"))
        second = pca(shuffled, list("abc"))

        assert np.allclose(np.abs(first.components), np.abs(second.components), atol=1e-8)
        assert np.allclose(first.components, second.components, atol=1e-8)

    def test_a_constant_column_is_dropped_and_named(self):
        rng = np.random.default_rng(16)
        matrix = np.column_stack([rng.normal(0, 1, 200), np.full(200, 4.0)])

        result = pca(matrix, ["varies", "constant"])

        assert result.dropped == ("constant",)
        assert result.names == ("varies",)
        assert any("constant" in note for note in result.notes)

    def test_a_log_mask_tames_a_column_spanning_decades(self):
        rng = np.random.default_rng(17)
        wide = 10.0 ** rng.uniform(0, 4, 500)
        matrix = np.column_stack([rng.normal(0, 1, 500), wide])

        linear = pca(matrix, ["a", "b"])
        logged = pca(matrix, ["a", "b"], log_mask=[False, True])

        assert linear.n_used == logged.n_used == 2
        assert float(logged.explained_variance_ratio[0]) < 0.99

    def test_fewer_rows_than_columns_does_not_raise(self):
        result = pca(np.arange(6.0).reshape(2, 3) + np.array([0.0, 1.0, 0.5]), list("abc"))

        assert result.intrinsic_dimension <= max(result.n_used, 1)

    def test_rows_with_nan_are_dropped(self):
        rng = np.random.default_rng(18)
        matrix = rng.normal(0, 1, (200, 2))
        dirty = np.vstack([matrix, [np.nan, 1.0]])

        assert pca(dirty, ["a", "b"]).n_rows == 200

    def test_a_mismatched_name_list_is_refused(self):
        with pytest.raises(ValueError, match="names"):
            pca(np.zeros((5, 3)), ["a", "b"])

    @pytest.mark.parametrize("threshold", [0.0, 1.5, -0.2])
    def test_an_invalid_threshold_is_refused(self, threshold):
        with pytest.raises(ValueError, match="threshold"):
            pca(np.zeros((5, 2)), ["a", "b"], threshold=threshold)


class TestCorrelation:
    def test_the_matrix_is_symmetric_with_a_unit_diagonal(self):
        rng = np.random.default_rng(21)
        matrix, names = correlation_matrix(rng.normal(0, 1, (300, 4)), list("abcd"))

        assert matrix.shape == (4, 4)
        assert names == ("a", "b", "c", "d")
        assert np.allclose(matrix, matrix.T)
        assert np.allclose(np.diag(matrix), 1.0)
        assert np.all(np.abs(matrix) <= 1.0 + 1e-12)

    def test_an_affine_transform_correlates_perfectly(self):
        rng = np.random.default_rng(22)
        x = rng.normal(0, 1, 500)
        matrix, _ = correlation_matrix(np.column_stack([x, 2.0 * x + 3.0]), ["x", "y"])

        assert matrix[0, 1] == pytest.approx(1.0, abs=1e-12)

    def test_a_constant_column_does_not_produce_nan(self):
        rng = np.random.default_rng(23)
        matrix, _ = correlation_matrix(
            np.column_stack([rng.normal(0, 1, 100), np.full(100, 2.0)]), ["a", "b"]
        )

        assert np.all(np.isfinite(matrix))
        assert matrix[0, 1] == 0.0


class TestSpearman:
    def test_a_monotone_relation_saturates(self):
        x = np.linspace(0, 10, 200)

        assert spearman(x, np.exp(x)) == pytest.approx(1.0, abs=1e-12)
        assert spearman(x, -np.exp(x)) == pytest.approx(-1.0, abs=1e-12)

    def test_nan_pairs_are_dropped(self):
        x = np.array([1.0, 2.0, 3.0, 4.0, np.nan])
        y = np.array([1.0, 2.0, 3.0, 4.0, 1.0])

        assert spearman(x, y) == pytest.approx(1.0)

    def test_too_few_points_gives_zero_rather_than_nan(self):
        assert spearman([1.0, 2.0], [2.0, 1.0]) == 0.0

    def test_mismatched_lengths_are_refused(self):
        with pytest.raises(ValueError, match="lengths"):
            spearman([1.0, 2.0], [1.0])
