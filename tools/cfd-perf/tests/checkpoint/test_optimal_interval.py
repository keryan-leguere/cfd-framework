"""Tests for check-point optimal interval."""

import math

import pytest

from cfd_perf.checkpoint.optimal_interval import (
    expected_utilization,
    mtbf_to_failure_rate,
    mtbf_years_to_failure_rate,
    optimal_interval,
    survival_probability,
)


class TestSurvivalProbability:
    def test_zero_time_is_one(self) -> None:
        assert survival_probability(0.0, 100, 1e-5) == 1.0

    def test_decreases_with_time(self) -> None:
        p1 = survival_probability(1.0, 10, 0.01)
        p2 = survival_probability(2.0, 10, 0.01)
        assert 0 < p2 < p1 < 1

    def test_decreases_with_nodes(self) -> None:
        p1 = survival_probability(1.0, 100, 1e-4)
        p2 = survival_probability(1.0, 200, 1e-4)
        assert 0 < p2 < p1 < 1


class TestExpectedUtilization:
    def test_zero_tc_raises(self) -> None:
        with pytest.raises(ValueError, match="tc must be positive"):
            expected_utilization(0.0, 1.0, 100, 1e-5)

    def test_at_opt_is_max(self) -> None:
        Tc = 5.0 / 60.0  # 5 min
        n_nodes = 786
        lam = mtbf_years_to_failure_rate(15.0)
        tc_opt = optimal_interval(Tc, n_nodes, lam)
        w_opt = expected_utilization(tc_opt, Tc, n_nodes, lam)
        # Slightly before and after should be lower
        w_before = expected_utilization(tc_opt * 0.7, Tc, n_nodes, lam)
        w_after = expected_utilization(tc_opt * 1.3, Tc, n_nodes, lam)
        assert w_before < w_opt
        assert w_after < w_opt


class TestOptimalInterval:
    def test_doc_example(self) -> None:
        # N=786, Tc=5 min, λ ~ 15 years → optimal ~ 4 h
        Tc_h = 5.0 / 60.0
        n_nodes = 786
        lam = mtbf_years_to_failure_rate(15.0)
        tc_opt = optimal_interval(Tc_h, n_nodes, lam)
        assert 3.0 <= tc_opt <= 5.5  # around 4 hours

    def test_larger_Tc_increases_interval(self) -> None:
        lam = 1e-5
        n = 100
        tc1 = optimal_interval(1.0 / 60.0, n, lam)
        tc2 = optimal_interval(10.0 / 60.0, n, lam)
        assert tc2 > tc1

    def test_more_nodes_decreases_interval(self) -> None:
        Tc_h = 5.0 / 60.0
        lam = mtbf_years_to_failure_rate(15.0)
        tc_100 = optimal_interval(Tc_h, 100, lam)
        tc_1000 = optimal_interval(Tc_h, 1000, lam)
        assert tc_1000 < tc_100

    def test_zero_Tc_returns_inf(self) -> None:
        result = optimal_interval(0.0, 100, 1e-5)
        assert math.isinf(result) and result > 0


class TestMtbfConversion:
    def test_mtbf_to_rate(self) -> None:
        mtbf_h = 1000.0
        lam = mtbf_to_failure_rate(mtbf_h)
        assert lam == pytest.approx(0.001)

    def test_mtbf_years(self) -> None:
        lam = mtbf_years_to_failure_rate(15.0)
        # 15 years = 15 * 365.25 * 24 hours
        expected = 1.0 / (15 * 365.25 * 24)
        assert lam == pytest.approx(expected)

    def test_invalid_mtbf_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            mtbf_to_failure_rate(0.0)
        with pytest.raises(ValueError, match="positive"):
            mtbf_years_to_failure_rate(0.0)
