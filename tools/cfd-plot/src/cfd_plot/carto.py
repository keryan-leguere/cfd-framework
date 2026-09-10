"""carto — maps of a quantity over a *pair* of sweep variables.

``batch_plot`` answers "how does CN vary with alpha?", one curve at a time.
Past two sweeps that stops scaling: a study over Mach × alpha × altitude is a
hundred polars, and the shape of ``CN(Mach, alpha)`` is spread across all of
them. A cartography puts that shape on one sheet.

    from cfd_plot import batch_carto

    batch_carto(
        configuration_dict=configuration_dict,   # one panel per source
        y_axis_dict=y_axis_dict,                 # one figure per quantity
        sweep_dict=sweep_dict,                   # one figure per PAIR of sweeps
        flight_point_dict=flight_point_dict,
        output_base="FIGURE",
    )

The loop is ``batch_plot``'s, one dimension wider: every **pair** of sweep
variables becomes a map, every *other* sweep is pinned as a directory level,
and flight points loop as usual. Inside one figure there is one **panel per
configuration** — the CFD, the model, the wind tunnel — drawn as filled
contours with black iso-lines labelled in place.

Reading a map honestly
----------------------
Panels of the same quantity from different sources share their colour scale by
default (``shared_scale=True``): the level *values* are computed once from the
combined range and handed to every panel, so a band means the same thing left
and right and one colorbar can describe them all. Independently levelled panels
would make two different fields look alike, which is the one thing a
side-by-side map exists to rule out.

That is also why the panels must then agree on ``cmap`` and on an explicit
``levels`` array: a single colorbar cannot describe two colormaps. Disagreeing
sources raise rather than produce a figure whose colorbar is wrong for half of
it. ``shared_scale=False`` is the way out — each panel then gets its own scale
*and* its own colorbar, and anything goes.

Overriding the look
-------------------
Defaults come from the ``carto=`` argument (a :class:`CartoSpec` or a plain
dict). A ``"CARTO"`` sub-dict overrides them, on a ``y_axis_dict`` entry (the
quantity: its colormap, its levels) and then on a ``configuration_dict`` entry
(that source's panel)::

    y_axis_dict = {
        "CN": {"col_name": "CN", "symbol": r"$C_N$", "unit": "-",
               "CARTO": {"cmap": "RdBu_r", "levels": 13}},
    }
    configuration_dict = {
        "CFD":   {"label": "CFD", "df": df_cfd},
        "MODEL": {"label": "Model", "df": df_model,
                  "CARTO": {"line_color": "0.2", "clabel": False}},
    }

``"CARTO"`` is metadata like ``df`` or ``label``: it never reaches
``plot_line``, so the same ``configuration_dict`` drives ``batch_plot`` and
``batch_carto`` unchanged.

What is not there
-----------------
A blank patch on a map is a question, and two very different facts produce
one. The cells the study never ran are outlined and hatched (``missing``); the
cells a table declares un-trimmable — an ``Equilibre`` column reading ``NON`` —
are dropped from the field and hatched under their own message
(``equilibre``, picked up on its own if the column is there). Neither is
interpolated over, and an un-trimmable cell leaves the colour scale and the
delta with it: a coefficient at a flight point that does not trim is not a
small value, it is not a value.

Titles
------
``panel_title``, ``suptitle`` and ``subtitle`` take a template or a callable.
A panel's template can name **any key of its ``configuration_dict`` entry**,
which is where the mass and the centre of gravity already live::

    carto = {"panel_title": "{label} — CDG {CDG} %, m={masse} kg",
             "suptitle": "{qoi_symbol} — {x} × {y}"}
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any, Union

import matplotlib.pyplot as plt
import numpy as np

from ._compat import zip_strict
from .batch import (
    BatchPlotContext,
    PdfReportArg,
    _cli_text,
    _coalesce_sweep_dict,
    _filter_df_by_context,
    _paths_for_formats,
    _prepare_flight_point_dict,
    _prepare_sweep_dict,
    _print_clean_report,
    _resolve_pdf_spec,
    _run_jobs,
    _subplot_grid_shape,
    build_output_path,
    format_axis_label,
    format_axis_title_label,
    format_flight_point_title_suffix,
    iter_flight_points,
    varying_flight_keys,
)
from .cleanup import clean_figure_dir
from .field2d import plot_contour, plot_contourf
from .mpl_template import (
    add_shared_colorbar,
    mathtext_safe,
    print_file_report,
    save_figure,
    set_suptitle,
    set_title,
    use_style,
)
from .prep import dataframe_to_grid

__all__ = [
    "CARTO_KEY",
    "CartoSpec",
    "DeltaSpec",
    "EquilibreSpec",
    "RegionSpec",
    "batch_carto",
]

#: Key of the override sub-dict, in a ``y_axis_dict`` or ``configuration_dict``
#: entry. Also listed in ``batch._CONFIG_METADATA_KEYS`` so it never reaches
#: ``plot_line``.
CARTO_KEY = "CARTO"

# Maps are squarer than curves and carry a colorbar; the default figsize is
# sized for one wide curve panel.
_CARTO_PANEL_SIZE_FACTOR = (0.95, 1.05)

# Behind the field, not over it. ``contourf`` sits at zorder 1 and its
# iso-lines at 2, so a zone drawn above them would hatch over data that a
# neighbouring source *does* hold on a shared-axes panel — and the hatching is
# the least important thing on the sheet. It stays visible because the cells it
# covers are exactly the ones the field leaves blank.
_ZONE_ZORDER = 0.4

# The message is the exception: it is the one thing on the zone that has to be
# read, it covers a few characters, and half of it under a neighbouring panel's
# fill would be worse than useless.
_ZONE_MESSAGE_ZORDER = 4.0

# 'level' is the spelling that comes to mind at the call site (and the one
# Matplotlib does *not* use). Accepted, mapped, documented — a silent no-op
# would be the worst of the three options.
_CARTO_ALIASES = {"level": "levels", "line_level": "line_levels"}


#: A title: a ``str.format`` template over the figure's fields, or a callable
#: taking that mapping. See :class:`CartoSpec`.
TitleArg = Union[str, Callable[[Mapping[str, Any]], str], None]


def _check_title(value: TitleArg, where: str) -> None:
    if value is None or isinstance(value, str) or callable(value):
        return
    raise TypeError(
        f"{where} must be a format string, a callable or None, "
        f"got {type(value).__name__}."
    )


def _check_resample(value: int | tuple[int, int] | None) -> None:
    if value is None:
        return
    counts = (value,) if isinstance(value, int) and not isinstance(value, bool) else value
    if not isinstance(counts, (tuple, list)) or len(counts) not in (1, 2):
        raise TypeError(
            f"DeltaSpec.resample must be an int or (nx, ny), got {value!r}."
        )
    for count in counts:
        if not isinstance(count, int) or isinstance(count, bool) or count < 2:
            raise ValueError(
                f"DeltaSpec.resample counts must be ints >= 2, got {value!r}."
            )


@dataclass(frozen=True)
class RegionSpec:
    """A zone drawn *instead of* the field: hatching, outline, one message.

    Two of these live on a :class:`CartoSpec`. ``missing`` covers the cells the
    study never ran; ``equilibre`` (an :class:`EquilibreSpec`) covers the ones a
    column in the table declares invalid. Both look the same on purpose — a
    blank patch on a map is a question, and the hatching plus the outline
    answers it before the reader starts inventing a reason.

    Parameters
    ----------
    hatch :
        Matplotlib hatch pattern. Repeat a character to densify it (``"///"``).
    color :
        Hatching *and* outline. The outline is what actually delimits the zone;
        the hatching only says "not a hole in the drawing".
    facecolor :
        Wash under the hatching, or ``None`` to leave the background showing.
    linewidth :
        Outline width, in points.
    message :
        Written inside the zone, in a small white box. ``None`` draws none.
    fontsize :
        ``None`` follows the style, one notch below body text.
    min_area :
        Fraction of the panel's cells below which the zone gets no message —
        text wider than the zone it names reads as text about its neighbour.
        The hatching and the legend entry still appear.
    legend :
        Add a proxy patch to a small legend on the panel, so a zone too small
        for its message is still named somewhere.
    """

    hatch: str = "//"
    color: str = "0.35"
    facecolor: str | None = "white"
    linewidth: float = 0.8
    message: str | None = None
    fontsize: float | None = None
    min_area: float = 0.02
    legend: bool = False

    def __post_init__(self) -> None:
        if not self.hatch:
            raise ValueError("RegionSpec.hatch must be a Matplotlib hatch pattern.")
        if not 0.0 <= self.min_area <= 1.0:
            raise ValueError(
                f"RegionSpec.min_area is a fraction of the panel, got {self.min_area}."
            )


@dataclass(frozen=True)
class EquilibreSpec(RegionSpec):
    """The zone a table declares un-trimmable, read from a column of its own.

    Picked up **automatically**: if the configuration's table carries the
    column, every cell whose value is one of *ko_values* is hatched and its
    quantity is dropped — ``NaN`` before anything else looks at the field, so
    those cells leave the colour scale, the shared levels and the delta with
    it. A coefficient at a flight point that does not trim is not a small
    value, it is not a value.

    Parameters
    ----------
    column :
        Column to read. Absent from a table, the feature stays off for it.
    ok_values, ko_values :
        Compared case-insensitively on the stripped text, so ``"oui "`` and
        ``True`` and ``1`` all read as ``"OUI"``. An empty cell means "not
        assessed" and is drawn normally; anything else raises, naming the
        value — a house spelling silently hatched is worse than a refusal.
    """

    message: str | None = "non équilibrable"
    column: str = "Equilibre"
    ok_values: tuple[str, ...] = ("OUI", "YES", "O", "Y", "TRUE", "1")
    ko_values: tuple[str, ...] = ("NON", "NO", "N", "FALSE", "0")

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.column:
            raise ValueError("EquilibreSpec.column must name a column.")
        overlap = {value.strip().upper() for value in self.ok_values} & {
            value.strip().upper() for value in self.ko_values
        }
        if overlap:
            raise ValueError(
                f"EquilibreSpec: {sorted(overlap)} is in both ok_values and ko_values."
            )


#: Discreet by default: the cells nobody ran get an outline and a thin hatch,
#: not a slab of colour competing with the field next to it.
_DEFAULT_MISSING = RegionSpec(
    hatch="\\\\", color="0.55", facecolor=None, linewidth=0.7, message=None
)
_DEFAULT_EQUILIBRE = EquilibreSpec()


@dataclass(frozen=True)
class DeltaSpec:
    """The extra panel comparing two configurations, ``conf2 - conf1``.

    The reference is the **first** entry of ``configuration_dict``, by
    convention, so the sign reads "what the second one adds".

    A delta is a diverging quantity around zero, and that drives every default
    here: a diverging colormap, a scale centred on zero and symmetric by
    construction, and an odd number of level boundaries so one of them falls
    *exactly* on zero. Get any of those wrong and the neutral colour stops
    meaning "no difference" — a map where blue starts at +0.3 is worse than no
    map at all.

    Parameters
    ----------
    mode : {"absolute", "relative"}
        ``conf2 - conf1``, or ``100 x (conf2 - conf1) / conf1`` in percent.
    cmap :
        Diverging by default. A sequential map on a signed field hides the sign.
    levels :
        Level boundaries, or their count. **Keep it odd**: an even count puts
        zero in the middle of a band, so a whole neighbourhood of zero takes
        one side's colour.
    bound :
        Half-range of the colour scale: the map runs ``-bound .. +bound``.
        ``None`` (default) takes the largest absolute difference on the figure.
        Pin it to compare figures across a study — an auto bound rescales on
        every sheet, which makes a small difference look like a large one.
    line_levels, line_color, line_width, line_style, clabel, clabel_fmt,
    clabel_fontsize :
        Iso-lines and their labels, as in :class:`CartoSpec`. Solid by default
        here too — on a delta almost every level is negative, and Matplotlib
        would dash the lot. ``clabel_fmt``
        defaults to a signed format, ``"%+.3g"`` or ``"%+.1f%%"``.
    colorbar, label :
        Its own colorbar, with its own label — the delta scale has nothing to
        do with the field's. ``label=None`` derives one from the quantity.
    extend :
        ``None`` (default) means "both" when *bound* clips the data and
        "neither" otherwise.
    grid :
        ``"common"`` (default) interpolates both configurations onto one fine
        grid over the sweep range they share, then subtracts. ``"exact"``
        subtracts cell by cell and refuses two tables that were not run on the
        same grid.
    resample :
        Size of that common grid: one int for both axes, or ``(nx, ny)``.
        ``None`` (default) takes four times the finer of the two, bounded to
        81..321 points per axis — fine enough that the iso-lines read as
        curves, cheap enough to draw a study's worth of sheets.
    title :
        Panel title: a template (``"{other} vs {reference}"``) or a callable
        taking the field mapping. ``None`` names the subtraction in the order
        it reads. See :class:`CartoSpec`.
    """

    mode: str = "absolute"
    cmap: str = "RdBu_r"
    levels: int | tuple[float, ...] = 13
    bound: float | None = None
    line_levels: int | tuple[float, ...] | None = None
    line_color: str | None = "black"
    line_width: float = 0.6
    line_style: str = "solid"
    clabel: bool = True
    clabel_fmt: str | None = None
    clabel_fontsize: float | None = None
    colorbar: bool = True
    label: str | None = None
    extend: str | None = None
    grid: str = "common"
    resample: int | tuple[int, int] | None = None
    title: TitleArg = None

    def __post_init__(self) -> None:
        if self.grid not in ("common", "exact"):
            raise ValueError(
                f"DeltaSpec.grid must be 'common' or 'exact', got {self.grid!r}."
            )
        _check_resample(self.resample)
        _check_title(self.title, "DeltaSpec.title")
        if self.mode not in ("absolute", "relative"):
            raise ValueError(
                f"DeltaSpec.mode must be 'absolute' or 'relative', got {self.mode!r}."
            )
        if isinstance(self.levels, int) and not isinstance(self.levels, bool):
            if self.levels < 2:
                raise ValueError(f"DeltaSpec.levels must be >= 2, got {self.levels}.")
        elif not isinstance(self.levels, (list, tuple, np.ndarray)):
            raise TypeError(
                f"DeltaSpec.levels must be an int or a sequence of values, "
                f"got {type(self.levels).__name__}."
            )
        if self.bound is not None and self.bound <= 0:
            raise ValueError(f"DeltaSpec.bound must be > 0, got {self.bound}.")
        if self.extend is not None and self.extend not in ("neither", "both", "min", "max"):
            raise ValueError(
                f"DeltaSpec.extend must be None, 'neither', 'both', 'min' or 'max', "
                f"got {self.extend!r}."
            )

    @property
    def resolved_extend(self) -> str:
        if self.extend is not None:
            return self.extend
        return "both" if self.bound is not None else "neither"

    @property
    def resolved_clabel_fmt(self) -> str:
        if self.clabel_fmt is not None:
            return self.clabel_fmt
        return "%+.1f%%" if self.mode == "relative" else "%+.3g"


@dataclass(frozen=True)
class CartoSpec:
    """How one cartography panel is drawn.

    Parameters
    ----------
    cmap :
        Colormap of the filled contours.
    levels :
        Number of level boundaries, or the explicit values. An int is turned
        into that many evenly spaced values across the shared range, so the
        bands are reproducible from one figure to the next — Matplotlib's own
        "nice round numbers" would differ per panel.
    line_levels :
        Levels of the black iso-lines. ``None`` (default) reuses the fill's, so
        a labelled line is exactly the edge of a colour band. An int or an
        explicit list draws fewer lines than bands, which is the readable
        choice past ~10 levels.
    line_color, line_width, line_style :
        Iso-line style. ``None`` as the colour drops the lines entirely.
        ``line_style`` is ``"solid"`` rather than Matplotlib's default, which
        dashes every *negative* level: on a signed field that halves the
        legibility of the lines to say what the colour already says.
    clabel, clabel_fmt, clabel_fontsize :
        In-place labels on the iso-lines (``ax.clabel``).
    colorbar :
        One colorbar for the figure when ``shared_scale`` is on, one per panel
        otherwise.
    shared_scale :
        Give every panel the same level values, computed from the combined
        range of all panels. See the module docstring.
    max_cols :
        Panels per row (1–3).
    extend :
        Colorbar arrows: ``"neither"``, ``"both"``, ``"min"``, ``"max"``.
    panel_size :
        ``(width, height)`` of one panel, in inches. ``None`` (default) scales
        the style's own figure size. Worth setting for a report: the default is
        cut for a wide curve panel, and a map usually wants to be squarer.
    aspect :
        Axes aspect. ``None`` (default) leaves it auto — a map over
        (Mach, alpha) has two unrelated units, and forcing ``"equal"`` would
        squash it to a sliver.
    delta :
        Add a third panel comparing the two configurations — see
        :class:`DeltaSpec`. A property of the *figure*, so it is read from
        ``carto=`` or a ``y_axis_dict`` entry, never from a source's own
        ``CARTO``.
    equilibre :
        How the cells a table declares un-trimmable are drawn — see
        :class:`EquilibreSpec`. ``True`` (default) uses it if the column is
        there; ``False`` ignores the column altogether.
    missing :
        How the cells the study never ran are drawn — see :class:`RegionSpec`.
        ``True`` (default) outlines and hatches them, ``False`` leaves them
        blank as they were.
    panel_title, suptitle, subtitle :
        Override the composed titles. Either a ``str.format`` template or a
        callable taking the mapping of available fields:

        ==================  ===================================================
        ``source``          configuration key (panel only)
        ``label``           its ``label`` (panel only)
        every other key     of that ``configuration_dict`` entry — ``{masse}``,
                            ``{CDG}`` — bar ``df``, ``style`` and ``CARTO``
        ``qoi``             quantity key, ``qoi_symbol``, ``qoi_label``,
                            ``qoi_unit``
        ``x``, ``y``        sweep symbols, with ``x_key`` and ``y_key``
        ``flight_point``    the formatted flight point, ``case`` the pinned
                            sweeps, ``context`` both
        the values          of the flight point and the pinned sweeps, by key
        ==================  ===================================================

        A field the mapping does not have is left as written, braces and all,
        so a LaTeX subscript survives a template and a typo shows up on the
        figure instead of taking the run down. ``verbose=True`` prints the
        first resolved heading, which is where to catch one.
    """

    cmap: str = "viridis"
    levels: int | tuple[float, ...] = 11
    line_levels: int | tuple[float, ...] | None = None
    line_color: str | None = "black"
    line_width: float = 0.6
    line_style: str = "solid"
    clabel: bool = True
    clabel_fmt: str = "%.3g"
    clabel_fontsize: float | None = None
    colorbar: bool = True
    shared_scale: bool = True
    max_cols: int = 3
    extend: str = "neither"
    aspect: str | float | None = None
    panel_size: tuple[float, float] | None = None
    delta: DeltaSpec | None = None
    equilibre: EquilibreSpec | Mapping[str, Any] | bool | None = True
    missing: RegionSpec | Mapping[str, Any] | bool | None = True
    panel_title: TitleArg = None
    suptitle: TitleArg = None
    subtitle: TitleArg = None

    def __post_init__(self) -> None:
        # Normalise here as well as in _override_spec: a CartoSpec built by
        # hand with a dict in one of these is otherwise a spec that only fails
        # once a figure is being drawn.
        object.__setattr__(
            self, "delta", _resolve_delta_arg(self.delta, where="CartoSpec.delta")
        )
        object.__setattr__(
            self,
            "equilibre",
            _resolve_region_arg(
                self.equilibre,
                cls=EquilibreSpec,
                default=_DEFAULT_EQUILIBRE,
                where="CartoSpec.equilibre",
            ),
        )
        object.__setattr__(
            self,
            "missing",
            _resolve_region_arg(
                self.missing,
                cls=RegionSpec,
                default=_DEFAULT_MISSING,
                where="CartoSpec.missing",
            ),
        )
        for name in ("panel_title", "suptitle", "subtitle"):
            _check_title(getattr(self, name), f"CartoSpec.{name}")
        for name, value in (("levels", self.levels), ("line_levels", self.line_levels)):
            if isinstance(value, int) and not isinstance(value, bool):
                if value < 2:
                    raise ValueError(f"CartoSpec.{name} must be >= 2, got {value}.")
            elif value is not None and not isinstance(value, (list, tuple, np.ndarray)):
                raise TypeError(
                    f"CartoSpec.{name} must be an int or a sequence of values, "
                    f"got {type(value).__name__}."
                )
        if self.panel_size is not None and (
            len(self.panel_size) != 2 or any(value <= 0 for value in self.panel_size)
        ):
            raise ValueError(
                f"CartoSpec.panel_size must be two positive inches, "
                f"got {self.panel_size!r}."
            )
        if self.max_cols < 1 or self.max_cols > 3:
            raise ValueError(f"CartoSpec.max_cols must be between 1 and 3, got {self.max_cols}.")
        if self.extend not in ("neither", "both", "min", "max"):
            raise ValueError(
                f"CartoSpec.extend must be 'neither', 'both', 'min' or 'max', "
                f"got {self.extend!r}."
            )

    @property
    def figure_keys(self) -> tuple[Any, ...]:
        """What every panel of one figure must agree on to share a colorbar."""
        return (self.cmap, _levels_key(self.levels))

    @property
    def resolved_equilibre(self) -> EquilibreSpec | None:
        """The spec after normalisation — ``__post_init__`` guarantees it."""
        value = self.equilibre
        return value if isinstance(value, EquilibreSpec) else None

    @property
    def resolved_missing(self) -> RegionSpec | None:
        value = self.missing
        return value if isinstance(value, RegionSpec) else None


CartoArg = Union[CartoSpec, Mapping[str, Any], None]
RegionArg = Union[RegionSpec, Mapping[str, Any], bool, None]
DeltaArg = Union[DeltaSpec, Mapping[str, Any], str, bool, None]


def _levels_key(levels: int | tuple[float, ...] | None) -> Any:
    """Hashable form of a *levels* value, for comparing two specs."""
    if levels is None or isinstance(levels, int):
        return levels
    return tuple(float(value) for value in levels)


def _spec_field_names() -> tuple[str, ...]:
    return tuple(field.name for field in fields(CartoSpec))


def _resolve_delta_arg(delta: DeltaArg, *, where: str) -> DeltaSpec | None:
    """``True`` / a mode string / a dict / a spec, all to a spec (or nothing)."""
    if delta is None or delta is False:
        return None
    if delta is True:
        return DeltaSpec()
    if isinstance(delta, DeltaSpec):
        return delta
    if isinstance(delta, str):
        return DeltaSpec(mode=delta)
    if isinstance(delta, Mapping):
        known = tuple(field.name for field in fields(DeltaSpec))
        resolved: dict[str, Any] = {}
        for key, value in delta.items():
            name = _CARTO_ALIASES.get(key, key)
            if name not in known:
                raise ValueError(
                    f"unknown delta key {key!r} in {where}; expected one of {list(known)}."
                )
            resolved[name] = (
                tuple(value)
                if name in ("levels", "line_levels") and isinstance(value, (list, np.ndarray))
                else value
            )
        return DeltaSpec(**resolved)
    raise TypeError(
        f"delta in {where} must be a bool, a mode string, a dict or a DeltaSpec, "
        f"got {type(delta).__name__}."
    )


def _resolve_region_arg(
    value: Any, *, cls: type, default: RegionSpec, where: str
) -> RegionSpec | None:
    """``True`` / ``False`` / a dict / a spec, all to a spec (or nothing)."""
    if value is None or value is False:
        return None
    if value is True:
        return default
    if isinstance(value, cls):
        assert isinstance(value, RegionSpec)
        return value
    if isinstance(value, Mapping):
        known = tuple(field.name for field in fields(cls))
        unknown = [key for key in value if key not in known]
        if unknown:
            raise ValueError(
                f"unknown {cls.__name__} key(s) {unknown} in {where}; "
                f"expected one of {list(known)}."
            )
        # Merged onto the default rather than onto a bare spec, so overriding
        # one key keeps the tuned look of the rest.
        return replace(default, **dict(value))
    raise TypeError(
        f"{where} must be a bool, a dict or a {cls.__name__}, "
        f"got {type(value).__name__}."
    )


def _override_spec(base: CartoSpec, overrides: Mapping[str, Any], *, where: str) -> CartoSpec:
    """Apply one ``CARTO`` sub-dict on top of *base*."""
    known = _spec_field_names()
    resolved: dict[str, Any] = {}
    for key, value in overrides.items():
        name = _CARTO_ALIASES.get(key, key)
        if name not in known:
            raise ValueError(
                f"unknown CARTO key {key!r} in {where}; expected one of {list(known)}."
            )
        if name == "delta":
            resolved[name] = _resolve_delta_arg(value, where=where)
            continue
        if name in ("equilibre", "missing"):
            spec_cls = EquilibreSpec if name == "equilibre" else RegionSpec
            fallback = _DEFAULT_EQUILIBRE if name == "equilibre" else _DEFAULT_MISSING
            resolved[name] = _resolve_region_arg(
                value, cls=spec_cls, default=fallback, where=f"{where} {CARTO_KEY}[{name!r}]"
            )
            continue
        resolved[name] = tuple(value) if name in ("levels", "line_levels") and isinstance(
            value, (list, np.ndarray)
        ) else value
    return replace(base, **resolved)


def _resolve_carto_arg(carto: CartoArg) -> CartoSpec:
    if carto is None:
        return CartoSpec()
    if isinstance(carto, CartoSpec):
        return carto
    if isinstance(carto, Mapping):
        return _override_spec(CartoSpec(), carto, where="carto=")
    raise TypeError(
        f"carto must be a CartoSpec, a dict or None, got {type(carto).__name__}."
    )


def _panel_spec(base: CartoSpec, entry: Mapping[str, Any], *, where: str) -> CartoSpec:
    """One source's spec — everything but the figure-level delta.

    Silently ignoring a ``delta`` written on a source would leave the user
    staring at a figure that does not have the panel they asked for.
    """
    overrides = entry.get(CARTO_KEY)
    if isinstance(overrides, Mapping) and "delta" in overrides:
        raise ValueError(
            f"{where}: 'delta' is a property of the figure, not of one panel — "
            "the extra panel compares the two configurations, so neither owns it. "
            "Put it on carto= or on the y_axis_dict entry."
        )
    return _spec_for(base, entry, where=where)


def _spec_for(base: CartoSpec, entry: Mapping[str, Any], *, where: str) -> CartoSpec:
    overrides = entry.get(CARTO_KEY)
    if overrides is None:
        return base
    if not isinstance(overrides, Mapping):
        raise TypeError(
            f"{CARTO_KEY!r} in {where} must be a dict of options, "
            f"got {type(overrides).__name__}."
        )
    return _override_spec(base, overrides, where=where)


# ---------------------------------------------------------------------------
# Titles
# ---------------------------------------------------------------------------

#: Never offered to a title template: the table itself, and the two sub-dicts
#: that are settings rather than facts about the configuration.
_TITLE_SKIP_KEYS = frozenset({"df", "style", CARTO_KEY})


class _TitleFields(dict[str, Any]):
    """A mapping that leaves an unknown field alone instead of raising.

    Two reasons, both learned from real templates: ``$\alpha_{max}$`` is a
    perfectly good thing to put in a heading and ``str.format`` would read
    ``{max}`` as a field, and a typo in ``{masse}`` should cost one wrong
    heading, not two hundred figures that never got written.
    """

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _resolve_title(
    template: TitleArg, fields: Mapping[str, Any], default: str, *, where: str = "title"
) -> str:
    if template is None:
        return default
    if callable(template):
        return str(template(dict(fields)))
    if isinstance(template, str):
        return template.format_map(_TitleFields(fields))
    raise TypeError(
        f"{where} must be a format string, a callable or None, "
        f"got {type(template).__name__}."
    )


def _figure_fields(
    *,
    qoi_key: str,
    qoi_spec: Mapping[str, Any],
    x_key: str,
    x_spec: Mapping[str, Any],
    y_key: str,
    y_spec: Mapping[str, Any],
    flight_point: Mapping[str, float],
    fixed_sweeps: Mapping[str, float],
    flight_point_label: str,
    case_label: str,
    context: str,
) -> dict[str, Any]:
    """What a title template of this figure can name."""
    return {
        "qoi": qoi_key,
        "qoi_symbol": format_axis_title_label(dict(qoi_spec), qoi_key),
        "qoi_label": format_axis_label(dict(qoi_spec), qoi_key),
        "qoi_unit": qoi_spec.get("unit", ""),
        "x": format_axis_title_label(dict(x_spec), x_key),
        "y": format_axis_title_label(dict(y_spec), y_key),
        "x_key": x_key,
        "y_key": y_key,
        "flight_point": flight_point_label,
        "case": case_label,
        "context": context,
        **dict(flight_point),
        **dict(fixed_sweeps),
    }


def _panel_fields(
    fields: Mapping[str, Any], source: str, config: Mapping[str, Any]
) -> dict[str, Any]:
    """The figure's fields plus this configuration's own keys.

    Which is what makes ``"{label} — CDG {CDG} %"`` work with nothing else set
    up: ``masse``, ``CDG`` and the rest already live in the configuration entry,
    where ``batch_plot`` leaves them alone.
    """
    own = {key: value for key, value in config.items() if key not in _TITLE_SKIP_KEYS}
    return {
        **dict(fields),
        **own,
        "source": source,
        "label": str(config.get("label", source)),
    }


def _strip_titles(spec: CartoSpec) -> CartoSpec:
    """The same spec with its templates spent, so a job carries no callable."""
    delta = spec.delta
    if isinstance(delta, DeltaSpec) and delta.title is not None:
        delta = replace(delta, title=None)
    if (
        spec.panel_title is None
        and spec.suptitle is None
        and spec.subtitle is None
        and delta is spec.delta
    ):
        return spec
    return replace(
        spec, panel_title=None, suptitle=None, subtitle=None, delta=delta
    )


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CartoPanel:
    """One source's map, gridded and ready to draw."""

    source: str
    label: str
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    spec: CartoSpec
    #: The configuration's own ``label``, before any ``panel_title`` template.
    #: What the delta panel names itself with — a subtraction of two long
    #: titles is a heading nobody can read.
    short_label: str = ""
    equilibre_mask: np.ndarray | None = None

    @property
    def finite_range(self) -> tuple[float, float] | None:
        """Its extent, or ``None`` when nothing on it is a number."""
        finite = self.z[np.isfinite(self.z)]
        if finite.size == 0:
            return None
        return float(finite.min()), float(finite.max())

    @property
    def missing_mask(self) -> np.ndarray:
        """Cells with no value that are not accounted for by another zone."""
        hole = ~np.isfinite(self.z)
        if self.equilibre_mask is not None:
            hole &= ~self.equilibre_mask
        return hole


