"""cfd-atm — atmosphere model and flight-mechanics airspeeds.

A solver-agnostic "block": given an altitude and a temperature model (ISA,
ISA±ΔT or a custom profile), it returns the air conditions (p, T, ρ), the
derived quantities (speed of sound, viscosity, ratios), every equivalent
altitude, and — from one speed input — the full set of airspeeds (Mach, Vc,
EAS, TAS) in both the subsonic and supersonic regimes.
"""

from __future__ import annotations

from cfd_atm.core.airspeed import (
    AirspeedSet,
    airspeeds,
    cas_from_mach,
    eas_from_mach,
    mach_from_cas,
    tas_from_mach,
)
from cfd_atm.core.atmosphere import (
    AtmosphereModel,
    AtmosphereState,
    ModelKind,
    temperature_profile_from_table,
)

__version__ = "1.0.0"

__all__ = [
    "AirspeedSet",
    "AtmosphereModel",
    "AtmosphereState",
    "ModelKind",
    "__version__",
    "airspeeds",
    "cas_from_mach",
    "eas_from_mach",
    "mach_from_cas",
    "tas_from_mach",
    "temperature_profile_from_table",
]
