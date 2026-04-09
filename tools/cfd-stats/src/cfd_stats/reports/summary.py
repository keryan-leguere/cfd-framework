"""Plain-text and JSON summary generation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def results_to_json(results: dict, *, input_file: str = "", version: str = "0.1.0") -> dict:
    """Wrap analysis *results* in a JSON-serialisable envelope with metadata."""
    per_coeff = results.get("per_coefficient", {})
    ga = results.get("global_assessment", {})

    n_iters = 0
    for data in per_coeff.values():
        moments = data.get("moments", {})
        if "mean" in moments:
            break

    return {
        "metadata": {
            "analysis_date": datetime.now(tz=timezone.utc).isoformat(),
            "version": version,
            "input_file": input_file,
            "n_coefficients": len(per_coeff),
        },
        "global": {
            "regime": ga.get("overall_regime", "unknown"),
            "all_converged": ga.get("all_converged", False),
            "quality_score": ga.get("quality_score", 0.0),
            "recommendation": ga.get("recommendation", ""),
        },
        "per_coefficient": _strip_arrays(per_coeff),
    }


def save_json(results: dict, path: str | Path, **kwargs: Any) -> Path:
    """Serialise *results* to a JSON file via :func:`results_to_json`."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = results_to_json(results, **kwargs)
    with open(out, "w") as fh:
        json.dump(payload, fh, indent=2, default=str)
    return out


def save_text(results: dict, path: str | Path) -> Path:
    """Write a human-readable plain-text summary."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ["=" * 60, "CFD Statistics Report", "=" * 60, ""]

    ga = results.get("global_assessment", {})
    lines.append(f"Overall regime     : {ga.get('overall_regime', '?')}")
    lines.append(f"All converged      : {ga.get('all_converged', '?')}")
    lines.append(f"Quality score      : {ga.get('quality_score', '?')}")
    lines.append(f"Recommendation     : {ga.get('recommendation', '')}")
    lines.append("")

    for name, data in results.get("per_coefficient", {}).items():
        lines.append("-" * 60)
        lines.append(f"  {name}")
        lines.append("-" * 60)
        regime = data.get("regime", {})
        lines.append(f"  Regime           : {regime.get('regime', '?')}")
        lines.append(f"  Quality score    : {regime.get('quality_score', '?')}")
        lines.append(f"  Transient end    : {regime.get('transient_end_iter', '?')}")
        conv = data.get("convergence", {})
        lines.append(f"  Cauchy criterion : {conv.get('cauchy_criterion', '?')}")
        lines.append(f"  Is converged     : {conv.get('is_converged', '?')}")
        moments = data.get("moments", {})
        if moments:
            lines.append(f"  Mean             : {moments.get('mean', '?')}")
            lines.append(f"  Std              : {moments.get('std', '?')}")
        lines.append("")

    with open(out, "w") as fh:
        fh.write("\n".join(lines))
    return out


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _strip_arrays(obj: Any) -> Any:
    """Recursively convert numpy arrays to lists for JSON serialisation."""
    import numpy as np

    if isinstance(obj, dict):
        return {k: _strip_arrays(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_strip_arrays(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    return obj
