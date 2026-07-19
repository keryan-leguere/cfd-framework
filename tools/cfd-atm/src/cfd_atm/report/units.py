"""Display-unit conversions between SI and aeronautical conventions.

The core of cfd-atm is SI; this module only exists so the terminal report and the
figures can lead with feet and knots (aeronautical practice) while still showing
the SI value alongside.
"""

from __future__ import annotations

FEET_PER_METRE: float = 1.0 / 0.3048
"""1 m = 3.28084 ft."""

METRES_PER_FOOT: float = 0.3048

KNOTS_PER_MPS: float = 1.0 / 0.514444
"""1 m/s = 1.94384 kt."""

MPS_PER_KNOT: float = 0.514444


def metres_to_feet(metres: float) -> float:
    """Metres to feet."""
    return metres * FEET_PER_METRE


def feet_to_metres(feet: float) -> float:
    """Feet to metres."""
    return feet * METRES_PER_FOOT


def mps_to_knots(mps: float) -> float:
    """m/s to knots."""
    return mps * KNOTS_PER_MPS


def knots_to_mps(knots: float) -> float:
    """Knots to m/s."""
    return knots * MPS_PER_KNOT
