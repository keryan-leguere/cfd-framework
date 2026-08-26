"""Loading a lot of dispersed trajectories from CSV files.

One file per shot. Each file carries the eight mandatory columns of
:data:`~cfd_traj.data.columns.REQUIRED_COLUMNS` plus any number of extra
parameter columns under any names; the extras are discovered, never assumed.

What is an error and what is a note is a deliberate distinction. A missing
mandatory column, or two files that disagree about which columns exist, makes
the lot unusable and raises. A non-monotone time vector, an all-NaN shot or an
unusually short shot are *data-quality* facts: they are recorded, reported in
yellow, and the analysis carries on -- a lot with one odd shot in it is still
worth looking at, and refusing to load it would just push the user into editing
their data before they have seen it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from cfd_traj.data.columns import REQUIRED_COLUMNS, RESERVED_COLUMNS, SHOT_COLUMN


class DatasetError(ValueError):
    """A lot of trajectories that cannot be read.

    Carries the offending file path so the CLI can point at it directly.
    """

    def __init__(self, message: str, *, path: Path | None = None) -> None:
        self.path = path
        super().__init__(f"{path} : {message}" if path is not None else message)


@dataclass(frozen=True)
class Shot:
    """One trajectory file, and what is worth knowing about it."""

    name: str
    path: Path
    n_rows: int
    t_min: float
    t_max: float
    n_nan_rows: int = 0
    time_is_monotone: bool = True

    @property
    def duration(self) -> float:
        """Time span of the shot."""
        return self.t_max - self.t_min


@dataclass(frozen=True)
class TrajectoryDataset:
    """A whole Monte-Carlo lot, as one long frame plus its metadata.

    The frame is mutable while the dataclass is frozen: the immutability is a
    façade, and copying a frame of millions of rows on every operation would be
    too expensive to be worth it. The rule that keeps this honest is that
    nothing outside this module writes to ``frame`` -- every modification goes
    through :meth:`with_columns`, which rebuilds.
    """

    frame: pd.DataFrame
    shots: tuple[Shot, ...]
    source_columns: tuple[str, ...]
    extra_columns: tuple[str, ...]
    derived_columns: tuple[str, ...] = ()
    n_dropped_rows: int = 0
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        missing = [c for c in REQUIRED_COLUMNS if c not in self.frame.columns]
        if missing:
            raise DatasetError(f"colonne(s) requise(s) absente(s) de la trame : {missing}")
        if SHOT_COLUMN not in self.frame.columns:
            raise DatasetError(f"la trame ne porte pas la colonne « {SHOT_COLUMN} »")

    @property
    def n_shots(self) -> int:
        """Number of trajectories in the lot."""
        return len(self.shots)

    @property
    def n_rows(self) -> int:
        """Total number of flight points."""
        return len(self.frame)

    @property
    def columns(self) -> tuple[str, ...]:
        """Every column of the frame, source order first then derived."""
        return tuple(str(c) for c in self.frame.columns)

    @property
    def mach_range(self) -> tuple[float, float]:
        """Extreme Mach numbers of the lot."""
        mach = self.values("Mach")
        finite = mach[np.isfinite(mach)]
        if finite.size == 0:
            return (float("nan"), float("nan"))
        return (float(finite.min()), float(finite.max()))

    @property
    def time_span(self) -> tuple[float, float]:
        """Earliest and latest time over the whole lot."""
        t = self.values("time")
        finite = t[np.isfinite(t)]
        if finite.size == 0:
            return (float("nan"), float("nan"))
        return (float(finite.min()), float(finite.max()))

    def values(self, name: str) -> NDArray[np.float64]:
        """One column as a float array."""
        if name not in self.frame.columns:
            raise KeyError(f"colonne « {name} » absente ; colonnes disponibles : {self.columns}")
        return np.asarray(self.frame[name].to_numpy(), dtype=np.float64)

    def matrix(self, names: Sequence[str]) -> NDArray[np.float64]:
        """Several columns as an ``(n, len(names))`` array, in the order given."""
        if not names:
            return np.zeros((self.n_rows, 0), dtype=np.float64)
        return np.column_stack([self.values(n) for n in names])

    def shot_labels(self) -> NDArray[np.object_]:
        """The shot name of every row."""
        return np.asarray(self.frame[SHOT_COLUMN].to_numpy(), dtype=object)

    def column_values(self) -> dict[str, NDArray[np.float64]]:
        """Every numeric column as a float array, for role detection."""
        out: dict[str, NDArray[np.float64]] = {}
        for name in self.columns:
            if name == SHOT_COLUMN:
                continue
            out[name] = self.values(name)
        return out

    def with_columns(self, new: Mapping[str, NDArray[np.float64]]) -> TrajectoryDataset:
        """Return a new dataset carrying additional (or refreshed) columns."""
        frame = self.frame.copy()
        for name, values in new.items():
            frame[name] = np.asarray(values)
        derived = tuple(dict.fromkeys([*self.derived_columns, *new]))
        return replace(self, frame=frame, derived_columns=derived)

    def with_notes(self, notes: Sequence[str]) -> TrajectoryDataset:
        """Return a new dataset with extra notes appended."""
        return replace(self, notes=(*self.notes, *notes))


def _resolve_paths(
    source: str | Path | Sequence[str | Path], *, pattern: str
) -> tuple[list[Path], Path | None]:
    """Turn a directory, a glob, a single file or a list into a sorted file list."""
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.is_dir():
            return sorted(path.glob(pattern)), path
        if path.exists():
            return [path], path.parent
        matches = sorted(Path(path.parent or ".").glob(path.name))
        if matches:
            return matches, path.parent or Path()
        raise DatasetError("source introuvable", path=path)

    paths = [Path(p) for p in source]
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise DatasetError("fichier introuvable", path=missing[0])
    return sorted(paths), None


def _read_one(path: Path) -> pd.DataFrame:
    """Read a single CSV, with the failure modes spelled out in French."""
    try:
        frame = pd.read_csv(path)
    except pd.errors.EmptyDataError as exc:
        raise DatasetError("fichier vide", path=path) from exc
    except UnicodeDecodeError as exc:
        raise DatasetError("fichier illisible (encodage non UTF-8)", path=path) from exc
    except pd.errors.ParserError as exc:
        raise DatasetError(f"CSV mal formé : {exc}", path=path) from exc

    if frame.shape[1] == 1 and frame.shape[0] >= 0:
        header = str(frame.columns[0])
        if ";" in header or "\t" in header:
            raise DatasetError(
                "une seule colonne détectée : le séparateur attendu est la virgule, "
                "et le séparateur décimal le point",
                path=path,
            )
    if len(frame) == 0:
        raise DatasetError("fichier sans aucune ligne de données", path=path)
    return frame


def load_dataset(
    source: str | Path | Sequence[str | Path],
    *,
    pattern: str = "*.csv",
    max_shots: int | None = None,
    drop_nan_rows: bool = False,
) -> TrajectoryDataset:
    """Load a lot of trajectories from a directory, a glob, a file or a list of files.

    Shots are loaded in sorted path order so two runs always produce the same
    frame -- reproducibility of the plan starts here.
    """
    paths, _ = _resolve_paths(source, pattern=pattern)
    if not paths:
        raise DatasetError(f"aucun fichier ne correspond à « {pattern} »", path=Path(str(source)))

    notes: list[str] = []
    if max_shots is not None and len(paths) > max_shots:
        notes.append(f"{len(paths)} fichiers trouvés, {max_shots} retenus (--max-tirs)")
        paths = paths[:max_shots]

    frames: list[pd.DataFrame] = []
    shots: list[Shot] = []
    canonical: tuple[str, ...] | None = None
    canonical_path: Path | None = None
    dropped = 0

    for path in paths:
        frame = _read_one(path)
        columns = tuple(str(c) for c in frame.columns)

        missing = [c for c in REQUIRED_COLUMNS if c not in columns]
        if missing:
            raise DatasetError(f"colonne(s) requise(s) absente(s) : {missing}", path=path)

        clashes = sorted(set(columns) & RESERVED_COLUMNS)
        if clashes:
            raise DatasetError(
                f"nom(s) de colonne réservé(s) au calcul : {clashes} ; renommez-les", path=path
            )

        if canonical is None:
            canonical, canonical_path = columns, path
        elif set(columns) != set(canonical):
            surplus = sorted(set(columns) - set(canonical))
            absent = sorted(set(canonical) - set(columns))
            raise DatasetError(
                f"colonnes incohérentes avec {canonical_path} : "
                f"en trop {surplus}, manquantes {absent}",
                path=path,
            )

        frame = frame[list(canonical)]
        numeric = frame.apply(pd.to_numeric, errors="coerce")

        n_nan_rows = int(numeric.isna().any(axis=1).sum())
        if n_nan_rows == len(numeric):
            notes.append(f"{path.name} : aucune ligne exploitable (valeurs toutes manquantes)")

        if drop_nan_rows and n_nan_rows:
            keep = ~numeric.isna().any(axis=1)
            dropped += n_nan_rows
            numeric = numeric[keep]
            if len(numeric) == 0:
                notes.append(f"{path.name} : toutes les lignes supprimées (--sans-nan)")
                continue

        time = np.asarray(numeric["time"].to_numpy(), dtype=np.float64)
        finite_time = time[np.isfinite(time)]
        monotone = bool(finite_time.size <= 1 or np.all(np.diff(finite_time) > 0))
        if not monotone:
            notes.append(f"{path.name} : temps non strictement croissant")

        numeric = numeric.assign(**{SHOT_COLUMN: path.stem})
        frames.append(numeric)
        shots.append(
            Shot(
                name=path.stem,
                path=path,
                n_rows=len(numeric),
                t_min=float(finite_time.min()) if finite_time.size else float("nan"),
                t_max=float(finite_time.max()) if finite_time.size else float("nan"),
                n_nan_rows=n_nan_rows,
                time_is_monotone=monotone,
            )
        )

    if not frames:
        raise DatasetError("aucune ligne exploitable dans le lot", path=Path(str(source)))

    assert canonical is not None
    combined = pd.concat(frames, ignore_index=True)
    extra = tuple(c for c in canonical if c not in REQUIRED_COLUMNS)

    return TrajectoryDataset(
        frame=combined,
        shots=tuple(shots),
        source_columns=tuple(canonical),
        extra_columns=extra,
        n_dropped_rows=dropped,
        notes=tuple(notes),
    )
