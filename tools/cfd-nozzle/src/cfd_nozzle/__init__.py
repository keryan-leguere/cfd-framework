"""cfd-nozzle — quasi-1D toolbox for convergent-divergent nozzles.

Given a gas, a throat area and an area ratio, it answers the three questions a
CFD engineer asks before meshing anything: in which regime does this nozzle
run at that back pressure, what does it deliver, and what contour should be
drawn.

Assumptions of the quasi-1D theory used throughout:

* steady, adiabatic, inviscid flow (except across shocks);
* calorically perfect gas — γ and R constant, no chemistry, no freezing;
* uniform properties over each cross-section, so A = A(x) only;
* slowly varying area (dA/dx small), hence no radial velocity component;
* internal shocks treated as localised normal shocks.

The method of characteristics in :mod:`cfd_nozzle.core.moc` is the one part
that is genuinely two-dimensional.
"""

from __future__ import annotations

from cfd_nozzle.core.gas import GAS_LIBRARY, GasModel, gas_from_name
from cfd_nozzle.core.geometry import NozzleContour, bell_contour, conical_contour, rao_angles
from cfd_nozzle.core.isentropic import (
    IsentropicState,
    area_ratio,
    isentropic_state,
    mach_angle,
    mach_from_area_ratio,
    mach_from_p0_over_p,
    p0_over_p,
    t0_over_t,
)
from cfd_nozzle.core.moc import MOCResult, moc_nozzle
from cfd_nozzle.core.nozzle import CriticalRatios, FlowField, Nozzle, NozzleState, Regime
from cfd_nozzle.core.shocks import (
    NormalShockState,
    ObliqueShockState,
    beta_from_theta,
    mach_from_prandtl_meyer,
    normal_shock_state,
    nu_max,
    oblique_shock,
    prandtl_meyer,
    theta_max_oblique,
)

__version__ = "1.0.0"

__all__ = [
    "GAS_LIBRARY",
    "CriticalRatios",
    "FlowField",
    "GasModel",
    "IsentropicState",
    "MOCResult",
    "NormalShockState",
    "Nozzle",
    "NozzleContour",
    "NozzleState",
    "ObliqueShockState",
    "Regime",
    "__version__",
    "area_ratio",
    "bell_contour",
    "beta_from_theta",
    "conical_contour",
    "gas_from_name",
    "isentropic_state",
    "mach_angle",
    "mach_from_area_ratio",
    "mach_from_p0_over_p",
    "mach_from_prandtl_meyer",
    "moc_nozzle",
    "normal_shock_state",
    "nu_max",
    "oblique_shock",
    "p0_over_p",
    "prandtl_meyer",
    "rao_angles",
    "t0_over_t",
    "theta_max_oblique",
]
