"""JSON and CSV export for optimization results."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cfd_perf.optimizer.models import CandidateConfig, OptimizationResult, RejectedConfig

_CANDIDATE_FIELDS = [f.name for f in CandidateConfig.__dataclass_fields__.values()]
_CSV_COLUMNS = [*_CANDIDATE_FIELDS, "status", "reject_reasons"]


def _candidate_row(c: CandidateConfig, status: str = "accepted", reasons: str = "") -> dict[str, Any]:
    row = asdict(c)
    row["status"] = status
    row["reject_reasons"] = reasons
    return row


def result_to_dict(result: OptimizationResult) -> dict[str, Any]:
    """Serialize an OptimizationResult to a JSON-friendly dict."""
    return {
        "mode": result.mode,
        "metadata": result.metadata,
        "optimal": asdict(result.optimal) if result.optimal else None,
        "accepted": [asdict(c) for c in result.accepted],
        "rejected": [{"cores": r.cores, "reasons": list(r.reasons)} for r in result.rejected],
    }


def export_json(result: OptimizationResult, path: Path) -> Path:
    """Write result to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result_to_dict(result), indent=2))
    return path


def export_csv(result: OptimizationResult, path: Path) -> Path:
    """Write result to a CSV file (one row per candidate + rejected)."""
    path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for c in result.accepted:
        rows.append(_candidate_row(c, "accepted"))

    for r in result.rejected:
        reject_row: dict[str, Any] = {col: "" for col in _CSV_COLUMNS}
        reject_row["cores"] = r.cores
        reject_row["status"] = "rejected"
        reject_row["reject_reasons"] = ";".join(r.reasons)
        rows.append(reject_row)

    rows.sort(key=lambda r: int(r.get("cores", 0)))

    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return path
