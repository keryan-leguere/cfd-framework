"""Tests for propagating a dispersion along a sweep.

The statistical assertions are checked against values derived by hand from the
dispersion model rather than against whatever the code happens to produce, so
a change in the sampling logic fails here instead of silently redefining what
the envelope means.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest

from cfd_plot import use_style
from cfd_plot.dispersion import (
    DispersionBand,
    DispersionSpec,
    QuantityDispersion,
    band_from_dispersion,
    band_from_quantities,
    plot_dispersion_band,
)

# A quadratic CN(alpha) sweep — the shape this feature exists for.
ALPHA = np.linspace(-4.0, 16.0, 21)
CN = 0.09 * ALPHA + 0.004 * ALPHA**2

NULL = DispersionSpec(disp_type=1, moy=0.0, var=0.0)

# CN crosses zero at alpha = 0. A multiplicative dispersion is proportional to
# the nominal, so it vanishes exactly there — several assertions below have to
# leave that point out to stay meaningful.
NONZERO_CN = np.abs(CN) > 0.05


@pytest.fixture(autouse=True)
def _use_notebook_style():
    use_style("notebook")
    yield
    plt.close("all")


@pytest.fixture
def rng():
    return np.random.default_rng(12345)


@pytest.fixture
def band(rng):
    return band_from_dispersion(
        ALPHA, CN,
        bias=DispersionSpec(disp_type=5, moy=0.0, var=0.02),
        scale=DispersionSpec(disp_type=6, moy=0.0, var=0.10),
        n=20_000, rng=rng,
    )


class TestShapeAndContent:
    def test_curves_follow_the_sweep(self, band):
        for arr in (band.x, band.nominal, band.mean, band.low, band.high):
            assert arr.shape == ALPHA.shape

    def test_samples_are_one_row_per_realisation(self, band):
        assert band.samples.shape == (20_000, ALPHA.size)
        assert band.n_samples == 20_000

    def test_nominal_is_preserved_untouched(self, band):
        assert np.allclose(band.nominal, CN)

    def test_envelope_brackets_the_mean(self, band):
        assert np.all(band.low <= band.mean)
        assert np.all(band.mean <= band.high)

    def test_rejects_mismatched_lengths(self):
        with pytest.raises(ValueError, match="must match"):
            band_from_dispersion(ALPHA, CN[:-1], bias=NULL, scale=NULL, n=10)

    def test_rejects_a_2d_abscissa(self):
        with pytest.raises(ValueError, match="1-D"):
            band_from_dispersion(ALPHA.reshape(-1, 1), CN, bias=NULL, scale=NULL, n=10)


class TestDispersionModel:
    def test_a_null_dispersion_collapses_onto_the_nominal(self):
        b = band_from_dispersion(ALPHA, CN, bias=NULL, scale=NULL, n=100)
        assert np.allclose(b.mean, CN)
        assert np.allclose(b.half_width, 0.0)

    def test_a_pure_bias_shifts_every_point_equally(self):
        """An additive component is independent of the nominal's magnitude."""
        b = band_from_dispersion(
            ALPHA, CN,
            bias=DispersionSpec(disp_type=2, moy=0.05, var=0.0),  # constant
            scale=NULL, n=100,
        )
        assert np.allclose(b.mean - CN, 0.05)

    def test_a_pure_scale_grows_with_the_nominal(self, rng):
        """A multiplicative component is proportional to the nominal."""
        b = band_from_dispersion(
            ALPHA, CN, bias=NULL,
            scale=DispersionSpec(disp_type=4, moy=0.0, var=0.10),
            n=40_000, rng=rng,
        )
        sigma_scale = 0.05  # sigma = var / 2
        assert np.allclose(b.std, np.abs(CN) * sigma_scale, rtol=0.05, atol=1e-4)

    def test_an_off_centre_bias_separates_the_mean_from_the_nominal(self, rng):
        """The gap between mean and nominal is the bias the analysis reveals."""
        b = band_from_dispersion(
            ALPHA, CN,
            bias=DispersionSpec(disp_type=4, moy=0.03, var=0.01),
            scale=NULL, n=20_000, rng=rng,
        )
        assert np.allclose(b.mean - b.nominal, 0.03, atol=2e-3)


