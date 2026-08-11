"""Root finding and maximisation."""

from __future__ import annotations

import math

import pytest

from cfd_nozzle.core.numerics import find_root, maximise


def test_finds_a_simple_root() -> None:
    assert find_root(lambda x: x * x - 2.0, 0.0, 3.0) == pytest.approx(math.sqrt(2.0), rel=1e-12)


def test_returns_an_exact_bracket_end() -> None:
    assert find_root(lambda x: x - 1.0, 1.0, 5.0) == 1.0
    assert find_root(lambda x: x - 5.0, 1.0, 5.0) == 5.0


def test_requires_a_sign_change() -> None:
    with pytest.raises(ValueError, match="changement de signe"):
        find_root(lambda x: x * x + 1.0, -1.0, 1.0)


def test_handles_a_very_stiff_function() -> None:
    """The guarded secant must not stall where the derivative explodes."""
    root = find_root(lambda x: 1.0 / x - 1e6, 1e-9, 1.0)
    assert root == pytest.approx(1e-6, rel=1e-6)


def test_works_with_a_reversed_bracket() -> None:
    assert find_root(lambda x: x * x - 2.0, 3.0, 0.0) == pytest.approx(math.sqrt(2.0), rel=1e-9)


def test_finds_a_maximum() -> None:
    x, value = maximise(lambda t: -((t - 0.3) ** 2) + 5.0, -2.0, 2.0)
    assert x == pytest.approx(0.3, abs=1e-6)
    assert value == pytest.approx(5.0, abs=1e-9)


def test_finds_a_maximum_at_the_edge_of_the_range() -> None:
    x, _ = maximise(math.sin, 0.0, 0.5 * math.pi)
    assert x == pytest.approx(0.5 * math.pi, abs=1e-3)
