"""Contour generation: conical and Rao bell."""

from __future__ import annotations

import math

import numpy as np
import pytest

from cfd_nozzle.core.geometry import bell_contour, conical_contour, rao_angles


@pytest.mark.parametrize("area_ratio", [2.0, 8.0, 16.0, 50.0])
def test_conical_contour_reaches_the_requested_area_ratio(area_ratio: float) -> None:
    contour = conical_contour(0.05, area_ratio)
    assert contour.area_ratio == pytest.approx(area_ratio, rel=1e-6)
    assert contour.throat_radius == pytest.approx(0.05, rel=1e-9)


@pytest.mark.parametrize("area_ratio", [2.0, 8.0, 16.0, 50.0])
def test_bell_contour_reaches_the_requested_area_ratio(area_ratio: float) -> None:
    contour = bell_contour(0.05, area_ratio)
    assert contour.area_ratio == pytest.approx(area_ratio, rel=1e-6)


@pytest.mark.parametrize("half_angle", [10.0, 15.0, 20.0])
def test_conical_divergence_loss(half_angle: float) -> None:
    contour = conical_contour(0.05, 16.0, half_angle)
    expected = 0.5 * (1.0 + math.cos(math.radians(half_angle)))
    assert contour.divergence_lambda == pytest.approx(expected)
    assert 0.9 < contour.divergence_lambda < 1.0


def test_opening_the_cone_shortens_it_and_costs_efficiency() -> None:
    narrow = conical_contour(0.05, 16.0, 10.0)
    wide = conical_contour(0.05, 16.0, 25.0)
    assert wide.divergent_length < narrow.divergent_length
    assert wide.divergence_lambda < narrow.divergence_lambda


def test_contours_are_monotonic_and_have_the_throat_at_origin() -> None:
    for contour in (conical_contour(0.05, 16.0), bell_contour(0.05, 16.0)):
        assert np.all(np.diff(contour.x) > 0.0)
        throat_index = int(np.argmin(contour.r))
        assert contour.x[throat_index] == pytest.approx(0.0, abs=1e-9)
        assert np.all(contour.r > 0.0)
        assert contour.area == pytest.approx(math.pi * contour.r**2)


def test_bell_is_shorter_than_the_reference_cone() -> None:
    cone = conical_contour(0.05, 16.0, 15.0)
    bell = bell_contour(0.05, 16.0, 80.0)
    assert bell.divergent_length == pytest.approx(0.80 * (bell.exit_radius - 0.05) / math.tan(math.radians(15.0)))
    assert bell.divergent_length < cone.divergent_length
    # ...and yet loses less to divergence, which is the whole point of a bell.
    assert bell.divergence_lambda > cone.divergence_lambda


def test_bell_length_scales_with_the_percentage() -> None:
    short = bell_contour(0.05, 16.0, 60.0)
    long = bell_contour(0.05, 16.0, 100.0)
    assert short.divergent_length < long.divergent_length
    assert short.theta_n_deg is not None and long.theta_n_deg is not None
    # A shorter bell must open faster at the throat and ends less aligned.
    assert short.theta_n_deg > long.theta_n_deg
    assert short.theta_e_deg is not None and long.theta_e_deg is not None
    assert short.theta_e_deg > long.theta_e_deg  # moins de longueur pour redresser


def test_rao_angles_follow_the_charts() -> None:
    theta_n, theta_e = rao_angles(20.0, 80.0)
    assert theta_n == pytest.approx(24.0, abs=0.1)
    assert theta_e == pytest.approx(9.5, abs=0.1)
    # θn grows with ε while θe falls: the bell opens faster and closes tighter.
    n_small, e_small = rao_angles(5.0)
    n_large, e_large = rao_angles(50.0)
    assert n_small < n_large
    assert e_small > e_large


def test_explicit_bell_angles_override_the_charts() -> None:
    contour = bell_contour(0.05, 16.0, 80.0, theta_n_deg=30.0, theta_e_deg=8.0)
    assert contour.theta_n_deg == pytest.approx(30.0)
    assert contour.theta_e_deg == pytest.approx(8.0)
    assert contour.divergence_lambda == pytest.approx(0.5 * (1.0 + math.cos(math.radians(8.0))))


def test_rejects_impossible_geometry() -> None:
    with pytest.raises(ValueError, match="rayon au col"):
        conical_contour(0.0, 16.0)
    with pytest.raises(ValueError, match="ε"):
        conical_contour(0.05, 0.5)
    with pytest.raises(ValueError, match="demi-angle"):
        conical_contour(0.05, 16.0, 95.0)
    with pytest.raises(ValueError, match="ε"):
        bell_contour(0.05, 1.0)
    with pytest.raises(ValueError, match="pourcentage"):
        bell_contour(0.05, 16.0, 0.0)
    with pytest.raises(ValueError, match="trop proches"):
        bell_contour(0.05, 16.0, 80.0, theta_n_deg=12.0, theta_e_deg=12.0)
    with pytest.raises(ValueError, match=r"galbe trop court|point de contrôle"):
        bell_contour(0.05, 50.0, 1.0)


def test_chamber_radius_must_exceed_the_throat_fillet() -> None:
    with pytest.raises(ValueError, match="rayon de chambre"):
        conical_contour(0.05, 16.0, chamber_ratio=1.0)
