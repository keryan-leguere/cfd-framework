"""Tests for the CLI interface."""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cfd_stats.cli import main


@pytest.fixture()
def pickle_file(tmp_path: Path, rng: np.random.Generator) -> Path:
    """Write a small test DataFrame as a pickle file."""
    n = 2000
    iters = np.arange(n)
    signal = 0.5 + 0.01 * np.sin(2 * np.pi * iters / 200) + rng.normal(0, 1e-4, n)
    df = pd.DataFrame({"iter": iters, "Cl": signal, "Cd": signal * 0.1})
    p = tmp_path / "test_data.pickle"
    with open(p, "wb") as fh:
        pickle.dump(df, fh)
    return p


class TestAnalyze:
    def test_basic_run(self, pickle_file: Path, tmp_path: Path) -> None:
        exit_code = main(["analyze", str(pickle_file), "-o", str(tmp_path / "out"), "--no-plots"])
        assert exit_code == 0

    def test_json_output(self, pickle_file: Path, tmp_path: Path) -> None:
        out = tmp_path / "out"
        exit_code = main(["analyze", str(pickle_file), "-o", str(out), "-f", "json", "--no-plots"])
        assert exit_code == 0
        assert (out / "report.json").exists()

    def test_missing_file(self, tmp_path: Path) -> None:
        exit_code = main(["analyze", str(tmp_path / "missing.pickle"), "--no-plots"])
        assert exit_code != 0


class TestReport:
    def test_all_formats(self, pickle_file: Path, tmp_path: Path) -> None:
        out = tmp_path / "reports"
        exit_code = main(
            ["report", str(pickle_file), "-o", str(out), "-f", "txt", "-f", "json", "-f", "html"],
        )
        assert exit_code == 0
        assert (out / "report.txt").exists()
        assert (out / "report.json").exists()
        assert (out / "report.html").exists()
