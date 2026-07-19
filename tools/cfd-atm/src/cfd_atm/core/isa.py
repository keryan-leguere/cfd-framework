"""The International Standard Atmosphere (ISA): T, p, rho versus geopotential
altitude, plus the analytic inversions used for pressure/density altitude.

Every function accepts a scalar or a NumPy array of geopotential altitudes ``H``
(in metres) and returns the same shape. The layer table lives in
:mod:`cfd_atm.core.constants`.
"""

from __future__ import annotations

from typing import cast

import numpy as np
from numpy.typing import ArrayLike, NDArray

from cfd_atm.core.constants import (
    G0,
    H_TOP,
    ISA_LAYERS,
    R_AIR,
)


def _layer_index(h: NDArray[np.float64]) -> NDArray[np.intp]:
    """Index of the ISA layer containing each geopotential altitude."""
    bases = np.array([layer.h_base for layer in ISA_LAYERS])
    # np.searchsorted gives the insertion point; subtract 1 for the owning layer.
    idx = np.searchsorted(bases, h, side="right") - 1
    return np.clip(idx, 0, len(ISA_LAYERS) - 1)


def isa_temperature(h: ArrayLike) -> NDArray[np.float64]:
    """ISA temperature (K) at geopotential altitude ``H`` (m)."""
    h_arr = np.asarray(h, dtype=np.float64)
    idx = _layer_index(h_arr)
    t_base = np.array([layer.t_base for layer in ISA_LAYERS])[idx]
    h_base = np.array([layer.h_base for layer in ISA_LAYERS])[idx]
    lapse = np.array([layer.lapse for layer in ISA_LAYERS])[idx]
    return cast(NDArray[np.float64], t_base + lapse * (h_arr - h_base))


def isa_pressure(h: ArrayLike) -> NDArray[np.float64]:
    """ISA pressure (Pa) at geopotential altitude ``H`` (m)."""
    h_arr = np.asarray(h, dtype=np.float64)
    idx = _layer_index(h_arr)
    t_base = np.array([layer.t_base for layer in ISA_LAYERS])[idx]
    h_base = np.array([layer.h_base for layer in ISA_LAYERS])[idx]
    lapse = np.array([layer.lapse for layer in ISA_LAYERS])[idx]
    p_base = np.array([layer.p_base for layer in ISA_LAYERS])[idx]

    t = t_base + lapse * (h_arr - h_base)
    with np.errstate(divide="ignore", invalid="ignore"):
        gradient = p_base * (t / t_base) ** (-G0 / (np.where(lapse == 0.0, 1.0, lapse) * R_AIR))
        isothermal = p_base * np.exp(-G0 * (h_arr - h_base) / (R_AIR * t_base))
    return cast(NDArray[np.float64], np.where(lapse == 0.0, isothermal, gradient))


def isa_density(h: ArrayLike) -> NDArray[np.float64]:
    """ISA density (kg/m³) at geopotential altitude ``H`` (m)."""
    h_arr = np.asarray(h, dtype=np.float64)
    return isa_pressure(h_arr) / (R_AIR * isa_temperature(h_arr))


def geopotential_from_pressure(p: ArrayLike) -> NDArray[np.float64]:
    """Invert the ISA pressure law: geopotential altitude (m) giving pressure ``p``.

    This is exactly the pressure altitude ``zp``. The inversion is analytic,
    layer by layer, because each layer's pressure law is monotonic and closed
    form.
    """
    p_arr = np.asarray(p, dtype=np.float64)

    # For each pressure, find the layer it belongs to: pressure decreases with
    # altitude, so a point is in layer i when p <= p_base[i] and p > p_base[i+1].
    result = np.empty_like(p_arr)
    for flat_idx, pv in np.ndenumerate(p_arr):
        layer_idx = 0
        for i, layer in enumerate(ISA_LAYERS):
            if pv <= layer.p_base:
                layer_idx = i
        layer = ISA_LAYERS[layer_idx]
        if layer.lapse == 0.0:
            h = layer.h_base - R_AIR * layer.t_base / G0 * float(np.log(pv / layer.p_base))
        else:
            t = layer.t_base * float(pv / layer.p_base) ** (-layer.lapse * R_AIR / G0)
            h = layer.h_base + (t - layer.t_base) / layer.lapse
        result[flat_idx] = h
    return result if result.ndim else result.reshape(())


def geopotential_from_density(rho: ArrayLike) -> NDArray[np.float64]:
    """Invert the ISA density law: geopotential altitude (m) giving density ``rho``.

    This is the density altitude ``zrho``. Density is monotonic across the
    modelled range, so a bracketed bisection on :func:`isa_density` is robust and
    dependency free.
    """
    rho_arr = np.asarray(rho, dtype=np.float64)
    result = np.empty_like(rho_arr)
    for flat_idx, rv in np.ndenumerate(rho_arr):
        lo, hi = 0.0, H_TOP
        f_lo = float(isa_density(lo)) - rv
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            f_mid = float(isa_density(mid)) - rv
            if f_lo * f_mid <= 0.0:
                hi = mid
            else:
                lo, f_lo = mid, f_mid
            if hi - lo < 1e-6:
                break
        result[flat_idx] = 0.5 * (lo + hi)
    return result if result.ndim else result.reshape(())
