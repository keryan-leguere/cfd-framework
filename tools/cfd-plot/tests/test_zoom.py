"""Tests for x-axis zooms in batch_plot (extra figures and insets)."""

from __future__ import annotations

import pickle
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.transforms import Bbox

from cfd_plot import ZoomSpec, batch_plot
from cfd_plot import batch as batch_module
from cfd_plot.zoom import (
    RESERVE_GID,
    _data_artists,
    _polylines,
    _samples_in_axes,
    add_zoom_insets,
    resolve_zooms,
    zoom_data_ylim,
    zoom_factor_label,
)

ALPHA = np.linspace(-4.0, 20.0, 49)


def _cn(scale: float, offset: float) -> np.ndarray:
    """Linear lift, then a stall past 12°: a peak worth zooming on."""
    return 0.1 * ALPHA * scale + offset - 0.06 * np.maximum(ALPHA - 12.0, 0.0) ** 2


@pytest.fixture()
def configuration_dict() -> dict:
    def frame(scale: float, offset: float) -> pd.DataFrame:
        return pd.DataFrame({"Mach": 0.8, "alpha": ALPHA, "CN": _cn(scale, offset)})

    return {
        "KW": {"df": frame(1.0, 0.0), "label": "KW", "color": "C0", "marker": "o"},
        "SA": {"df": frame(1.02, 0.03), "label": "SA", "color": "C1", "marker": "s"},
    }


Y_AXIS = {"CN": {"col_name": "CN", "symbol": r"$C_N$", "unit": "-"}}


def _sweep(zoom) -> dict:
    return {"alpha": {"col_name": "alpha", "symbol": r"$\alpha$", "unit": "°", "zoom": zoom}}


def _run(configuration_dict, tmp_path, zoom, **kwargs):
    return batch_plot(
        configuration_dict=configuration_dict,
        y_axis_dict=Y_AXIS,
        sweep_dict=_sweep(zoom),
        flight_point_dict={"Mach": {}},
        output_base=tmp_path,
        report=False,
        **kwargs,
    )


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


# ---------------------------------------------------------------------------
# Declaration
# ---------------------------------------------------------------------------


class TestResolveZooms:
    def test_bare_pair_is_one_zoom(self):
        (spec,) = resolve_zooms((0, 4))
        assert spec.xlim == (0.0, 4.0)
        assert spec.mode == "figure"

    def test_dict_and_spec_and_list(self):
        specs = resolve_zooms(
            [(0, 4), {"xlim": (8, 12), "mode": "inset"}, ZoomSpec(xlim=(1, 2), mode="both")]
        )
        assert [s.mode for s in specs] == ["figure", "inset", "both"]

    def test_none_is_no_zoom(self):
        assert resolve_zooms(None) == ()

    @pytest.mark.parametrize(
        ("value", "match"),
        [
            ((4, 0), "increasing"),
            ({"xlim": (0, 1), "mode": "popup"}, "mode"),
            ({"xlim": (0, 1), "colour": "r"}, "unknown zoom key"),
            ({"mode": "inset"}, "needs 'xlim'"),
            ("0-4", "a zoom is"),
            ({"xlim": (0, 1), "loc": "top"}, "loc"),
            ({"xlim": (0, 1), "size": (0, 0.4)}, "size"),
            ({"xlim": (0, float("nan"))}, "finite"),
        ],
    )
    def test_bad_declarations_are_refused(self, value, match):
        with pytest.raises(ValueError, match=match):
            resolve_zooms(value, "sweep_dict['alpha']['zoom']")

    def test_same_file_twice_is_refused(self):
        with pytest.raises(ValueError, match="same file"):
            resolve_zooms([{"xlim": (0, 1), "name": "A"}, {"xlim": (2, 3), "name": "A"}])

    def test_inset_only_zooms_may_share_bounds(self):
        assert len(resolve_zooms([{"xlim": (0, 1), "mode": "inset"}] * 2)) == 2

    def test_file_suffix(self):
        assert ZoomSpec(xlim=(0, 4)).file_suffix == "ZOOM_0_4"
        assert ZoomSpec(xlim=(-2.5, 4)).file_suffix == "ZOOM_-2.5_4"
        assert ZoomSpec(xlim=(0, 4), name="stall").file_suffix == "ZOOM_stall"

    def test_spec_pickles(self):
        spec = ZoomSpec(xlim=(0, 4), mode="both", loc=(0.1, 0.1, 0.3, 0.3))
        assert pickle.loads(pickle.dumps(spec)) == spec

    def test_error_names_the_sweep(self, configuration_dict, tmp_path):
        with pytest.raises(ValueError, match=r"sweep_dict\['alpha'\]\['zoom'\]"):
            _run(configuration_dict, tmp_path, (4, 0), dry_run=True)


