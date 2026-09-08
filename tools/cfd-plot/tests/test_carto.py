"""Tests for cartographies (``cfd_plot.carto``)."""

from __future__ import annotations

import pickle

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from cfd_plot import CartoSpec, DeltaSpec, batch_carto
from cfd_plot.batch import (
    _extract_plot_style_kwargs,
    _prepare_flight_point_dict,
    _prepare_sweep_dict,
)
from cfd_plot.carto import (
    _CartoPlotJob,
    _delta_levels,
    _enumerate_carto_jobs,
    _resolve_delta_arg,
    _resolve_pairs,
    _shared_levels,
)


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


_MACHS = (0.6, 0.8, 1.0)
_ALPHAS = (0.0, 2.0, 4.0, 6.0)
_ALTITUDES = (5000.0, 10000.0)


def _rows(scale: float) -> list[dict]:
    return [
        {
            "Mach": mach,
            "alpha": alpha,
            "Altitude_m": altitude,
            "beta": 0.0,
            "CN": scale * (0.1 * alpha + 0.5 * mach),
            "CA": scale * (0.02 + 0.001 * alpha),
        }
        for mach in _MACHS
        for alpha in _ALPHAS
        for altitude in _ALTITUDES
    ]


@pytest.fixture()
def configuration_dict() -> dict:
    """Two sources over a full Mach x alpha x altitude grid."""
    return {
        "CFD": {"name": "CFD", "label": "CFD", "df": pd.DataFrame(_rows(1.0))},
        "MODEL": {"name": "MODEL", "label": "Model", "df": pd.DataFrame(_rows(0.9))},
    }


_Y_AXIS = {
    "CN": {"col_name": "CN", "symbol": r"$C_N$", "unit": "-", "y_save_name": "CN"},
}
_TWO_Y_AXES = {
    **_Y_AXIS,
    "CA": {"col_name": "CA", "symbol": r"$C_A$", "unit": "-", "y_save_name": "CA"},
}
_SWEEPS = {
    "alpha": {
        "col_name": "alpha",
        "symbol": r"$\alpha$",
        "unit": "deg",
        "x_save_name": "alpha",
        "save_name": "ALPHA",
    },
    "Mach": {
        "col_name": "Mach",
        "symbol": r"$M$",
        "unit": "-",
        "x_save_name": "Mach",
        "save_name": "M",
    },
}
_FLIGHT_POINTS = {
    "Altitude_m": {"values": [], "label": "Z", "save_name": "Z", "unit": "m"},
    "beta": {"values": [], "label": r"$\beta$", "save_name": "BETA", "unit": "deg"},
}


def _carto(configuration_dict, tmp_path, **kwargs):
    return batch_carto(
        configuration_dict=configuration_dict,
        y_axis_dict=kwargs.pop("y_axis_dict", _Y_AXIS),
        sweep_dict=kwargs.pop("sweep_dict", _SWEEPS),
        flight_point_dict=_FLIGHT_POINTS,
        output_base=tmp_path,
        formats=("png",),
        report=False,
        **kwargs,
    )


def _jobs(configuration_dict, tmp_path, **kwargs):
    """Enumerate without rendering — the geometry, not the pixels."""
    sweep_dict = kwargs.pop("sweep_dict", _SWEEPS)
    y_axis_dict = kwargs.pop("y_axis_dict", _Y_AXIS)
    completed_sweeps = _prepare_sweep_dict(configuration_dict, sweep_dict)
    completed_flight_points = _prepare_flight_point_dict(
        configuration_dict, _FLIGHT_POINTS, list(sweep_dict)
    )
    return _enumerate_carto_jobs(
        configuration_dict=configuration_dict,
        y_axis_dict=y_axis_dict,
        completed_sweeps=completed_sweeps,
        completed_flight_points=completed_flight_points,
        output_base=tmp_path,
        base_spec=kwargs.pop("base_spec", CartoSpec()),
        pairs=kwargs.pop("pairs", None),
        include_panel=kwargs.pop("include_panel", None),
    )


class TestCartoSpec:
    def test_defaults_are_sane(self):
        spec = CartoSpec()
        assert spec.levels == 11
        assert spec.line_levels is None
        assert spec.clabel is True
        assert spec.shared_scale is True
        # Not "equal": a map over (Mach, alpha) has two unrelated units.
        assert spec.aspect is None

    def test_too_few_levels_is_rejected(self):
        with pytest.raises(ValueError, match="levels must be >= 2"):
            CartoSpec(levels=1)

    def test_a_levels_of_the_wrong_type_is_rejected(self):
        with pytest.raises(TypeError, match="levels must be an int or a sequence"):
            CartoSpec(levels="many")

    def test_max_cols_is_bounded(self):
        with pytest.raises(ValueError, match="max_cols must be between 1 and 3"):
            CartoSpec(max_cols=4)

    def test_extend_is_validated(self):
        with pytest.raises(ValueError, match="extend must be"):
            CartoSpec(extend="up")

    def test_explicit_levels_are_accepted(self):
        assert CartoSpec(levels=(0.0, 0.5, 1.0)).levels == (0.0, 0.5, 1.0)


