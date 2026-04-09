"""Configuration dataclass and YAML loader for analysis settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AnalysisConfig:
    """Global configuration for the CFD statistics analysis pipeline."""

    # Convergence detection
    convergence_threshold: float = 1e-6
    plateau_window: int = 100
    cauchy_window: int = 200
    cauchy_eps: float = 1e-4

    # Periodicity
    min_periods_required: int = 10
    fft_confidence_threshold: float = 0.7
    autocorr_threshold: float = 0.5

    # Statistics
    confidence_level: float = 0.95
    bootstrap_samples: int = 1000
    max_moment_order: int = 4

    # Quality thresholds (score -> label)
    quality_thresholds: dict[str, float] = field(default_factory=dict)

    # Plotting bridge
    plot_settings: dict[str, Any] = field(default_factory=dict)

    # I/O
    output_formats: list[str] = field(default_factory=lambda: ["txt"])

    def __post_init__(self) -> None:
        if not self.quality_thresholds:
            self.quality_thresholds = {
                "excellent": 0.95,
                "good": 0.80,
                "acceptable": 0.60,
                "poor": 0.40,
            }

    def quality_label(self, score: float) -> str:
        """Map a 0-1 quality score to a human-readable label."""
        for label in ("excellent", "good", "acceptable", "poor"):
            if score >= self.quality_thresholds.get(label, 0.0):
                return label
        return "insufficient"

    @classmethod
    def from_yaml(cls, filepath: str | Path) -> AnalysisConfig:
        """Load configuration from a YAML file."""
        with open(filepath) as fh:
            raw = yaml.safe_load(fh) or {}
        return cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})

    def to_yaml(self, filepath: str | Path) -> None:
        """Persist current configuration to *filepath*."""
        from dataclasses import asdict

        with open(filepath, "w") as fh:
            yaml.safe_dump(asdict(self), fh, default_flow_style=False, sort_keys=False)
