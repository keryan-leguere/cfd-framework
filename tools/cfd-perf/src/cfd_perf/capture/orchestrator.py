"""Orchestration de la capture pilote en deux phases : soumettre puis collecter.

`submit()` lance un run par nombre de cœurs et écrit un manifeste, puis rend la
main (les jobs tournent). `collect()`, exécuté plus tard, relit le manifeste,
vérifie que les runs sont terminés, extrait les métriques, génère le fichier
d'étude validé, et laisse l'appelant (le CLI) lancer la recommandation.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from cfd_perf.capture.adapter import BashAdapter, CaptureError
from cfd_perf.capture.machine_detect import MachineOverrides, detect_machine
from cfd_perf.capture.manifest import CaptureManifest, CaptureRun
from cfd_perf.capture.study_writer import (
    CapturedPoint,
    ObjectiveSpec,
    build_study_dict,
    write_study,
)

WORK_DIR_DEFAULT = "PILOTE"
STUDY_NAME = "ETUDE.yaml"
_FALLBACK_N_ITERATIONS = 5000

_DONE = "DONE"
_FAILED = "FAILED"
_PENDING_STATES = {"PENDING", "RUNNING", "COMPLETING", "REQUEUED"}


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class SubmitResult:
    manifest: CaptureManifest
    manifest_path: Path


@dataclass(frozen=True)
class CollectResult:
    ready: bool
    study_path: Path | None
    points: tuple[CapturedPoint, ...] = ()
    pending: tuple[tuple[int, str], ...] = ()  # (cores, état)
    failed: tuple[int, ...] = ()
    num_cells: int = 0
    n_iterations: int = 0
    notes: tuple[str, ...] = field(default_factory=tuple)


def _copy_inputs(adapter: BashAdapter, case_dir: Path, run_dir: Path) -> list[str]:
    """Copie best-effort des éléments déclarés par l'adaptateur. Renvoie les manquants."""
    missing: list[str] = []
    for element in adapter.elements_a_copier():
        src = case_dir / element
        if not src.exists():
            missing.append(element)
            continue
        dst = run_dir / element
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    return missing


def submit(
    *,
    case_dir: Path,
    adapter: BashAdapter,
    coeurs: list[int],
    work_dir: Path,
    queue: str | None = None,
) -> SubmitResult:
    """Phase 1 : prépare et soumet un run par nombre de cœurs ; écrit le manifeste."""
    if not coeurs:
        raise CaptureError("la liste de cœurs est vide (--coeurs)")
    if not adapter.verifier_installation():
        raise CaptureError(
            f"l'adaptateur « {adapter.adapter_id} » signale que le solveur n'est pas installé"
        )

    case_dir = case_dir.resolve()
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    runs: list[CaptureRun] = []
    for cores in coeurs:
        run_dir = work_dir / f"{adapter.adapter_id}_{cores}_{_timestamp()}"
        run_dir.mkdir(parents=True, exist_ok=True)
        _copy_inputs(adapter, case_dir, run_dir)
        adapter.preparer(run_dir, cores)
        job_id = adapter.soumettre(run_dir, cores, queue)
        runs.append(
            CaptureRun(
                cores=cores,
                run_dir=str(run_dir),
                job_id=job_id,
                submitted_at=_now_iso(),
            )
        )

    manifest = CaptureManifest(
        adapter_id=adapter.adapter_id,
        case_dir=str(case_dir),
        title=case_dir.name,
        created_at=_now_iso(),
        queue=queue,
        runs=tuple(runs),
    )
    path = manifest.save(work_dir)
    return SubmitResult(manifest=manifest, manifest_path=path)


def collect(
    *,
    work_dir: Path,
    adapter: BashAdapter,
    machine_overrides: MachineOverrides | None = None,
    machine_name: str | None = None,
    num_cells: int | None = None,
    n_iterations: int | None = None,
    objective: ObjectiveSpec | None = None,
    constraints: dict[str, object] | None = None,
) -> CollectResult:
    """Phase 2 : vérifie l'état des runs, extrait les métriques, écrit l'étude."""
    manifest = CaptureManifest.load(work_dir)
    case_dir = Path(manifest.case_dir)

    pending: list[tuple[int, str]] = []
    failed: list[int] = []
    points: list[CapturedPoint] = []

    for run in manifest.runs:
        run_dir = Path(run.run_dir)
        state = adapter.etat(run_dir, run.job_id).strip().upper()
        if state == _FAILED:
            failed.append(run.cores)
            continue
        if state != _DONE:
            pending.append((run.cores, state or "?"))
            continue

        temps = adapter.temps_total_s(run_dir)
        n_iter = adapter.nb_iterations(run_dir)
        if n_iter <= 0:
            failed.append(run.cores)
            continue
        ram = adapter.ram_crete_gb(run_dir, run.job_id)
        points.append(
            CapturedPoint(
                cores=run.cores,
                time_per_iter_s=temps / n_iter,
                peak_ram_total_gb=ram,
            )
        )

    if pending:
        return CollectResult(
            ready=False,
            study_path=None,
            pending=tuple(sorted(pending)),
            failed=tuple(sorted(failed)),
        )

    notes: list[str] = []
    if failed:
        notes.append(
            f"{len(failed)} run(s) en échec, ignoré(s) : {sorted(failed)}"
        )
    if not points:
        return CollectResult(
            ready=True, study_path=None, failed=tuple(sorted(failed)), notes=tuple(notes)
        )

    resolved_cells = num_cells if num_cells is not None else adapter.nb_cellules(case_dir)
    resolved_niter = n_iterations
    if resolved_niter is None:
        resolved_niter = adapter.cible_iterations(case_dir)
    if resolved_niter is None or resolved_niter <= 0:
        resolved_niter = _FALLBACK_N_ITERATIONS
        notes.append(
            f"study.n_iterations non extrait ; valeur par défaut {_FALLBACK_N_ITERATIONS} "
            "(placeholder — corrigez-la ou passez --n-iterations)"
        )

    machine = detect_machine(overrides=machine_overrides, name=machine_name)

    doc = build_study_dict(
        title=manifest.title,
        n_iterations=resolved_niter,
        num_cells=resolved_cells,
        machine=machine,
        points=points,
        objective=objective,
        constraints=constraints,
    )
    study_path = write_study(case_dir / STUDY_NAME, doc)

    return CollectResult(
        ready=True,
        study_path=study_path,
        points=tuple(points),
        failed=tuple(sorted(failed)),
        num_cells=resolved_cells,
        n_iterations=resolved_niter,
        notes=tuple(notes),
    )
