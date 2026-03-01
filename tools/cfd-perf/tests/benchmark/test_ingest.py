"""Tests for pilot ingest (load_pilot, pilot_from_data)."""

import json
from pathlib import Path

import pandas as pd
import pytest

from cfd_perf.benchmark.ingest import load_pilot, pilot_from_data


class TestPilotFromDataDict:
    def test_from_dict_points(self) -> None:
        data = {
            "points": [
                {"cores": 64, "time_per_iter_s": 1.2, "peak_ram_total_gb": 48.0},
                {"cores": 128, "time_per_iter_s": 0.72, "peak_ram_total_gb": 48.0},
            ]
        }
        series = pilot_from_data(data, n_iterations=5000)
        assert series.n_iterations == 5000
        assert len(series.points) == 2
        assert series.points[0].cores == 64
        assert series.points[1].cores == 128
        assert series.baseline.cores == 64

    def test_from_dict_sorts_by_cores(self) -> None:
        data = {
            "points": [
                {"cores": 128, "time_per_iter_s": 0.72, "peak_ram_total_gb": 48.0},
                {"cores": 64, "time_per_iter_s": 1.2, "peak_ram_total_gb": 48.0},
            ]
        }
        series = pilot_from_data(data, n_iterations=1000)
        assert series.points[0].cores == 64
        assert series.points[1].cores == 128

    def test_from_dict_missing_points_raises(self) -> None:
        with pytest.raises(ValueError, match='"points"'):
            pilot_from_data({"n_iterations": 5000}, n_iterations=5000)

    def test_from_dict_empty_points_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one point"):
            pilot_from_data({"points": []}, n_iterations=5000)


class TestPilotFromDataDataFrame:
    def test_from_dataframe(self) -> None:
        df = pd.DataFrame([
            {"cores": 8, "time_per_iter_s": 10.0, "peak_ram_total_gb": 32.0},
            {"cores": 16, "time_per_iter_s": 5.5, "peak_ram_total_gb": 32.0},
        ])
        series = pilot_from_data(df, n_iterations=2000)
        assert series.n_iterations == 2000
        assert len(series.points) == 2
        assert series.points[0].cores == 8
        assert series.points[1].cores == 16

    def test_from_dataframe_sorts_by_cores(self) -> None:
        df = pd.DataFrame([
            {"cores": 32, "time_per_iter_s": 2.0, "peak_ram_total_gb": 64.0},
            {"cores": 16, "time_per_iter_s": 4.0, "peak_ram_total_gb": 64.0},
        ])
        series = pilot_from_data(df, n_iterations=100)
        assert series.points[0].cores == 16
        assert series.points[1].cores == 32

    def test_from_dataframe_missing_columns_raises(self) -> None:
        df = pd.DataFrame([{"cores": 8, "time_per_iter_s": 1.0}])  # missing peak_ram_total_gb
        with pytest.raises(ValueError, match="missing"):
            pilot_from_data(df, n_iterations=100)

    def test_from_dataframe_empty_raises(self) -> None:
        df = pd.DataFrame(columns=["cores", "time_per_iter_s", "peak_ram_total_gb"])
        with pytest.raises(ValueError, match="at least one row"):
            pilot_from_data(df, n_iterations=100)


class TestLoadPilot:
    def test_roundtrip_with_pilot_from_data(self, tmp_path: Path) -> None:
        data = {
            "n_iterations": 3000,
            "points": [
                {"cores": 48, "time_per_iter_s": 2.0, "peak_ram_total_gb": 96.0},
            ],
        }
        path = tmp_path / "pilot.json"
        path.write_text(json.dumps(data, indent=2))
        loaded = load_pilot(path)
        assert loaded.n_iterations == 3000
        assert len(loaded.points) == 1
        assert loaded.points[0].cores == 48
        # Same as pilot_from_data
        from_data = pilot_from_data(data, n_iterations=data["n_iterations"])
        assert from_data.n_iterations == loaded.n_iterations
        assert from_data.points[0].cores == loaded.points[0].cores