class TestCartoOverrides:
    def test_a_dict_is_accepted_in_place_of_a_spec(self, configuration_dict, tmp_path):
        jobs = _jobs(configuration_dict, tmp_path)
        assert jobs
        written = _carto(configuration_dict, tmp_path, carto={"cmap": "magma", "levels": 7})
        assert written

    def test_level_is_an_accepted_alias_for_levels(self, configuration_dict, tmp_path):
        """The spelling that comes to mind at the call site, mapped not ignored."""
        y_axis = {"CN": {**_Y_AXIS["CN"], "CARTO": {"level": 5}}}
        jobs = _jobs(configuration_dict, tmp_path, y_axis_dict=y_axis)
        assert jobs[0].spec.levels == 5

    def test_a_quantity_overrides_the_defaults(self, configuration_dict, tmp_path):
        y_axis = {"CN": {**_Y_AXIS["CN"], "CARTO": {"cmap": "RdBu_r", "levels": 9}}}
        jobs = _jobs(configuration_dict, tmp_path, y_axis_dict=y_axis)
        assert jobs[0].spec.cmap == "RdBu_r"
        assert all(panel.spec.cmap == "RdBu_r" for panel in jobs[0].panels)

    def test_a_configuration_overrides_the_quantity(self, configuration_dict, tmp_path):
        configuration_dict["MODEL"]["CARTO"] = {"line_color": "0.4", "clabel": False}
        y_axis = {"CN": {**_Y_AXIS["CN"], "CARTO": {"line_color": "black"}}}
        jobs = _jobs(configuration_dict, tmp_path, y_axis_dict=y_axis)
        by_source = {panel.source: panel.spec for panel in jobs[0].panels}
        assert by_source["CFD"].line_color == "black"
        assert by_source["MODEL"].line_color == "0.4"
        assert by_source["MODEL"].clabel is False

    def test_an_unknown_carto_key_is_rejected_by_name(self, configuration_dict, tmp_path):
        configuration_dict["CFD"]["CARTO"] = {"colormap": "magma"}
        with pytest.raises(ValueError, match="unknown CARTO key 'colormap'"):
            _jobs(configuration_dict, tmp_path)

    def test_a_carto_entry_of_the_wrong_type_is_rejected(self, configuration_dict, tmp_path):
        configuration_dict["CFD"]["CARTO"] = "magma"
        with pytest.raises(TypeError, match="must be a dict of options"):
            _jobs(configuration_dict, tmp_path)

    def test_carto_never_reaches_plot_line(self, configuration_dict):
        """The same configuration_dict drives batch_plot unchanged."""
        configuration_dict["CFD"]["CARTO"] = {"cmap": "magma"}
        kwargs = _extract_plot_style_kwargs(configuration_dict["CFD"])
        assert "CARTO" not in kwargs

    def test_carto_argument_of_the_wrong_type_is_rejected(self, configuration_dict, tmp_path):
        with pytest.raises(TypeError, match="carto must be a CartoSpec"):
            _carto(configuration_dict, tmp_path, carto="magma")


class TestPairs:
    def test_every_combination_by_default(self):
        assert _resolve_pairs(None, ["a", "b", "c"]) == [
            ("a", "b"),
            ("a", "c"),
            ("b", "c"),
        ]

    def test_one_sweep_cannot_make_a_map(self):
        with pytest.raises(ValueError, match="at least two sweep variables"):
            _resolve_pairs(None, ["alpha"])

    def test_an_explicit_pair_is_honoured_in_its_own_order(self):
        assert _resolve_pairs([("Mach", "alpha")], ["alpha", "Mach"]) == [("Mach", "alpha")]

    def test_an_unknown_key_is_rejected(self):
        with pytest.raises(KeyError, match="not in sweep_dict"):
            _resolve_pairs([("alpha", "Reynolds")], ["alpha", "Mach"])

    def test_a_sweep_against_itself_is_rejected(self):
        with pytest.raises(ValueError, match="against itself"):
            _resolve_pairs([("alpha", "alpha")], ["alpha", "Mach"])

    def test_a_malformed_pair_is_rejected(self):
        with pytest.raises(ValueError, match="must be two sweep keys"):
            _resolve_pairs([("alpha",)], ["alpha", "Mach"])

    def test_pairs_restrict_the_run(self, configuration_dict, tmp_path):
        sweeps = {**_SWEEPS, "Altitude_m": {"col_name": "Altitude_m", "x_save_name": "Z"}}
        every = _jobs(configuration_dict, tmp_path, sweep_dict=sweeps)
        assert len({(job.sweep_x_key, job.sweep_y_key) for job in every}) == 3

        one = _jobs(
            configuration_dict, tmp_path, sweep_dict=sweeps, pairs=[("alpha", "Mach")]
        )
        assert {(job.sweep_x_key, job.sweep_y_key) for job in one} == {("alpha", "Mach")}


