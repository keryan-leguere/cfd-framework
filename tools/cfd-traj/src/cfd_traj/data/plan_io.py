"""Writing and reading back the envelope table and the design of experiments.

The plan is written as a tidy CSV -- one row per computation case -- because
that is what gets handed to whoever launches the runs, opened in a spreadsheet
in a design review, and diffed between two revisions of the study. The column
order is *derived from the envelope*, never from a hardcoded list, so a lot
with twelve generic parameters produces twelve columns without a line of code
knowing their names.

Numbers are written with a machine decimal point. French formatting belongs to
the terminal report, not to a file another program has to read.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

#: Columns that frame the variable ones, before and after.
LEADING_COLUMNS: tuple[str, ...] = ("node_id", "bande", "mach_bas", "mach_haut")
TRAILING_COLUMNS: tuple[str, ...] = (
    "braquage",
    "dl",
    "dm",
    "dn",
    "configuration",
    "cout_relatif",
    "composantes_nulles",
    "origine",
)


def plan_columns(variable_names: Sequence[str]) -> tuple[str, ...]:
    """Full column order of the plan CSV, given the envelope's variables."""
    return (*LEADING_COLUMNS, *variable_names, *TRAILING_COLUMNS)


def write_plan_csv(frame: pd.DataFrame, path: str | Path) -> Path:
    """Write the plan as a tidy CSV."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False, float_format="%.10g")
    return target


def read_plan_csv(path: str | Path) -> pd.DataFrame:
    """Read a plan back. The inverse of :func:`write_plan_csv`."""
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"plan introuvable : {target}")
    return pd.read_csv(target)


def write_plan_yaml(payload: dict[str, Any], path: str | Path) -> Path:
    """Write the plan grouped by band, for readers who prefer structure to rows."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    return target


def write_envelope_csv(rows: Sequence[dict[str, Any]], path: str | Path) -> Path:
    """Write the envelope table: one row per (band, variable)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(list(rows)).to_csv(target, index=False, float_format="%.10g")
    return target


def write_offenders_csv(rows: Sequence[dict[str, Any]], path: str | Path) -> Path:
    """Write every out-of-domain trajectory point found by the coverage check."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        frame = pd.DataFrame(
            columns=[
                "tir",
                "ligne",
                "temps",
                "mach",
                "variable",
                "valeur",
                "borne",
                "cote",
                "exces",
            ]
        )
    frame.to_csv(target, index=False, float_format="%.10g")
    return target
