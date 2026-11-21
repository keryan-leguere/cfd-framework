"""Canevas Qt d'une figure Matplotlib — le seul module de ``gui`` qui importe matplotlib."""

from __future__ import annotations

from typing import Any

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt5.QtWidgets import QSizePolicy

__all__ = ["Canevas"]


class Canevas(FigureCanvasQTAgg):
    """Une ``Figure`` dans un widget Qt ; ``figure`` est passée aux vues de ``engine``."""

    def __init__(self, largeur: float = 6.0, hauteur: float = 4.0, dpi: float = 100.0, parent: Any = None) -> None:
        super().__init__(Figure(figsize=(largeur, hauteur), dpi=dpi))
        if parent is not None:
            self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(120, 80)
