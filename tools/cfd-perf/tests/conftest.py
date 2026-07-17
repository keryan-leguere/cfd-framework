"""Shared fixtures.

``REAL_PILOT`` is the measured strong-scaling series from a 20M-cell RANS
case on an air-gapped cluster.  It is the reference dataset for the whole
suite because it exhibits the hardest feature to model: a genuine
communication-dominated uptick past ~576 cores.
"""

from __future__ import annotations

import pytest

from cfd_perf.data.machine import Machine
from cfd_perf.data.mesh import mesh_from_data
from cfd_perf.data.pilot import pilot_from_points

REAL_PILOT_POINTS = [
    {"cores": 48, "time_per_iter_s": 3.85, "peak_ram_total_gb": 142.0},
    {"cores": 96, "time_per_iter_s": 2.18, "peak_ram_total_gb": 142.0},
    {"cores": 192, "time_per_iter_s": 1.41, "peak_ram_total_gb": 143.0},
    {"cores": 384, "time_per_iter_s": 1.12, "peak_ram_total_gb": 144.0},
    {"cores": 576, "time_per_iter_s": 1.05, "peak_ram_total_gb": 145.0},
    {"cores": 768, "time_per_iter_s": 1.10, "peak_ram_total_gb": 146.0},
    {"cores": 1024, "time_per_iter_s": 1.28, "peak_ram_total_gb": 148.0},
]


@pytest.fixture
def pilot():
    return pilot_from_points(REAL_PILOT_POINTS, n_iterations=12_000)


@pytest.fixture
def mesh(pilot):
    return mesh_from_data(num_cells=20_000_000, num_faces=61_200_000, pilot=pilot)


@pytest.fixture
def machine():
    return Machine(
        name="test-cluster",
        cores_per_node=48,
        ram_per_node_gb=192,
        max_nodes=32,
        max_walltime_hours=24,
    )
