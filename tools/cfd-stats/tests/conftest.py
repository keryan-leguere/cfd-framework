"""Shared pytest fixtures for cfd-stats tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture()
def rng() -> np.random.Generator:
    return np.random.default_rng(42)


@pytest.fixture()
def converged_df(rng: np.random.Generator) -> pd.DataFrame:
    """DataFrame with a signal that converges to a constant after a transient."""
    n = 5000
    iters = np.arange(n)
    transient = np.exp(-iters[:1000] / 200) * 2.0
    steady = np.full(n - 1000, 0.0)
    signal = np.concatenate([transient, steady]) + rng.normal(0, 1e-4, n)
    return pd.DataFrame({"iter": iters, "Cl": signal})


@pytest.fixture()
def periodic_df(rng: np.random.Generator) -> pd.DataFrame:
    """DataFrame with a clearly periodic signal after a short transient."""
    n = 10000
    iters = np.arange(n)
    period = 200.0
    transient = np.exp(-iters[:500] / 100) * 0.5
    periodic = 0.5 + 0.02 * np.sin(2 * np.pi * iters / period)
    signal = periodic.copy()
    signal[:500] += transient
    signal += rng.normal(0, 1e-4, n)
    return pd.DataFrame({"iter": iters, "Cl": signal})


@pytest.fixture()
def diverging_df(rng: np.random.Generator) -> pd.DataFrame:
    """DataFrame with a diverging signal."""
    n = 2000
    iters = np.arange(n)
    signal = iters.astype(float) * 0.05 + rng.normal(0, 0.1, n)
    return pd.DataFrame({"iter": iters, "Cl": signal})


@pytest.fixture()
def normal_sample(rng: np.random.Generator) -> np.ndarray:
    """Large sample from a normal distribution."""
    return rng.normal(loc=5.0, scale=0.1, size=10000)


@pytest.fixture()
def family_df(rng: np.random.Generator) -> pd.DataFrame:
    """DataFrame with multiple families for comparison tests."""
    frames = []
    for fam, offset in [("RANS-SST", 0.5), ("LES", 0.52), ("DES", 0.51)]:
        n = 2000
        iters = np.arange(n)
        signal = offset + rng.normal(0, 0.005, n)
        frames.append(pd.DataFrame({"iter": iters, "Cl": signal, "family": fam}))
    return pd.concat(frames, ignore_index=True)
