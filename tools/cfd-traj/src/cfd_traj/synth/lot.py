"""Monte-Carlo lot: many dispersed shots, written as CSV files.

The dispersion is applied to the *causes* -- thrust level, mass, drag, launch
elevation, gust amplitude -- not to the results. That is what makes the cloud
have the shape the method exploits: Mach, altitude and Reynolds stay correlated
inside each shot, and it is only the whole bundle that spreads.

Everything is seeded. Two runs with the same seed produce byte-identical files,
which is what makes the end-to-end determinism test possible.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from cfd_traj.synth.autopilot import AutopilotSpec, deflections
from cfd_traj.synth.flight import Guidance, Trajectory, Vehicle, integrate
from cfd_traj.synth.parametres import ParameterModel, default_models, generate

#: Column order of every generated file: the mandatory eight, then the extras.
BASE_COLUMNS: tuple[str, ...] = (
    "time",
    "Mach",
    "Altitude",
    "alpha",
    "beta",
    "dl",
    "dm",
    "dn",
)


@dataclass(frozen=True)
class LotSpec:
    """Everything that defines a lot of dispersed trajectories."""

    n_shots: int = 40
    seed: int = 12345
    dt: float = 0.02
    dt_out: float = 0.25
    t_max: float = 400.0
    prefix: str = "tir"
    parameters: tuple[ParameterModel, ...] = field(default_factory=lambda: default_models(2))
    vehicle: Vehicle = field(default_factory=Vehicle)
    autopilot: AutopilotSpec = field(default_factory=AutopilotSpec)
    thrust_sigma: float = 0.045
    mass_sigma: float = 0.020
    drag_sigma: float = 0.070
    elevation_sigma_deg: float = 1.8
    gust_sigma: float = 0.35
    parameter_sigma: float = 0.08

    def __post_init__(self) -> None:
        if self.n_shots <= 0:
            raise ValueError(f"n_shots must be positive, got {self.n_shots}")
        names = [p.name for p in self.parameters]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ValueError(f"colonnes de paramètres en double : {duplicates}")
        clashes = sorted(set(names) & set(BASE_COLUMNS))
        if clashes:
            raise ValueError(f"nom(s) de paramètre déjà utilisé(s) par le format : {clashes}")

    @property
    def columns(self) -> tuple[str, ...]:
        """Header of every generated file."""
        return (*BASE_COLUMNS, *(p.name for p in self.parameters))


@dataclass(frozen=True)
class ShotData:
    """One generated shot, ready to be written."""

    name: str
    columns: tuple[str, ...]
    values: dict[str, np.ndarray]
    trajectory: Trajectory

    @property
    def n_rows(self) -> int:
        """Number of samples."""
        return int(self.values["time"].size)


def generate_shot(index: int, spec: LotSpec, rng: np.random.Generator) -> ShotData:
    """Integrate one dispersed shot and dress it with its parameter columns."""
    thrust_scale = float(1.0 + rng.normal(0.0, spec.thrust_sigma))
    mass_scale = float(1.0 + rng.normal(0.0, spec.mass_sigma))
    drag_scale = float(1.0 + rng.normal(0.0, spec.drag_sigma))
    elevation = float(rng.normal(0.0, spec.elevation_sigma_deg))
    gust_scale = float(np.exp(rng.normal(0.0, spec.gust_sigma)))
    roll_phase = float(rng.uniform(0.0, 2.0 * np.pi))

    base = Guidance()
    guidance = Guidance(
        gamma0_deg=base.gamma0_deg + elevation,
        gamma_end_deg=base.gamma_end_deg + 0.5 * elevation,
        pitch_time_s=base.pitch_time_s * float(1.0 + rng.normal(0.0, 0.06)),
        gain=base.gain,
        alpha_max_deg=base.alpha_max_deg,
        gust_amplitude_ms=base.gust_amplitude_ms * gust_scale,
        gust_periods_s=base.gust_periods_s,
        gust_phases=tuple(float(rng.uniform(0.0, 2.0 * np.pi)) for _ in range(3)),  # type: ignore[arg-type]
        gust_decay_m=base.gust_decay_m,
    )

    trajectory = integrate(
        vehicle=spec.vehicle,
        guidance=guidance,
        thrust_scale=max(thrust_scale, 0.2),
        drag_scale=max(drag_scale, 0.2),
        mass_scale=max(mass_scale, 0.5),
        dt=spec.dt,
        dt_out=spec.dt_out,
        t_max=spec.t_max,
    )

    surfaces = deflections(
        trajectory.time_s,
        trajectory.alpha_deg,
        trajectory.beta_deg,
        spec=spec.autopilot,
        roll_phase=roll_phase,
    )

    values: dict[str, np.ndarray] = {
        "time": trajectory.time_s,
        "Mach": trajectory.mach,
        "Altitude": trajectory.altitude_m,
        "alpha": trajectory.alpha_deg,
        "beta": trajectory.beta_deg,
        **surfaces,
    }
    for model in spec.parameters:
        values[model.name] = generate(
            model,
            time_s=trajectory.time_s,
            mach=trajectory.mach,
            altitude_m=trajectory.altitude_m,
            rng=rng,
            scale=float(np.exp(rng.normal(0.0, spec.parameter_sigma))),
        )

    return ShotData(
        name=f"{spec.prefix}_{index + 1:04d}",
        columns=spec.columns,
        values=values,
        trajectory=trajectory,
    )


def generate_lot(spec: LotSpec) -> tuple[ShotData, ...]:
    """Generate every shot of the lot, in order."""
    rng = np.random.default_rng(spec.seed)
    return tuple(generate_shot(i, spec, rng) for i in range(spec.n_shots))


def write_shot(shot: ShotData, path: Path) -> Path:
    """Write one shot as a comma-separated file with a machine decimal point."""
    path.parent.mkdir(parents=True, exist_ok=True)
    block = np.column_stack([shot.values[c] for c in shot.columns])
    np.savetxt(
        path,
        block,
        delimiter=",",
        header=",".join(shot.columns),
        comments="",
        fmt="%.9g",
    )
    return path


def write_lot(directory: str | Path, spec: LotSpec) -> tuple[Path, ...]:
    """Generate a lot and write it to ``directory``, one file per shot."""
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for shot in generate_lot(spec):
        written.append(write_shot(shot, out / f"{shot.name}.csv"))
    return tuple(written)


def summarise(shots: Sequence[ShotData]) -> dict[str, float]:
    """A few aggregate numbers about a generated lot, for the CLI report."""
    apogees = np.array([s.trajectory.apogee_m for s in shots], dtype=np.float64)
    machs = np.array([s.trajectory.mach_max for s in shots], dtype=np.float64)
    rows = np.array([s.n_rows for s in shots], dtype=np.float64)
    return {
        "n_shots": float(len(shots)),
        "n_rows": float(rows.sum()),
        "apogee_mean_m": float(apogees.mean()),
        "apogee_std_m": float(apogees.std()),
        "mach_max_mean": float(machs.mean()),
        "mach_max_max": float(machs.max()),
        "rows_min": float(rows.min()),
        "rows_max": float(rows.max()),
    }
