"""Pilot benchmark measurements: the observed input to the whole tool.

A "pilot" is a short run of the *real* case at a handful of core counts.
Everything downstream is fitted from these points, so this module validates
them strictly and explains what is wrong rather than failing deep inside a
least-squares solve.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_POINTS_RECOMMENDED = 4


@dataclass(frozen=True)
class PilotPoint:
    """One pilot measurement at a given core count."""

    cores: int
    time_per_iter_s: float
    peak_ram_total_gb: float | None = None

    def __post_init__(self) -> None:
        if self.cores <= 0:
            raise ValueError(f"cores must be positive, got {self.cores}")
        if self.time_per_iter_s <= 0:
            raise ValueError(
                f"time_per_iter_s must be positive, got {self.time_per_iter_s} "
                f"(at {self.cores} cores)"
            )
        if self.peak_ram_total_gb is not None and self.peak_ram_total_gb <= 0:
            raise ValueError(
                f"peak_ram_total_gb must be positive when given, got "
                f"{self.peak_ram_total_gb} (at {self.cores} cores)"
            )


@dataclass(frozen=True)
class PilotSeries:
    """Pilot measurements for one case, sorted by ascending core count."""

    points: tuple[PilotPoint, ...]
    n_iterations: int

    def __post_init__(self) -> None:
        if not self.points:
            raise ValueError("at least one pilot point is required")
        if self.n_iterations <= 0:
            raise ValueError(f"n_iterations must be positive, got {self.n_iterations}")

        cores = [p.cores for p in self.points]
        if len(set(cores)) != len(cores):
            dupes = sorted({c for c in cores if cores.count(c) > 1})
            raise ValueError(
                f"duplicate pilot core counts: {dupes}. "
                "Average the repeats into a single point before ingesting."
            )
        if cores != sorted(cores):
            raise ValueError("pilot points must be sorted by ascending core count")

    @property
    def baseline(self) -> PilotPoint:
        """Reference point: the lowest core count measured."""
        return self.points[0]

    @property
    def baseline_cores(self) -> int:
        return self.baseline.cores

    @property
    def baseline_time_per_iter_s(self) -> float:
        return self.baseline.time_per_iter_s

    @property
    def core_range(self) -> tuple[int, int]:
        return (self.points[0].cores, self.points[-1].cores)

    @property
    def peak_ram_total_gb(self) -> float | None:
        """Largest observed total RAM across pilot points, if measured.

        Uses the max rather than the baseline: total footprint creeps up with
        core count (halo duplication), and sizing on the smallest value would
        under-provision the job.
        """
        values = [p.peak_ram_total_gb for p in self.points if p.peak_ram_total_gb is not None]
        return max(values) if values else None

    def warnings(self) -> list[str]:
        """Problèmes de qualité non bloquants à signaler à l'utilisateur.

        Ce sont des avertissements : l'outil tourne quand même, mais la réponse
        ne vaut que ce que vaut le pilote derrière elle.
        """
        issues: list[str] = []

        if len(self.points) < MIN_POINTS_RECOMMENDED:
            issues.append(
                f"seulement {len(self.points)} point(s) pilote(s) ; >= {MIN_POINTS_RECOMMENDED} "
                "donne un bien meilleur ajustement du terme de communication"
            )

        lo, hi = self.core_range
        if hi / lo < 4:
            issues.append(
                f"le pilote ne couvre que {lo}-{hi} cœurs ({hi / lo:.1f}×) ; couvrez au moins "
                "4× pour que l'ajustement voie une vraie dégradation de scalabilité"
            )

        first = self.points[0]
        if len(self.points) >= 2:
            second = self.points[1]
            if second.time_per_iter_s >= first.time_per_iter_s:
                issues.append(
                    f"le temps ne s'améliore pas de {first.cores} à {second.cores} cœurs "
                    f"({first.time_per_iter_s:.3g}s -> {second.time_per_iter_s:.3g}s) ; "
                    "le cas est peut-être déjà limité par la communication au point de référence"
                )

        if any(p.peak_ram_total_gb is None for p in self.points):
            issues.append(
                "certains points pilotes n'ont pas de peak_ram_total_gb ; les contraintes "
                "mémoire seront ignorées pour ceux-là"
            )

        return issues


def pilot_from_points(
    raw: list[dict[str, float | int]],
    n_iterations: int,
) -> PilotSeries:
    """Build a PilotSeries from a list of plain dicts, sorting by core count.

    Each dict needs ``cores`` and ``time_per_iter_s``; ``peak_ram_total_gb``
    is optional.
    """
    if not raw:
        raise ValueError("pilot data must contain at least one point")

    points: list[PilotPoint] = []
    for i, entry in enumerate(raw):
        missing = {"cores", "time_per_iter_s"} - set(entry)
        if missing:
            raise ValueError(
                f"pilot point #{i + 1} is missing required key(s): {sorted(missing)}"
            )
        ram = entry.get("peak_ram_total_gb")
        points.append(
            PilotPoint(
                cores=int(entry["cores"]),
                time_per_iter_s=float(entry["time_per_iter_s"]),
                peak_ram_total_gb=float(ram) if ram is not None else None,
            )
        )

    points.sort(key=lambda p: p.cores)
    return PilotSeries(points=tuple(points), n_iterations=n_iterations)
