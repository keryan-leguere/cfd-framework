"""Adding the derived columns: what the flow sees, next to what the flight logged.

This is the single place where :mod:`cfd_traj.core.angles`,
:mod:`cfd_traj.core.adim` and :mod:`cfd_traj.core.symmetry` meet the data. It
is deliberately idempotent: running it twice recomputes the same values in
place rather than appending duplicates, so a study can be re-derived after the
symmetry group or the reference length changes without reloading the CSVs.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from cfd_traj.core.adim import Reference, nondimensionalise
from cfd_traj.core.angles import to_aeroballistic
from cfd_traj.core.symmetry import SymmetrySpec, fold_phi
from cfd_traj.data.dataset import TrajectoryDataset


def add_derived_columns(
    ds: TrajectoryDataset,
    *,
    reference: Reference,
    symmetry: SymmetrySpec,
    delta_t_k: float = 0.0,
) -> TrajectoryDataset:
    """Add every derived column in one pass.

    ``phi_defined`` is stored as a float (0.0 / 1.0) so that the frame stays
    homogeneously numeric; the rows where it is 0 carry an arbitrary phi and
    must be excluded from any statistic on the azimuth.
    """
    alpha = ds.values("alpha")
    beta = ds.values("beta")
    mach = ds.values("Mach")
    altitude = ds.values("Altitude")

    alpha_tot, phi, defined = to_aeroballistic(alpha, beta)
    phi_fold = fold_phi(phi, symmetry)
    flow = nondimensionalise(mach, altitude, reference=reference, delta_t_k=delta_t_k)

    new: dict[str, NDArray[np.float64]] = {
        "alpha_tot": alpha_tot,
        "phi": phi,
        "phi_fold": phi_fold,
        "phi_defined": defined.astype(np.float64),
        **flow,
    }
    return ds.with_columns(new)
