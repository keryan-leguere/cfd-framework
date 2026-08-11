"""Locations of the data directories shipped inside the package.

The example is package data, so a plain ``pip install cfd-nozzle`` is
self-sufficient: nothing here is resolved relative to the repository.
"""

from __future__ import annotations

from pathlib import Path

#: Root of the installed package.
PACKAGE_DIR = Path(__file__).resolve().parent

#: Ready-to-run example, copied out by ``cfd-nozzle example``.
EXEMPLE_DIR = PACKAGE_DIR / "01_EXEMPLE"

__all__ = ["EXEMPLE_DIR", "PACKAGE_DIR"]