class TestEnumeration:
    def test_one_job_per_flight_point_and_quantity(self, configuration_dict, tmp_path):
        jobs = _jobs(configuration_dict, tmp_path, y_axis_dict=_TWO_Y_AXES)
        # 2 altitudes x 2 quantities, beta constant so it is not a directory.
        assert len(jobs) == 4
        assert {job.qoi_key for job in jobs} == {"CN", "CA"}

    def test_the_pair_names_the_top_directory_and_the_file(self, configuration_dict, tmp_path):
        job = _jobs(configuration_dict, tmp_path)[0]
        assert job.polar_prefix == "ALPHA_MACH_CARTO"
        assert job.output_path.name == "CN_vs_alpha_Mach"
        assert job.output_path.parent.name == "Z_5000"

    def test_a_third_sweep_becomes_a_directory_level(self, configuration_dict, tmp_path):
        """Every sweep outside the pair is pinned, exactly as batch_plot pins it."""
        sweeps = {**_SWEEPS, "Altitude_m": {"col_name": "Altitude_m", "x_save_name": "Z",
                                            "save_name": "Z"}}
        jobs = _jobs(configuration_dict, tmp_path, sweep_dict=sweeps,
                     pairs=[("alpha", "Mach")])
        assert {job.output_path.parent.name for job in jobs} == {"Z_5000", "Z_10000"}
        assert all(job.fixed_sweeps for job in jobs)

    def test_one_panel_per_configuration(self, configuration_dict, tmp_path):
        job = _jobs(configuration_dict, tmp_path)[0]
        assert [panel.source for panel in job.panels] == ["CFD", "MODEL"]
        assert [panel.label for panel in job.panels] == ["CFD", "Model"]

    def test_the_grid_has_the_shape_of_the_sweeps(self, configuration_dict, tmp_path):
        panel = _jobs(configuration_dict, tmp_path)[0].panels[0]
        assert panel.x.tolist() == list(_ALPHAS)
        assert panel.y.tolist() == list(_MACHS)
        assert panel.z.shape == (len(_MACHS), len(_ALPHAS))

    def test_include_panel_filters_sources(self, configuration_dict, tmp_path):
        def only_cfd(source, flight_point, pair, qoi_key, fixed_sweeps):
            assert pair == ("alpha", "Mach")
            assert qoi_key == "CN"
            return source == "CFD"

        jobs = _jobs(configuration_dict, tmp_path, include_panel=only_cfd)
        assert all([panel.source for panel in job.panels] == ["CFD"] for job in jobs)

    def test_a_source_with_no_rows_here_is_skipped(self, configuration_dict, tmp_path):
        frame = configuration_dict["MODEL"]["df"]
        configuration_dict["MODEL"]["df"] = frame[frame["Altitude_m"] == 5000.0]
        by_altitude = {
            job.flight_point["Altitude_m"]: [panel.source for panel in job.panels]
            for job in _jobs(configuration_dict, tmp_path)
        }
        assert by_altitude[5000.0] == ["CFD", "MODEL"]
        assert by_altitude[10000.0] == ["CFD"]

    def test_an_all_nan_quantity_produces_no_panel(self, configuration_dict, tmp_path):
        for config in configuration_dict.values():
            config["df"] = config["df"].assign(CN=np.nan)
        assert _jobs(configuration_dict, tmp_path) == []

    def test_a_hole_in_the_study_stays_a_hole(self, configuration_dict, tmp_path):
        """A cell nobody ran is NaN, not interpolated across."""
        frame = configuration_dict["CFD"]["df"]
        configuration_dict["CFD"]["df"] = frame[
            ~((frame["alpha"] == 2.0) & (frame["Mach"] == 0.8))
        ]
        panel = _jobs(configuration_dict, tmp_path)[0].panels[0]
        assert np.isnan(panel.z).sum() == 1

    def test_an_unpinned_dimension_is_an_error_naming_the_source(
        self, configuration_dict, tmp_path
    ):
        """Two rows in one cell: some column varies that never became a directory."""
        frame = configuration_dict["CFD"]["df"]
        configuration_dict["CFD"]["df"] = pd.concat([frame, frame.assign(CN=frame["CN"] * 2)])
        with pytest.raises(ValueError, match=r"cannot grid 'CN'.*'CFD'"):
            _jobs(configuration_dict, tmp_path)

    def test_a_missing_column_is_an_error(self, configuration_dict, tmp_path):
        y_axis = {"CZ": {"col_name": "CZ", "y_save_name": "CZ"}}
        with pytest.raises(KeyError, match="CZ"):
            _jobs(configuration_dict, tmp_path, y_axis_dict=y_axis)

    def test_the_heading_names_the_quantity_and_the_pair(self, configuration_dict, tmp_path):
        job = _jobs(configuration_dict, tmp_path)[0]
        assert job.suptitle == r"$C_N$ over $\alpha$ × $M$"
        assert job.subtitle == r"Z=5000 m, $\beta$=0 deg"