class TestLimitsAndLabels:
    def test_ylim_fitted_inside_range_with_interpolated_bounds(self):
        x = np.array([0.0, 10.0])
        y = np.array([0.0, 10.0])
        lo, hi = zoom_data_ylim(ZoomSpec(xlim=(2, 4), margin=0.0), [(x, y)])
        # No sample lies in [2, 4]: the values come from interpolation.
        assert (lo, hi) == pytest.approx((2.0, 4.0))

    def test_ylim_margin(self):
        x = np.array([0.0, 10.0])
        lo, hi = zoom_data_ylim(ZoomSpec(xlim=(2, 4), margin=0.1), [(x, x)])
        assert (lo, hi) == pytest.approx((1.8, 4.2))

    def test_declared_ylim_wins(self):
        spec = ZoomSpec(xlim=(2, 4), ylim=(-1, 1))
        assert zoom_data_ylim(spec, [(np.arange(5.0), np.arange(5.0))]) == (-1.0, 1.0)

    def test_flat_curve_gets_a_nonzero_range(self):
        lo, hi = zoom_data_ylim(ZoomSpec(xlim=(0, 1)), [(np.arange(3.0), np.ones(3))])
        assert lo < 1.0 < hi

    def test_no_data_in_range(self):
        assert zoom_data_ylim(ZoomSpec(xlim=(50, 60)), [(np.arange(3.0), np.ones(3))]) is None

    def test_default_label_is_the_factor(self):
        assert zoom_factor_label(ZoomSpec(xlim=(0, 6)), 24.0) == "Zoom \u00d74"
        assert zoom_factor_label(ZoomSpec(xlim=(0, 2)), 25.0).endswith("12")

    def test_custom_and_empty_label(self):
        assert zoom_factor_label(ZoomSpec(xlim=(0, 6), label="Stall"), 24.0) == "Stall"
        assert zoom_factor_label(ZoomSpec(xlim=(0, 6), label=""), 24.0) == ""

    def test_zoom_wider_than_data_is_just_zoom(self):
        assert zoom_factor_label(ZoomSpec(xlim=(0, 30)), 24.0) == "Zoom"


# ---------------------------------------------------------------------------
# Extra figures
# ---------------------------------------------------------------------------


_SEEN: list[tuple] = []


def _record_limits(fig, ax, context):
    _SEEN.append((context.zoom, ax.get_xlim(), ax.get_ylim(), ax.get_title(), len(ax.child_axes)))


class TestZoomFigure:
    def test_dry_run_lists_the_extra_file(self, configuration_dict, tmp_path):
        planned = _run(configuration_dict, tmp_path, (10, 16), dry_run=True)
        names = sorted(p.name for p in planned)
        assert names == ["CN_vs_alpha.svg", "CN_vs_alpha_ZOOM_10_16.svg"]

    def test_inset_mode_writes_no_extra_file(self, configuration_dict, tmp_path):
        planned = _run(
            configuration_dict, tmp_path, {"xlim": (10, 16), "mode": "inset"}, dry_run=True
        )
        assert [p.name for p in planned] == ["CN_vs_alpha.svg"]

    def test_both_mode(self, configuration_dict, tmp_path):
        planned = _run(
            configuration_dict, tmp_path, {"xlim": (10, 16), "mode": "both", "name": "stall"},
            dry_run=True,
        )
        assert sorted(p.name for p in planned) == ["CN_vs_alpha.svg", "CN_vs_alpha_ZOOM_stall.svg"]

    def test_files_are_written(self, configuration_dict, tmp_path):
        written = _run(configuration_dict, tmp_path, [(10, 16), (-1, 1)], formats=("png",))
        assert sorted(p.name for p in written) == [
            "CN_vs_alpha.png",
            "CN_vs_alpha_ZOOM_-1_1.png",
            "CN_vs_alpha_ZOOM_10_16.png",
        ]
        assert all(p.stat().st_size > 0 for p in written)

    def test_limits_and_hook_context(self, configuration_dict, tmp_path):
        _SEEN.clear()
        _run(configuration_dict, tmp_path, {"xlim": (10, 16), "margin": 0.0},
             on_before_save=_record_limits)
        full, zoom = _SEEN
        assert full[0] is None
        spec, xlim, ylim, title, n_insets = zoom
        assert spec.xlim == (10.0, 16.0)
        assert xlim == (10.0, 16.0)
        inside = np.concatenate([_cn(1.0, 0.0), _cn(1.02, 0.03)])
        mask = np.tile((ALPHA >= 10) & (ALPHA <= 16), 2)
        assert ylim == pytest.approx((inside[mask].min(), inside[mask].max()))
        assert "Zoom" in title and title.startswith(full[3])
        assert n_insets == 0

    def test_zoom_figure_follows_its_parent(self, configuration_dict, tmp_path):
        planned = _run(configuration_dict, tmp_path, (10, 16), dry_run=True,
                       fold="context")
        # Zoom files sit beside their parent, never inside a fold.
        stems = [p.stem for p in planned]
        assert stems.index("CN_vs_alpha_ZOOM_10_16") == stems.index("CN_vs_alpha") + 1
        assert not any("FOLD" in str(p) and "ZOOM" in p.stem for p in planned)

    def test_range_without_data_warns_and_writes_nothing(self, configuration_dict, tmp_path):
        with pytest.warns(RuntimeWarning, match="holding no data"):
            planned = _run(configuration_dict, tmp_path, (50, 60), dry_run=True)
        assert [p.name for p in planned] == ["CN_vs_alpha.svg"]

    def test_x_axis_dict_carries_the_zoom(self, configuration_dict, tmp_path):
        planned = batch_plot(
            configuration_dict=configuration_dict,
            y_axis_dict=Y_AXIS,
            x_axis_dict=_sweep((10, 16)),
            flight_point_dict={"Mach": {}},
            output_base=tmp_path,
            dry_run=True,
            report=False,
        )
        assert any(p.stem.endswith("ZOOM_10_16") for p in planned)

    def test_parallel_rendering(self, configuration_dict, tmp_path):
        written = _run(configuration_dict, tmp_path, {"xlim": (10, 16), "mode": "both"},
                       formats=("png",), n_jobs=2)
        assert len(written) == 2

    def test_verbose_plan_mentions_zooms(self, configuration_dict, tmp_path, capsys):
        _run(configuration_dict, tmp_path, [(10, 16), {"xlim": (-1, 1), "mode": "inset"}],
             dry_run=True, verbose=True)
        out = capsys.readouterr().out
        assert "1 extra figure(s)" in out and "1 inset(s)" in out


