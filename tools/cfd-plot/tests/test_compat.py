"""Tests for the version shims in ``cfd_plot._compat``.

The layout helpers exist for a Matplotlib older than the one ``pyproject.toml``
asks for — the situation on a cluster that *provides* Matplotlib. That version
cannot be installed here, so the legacy branch is exercised against stand-in
figures that expose the pre-3.6 API and nothing else.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest

import cfd_plot
from cfd_plot._compat import figure_disable_layout, figure_set_layout_pad


def _calls_the_engine_api(path: Path) -> bool:
    """Real calls only — a comment may name the API it is explaining."""
    return any(
        not line.lstrip().startswith("#")
        and any(call in line for call in (".get_layout_engine(", ".set_layout_engine("))
        for line in path.read_text().splitlines()
    )


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


class _LegacyFigure:
    """A Matplotlib < 3.6 figure: two flags, no layout-engine object."""

    def __init__(self, *, constrained: bool = False, tight: bool = False) -> None:
        self._constrained = constrained
        self._tight = tight
        self.calls: list[tuple[str, object]] = []

    def get_constrained_layout(self) -> bool:
        return self._constrained

    def get_tight_layout(self) -> bool:
        return self._tight

    def set_constrained_layout_pads(self, **kwargs: float) -> None:
        self.calls.append(("set_constrained_layout_pads", kwargs))

    def set_tight_layout(self, value: object) -> None:
        self.calls.append(("set_tight_layout", value))

    def set_constrained_layout(self, value: object) -> None:
        self.calls.append(("set_constrained_layout", value))


class TestFigureSetLayoutPad:
    def test_modern_figure_gets_the_padding(self):
        fig = plt.figure(layout="constrained")
        figure_set_layout_pad(fig, h_pad=0.42)
        assert fig.get_layout_engine().get()["h_pad"] == pytest.approx(0.42)

    def test_a_figure_without_an_engine_is_left_alone(self):
        """Hand-placed figures have no engine: padding them is a no-op, not a crash."""
        fig = plt.figure(layout="none")
        figure_set_layout_pad(fig, h_pad=0.42)
        assert fig.get_layout_engine() is None

    def test_legacy_constrained_figure(self):
        fig = _LegacyFigure(constrained=True)
        figure_set_layout_pad(fig, h_pad=0.42)
        assert fig.calls == [("set_constrained_layout_pads", {"h_pad": 0.42})]

    def test_legacy_tight_figure(self):
        fig = _LegacyFigure(tight=True)
        figure_set_layout_pad(fig, h_pad=0.42)
        assert fig.calls == [("set_tight_layout", {"h_pad": 0.42})]

    def test_legacy_figure_laid_out_by_hand(self):
        fig = _LegacyFigure()
        figure_set_layout_pad(fig, h_pad=0.42)
        assert fig.calls == []


class TestFigureDisableLayout:
    def test_modern_figure_stops_being_laid_out(self):
        fig = plt.figure(layout="constrained")
        figure_disable_layout(fig)
        engine = fig.get_layout_engine()
        # Matplotlib keeps a placeholder that executes nothing, to remember the
        # geometry the real engine had chosen.
        assert engine is None or type(engine).__name__ == "PlaceHolderLayoutEngine"

    def test_legacy_figure_gets_both_flags_cleared(self):
        fig = _LegacyFigure(constrained=True, tight=True)
        figure_disable_layout(fig)
        assert fig.calls == [
            ("set_constrained_layout", False),
            ("set_tight_layout", False),
        ]


class TestNoDirectLayoutEngineCalls:
    """The shim is only useful if nothing bypasses it.

    ``fig.get_layout_engine()`` in a rendering path is exactly the crash this
    module exists to prevent, and it only shows up on the old Matplotlib we
    cannot install in CI — so guard it at the source level instead.
    """

    def test_the_layout_engine_api_is_only_touched_in_compat(self):
        package = Path(cfd_plot.__file__).parent
        offenders = {
            path.relative_to(package).as_posix()
            for path in package.rglob("*.py")
            if path.name != "_compat.py" and _calls_the_engine_api(path)
        }
        assert offenders == set()
