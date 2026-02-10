"""
mpl_template — Matplotlib figure template with style profiles and smart export.

Provides:
    use_style(profile)        — apply a style profile globally
    style_context(profile)    — context-manager for temporary style
    new_figure(...)           — wrapper around plt.subplots with profile support
    save_figure(...)          — export normal + optional "declassified" variant
    plot_line(ax, x, y, ...)  — line+marker plot with white-filled markers
    apply_marker_style(line)  — retrofit marker style on an existing Line2D

Profiles: "notebook", "slides", "paper"
"""

from __future__ import annotations

import copy
import logging
import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Literal, Sequence

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_STYLES_DIR = Path(__file__).resolve().parent / "styles"

_VALID_PROFILES = ("notebook", "slides", "paper")

DeclassifyAxis = Literal["x", "y", "both"]


# ---------------------------------------------------------------------------
# Style application
# ---------------------------------------------------------------------------

def _style_path(profile: str) -> str:
    """Return the absolute path to a .mplstyle file for *profile*."""
    if profile not in _VALID_PROFILES:
        raise ValueError(
            f"Unknown profile {profile!r}. Choose from {_VALID_PROFILES}."
        )
    path = _STYLES_DIR / f"{profile}.mplstyle"
    if not path.exists():
        raise FileNotFoundError(f"Style file not found: {path}")
    return str(path)


def use_style(profile: str = "notebook") -> None:
    """Apply a style profile **globally** (modifies rcParams in place).

    Parameters
    ----------
    profile : str
        One of ``"notebook"``, ``"slides"``, ``"paper"``.
    """
    mpl.style.use(_style_path(profile))


@contextmanager
def style_context(profile: str = "notebook"):
    """Temporarily apply a style profile (context manager).

    Usage::

        with style_context("slides"):
            fig, ax = plt.subplots()
            ...
    """
    with mpl.style.context(_style_path(profile)):
        yield


# ---------------------------------------------------------------------------
# Figure creation helper
# ---------------------------------------------------------------------------

def new_figure(
    nrows: int = 1,
    ncols: int = 1,
    *,
    profile: str | None = None,
    figsize: tuple[float, float] | None = None,
    **subplots_kw,
) -> tuple[Figure, any]:
    """Create a new figure (thin wrapper around ``plt.subplots``).

    Parameters
    ----------
    nrows, ncols : int
        Subplot grid dimensions.
    profile : str, optional
        If given, the style is applied via a context manager so only this
        figure inherits the profile settings.
    figsize : tuple, optional
        Override ``figsize`` from the profile.
    **subplots_kw
        Forwarded to ``plt.subplots``.

    Returns
    -------
    fig, axes
    """
    ctx = style_context(profile) if profile else _noop_context()
    with ctx:
        kw = dict(subplots_kw)
        if figsize is not None:
            kw["figsize"] = figsize
        fig, axes = plt.subplots(nrows, ncols, **kw)
    return fig, axes


@contextmanager
def _noop_context():
    yield


# ---------------------------------------------------------------------------
# Marker helpers
# ---------------------------------------------------------------------------

_MARKER_DEFAULTS = dict(
    marker="o",
    markerfacecolor="white",
    markeredgewidth=None,  # will be read from rcParams
)


def plot_line(
    ax,
    x,
    y,
    *,
    marker: str = "o",
    label: str | None = None,
    **kwargs,
) -> Line2D:
    """Plot a line with **white-filled markers** whose edge matches the line color.

    All extra *kwargs* are forwarded to ``ax.plot``.  The returned object is
    the ``Line2D`` instance.
    """
    # Let matplotlib pick the color from the cycle if not explicit
    (line,) = ax.plot(x, y, marker=marker, label=label, **kwargs)
    apply_marker_style(line)
    return line


def apply_marker_style(line: Line2D) -> None:
    """Set white face + edge-color matching the line color on *line*."""
    color = line.get_color()
    line.set_markerfacecolor("white")
    line.set_markeredgecolor(color)
    # Use rcParams markeredgewidth if not already overridden
    if line.get_markeredgewidth() == mpl.rcParams.get("lines.markeredgewidth", 1.0):
        pass  # already set by the style sheet — keep it
    # Ensure marker edge width is at least reasonable
    mew = line.get_markeredgewidth()
    if mew < 1.0:
        line.set_markeredgewidth(1.2)


# ---------------------------------------------------------------------------
# Declassify helpers (internal)
# ---------------------------------------------------------------------------

