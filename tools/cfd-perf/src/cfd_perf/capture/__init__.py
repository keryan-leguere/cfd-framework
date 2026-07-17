"""Capture automatique des données pilotes.

Lance les runs pilotes via un adaptateur bash solveur-spécifique, extrait
temps/itérations/RAM, et génère un fichier d'étude validé — pour supprimer la
saisie manuelle en amont de la recommandation.
"""

from __future__ import annotations

from cfd_perf.capture.adapter import ADAPTATEUR_DIR, BashAdapter, CaptureError
from cfd_perf.capture.machine_detect import MachineOverrides, detect_machine
from cfd_perf.capture.manifest import CaptureManifest, CaptureRun
from cfd_perf.capture.orchestrator import (
    CollectResult,
    SubmitResult,
    collect,
    submit,
)
from cfd_perf.capture.study_writer import (
    CapturedPoint,
    ObjectiveSpec,
    build_study_dict,
    write_study,
)

__all__ = [
    "ADAPTATEUR_DIR",
    "BashAdapter",
    "CaptureError",
    "CaptureManifest",
    "CaptureRun",
    "CapturedPoint",
    "CollectResult",
    "MachineOverrides",
    "ObjectiveSpec",
    "SubmitResult",
    "build_study_dict",
    "collect",
    "detect_machine",
    "submit",
    "write_study",
]