@dataclass(frozen=True)
class _DeltaPanel:
    """The difference between two configurations, gridded and ready to draw."""

    label: str
    reference: str
    other: str
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    spec: DeltaSpec
    cbar_label: str

    @property
    def half_range(self) -> float:
        """Largest absolute difference on the panel — the symmetric bound."""
        finite = self.z[np.isfinite(self.z)]
        if finite.size == 0:
            return 0.0
        return float(np.max(np.abs(finite)))


def _delta_field(
    reference: np.ndarray, other: np.ndarray, mode: str
) -> np.ndarray:
    """``conf2 - conf1``, absolute or in percent of the reference."""
    if mode == "absolute":
        return np.asarray(other - reference, dtype=float)
    # A percentage of nothing is not a number, and a huge one drawn next to a
    # real one would rescale the whole map. NaN leaves the cell blank instead.
    with np.errstate(divide="ignore", invalid="ignore"):
        relative = 100.0 * (other - reference) / reference
    return np.where(reference == 0.0, np.nan, relative)


def _delta_labels(
    spec: DeltaSpec,
    reference: _CartoPanel,
    other: _CartoPanel,
    qoi_spec: Mapping[str, Any],
    qoi_key: str,
) -> tuple[str, str]:
    """Panel title and colorbar label, in the order the subtraction reads."""
    symbol = format_axis_title_label(dict(qoi_spec), qoi_key)
    left, right = other.short_label, reference.short_label
    if spec.mode == "relative":
        title = f"({left} − {right}) / {right}"
        cbar = spec.label or f"Δ{symbol} / {symbol} (%)"
        return title, cbar
    title = f"{left} − {right}"
    unit = qoi_spec.get("unit")
    cbar = spec.label or (f"Δ{symbol} ({unit})" if unit else f"Δ{symbol}")
    return title, cbar