class TestSharedScale:
    def test_the_level_values_are_shared_across_panels(self, configuration_dict, tmp_path):
        job = _jobs(configuration_dict, tmp_path)[0]
        levels = _shared_levels(job)
        assert levels is not None
        lows = [panel.finite_range[0] for panel in job.panels]
        highs = [panel.finite_range[1] for panel in job.panels]
        assert levels[0] == pytest.approx(min(lows))
        assert levels[-1] == pytest.approx(max(highs))
        assert len(levels) == 11

    def test_shared_scale_off_leaves_the_levels_to_each_panel(
        self, configuration_dict, tmp_path
    ):
        job = _jobs(configuration_dict, tmp_path, base_spec=CartoSpec(shared_scale=False))[0]
        assert _shared_levels(job) is None

    def test_an_explicit_level_array_is_used_as_given(self, configuration_dict, tmp_path):
        spec = CartoSpec(levels=(0.0, 1.0, 2.0))
        job = _jobs(configuration_dict, tmp_path, base_spec=spec)[0]
        assert _shared_levels(job).tolist() == [0.0, 1.0, 2.0]

    def test_a_constant_quantity_still_gets_increasing_levels(
        self, configuration_dict, tmp_path
    ):
        """A model that ignores one sweep is a result, not a crash."""
        for config in configuration_dict.values():
            config["df"] = config["df"].assign(CN=1.0)
        job = _jobs(configuration_dict, tmp_path)[0]
        levels = _shared_levels(job)
        assert np.all(np.diff(levels) > 0)
        written = _carto(configuration_dict, tmp_path)
        assert written and written[0].exists()

    def test_panels_disagreeing_on_the_scale_are_refused(self, configuration_dict, tmp_path):
        """One colorbar cannot describe two colormaps."""
        configuration_dict["MODEL"]["CARTO"] = {"cmap": "magma"}
        with pytest.raises(ValueError, match="panels disagree on the colour scale"):
            _carto(configuration_dict, tmp_path)

    def test_the_refusal_names_the_way_out(self, configuration_dict, tmp_path):
        configuration_dict["MODEL"]["CARTO"] = {"cmap": "magma"}
        with pytest.raises(ValueError, match="shared_scale=False"):
            _carto(configuration_dict, tmp_path)

    def test_disagreeing_panels_are_fine_without_a_shared_scale(
        self, configuration_dict, tmp_path
    ):
        configuration_dict["MODEL"]["CARTO"] = {"cmap": "magma"}
        written = _carto(configuration_dict, tmp_path, carto={"shared_scale": False})
        assert written and written[0].exists()

    def test_a_single_panel_may_differ_freely(self, configuration_dict, tmp_path):
        del configuration_dict["MODEL"]
        configuration_dict["CFD"]["CARTO"] = {"cmap": "magma", "levels": 5}
        written = _carto(configuration_dict, tmp_path)
        assert written and written[0].exists()