class TestCorrelation:
    def test_correlated_is_the_default(self, band):
        assert band.correlated is True

    def test_a_correlated_realisation_is_a_smooth_curve(self, rng):
        """One shared draw tilts the whole curve; it must not go ragged.

        Compared against the *nominal*'s own roughness, so the assertion is
        about the dispersion adding no point-to-point noise, not about the
        underlying sweep being smooth.
        """
        b = band_from_dispersion(
            ALPHA, CN, bias=DispersionSpec(disp_type=4, moy=0.0, var=0.10),
            scale=NULL, n=50, rng=rng, correlated=True,
        )
        realisation_roughness = np.abs(np.diff(b.samples[0], 2)).max()
        nominal_roughness = np.abs(np.diff(CN, 2)).max()
        assert realisation_roughness == pytest.approx(nominal_roughness, abs=1e-12)

    def test_an_independent_realisation_is_ragged(self, rng):
        b = band_from_dispersion(
            ALPHA, CN, bias=DispersionSpec(disp_type=4, moy=0.0, var=0.10),
            scale=NULL, n=50, rng=rng, correlated=False,
        )
        assert np.abs(np.diff(b.samples[0], 2)).max() > np.abs(np.diff(CN, 2)).max()

    def test_correlation_does_not_change_the_pointwise_spread(self, rng):
        """Both modes give the same envelope; only what is inside differs."""
        kw = dict(bias=DispersionSpec(disp_type=4, moy=0.0, var=0.10), scale=NULL, n=40_000)
        corr = band_from_dispersion(ALPHA, CN, **kw, correlated=True, rng=np.random.default_rng(1))
        indep = band_from_dispersion(ALPHA, CN, **kw, correlated=False, rng=np.random.default_rng(1))
        assert np.allclose(corr.std, indep.std, rtol=0.05)

    def test_correlated_points_move_together(self, rng):
        """The whole point: the first and last point are perfectly coupled."""
        b = band_from_dispersion(
            ALPHA, CN, bias=DispersionSpec(disp_type=4, moy=0.0, var=0.10),
            scale=NULL, n=5_000, rng=rng, correlated=True,
        )
        assert np.corrcoef(b.samples[:, 0], b.samples[:, -1])[0, 1] == pytest.approx(1.0)

    def test_independent_points_do_not(self, rng):
        b = band_from_dispersion(
            ALPHA, CN, bias=DispersionSpec(disp_type=4, moy=0.0, var=0.10),
            scale=NULL, n=5_000, rng=rng, correlated=False,
        )
        assert abs(np.corrcoef(b.samples[:, 0], b.samples[:, -1])[0, 1]) < 0.1


class TestInterval:
    def test_sigma_interval_is_mean_plus_minus_k_sigma(self, rng):
        b = band_from_dispersion(
            ALPHA, CN, bias=NULL,
            scale=DispersionSpec(disp_type=4, moy=0.0, var=0.10),
            n=20_000, interval="sigma", k=2.0, rng=rng,
        )
        assert np.allclose(b.half_width, 2.0 * b.std)
        assert np.allclose(0.5 * (b.low + b.high), b.mean)

    def test_percentile_interval_covers_the_requested_fraction(self, rng):
        b = band_from_dispersion(
            ALPHA, CN, bias=NULL,
            scale=DispersionSpec(disp_type=4, moy=0.0, var=0.10),
            n=20_000, coverage=0.90, rng=rng,
        )
        inside = (b.samples >= b.low) & (b.samples <= b.high)
        assert inside.mean() == pytest.approx(0.90, abs=0.01)

    def test_truncated_tails_make_percentiles_tighter_than_sigma(self, rng):
        """Type 6 is truncated at ±2σ, so a 95 % interval is *narrower*.

        This is the reason percentiles are the default: reporting mean ± 2σ
        on a truncated distribution overstates the envelope.
        """
        kw = dict(bias=NULL, scale=DispersionSpec(disp_type=6, moy=0.0, var=0.10), n=40_000)
        pct = band_from_dispersion(ALPHA, CN, **kw, coverage=0.95, rng=np.random.default_rng(2))
        sig = band_from_dispersion(ALPHA, CN, **kw, interval="sigma", k=2.0, rng=np.random.default_rng(2))
        # A purely multiplicative dispersion vanishes where the nominal does
        # (CN = 0 at alpha = 0); there both envelopes are zero-width and the
        # comparison is vacuous, so skip that point.
        live = NONZERO_CN
        assert np.all(pct.half_width[live] < sig.half_width[live])

    def test_wider_coverage_gives_a_wider_envelope(self, rng):
        kw = dict(bias=DispersionSpec(disp_type=4, moy=0.0, var=0.1), scale=NULL, n=20_000)
        narrow = band_from_dispersion(ALPHA, CN, **kw, coverage=0.50, rng=np.random.default_rng(3))
        wide = band_from_dispersion(ALPHA, CN, **kw, coverage=0.99, rng=np.random.default_rng(3))
        assert np.all(narrow.half_width < wide.half_width)

    def test_mixing_up_coverage_and_k_is_rejected(self):
        with pytest.raises(ValueError, match="interval='sigma'"):
            band_from_dispersion(ALPHA, CN, bias=NULL, scale=NULL, n=10, k=2.0)
        with pytest.raises(ValueError, match="interval='percentile'"):
            band_from_dispersion(
                ALPHA, CN, bias=NULL, scale=NULL, n=10, interval="sigma", coverage=0.95
            )

    def test_rejects_an_unknown_interval(self):
        with pytest.raises(ValueError, match="percentile"):
            band_from_dispersion(ALPHA, CN, bias=NULL, scale=NULL, n=10, interval="iqr")

    def test_rejects_an_out_of_range_coverage(self):
        with pytest.raises(ValueError, match="0, 1"):
            band_from_dispersion(ALPHA, CN, bias=NULL, scale=NULL, n=10, coverage=95.0)