def _build_delta_panel(
    spec: DeltaSpec,
    panels: Sequence[_CartoPanel],
    qoi_spec: Mapping[str, Any],
    qoi_key: str,
    fields: Mapping[str, Any] | None = None,
) -> _DeltaPanel | None:
    """The third panel, when exactly two configurations are on this figure.

    A flight point where only one source ran has nothing to subtract; the
    figure is still valid, so it simply comes out with its one panel.
    """
    if len(panels) != 2:
        return None
    reference, other = panels

    if spec.grid == "exact":
        if not (
            np.array_equal(reference.x, other.x) and np.array_equal(reference.y, other.y)
        ):
            raise ValueError(
                f"cannot difference {other.source!r} against {reference.source!r} for "
                f"{qoi_key!r} with grid='exact': they were run on different grids "
                f"({reference.z.shape} vs {other.z.shape} over "
                f"x={reference.x.size}/{other.x.size}, "
                f"y={reference.y.size}/{other.y.size} points). Leave grid='common' "
                "to interpolate both onto one grid first, or drop the delta panel."
            )
        x_axis, y_axis = reference.x, reference.y
        z_reference, z_other = reference.z, other.z
    else:
        x_axis, y_axis, z_reference, z_other = _common_field(
            reference, other, spec, qoi_key
        )

    title, cbar_label = _delta_labels(spec, reference, other, qoi_spec, qoi_key)
    title = _resolve_title(
        spec.title,
        {
            **dict(fields or {}),
            "reference": reference.short_label,
            "other": other.short_label,
        },
        title,
        where="delta title",
    )
    return _DeltaPanel(
        label=title,
        reference=reference.source,
        other=other.source,
        x=x_axis,
        y=y_axis,
        z=_delta_field(z_reference, z_other, spec.mode),
        spec=replace(spec, title=None),
        cbar_label=cbar_label,
    )