# ---------------------------------------------------------------------------
# Insets
# ---------------------------------------------------------------------------


def _figure_with_stall():
    fig, ax = plt.subplots()
    ax.plot(ALPHA, _cn(1.0, 0.0), "o-", label="KW")
    ax.plot(ALPHA, _cn(1.02, 0.03), "s-", label="SA")
    ax.legend()
    return fig, ax


def _region(ax, spec_xlim, ylim) -> Bbox:
    to_axes = ax.transData + ax.transAxes.inverted()
    (x0, y0), (x1, y1) = to_axes.transform([(spec_xlim[0], ylim[0]), (spec_xlim[1], ylim[1])])
    return Bbox.from_extents(x0, y0, x1, y1)


def _hidden(ax, footprint: Bbox) -> int:
    lines, polys = _data_artists(ax)
    pts = _samples_in_axes(ax, _polylines(lines, polys))
    return int(np.count_nonzero(
        (pts[:, 0] >= footprint.x0) & (pts[:, 0] <= footprint.x1)
        & (pts[:, 1] >= footprint.y0) & (pts[:, 1] <= footprint.y1)
    ))


class TestInsets:
    def test_inset_shows_the_range_and_hides_no_data(self):
        fig, ax = _figure_with_stall()
        spec = ZoomSpec(xlim=(10, 16), mode="inset")
        ((inset, footprint),) = add_zoom_insets(ax, [spec])
        assert inset.get_xlim() == (10.0, 16.0)
        assert len(inset.get_lines()) == 2
        assert _hidden(ax, footprint) == 0
        ylim = inset.get_ylim()
        assert not footprint.overlaps(_region(ax, spec.xlim, ylim))
        assert inset.get_title().startswith("Zoom")

    def test_several_insets_never_cover_each_other_or_any_region(self):
        fig, ax = _figure_with_stall()
        specs = [ZoomSpec(xlim=(10, 16), mode="inset"), ZoomSpec(xlim=(-1, 1), mode="inset")]
        drawn = add_zoom_insets(ax, specs)
        assert len(drawn) == 2
        (a, fa), (b, fb) = drawn
        assert not fa.overlaps(fb)
        for _inset, footprint in drawn:
            assert _hidden(ax, footprint) == 0
        for spec, (inset, _) in zip(specs, drawn):
            region = _region(ax, spec.xlim, inset.get_ylim())
            assert not fa.overlaps(region) and not fb.overlaps(region)

    def test_footprint_includes_tick_labels_and_title(self):
        fig, ax = _figure_with_stall()
        ((inset, footprint),) = add_zoom_insets(ax, [ZoomSpec(xlim=(10, 16), mode="inset")])
        fig.canvas.draw()
        tight = inset.get_tightbbox(fig.canvas.get_renderer()).transformed(
            ax.transAxes.inverted()
        )
        assert footprint.x0 <= tight.x0 + 1e-3 and footprint.y0 <= tight.y0 + 1e-3
        assert footprint.x1 >= tight.x1 - 1e-3 and footprint.y1 >= tight.y1 - 1e-3

    def test_legend_best_avoids_the_inset(self):
        fig, ax = _figure_with_stall()
        ((_, footprint),) = add_zoom_insets(ax, [ZoomSpec(xlim=(10, 16), mode="inset")])
        reserves = [p for p in ax.patches if p.get_gid() == RESERVE_GID]
        assert len(reserves) == 1 and not reserves[0].get_visible()
        fig.canvas.draw()
        legend = ax.get_legend().get_window_extent().transformed(ax.transAxes.inverted())
        assert not legend.overlaps(footprint)

    def test_fixed_legend_is_an_obstacle(self):
        fig, ax = _figure_with_stall()
        ax.legend(loc="lower center")
        fig.canvas.draw()
        legend = ax.get_legend().get_window_extent().transformed(ax.transAxes.inverted())
        ((_, footprint),) = add_zoom_insets(ax, [ZoomSpec(xlim=(10, 16), mode="inset")])
        assert not legend.overlaps(footprint)

    def test_parent_limits_are_frozen(self):
        fig, ax = _figure_with_stall()
        before = (ax.get_xlim(), ax.get_ylim())
        add_zoom_insets(ax, [ZoomSpec(xlim=(10, 16), mode="inset")])
        ax.plot([100], [100])  # would autoscale if limits were still free
        assert (ax.get_xlim(), ax.get_ylim()) == before

    def test_hook_artists_are_replicated(self):
        fig, ax = _figure_with_stall()
        ax.fill_between(ALPHA, _cn(1.0, 0.0) - 0.05, _cn(1.0, 0.0) + 0.05, alpha=0.2)
        ax.plot(ALPHA, _cn(1.0, 0.0) + 0.1, "k--")
        ax.axhline(0.0)  # axes-coordinate decoration: not data, not copied
        ((inset, _),) = add_zoom_insets(ax, [ZoomSpec(xlim=(10, 16), mode="inset")])
        assert len(inset.get_lines()) == 3
        assert len(inset.collections) == 1

    def test_explicit_loc(self):
        fig, ax = _figure_with_stall()
        ((inset, _),) = add_zoom_insets(
            ax, [ZoomSpec(xlim=(10, 16), mode="inset", loc=(0.05, 0.05, 0.3, 0.2))]
        )
        fig.canvas.draw()
        bounds = inset.get_window_extent().transformed(ax.transAxes.inverted())
        assert bounds.bounds == pytest.approx((0.05, 0.05, 0.3, 0.2), abs=1e-6)

    def test_named_loc(self):
        fig, ax = _figure_with_stall()
        ((_, footprint),) = add_zoom_insets(
            ax, [ZoomSpec(xlim=(10, 16), mode="inset", loc="lower right")]
        )
        assert footprint.x1 == pytest.approx(0.98) and footprint.y0 == pytest.approx(0.02)

    def test_no_label_no_title(self):
        fig, ax = _figure_with_stall()
        ((inset, _),) = add_zoom_insets(ax, [ZoomSpec(xlim=(10, 16), mode="inset", label="")])
        assert inset.get_title() == ""

    def test_range_without_data_is_skipped(self):
        fig, ax = _figure_with_stall()
        assert add_zoom_insets(ax, [ZoomSpec(xlim=(50, 60), mode="inset")]) == []
        assert ax.child_axes == []

    def test_no_connectors(self):
        fig, ax = _figure_with_stall()
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            add_zoom_insets(ax, [ZoomSpec(xlim=(10, 16), mode="inset", connectors=False)])
        fig.canvas.draw()

    def test_batch_draws_the_inset_after_the_hook(self, configuration_dict, tmp_path,
                                                 monkeypatch):
        seen: list[int] = []
        original = batch_module.save_figure

        def spy(fig, path, **kwargs):
            seen.append(len(fig.axes[0].child_axes))
            return original(fig, path, **kwargs)

        monkeypatch.setattr(batch_module, "save_figure", spy)
        _SEEN.clear()
        written = _run(
            configuration_dict, tmp_path,
            [{"xlim": (10, 16), "mode": "inset"}, {"xlim": (-1, 1), "mode": "inset"}],
            formats=("png",), on_before_save=_record_limits,
        )
        assert [Path(p).name for p in written] == ["CN_vs_alpha.png"]
        assert seen == [2]
        assert _SEEN[0][4] == 0  # the hook ran before the insets

    def test_pdf_report_includes_zoom_figure(self, configuration_dict, tmp_path):
        pdf = tmp_path / "report.pdf"
        written = _run(configuration_dict, tmp_path, {"xlim": (10, 16), "mode": "both"},
                       formats=("png",), pdf_report=pdf)
        assert pdf in written and pdf.stat().st_size > 0
        assert any(p.stem.endswith("ZOOM_10_16") for p in written)
