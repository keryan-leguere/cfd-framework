"""Tests for the domain-region helpers (``cfd_plot.domains``)."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from cfd_plot import Domain, domain_segments, plot_domains


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


@pytest.fixture()
def sweep():
    """A Mach sweep crossing three regimes, sampled every 0.1."""
    x = np.round(np.arange(0.0, 2.01, 0.1), 3)
    idomain = np.where(x < 0.8, 0, np.where(x < 1.2, 1, 2))
    return x, idomain


def _axes(sweep):
    x, _ = sweep
    fig, ax = plt.subplots()
    ax.plot(x, np.sin(x))
    return fig, ax


class TestDomainSegments:
    def test_runs_are_cut_halfway_between_samples(self, sweep):
        x, idomain = sweep
        assert domain_segments(x, idomain) == [
            (0, 0.0, 0.75),
            (1, 0.75, 1.15),
            (2, 1.15, 2.0),
        ]

    def test_boundary_left_and_right(self, sweep):
        x, idomain = sweep
        left = domain_segments(x, idomain, boundary="left")
        right = domain_segments(x, idomain, boundary="right")
        assert [round(seg[1], 3) for seg in left] == [0.0, 0.7, 1.1]
        assert [round(seg[1], 3) for seg in right] == [0.0, 0.8, 1.2]

    def test_a_value_that_comes_back_gets_a_second_region(self):
        """Subsonic → transonic → subsonic is three regions, not two."""
        segments = domain_segments([0, 1, 2, 3], [0, 1, 1, 0])
        assert [seg[0] for seg in segments] == [0, 1, 0]

    def test_unsorted_x_is_sorted_first(self):
        """Solver output is not always monotonic; overlapping spans would be wrong."""
        segments = domain_segments([2, 0, 1, 3], [1, 0, 0, 1])
        assert segments == [(0, 0.0, 1.5), (1, 1.5, 3.0)]

    def test_missing_points_break_the_run(self):
        """A hole in the model is left blank, not shaded through."""
        segments = domain_segments([0, 1, 2, 3], [0, np.nan, 0, 0])
        assert segments == [(0, 0.0, 0.5), (0, 1.5, 3.0)]

    def test_a_point_without_an_x_is_dropped_without_breaking_the_run(self):
        segments = domain_segments([0, np.nan, 2, 3], [0, 0, 0, 0])
        assert segments == [(0, 0.0, 3.0)]

    def test_none_is_missing_too(self):
        assert domain_segments([0, 1], [None, None]) == []

    def test_empty_input(self):
        assert domain_segments([], []) == []

    def test_single_point(self):
        assert domain_segments([1.5], [3]) == [(3, 1.5, 1.5)]

    def test_length_mismatch_is_an_error(self):
        with pytest.raises(ValueError, match="same length"):
            domain_segments([0, 1, 2], [0, 1])

    def test_unknown_boundary_is_an_error(self):
        with pytest.raises(ValueError, match="boundary must be"):
            domain_segments([0, 1], [0, 1], boundary="middle")

    def test_string_domains_work_too(self):
        segments = domain_segments([0, 1, 2], ["attached", "attached", "stalled"])
        assert [seg[0] for seg in segments] == ["attached", "stalled"]

    def test_numpy_scalars_come_back_as_python_values(self, sweep):
        x, idomain = sweep
        assert all(type(seg[0]) is int for seg in domain_segments(x, idomain))

    def test_a_pandas_column_is_accepted(self, sweep):
        x, idomain = sweep
        frame = pd.DataFrame({"Mach": x, "iDomain": idomain})
        assert domain_segments(frame["Mach"], frame["iDomain"]) == domain_segments(x, idomain)


class TestPlotDomains:
    def test_one_patch_and_one_label_per_region(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        spans = plot_domains(ax, x, idomain, domains={0: "Sub", 1: "Trans", 2: "Super"})
        assert [span.name for span in spans] == ["Sub", "Trans", "Super"]
        assert all(span.patch is not None for span in spans)
        assert [span.text.get_text() for span in spans] == ["Sub", "Trans", "Super"]

    def test_labels_sit_at_the_middle_of_their_region(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        spans = plot_domains(ax, x, idomain)
        for span in spans:
            assert span.text.get_position()[0] == pytest.approx(0.5 * (span.start + span.end))

    def test_a_value_without_an_entry_is_named_after_itself(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        spans = plot_domains(ax, x, idomain, domains={1: "Transonic"})
        assert [span.name for span in spans] == ["0", "Transonic", "2"]

    def test_domain_dataclass_and_dict_entries_agree(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        from_dict = plot_domains(ax, x, idomain, domains={1: {"name": "T", "color": "#123456"}})
        from_object = plot_domains(ax, x, idomain, domains={1: Domain("T", color="#123456")})
        assert [(s.name, s.color) for s in from_dict] == [(s.name, s.color) for s in from_object]

    def test_an_unknown_domain_key_is_rejected(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        with pytest.raises(ValueError, match="unknown domain keys"):
            plot_domains(ax, x, idomain, domains={0: {"name": "Sub", "colour": "red"}})

    def test_a_domain_entry_of_the_wrong_type_is_rejected(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        with pytest.raises(TypeError, match="must be a str, a dict or a Domain"):
            plot_domains(ax, x, idomain, domains={0: 3.5})

    def test_colours_follow_the_value_not_the_order(self, sweep):
        """A sweep missing regime 1 keeps regime 2's colour.

        Otherwise the same regime changes colour from one flight point to the
        next, which is exactly the comparison the figures exist to support.
        """
        x, idomain = sweep
        fig, ax = _axes(sweep)
        full = plot_domains(ax, x, idomain)
        partial = plot_domains(ax, x, np.where(idomain == 1, 0, idomain))
        colors_full = {span.value: span.color for span in full}
        colors_partial = {span.value: span.color for span in partial}
        assert colors_partial[2] == colors_full[2]
        assert colors_partial[0] == colors_full[0]

    def test_explicit_colours_win(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        spans = plot_domains(ax, x, idomain, domains={2: {"name": "S", "color": "#FF0000"}})
        assert spans[-1].color == "#FF0000"

    def test_alternate_shades_every_other_region(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        spans = plot_domains(ax, x, idomain, alternate=True)
        assert [span.patch is not None for span in spans] == [True, False, True]

    def test_fill_false_draws_no_patch(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        spans = plot_domains(ax, x, idomain, fill=False)
        assert all(span.patch is None for span in spans)

    def test_lines_are_drawn_at_internal_boundaries_only(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        before = len(ax.lines)
        spans = plot_domains(ax, x, idomain, lines=True)
        drawn = [line for line in ax.lines[before:]]
        assert len(drawn) == len(spans) - 1
        assert [line.get_xdata()[0] for line in drawn] == [spans[1].start, spans[2].start]

    def test_line_style_can_be_overridden(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        before = len(ax.lines)
        plot_domains(ax, x, idomain, lines={"color": "red", "linewidth": 2.0})
        assert ax.lines[before].get_color() == "red"

    def test_hatch_takes_the_domain_colour(self, sweep):
        """A hatch on a near-white fill has to be drawn in something visible."""
        x, idomain = sweep
        fig, ax = _axes(sweep)
        spans = plot_domains(ax, x, idomain, domains={1: Domain("T", color="#D55E00", hatch="//")})
        patch = spans[1].patch
        assert patch.get_hatch() == "//"
        assert matplotlib.colors.to_hex(patch.get_edgecolor()) == "#d55e00"

    def test_per_domain_alpha_overrides_the_global_one(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        spans = plot_domains(ax, x, idomain, alpha=0.1, domains={1: Domain("T", alpha=0.5)})
        assert spans[1].alpha == 0.5
        assert spans[0].alpha == 0.1

    def test_narrow_regions_go_unlabelled(self):
        """A name wider than its own region lands on the neighbour instead."""
        x = np.linspace(0, 1, 101)
        idomain = np.where((x > 0.50) & (x < 0.52), 1, 0)
        fig, ax = plt.subplots()
        spans = plot_domains(ax, x, idomain)
        assert [span.text is not None for span in spans] == [True, False, True]

    def test_min_label_width_zero_labels_everything(self):
        x = np.linspace(0, 1, 101)
        idomain = np.where((x > 0.50) & (x < 0.52), 1, 0)
        fig, ax = plt.subplots()
        spans = plot_domains(ax, x, idomain, min_label_width=0.0)
        assert all(span.text is not None for span in spans)

    def test_label_locations(self, sweep):
        x, idomain = sweep
        for loc, expected_y in (("top", 1.0), ("inside", 0.965), ("bottom", 0.02)):
            fig, ax = _axes(sweep)
            spans = plot_domains(ax, x, idomain, label_loc=loc)
            assert spans[0].text.get_position()[1] == pytest.approx(expected_y)

    def test_label_loc_none_draws_no_text(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        spans = plot_domains(ax, x, idomain, label_loc="none")
        assert all(span.text is None for span in spans)

    def test_an_unknown_label_loc_is_rejected(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        with pytest.raises(ValueError, match="label_loc must be"):
            plot_domains(ax, x, idomain, label_loc="above")

    def test_label_kwargs_reach_the_text(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        spans = plot_domains(
            ax, x, idomain, label_rotation=90, label_kwargs={"fontsize": 6, "color": "red"}
        )
        text = spans[0].text
        assert text.get_rotation() == 90
        assert text.get_fontsize() == 6
        assert text.get_color() == "red"

    def test_label_box_puts_the_name_on_a_chip(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        spans = plot_domains(ax, x, idomain, label_box=True)
        assert spans[0].text.get_bbox_patch() is not None

    def test_top_labels_push_the_title_up_once(self, sweep):
        """Twice would stack two gaps under a title that has already moved."""
        x, idomain = sweep
        fig, ax = _axes(sweep)
        ax.set_title("CN vs Mach", fontsize=11, color="#112233")
        pad_before = matplotlib.rcParams["axes.titlepad"]
        plot_domains(ax, x, idomain)
        pad_once = ax.title.get_position()[1]
        plot_domains(ax, x, idomain)
        assert ax.title.get_position()[1] == pad_once
        assert ax.title.get_fontsize() == 11
        assert ax.title.get_color() == "#112233"
        assert pad_before == matplotlib.rcParams["axes.titlepad"]

    def test_an_untitled_axes_is_left_alone(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        plot_domains(ax, x, idomain)
        assert ax.get_title() == ""

    def test_legend_entries_are_unique_and_in_x_order(self):
        x = np.linspace(0, 3, 31)
        idomain = np.where(x < 1, 0, np.where(x < 2, 1, 0))
        fig, ax = plt.subplots()
        plot_domains(ax, x, idomain, domains={0: "Attached", 1: "Buffet"}, legend=True)
        assert ax.get_legend_handles_labels()[1] == ["Attached", "Buffet"]

    def test_legend_works_without_any_fill(self, sweep):
        """fill=False leaves no patch to label — the swatch is a proxy span."""
        x, idomain = sweep
        fig, ax = _axes(sweep)
        plot_domains(ax, x, idomain, fill=False, lines=True, legend=True)
        assert ax.get_legend_handles_labels()[1] == ["0", "1", "2"]

    def test_extend_axes_runs_the_edges_to_the_limits(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        ax.set_xlim(-1.0, 3.0)
        spans = plot_domains(ax, x, idomain, extend="axes")
        assert spans[0].start == -1.0
        assert spans[-1].end == 3.0

    def test_extend_data_stops_at_the_data(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        ax.set_xlim(-1.0, 3.0)
        spans = plot_domains(ax, x, idomain)
        assert spans[0].start == 0.0
        assert spans[-1].end == 2.0

    def test_an_unknown_extend_is_rejected(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        with pytest.raises(ValueError, match="extend must be"):
            plot_domains(ax, x, idomain, extend="figure")

    def test_extra_kwargs_reach_the_patch(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        spans = plot_domains(ax, x, idomain, edgecolor="black", linewidth=1.5)
        assert spans[0].patch.get_linewidth() == 1.5

    def test_nothing_to_draw_returns_an_empty_list(self):
        fig, ax = plt.subplots()
        assert plot_domains(ax, [], []) == []

    def test_the_regions_do_not_change_the_data_limits(self, sweep):
        """Shading is context: it must never rescale the y axis."""
        x, idomain = sweep
        fig, ax = _axes(sweep)
        before = ax.get_ylim()
        plot_domains(ax, x, idomain)
        assert ax.get_ylim() == before

    def test_spans_tile_the_x_range_without_gaps(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        spans = plot_domains(ax, x, idomain)
        for previous, current in zip(spans, spans[1:]):
            assert previous.end == current.start
        assert spans[0].start == float(min(x))
        assert spans[-1].end == float(max(x))

    def test_width_property(self, sweep):
        x, idomain = sweep
        fig, ax = _axes(sweep)
        spans = plot_domains(ax, x, idomain)
        assert spans[0].width == pytest.approx(0.75)

    def test_a_figure_with_regions_renders(self, sweep, tmp_path):
        """End to end, through the package's own style and save helper."""
        from cfd_plot import plot_line, save_figure, style_context

        x, idomain = sweep
        with style_context("notebook"):
            fig, ax = plt.subplots()
            plot_line(ax, x, np.sin(x), label="CN")
            plot_domains(ax, x, idomain, domains={0: "Sub", 1: "Trans", 2: "Super"})
            written = save_figure(fig, tmp_path / "domains", formats=("png",))
        assert written[0].exists()