class TestLabel:
    def test_percentile_label(self, band):
        assert band.label == "95 %"

    def test_sigma_label_drops_a_trailing_zero(self):
        b = band_from_dispersion(
            ALPHA, CN, bias=NULL, scale=NULL, n=10, interval="sigma", k=2.0
        )
        assert b.label == "±2σ"

    def test_fractional_sigma_label_is_kept(self):
        b = band_from_dispersion(
            ALPHA, CN, bias=NULL, scale=NULL, n=10, interval="sigma", k=1.5
        )
        assert b.label == "±1.5σ"


class TestReduce:
    def test_reuses_the_same_cloud(self, band):
        again = band.reduce(interval="sigma", level=1.0)
        assert again.samples is band.samples

    def test_applies_the_new_reduction(self, band):
        again = band.reduce(interval="sigma", level=1.0)
        assert np.allclose(again.half_width, band.std)
        assert again.label == "±1σ"

    def test_keeps_the_current_interval_when_only_the_level_changes(self, band):
        again = band.reduce(level=0.50)
        assert again.interval == "percentile"
        assert np.all(again.half_width < band.half_width)

    def test_switching_interval_picks_that_interval_s_default_level(self, band):
        assert band.reduce(interval="sigma").level == 2.0
        assert band.reduce(interval="sigma").reduce(interval="percentile").level == 0.95


class TestFromQuantities:
    @pytest.fixture
    def quantities(self):
        # Uncertainty that grows along the sweep — the case this entry point
        # exists for, and one a single spec pair cannot express.
        return [
            QuantityDispersion(
                name=f"CN@{a:.0f}", nominal=float(c),
                bias=NULL,
                scale=DispersionSpec(disp_type=4, moy=0.0, var=0.02 + 0.01 * i),
            )
            for i, (a, c) in enumerate(zip(ALPHA, CN, strict=True))
        ]

    def test_reads_the_nominal_from_the_quantities(self, quantities, rng):
        b = band_from_quantities(ALPHA, quantities, n=2_000, rng=rng)
        assert np.allclose(b.nominal, CN)

    def test_is_always_independent(self, quantities, rng):
        assert band_from_quantities(ALPHA, quantities, n=2_000, rng=rng).correlated is False

    def test_honours_per_point_specs(self, quantities, rng):
        """The spread must widen along the sweep, as the specs ask."""
        b = band_from_quantities(ALPHA, quantities, n=40_000, rng=rng)
        relative = b.std[NONZERO_CN] / np.abs(b.nominal[NONZERO_CN])
        assert np.all(np.diff(relative) > 0)

    def test_rejects_a_length_mismatch(self, quantities):
        with pytest.raises(ValueError, match="must match"):
            band_from_quantities(ALPHA, quantities[:-1], n=10)

    def test_accepts_the_same_interval_options(self, quantities, rng):
        b = band_from_quantities(ALPHA, quantities, n=5_000, interval="sigma", k=3.0, rng=rng)
        assert np.allclose(b.half_width, 3.0 * b.std)


