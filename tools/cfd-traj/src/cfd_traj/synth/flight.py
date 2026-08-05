"""A small boost/coast flight model, good enough to produce credible trajectories.

This exists to give the package something to work on: a demonstrable example
and a test fixture whose cloud has the structure the method is designed to
exploit -- Mach, altitude and Reynolds moving together along the flight, a
transonic crossing, incidence decaying as dynamic pressure builds.

It is a 3-degree-of-freedom point-mass model integrated with RK4, not a
six-degree-of-freedom simulation, and it makes no claim to represent any real
vehicle. State: speed, flight-path angle, altitude, downrange, mass. The
incidence comes from a proportional autopilot tracking a pitch programme plus a
gust-induced term; the sideslip comes from the lateral gust alone. Beyond the
burn the thrust is zero and the vehicle coasts to apogee and back down.

SI units throughout; angles in radians inside, degrees on the way out.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from cfd_traj.core.adim import isa_density, isa_speed_of_sound

G0: float = 9.80665

#: Ceiling of the standard atmosphere used here; above it, no aerodynamics.
DRAG_CEILING_M: float = 80_000.0

#: Altitude step of the atmosphere lookup table. The RK4 loop asks for density
#: and speed of sound tens of thousands of times per shot, and going through
#: the full ISA relations each time dominates the run time by a factor of
#: twenty. A 50 m table interpolated linearly is well inside the accuracy this
#: model deserves.
_TABLE_STEP_M: float = 50.0
_TABLE_ALTITUDE: NDArray[np.float64] = np.arange(
    -2_000.0, DRAG_CEILING_M + _TABLE_STEP_M, _TABLE_STEP_M
)
_TABLE_DENSITY: NDArray[np.float64] = isa_density(_TABLE_ALTITUDE)
_TABLE_SOUND: NDArray[np.float64] = isa_speed_of_sound(_TABLE_ALTITUDE)


_TABLE_BASE_M: float = float(_TABLE_ALTITUDE[0])
_TABLE_LAST: int = int(_TABLE_ALTITUDE.size) - 2
_DENSITY_LIST: list[float] = _TABLE_DENSITY.tolist()
_SOUND_LIST: list[float] = _TABLE_SOUND.tolist()


def atmosphere(altitude_m: float) -> tuple[float, float]:
    """Density and speed of sound at a geometric altitude, from the lookup table.

    Hand-rolled linear interpolation on Python floats: this is called four
    times per integration step, and ``np.interp`` on a scalar costs several
    microseconds of array machinery for a two-line calculation.
    """
    z = min(max(altitude_m, _TABLE_BASE_M), DRAG_CEILING_M)
    position = (z - _TABLE_BASE_M) / _TABLE_STEP_M
    index = min(int(position), _TABLE_LAST)
    frac = position - index
    rho = _DENSITY_LIST[index]
    sound = _SOUND_LIST[index]
    return (
        rho + frac * (_DENSITY_LIST[index + 1] - rho),
        sound + frac * (_SOUND_LIST[index + 1] - sound),
    )


@dataclass(frozen=True)
class Vehicle:
    """The (entirely fictional) vehicle being flown."""

    mass_launch_kg: float = 320.0
    mass_propellant_kg: float = 190.0
    thrust_n: float = 32_000.0
    burn_time_s: float = 9.5
    reference_area_m2: float = 0.049
    cd0: float = 0.28
    cd_induced: float = 1.6
    cl_alpha_per_rad: float = 12.0

    def __post_init__(self) -> None:
        # Positivity first: a zero launch mass would otherwise be reported as a
        # propellant-mass problem, which is not what the user got wrong.
        for name in ("mass_launch_kg", "thrust_n", "burn_time_s", "reference_area_m2"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.mass_propellant_kg >= self.mass_launch_kg:
            raise ValueError("propellant mass must be smaller than launch mass")

    @property
    def mass_empty_kg(self) -> float:
        """Mass once the propellant is spent."""
        return self.mass_launch_kg - self.mass_propellant_kg

    @property
    def mass_flow_kg_s(self) -> float:
        """Constant propellant mass flow over the burn."""
        return self.mass_propellant_kg / self.burn_time_s


@dataclass(frozen=True)
class Guidance:
    """Pitch programme and gust environment of one shot."""

    gamma0_deg: float = 84.0
    gamma_end_deg: float = 28.0
    pitch_time_s: float = 45.0
    gain: float = 0.9
    alpha_max_deg: float = 12.0
    gust_amplitude_ms: float = 14.0
    gust_periods_s: tuple[float, float, float] = (7.0, 3.1, 1.7)
    gust_phases: tuple[float, float, float] = (0.0, 1.1, 2.3)
    gust_decay_m: float = 9_000.0

    def gamma_command_rad(self, t: float) -> float:
        """Commanded flight-path angle at time ``t``."""
        blend = min(1.0, max(0.0, t / self.pitch_time_s))
        deg = self.gamma0_deg + (self.gamma_end_deg - self.gamma0_deg) * blend
        return math.radians(deg)

    def gust(self, t: float, altitude_m: float) -> tuple[float, float]:
        """Vertical and lateral gust components, decaying with altitude."""
        decay = math.exp(-max(altitude_m, 0.0) / self.gust_decay_m)
        vertical = 0.0
        lateral = 0.0
        for i, (period, phase) in enumerate(
            zip(self.gust_periods_s, self.gust_phases, strict=True)
        ):
            wave = math.sin(2.0 * math.pi * t / period + phase)
            weight = 1.0 / (i + 1)
            if i % 2 == 0:
                vertical += weight * wave
            else:
                lateral += weight * wave
        scale = self.gust_amplitude_ms * decay
        return scale * vertical, scale * lateral


@dataclass(frozen=True)
class Trajectory:
    """One integrated shot, resampled on a regular output grid."""

    time_s: NDArray[np.float64]
    mach: NDArray[np.float64]
    altitude_m: NDArray[np.float64]
    alpha_deg: NDArray[np.float64]
    beta_deg: NDArray[np.float64]
    speed_ms: NDArray[np.float64]
    mass_kg: NDArray[np.float64]
    downrange_m: NDArray[np.float64]

    @property
    def n_rows(self) -> int:
        """Number of output samples."""
        return int(self.time_s.size)

    @property
    def apogee_m(self) -> float:
        """Highest altitude reached."""
        return float(np.max(self.altitude_m))

    @property
    def mach_max(self) -> float:
        """Highest Mach number reached."""
        return float(np.max(self.mach))


def drag_coefficient(mach: float, alpha_rad: float, vehicle: Vehicle) -> float:
    """Zero-lift drag with a transonic rise, plus an induced term.

    The transonic bump is placed just above Mach 1 and decays supersonically:
    a caricature of the real curve, but with the peak in the right place, which
    is what matters for the Mach bands the tool later builds.
    """
    m = abs(mach)
    peak = 1.0 + 1.4 * math.exp(-(((m - 1.1) / 0.22) ** 2))
    supersonic = 1.0 / (1.0 + 0.25 * max(m - 1.4, 0.0))
    return vehicle.cd0 * peak * supersonic + vehicle.cd_induced * alpha_rad**2


def _alpha_command(t: float, gamma: float, guidance: Guidance) -> float:
    """Incidence asked for by the pitch autopilot, in radians."""
    error = guidance.gamma_command_rad(t) - gamma
    limit = math.radians(guidance.alpha_max_deg)
    return min(max(guidance.gain * error, -limit), limit)


def _wind_angles(
    t: float, speed: float, altitude: float, guidance: Guidance
) -> tuple[float, float]:
    """Gust-induced incidence and sideslip, in radians."""
    vertical, lateral = guidance.gust(t, altitude)
    v = max(speed, 1.0)
    return math.atan2(vertical, v), math.atan2(lateral, v)


#: State vector layout of the integrator.
State = tuple[float, float, float, float, float]


def _derivatives(
    t: float,
    state: State,
    vehicle: Vehicle,
    guidance: Guidance,
    thrust_scale: float,
    drag_scale: float,
) -> State:
    """Right-hand side for (speed, gamma, altitude, downrange, mass).

    Deliberately written on plain Python floats rather than NumPy arrays: it is
    evaluated four times per step and tens of thousands of times per shot, and
    at this size the array machinery costs an order of magnitude more than the
    arithmetic it wraps.
    """
    speed, gamma, altitude, _, mass = state
    speed = max(speed, 1.0)
    mass = max(mass, vehicle.mass_empty_kg)

    burning = t < vehicle.burn_time_s
    thrust = thrust_scale * vehicle.thrust_n if burning else 0.0
    mass_rate = -vehicle.mass_flow_kg_s if burning else 0.0

    rho, sound = atmosphere(altitude)
    if altitude >= DRAG_CEILING_M:
        rho = 0.0

    mach = speed / sound
    alpha_wind, _ = _wind_angles(t, speed, altitude, guidance)
    alpha = _alpha_command(t, gamma, guidance) + alpha_wind

    q = 0.5 * rho * speed * speed
    area = vehicle.reference_area_m2
    drag = drag_scale * q * area * drag_coefficient(mach, alpha, vehicle)
    lift = q * area * vehicle.cl_alpha_per_rad * alpha

    sin_gamma = math.sin(gamma)
    cos_gamma = math.cos(gamma)
    return (
        (thrust - drag) / mass - G0 * sin_gamma,
        lift / (mass * speed) - G0 * cos_gamma / speed,
        speed * sin_gamma,
        speed * cos_gamma,
        mass_rate,
    )


def integrate(
    *,
    vehicle: Vehicle | None = None,
    guidance: Guidance | None = None,
    thrust_scale: float = 1.0,
    drag_scale: float = 1.0,
    mass_scale: float = 1.0,
    speed0_ms: float = 35.0,
    altitude0_m: float = 150.0,
    dt: float = 0.02,
    dt_out: float = 0.25,
    t_max: float = 400.0,
    stop_at_apogee: bool = True,
) -> Trajectory:
    """Integrate one shot with RK4 and resample it on the output grid.

    The flight ends at apogee by default: the ballistic descent adds little to
    a design of experiments and the model is at its crudest there. Because the
    time of apogee depends on the dispersion, this is also what gives the lot
    shots of *different lengths* -- the rest of the package must cope with that.
    """
    vehicle = vehicle or Vehicle()
    guidance = guidance or Guidance()
    if dt <= 0 or dt_out <= 0:
        raise ValueError("dt and dt_out must be positive")
    if dt_out < dt:
        raise ValueError("dt_out must be at least dt")

    state: State = (
        speed0_ms,
        math.radians(guidance.gamma0_deg),
        altitude0_m,
        0.0,
        mass_scale * vehicle.mass_launch_kg,
    )
    empty = mass_scale * vehicle.mass_empty_kg
    half = dt / 2.0
    sixth = dt / 6.0

    times: list[float] = []
    states: list[State] = []
    t = 0.0
    while t <= t_max:
        times.append(t)
        states.append(state)

        k1 = _derivatives(t, state, vehicle, guidance, thrust_scale, drag_scale)
        s2 = tuple(x + half * k for x, k in zip(state, k1, strict=True))
        k2 = _derivatives(t + half, s2, vehicle, guidance, thrust_scale, drag_scale)  # type: ignore[arg-type]
        s3 = tuple(x + half * k for x, k in zip(state, k2, strict=True))
        k3 = _derivatives(t + half, s3, vehicle, guidance, thrust_scale, drag_scale)  # type: ignore[arg-type]
        s4 = tuple(x + dt * k for x, k in zip(state, k3, strict=True))
        k4 = _derivatives(t + dt, s4, vehicle, guidance, thrust_scale, drag_scale)  # type: ignore[arg-type]

        advanced = tuple(
            x + sixth * (a + 2.0 * b + 2.0 * c + d)
            for x, a, b, c, d in zip(state, k1, k2, k3, k4, strict=True)
        )
        state = (
            max(advanced[0], 1.0),
            advanced[1],
            advanced[2],
            advanced[3],
            max(advanced[4], empty),
        )
        t += dt

        past_burn = t > vehicle.burn_time_s
        if past_burn and stop_at_apogee and state[1] <= 0.0:
            break
        if past_burn and state[2] <= 0.0:
            break

    history = np.asarray(states, dtype=np.float64)
    time = np.asarray(times, dtype=np.float64)

    grid = np.arange(0.0, float(time[-1]) + 0.5 * dt_out, dt_out)
    grid = grid[grid <= time[-1]]
    if grid.size < 2:
        grid = time[:2]

    speed = np.interp(grid, time, history[:, 0])
    gamma = np.interp(grid, time, history[:, 1])
    altitude = np.interp(grid, time, history[:, 2])
    downrange = np.interp(grid, time, history[:, 3])
    mass = np.interp(grid, time, history[:, 4])

    sound = isa_speed_of_sound(np.clip(altitude, -1_000.0, DRAG_CEILING_M))
    mach = speed / sound

    alpha = np.empty_like(grid)
    beta = np.empty_like(grid)
    for i, (ti, gi, si, hi) in enumerate(zip(grid, gamma, speed, altitude, strict=True)):
        alpha_wind, beta_wind = _wind_angles(float(ti), float(si), float(hi), guidance)
        alpha[i] = _alpha_command(float(ti), float(gi), guidance) + alpha_wind
        beta[i] = beta_wind

    return Trajectory(
        time_s=grid,
        mach=np.asarray(mach, dtype=np.float64),
        altitude_m=np.asarray(np.maximum(altitude, 0.0), dtype=np.float64),
        alpha_deg=np.rad2deg(alpha),
        beta_deg=np.rad2deg(beta),
        speed_ms=np.asarray(speed, dtype=np.float64),
        mass_kg=np.asarray(mass, dtype=np.float64),
        downrange_m=np.asarray(downrange, dtype=np.float64),
    )
