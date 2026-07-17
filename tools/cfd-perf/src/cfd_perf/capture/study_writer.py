"""Assemble un fichier d'étude YAML à partir des points pilotes capturés.

Le dictionnaire produit respecte exactement le schéma de `cfd_perf.data.study`.
Il est systématiquement **revalidé** via `parse_study` avant d'être écrit :
cfd-perf ne génère jamais un YAML qu'il ne saurait pas relire.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cfd_perf.data.machine import Machine
from cfd_perf.data.study import parse_study
from cfd_perf.engine.recommend import DEFAULT_MAX_EFFICIENCY_LOSS, Strategy


@dataclass(frozen=True)
class CapturedPoint:
    """Un point pilote mesuré."""

    cores: int
    time_per_iter_s: float
    peak_ram_total_gb: float | None = None


@dataclass(frozen=True)
class ObjectiveSpec:
    """Paramètres d'objectif à écrire dans l'étude (tous optionnels)."""

    strategy: Strategy = Strategy.EFFICIENCY
    max_efficiency_loss: float = DEFAULT_MAX_EFFICIENCY_LOSS
    deadline_hours: float | None = None
    cores_max: int | None = None


_HEADER = (
    "# Fichier d'étude généré automatiquement par « cfd-perf capture ».\n"
    "# Les points pilotes proviennent de runs réels ; vérifiez la section machine\n"
    "# et study.n_iterations (extrait via un placeholder) avant de vous y fier.\n"
)


def _average_duplicates(points: list[CapturedPoint]) -> list[CapturedPoint]:
    """Moyenne les points partageant un même nombre de cœurs (runs répétés)."""
    groups: dict[int, list[CapturedPoint]] = defaultdict(list)
    for p in points:
        groups[p.cores].append(p)

    merged: list[CapturedPoint] = []
    for cores, grp in groups.items():
        t = sum(p.time_per_iter_s for p in grp) / len(grp)
        rams = [p.peak_ram_total_gb for p in grp if p.peak_ram_total_gb is not None]
        ram = sum(rams) / len(rams) if rams else None
        merged.append(CapturedPoint(cores=cores, time_per_iter_s=t, peak_ram_total_gb=ram))
    merged.sort(key=lambda p: p.cores)
    return merged


def build_study_dict(
    *,
    title: str,
    n_iterations: int,
    num_cells: int,
    machine: Machine,
    points: list[CapturedPoint],
    objective: ObjectiveSpec | None = None,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit le dictionnaire d'étude (schéma `cfd_perf.data.study`)."""
    obj = objective or ObjectiveSpec()
    merged = _average_duplicates(points)

    machine_sec: dict[str, Any] = {"name": machine.name, "cores_per_node": machine.cores_per_node}
    if machine.ram_per_node_gb is not None:
        machine_sec["ram_per_node_gb"] = machine.ram_per_node_gb
    if machine.max_nodes is not None:
        machine_sec["max_nodes"] = machine.max_nodes
    if machine.max_walltime_hours is not None:
        machine_sec["max_walltime_hours"] = machine.max_walltime_hours

    objective_sec: dict[str, Any] = {
        "strategy": obj.strategy.value,
        "max_efficiency_loss": obj.max_efficiency_loss,
    }
    if obj.deadline_hours is not None:
        objective_sec["deadline_hours"] = obj.deadline_hours
    if obj.cores_max is not None:
        objective_sec["cores_max"] = obj.cores_max

    pilot_sec: list[dict[str, Any]] = []
    for p in merged:
        row: dict[str, Any] = {
            "cores": p.cores,
            "time_per_iter_s": round(p.time_per_iter_s, 6),
        }
        if p.peak_ram_total_gb is not None:
            row["peak_ram_total_gb"] = round(p.peak_ram_total_gb, 3)
        pilot_sec.append(row)

    doc: dict[str, Any] = {
        "study": {"name": title, "n_iterations": n_iterations},
        "mesh": {"num_cells": num_cells},
        "machine": machine_sec,
        "objective": objective_sec,
        "pilot": pilot_sec,
    }
    if constraints:
        doc["constraints"] = constraints
    return doc


def write_study(path: Path, doc: dict[str, Any]) -> Path:
    """Valide *doc* via `parse_study` puis l'écrit en YAML. Renvoie le chemin.

    Lève `StudyError` (via `parse_study`) si le dictionnaire est invalide — on
    n'écrit jamais un fichier que le chargeur refuserait.
    """
    parse_study(doc)  # validation ; lève StudyError si invalide
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, default_flow_style=False)
    path.write_text(_HEADER + body)
    return path