class TestReproducibility:
    def test_the_same_generator_seed_gives_the_same_band(self):
        kw = dict(
            bias=DispersionSpec(disp_type=5, moy=0.0, var=0.02),
            scale=DispersionSpec(disp_type=6, moy=0.0, var=0.10),
            n=2_000,
        )
        a = band_from_dispersion(ALPHA, CN, **kw, rng=np.random.default_rng(7))
        b = band_from_dispersion(ALPHA, CN, **kw, rng=np.random.default_rng(7))
        assert np.array_equal(a.samples, b.samples)

    def test_the_legacy_global_seed_still_works(self):
        kw = dict(bias=DispersionSpec(disp_type=4, moy=0.0, var=0.1), scale=NULL, n=500)
        np.random.seed(42)
        a = band_from_dispersion(ALPHA, CN, **kw)
        np.random.seed(42)
        b = band_from_dispersion(ALPHA, CN, **kw)
        assert np.array_equal(a.samples, b.samples)


class TestPlot:
    def test_draws_a_mean_curve_a_band_and_the_nominal(self, band):
        _, ax = plt.subplots()
        art = plot_dispersion_band(ax, band, label="CN")
        assert art["line"] in ax.get_lines()
        assert art["band"] in ax.collections
        assert art["nominal"] in ax.get_lines()

    def test_the_mean_curve_carries_the_mean(self, band):
        _, ax = plt.subplots()
        art = plot_dispersion_band(ax, band)
        assert np.allclose(art["line"].get_ydata(), band.mean)

    def test_the_nominal_is_dashed_to_separate_it_from_the_mean(self, band):
        _, ax = plt.subplots()
        art = plot_dispersion_band(ax, band)
        assert art["nominal"].get_linestyle() == "--"
        assert np.allclose(art["nominal"].get_ydata(), band.nominal)

    def test_show_nominal_false_omits_it(self, band):
        _, ax = plt.subplots()
        art = plot_dispersion_band(ax, band, show_nominal=False)
        assert art["nominal"] is None
        assert len(ax.get_lines()) == 1

    def test_the_band_is_labelled_from_the_interval(self, band):
        _, ax = plt.subplots()
        art = plot_dispersion_band(ax, band, label="CN")
        assert art["band"].get_label() == "95 %"

    def test_an_empty_band_label_keeps_it_out_of_the_legend(self, band):
        _, ax = plt.subplots()
        plot_dispersion_band(ax, band, label="CN", band_label="")
        legend = ax.legend()
        assert [t.get_text() for t in legend.get_texts()] == ["CN"]

    def test_realisations_draw_that_many_extra_curves(self, band):
        _, ax = plt.subplots()
        art = plot_dispersion_band(ax, band, realisations=12)
        assert len(art["realisations"]) == 12
        assert np.allclose(art["realisations"][0].get_ydata(), band.samples[0])

    def test_realisations_are_capped_at_the_sample_count(self):
        b = band_from_dispersion(
            ALPHA, CN, bias=DispersionSpec(disp_type=4, moy=0.0, var=0.1), scale=NULL, n=5
        )
        _, ax = plt.subplots()
        assert len(plot_dispersion_band(ax, b, realisations=50)["realisations"]) == 5

    def test_no_realisations_by_default(self, band):
        _, ax = plt.subplots()
        assert plot_dispersion_band(ax, band)["realisations"] == []

    def test_rejects_a_negative_realisation_count(self, band):
        _, ax = plt.subplots()
        with pytest.raises(ValueError, match=">= 0"):
            plot_dispersion_band(ax, band, realisations=-1)

    def test_the_mean_curve_has_no_markers_by_default(self, band):
        _, ax = plt.subplots()
        art = plot_dispersion_band(ax, band)
        assert art["line"].get_marker() in ("", "None", None)

    def test_the_nominal_inherits_the_mean_curve_colour(self, band):
        _, ax = plt.subplots()
        art = plot_dispersion_band(ax, band, color="tab:purple")
        assert art["nominal"].get_color() == art["line"].get_color()

    def test_two_bands_can_share_one_axes(self, band, rng):
        other = band_from_dispersion(
            ALPHA, CN * 1.15, bias=NULL,
            scale=DispersionSpec(disp_type=4, moy=0.0, var=0.06), n=2_000, rng=rng,
        )
        _, ax = plt.subplots()
        plot_dispersion_band(ax, band, label="baseline")
        plot_dispersion_band(ax, other, label="modifiée")
        assert len(ax.collections) == 2
        assert len(ax.get_lines()) == 4  # two means + two nominals


class TestDataclass:
    def test_the_band_is_immutable(self, band):
        with pytest.raises(AttributeError):
            band.mean = np.zeros_like(band.mean)  # type: ignore[misc]

    def test_it_is_a_dispersion_band(self, band):
        assert isinstance(band, DispersionBand)
