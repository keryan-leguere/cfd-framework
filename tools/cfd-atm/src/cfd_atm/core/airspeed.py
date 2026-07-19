"""Flight-mechanics airspeeds: Mach, calibrated (Vc/CAS), equivalent (EAS) and
true (TAS) airspeed, in both the subsonic and supersonic regimes.

Everything hinges on the **impact pressure** ``qc = pt - p`` measured by the
pitot tube:

- ``qc <-> Vc``  uses the **sea-level** constants ``p0``, ``a0``;
- ``qc <-> M``   uses the **local** static pressure ``p``.

Subsonic (M <= 1) the relations are the compressible isentropic pitot formulas
and invert analytically. Supersonic (M > 1) the Rayleigh pitot formula applies
and the M inversion is done by a bracketed Newton/bisection solver (no SciPy).

See ``00_DOC/02_GRANDEURS_VITESSE.md`` for the derivation and the key subtlety
that ``Vc <-> M`` does not depend on temperature.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import numpy as np
from numpy.typing import ArrayLike, NDArray

from cfd_atm.core.constants import A0, GAMMA, P0, R_AIR
from cfd_atm.core.thermo import speed_of_sound

_GM1 = GAMMA - 1.0
_GP1 = GAMMA + 1.0
_EXP_SUB = GAMMA / _GM1  # 3.5 for air
_EXP_SUP_NUM = GAMMA / _GM1  # 3.5
_EXP_SUP_DEN = 1.0 / _GM1  # 2.5

# qc/p at exactly M = 1 (continuity point between the two regimes).
_RATIO_AT_M1 = (1.0 + 0.5 * _GM1) ** _EXP_SUB - 1.0


def _qc_ratio_supersonic(mach: float) -> float:
    """qc/p as a function of Mach, supersonic (Rayleigh) branch."""
    num = (0.5 * _GP1 * mach**2) ** _EXP_SUP_NUM
    den = (2.0 * GAMMA / _GP1 * mach**2 - _GM1 / _GP1) ** _EXP_SUP_DEN
    return float(num / den - 1.0)


def _qc_ratio_scalar(mach: float) -> float:
    """qc/p for a single Mach, choosing the subsonic or Rayleigh branch."""
    if mach <= 1.0:
        return float((1.0 + 0.5 * _GM1 * mach**2) ** _EXP_SUB - 1.0)
    return _qc_ratio_supersonic(mach)


def _mach_from_ratio_scalar(ratio: float) -> float:
    """Invert qc/p -> Mach for a single ratio, choosing the regime."""
    if ratio <= 0.0:
        return 0.0
    if ratio <= _RATIO_AT_M1:
        # Subsonic: analytic inversion.
        return float(np.sqrt(2.0 / _GM1 * ((ratio + 1.0) ** (1.0 / _EXP_SUB) - 1.0)))
    # Supersonic: bracketed bisection on [1, 30]. The function is monotonic, so
    # bisection converges reliably without any external dependency.
    lo, hi = 1.0, 30.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _qc_ratio_supersonic(mid) < ratio:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return 0.5 * (lo + hi)


def impact_pressure_from_mach(mach: ArrayLike, p: ArrayLike) -> NDArray[np.float64]:
    """Impact pressure ``qc`` (Pa) from Mach and local static pressure ``p`` (Pa)."""
    mach_arr = np.asarray(mach, dtype=np.float64)
    p_arr = np.asarray(p, dtype=np.float64)
    ratio = np.vectorize(_qc_ratio_scalar, otypes=[np.float64])(mach_arr)
    return cast(NDArray[np.float64], p_arr * ratio)


def mach_from_impact_pressure(qc: ArrayLike, p: ArrayLike) -> NDArray[np.float64]:
    """Mach from impact pressure ``qc`` (Pa) and local static pressure ``p`` (Pa)."""
    qc_arr = np.asarray(qc, dtype=np.float64)
    p_arr = np.asarray(p, dtype=np.float64)
    ratio = qc_arr / p_arr
    return cast(
        NDArray[np.float64],
        np.vectorize(_mach_from_ratio_scalar, otypes=[np.float64])(ratio),
    )


def impact_pressure_from_cas(cas: ArrayLike) -> NDArray[np.float64]:
    """Impact pressure ``qc`` (Pa) from calibrated airspeed ``Vc`` (m/s).

    Uses the sea-level static pressure ``p0``: the "sea-level Mach" is ``Vc/a0``.
    """
    cas_arr = np.asarray(cas, dtype=np.float64)
    return impact_pressure_from_mach(cas_arr / A0, P0)


def cas_from_impact_pressure(qc: ArrayLike) -> NDArray[np.float64]:
    """Calibrated airspeed ``Vc`` (m/s) from impact pressure ``qc`` (Pa)."""
    mach_sl = mach_from_impact_pressure(qc, P0)
    return mach_sl * A0


def mach_from_cas(cas: ArrayLike, p: ArrayLike) -> NDArray[np.float64]:
    """Mach from calibrated airspeed ``Vc`` (m/s) and local pressure ``p`` (Pa)."""
    return mach_from_impact_pressure(impact_pressure_from_cas(cas), p)


def cas_from_mach(mach: ArrayLike, p: ArrayLike) -> NDArray[np.float64]:
    """Calibrated airspeed ``Vc`` (m/s) from Mach and local pressure ``p`` (Pa)."""
    return cas_from_impact_pressure(impact_pressure_from_mach(mach, p))


def tas_from_mach(mach: ArrayLike, t: ArrayLike) -> NDArray[np.float64]:
    """True airspeed (m/s) from Mach and temperature ``T`` (K)."""
    return np.asarray(mach, dtype=np.float64) * speed_of_sound(t)


def mach_from_tas(tas: ArrayLike, t: ArrayLike) -> NDArray[np.float64]:
    """Mach from true airspeed (m/s) and temperature ``T`` (K)."""
    return np.asarray(tas, dtype=np.float64) / speed_of_sound(t)


def eas_from_mach(mach: ArrayLike, p: ArrayLike) -> NDArray[np.float64]:
    """Equivalent airspeed (m/s) from Mach and local pressure ``p`` (Pa).

    ``EAS = a0 · M · sqrt(p/p0)`` — depends only on pressure, not temperature.
    """
    mach_arr = np.asarray(mach, dtype=np.float64)
    p_arr = np.asarray(p, dtype=np.float64)
    return A0 * mach_arr * np.sqrt(p_arr / P0)


def mach_from_eas(eas: ArrayLike, p: ArrayLike) -> NDArray[np.float64]:
    """Mach from equivalent airspeed (m/s) and local pressure ``p`` (Pa)."""
    eas_arr = np.asarray(eas, dtype=np.float64)
    p_arr = np.asarray(p, dtype=np.float64)
    return eas_arr / (A0 * np.sqrt(p_arr / P0))


@dataclass(frozen=True)
class AirspeedSet:
    """The full set of airspeeds at a point, all in SI (m/s except Mach, Pa)."""

    mach: float
    cas: float  # calibrated / Vc (m/s)
    eas: float  # equivalent (m/s)
    tas: float  # true (m/s)
    q: float  # dynamic pressure ½·rho·TAS² (Pa)


def airspeeds(
    p: float,
    t: float,
    *,
    mach: float | None = None,
    cas: float | None = None,
    tas: float | None = None,
    eas: float | None = None,
) -> AirspeedSet:
    """Reconstruct every airspeed from exactly one of Mach/Vc/TAS/EAS.

    ``p`` and ``t`` are the local static pressure (Pa) and temperature (K).
    Exactly one of ``mach``/``cas``/``tas``/``eas`` must be given.
    """
    given = [name for name, val in (("mach", mach), ("cas", cas), ("tas", tas), ("eas", eas)) if val is not None]
    if len(given) != 1:
        raise ValueError("Fournir exactement une grandeur parmi mach/cas/tas/eas.")

    if mach is not None:
        m = float(mach)
    elif cas is not None:
        m = float(mach_from_cas(cas, p))
    elif tas is not None:
        m = float(mach_from_tas(tas, t))
    else:
        assert eas is not None
        m = float(mach_from_eas(eas, p))

    rho = p / (R_AIR * t)
    tas_val = float(tas_from_mach(m, t))
    return AirspeedSet(
        mach=m,
        cas=float(cas_from_mach(m, p)),
        eas=float(eas_from_mach(m, p)),
        tas=tas_val,
        q=0.5 * rho * tas_val**2,
    )