class TestRendering:
    def test_a_figure_is_written_per_job(self, configuration_dict, tmp_path):
        written = _carto(configuration_dict, tmp_path, y_axis_dict=_TWO_Y_AXES)
        assert len(written) == 4
        assert all(path.exists() for path in written)
        assert {path.name for path in written} == {"CN_vs_alpha_Mach.png", "CA_vs_alpha_Mach.png"}

    def test_the_panels_carry_fill_lines_and_labels(self, configuration_dict, tmp_path):
        """contourf + black contour + clabel, which is the whole point."""
        seen: list[tuple] = []

        def on_before_save(fig, ax, context):
            texts = [text for text in ax.texts if text.get_text()]
            seen.append((len(ax.collections), ax.get_title(), len(texts)))

        _carto(configuration_dict, tmp_path, on_before_save=on_before_save)
        assert len(seen) == 4
        for n_collections, title, n_labels in seen:
            assert n_collections >= 2  # the fill and the iso-lines
            assert title in ("CFD", "Model")
            assert n_labels > 0  # clabel wrote on the lines

    def test_clabel_off_leaves_the_lines_unlabelled(self, configuration_dict, tmp_path):
        labels: list[int] = []

        def on_before_save(fig, ax, context):
            labels.append(len([text for text in ax.texts if text.get_text()]))

        _carto(
            configuration_dict,
            tmp_path,
            carto={"clabel": False},
            on_before_save=on_before_save,
        )
        assert set(labels) == {0}

    def test_line_color_none_drops_the_iso_lines(self, configuration_dict, tmp_path):
        counts: list[int] = []

        def on_before_save(fig, ax, context):
            counts.append(len(ax.collections))

        _carto(
            configuration_dict,
            tmp_path,
            carto={"line_color": None},
            on_before_save=on_before_save,
        )
        with_lines: list[int] = []

        def with_lines_hook(fig, ax, context):
            with_lines.append(len(ax.collections))

        _carto(configuration_dict, tmp_path, on_before_save=with_lines_hook)
        assert max(counts) < max(with_lines)

    def test_the_context_describes_both_sweeps_and_the_source(
        self, configuration_dict, tmp_path
    ):
        seen: list[tuple] = []

        def on_before_save(fig, ax, context):
            seen.append(
                (
                    context.sweep_key,
                    context.carto_sweep_key,
                    context.y_key,
                    context.carto_source,
                    context.panel_index,
                )
            )

        _carto(configuration_dict, tmp_path, on_before_save=on_before_save)
        assert ("alpha", "Mach", "CN", "CFD", 0) in seen
        assert ("alpha", "Mach", "CN", "MODEL", 1) in seen

    def test_the_context_carries_the_vertical_sweep_spec(self, configuration_dict, tmp_path):
        specs: list[dict] = []

        def on_before_save(fig, ax, context):
            specs.append(context.carto_sweep_spec)

        _carto(configuration_dict, tmp_path, on_before_save=on_before_save)
        assert specs[0]["col_name"] == "Mach"

    def test_unused_grid_cells_are_hidden(self, configuration_dict, tmp_path):
        """Three panels on a two-wide grid leaves a fourth cell; it must not show."""
        configuration_dict["THIRD"] = {
            "name": "THIRD",
            "label": "Third",
            "df": pd.DataFrame(_rows(1.1)),
        }
        visible: list[bool] = []

        def on_before_save(fig, ax, context):
            visible.append([axes.get_visible() for axes in fig.axes])

        _carto(
            configuration_dict,
            tmp_path,
            carto={"max_cols": 2, "colorbar": False},
            on_before_save=on_before_save,
        )
        assert visible[-1].count(False) == 1

    def test_one_shared_colorbar_when_the_scale_is_shared(self, configuration_dict, tmp_path):
        counts: list[int] = []

        def on_before_save(fig, ax, context):
            counts.append(len(fig.axes))

        _carto(configuration_dict, tmp_path, on_before_save=on_before_save)
        # Two panels plus one colorbar, and it is already there when the hook
        # runs: the hook is the caller's last word on a finished figure.
        assert set(counts) == {3}

    def test_a_colorbar_per_panel_without_a_shared_scale(self, configuration_dict, tmp_path):
        counts: list[int] = []

        def on_before_save(fig, ax, context):
            counts.append(len(fig.axes))

        _carto(
            configuration_dict,
            tmp_path,
            carto={"shared_scale": False},
            on_before_save=on_before_save,
        )
        # Two panels, one colorbar each — and, as above, the figure is finished
        # before any hook sees it.
        assert set(counts) == {4}

    def test_the_map_is_not_forced_square(self, configuration_dict, tmp_path):
        """aspect="equal" over (alpha, Mach) would squash the map to a sliver."""
        aspects: list = []

        def on_before_save(fig, ax, context):
            aspects.append(ax.get_aspect())

        _carto(configuration_dict, tmp_path, on_before_save=on_before_save)
        assert set(aspects) == {"auto"}


class TestPipeline:
    def test_dry_run_writes_nothing(self, configuration_dict, tmp_path):
        planned = _carto(configuration_dict, tmp_path, dry_run=True)
        assert planned
        assert not any(path.exists() for path in planned)

    def test_the_plan_names_the_pair_and_the_overrides(
        self, configuration_dict, tmp_path, capsys
    ):
        configuration_dict["CFD"]["CARTO"] = {"levels": 7}
        _carto(configuration_dict, tmp_path, dry_run=True, verbose=True)
        out = capsys.readouterr().out
        assert "alpha" in out and "Mach" in out
        assert "CARTO overrides" in out

    def test_clean_wipes_the_previous_run(self, configuration_dict, tmp_path):
        stale = tmp_path / "ALPHA_MACH_CARTO" / "OLD.png"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"")
        _carto(configuration_dict, tmp_path, clean=True)
        assert not stale.exists()

    def test_a_job_survives_pickling(self, configuration_dict, tmp_path):
        """n_jobs > 1 sends the job, and its bound render method, to a worker."""
        job = _jobs(configuration_dict, tmp_path)[0]
        revived = pickle.loads(pickle.dumps(job))
        assert isinstance(revived, _CartoPlotJob)
        assert revived.output_path == job.output_path
        assert pickle.loads(pickle.dumps(job.render)) is not None

    def test_parallel_rendering_writes_the_same_files(self, configuration_dict, tmp_path):
        written = _carto(configuration_dict, tmp_path, y_axis_dict=_TWO_Y_AXES, n_jobs=2)
        assert len(written) == 4
        assert all(path.exists() for path in written)

    def test_the_progress_label_describes_the_map(self, configuration_dict, tmp_path):
        from cfd_plot.batch import _any_job_label

        job = _jobs(configuration_dict, tmp_path)[0]
        label = _any_job_label(job)
        assert "carto" in label
        assert "CN over alpha x Mach" in label

    def test_a_pdf_report_is_assembled(self, configuration_dict, tmp_path):
        pdf = tmp_path / "carto.pdf"
        written = _carto(configuration_dict, tmp_path, pdf_report=pdf)
        assert pdf in written
        assert pdf.exists() and pdf.stat().st_size > 0

    def test_an_empty_y_axis_dict_is_rejected(self, configuration_dict, tmp_path):
        with pytest.raises(ValueError, match="y_axis_dict must contain"):
            _carto(configuration_dict, tmp_path, y_axis_dict={})

    def test_no_sweep_dict_is_rejected(self, configuration_dict, tmp_path):
        with pytest.raises(ValueError, match="sweep_dict or x_axis_dict"):
            batch_carto(
                configuration_dict=configuration_dict,
                y_axis_dict=_Y_AXIS,
                sweep_dict=None,
                x_axis_dict=None,
                flight_point_dict=_FLIGHT_POINTS,
                output_base=tmp_path,
                report=False,
            )


