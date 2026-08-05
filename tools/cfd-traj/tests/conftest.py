"""Shared fixtures.

The Matplotlib backend is forced to Agg before anything imports pyplot: the
figure tests must never try to open a window.

Two families of test data live here. ``make_lot`` writes hand-built CSVs whose
content is fully controlled, which is what the unit tests want. The
``lot_realiste`` fixture goes through the real synthetic generator, which is
what the envelope, plan and coverage tests want -- they need a cloud with the
genuine Mach/altitude correlation in it, not white noise.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

from cfd_traj.core.adim import Reference
from cfd_traj.core.symmetry import SymmetryGroup, SymmetrySpec
from cfd_traj.data.dataset import TrajectoryDataset, load_dataset
from cfd_traj.data.derive import add_derived_columns
from cfd_traj.synth.lot import LotSpec, write_lot
from cfd_traj.synth.parametres import ParameterModel

REFERENCE = Reference(length_m=2.5, area_m2=0.049)
C4V = SymmetrySpec(group=SymmetryGroup.C4V)

#: Path of the shipped example, used by several end-to-end tests.
EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "01_EXEMPLE"


def _one_shot(rng: np.random.Generator, n_rows: int, extra: Sequence[str]) -> dict[str, np.ndarray]:
    """One credible-looking shot, cheap enough to build thousands of times."""
    t = np.linspace(0.0, 60.0, n_rows)
    phase = t / 60.0
    mach = 0.4 + 2.6 * np.sin(np.pi * phase) ** 0.7 + rng.normal(0, 0.02, n_rows)
    mach = np.clip(mach, 0.25, 3.4)
    altitude = 200.0 + 18_000.0 * phase**1.3 + rng.normal(0, 50.0, n_rows)
    alpha = 4.0 * np.exp(-3.0 * phase) * np.cos(6.0 * t) + rng.normal(0, 0.2, n_rows)
    beta = 3.0 * np.exp(-3.0 * phase) * np.sin(5.0 * t) + rng.normal(0, 0.2, n_rows)
    row = {
        "time": t,
        "Mach": mach,
        "Altitude": altitude,
        "alpha": alpha,
        "beta": beta,
        "dl": 0.4 * np.sin(3.0 * t),
        "dm": -1.5 * alpha,
        "dn": -1.2 * beta,
    }
    for i, name in enumerate(extra):
        if i % 3 == 0:
            # Monotone in Mach: this is the one auto-detection calls conditional.
            row[name] = 40.0 * mach + 30.0 + rng.normal(0, 1.0, n_rows)
        elif i % 3 == 1:
            row[name] = 300.0 + rng.normal(0, 12.0, n_rows)
        else:
            row[name] = np.where(t < 30.0, 0.0, 1.0)
    return row


@pytest.fixture
def make_lot(tmp_path: Path) -> Callable[..., Path]:
    """Factory writing a lot of hand-built CSVs into a fresh directory."""

    def build(
        n_shots: int = 6,
        extra: Sequence[str] = ("PARA1", "PARA2"),
        n_rows: int = 120,
        *,
        name: str = "LOT",
        seed: int = 1234,
        vary_length: bool = True,
        overrides: Mapping[str, Callable[[dict[str, np.ndarray]], np.ndarray]] | None = None,
    ) -> Path:
        directory = tmp_path / name
        directory.mkdir(parents=True, exist_ok=True)
        rng = np.random.default_rng(seed)
        for i in range(n_shots):
            rows = n_rows + (i * 7 if vary_length else 0)
            data = _one_shot(rng, rows, extra)
            for key, fn in (overrides or {}).items():
                data[key] = fn(data)
            header = ",".join(data)
            block = np.column_stack(list(data.values()))
            np.savetxt(
                directory / f"tir_{i:04d}.csv",
                block,
                delimiter=",",
                header=header,
                comments="",
                fmt="%.9g",
            )
        return directory

    return build


@pytest.fixture
def lot_simple(make_lot: Callable[..., Path]) -> TrajectoryDataset:
    """A small hand-built lot, loaded but not derived."""
    return load_dataset(make_lot())


@pytest.fixture
def lot_derive(lot_simple: TrajectoryDataset) -> TrajectoryDataset:
    """The same lot with every derived column present."""
    return add_derived_columns(lot_simple, reference=REFERENCE, symmetry=C4V)


@pytest.fixture(scope="session")
def lot_realiste(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A lot produced by the real flight model: the cloud has a genuine tube."""
    directory = tmp_path_factory.mktemp("lot_realiste")
    write_lot(
        directory,
        LotSpec(
            n_shots=24,
            seed=4242,
            parameters=(
                ParameterModel(name="PARA1", archetype="correle_mach"),
                ParameterModel(name="PARA2", archetype="plateau_bruite"),
            ),
        ),
    )
    return directory


@pytest.fixture
def dataset_realiste(lot_realiste: Path) -> TrajectoryDataset:
    """The realistic lot, loaded and derived."""
    return add_derived_columns(load_dataset(lot_realiste), reference=REFERENCE, symmetry=C4V)


@pytest.fixture
def specs(dataset_realiste):
    """Auto-detected column specs of the realistic lot."""
    from cfd_traj.data.columns import build_specs

    built, _ = build_specs(dataset_realiste.columns, dataset_realiste.column_values(), {})
    return built


@pytest.fixture
def band_set(dataset_realiste):
    """A five-band partition of the realistic lot."""
    from cfd_traj.data.study import BandSpec
    from cfd_traj.engine.bands import build_bands

    return build_bands(dataset_realiste.values("Mach"), BandSpec(n_bands=5, min_points=50))


@pytest.fixture
def envelope(dataset_realiste, band_set, specs):
    """The conditional envelope of the realistic lot, with default quantiles."""
    from cfd_traj.data.study import EnvelopeSpec
    from cfd_traj.engine.envelope import build_envelope

    return build_envelope(
        dataset_realiste, band_set=band_set, specs=specs, spec=EnvelopeSpec(), symmetry=C4V
    )


@pytest.fixture
def envelope_exacte(dataset_realiste, band_set, specs):
    """The envelope built on the full range: coverage of its own lot is a theorem."""
    from cfd_traj.data.study import EnvelopeSpec
    from cfd_traj.engine.envelope import build_envelope

    return build_envelope(
        dataset_realiste,
        band_set=band_set,
        specs=specs,
        spec=EnvelopeSpec(q_low=0.0, q_high=1.0, margin=0.0),
        symmetry=C4V,
    )
