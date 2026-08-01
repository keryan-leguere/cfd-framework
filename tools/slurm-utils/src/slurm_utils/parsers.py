"""Parsers for Slurm command output (pipe-delimited ``-o`` formats)."""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# squeue
# ---------------------------------------------------------------------------

SQUEUE_FORMAT = "%i|%j|%P|%T|%u|%M|%l|%D|%C|%m|%r"
SQUEUE_HEADERS = [
    "JOBID", "NAME", "PARTITION", "STATE", "USER",
    "TIME", "TIME_LIMIT", "NODES", "CPUS", "MIN_MEMORY", "REASON",
]


@dataclass
class JobRecord:
    jobid: str
    name: str
    partition: str
    state: str
    user: str
    time_used: str
    time_limit: str
    nodes: str
    cpus: str
    min_memory: str
    reason: str


def parse_squeue(stdout: str) -> list[JobRecord]:
    rows: list[JobRecord] = []
    for line in stdout.strip().splitlines()[1:]:  # skip header
        parts = line.split("|")
        if len(parts) < len(SQUEUE_HEADERS):
            continue
        rows.append(JobRecord(*parts[: len(SQUEUE_HEADERS)]))
    return rows


# ---------------------------------------------------------------------------
# sinfo
# ---------------------------------------------------------------------------

SINFO_FORMAT = "%P|%a|%l|%D|%T|%c|%m|%f|%N|%C"
SINFO_HEADERS = [
    "PARTITION", "AVAIL", "TIMELIMIT", "NODES", "STATE",
    "CPUS", "MEMORY", "FEATURES", "NODELIST", "CPUS_AIOT",
]


@dataclass
class PartitionRecord:
    partition: str
    avail: str
    timelimit: str
    nodes: int
    state: str
    cpus_per_node: int
    memory_mb: int
    features: str
    nodelist: str
    cpus_aiot: str  # allocated/idle/other/total

    @property
    def is_up(self) -> bool:
        return self.avail.lower() == "up"

    @property
    def name_clean(self) -> str:
        return self.partition.rstrip("*")

    @property
    def timelimit_minutes(self) -> int | None:
        return _parse_timelimit(self.timelimit)


def _safe_int(val: str) -> int:
    cleaned = re.sub(r"[^\d]", "", val)
    return int(cleaned) if cleaned else 0


def _parse_timelimit(raw: str) -> int | None:
    """Convert Slurm time-limit string to minutes.  Returns None for 'infinite'."""
    raw = raw.strip().lower()
    if raw in ("infinite", "n/a", ""):
        return None

    # D-HH:MM:SS or HH:MM:SS or MM:SS
    days = 0
    if "-" in raw:
        d, rest = raw.split("-", 1)
        days = int(d)
        raw = rest

    parts = raw.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return days * 24 * 60 + int(h) * 60 + int(m) + (1 if int(s) > 0 else 0)
    if len(parts) == 2:
        m, s = parts
        return days * 24 * 60 + int(m) + (1 if int(s) > 0 else 0)
    return None


def parse_sinfo(stdout: str) -> list[PartitionRecord]:
    rows: list[PartitionRecord] = []
    for line in stdout.strip().splitlines()[1:]:
        parts = line.split("|")
        if len(parts) < len(SINFO_HEADERS):
            continue
        rows.append(PartitionRecord(
            partition=parts[0],
            avail=parts[1],
            timelimit=parts[2],
            nodes=_safe_int(parts[3]),
            state=parts[4],
            cpus_per_node=_safe_int(parts[5]),
            memory_mb=_safe_int(parts[6]),
            features=parts[7],
            nodelist=parts[8],
            cpus_aiot=parts[9] if len(parts) > 9 else "",
        ))
    return rows


# ---------------------------------------------------------------------------
# sprio
# ---------------------------------------------------------------------------

SPRIO_FORMAT = "%i|%r|%Y|%A|%B|%F|%J|%N|%P|%Q|%T"
SPRIO_HEADERS = [
    "JOBID", "USER", "PRIORITY", "AGE", "ASSOC",
    "FAIRSHARE", "JOBSIZE", "NICE", "PARTITION", "QOS", "TRES",
]


@dataclass
class PriorityRecord:
    jobid: str
    user: str
    priority: str
    age: str
    assoc: str
    fairshare: str
    jobsize: str
    nice: str
    partition: str
    qos: str
    tres: str


def parse_sprio(stdout: str) -> list[PriorityRecord]:
    rows: list[PriorityRecord] = []
    for line in stdout.strip().splitlines()[1:]:
        parts = line.split("|")
        if len(parts) < len(SPRIO_HEADERS):
            continue
        rows.append(PriorityRecord(*parts[: len(SPRIO_HEADERS)]))
    return rows


# ---------------------------------------------------------------------------
# Helpers for squeue pending/running splitting
# ---------------------------------------------------------------------------


def parse_time_to_seconds(slurm_time: str) -> int:
    """Parse a Slurm time string (D-HH:MM:SS / HH:MM:SS / MM:SS) to seconds."""
    raw = slurm_time.strip()
    if not raw or raw.lower() in ("n/a", "invalid", "unknown"):
        return 0
    days = 0
    if "-" in raw:
        d, rest = raw.split("-", 1)
        days = int(d)
        raw = rest
    parts = raw.split(":")
    if len(parts) == 3:
        return days * 86400 + int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    if len(parts) == 2:
        return days * 86400 + int(parts[0]) * 60 + int(parts[1])
    return 0
