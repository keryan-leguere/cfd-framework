"""Tests for batch curve plotting helpers."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from plotting import (
    batch_plot,
    build_output_path,
    discover_flight_point_values,
    format_axis_label,
    format_axis_title_label,
    format_flight_point_title_suffix,
    format_plot_title,
    iter_fixed_sweep_combinations,
    iter_flight_points,
    varying_flight_keys,
)


def _make_row(
    mach: float,
    altitude: float,
    alpha: float,
    cn: float,
    scheme: str,
    *,
    beta: float = 0.0,
) -> dict:
    return {
        "Mach": mach,
        "Altitude_m": altitude,
        "alpha": alpha,
        "beta": beta,
        "DL": 0.0,
        "DM": 0.0,
        "DN": 0.0,
        "CN": cn,
        "scheme": scheme,
    }


@pytest.fixture()
def sample_configuration_dict() -> dict:
    rows_a = [
        _make_row(0.80, 8000, alpha, 0.1 + 0.01 * alpha, "KW")
        for alpha in [0.0, 2.0, 4.0]
    ]
    rows_b = [
        _make_row(0.80, 8000, alpha, 0.12 + 0.01 * alpha, "SA")
        for alpha in [0.0, 2.0, 4.0]
    ]
    rows_c = [
        _make_row(0.85, 10000, alpha, 0.11 + 0.01 * alpha, "KW")
        for alpha in [1.0, 3.0]
    ]
    return {
        "KW": {
            "name": "KW",
            "label": "KW",
            "dir": "",
            "CDG": [0, 0, 0],
            "df": pd.DataFrame(rows_a + rows_c),
        },
        "SA": {
            "name": "SA",
            "label": "SA",
            "dir": "",
            "CDG": [0, 0, 0],
            "df": pd.DataFrame(rows_b),
        },
    }


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


class TestDiscoverFlightPointValues:
    def test_returns_sorted_unique_values(self, sample_configuration_dict):
        keys = ["Mach", "Altitude_m", "beta", "DL", "DM", "DN"]
        discovered = discover_flight_point_values(sample_configuration_dict, keys)

        assert discovered["Mach"] == [0.80, 0.85]
        assert discovered["Altitude_m"] == [8000, 10000]
        assert discovered["beta"] == [0.0]
        assert discovered["DL"] == [0.0]


class TestVaryingFlightKeys:
    def test_skips_single_value_columns(self, sample_configuration_dict):
        keys = ["Mach", "Altitude_m", "beta", "DL", "DM", "DN"]
        varying = varying_flight_keys(sample_configuration_dict, keys)

        assert varying == ["Mach", "Altitude_m"]


class TestBuildOutputPath:
    def test_uses_polar_prefix_and_save_names(self):
        flight_point = {
            "Mach": 0.80,
            "Altitude_m": 10000,
            "DL": 0.0,
            "DM": 0.0,
            "DN": 0.0,
        }
        specs = {
            "Mach": {"save_name": "M"},
            "Altitude_m": {"save_name": "Z"},
        }
        path = build_output_path(
            "/tmp/out",
            flight_point,
            ["Mach", "Altitude_m"],
            {"beta": 2.0},
            ["beta"],
            "ALPHA_POLAR",
            "alpha",
            "CN",
            specs,
            {"beta": {"save_name": "BETA"}},
        )

        assert path == Path("/tmp/out/ALPHA_POLAR/M_0.8/Z_10000/BETA_2/CN_vs_alpha")

    def test_falls_back_to_uppercase_key_without_save_name(self):
        flight_point = {"Mach": 0.80, "Altitude_m": 10000}
        path = build_output_path(
            "/tmp/out",
            flight_point,
            ["Mach", "Altitude_m"],
            {},
            [],
            "ALPHA_POLAR",
            "alpha",
            "CN",
        )

        assert path == Path("/tmp/out/ALPHA_POLAR/MACH_0.8/ALTITUDE_M_10000/CN_vs_alpha")


class TestIterFixedSweepCombinations:
    def test_yields_other_sweep_values(self, sample_configuration_dict):
        combos = list(
            iter_fixed_sweep_combinations(
                sample_configuration_dict,
                ["alpha", "beta"],
                "alpha",
            )
        )
        assert combos == [{"beta": 0.0}]

    def test_yields_cross_sweep_combinations(self):
        rows = [
            _make_row(0.80, 8000, alpha, 0.1 + 0.01 * alpha, "KW", beta=beta)
            for alpha in [0.0, 2.0, 4.0]
            for beta in [0.0, 2.0]
        ]
        config = {
            "KW": {
                "name": "KW",
                "label": "KW",
                "dir": "",
                "CDG": [0, 0, 0],
                "df": pd.DataFrame(rows),
            }
        }
        combos = list(iter_fixed_sweep_combinations(config, ["alpha", "beta"], "alpha"))
        assert len(combos) == 2
        assert {"beta": 0.0} in combos
        assert {"beta": 2.0} in combos


class TestFormatAxisLabel:
    def test_builds_label_from_literal_symbol_unit(self):
        spec = {
            "literal_name": "Normal force coefficient",
            "symbol": r"$C_N$",
            "unit": "-",
        }
        assert format_axis_label(spec, "CN") == "Normal force coefficient, $C_N$ (-)"

    def test_skips_empty_literal_name(self):
        spec = {
            "literal_name": "",
            "symbol": r"$C_N$",
            "unit": "-",
        }
        assert format_axis_label(spec, "CN") == "$C_N$ (-)"

    def test_falls_back_to_default_name(self):
        assert format_axis_label({}, "CN") == "CN"

    def test_supports_legacy_xlabel(self):
        assert format_axis_label({"xlabel": r"$\alpha$ (deg)"}, "alpha") == r"$\alpha$ (deg)"


class TestFormatAxisTitleLabel:
    def test_uses_symbol_and_unit_only(self):
        spec = {
            "literal_name": "Normal force coefficient",
            "symbol": r"$C_N$",
            "unit": "-",
        }
        assert format_axis_title_label(spec, "CN") == "$C_N$ (-)"


class TestFormatFlightPointTitleSuffix:
    def test_groups_equal_deflections_with_labels(self):
        flight_point = {
            "Mach": 0.80,
            "Altitude_m": 8000,
            "beta": 0.0,
            "DL": 0.0,
            "DM": 0.0,
            "DN": 0.0,
        }
        keys = ["Mach", "Altitude_m", "beta", "DL", "DM", "DN"]
        specs = {
            "Mach": {"label": "M"},
            "Altitude_m": {"label": "H"},
            "beta": {"label": r"$\beta$"},
            "DL": {"label": r"$\delta_L$"},
            "DM": {"label": r"$\delta_M$"},
            "DN": {"label": r"$\delta_N$"},
        }
        suffix = format_flight_point_title_suffix(flight_point, keys, specs)

        assert suffix == r"M=0.8, H=8000, $\beta$=0, $\delta_L$=$\delta_M$=$\delta_N$=0"


class TestFormatPlotTitle:
    def test_uses_symbol_only_and_flight_point_labels(self):
        y_spec = {
            "literal_name": "",
            "symbol": r"$C_N$",
            "unit": "-",
        }
        x_spec = {
            "literal_name": "Angle of attack",
            "symbol": r"$\alpha$",
            "unit": "deg",
        }
        flight_point = {
            "Mach": 0.80,
            "Altitude_m": 8000,
            "beta": 0.0,
            "DL": 0.0,
            "DM": 0.0,
            "DN": 0.0,
        }
        specs = {
            "Mach": {"label": "M"},
            "Altitude_m": {"label": "H"},
            "beta": {"label": r"$\beta$"},
            "DL": {"label": r"$\delta_L$"},
            "DM": {"label": r"$\delta_M$"},
            "DN": {"label": r"$\delta_N$"},
        }
        title = format_plot_title(
            y_spec,
            "CN",
            x_spec,
            "alpha",
            flight_point,
            ["Mach", "Altitude_m", "beta", "DL", "DM", "DN"],
            specs,
        )

        assert (
            title
            == r"$C_N$ (-) vs. $\alpha$ (deg) "
            r"(M=0.8, H=8000, $\beta$=0, $\delta_L$=$\delta_M$=$\delta_N$=0)"
        )


class TestIterFlightPoints:
    def test_yields_unique_combinations(self, sample_configuration_dict):
        keys = ["Mach", "Altitude_m", "beta", "DL", "DM", "DN"]
        points = list(iter_flight_points(sample_configuration_dict, keys))

        assert len(points) == 2
        assert any(p["Mach"] == 0.80 and p["Altitude_m"] == 8000 for p in points)
        assert any(p["Mach"] == 0.85 and p["Altitude_m"] == 10000 for p in points)


class TestBatchPlot:
    def test_single_sweep_polar(self, sample_configuration_dict, tmp_path):
        y_axis_dict = {
            "CN": {
                "col_name": "CN",
                "literal_name": "Normal force coefficient",
                "symbol": r"$C_N$",
                "unit": "-",
                "y_save_name": "CN",
            },
        }
        sweep_dict = {
            "alpha": {
                "col_name": "alpha",
                "literal_name": "Angle of attack",
                "symbol": r"$\alpha$",
                "unit": "deg",
                "x_save_name": "alpha",
                "polar_prefix": "ALPHA_POLAR",
            },
        }
        flight_point_dict = {
            "Mach": {"values": [], "label": "M", "save_name": "M"},
            "Altitude_m": {"values": [], "label": "H", "save_name": "H"},
            "beta": {"values": [], "label": "beta", "save_name": "BETA"},
            "DL": {"values": [], "label": "DL", "save_name": "DL"},
            "DM": {"values": [], "label": "DM", "save_name": "DM"},
            "DN": {"values": [], "label": "DN", "save_name": "DN"},
        }

        written = batch_plot(
            configuration_dict=sample_configuration_dict,
            y_axis_dict=y_axis_dict,
            sweep_dict=sweep_dict,
            flight_point_dict=flight_point_dict,
            output_base=tmp_path,
            formats=("svg",),
        )

        assert len(written) == 2
        assert all("ALPHA_POLAR" in str(path) for path in written)
        assert any("M_0.8" in str(path) for path in written)
        assert any("M_0.85" in str(path) for path in written)

    def test_cross_sweep_generates_both_polars(self, tmp_path):
        rows = [
            _make_row(0.80, 8000, alpha, 0.1 + 0.01 * alpha, "KW", beta=beta)
            for alpha in [0.0, 2.0, 4.0]
            for beta in [0.0, 2.0]
        ]
        config = {
            "KW": {
                "name": "KW",
                "label": "KW",
                "dir": "",
                "CDG": [0, 0, 0],
                "df": pd.DataFrame(rows),
            }
        }
        sweep_dict = {
            "alpha": {
                "col_name": "alpha",
                "symbol": r"$\alpha$",
                "unit": "deg",
                "x_save_name": "alpha",
                "polar_prefix": "ALPHA_POLAR",
                "save_name": "ALPHA",
            },
            "beta": {
                "col_name": "beta",
                "symbol": r"$\beta$",
                "unit": "deg",
                "x_save_name": "beta",
                "polar_prefix": "BETA_POLAR",
                "save_name": "BETA",
            },
        }
        flight_point_dict = {
            "Mach": {"values": [], "label": "M", "save_name": "M"},
            "Altitude_m": {"values": [], "label": "H", "save_name": "H"},
            "DL": {"values": [], "label": "DL", "save_name": "DL"},
            "DM": {"values": [], "label": "DM", "save_name": "DM"},
            "DN": {"values": [], "label": "DN", "save_name": "DN"},
        }

        written = batch_plot(
            configuration_dict=config,
            y_axis_dict={"CN": {"col_name": "CN", "y_save_name": "CN"}},
            sweep_dict=sweep_dict,
            flight_point_dict=flight_point_dict,
            output_base=tmp_path,
            formats=("svg",),
        )

        # 1 flight point × 2 beta slices × 1 y (ALPHA) + 1 flight × 3 alpha slices × 1 y (BETA)
        assert len(written) == 5
        assert sum("ALPHA_POLAR" in str(path) for path in written) == 2
        assert sum("BETA_POLAR" in str(path) for path in written) == 3
        assert any("BETA_2" in str(path) for path in written)
        assert any("ALPHA_2" in str(path) for path in written)

    def test_include_curve_filters_sources(self, sample_configuration_dict, tmp_path):
        y_axis_dict = {"CN": {"col_name": "CN", "y_save_name": "CN"}}
        sweep_dict = {"alpha": {"col_name": "alpha", "x_save_name": "alpha", "polar_prefix": "ALPHA_POLAR"}}
        flight_point_dict = {
            "Mach": {"values": [], "label": "M", "save_name": "M"},
            "Altitude_m": {"values": [], "label": "H", "save_name": "H"},
            "beta": {"values": [], "label": "beta", "save_name": "BETA"},
            "DL": {"values": [], "label": "DL", "save_name": "DL"},
            "DM": {"values": [], "label": "DM", "save_name": "DM"},
            "DN": {"values": [], "label": "DN", "save_name": "DN"},
        }

        written = batch_plot(
            configuration_dict=sample_configuration_dict,
            y_axis_dict=y_axis_dict,
            sweep_dict=sweep_dict,
            flight_point_dict=flight_point_dict,
            output_base=tmp_path,
            formats=("svg",),
            include_curve=lambda source, *_args: source == "KW",
        )

        assert len(written) == 2
