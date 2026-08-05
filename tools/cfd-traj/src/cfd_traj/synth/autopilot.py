"""Control-surface deflections that look like an autopilot produced them.

The point is not fidelity -- it is that ``dl``, ``dm`` and ``dn`` must carry the
correlations a real log would have, so that the role auto-detection, the
mechanical-range handling and the deflection-symmetry classification are all
exercised on something other than noise.

Pitch and yaw deflections oppose the incidence and the sideslip (that is what
trimming is), roll follows a slow programme, and every channel is rate-limited
and clipped to the mechanical stops.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class AutopilotSpec:
    """Gains and limits of the deflection model."""

    pitch_gain: float = 1.0
    yaw_gain: float = 1.1
    roll_amplitude_deg: float = 3.0
    roll_period_s: float = 22.0
    limit_deg: float = 20.0
    rate_limit_deg_s: float = 120.0

    def __post_init__(self) -> None:
        if self.limit_deg <= 0:
            raise ValueError("limit_deg must be positive")
        if self.rate_limit_deg_s <= 0:
            raise ValueError("rate_limit_deg_s must be positive")


def _rate_limit(
    command: NDArray[np.float64], time_s: NDArray[np.float64], rate: float
) -> NDArray[np.float64]:
    """Follow a command as fast as the actuator allows, no faster."""
    out = np.empty_like(command)
    out[0] = command[0]
    for i in range(1, command.size):
        step = rate * max(float(time_s[i] - time_s[i - 1]), 0.0)
        out[i] = out[i - 1] + float(np.clip(command[i] - out[i - 1], -step, step))
    return out


def deflections(
    time_s: NDArray[np.float64],
    alpha_deg: NDArray[np.float64],
    beta_deg: NDArray[np.float64],
    *,
    spec: AutopilotSpec | None = None,
    roll_phase: float = 0.0,
) -> dict[str, NDArray[np.float64]]:
    """Return ``dl``, ``dm`` and ``dn`` in degrees, clipped to the mechanical stops."""
    spec = spec or AutopilotSpec()
    limit = spec.limit_deg

    roll_cmd = spec.roll_amplitude_deg * np.sin(
        2.0 * np.pi * time_s / spec.roll_period_s + roll_phase
    )
    pitch_cmd = -spec.pitch_gain * alpha_deg
    yaw_cmd = -spec.yaw_gain * beta_deg

    out: dict[str, NDArray[np.float64]] = {}
    for name, command in (("dl", roll_cmd), ("dm", pitch_cmd), ("dn", yaw_cmd)):
        clipped = np.clip(np.nan_to_num(command, nan=0.0), -limit, limit)
        out[name] = np.clip(_rate_limit(clipped, time_s, spec.rate_limit_deg_s), -limit, limit)
    return out