def _resample_counts(spec: DeltaSpec) -> tuple[int | None, int | None]:
    if spec.resample is None:
        return None, None
    if isinstance(spec.resample, int):
        return spec.resample, spec.resample
    return spec.resample[0], spec.resample[1]


def _common_axis(
    first: np.ndarray,
    second: np.ndarray,
    count: int | None,
    *,
    name: str,
    sources: tuple[str, str],
) -> np.ndarray:
    """One axis of the fine grid the two configurations share.

    The **intersection** of their ranges, never the union: past the last point
    a table actually holds there is no value to interpolate, and extending the
    difference there would be inventing one.
    """
    for axis, source in zip_strict((first, second), sources):
        if axis.size < 2:
            raise ValueError(
                f"cannot interpolate configuration {source!r} along {name}: it holds "
                f"{axis.size} value(s) there, and a difference on a common grid needs "
                "at least two. Pin that sweep as a flight point, or use "
                "delta={'grid': 'exact'}."
            )
    low = max(float(first[0]), float(second[0]))
    high = min(float(first[-1]), float(second[-1]))
    if not high > low:
        raise ValueError(
            f"configurations {sources[0]!r} and {sources[1]!r} do not overlap along "
            f"{name}: [{first[0]:g}, {first[-1]:g}] against "
            f"[{second[0]:g}, {second[-1]:g}]. There is no domain to difference them on."
        )
    if count is None:
        # Fine enough that the iso-lines read as curves rather than as the
        # staircase of the coarser table, bounded so a study of sheets stays
        # cheap to draw.
        count = int(np.clip(4 * max(first.size, second.size), 81, 321))
    return np.linspace(low, high, count)