class TestDeltaSpec:
    def test_defaults_suit_a_signed_field(self):
        spec = DeltaSpec()
        assert spec.mode == "absolute"
        # Diverging, and an ODD count so a boundary lands exactly on zero.
        assert spec.cmap == "RdBu_r"
        assert spec.levels % 2 == 1
        assert spec.bound is None
        # Matplotlib would dash every negative level; on a delta that is most.
        assert spec.line_style == "solid"

    def test_an_unknown_mode_is_rejected(self):
        with pytest.raises(ValueError, match="mode must be 'absolute' or 'relative'"):
            DeltaSpec(mode="percent")

    def test_a_non_positive_bound_is_rejected(self):
        with pytest.raises(ValueError, match="bound must be > 0"):
            DeltaSpec(bound=0.0)

    def test_levels_are_validated(self):
        with pytest.raises(ValueError, match="levels must be >= 2"):
            DeltaSpec(levels=1)
        with pytest.raises(TypeError, match="levels must be an int or a sequence"):
            DeltaSpec(levels="lots")

    def test_extend_is_validated(self):
        with pytest.raises(ValueError, match="extend must be None"):
            DeltaSpec(extend="up")

    def test_extend_defaults_to_both_only_when_the_bound_clips(self):
        assert DeltaSpec().resolved_extend == "neither"
        assert DeltaSpec(bound=5.0).resolved_extend == "both"
        assert DeltaSpec(bound=5.0, extend="neither").resolved_extend == "neither"

    def test_the_label_format_follows_the_mode(self):
        assert DeltaSpec().resolved_clabel_fmt == "%+.3g"
        assert DeltaSpec(mode="relative").resolved_clabel_fmt == "%+.1f%%"
        assert DeltaSpec(clabel_fmt="%.1f").resolved_clabel_fmt == "%.1f"


