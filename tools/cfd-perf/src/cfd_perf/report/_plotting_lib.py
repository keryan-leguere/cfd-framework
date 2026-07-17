"""Locate and import the in-house ``plotting`` library.

``scripts/post/plot/plotting`` is not pip-installable (its ``pyproject.toml``
carries tooling config only, no ``[project]`` table), so it cannot be declared
as a dependency and has to be found on disk and put on ``sys.path``.

Search order:

1. already importable (someone put it on PYTHONPATH);
2. ``$CFD_FRAMEWORK/scripts/post/plot``;
3. walking up from this file, for a checkout-relative layout.

If it cannot be found we fall back to plain Matplotlib rather than failing:
cfd-perf must stay usable when the package is copied to a cluster on its own.
Call :func:`get_plotting` for the module (or None) and check
:data:`HAS_PLOTTING`.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import cast

_REL_PATH = Path("scripts") / "post" / "plot"


def _candidate_dirs() -> list[Path]:
    candidates: list[Path] = []

    framework = os.environ.get("CFD_FRAMEWORK")
    if framework:
        candidates.append(Path(framework) / _REL_PATH)

    # src/cfd_perf/report/_plotting_lib.py -> up to the repo root
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.append(parent / _REL_PATH)

    return candidates


@lru_cache(maxsize=1)
def get_plotting() -> ModuleType | None:
    """Return the ``plotting`` module, or None if it cannot be located."""
    try:
        import plotting

        return cast(ModuleType, plotting)
    except ImportError:
        pass

    for directory in _candidate_dirs():
        if not (directory / "plotting" / "__init__.py").is_file():
            continue
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
        try:
            import plotting

            return cast(ModuleType, plotting)
        except ImportError:
            # Found the directory but its own dependencies are missing
            # (it needs pandas). Fall back rather than crash.
            return None

    return None


HAS_PLOTTING: bool = get_plotting() is not None