def _common_field(
    reference: _CartoPanel, other: _CartoPanel, spec: DeltaSpec, qoi_key: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Both maps interpolated onto one fine grid, ready to subtract."""
    nx, ny = _resample_counts(spec)
    sources = (reference.source, other.source)
    x_axis = _common_axis(reference.x, other.x, nx, name=f"the {qoi_key} x sweep", sources=sources)
    y_axis = _common_axis(reference.y, other.y, ny, name=f"the {qoi_key} y sweep", sources=sources)
    return (
        x_axis,
        y_axis,
        _resample_bilinear(reference.x, reference.y, reference.z, x_axis, y_axis),
        _resample_bilinear(other.x, other.y, other.z, x_axis, y_axis),
    )


def _resample_bilinear(
    x: np.ndarray, y: np.ndarray, z: np.ndarray, x_new: np.ndarray, y_new: np.ndarray
) -> np.ndarray:
    """Bilinear interpolation of a regular grid, in NumPy alone.

    Separable — along x, then along y — which is what bilinear *is* on a
    rectangular grid, and it keeps SciPy optional for the package.

    ``NaN`` spreads: a fine cell whose surrounding coarse values include a hole
    comes out a hole too. That is the honest answer — the alternative is a
    difference computed against a value nobody ran — and it is why a masked
    cell widens by one coarse cell on the delta panel.
    """
    along_x = np.empty((y.size, x_new.size), dtype=float)
    for row in range(y.size):
        along_x[row] = np.interp(x_new, x, z[row])

    out = np.empty((y_new.size, x_new.size), dtype=float)
    for col in range(x_new.size):
        out[:, col] = np.interp(y_new, y, along_x[:, col])
    return out


@dataclass(frozen=True)
class _CartoPlotJob:
    """One cartography figure: a quantity over a sweep pair, panel per source."""

    flight_point: dict[str, float]
    fixed_sweeps: dict[str, float]
    flight_point_keys: tuple[str, ...]
    sweep_x_key: str
    sweep_y_key: str
    qoi_key: str
    sweep_x_spec: dict[str, Any]
    sweep_y_spec: dict[str, Any]
    qoi_spec: dict[str, Any]
    polar_prefix: str
    output_path: Path
    suptitle: str
    subtitle: str
    flight_point_label: str
    case_label: str
    panels: tuple[_CartoPanel, ...]
    spec: CartoSpec
    delta: _DeltaPanel | None = None

    def cli_label(self) -> str:
        """Progress-bar description (``batch._any_job_label`` calls this)."""
        context = _cli_text(self.subtitle) or "all conditions"
        pair = f"{self.sweep_x_key} x {self.sweep_y_key}"
        return f"{self.polar_prefix} · carto · {context} · {self.qoi_key} over {pair}"

    def render(
        self,
        style_profile: str,
        formats: tuple[str, ...],
        on_before_save: Callable[[plt.Figure, plt.Axes, BatchPlotContext], None] | None,
        builder: Any = None,
    ) -> list[Path]:
        """Draw and export this figure (``batch._render_any`` calls this)."""
        return _render_one_carto_job(self, style_profile, formats, on_before_save, builder)


def _shared_levels(job: _CartoPlotJob) -> np.ndarray | None:
    """The level boundaries every panel shares, or ``None`` for per-panel levels."""
    spec = job.spec
    if not spec.shared_scale:
        return None
    if not isinstance(spec.levels, int) or isinstance(spec.levels, bool):
        return np.asarray(spec.levels, dtype=float)

    ranges = [panel.finite_range for panel in job.panels]
    known = [bounds for bounds in ranges if bounds is not None]
    if not known:
        # Every panel entirely masked or unrun: there is still a figure to
        # write — the hatching is the result — and contourf still wants levels.
        return np.linspace(0.0, 1.0, int(spec.levels))
    low = min(bounds[0] for bounds in known)
    high = max(bounds[1] for bounds in known)
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        # A quantity constant over the whole map is a real result (a model that
        # ignores one of the two sweeps), not an error. Give it a band to sit
        # in rather than handing Matplotlib non-increasing levels.
        span = max(abs(low), 1.0) * 1e-3
        low, high = low - span, high + span
    return np.linspace(low, high, int(spec.levels))


def _delta_levels(panel: _DeltaPanel) -> np.ndarray:
    """Level boundaries centred on zero, symmetric by construction.

    Symmetry is the whole point: with -bound..+bound and an odd number of
    boundaries, one lands exactly on zero and the diverging map's neutral
    colour means "no difference". An asymmetric scale would put neutral at
    some arbitrary non-zero value and quietly mislead every reader.
    """
    spec = panel.spec
    if not isinstance(spec.levels, int) or isinstance(spec.levels, bool):
        return np.asarray(spec.levels, dtype=float)
    bound = spec.bound if spec.bound is not None else panel.half_range
    if not np.isfinite(bound) or bound <= 0.0:
        # Two identical configurations: a flat zero everywhere is a result
        # worth showing, and Matplotlib still needs increasing levels.
        bound = 1.0
    return np.linspace(-bound, bound, int(spec.levels))


def _delta_line_levels(panel: _DeltaPanel, fill_levels: np.ndarray) -> Any:
    spec = panel.spec
    if spec.line_levels is None:
        return fill_levels
    if isinstance(spec.line_levels, int) and not isinstance(spec.line_levels, bool):
        return np.linspace(fill_levels[0], fill_levels[-1], spec.line_levels)
    return np.asarray(spec.line_levels, dtype=float)


def _draw_iso_lines(
    ax: Any,
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    *,
    levels: Any,
    color: str,
    width: float,
    style: str,
    clabel: bool,
    clabel_fmt: str,
    clabel_fontsize: float | None,
    aspect: str | float | None,
) -> None:
    """Black iso-lines over a filled map, labelled in place."""
    lines, _ = plot_contour(
        ax, x, y, z,
        levels=levels,
        colors=color,
        linewidths=width,
        linestyles=style,
        colorbar=False,
        aspect=aspect,
    )
    if clabel:
        kwargs: dict[str, Any] = {"fmt": clabel_fmt, "inline": True}
        if clabel_fontsize is not None:
            kwargs["fontsize"] = clabel_fontsize
        ax.clabel(lines, **kwargs)


def _line_levels(spec: CartoSpec, fill_levels: np.ndarray | int) -> Any:
    """Levels of the black iso-lines, defaulting to the fill's own."""
    if spec.line_levels is None:
        return fill_levels
    if isinstance(spec.line_levels, int) and not isinstance(spec.line_levels, bool):
        if isinstance(fill_levels, np.ndarray):
            return np.linspace(fill_levels[0], fill_levels[-1], spec.line_levels)
        return spec.line_levels
    return np.asarray(spec.line_levels, dtype=float)


def _mask_anchor(
    x: np.ndarray, y: np.ndarray, mask: np.ndarray
) -> tuple[float, float] | None:
    """A point *inside* the zone to hang its message on.

    The row holding the most flagged cells, then the middle of its longest
    unbroken run. A centroid would be quicker and would land outside any zone
    that is not convex — a ring of un-trimmable flight points around a solved
    core is exactly the shape this has to survive.
    """
    counts = mask.sum(axis=1)
    row = int(np.argmax(counts))
    if counts[row] == 0:
        return None

    best_start, best_len, start = 0, 0, None
    line = mask[row]
    for index in range(line.size + 1):
        inside = index < line.size and bool(line[index])
        if inside and start is None:
            start = index
        elif not inside and start is not None:
            if index - start > best_len:
                best_start, best_len = start, index - start
            start = None
    if best_len == 0:
        return None
    span = x[best_start : best_start + best_len]
    return float(0.5 * (span[0] + span[-1])), float(y[row])


def _region_quads(mask: np.ndarray) -> np.ndarray:
    """The grid cells the field does not cover, from a mask on its nodes.

    ``contourf`` fills a cell only when all four of its corners are numbers, so
    one flagged node blanks the four cells around it. Hatching the *nodes*
    instead — a contour at 0.5 — would cover half of each, leaving a white
    ring between the field and its own hatching. The cell is the unit here.
    """
    quads: np.ndarray = mask[:-1, :-1] | mask[1:, :-1] | mask[:-1, 1:] | mask[1:, 1:]
    return quads


def _region_path(x: np.ndarray, y: np.ndarray, quads: np.ndarray) -> Any:
    """One compound path over every flagged cell, so the hatch is continuous."""
    from matplotlib.path import Path

    rows, cols = np.nonzero(quads)
    x_low, x_high = x[cols], x[cols + 1]
    y_low, y_high = y[rows], y[rows + 1]

    verts = np.empty((rows.size * 5, 2), dtype=float)
    verts[0::5] = np.column_stack((x_low, y_low))
    verts[1::5] = np.column_stack((x_high, y_low))
    verts[2::5] = np.column_stack((x_high, y_high))
    verts[3::5] = np.column_stack((x_low, y_high))
    verts[4::5] = verts[0::5]
    codes = np.tile(
        [Path.MOVETO, Path.LINETO, Path.LINETO, Path.LINETO, Path.CLOSEPOLY],
        rows.size,
    )
    return Path(verts, codes)


def _region_boundary(
    x: np.ndarray, y: np.ndarray, quads: np.ndarray
) -> list[np.ndarray]:
    """Only the outer edges of the flagged cells — never the seams between them."""
    padded = np.pad(quads, 1, constant_values=False)
    sides = {
        "bottom": quads & ~padded[:-2, 1:-1],
        "top": quads & ~padded[2:, 1:-1],
        "left": quads & ~padded[1:-1, :-2],
        "right": quads & ~padded[1:-1, 2:],
    }
    segments: list[np.ndarray] = []
    for side, flags in sides.items():
        rows, cols = np.nonzero(flags)
        if rows.size == 0:
            continue
        x_low, x_high = x[cols], x[cols + 1]
        y_low, y_high = y[rows], y[rows + 1]
        if side == "bottom":
            starts, ends = (x_low, y_low), (x_high, y_low)
        elif side == "top":
            starts, ends = (x_low, y_high), (x_high, y_high)
        elif side == "left":
            starts, ends = (x_low, y_low), (x_low, y_high)
        else:
            starts, ends = (x_high, y_low), (x_high, y_high)
        segments.extend(
            np.array([[sx, sy], [ex, ey]])
            for sx, sy, ex, ey in zip_strict(starts[0], starts[1], ends[0], ends[1])
        )
    return segments


def _shade_region(
    ax: Any,
    x: np.ndarray,
    y: np.ndarray,
    mask: np.ndarray,
    spec: RegionSpec,
    *,
    legend_label: str,
    handles: list[Any],
) -> None:
    """Outline, hatch and name the cells the field does not cover."""
    if mask.size == 0 or not mask.any() or x.size < 2 or y.size < 2:
        return
    quads = _region_quads(mask)
    if not quads.any():
        return

    from matplotlib.collections import LineCollection
    from matplotlib.patches import Patch, PathPatch

    path = _region_path(x, y, quads)
    if spec.facecolor is not None:
        ax.add_patch(
            PathPatch(path, facecolor=spec.facecolor, linewidth=0.0, zorder=_ZONE_ZORDER)
        )
    # linewidth=0 on the hatched patch: the hatch still draws in the edge
    # colour, and nothing strokes the seams between neighbouring cells.
    ax.add_patch(
        PathPatch(
            path,
            facecolor="none",
            edgecolor=spec.color,
            hatch=spec.hatch,
            linewidth=0.0,
            zorder=_ZONE_ZORDER + 0.1,
        )
    )
    ax.add_collection(
        LineCollection(
            _region_boundary(x, y, quads),
            colors=spec.color,
            linewidths=spec.linewidth,
            zorder=_ZONE_ZORDER + 0.2,
        )
    )

    if spec.legend:
        handles.append(
            Patch(
                facecolor=spec.facecolor or "none",
                edgecolor=spec.color,
                hatch=spec.hatch,
                linewidth=spec.linewidth,
                label=mathtext_safe(legend_label),
            )
        )

    if not spec.message or float(quads.mean()) < spec.min_area:
        return
    anchor = _mask_anchor(_midpoints(x), _midpoints(y), quads)
    if anchor is None:
        return
    fontsize = spec.fontsize
    if fontsize is None:
        fontsize = float(plt.rcParams["font.size"]) * 0.9
    ax.text(
        anchor[0], anchor[1], mathtext_safe(spec.message),
        ha="center", va="center", fontsize=fontsize, color=spec.color, zorder=_ZONE_MESSAGE_ZORDER,
        bbox={
            "boxstyle": "round,pad=0.28",
            "facecolor": "white",
            "edgecolor": spec.color,
            "linewidth": 0.6,
            "alpha": 0.92,
        },
    )


def _midpoints(axis: np.ndarray) -> np.ndarray:
    return np.asarray(0.5 * (axis[:-1] + axis[1:]), dtype=float)


def _shade_panel_regions(ax: Any, panel: _CartoPanel) -> None:
    """Both zones of one field panel, in the order they must be read."""
    handles: list[Any] = []
    equilibre = panel.spec.resolved_equilibre
    if equilibre is not None and panel.equilibre_mask is not None:
        _shade_region(
            ax, panel.x, panel.y, panel.equilibre_mask, equilibre,
            legend_label=equilibre.message or "not balanced",
            handles=handles,
        )
    missing = panel.spec.resolved_missing
    if missing is not None:
        _shade_region(
            ax, panel.x, panel.y, panel.missing_mask, missing,
            legend_label=missing.message or "not computed",
            handles=handles,
        )
    if handles:
        ax.legend(
            handles=handles,
            loc="lower right",
            fontsize=float(plt.rcParams["font.size"]) * 0.8,
            framealpha=0.9,
        )


def _check_panels_agree(job: _CartoPlotJob) -> None:
    """Refuse a shared colorbar over panels it cannot describe."""
    if not job.spec.shared_scale or len(job.panels) < 2:
        return
    grouped: dict[tuple[Any, ...], list[str]] = {}
    for panel in job.panels:
        grouped.setdefault(panel.spec.figure_keys, []).append(panel.source)
    if len(grouped) > 1:
        disagreeing = " vs ".join(
            f"{sources} → cmap={keys[0]!r}, levels={keys[1]!r}"
            for keys, sources in grouped.items()
        )
        raise ValueError(
            f"cartography {job.output_path.name}: panels disagree on the colour "
            f"scale ({disagreeing}). One colorbar cannot describe two of them — "
            f"make the {CARTO_KEY!r} entries agree on 'cmap' and 'levels', or pass "
            "shared_scale=False to give each panel its own scale and colorbar."
        )


def _render_one_carto_job(
    job: _CartoPlotJob,
    style_profile: str,
    formats: tuple[str, ...],
    on_before_save: Callable[[plt.Figure, plt.Axes, BatchPlotContext], None] | None,
    builder: Any = None,
) -> list[Path]:
    """Render one cartography figure (safe for process workers)."""
    use_style(style_profile)
    _check_panels_agree(job)

    spec = job.spec
    n_fields = len(job.panels)
    n_panels = n_fields + (1 if job.delta is not None else 0)
    nrows, ncols = _subplot_grid_shape(n_panels, spec.max_cols)
    if spec.panel_size is not None:
        panel_w, panel_h = spec.panel_size
    else:
        base_w, base_h = plt.rcParams["figure.figsize"]
        width_factor, height_factor = _CARTO_PANEL_SIZE_FACTOR
        panel_w, panel_h = base_w * width_factor, base_h * height_factor
    fig, axes = plt.subplots(
        nrows,
        ncols,
        figsize=(panel_w * ncols, panel_h * nrows),
        squeeze=False,
    )
    axes_flat = list(axes.ravel())
    used_axes = axes_flat[:n_panels]
    field_axes = axes_flat[:n_fields]

    shared = _shared_levels(job)
    x_label = format_axis_label(job.sweep_x_spec, job.sweep_x_key)
    y_label = format_axis_label(job.sweep_y_spec, job.sweep_y_key)
    qoi_label = format_axis_label(job.qoi_spec, job.qoi_key)

    last_fill = None
    for ax, panel in zip_strict(field_axes, list(job.panels)):
        panel_spec = panel.spec
        fill_levels: Any = shared if shared is not None else panel_spec.levels
        fill, _ = plot_contourf(
            ax,
            panel.x,
            panel.y,
            panel.z,
            levels=fill_levels,
            cmap=panel_spec.cmap,
            colorbar=not spec.shared_scale and spec.colorbar,
            cbar_label=qoi_label,
            extend=panel_spec.extend,
            aspect=panel_spec.aspect,
        )
        last_fill = fill

        if panel_spec.line_color is not None:
            _draw_iso_lines(
                ax, panel.x, panel.y, panel.z,
                levels=_line_levels(panel_spec, fill_levels),
                color=panel_spec.line_color,
                width=panel_spec.line_width,
                style=panel_spec.line_style,
                clabel=panel_spec.clabel,
                clabel_fmt=panel_spec.clabel_fmt,
                clabel_fontsize=panel_spec.clabel_fontsize,
                aspect=panel_spec.aspect,
            )

        _shade_panel_regions(ax, panel)

        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        set_title(ax, mathtext_safe(panel.label))

    if job.delta is not None:
        _render_delta_panel(
            axes_flat[n_fields],
            job.delta,
            x_label,
            y_label,
            spec.aspect,
            missing=spec.resolved_missing,
        )

    for ax in axes_flat[n_panels:]:
        ax.set_visible(False)

    if spec.shared_scale and spec.colorbar and last_fill is not None:
        # match_axes=False keeps constrained_layout in charge: the manual
        # placement reads axes positions that the engine has not settled yet,
        # and every style profile here runs constrained.
        # ``ax=field_axes``, not every panel: the delta has its own scale and
        # its own bar, and letting this one span it would suggest they share.
        add_shared_colorbar(
            fig, last_fill, match_axes=False, label=qoi_label, ax=field_axes
        )

    panel_titlesize = float(plt.rcParams["axes.titlesize"])
    heading = f"{job.suptitle}\n{job.subtitle}" if job.subtitle else job.suptitle
    set_suptitle(
        fig, mathtext_safe(heading), fontsize=panel_titlesize * 1.25, fontweight="bold"
    )

    if on_before_save is not None:
        sources: list[str | None] = [panel.source for panel in job.panels]
        deltas: list[str | None] = [None] * n_fields
        if job.delta is not None:
            sources.append(None)
            deltas.append(job.delta.spec.mode)
        for index, (ax, source, delta_mode) in enumerate(
            zip_strict(used_axes, sources, deltas)
        ):
            on_before_save(
                fig,
                ax,
                BatchPlotContext(
                    flight_point=job.flight_point,
                    fixed_sweeps=job.fixed_sweeps,
                    sweep_key=job.sweep_x_key,
                    y_key=job.qoi_key,
                    x_spec=job.sweep_x_spec,
                    y_spec=job.qoi_spec,
                    polar_prefix=job.polar_prefix,
                    output_path=job.output_path,
                    panel_index=index,
                    carto_sweep_key=job.sweep_y_key,
                    carto_sweep_spec=job.sweep_y_spec,
                    carto_source=source,
                    carto_delta=delta_mode,
                ),
            )

    written = save_figure(fig, job.output_path, formats=formats)
    if builder is not None:
        builder.add(fig)
    plt.close(fig)
    return written


def _render_delta_panel(
    ax: Any,
    panel: _DeltaPanel,
    x_label: str,
    y_label: str,
    aspect: str | float | None,
    *,
    missing: RegionSpec | None = None,
) -> None:
    """Draw the difference panel: symmetric diverging fill, iso-lines, own bar."""
    spec = panel.spec
    levels = _delta_levels(panel)
    plot_contourf(
        ax,
        panel.x,
        panel.y,
        panel.z,
        levels=levels,
        cmap=spec.cmap,
        colorbar=spec.colorbar,
        cbar_label=mathtext_safe(panel.cbar_label),
        extend=spec.resolved_extend,
        aspect=aspect,
    )
    if spec.line_color is not None:
        _draw_iso_lines(
            ax, panel.x, panel.y, panel.z,
            levels=_delta_line_levels(panel, levels),
            color=spec.line_color,
            width=spec.line_width,
            style=spec.line_style,
            clabel=spec.clabel,
            clabel_fmt=spec.resolved_clabel_fmt,
            clabel_fontsize=spec.clabel_fontsize,
            aspect=aspect,
        )
    if missing is not None:
        # The holes here are wider than the sources' own: interpolation onto
        # the common grid cannot span a cell nobody ran.
        _shade_region(
            ax, panel.x, panel.y, ~np.isfinite(panel.z), missing,
            legend_label=missing.message or "not computed",
            handles=[],
        )
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    set_title(ax, mathtext_safe(panel.label))


# ---------------------------------------------------------------------------
# Enumeration
# ---------------------------------------------------------------------------


def _carto_prefix(x_spec: Mapping[str, Any], y_spec: Mapping[str, Any], x_key: str, y_key: str) -> str:
    """Top directory level of a pair, mirroring ``ALPHA_POLAR``."""
    x_save = str(x_spec.get("x_save_name", x_key)).upper()
    y_save = str(y_spec.get("x_save_name", y_key)).upper()
    return f"{x_save}_{y_save}_CARTO"


def _resolve_pairs(
    pairs: Sequence[tuple[str, str]] | None,
    sweep_keys: Sequence[str],
) -> list[tuple[str, str]]:
    """Which sweep pairs to map — every combination by default."""
    if pairs is None:
        if len(sweep_keys) < 2:
            raise ValueError(
                "batch_carto needs at least two sweep variables to make a map; "
                f"got {list(sweep_keys)}. Use batch_plot for a single sweep."
            )
        return list(itertools.combinations(sweep_keys, 2))

    resolved: list[tuple[str, str]] = []
    for pair in pairs:
        if len(pair) != 2:
            raise ValueError(f"each entry of pairs must be two sweep keys, got {pair!r}.")
        x_key, y_key = pair
        unknown = [key for key in pair if key not in sweep_keys]
        if unknown:
            raise KeyError(
                f"pairs entry {pair!r} names sweep keys not in sweep_dict: {unknown}."
            )
        if x_key == y_key:
            raise ValueError(f"pairs entry {pair!r} maps a sweep against itself.")
        resolved.append((x_key, y_key))
    return resolved


def _pad_axis(
    axis: np.ndarray, low: float, high: float
) -> tuple[np.ndarray, int, int]:
    """*axis* stretched to ``[low, high]``, and how many slots were added."""
    before = 1 if axis[0] > low else 0
    after = 1 if axis[-1] < high else 0
    if not (before or after):
        return axis, 0, 0
    parts = [np.array([low])] * before + [axis] + [np.array([high])] * after
    return np.concatenate(parts), before, after


def _align_panel_extents(panels: Sequence[_CartoPanel]) -> list[_CartoPanel]:
    """Give every panel of one figure the same axes, hatching what it lacks.

    A configuration run over a narrower sweep than its neighbour otherwise
    comes out as a *smaller* panel, and two maps of the same quantity that do
    not share their axes are the one thing a side-by-side sheet exists to rule
    out — the reader compares positions before values. Padding the short panel
    with empty rows puts the axes back in step and hands the gap to the same
    treatment as any other hole: outlined, hatched, named.

    Only when the missing zones are on. ``missing=False`` asked for the blanks
    to stay blank, and that includes this one.
    """
    if len(panels) < 2 or any(panel.spec.resolved_missing is None for panel in panels):
        return list(panels)

    x_low = min(float(panel.x[0]) for panel in panels)
    x_high = max(float(panel.x[-1]) for panel in panels)
    y_low = min(float(panel.y[0]) for panel in panels)
    y_high = max(float(panel.y[-1]) for panel in panels)

    padded: list[_CartoPanel] = []
    for panel in panels:
        x_axis, left, right = _pad_axis(panel.x, x_low, x_high)
        y_axis, below, above = _pad_axis(panel.y, y_low, y_high)
        if not (left or right or below or above):
            padded.append(panel)
            continue
        pad = ((below, above), (left, right))
        field = np.pad(panel.z, pad, constant_values=np.nan)
        mask = panel.equilibre_mask
        padded.append(
            replace(
                panel,
                x=x_axis,
                y=y_axis,
                z=field,
                equilibre_mask=(
                    None if mask is None else np.pad(mask, pad, constant_values=False)
                ),
            )
        )
    return padded


def _equilibre_mask(
    raw: np.ndarray, spec: EquilibreSpec, source: str
) -> np.ndarray:
    """Which gridded cells the table declares un-trimmable.

    An unexpected value raises rather than being taken for one side or the
    other: the whole point of the column is that the reader trusts the
    hatching, and ``"n"`` quietly read as "not assessed" would break that.
    """
    ok = {value.strip().upper() for value in spec.ok_values}
    ko = {value.strip().upper() for value in spec.ko_values}
    mask = np.zeros(raw.shape, dtype=bool)
    unknown: list[Any] = []

    for index, value in np.ndenumerate(np.asarray(raw, dtype=object)):
        if value is None:
            continue
        if isinstance(value, float) and np.isnan(value):
            continue
        if isinstance(value, (int, float, np.integer, np.floating)) and float(
            value
        ).is_integer():
            token = str(int(value))
        else:
            token = str(value).strip().upper()
        if token == "":
            continue
        if token in ko:
            mask[index] = True
        elif token not in ok:
            unknown.append(value)

    if unknown:
        seen = sorted({str(value) for value in unknown})
        raise ValueError(
            f"column {spec.column!r} of configuration {source!r} holds "
            f"{seen} — expected one of {sorted(ok)} (drawn) or {sorted(ko)} "
            f"(hatched), or an empty cell (not assessed). Extend "
            f"EquilibreSpec.ok_values / ko_values if that is your spelling."
        )
    return mask


def _grid_panel(
    source: str,
    config: Mapping[str, Any],
    *,
    label: str,
    flight_point: dict[str, float],
    fixed_sweeps: dict[str, float],
    flight_point_keys: Sequence[str],
    x_col: str,
    y_col: str,
    qoi_col: str,
    spec: CartoSpec,
) -> _CartoPanel | None:
    """Pivot one source's rows into a map, or ``None`` when it has none here."""
    context = {**flight_point, **fixed_sweeps}
    keys = list(flight_point_keys) + list(fixed_sweeps.keys())
    frame = _filter_df_by_context(config["df"], context, keys)
    if frame.empty:
        return None

    missing = [col for col in (x_col, y_col, qoi_col) if col not in frame.columns]
    if missing:
        raise KeyError(f"Columns {missing} not found in configuration {source!r}.")

    equilibre = spec.resolved_equilibre
    wants_equilibre = equilibre is not None and equilibre.column in frame.columns
    columns = [qoi_col, equilibre.column] if wants_equilibre and equilibre else [qoi_col]

    try:
        x_values, y_values, gridded = dataframe_to_grid(
            frame, x=x_col, y=y_col, values=columns
        )
    except ValueError as error:
        # The usual cause is a dimension nobody pinned: two rows share
        # (x, y) because they differ by a column that is in neither
        # sweep_dict nor flight_point_dict, so it never became a directory.
        raise ValueError(
            f"cannot grid {qoi_col!r} over ({x_col}, {y_col}) for configuration "
            f"{source!r} at {context or 'the whole table'}: {error} "
            "Every column that varies must appear in sweep_dict or "
            "flight_point_dict, or the map has several values per cell."
        ) from error

    field = np.asarray(gridded[qoi_col], dtype=float)

    mask: np.ndarray | None = None
    if wants_equilibre and equilibre is not None:
        mask = _equilibre_mask(gridded[equilibre.column], equilibre, source)
        if mask.any():
            # Dropped before anything measures the field, so an un-trimmable
            # cell leaves the colour scale and the delta with it.
            field = np.where(mask, np.nan, field)
        else:
            mask = None

    if not np.any(np.isfinite(field)) and mask is None:
        return None

    return _CartoPanel(
        source=source,
        label=label,
        short_label=str(config.get("label", source)),
        x=np.asarray(x_values, dtype=float),
        y=np.asarray(y_values, dtype=float),
        z=field,
        spec=spec,
        equilibre_mask=mask,
    )


def _enumerate_carto_jobs(
    *,
    configuration_dict: dict[str, dict[str, Any]],
    y_axis_dict: dict[str, dict[str, Any]],
    completed_sweeps: dict[str, dict[str, Any]],
    completed_flight_points: dict[str, dict[str, Any]],
    output_base: str | Path,
    base_spec: CartoSpec,
    pairs: Sequence[tuple[str, str]] | None,
    include_panel: Callable[..., bool] | None,
) -> list[_CartoPlotJob]:
    """Build one job per (sweep pair, flight point, pinned sweeps, quantity)."""
    sweep_keys = list(completed_sweeps.keys())
    flight_point_keys = list(completed_flight_points.keys())
    varying_fp_keys = varying_flight_keys(configuration_dict, flight_point_keys)
    varying_sw_keys = varying_flight_keys(configuration_dict, sweep_keys)
    jobs: list[_CartoPlotJob] = []

    for x_key, y_key in _resolve_pairs(pairs, sweep_keys):
        x_spec = completed_sweeps[x_key]
        y_spec = completed_sweeps[y_key]
        prefix = _carto_prefix(x_spec, y_spec, x_key, y_key)
        x_col = x_spec["col_name"]
        y_col = y_spec["col_name"]
        x_save = str(x_spec.get("x_save_name", x_key))
        y_save = str(y_spec.get("x_save_name", y_key))
        other_sweeps = [key for key in sweep_keys if key not in (x_key, y_key)]
        varying_other_sweeps = [key for key in other_sweeps if key in varying_sw_keys]

        for flight_point in iter_flight_points(
            configuration_dict, flight_point_keys, completed_flight_points
        ):
            for fixed_sweeps in iter_flight_points(
                configuration_dict, other_sweeps, completed_sweeps
            ):
                for qoi_key, qoi_spec in y_axis_dict.items():
                    qoi_col = qoi_spec.get("col_name", qoi_key)
                    qoi_save = qoi_spec.get("y_save_name", qoi_key)
                    figure_spec = _spec_for(
                        base_spec, qoi_spec, where=f"y_axis_dict[{qoi_key!r}]"
                    )

                    flight_point_label = format_flight_point_title_suffix(
                        flight_point, flight_point_keys, completed_flight_points
                    )
                    case_label = (
                        format_flight_point_title_suffix(
                            fixed_sweeps, list(fixed_sweeps.keys()), completed_sweeps
                        )
                        if fixed_sweeps
                        else ""
                    )
                    default_subtitle = ", ".join(
                        part for part in (flight_point_label, case_label) if part
                    )
                    default_suptitle = (
                        f"{format_axis_title_label(qoi_spec, qoi_key)} over "
                        f"{format_axis_title_label(x_spec, x_key)} × "
                        f"{format_axis_title_label(y_spec, y_key)}"
                    )
                    fields = _figure_fields(
                        qoi_key=qoi_key,
                        qoi_spec=qoi_spec,
                        x_key=x_key,
                        x_spec=x_spec,
                        y_key=y_key,
                        y_spec=y_spec,
                        flight_point=flight_point,
                        fixed_sweeps=fixed_sweeps,
                        flight_point_label=flight_point_label,
                        case_label=case_label,
                        context=default_subtitle,
                    )

                    panels: list[_CartoPanel] = []
                    for source, config in configuration_dict.items():
                        if include_panel is not None and not include_panel(
                            source, flight_point, (x_key, y_key), qoi_key, fixed_sweeps
                        ):
                            continue
                        panel_spec = _panel_spec(
                            figure_spec, config, where=f"configuration_dict[{source!r}]"
                        )
                        panel = _grid_panel(
                            source,
                            config,
                            label=_resolve_title(
                                panel_spec.panel_title,
                                _panel_fields(fields, source, config),
                                str(config.get("label", source)),
                                where=f"configuration_dict[{source!r}] panel_title",
                            ),
                            flight_point=flight_point,
                            fixed_sweeps=fixed_sweeps,
                            flight_point_keys=flight_point_keys,
                            x_col=x_col,
                            y_col=y_col,
                            qoi_col=qoi_col,
                            # Stripped: the titles are resolved here, in the
                            # parent, so a callable never has to cross into a
                            # worker — a lambda would drop the run to one core.
                            spec=_strip_titles(panel_spec),
                        )
                        if panel is not None:
                            panels.append(panel)
                    if not panels:
                        continue
                    delta_panel = (
                        _build_delta_panel(
                            figure_spec.delta, panels, qoi_spec, qoi_key, fields
                        )
                        if figure_spec.delta is not None
                        else None
                    )
                    # After the delta: it is built on what each source actually
                    # holds, and padding first would hand it two grids of NaN
                    # margins to intersect.
                    panels = _align_panel_extents(panels)

                    output_path = build_output_path(
                        output_base,
                        flight_point,
                        varying_fp_keys,
                        fixed_sweeps,
                        varying_other_sweeps,
                        prefix,
                        f"{x_save}_{y_save}",
                        qoi_save,
                        completed_flight_points,
                        completed_sweeps,
                    )
                    jobs.append(
                        _CartoPlotJob(
                            flight_point=flight_point,
                            fixed_sweeps=fixed_sweeps,
                            flight_point_keys=tuple(flight_point_keys),
                            sweep_x_key=x_key,
                            sweep_y_key=y_key,
                            qoi_key=qoi_key,
                            sweep_x_spec=x_spec,
                            sweep_y_spec=y_spec,
                            qoi_spec=qoi_spec,
                            polar_prefix=prefix,
                            output_path=output_path,
                            suptitle=_resolve_title(
                                figure_spec.suptitle,
                                fields,
                                default_suptitle,
                                where=f"y_axis_dict[{qoi_key!r}] suptitle",
                            ),
                            subtitle=_resolve_title(
                                figure_spec.subtitle,
                                fields,
                                default_subtitle,
                                where=f"y_axis_dict[{qoi_key!r}] subtitle",
                            ),
                            flight_point_label=flight_point_label,
                            case_label=case_label,
                            panels=tuple(panels),
                            spec=_strip_titles(figure_spec),
                            delta=delta_panel,
                        )
                    )
    return jobs


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def batch_carto(
    *,
    configuration_dict: dict[str, dict[str, Any]],
    y_axis_dict: dict[str, dict[str, Any]],
    sweep_dict: dict[str, dict[str, Any]] | None = None,
    x_axis_dict: dict[str, dict[str, Any]] | None = None,
    flight_point_dict: dict[str, Any] | None = None,
    output_base: str | Path,
    pairs: Sequence[tuple[str, str]] | None = None,
    carto: CartoArg = None,
    delta: DeltaArg = None,
    style_profile: str = "paper",
    formats: tuple[str, ...] = ("svg",),
    on_before_save: Callable[[plt.Figure, plt.Axes, BatchPlotContext], None] | None = None,
    include_panel: Callable[..., bool] | None = None,
    report: bool = True,
    verbose: bool = False,
    dry_run: bool = False,
    n_jobs: int = 1,
    pdf_report: PdfReportArg = None,
    clean: bool | str = False,
) -> list[Path]:
    """Map every quantity over every pair of sweep variables.

    One figure per (sweep pair, flight point, pinned sweeps, quantity), with one
    **panel per configuration** — filled contours, black iso-lines, labels in
    place. Every other sweep becomes a directory level, exactly as in
    :func:`~cfd_plot.batch_plot`.

    Output layout::

        output_base/ALPHA_MACH_CARTO/Z_8000/BETA_2/CN_vs_alpha_Mach.svg
        output_base/ALPHA_BETA_CARTO/Z_8000/MACH_0.8/CN_vs_alpha_beta.svg

    Parameters
    ----------
    configuration_dict, y_axis_dict, sweep_dict, x_axis_dict, flight_point_dict :
        The same four dictionaries :func:`~cfd_plot.batch_plot` takes, read the
        same way. ``sweep_dict`` needs at least two entries. A ``"CARTO"``
        sub-dict on a ``y_axis_dict`` or ``configuration_dict`` entry overrides
        the drawing options — see the module docstring.
    pairs :
        Which sweep pairs to map, e.g. ``[("alpha", "Mach")]``. Default: every
        combination, in ``sweep_dict`` order, first key on the horizontal axis.
    carto :
        Defaults for every panel: a :class:`CartoSpec` or a plain dict of the
        same keys.
    delta :
        Add a third panel with the difference between the two configurations,
        ``conf2 - conf1`` — the first entry of ``configuration_dict`` is the
        reference, by convention. ``True`` for the absolute difference,
        ``"relative"`` for a percentage of the reference, or a
        :class:`DeltaSpec` / dict to tune its own diverging scale. Only with
        exactly two configurations; a flight point where one of them did not
        run simply comes out without the panel. Both are interpolated onto one
        fine grid over the sweep range they share before being subtracted, so
        two tables run on different steps still compare —
        ``delta={"grid": "exact"}`` restores the cell-by-cell subtraction.
    include_panel :
        ``f(source, flight_point, (x_key, y_key), qoi_key, fixed_sweeps) -> bool``
        — the cartography analogue of ``batch_plot``'s ``include_curve``.
    on_before_save :
        Called once per panel with the panel's axes and a
        :class:`~cfd_plot.BatchPlotContext` whose ``carto_sweep_key`` /
        ``carto_sweep_spec`` describe the vertical sweep and whose
        ``carto_source`` names the configuration.
    report, verbose, dry_run, n_jobs, pdf_report, clean :
        As in :func:`~cfd_plot.batch_plot`.

    Notes
    -----
    Each source's rows are pivoted onto a grid, so a ``(x, y)`` cell that the
    study never ran comes out ``NaN``, is left blank rather than interpolated,
    and is outlined and hatched so the blank reads as an absence rather than as
    a drawing fault. Two rows landing in the same cell is an error naming the
    configuration: some column varies that is in neither ``sweep_dict`` nor
    ``flight_point_dict``, so it never became a directory.

    A table carrying an ``Equilibre`` column is read without being asked: every
    cell it marks ``NON`` is hatched under a "non équilibrable" message and
    dropped from the field — see :class:`EquilibreSpec`.
    """
    if not y_axis_dict:
        raise ValueError("y_axis_dict must contain at least one entry.")

    base_spec = _resolve_carto_arg(carto)
    if delta is not None and delta is not False:
        base_spec = replace(base_spec, delta=_resolve_delta_arg(delta, where="delta="))
    if base_spec.delta is not None and len(configuration_dict) != 2:
        raise ValueError(
            f"delta compares exactly two configurations, but configuration_dict has "
            f"{len(configuration_dict)}: {list(configuration_dict)}. Narrow it, or use "
            "include_panel to keep two per figure."
        )
    resolved_sweep_dict = _coalesce_sweep_dict(sweep_dict, x_axis_dict)
    if not resolved_sweep_dict:
        raise ValueError("Either sweep_dict or x_axis_dict must be provided.")

    completed_sweeps = _prepare_sweep_dict(
        configuration_dict, resolved_sweep_dict, flight_point_dict
    )
    completed_flight_points = _prepare_flight_point_dict(
        configuration_dict,
        flight_point_dict,
        list(resolved_sweep_dict.keys()),
    )

    jobs = _enumerate_carto_jobs(
        configuration_dict=configuration_dict,
        y_axis_dict=y_axis_dict,
        completed_sweeps=completed_sweeps,
        completed_flight_points=completed_flight_points,
        output_base=output_base,
        base_spec=base_spec,
        pairs=pairs,
        include_panel=include_panel,
    )

    if verbose:
        _print_carto_plan(
            configuration_dict=configuration_dict,
            y_axis_dict=y_axis_dict,
            completed_sweeps=completed_sweeps,
            completed_flight_points=completed_flight_points,
            jobs=jobs,
            output_base=output_base,
            formats=formats,
            style_profile=style_profile,
            spec=base_spec,
            n_jobs=n_jobs,
            dry_run=dry_run,
            clean=clean,
        )

    if clean:
        clean_report = clean_figure_dir(output_base, mode=clean, dry_run=dry_run)
        if verbose or report:
            _print_clean_report(clean_report)

    if dry_run:
        planned: list[Path] = []
        for job in jobs:
            planned.extend(_paths_for_formats(job.output_path, formats))
        if verbose:
            print(
                f"Dry run complete: {len(jobs)} cartography figure(s) → "
                f"{len(planned)} file(s) (nothing written)."
            )
        return planned

    spec = _resolve_pdf_spec(
        pdf_report, style_profile=style_profile, title=_carto_study_title(jobs)
    )
    written_paths = _run_jobs(
        jobs,
        style_profile=style_profile,
        formats=formats,
        on_before_save=on_before_save,
        n_jobs=n_jobs,
        verbose=verbose,
        pdf_spec=spec,
        pdf_summary=_carto_summary(jobs, formats),
    )
    if spec is not None and jobs:
        written_paths.append(Path(spec.path))

    if report and written_paths:
        print_file_report(written_paths, title="Cartographies")

    return written_paths


def _carto_study_title(jobs: Sequence[_CartoPlotJob]) -> str:
    prefixes = sorted({job.polar_prefix for job in jobs})
    if not prefixes:
        return "Cartographies"
    if len(prefixes) <= 3:
        return ", ".join(prefixes)
    return f"{len(prefixes)} cartographies"


def _carto_summary(
    jobs: Sequence[_CartoPlotJob], formats: Sequence[str]
) -> list[tuple[str, str]]:
    """Cover-page facts for a cartography run."""
    pairs = {f"{job.sweep_x_key} × {job.sweep_y_key}" for job in jobs}
    sources: set[str] = set()
    for job in jobs:
        sources.update(panel.label for panel in job.panels)
    rows = [("Cartographies", str(len(jobs))), ("Sweep pairs", ", ".join(sorted(pairs)))]
    if sources:
        rows.append(("Sources", ", ".join(sorted(sources))))
    if formats:
        rows.append(("Also exported", ", ".join(formats)))
    return rows


def _delta_note(spec: CartoSpec, configuration_dict: Mapping[str, Any]) -> str:
    """Which subtraction the plan is about to draw, in the order it reads."""
    if spec.delta is None:
        return "no"
    sources = list(configuration_dict)
    if len(sources) == 2:
        subtraction = f"{sources[1]} - {sources[0]}"
    else:
        subtraction = "needs exactly two configurations"
    return f"{spec.delta.mode} ({subtraction})"


def _zone_note(spec: CartoSpec) -> str:
    """What the plan will do with the blanks."""
    parts = []
    equilibre = spec.resolved_equilibre
    parts.append(
        f"column {equilibre.column!r} where a table has it"
        if equilibre
        else "equilibre off"
    )
    parts.append("holes outlined" if spec.resolved_missing else "holes left blank")
    return ", ".join(parts)


def _first_heading(jobs: Sequence[_CartoPlotJob]) -> str:
    if not jobs:
        return "none"
    job = jobs[0]
    panels = " | ".join(panel.label for panel in job.panels)
    heading = job.suptitle if not job.subtitle else f"{job.suptitle} / {job.subtitle}"
    return f"{heading}   [{panels}]"


def _print_carto_plan(
    *,
    configuration_dict: dict[str, dict[str, Any]],
    y_axis_dict: dict[str, dict[str, Any]],
    completed_sweeps: dict[str, dict[str, Any]],
    completed_flight_points: dict[str, dict[str, Any]],
    jobs: Sequence[_CartoPlotJob],
    output_base: str | Path,
    formats: Sequence[str],
    style_profile: str,
    spec: CartoSpec,
    n_jobs: int,
    dry_run: bool,
    clean: bool | str,
) -> None:
    """Print what the run will do — pairs, panels, files."""
    from . import batch as _batch

    pairs = sorted({f"{job.sweep_x_key} × {job.sweep_y_key}" for job in jobs})
    panels = sum(len(job.panels) for job in jobs)
    lines = [
        f"Sources      : {', '.join(configuration_dict)}  ({len(configuration_dict)})",
        f"Quantities   : {', '.join(y_axis_dict)}  ({len(y_axis_dict)})",
        f"Sweeps       : {', '.join(completed_sweeps)}  ({len(completed_sweeps)})",
        f"Sweep pairs  : {', '.join(pairs) if pairs else 'none'}",
        f"Flight params: {', '.join(completed_flight_points)}"
        f"  ({len(completed_flight_points)})",
        f"Output base  : {output_base}",
        f"Formats      : {', '.join(formats)}",
        f"Style        : {style_profile}",
        f"Mode         : {'dry-run (no files written)' if dry_run else 'write'}",
        f"Colour scale : {'shared across panels' if spec.shared_scale else 'per panel'}"
        f", cmap={spec.cmap}, levels={spec.levels}  (defaults)",
        "Delta panel  : " + _delta_note(spec, configuration_dict),
        "Zones        : " + _zone_note(spec),
        # The resolved heading, because a template typo is invisible until a
        # figure is open and the run is over.
        f"First heading: {_first_heading(jobs)}",
        f"Parallel     : {'sequential (n_jobs=1)' if n_jobs == 1 else f'{n_jobs} workers'}",
        f"Clean        : {_batch._clean_note(clean)}",
        f"Figures      : {len(jobs)}  ({panels} panels)  →  "
        f"{len(jobs) * len(formats)} file(s)",
    ]
    overriding = [
        f"y_axis_dict[{key!r}]" for key, entry in y_axis_dict.items() if CARTO_KEY in entry
    ] + [
        f"configuration_dict[{key!r}]"
        for key, entry in configuration_dict.items()
        if CARTO_KEY in entry
    ]
    if overriding:
        # Without this the "defaults" line above reads as what was drawn, and a
        # CARTO override is invisible until you open the figure.
        lines.insert(-1, f"{CARTO_KEY} overrides: {', '.join(overriding)}")
    if _batch._RICH and _batch._console is not None and _batch.Panel is not None:
        _batch._console.print(
            _batch.Panel("\n".join(lines), title="Cartography plan", border_style="cyan")
        )
        return
    print("=== Cartography plan ===")
    for line in lines:
        print(line)
