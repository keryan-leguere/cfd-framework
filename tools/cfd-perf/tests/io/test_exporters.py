"""Tests for JSON and CSV exporters."""

import csv
import json
from pathlib import Path

from cfd_perf.io.exporters import export_csv, export_json, result_to_dict
from cfd_perf.optimizer.models import CandidateConfig, OptimizationResult, RejectedConfig


def _make_result() -> OptimizationResult:
    c1 = CandidateConfig(
        cores=64, time_per_iter_s=1.0, runtime_hours=1.39,
        speedup=1.0, efficiency=1.0, efficiency_loss=0.0,
        ram_total_gb=32.0, ram_per_core_gb=0.5,
    )
    c2 = CandidateConfig(
        cores=128, time_per_iter_s=0.625, runtime_hours=0.868,
        speedup=1.6, efficiency=0.8, efficiency_loss=0.2,
        ram_total_gb=32.0, ram_per_core_gb=0.25,
    )
    r1 = RejectedConfig(cores=256, reasons=("cells_per_core",))
    return OptimizationResult(
        mode="efficiency",
        optimal=c2,
        accepted=(c1, c2),
        rejected=(r1,),
        metadata={"beta": 0.25},
    )


class TestResultToDict:
    def test_keys(self) -> None:
        d = result_to_dict(_make_result())
        assert "mode" in d
        assert "optimal" in d
        assert "accepted" in d
        assert "rejected" in d
        assert "metadata" in d

    def test_json_serializable(self) -> None:
        d = result_to_dict(_make_result())
        text = json.dumps(d)
        assert isinstance(text, str)


class TestExportJson:
    def test_roundtrip(self, tmp_path: Path) -> None:
        out = tmp_path / "result.json"
        export_json(_make_result(), out)
        data = json.loads(out.read_text())
        assert data["mode"] == "efficiency"
        assert data["optimal"]["cores"] == 128
        assert len(data["accepted"]) == 2
        assert len(data["rejected"]) == 1


class TestExportCsv:
    def test_structure(self, tmp_path: Path) -> None:
        out = tmp_path / "result.csv"
        export_csv(_make_result(), out)
        with out.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 3  # 2 accepted + 1 rejected
        statuses = {r["status"] for r in rows}
        assert "accepted" in statuses
        assert "rejected" in statuses
