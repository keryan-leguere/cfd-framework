from __future__ import annotations

from pathlib import Path
from typing import Dict, List


def clean_trace_script(trace_path: str | Path) -> str:
    """
    Load a ParaView trace script and apply simple cleanups:
    - remove trailing whitespace
    - drop empty leading/trailing lines
    Returns the cleaned source as a string.
    """
    text = Path(trace_path).read_text()
    lines = [line.rstrip() for line in text.splitlines()]
    # strip leading/trailing empty lines
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


def parameterize_trace_script(trace_path: str | Path, placeholders: Dict[str, str]) -> str:
    """
    Replace simple placeholders in a trace script and return the new content.

    Example: placeholders = {\"DATA_PATH\": \"/tmp/case.vtm\"}
    """
    text = Path(trace_path).read_text()
    for key, value in placeholders.items():
        text = text.replace(f\"{{{{{key}}}}}\", value)
    return text


def extract_trace_parameters(trace_path: str | Path) -> List[str]:
    """
    Return a list of placeholder names of the form {{NAME}} found in the trace.
    """
    text = Path(trace_path).read_text()
    params: List[str] = []
    start = 0
    while True:
        i = text.find(\"{{\", start)
        if i == -1:
            break
        j = text.find(\"}}\", i + 2)
        if j == -1:
            break
        name = text[i + 2 : j].strip()
        if name and name not in params:
            params.append(name)
        start = j + 2
    return params

