"""Renseigne automatiquement les paramètres machine du fichier d'étude.

Ordre de priorité (le premier défini gagne, champ par champ) :
    1. surcharges explicites (options CLI)
    2. détection automatique (scontrol / nproc / /proc/meminfo)
    3. ADAPTATEUR/hotes.yaml, indexé par nom d'hôte (préfixe le plus long)
    4. la clé « defaut » de hotes.yaml
    5. valeurs par défaut de Machine (cores_per_node=1)

Toutes les commandes système sont protégées (shutil.which + try/except) : hors
calculateur, la détection échoue silencieusement et on retombe sur les valeurs
suivantes. Aucune dépendance vers d'autres sous-projets.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cfd_perf.capture.adapter import ADAPTATEUR_DIR
from cfd_perf.data.machine import Machine

HOTES_YAML = ADAPTATEUR_DIR / "hotes.yaml"
_SCONTROL_TIMEOUT_S = 10


@dataclass(frozen=True)
class MachineOverrides:
    """Valeurs imposées par l'utilisateur (aucune détection pour celles-ci)."""

    cores_per_node: int | None = None
    ram_per_node_gb: float | None = None
    max_nodes: int | None = None
    max_walltime_hours: float | None = None


def _run(cmd: list[str]) -> str | None:
    """Exécute une commande courte ; renvoie stdout, ou None si indisponible."""
    if shutil.which(cmd[0]) is None:
        return None
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=_SCONTROL_TIMEOUT_S, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _scontrol_field(node_text: str, key: str) -> str | None:
    """Extrait « Key=Value » d'une sortie scontrol (paires espacées)."""
    for token in node_text.split():
        if token.startswith(f"{key}="):
            return token[len(key) + 1 :]
    return None


def _detect_cores_per_node() -> int | None:
    host = socket.gethostname()
    node_text = _run(["scontrol", "show", "node", host])
    if node_text:
        val = _scontrol_field(node_text, "CPUTot")
        if val and val.isdigit() and int(val) > 0:
            return int(val)
    nproc = _run(["nproc"])
    if nproc and nproc.strip().isdigit():
        n = int(nproc.strip())
        if n > 0:
            return n
    return None


def _detect_ram_per_node_gb() -> float | None:
    host = socket.gethostname()
    node_text = _run(["scontrol", "show", "node", host])
    if node_text:
        val = _scontrol_field(node_text, "RealMemory")  # Mo
        if val and val.replace(".", "", 1).isdigit() and float(val) > 0:
            return round(float(val) / 1024.0, 1)
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        for line in meminfo.read_text().splitlines():
            if line.startswith("MemTotal:"):
                kb = float(line.split()[1])  # kio
                return round(kb / (1024.0 * 1024.0), 1)
    return None


def _load_hotes(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _hotes_entry(hotes: dict[str, Any], hostname: str) -> dict[str, Any]:
    """Entrée hotes.yaml matchant l'hôte : le préfixe (clé) le plus long."""
    best: dict[str, Any] = {}
    best_len = -1
    for key, val in hotes.items():
        if key == "defaut" or not isinstance(val, dict):
            continue
        if hostname.startswith(key) and len(key) > best_len:
            best, best_len = val, len(key)
    if not best and isinstance(hotes.get("defaut"), dict):
        best = hotes["defaut"]
    return best


def detect_machine(
    *,
    overrides: MachineOverrides | None = None,
    hotes_path: Path | None = None,
    name: str | None = None,
) -> Machine:
    """Construit un `Machine` du mieux possible. Ne lève jamais sur l'absence d'infos."""
    ov = overrides or MachineOverrides()
    hotes = _load_hotes(hotes_path or HOTES_YAML)
    hostname = socket.gethostname()
    entry = _hotes_entry(hotes, hostname)

    def pick(field: str, detector: Any) -> Any:
        cli = getattr(ov, field)
        if cli is not None:
            return cli
        detected = detector() if detector is not None else None
        if detected is not None:
            return detected
        return entry.get(field)

    cores_per_node = pick("cores_per_node", _detect_cores_per_node) or 1
    ram_per_node_gb = pick("ram_per_node_gb", _detect_ram_per_node_gb)
    # max_nodes / max_walltime ne sont pas détectés de façon fiable : CLI ou hotes.
    max_nodes = ov.max_nodes if ov.max_nodes is not None else entry.get("max_nodes")
    max_walltime = (
        ov.max_walltime_hours
        if ov.max_walltime_hours is not None
        else entry.get("max_walltime_hours")
    )

    return Machine(
        name=name or hostname,
        cores_per_node=int(cores_per_node),
        ram_per_node_gb=float(ram_per_node_gb) if ram_per_node_gb is not None else None,
        max_nodes=int(max_nodes) if max_nodes is not None else None,
        max_walltime_hours=float(max_walltime) if max_walltime is not None else None,
    )
