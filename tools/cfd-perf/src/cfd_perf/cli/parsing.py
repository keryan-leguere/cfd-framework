"""Shared CLI parsing helpers."""

from __future__ import annotations

import re


_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(h|m|s)$", re.IGNORECASE)


def parse_duration_hours(text: str) -> float:
    """Parse a human duration string like ``6h``, ``90m``, ``5400s`` to hours.

    Raises ValueError on unrecognised format.
    """
    m = _DURATION_RE.match(text.strip())
    if not m:
        raise ValueError(f"Invalid duration format: {text!r}. Expected e.g. 6h, 90m, 5400s")

    value = float(m.group(1))
    unit = m.group(2).lower()
    if unit == "h":
        return value
    if unit == "m":
        return value / 60.0
    return value / 3600.0
