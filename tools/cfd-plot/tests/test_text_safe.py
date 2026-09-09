"""Composed labels against a font stack that cannot draw them.

Matplotlib hands a string to its mathtext engine as soon as it holds one
``$`` — the parts outside the maths included. A cartography heading like
``"$C_N$ over $\\alpha$ × $M$"`` therefore asks the *mathtext* font for a
multiplication sign, which is how a figure that draws on one machine can fail
to draw on another with the same code and the same data.
"""

from __future__ import annotations

import warnings

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from cfd_plot import batch_carto, mathtext_safe, use_style
from cfd_plot.mpl_template import (
    MATHTEXT_ASCII_ENV,
    _mathtext_ok,
    mathtext_ascii_fallback,
)

_COMPOSED = "$C_N$ over $\\alpha$ × $M$"


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    monkeypatch.delenv(MATHTEXT_ASCII_ENV, raising=False)
    use_style("paper")
    yield
    plt.close("all")


class TestTheProbe:
    def test_a_complete_font_stack_needs_no_fallback(self):
        assert _mathtext_ok("stix", "serif") is True
        assert mathtext_ascii_fallback() is False

    def test_the_answer_is_cached_per_font_stack(self):
        _mathtext_ok.cache_clear()
        _mathtext_ok("stix", "serif")
        first = _mathtext_ok.cache_info().misses
        _mathtext_ok("stix", "serif")
        assert _mathtext_ok.cache_info().misses == first

    def test_text_is_left_alone_when_the_stack_is_whole(self):
        assert mathtext_safe(_COMPOSED) == _COMPOSED


class TestTheFallback:
    def test_a_broken_stack_downgrades_the_composed_glyphs(self, monkeypatch):
        monkeypatch.setattr("cfd_plot.mpl_template._mathtext_ok", lambda *_: False)
        monkeypatch.setattr("cfd_plot.mpl_template._MATHTEXT_WARNED", set())
        with pytest.warns(RuntimeWarning, match="ASCII"):
            assert mathtext_safe(_COMPOSED) == "$C_N$ over $\\alpha$ x $M$"

    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    def test_every_glyph_the_package_composes_has_an_ascii_form(self, monkeypatch):
        monkeypatch.setattr("cfd_plot.mpl_template._mathtext_ok", lambda *_: False)
        assert mathtext_safe("Δ$C_N$ / $C_N$") == "Delta $C_N$ / $C_N$"
        assert mathtext_safe("Model − CFD") == "Model - CFD"
        assert mathtext_safe("±3 σ") == "+/-3 σ"  # only the composed ones

    def test_the_warning_is_raised_once_per_font_stack(self, monkeypatch):
        """One line about the fonts, not one per label on every figure."""
        monkeypatch.setattr("cfd_plot.mpl_template._mathtext_ok", lambda *_: False)
        monkeypatch.setattr("cfd_plot.mpl_template._MATHTEXT_WARNED", set())
        with pytest.warns(RuntimeWarning):
            mathtext_safe(_COMPOSED)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert mathtext_safe(_COMPOSED) == "$C_N$ over $\\alpha$ x $M$"

    def test_an_empty_string_is_returned_untouched(self, monkeypatch):
        monkeypatch.setattr("cfd_plot.mpl_template._mathtext_ok", lambda *_: False)
        assert mathtext_safe("") == ""


class TestTheOverride:
    def test_the_environment_can_force_the_fallback(self, monkeypatch):
        monkeypatch.setenv(MATHTEXT_ASCII_ENV, "1")
        assert mathtext_ascii_fallback() is True
        assert mathtext_safe("a × b") == "a x b"

    def test_the_environment_can_forbid_it(self, monkeypatch):
        monkeypatch.setenv(MATHTEXT_ASCII_ENV, "0")
        monkeypatch.setattr("cfd_plot.mpl_template._mathtext_ok", lambda *_: False)
        assert mathtext_ascii_fallback() is False
        assert mathtext_safe("a × b") == "a × b"


class TestOnACartography:
    """The composed headings are the ones that break; the caller's are not."""

    def test_the_headings_come_out_ascii(self, monkeypatch, tmp_path):
        monkeypatch.setenv(MATHTEXT_ASCII_ENV, "1")
        frame = pd.DataFrame(
            [
                {
                    "Mach": mach,
                    "alpha": alpha,
                    "Altitude_m": 8000.0,
                    "CN": 0.1 * alpha + mach,
                }
                for mach in (0.6, 0.8)
                for alpha in (0.0, 2.0, 4.0)
            ]
        )
        seen: list[str] = []

        def on_before_save(fig, ax, context):
            seen.append(fig._suptitle.get_text())

        batch_carto(
            configuration_dict={"CFD": {"label": "CFD", "df": frame}},
            y_axis_dict={"CN": {"col_name": "CN", "symbol": r"$C_N$", "unit": "-"}},
            sweep_dict={
                "alpha": {"col_name": "alpha", "symbol": r"$\alpha$"},
                "Mach": {"col_name": "Mach", "symbol": r"$M$"},
            },
            flight_point_dict={"Altitude_m": {"values": [], "label": "Z"}},
            output_base=tmp_path,
            formats=("png",),
            report=False,
            on_before_save=on_before_save,
        )
        assert seen and "×" not in seen[0]
        assert seen[0].splitlines()[0] == r"$C_N$ over $\alpha$ x $M$"
