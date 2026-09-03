"""Tests for folded batch figures — the bonus sheets that gather siblings.

A batch run produces one figure per (polar, condition, Y). Reading it means
opening one file per directory; folding collapses a family of those onto one
sheet. These tests pin what ends up on which sheet, where it is written, and
what its titles say — the three things that make a bonus figure usable rather
than a puzzle.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from cfd_plot import FOLD_Y_STEM, FoldSpec, batch_plot
from cfd_plot.batch import (
    _enumerate_fold_jobs,
    _enumerate_jobs,
    _merge_render_order,
    _prepare_flight_point_dict,
    _prepare_sweep_dict,
    _resolve_fold_specs,
)

ALTITUDES = [0.0, 5000.0, 10000.0]
MACHS = [0.5, 0.8]
ALPHAS = [0.0, 2.0, 4.0]


def _rows(scheme: str, offset: float) -> list[dict]:
    return [
        {
            "Mach": mach,
            "Altitude_m": altitude,
            "alpha": alpha,
            "beta": 0.0,
            "DL": 0.0,
            "DM": 0.0,
            "DN": 0.0,
            "CN": offset + 0.01 * alpha + 0.1 * mach,
            "CA": offset + 0.02 * alpha - 1e-5 * altitude,
            "scheme": scheme,
        }
        for mach in MACHS
        for altitude in ALTITUDES
        for alpha in ALPHAS
    ]


@pytest.fixture()
def two_sources() -> dict:
    return {
        "KW": {"name": "KW", "label": "KW", "color": "C0", "df": pd.DataFrame(_rows("KW", 0.10))},
        "SA": {"name": "SA", "label": "SA", "color": "C1", "df": pd.DataFrame(_rows("SA", 0.12))},
    }


@pytest.fixture()
def one_source() -> dict:
    return {"KW": {"name": "KW", "label": "KW", "color": "C0", "df": pd.DataFrame(_rows("KW", 0.10))}}


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


Y_AXES = {
    "CN": {"col_name": "CN", "symbol": r"$C_N$", "unit": "-", "y_save_name": "CN"},
    "CA": {"col_name": "CA", "symbol": r"$C_A$", "unit": "-", "y_save_name": "CA"},
}
SWEEPS = {
    "alpha": {
        "col_name": "alpha",
        "symbol": r"$\alpha$",
        "unit": "deg",
        "x_save_name": "alpha",
        "polar_prefix": "ALPHA_POLAR",
        "save_name": "ALPHA",
    },
}
FLIGHT_POINTS = {
    "Mach": {"values": [], "label": "M", "save_name": "M", "unit": "-"},
    "Altitude_m": {"values": [], "label": "Z", "save_name": "Z", "unit": "m"},
    "beta": {"values": [], "label": "beta", "save_name": "BETA", "unit": "deg"},
    "DL": {"values": [], "label": "DL", "save_name": "DL", "unit": "deg"},
    "DM": {"values": [], "label": "DM", "save_name": "DM", "unit": "deg"},
    "DN": {"values": [], "label": "DN", "save_name": "DN", "unit": "deg"},
}


BETA_SWEEP = {
    "beta": {
        "col_name": "beta",
        "symbol": r"$\beta$",
        "unit": "deg",
        "x_save_name": "beta",
        "polar_prefix": "BETA_POLAR",
        "save_name": "BETA",
    },
}


@pytest.fixture()
def two_sweeps() -> dict:
    """A study where beta varies too, so both alpha and beta are real polars."""
    rows = []
    for scheme, offset in [("KW", 0.10), ("SA", 0.12)]:
        for beta in (0.0, 2.0):
            for row in _rows(scheme, offset):
                rows.append({**row, "beta": beta, "CN": row["CN"] + 0.01 * beta})
    frame = pd.DataFrame(rows)
    return {
        key: {"name": key, "label": key, "df": frame[frame["scheme"] == key]}
        for key in ("KW", "SA")
    }


def _plan_two_sweeps(configuration_dict: dict, base: Path, specs) -> list:
    """As :func:`_plan`, with alpha *and* beta as sweeps; returns the folds."""
    sweeps = _prepare_sweep_dict(configuration_dict, {**SWEEPS, **BETA_SWEEP})
    flight_points = _prepare_flight_point_dict(
        configuration_dict, FLIGHT_POINTS, list(sweeps)
    )
    jobs = _enumerate_jobs(
        configuration_dict=configuration_dict,
        y_axis_dict=Y_AXES,
        completed_sweeps=sweeps,
        completed_flight_points=flight_points,
        output_base=base,
        include_curve=None,
    )
    return _enumerate_fold_jobs(
        jobs,
        specs,
        y_axis_dict=Y_AXES,
        completed_sweeps=sweeps,
        completed_flight_points=flight_points,
        output_base=base,
    )


def _plan(configuration_dict: dict, base: Path, specs) -> tuple[list, list]:
    """Enumerate the ordinary jobs and the folds they produce, without drawing."""
    sweeps = _prepare_sweep_dict(configuration_dict, SWEEPS)
    flight_points = _prepare_flight_point_dict(configuration_dict, FLIGHT_POINTS, list(SWEEPS))
    jobs = _enumerate_jobs(
        configuration_dict=configuration_dict,
        y_axis_dict=Y_AXES,
        completed_sweeps=sweeps,
        completed_flight_points=flight_points,
        output_base=base,
        include_curve=None,
    )
    folds = _enumerate_fold_jobs(
        jobs,
        specs,
        y_axis_dict=Y_AXES,
        completed_sweeps=sweeps,
        completed_flight_points=flight_points,
        output_base=base,
    )
    return jobs, folds


class TestFoldSpecValidation:
    def test_defaults_are_a_y_subplot_fold(self) -> None:
        spec = FoldSpec()
        assert (spec.kind, spec.layout, spec.max_panels) == ("y", "subplot", 6)

    def test_unknown_kind_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="kind must be one of"):
            FoldSpec(kind="sideways")

    def test_unknown_layout_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="layout must be one of"):
            FoldSpec(kind="context", layout="stacked")

    def test_overlaying_different_quantities_is_refused(self) -> None:
        """CN and CA share no unit; one Y axis for both would be a coincidence."""
        with pytest.raises(ValueError, match="different units"):
            FoldSpec(kind="y", layout="overlay")

    def test_a_single_panel_sheet_is_refused(self) -> None:
        with pytest.raises(ValueError, match="max_panels must be >= 2"):
            FoldSpec(max_panels=1)

    def test_max_cols_is_bounded(self) -> None:
        with pytest.raises(ValueError, match="max_cols must be between 1 and 3"):
            FoldSpec(max_cols=4)

    def test_sync_axes_is_validated(self) -> None:
        with pytest.raises(ValueError, match="sync_axes"):
            FoldSpec(kind="context", sync_axes="diagonal")

    def test_overlay_color_is_validated(self) -> None:
        with pytest.raises(ValueError, match="overlay_color"):
            FoldSpec(kind="context", layout="overlay", overlay_color="rainbow")

    def test_over_accepts_any_sequence(self) -> None:
        assert FoldSpec(kind="context", over=["Altitude_m"]).over == ("Altitude_m",)

    def test_folder_defaults_keep_the_two_layouts_apart(self) -> None:
        assert FoldSpec(kind="context").resolved_folder == "FOLD"
        assert FoldSpec(kind="context", layout="overlay").resolved_folder == "FOLD_OVERLAY"
        assert FoldSpec(kind="context", folder="PLANCHE").resolved_folder == "PLANCHE"

    def test_auto_sync_is_on_only_where_the_units_match(self) -> None:
        assert FoldSpec(kind="context").resolved_sync == "both"
        assert FoldSpec(kind="y").resolved_sync is None
        assert FoldSpec(kind="context", layout="overlay").resolved_sync is None
        assert FoldSpec(kind="context", sync_axes=None).resolved_sync is None
        assert FoldSpec(kind="y", sync_axes="y").resolved_sync == "y"


class TestFoldShorthands:
    def test_none_and_false_mean_no_folding(self) -> None:
        assert _resolve_fold_specs(None) == ()
        assert _resolve_fold_specs(False) == ()

    def test_true_means_the_two_obvious_folds(self) -> None:
        specs = _resolve_fold_specs(True)
        assert [(s.kind, s.layout) for s in specs] == [("y", "subplot"), ("context", "subplot")]

    def test_strings_map_to_specs(self) -> None:
        assert _resolve_fold_specs("y")[0].kind == "y"
        assert _resolve_fold_specs("overlay")[0].layout == "overlay"
        assert _resolve_fold_specs("context-overlay")[0].layout == "overlay"

    def test_a_sequence_mixes_strings_and_specs(self) -> None:
        specs = _resolve_fold_specs(["y", FoldSpec(kind="context", max_panels=4)])
        assert len(specs) == 2
        assert specs[1].max_panels == 4

    def test_a_typo_names_the_valid_shorthands(self) -> None:
        with pytest.raises(ValueError, match="Unknown fold shorthand"):
            _resolve_fold_specs("contxet")

    def test_a_non_spec_entry_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be FoldSpec or str"):
            _resolve_fold_specs([42])  # type: ignore[list-item]


class TestYFold:
    def test_one_sheet_per_condition_holding_every_y(self, two_sources: dict, tmp_path: Path) -> None:
        jobs, folds = _plan(two_sources, tmp_path, [FoldSpec(kind="y")])

        # 2 Mach x 3 altitudes conditions, 2 Y each.
        assert len(jobs) == 12
        assert len(folds) == 6
        assert all(len(fold.panels) == 2 for fold in folds)

    def test_it_is_written_beside_the_figures_it_folds(self, two_sources: dict, tmp_path: Path) -> None:
        jobs, folds = _plan(two_sources, tmp_path, [FoldSpec(kind="y")])
        parents = {job.output_path.parent for job in jobs}

        assert {fold.output_path.parent for fold in folds} <= parents
        assert all(fold.output_path.name == f"{FOLD_Y_STEM}_vs_alpha" for fold in folds)

    def test_panels_follow_the_y_axis_dict_order(self, two_sources: dict, tmp_path: Path) -> None:
        _, folds = _plan(two_sources, tmp_path, [FoldSpec(kind="y")])
        assert [panel.y_key for panel in folds[0].panels] == ["CN", "CA"]

    def test_titles_name_the_quantities_and_the_condition(
        self, two_sources: dict, tmp_path: Path
    ) -> None:
        _, folds = _plan(two_sources, tmp_path, [FoldSpec(kind="y")])
        fold = folds[0]

        assert fold.suptitle == r"$C_N$, $C_A$ vs. $\alpha$"
        assert "M=" in fold.subtitle and "Z=" in fold.subtitle

    def test_a_lone_y_is_not_folded(self, two_sources: dict, tmp_path: Path) -> None:
        """A one-panel sheet is a copy of the figure it folds."""
        sweeps = _prepare_sweep_dict(two_sources, SWEEPS)
        flight_points = _prepare_flight_point_dict(two_sources, FLIGHT_POINTS, list(SWEEPS))
        one_y = {"CN": Y_AXES["CN"]}
        jobs = _enumerate_jobs(
            configuration_dict=two_sources,
            y_axis_dict=one_y,
            completed_sweeps=sweeps,
            completed_flight_points=flight_points,
            output_base=tmp_path,
            include_curve=None,
        )
        folds = _enumerate_fold_jobs(
            jobs,
            [FoldSpec(kind="y")],
            y_axis_dict=one_y,
            completed_sweeps=sweeps,
            completed_flight_points=flight_points,
            output_base=tmp_path,
        )
        assert folds == []

    def test_a_large_family_is_split_not_shrunk(self, two_sources: dict, tmp_path: Path) -> None:
        _, folds = _plan(two_sources, tmp_path, [FoldSpec(kind="y", max_panels=2)])
        assert all(len(fold.panels) <= 2 for fold in folds)
        assert all(fold.part == (1, 1) for fold in folds)


class TestContextFold:
    def test_one_sheet_per_y_gathering_every_altitude(
        self, two_sources: dict, tmp_path: Path
    ) -> None:
        _, folds = _plan(two_sources, tmp_path, [FoldSpec(kind="context", over=("Altitude_m",))])

        # 2 Y x 2 Mach, each gathering the 3 altitudes.
        assert len(folds) == 4
        assert all(len(fold.panels) == 3 for fold in folds)

    def test_panels_are_sorted_by_the_folded_value(
        self, two_sources: dict, tmp_path: Path
    ) -> None:
        """Data order is whatever the DataFrame happened to hold; a sheet reads
        left to right."""
        _, folds = _plan(two_sources, tmp_path, [FoldSpec(kind="context", over=("Altitude_m",))])
        altitudes = [panel.flight_point["Altitude_m"] for panel in folds[0].panels]
        assert altitudes == sorted(altitudes)

    def test_the_path_says_what_was_folded_and_what_was_not(
        self, two_sources: dict, tmp_path: Path
    ) -> None:
        _, folds = _plan(two_sources, tmp_path, [FoldSpec(kind="context", over=("Altitude_m",))])
        relative = sorted(str(fold.output_path.relative_to(tmp_path)) for fold in folds)

        assert relative == [
            "ALPHA_POLAR/FOLD/M_0.5/CA_vs_alpha_by_Z",
            "ALPHA_POLAR/FOLD/M_0.5/CN_vs_alpha_by_Z",
            "ALPHA_POLAR/FOLD/M_0.8/CA_vs_alpha_by_Z",
            "ALPHA_POLAR/FOLD/M_0.8/CN_vs_alpha_by_Z",
        ]

    def test_folding_everything_leaves_no_directory_level(
        self, two_sources: dict, tmp_path: Path
    ) -> None:
        _, folds = _plan(two_sources, tmp_path, [FoldSpec(kind="context", max_panels=6)])
        relative = sorted(str(fold.output_path.relative_to(tmp_path)) for fold in folds)

        assert relative == [
            "ALPHA_POLAR/FOLD/CA_vs_alpha_by_M_Z",
            "ALPHA_POLAR/FOLD/CN_vs_alpha_by_M_Z",
        ]
        assert all(len(fold.panels) == 6 for fold in folds)

    def test_a_family_larger_than_max_panels_becomes_numbered_sheets(
        self, two_sources: dict, tmp_path: Path
    ) -> None:
        _, folds = _plan(two_sources, tmp_path, [FoldSpec(kind="context", max_panels=4)])
        names = sorted(fold.output_path.name for fold in folds)

        assert names == [
            "CA_vs_alpha_by_M_Z_p1of2",
            "CA_vs_alpha_by_M_Z_p2of2",
            "CN_vs_alpha_by_M_Z_p1of2",
            "CN_vs_alpha_by_M_Z_p2of2",
        ]
        assert [len(fold.panels) for fold in sorted(folds, key=lambda f: f.output_path.name)] == [
            4,
            2,
            4,
            2,
        ]

    def test_the_subtitle_names_the_folded_parameter_and_the_part(
        self, two_sources: dict, tmp_path: Path
    ) -> None:
        _, folds = _plan(two_sources, tmp_path, [FoldSpec(kind="context", max_panels=4)])
        fold = min(folds, key=lambda f: f.output_path.name)

        assert fold.subtitle == "M, Z folded — part 1/2"

    def test_the_subtitle_keeps_the_conditions_that_were_not_folded(
        self, two_sources: dict, tmp_path: Path
    ) -> None:
        _, folds = _plan(two_sources, tmp_path, [FoldSpec(kind="context", over=("Altitude_m",))])
        assert any(fold.subtitle.startswith("M=0.5") for fold in folds)

    def test_panel_titles_carry_the_folded_value_with_its_unit(
        self, two_sources: dict, tmp_path: Path
    ) -> None:
        _, folds = _plan(two_sources, tmp_path, [FoldSpec(kind="context", over=("Altitude_m",))])
        assert [panel.title for panel in folds[0].panels] == ["Z=0 m", "Z=5000 m", "Z=10000 m"]

    def test_a_constant_key_produces_nothing(self, two_sources: dict, tmp_path: Path) -> None:
        """beta never varies here, so there is no family to fold."""
        _, folds = _plan(two_sources, tmp_path, [FoldSpec(kind="context", over=("beta",))])
        assert folds == []

    def test_a_polars_own_sweep_is_skipped_there(self, two_sweeps: dict, tmp_path: Path) -> None:
        """Folding over alpha gathers the pinned alphas of BETA_POLAR.

        In ALPHA_POLAR alpha is the x axis, so there is no family of alphas to
        gather — and that is a silent skip, not an error, so one spec can serve
        a study whose polars pin different variables.
        """
        folds = _plan_two_sweeps(
            two_sweeps, tmp_path, [FoldSpec(kind="context", over=("alpha",))]
        )
        assert {fold.polar_prefix for fold in folds} == {"BETA_POLAR"}
        assert all("_by_ALPHA" in fold.output_path.name for fold in folds)

    def test_an_unknown_over_key_is_reported(self, two_sources: dict, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="unknown keys"):
            _plan(two_sources, tmp_path, [FoldSpec(kind="context", over=("Reynolds",))])

    def test_the_overlay_layout_has_its_own_directory(
        self, two_sources: dict, tmp_path: Path
    ) -> None:
        """Requesting both layouts must not make them overwrite each other."""
        _, folds = _plan(
            two_sources,
            tmp_path,
            [
                FoldSpec(kind="context", over=("Altitude_m",)),
                FoldSpec(kind="context", layout="overlay", over=("Altitude_m",)),
            ],
        )
        assert len({fold.output_path for fold in folds}) == len(folds)
        assert any("FOLD_OVERLAY" in str(fold.output_path) for fold in folds)


class TestRenderOrder:
    def test_folds_follow_the_polar_they_belong_to(
        self, two_sources: dict, tmp_path: Path
    ) -> None:
        """A trailing "folds" chapter would divorce every sheet from its
        chapter in the PDF outline and the terminal report."""
        jobs, folds = _plan(two_sources, tmp_path, [FoldSpec(kind="y")])
        order = _merge_render_order(jobs, folds)

        assert len(order) == len(jobs) + len(folds)
        prefixes = [job.polar_prefix for job in order]
        assert prefixes == sorted(prefixes, key=prefixes.index)  # contiguous runs
        assert order[-1] in folds


class TestBatchPlotIntegration:
    def test_folded_sheets_land_on_disk(self, two_sources: dict, tmp_path: Path) -> None:
        written = batch_plot(
            configuration_dict=two_sources,
            y_axis_dict=Y_AXES,
            sweep_dict=SWEEPS,
            flight_point_dict=FLIGHT_POINTS,
            output_base=tmp_path,
            formats=("png",),
            report=False,
            fold=["y", FoldSpec(kind="context", over=("Altitude_m",))],
        )

        assert all(path.exists() for path in written)
        assert len(list(tmp_path.rglob(f"{FOLD_Y_STEM}_vs_alpha.png"))) == 6
        assert len(list((tmp_path / "ALPHA_POLAR" / "FOLD").rglob("*.png"))) == 4

    def test_dry_run_lists_the_folds_it_would_write(
        self, two_sources: dict, tmp_path: Path
    ) -> None:
        planned = batch_plot(
            configuration_dict=two_sources,
            y_axis_dict=Y_AXES,
            sweep_dict=SWEEPS,
            flight_point_dict=FLIGHT_POINTS,
            output_base=tmp_path,
            formats=("png",),
            report=False,
            dry_run=True,
            fold="y",
        )

        assert len(planned) == 18
        assert not list(tmp_path.rglob("*.png"))

    def test_hooks_see_the_fold_context(self, two_sources: dict, tmp_path: Path) -> None:
        seen: list[tuple] = []

        def on_before_save(fig, ax, context):
            if context.fold_kind is not None:
                seen.append((context.fold_kind, context.fold_layout, context.fold_label))

        batch_plot(
            configuration_dict=two_sources,
            y_axis_dict=Y_AXES,
            sweep_dict=SWEEPS,
            flight_point_dict=FLIGHT_POINTS,
            output_base=tmp_path,
            formats=("png",),
            report=False,
            fold=[FoldSpec(kind="context", over=("Altitude_m",))],
            on_before_save=on_before_save,
        )

        assert len(seen) == 12  # 4 sheets x 3 panels
        assert {kind for kind, _, _ in seen} == {"context"}
        assert "Z=5000 m" in {label for _, _, label in seen}

    def test_an_overlay_hook_fires_once_and_names_every_condition(
        self, one_source: dict, tmp_path: Path
    ) -> None:
        seen: list[str] = []

        def on_before_save(fig, ax, context):
            if context.fold_layout == "overlay":
                seen.append(context.fold_label)

        batch_plot(
            configuration_dict=one_source,
            y_axis_dict=Y_AXES,
            sweep_dict=SWEEPS,
            flight_point_dict=FLIGHT_POINTS,
            output_base=tmp_path,
            formats=("png",),
            report=False,
            fold=[FoldSpec(kind="context", layout="overlay", over=("Altitude_m",))],
            on_before_save=on_before_save,
        )

        assert len(seen) == 4  # one call per sheet, not one per condition
        assert seen[0] == "Z=0 m / Z=5000 m / Z=10000 m"

    def test_folds_survive_the_process_pool(self, two_sources: dict, tmp_path: Path) -> None:
        written = batch_plot(
            configuration_dict=two_sources,
            y_axis_dict=Y_AXES,
            sweep_dict=SWEEPS,
            flight_point_dict=FLIGHT_POINTS,
            output_base=tmp_path,
            formats=("png",),
            report=False,
            n_jobs=2,
            fold="y",
        )
        assert len(list(tmp_path.rglob(f"{FOLD_Y_STEM}_vs_alpha.png"))) == 6
        assert all(path.exists() for path in written)

    def test_clean_then_fold_leaves_only_the_new_run(
        self, two_sources: dict, tmp_path: Path
    ) -> None:
        stale = tmp_path / "ALPHA_POLAR" / "M_0.5" / "Z_0" / "CZ_vs_alpha.png"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"stale")

        batch_plot(
            configuration_dict=two_sources,
            y_axis_dict=Y_AXES,
            sweep_dict=SWEEPS,
            flight_point_dict=FLIGHT_POINTS,
            output_base=tmp_path,
            formats=("png",),
            report=False,
            clean=True,
            fold="y",
        )
        assert not stale.exists()
        assert (stale.parent / f"{FOLD_Y_STEM}_vs_alpha.png").exists()

    def test_clean_honours_dry_run(self, two_sources: dict, tmp_path: Path) -> None:
        stale = tmp_path / "ALPHA_POLAR" / "stale.png"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"stale")

        batch_plot(
            configuration_dict=two_sources,
            y_axis_dict=Y_AXES,
            sweep_dict=SWEEPS,
            flight_point_dict=FLIGHT_POINTS,
            output_base=tmp_path,
            formats=("png",),
            report=False,
            dry_run=True,
            clean=True,
        )
        assert stale.exists()

    def test_the_pdf_report_includes_the_folds(self, two_sources: dict, tmp_path: Path) -> None:
        pdf = tmp_path / "study.pdf"
        batch_plot(
            configuration_dict=two_sources,
            y_axis_dict=Y_AXES,
            sweep_dict=SWEEPS,
            flight_point_dict=FLIGHT_POINTS,
            output_base=tmp_path,
            formats=(),
            report=False,
            fold="y",
            pdf_report=pdf,
        )
        assert pdf.exists() and pdf.stat().st_size > 0


class TestOverlayRendering:
    def _fold_figure(self, configuration_dict: dict, tmp_path: Path, **spec_kwargs):
        from cfd_plot.batch import _render_fold_overlay

        _, folds = _plan(
            configuration_dict,
            tmp_path,
            [FoldSpec(kind="context", layout="overlay", over=("Altitude_m",), **spec_kwargs)],
        )
        return _render_fold_overlay(folds[0])

    def test_one_source_is_labelled_by_condition_alone(
        self, one_source: dict, tmp_path: Path
    ) -> None:
        fig, (ax,) = self._fold_figure(one_source, tmp_path)
        assert [line.get_label() for line in ax.lines] == ["Z=0 m", "Z=5000 m", "Z=10000 m"]

    def test_several_sources_keep_their_name_in_the_legend(
        self, two_sources: dict, tmp_path: Path
    ) -> None:
        fig, (ax,) = self._fold_figure(two_sources, tmp_path)
        labels = [line.get_label() for line in ax.lines]
        assert "KW · Z=0 m" in labels
        assert "SA · Z=10000 m" in labels

    def test_colour_by_condition_overrides_the_source_colour(
        self, two_sources: dict, tmp_path: Path
    ) -> None:
        """Default overlay_color='fold': colour reads the condition, the
        marker/linestyle reads the source."""
        fig, (ax,) = self._fold_figure(two_sources, tmp_path)
        by_condition: dict[str, set] = {}
        for line in ax.lines:
            condition = str(line.get_label()).split(" · ")[-1]
            by_condition.setdefault(condition, set()).add(line.get_color())
        assert all(len(colors) == 1 for colors in by_condition.values())
        assert len({next(iter(c)) for c in by_condition.values()}) == 3

    def test_colour_by_source_varies_the_linestyle_instead(
        self, two_sources: dict, tmp_path: Path
    ) -> None:
        fig, (ax,) = self._fold_figure(two_sources, tmp_path, overlay_color="source")
        by_source: dict[str, set] = {}
        for line in ax.lines:
            source = str(line.get_label()).split(" · ")[0]
            by_source.setdefault(source, set()).add(line.get_color())
        assert all(len(colors) == 1 for colors in by_source.values())
        assert len({line.get_linestyle() for line in ax.lines}) == 3


class TestSubplotRendering:
    def _render(self, configuration_dict: dict, tmp_path: Path, spec: FoldSpec):
        from cfd_plot.batch import _render_fold_subplot

        _, folds = _plan(configuration_dict, tmp_path, [spec])
        return _render_fold_subplot(folds[0])

    def test_y_panels_keep_independent_scales(self, two_sources: dict, tmp_path: Path) -> None:
        """CN and CA have different magnitudes; a shared scale flattens one."""
        fig, axes = self._render(two_sources, tmp_path, FoldSpec(kind="y"))
        assert axes[0].get_ylim() != axes[1].get_ylim()

    def test_context_panels_are_synchronised_by_default(
        self, two_sources: dict, tmp_path: Path
    ) -> None:
        from cfd_plot.batch import _render_one_fold_job

        _, folds = _plan(two_sources, tmp_path, [FoldSpec(kind="context", over=("Altitude_m",))])
        _render_one_fold_job(folds[0], "paper", ("png",), None)
        fig = plt.gcf()
        del fig  # the job closes its own figure; the assertion is below

        # Re-render without closing to inspect the axes.
        fig, axes = self._render(two_sources, tmp_path, FoldSpec(kind="context", over=("Altitude_m",)))
        from cfd_plot import sync_axes_limits

        sync_axes_limits(axes, which="both")
        assert len({ax.get_ylim() for ax in axes}) == 1

    def test_unused_grid_cells_are_hidden(self, two_sources: dict, tmp_path: Path) -> None:
        fig, axes = self._render(
            two_sources, tmp_path, FoldSpec(kind="context", over=("Altitude_m",), max_cols=2)
        )
        hidden = [ax for ax in fig.axes if not ax.get_visible()]
        assert len(hidden) == 1  # 3 panels in a 2x2 grid

    def test_one_legend_when_every_panel_shows_the_same_series(
        self, two_sources: dict, tmp_path: Path
    ) -> None:
        fig, axes = self._render(two_sources, tmp_path, FoldSpec(kind="y"))
        assert sum(ax.get_legend() is not None for ax in axes) == 1