class TestDeltaPanel:
    def test_the_shorthands_all_resolve(self, configuration_dict, tmp_path):
        for shorthand, mode in (
            (True, "absolute"),
            ("relative", "relative"),
            ({"mode": "relative"}, "relative"),
            (DeltaSpec(mode="relative"), "relative"),
        ):
            spec = _resolve_delta_arg(shorthand, where="test")
            assert spec is not None and spec.mode == mode
        assert _resolve_delta_arg(None, where="test") is None
        assert _resolve_delta_arg(False, where="test") is None

    def test_an_unknown_delta_key_is_rejected_by_name(self):
        with pytest.raises(ValueError, match="unknown delta key 'colormap'"):
            _resolve_delta_arg({"colormap": "RdBu"}, where="test")

    def test_a_delta_of_the_wrong_type_is_rejected(self):
        with pytest.raises(TypeError, match="must be a bool, a mode string"):
            _resolve_delta_arg(3.5, where="test")

    def test_the_absolute_difference_is_conf2_minus_conf1(
        self, configuration_dict, tmp_path
    ):
        """conf1 is the reference by convention: the sign reads as conf2's excess."""
        job = _jobs(configuration_dict, tmp_path, base_spec=CartoSpec(delta=DeltaSpec()))[0]
        reference, other = job.panels
        assert job.delta is not None
        assert job.delta.reference == "CFD"
        assert job.delta.other == "MODEL"
        assert job.delta.z == pytest.approx(other.z - reference.z)
        assert np.all(job.delta.z <= 0.0)  # MODEL is 0.9 x CFD

    def test_the_relative_difference_is_a_percentage_of_the_reference(
        self, configuration_dict, tmp_path
    ):
        spec = CartoSpec(delta=DeltaSpec(mode="relative"))
        job = _jobs(configuration_dict, tmp_path, base_spec=spec)[0]
        finite = job.delta.z[np.isfinite(job.delta.z)]
        assert finite == pytest.approx(-10.0)  # MODEL is 0.9 x CFD, everywhere

    def test_a_zero_reference_leaves_a_hole_not_an_infinity(
        self, configuration_dict, tmp_path
    ):
        """A percentage of nothing is undefined; an inf would rescale the map."""
        for config in configuration_dict.values():
            frame = config["df"]
            config["df"] = frame.assign(CN=frame["CN"].where(frame["alpha"] > 0.0, 0.0))
        spec = CartoSpec(delta=DeltaSpec(mode="relative"))
        job = _jobs(configuration_dict, tmp_path, base_spec=spec)[0]
        assert np.isnan(job.delta.z[:, 0]).all()      # alpha = 0 column
        assert np.isfinite(job.delta.z[:, 1:]).all()

    def test_the_panel_title_reads_as_the_subtraction(self, configuration_dict, tmp_path):
        absolute = _jobs(
            configuration_dict, tmp_path, base_spec=CartoSpec(delta=DeltaSpec())
        )[0]
        assert absolute.delta.label == "Model − CFD"
        relative = _jobs(
            configuration_dict,
            tmp_path,
            base_spec=CartoSpec(delta=DeltaSpec(mode="relative")),
        )[0]
        assert relative.delta.label == "(Model − CFD) / CFD"

    def test_the_colorbar_label_carries_the_unit_or_the_percent(
        self, configuration_dict, tmp_path
    ):
        absolute = _jobs(
            configuration_dict, tmp_path, base_spec=CartoSpec(delta=DeltaSpec())
        )[0]
        assert absolute.delta.cbar_label == r"Δ$C_N$ (-)"
        relative = _jobs(
            configuration_dict,
            tmp_path,
            base_spec=CartoSpec(delta=DeltaSpec(mode="relative")),
        )[0]
        assert relative.delta.cbar_label == r"Δ$C_N$ / $C_N$ (%)"

    def test_an_explicit_label_wins(self, configuration_dict, tmp_path):
        spec = CartoSpec(delta=DeltaSpec(label="Écart modèle"))
        job = _jobs(configuration_dict, tmp_path, base_spec=spec)[0]
        assert job.delta.cbar_label == "Écart modèle"

    def test_different_grids_cannot_be_subtracted(self, configuration_dict, tmp_path):
        """Cell by cell is the only honest subtraction."""
        frame = configuration_dict["MODEL"]["df"]
        configuration_dict["MODEL"]["df"] = frame[frame["alpha"] < 6.0]
        with pytest.raises(ValueError, match="run on different grids"):
            _jobs(configuration_dict, tmp_path, base_spec=CartoSpec(delta=DeltaSpec()))

    def test_a_flight_point_with_one_source_simply_has_no_delta(
        self, configuration_dict, tmp_path
    ):
        frame = configuration_dict["MODEL"]["df"]
        configuration_dict["MODEL"]["df"] = frame[frame["Altitude_m"] == 5000.0]
        jobs = _jobs(configuration_dict, tmp_path, base_spec=CartoSpec(delta=DeltaSpec()))
        by_altitude = {job.flight_point["Altitude_m"]: job for job in jobs}
        assert by_altitude[5000.0].delta is not None
        assert by_altitude[10000.0].delta is None

    def test_delta_needs_exactly_two_configurations(self, configuration_dict, tmp_path):
        configuration_dict["THIRD"] = {"label": "Third", "df": pd.DataFrame(_rows(1.1))}
        with pytest.raises(ValueError, match="delta compares exactly two configurations"):
            _carto(configuration_dict, tmp_path, delta=True)

    def test_delta_is_not_a_property_of_one_panel(self, configuration_dict, tmp_path):
        configuration_dict["CFD"]["CARTO"] = {"delta": True}
        with pytest.raises(ValueError, match="'delta' is a property of the figure"):
            _jobs(configuration_dict, tmp_path)

    def test_a_quantity_may_carry_its_own_delta(self, configuration_dict, tmp_path):
        y_axis = {"CN": {**_Y_AXIS["CN"], "CARTO": {"delta": {"mode": "relative"}}}}
        job = _jobs(configuration_dict, tmp_path, y_axis_dict=y_axis)[0]
        assert job.delta is not None and job.delta.spec.mode == "relative"


