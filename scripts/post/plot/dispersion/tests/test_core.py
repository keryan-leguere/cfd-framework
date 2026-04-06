"""Tests for dispersion.core — sampling statistics and edge cases."""

from __future__ import annotations

import numpy as np
import pytest

from dispersion.core import (
    DISP_TYPE_LABELS,
    DispersionSpec,
    QuantityDispersion,
    dispersion_type_label,
    sigma,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

N = 50_000  # sample size for statistical checks
SEED = 42


def rng():
    return np.random.default_rng(SEED)


# ---------------------------------------------------------------------------
# sigma helper
# ---------------------------------------------------------------------------

def test_sigma():
    assert sigma(0.10) == pytest.approx(0.05)
    assert sigma(0.0) == 0.0


# ---------------------------------------------------------------------------
# dispersion_type_label
# ---------------------------------------------------------------------------

def test_type_label_known():
    assert dispersion_type_label(1) == "Null"
    assert dispersion_type_label(2) == "Constant"
    assert dispersion_type_label(3) == "Uniform"
    assert dispersion_type_label(4) == "Gaussian"
    assert "3" in dispersion_type_label(5)
    assert "2" in dispersion_type_label(6)


def test_type_label_unknown():
    with pytest.raises(ValueError):
        dispersion_type_label(0)
    with pytest.raises(ValueError):
        dispersion_type_label(7)


# ---------------------------------------------------------------------------
# DispersionSpec validation
# ---------------------------------------------------------------------------

def test_invalid_type_raises():
    with pytest.raises(ValueError):
        DispersionSpec(disp_type=0, moy=0.0, var=1.0)
    with pytest.raises(ValueError):
        DispersionSpec(disp_type=7, moy=0.0, var=1.0)


def test_label_property():
    for t in range(1, 7):
        spec = DispersionSpec(disp_type=t, moy=0.0, var=1.0)
        assert spec.label == DISP_TYPE_LABELS[t]


def test_sigma_property():
    spec = DispersionSpec(disp_type=4, moy=0.0, var=0.10)
    assert spec.sigma == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# Type 1 — NULL
# ---------------------------------------------------------------------------

class TestNull:
    spec = DispersionSpec(disp_type=1, moy=5.0, var=3.0)

    def test_shape(self):
        out = self.spec.draw(100)
        assert out.shape == (100,)

    def test_all_zero(self):
        out = self.spec.draw(1000, rng=rng())
        np.testing.assert_array_equal(out, 0.0)

    def test_rng_also_zero(self):
        out = self.spec.draw(500, rng=np.random.default_rng(0))
        np.testing.assert_array_equal(out, 0.0)


# ---------------------------------------------------------------------------
# Type 2 — CONSTANT
# ---------------------------------------------------------------------------

class TestConstant:
    spec = DispersionSpec(disp_type=2, moy=3.14, var=99.0)

    def test_all_equal_moy(self):
        out = self.spec.draw(200, rng=rng())
        np.testing.assert_array_equal(out, 3.14)


# ---------------------------------------------------------------------------
# Type 3 — UNIFORM
# ---------------------------------------------------------------------------

class TestUniform:
    spec = DispersionSpec(disp_type=3, moy=1.0, var=2.0)

    def test_within_support(self):
        out = self.spec.draw(N, rng=rng())
        assert out.min() >= -1.0 - 1e-12
        assert out.max() <= 3.0 + 1e-12

    def test_mean_approx(self):
        out = self.spec.draw(N, rng=rng())
        assert np.mean(out) == pytest.approx(1.0, abs=0.05)

    def test_std_approx(self):
        # std of Uniform[a,b] = (b-a) / sqrt(12)
        expected_std = (2 * 2.0) / np.sqrt(12)
        out = self.spec.draw(N, rng=rng())
        assert np.std(out) == pytest.approx(expected_std, rel=0.05)

    def test_var_zero_degenerate(self):
        spec = DispersionSpec(disp_type=3, moy=5.0, var=0.0)
        out = spec.draw(100, rng=rng())
        np.testing.assert_array_equal(out, 5.0)

    def test_legacy_rng(self):
        np.random.seed(SEED)
        out1 = DispersionSpec(disp_type=3, moy=0.0, var=1.0).draw(10)
        np.random.seed(SEED)
        out2 = DispersionSpec(disp_type=3, moy=0.0, var=1.0).draw(10)
        np.testing.assert_array_equal(out1, out2)


# ---------------------------------------------------------------------------
# Type 4 — GAUSSIAN
# ---------------------------------------------------------------------------

class TestGaussian:
    spec = DispersionSpec(disp_type=4, moy=2.0, var=1.0)

    def test_mean_approx(self):
        out = self.spec.draw(N, rng=rng())
        assert np.mean(out) == pytest.approx(2.0, abs=0.05)

    def test_std_approx(self):
        out = self.spec.draw(N, rng=rng())
        assert np.std(out) == pytest.approx(sigma(1.0), rel=0.05)

    def test_var_zero_degenerate(self):
        spec = DispersionSpec(disp_type=4, moy=-1.5, var=0.0)
        out = spec.draw(50, rng=rng())
        np.testing.assert_array_equal(out, -1.5)


# ---------------------------------------------------------------------------
# Type 5 — GAUSSIAN_3S
# ---------------------------------------------------------------------------

class TestGaussian3S:
    spec = DispersionSpec(disp_type=5, moy=0.0, var=1.0)

    def test_within_support(self):
        out = self.spec.draw(N, rng=rng())
        lo = self.spec.moy - 1.5 * self.spec.var
        hi = self.spec.moy + 1.5 * self.spec.var
        assert out.min() >= lo - 1e-12
        assert out.max() <= hi + 1e-12

    def test_mean_approx(self):
        out = self.spec.draw(N, rng=rng())
        assert np.mean(out) == pytest.approx(0.0, abs=0.05)

    def test_var_zero_degenerate(self):
        spec = DispersionSpec(disp_type=5, moy=3.0, var=0.0)
        out = spec.draw(50, rng=rng())
        np.testing.assert_array_equal(out, 3.0)


# ---------------------------------------------------------------------------
# Type 6 — GAUSSIAN_2S
# ---------------------------------------------------------------------------

class TestGaussian2S:
    spec = DispersionSpec(disp_type=6, moy=0.0, var=1.0)

    def test_within_support(self):
        out = self.spec.draw(N, rng=rng())
        lo = self.spec.moy - self.spec.var
        hi = self.spec.moy + self.spec.var
        assert out.min() >= lo - 1e-12
        assert out.max() <= hi + 1e-12

    def test_mean_approx(self):
        out = self.spec.draw(N, rng=rng())
        assert np.mean(out) == pytest.approx(0.0, abs=0.05)


# ---------------------------------------------------------------------------
# QuantityDispersion
# ---------------------------------------------------------------------------

class TestQuantityDispersion:
    qty = QuantityDispersion(
        name="CL",
        nominal=1.2,
        bias=DispersionSpec(disp_type=3, moy=0.0, var=0.05),
        scale=DispersionSpec(disp_type=6, moy=0.0, var=0.10),
    )

    def test_shape(self):
        out = self.qty.sample(200, rng=rng())
        assert out.shape == (200,)

    def test_deterministic_with_seed(self):
        r = np.random.default_rng(0)
        out1 = self.qty.sample(100, rng=r)
        r = np.random.default_rng(0)
        out2 = self.qty.sample(100, rng=r)
        np.testing.assert_array_equal(out1, out2)

    def test_formula(self):
        """Manually verify the dispersed-value formula."""
        np.random.seed(SEED)
        b = DispersionSpec(disp_type=2, moy=0.1, var=0.0).draw(5)
        s = DispersionSpec(disp_type=2, moy=0.0, var=0.0).draw(5)
        expected = (1.0 + s) * 1.2 + b

        qty2 = QuantityDispersion(
            name="test",
            nominal=1.2,
            bias=DispersionSpec(disp_type=2, moy=0.1, var=0.0),
            scale=DispersionSpec(disp_type=2, moy=0.0, var=0.0),
        )
        np.random.seed(SEED)
        out = qty2.sample(5)
        np.testing.assert_allclose(out, expected)

    def test_legacy_seed(self):
        np.random.seed(99)
        out1 = self.qty.sample(50)
        np.random.seed(99)
        out2 = self.qty.sample(50)
        np.testing.assert_array_equal(out1, out2)