class DomainBands:
    """The hook documented in README §19 — module level, so it pickles.

    ``batch_plot`` silently drops to ``n_jobs=1`` when its hook cannot be
    pickled, so the README example being picklable is part of the contract.
    """

    def __init__(self, df, *, column="iDomain", domains=None):
        self.df, self.column, self.domains = df, column, domains

    def __call__(self, fig, ax, context):
        sub = self.df
        for key, value in {**context.flight_point, **context.fixed_sweeps}.items():
            sub = sub[sub[key] == value]
        x_col = context.x_spec["col_name"]
        sub = sub.sort_values(x_col)
        plot_domains(ax, sub[x_col], sub[self.column], domains=self.domains)


class TestInABatch:
    @staticmethod
    def _frame():
        rows = [
            {
                "Mach": mach,
                "Altitude_m": 5000.0,
                "alpha": float(alpha),
                "beta": 0.0,
                "DL": 0.0,
                "DM": 0.0,
                "DN": 0.0,
                "CN": 0.1 * alpha,
                "iDomain": 0 if alpha < 6 else (1 if alpha < 10 else 2),
            }
            for mach in (0.7, 0.85)
            for alpha in range(0, 13, 2)
        ]
        return pd.DataFrame(rows)

    def test_the_readme_hook_is_picklable(self):
        import pickle

        pickle.loads(pickle.dumps(DomainBands(self._frame(), domains={0: "Attached"})))

    def test_regions_reach_a_batch_figure(self, tmp_path):
        from cfd_plot import batch_plot

        frame = self._frame()
        hook = DomainBands(frame, domains={0: "Attached", 1: "Buffet", 2: "Stalled"})
        written = batch_plot(
            configuration_dict={"CFD": {"name": "CFD", "label": "CFD", "df": frame}},
            y_axis_dict={"CN": {"col_name": "CN", "y_save_name": "CN"}},
            sweep_dict={
                "alpha": {
                    "col_name": "alpha",
                    "x_save_name": "alpha",
                    "polar_prefix": "ALPHA_POLAR",
                }
            },
            flight_point_dict={
                key: {"values": [], "label": key, "save_name": key.upper()}
                for key in ("Mach", "Altitude_m", "beta", "DL", "DM", "DN")
            },
            output_base=tmp_path,
            formats=("png",),
            report=False,
            on_before_save=hook,
        )
        assert len(written) == 2
        assert all(path.exists() for path in written)
