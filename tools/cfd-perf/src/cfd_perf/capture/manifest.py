"""Manifeste de capture : l'état persistant entre `capture` et `capture --collect`.

La phase de soumission écrit un manifeste JSON décrivant chaque run lancé (cœurs,
répertoire, identifiant de job). La phase de collecte le relit pour interroger
l'état des jobs et extraire les métriques.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True)
class CaptureRun:
    """Un run pilote soumis, à une taille de cœurs donnée."""

    cores: int
    run_dir: str
    job_id: str
    submitted_at: str


@dataclass(frozen=True)
class CaptureManifest:
    """L'ensemble d'une campagne de capture."""

    adapter_id: str
    case_dir: str
    title: str
    created_at: str
    queue: str | None = None
    runs: tuple[CaptureRun, ...] = field(default_factory=tuple)

    def save(self, work_dir: Path) -> Path:
        work_dir.mkdir(parents=True, exist_ok=True)
        path = work_dir / MANIFEST_NAME
        data = asdict(self)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        return path

    @staticmethod
    def load(work_dir: Path) -> CaptureManifest:
        path = work_dir / MANIFEST_NAME
        if not path.is_file():
            raise FileNotFoundError(
                f"manifeste introuvable : {path}. Lancez d'abord la phase de soumission "
                "(cfd-perf capture --coeurs …)."
            )
        data = json.loads(path.read_text())
        runs = tuple(CaptureRun(**r) for r in data.pop("runs", []))
        return CaptureManifest(runs=runs, **data)
