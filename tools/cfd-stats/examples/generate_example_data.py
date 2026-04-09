"""Generate example .pickle data for cfd-stats demos.

Mimics real CFD output with columns: family, Cl, Cd, Cm, iter
where family is a boundary surface (WALL, AIRFOIL, TOTAL).
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> None:
    rng = np.random.default_rng(123)
    n = 10000
    iters = np.arange(n)
    period = 250.0

    frames: list[pd.DataFrame] = []

    for fam, cl_mean, cd_mean, cm_mean, cl_amp, cm_amp in [
        ("AIRFOIL", 0.523, 0.012, -0.080, 0.015, 0.003),
        ("WALL", 0.001, 0.035, -0.002, 0.0002, 0.0001),
        ("TOTAL", 0.524, 0.047, -0.082, 0.015, 0.003),
    ]:
        transient = np.exp(-iters[:1500] / 300)

        cl = cl_mean + cl_amp * np.sin(2 * np.pi * iters / period)
        cl[:1500] += transient * 0.1
        cl += rng.normal(0, 5e-4, n)

        cd = cd_mean + rng.normal(0, 1e-5, n)
        cd[:1500] += transient * 0.005

        cm = cm_mean + cm_amp * np.sin(2 * np.pi * iters / period)
        cm += rng.normal(0, 2e-4, n)

        frames.append(pd.DataFrame({
            "family": fam,
            "Cl": cl,
            "Cd": cd,
            "Cm": cm,
            "iter": iters,
        }))

    df = pd.concat(frames, ignore_index=True)

    out = Path(__file__).parent / "example_data.pickle"
    with open(out, "wb") as fh:
        pickle.dump(df, fh)
    print(f"Written {len(df)} rows ({df['family'].nunique()} families) to {out}")


if __name__ == "__main__":
    main()