class TestDeltaScale:
    def test_the_scale_is_symmetric_around_zero(self, configuration_dict, tmp_path):
        job = _jobs(configuration_dict, tmp_path, base_spec=CartoSpec(delta=DeltaSpec()))[0]
        levels = _delta_levels(job.delta)
        assert levels[0] == pytest.approx(-levels[-1])
        assert levels[len(levels) // 2] == pytest.approx(0.0)

    def test_an_odd_count_puts_a_boundary_exactly_on_zero(
        self, configuration_dict, tmp_path
    ):
        """Even, and a band straddles zero: a neighbourhood of nothing takes a side."""
        spec = CartoSpec(delta=DeltaSpec(levels=13))
        job = _jobs(configuration_dict, tmp_path, base_spec=spec)[0]
        levels = _delta_levels(job.delta)
        assert min(abs(value) for value in levels) == pytest.approx(0.0)

    def test_the_bound_pins_the_scale(self, configuration_dict, tmp_path):
        spec = CartoSpec(delta=DeltaSpec(mode="relative", bound=25.0))
        job = _jobs(configuration_dict, tmp_path, base_spec=spec)[0]
        levels = _delta_levels(job.delta)
        assert levels[0] == pytest.approx(-25.0)
        assert levels[-1] == pytest.approx(25.0)

    def test_identical_configurations_still_produce_a_drawable_scale(
        self, configuration_dict, tmp_path
    ):
        configuration_dict["MODEL"]["df"] = configuration_dict["CFD"]["df"].copy()
        job = _jobs(configuration_dict, tmp_path, base_spec=CartoSpec(delta=DeltaSpec()))[0]
        levels = _delta_levels(job.delta)
        assert np.all(np.diff(levels) > 0)
        written = _carto(configuration_dict, tmp_path, delta=True)
        assert written and written[0].exists()

    def test_explicit_levels_are_used_as_given(self, configuration_dict, tmp_path):
        spec = CartoSpec(delta=DeltaSpec(levels=(-1.0, 0.0, 1.0)))
        job = _jobs(configuration_dict, tmp_path, base_spec=spec)[0]
        assert _delta_levels(job.delta).tolist() == [-1.0, 0.0, 1.0]


class TestDeltaRendering:
    def test_the_figure_gains_a_third_panel(self, configuration_dict, tmp_path):
        titles: list[str] = []

        def on_before_save(fig, ax, context):
            titles.append(ax.get_title())

        _carto(configuration_dict, tmp_path, delta=True, on_before_save=on_before_save)
        assert titles[:3] == ["CFD", "Model", "Model − CFD"]

    def test_the_hook_can_tell_the_delta_panel_apart(self, configuration_dict, tmp_path):
        seen: list[tuple] = []

        def on_before_save(fig, ax, context):
            seen.append((context.carto_source, context.carto_delta))

        _carto(configuration_dict, tmp_path, delta="relative", on_before_save=on_before_save)
        assert seen[:3] == [("CFD", None), ("MODEL", None), (None, "relative")]

    def test_the_field_colorbar_does_not_span_the_delta(
        self, configuration_dict, tmp_path
    ):
        """Two scales, two bars: one spanning all three would suggest they share."""
        counts: list[int] = []

        def on_before_save(fig, ax, context):
            counts.append(len(fig.axes))

        _carto(configuration_dict, tmp_path, delta=True, on_before_save=on_before_save)
        # 3 panels + the shared field bar + the delta's own bar.
        assert set(counts) == {5}

    def test_the_delta_colorbar_can_be_dropped(self, configuration_dict, tmp_path):
        counts: list[int] = []

        def on_before_save(fig, ax, context):
            counts.append(len(fig.axes))

        _carto(
            configuration_dict,
            tmp_path,
            delta={"colorbar": False},
            on_before_save=on_before_save,
        )
        assert set(counts) == {4}

    def test_the_delta_lines_are_solid(self, configuration_dict, tmp_path):
        """Matplotlib dashes negative levels; a delta is mostly negative here."""
        styles: list = []

        def on_before_save(fig, ax, context):
            if context.carto_delta:
                styles.extend(
                    collection.get_linestyle() for collection in ax.collections[1:]
                )

        _carto(configuration_dict, tmp_path, delta=True, on_before_save=on_before_save)
        assert styles
        # A solid line has no dash pattern.
        assert all(pattern is None for _offset, pattern in
                   [style[0] for style in styles if style])

    def test_the_report_grade_settings_render(self, configuration_dict, tmp_path):
        """The block the README hands out, exercised end to end."""
        y_axis = {
            "CN": {
                **_Y_AXIS["CN"],
                "CARTO": {
                    "cmap": "jet",
                    "levels": 25,
                    "line_levels": 9,
                    "clabel_fmt": "%.2f",
                    "clabel_fontsize": 8,
                    "panel_size": (4.6, 4.0),
                    "delta": {
                        "mode": "relative",
                        "levels": 13,
                        "bound": 6.0,
                        "line_levels": 7,
                        "clabel_fmt": "%+.1f%%",
                    },
                },
            },
        }
        written = _carto(configuration_dict, tmp_path, y_axis_dict=y_axis)
        assert written and all(path.exists() for path in written)

    def test_panel_size_sets_the_figure_size(self, configuration_dict, tmp_path):
        sizes: list[tuple[float, float]] = []

        def on_before_save(fig, ax, context):
            sizes.append(tuple(fig.get_size_inches()))

        _carto(
            configuration_dict,
            tmp_path,
            carto={"panel_size": (4.0, 3.0)},
            on_before_save=on_before_save,
        )
        assert sizes[0] == (8.0, 3.0)  # two panels wide, one row

    def test_a_bad_panel_size_is_rejected(self):
        with pytest.raises(ValueError, match="panel_size must be two positive inches"):
            CartoSpec(panel_size=(0.0, 3.0))

    def test_the_plan_names_the_subtraction(self, configuration_dict, tmp_path, capsys):
        _carto(configuration_dict, tmp_path, delta="relative", dry_run=True, verbose=True)
        out = capsys.readouterr().out
        assert "Delta panel" in out
        assert "MODEL - CFD" in out