def _declassify_axes(
    fig: Figure,
    axes_to_modify: Literal["x", "y", "both"],
) -> dict:
    """Remove ticks + ticklabels on requested axes and add DECLASSIFIE stamp.

    Returns a *restore_info* dict that ``_restore_axes`` can use to undo
    everything.
    """
    restore = {"axes": [], "texts": []}

    for ax in fig.get_axes():
        info: dict = {"ax": ax}

        if axes_to_modify in ("x", "both"):
            info["xtick_params"] = {
                "labelbottom": True,
                "bottom": True,
            }
            info["xtick_labels"] = [t.get_text() for t in ax.get_xticklabels()]
            info["xtick_locs"] = list(ax.get_xticks())
            ax.tick_params(axis="x", which="both", bottom=False, labelbottom=False)

        if axes_to_modify in ("y", "both"):
            info["ytick_params"] = {
                "labelleft": True,
                "left": True,
            }
            info["ytick_labels"] = [t.get_text() for t in ax.get_yticklabels()]
            info["ytick_locs"] = list(ax.get_yticks())
            ax.tick_params(axis="y", which="both", left=False, labelleft=False)

        restore["axes"].append(info)

    # Stamp "DECLASSIFIE" in the bottom-left corner of the figure
    txt = fig.text(
        0.05,
        0.02,
        "DECLASSIFIE",
        fontsize=9,
        color="0.60",
        fontstyle="italic",
        fontweight="bold",
        ha="left",
        va="bottom",
        alpha=0.8,
    )
    restore["texts"].append(txt)

    return restore


def _restore_axes(fig: Figure, restore: dict) -> None:
    """Undo the changes made by ``_declassify_axes``."""
    for info in restore["axes"]:
        ax = info["ax"]
        if "xtick_params" in info:
            ax.tick_params(axis="x", which="both", bottom=True, labelbottom=True)
        if "ytick_params" in info:
            ax.tick_params(axis="y", which="both", left=True, labelleft=True)

    for txt in restore["texts"]:
        txt.remove()

    fig.canvas.draw_idle()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _inkscape_available() -> bool:
    return shutil.which("inkscape") is not None


def _convert_svg_to_emf(svg_path: Path, emf_path: Path) -> None:
    """Convert an SVG file to EMF using Inkscape."""
    try:
        subprocess.run(
            ["inkscape", str(svg_path), f"--export-filename={emf_path}"],
            check=True,
            capture_output=True,
        )
        logger.info("Converted %s -> %s", svg_path, emf_path)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        logger.warning("SVG->EMF conversion failed: %s", exc)


def save_figure(
    fig: Figure,
    path: str | Path,
    *,
    formats: Sequence[str] = ("png",),
    dpi: int | None = None,
    transparent: bool | None = None,
    declassify: DeclassifyAxis | None = None,
) -> list[Path]:
    """Save *fig* to disk, optionally producing a declassified variant.

    Parameters
    ----------
    fig : Figure
        The matplotlib figure to save.
    path : str or Path
        Base path **without extension** (e.g. ``"output/fig1"``).
        Directories are created automatically.
    formats : sequence of str
        File formats to export (``"png"``, ``"svg"``, ``"pdf"``, ``"emf"``).
        ``"emf"`` triggers an SVG intermediate + Inkscape conversion.
    dpi : int, optional
        Override DPI (otherwise uses the style's ``savefig.dpi``).
    transparent : bool, optional
        Override transparency.
    declassify : ``"x"`` | ``"y"`` | ``"both"`` | None
        If set, **also** export a second variant with ticks/ticklabels
        removed on the specified axis(es) and a ``DECLASSIFIE`` stamp
        in the bottom-left corner.

    Returns
    -------
    list of Path
        All files that were written.
    """
    base = Path(path)
    base.parent.mkdir(parents=True, exist_ok=True)

    save_kw: dict = {"bbox_inches": "tight"}
    if dpi is not None:
        save_kw["dpi"] = dpi
    if transparent is not None:
        save_kw["transparent"] = transparent

    written: list[Path] = []

    # ---- normal export ----------------------------------------------------
    for fmt in formats:
        if fmt == "emf":
            # Export SVG first, then convert
            svg_tmp = base.with_suffix(".svg")
            fig.savefig(svg_tmp, format="svg", **save_kw)
            emf_out = base.with_suffix(".emf")
            if _inkscape_available():
                _convert_svg_to_emf(svg_tmp, emf_out)
                written.append(emf_out)
            else:
                logger.warning(
                    "Inkscape not found — EMF export skipped.  SVG saved: %s",
                    svg_tmp,
                )
            written.append(svg_tmp)
        else:
            out = base.with_suffix(f".{fmt}")
            fig.savefig(out, format=fmt, **save_kw)
            written.append(out)

    # ---- declassified export ----------------------------------------------
    if declassify is not None:
        restore = _declassify_axes(fig, declassify)
        suffix_tag = {"x": "declass_x", "y": "declass_y", "both": "declass_xy"}[
            declassify
        ]
        declass_base = base.parent / f"{base.stem}_{suffix_tag}"

        for fmt in formats:
            if fmt == "emf":
                svg_tmp = declass_base.with_suffix(".svg")
                fig.savefig(svg_tmp, format="svg", **save_kw)
                emf_out = declass_base.with_suffix(".emf")
                if _inkscape_available():
                    _convert_svg_to_emf(svg_tmp, emf_out)
                    written.append(emf_out)
                written.append(svg_tmp)
            else:
                out = declass_base.with_suffix(f".{fmt}")
                fig.savefig(out, format=fmt, **save_kw)
                written.append(out)

        _restore_axes(fig, restore)

    return written
