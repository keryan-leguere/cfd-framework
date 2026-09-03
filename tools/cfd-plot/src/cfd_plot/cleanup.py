"""cleanup — wipe a generated figure tree before a batch run.

A batch tree is generated output: rerunning a study after renaming a Y
variable, dropping a flight point or changing ``save_name`` leaves the old
files behind, and nothing in the new run overwrites them. What you then open
is a directory that mixes two studies, with no way to tell which figure came
from which — the failure this module exists to prevent.

Two modes, because "delete the figures" and "delete the directory" are not the
same promise:

``"figures"`` (the default)
    Remove only files whose extension is a known figure/report format, then
    prune the directories left empty. A stray ``notes.md`` or a data file the
    user dropped in there survives. Safe to point at a directory you share with
    something else.
``"all"``
    ``shutil.rmtree`` on the whole tree. Use it when the directory is yours
    alone.

Both refuse a handful of obviously wrong targets (see :func:`clean_figure_dir`),
because the argument is usually built by string concatenation in a study
script, and an empty variable turns ``output_base`` into ``/`` or ``$HOME``.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "FIGURE_SUFFIXES",
    "CleanReport",
    "clean_figure_dir",
]

#: Extensions treated as generated figures by ``mode="figures"``. Covers every
#: format :func:`cfd_plot.save_figure` can write plus the PDF a batch report
#: assembles.
FIGURE_SUFFIXES: frozenset[str] = frozenset(
    {
        ".svg",
        ".png",
        ".pdf",
        ".jpg",
        ".jpeg",
        ".eps",
        ".ps",
        ".emf",
        ".tif",
        ".tiff",
        ".webp",
        ".gif",
        ".mp4",
    }
)

_MODES = ("figures", "all")


@dataclass(frozen=True)
class CleanReport:
    """What :func:`clean_figure_dir` removed (or would have removed)."""

    root: Path
    mode: str
    existed: bool
    removed_files: tuple[Path, ...] = ()
    removed_dirs: tuple[Path, ...] = ()
    kept_files: tuple[Path, ...] = ()
    dry_run: bool = False

    @property
    def n_files(self) -> int:
        return len(self.removed_files)

    @property
    def n_dirs(self) -> int:
        return len(self.removed_dirs)

    def summary(self) -> str:
        """One line fit for a terminal report."""
        if not self.existed:
            return f"clean: {self.root} does not exist — nothing to do"
        verb = "would remove" if self.dry_run else "removed"
        if self.mode == "all":
            return f"clean (all): {verb} {self.root} and everything under it"
        kept = f", kept {len(self.kept_files)} non-figure file(s)" if self.kept_files else ""
        return (
            f"clean (figures): {verb} {self.n_files} file(s) and "
            f"{self.n_dirs} empty director(y|ies) under {self.root}{kept}"
        )


def _guard(root: Path) -> Path:
    """Reject targets that are almost certainly a mistake.

    ``output_base`` is nearly always assembled from variables in a study
    script. When one of them is empty the result is ``/`` or the user's home,
    and ``mode="all"`` on either is unrecoverable. These checks cost nothing
    and only ever fire on a path no one meant to pass.
    """
    resolved = root.expanduser().resolve()
    if resolved == Path(resolved.anchor):
        raise ValueError(f"Refusing to clean the filesystem root: {resolved}")
    if resolved == Path.home():
        raise ValueError(f"Refusing to clean the home directory: {resolved}")
    if len(resolved.parts) <= 2:
        raise ValueError(
            f"Refusing to clean a top-level directory: {resolved}. "
            "Point output_base at a dedicated figure directory."
        )
    if (resolved / ".git").exists():
        raise ValueError(
            f"Refusing to clean {resolved}: it is the root of a git repository. "
            "Point output_base at the figure directory, not at the project."
        )
    return resolved


def _normalize_mode(mode: bool | str) -> str:
    if mode is True:
        return "figures"
    if mode is False:
        raise ValueError("clean=False means 'do not clean'; do not call clean_figure_dir.")
    if mode not in _MODES:
        raise ValueError(f"mode must be one of {_MODES} (or True), got {mode!r}.")
    return mode


def clean_figure_dir(
    root: str | Path,
    *,
    mode: bool | str = "figures",
    suffixes: Iterable[str] | None = None,
    dry_run: bool = False,
) -> CleanReport:
    """Delete a generated figure tree under *root*.

    Parameters
    ----------
    root :
        The directory to clean — typically the ``output_base`` of a batch run.
        A missing directory is not an error: the report comes back with
        ``existed=False`` and nothing removed.
    mode :
        ``"figures"`` (or ``True``) removes only files with a figure extension
        (:data:`FIGURE_SUFFIXES`, or *suffixes*) and then prunes the
        directories that became empty. ``"all"`` removes the whole tree,
        *root* included.
    suffixes :
        Override the extensions considered figures. Leading dots optional;
        matching is case-insensitive. Ignored when ``mode="all"``.
    dry_run :
        List what would go without touching the disk.

    Returns
    -------
    CleanReport
        Paths removed, directories pruned, and — in ``"figures"`` mode — the
        non-figure files deliberately left in place.

    Raises
    ------
    ValueError
        If *root* is the filesystem root, the user's home, a top-level
        directory, or a git repository root — see the module docstring.
    NotADirectoryError
        If *root* exists but is not a directory.
    """
    resolved_mode = _normalize_mode(mode)
    root_path = _guard(Path(root))

    if not root_path.exists():
        return CleanReport(root=root_path, mode=resolved_mode, existed=False, dry_run=dry_run)
    if not root_path.is_dir():
        raise NotADirectoryError(f"clean target is not a directory: {root_path}")

    if resolved_mode == "all":
        if not dry_run:
            shutil.rmtree(root_path)
        return CleanReport(root=root_path, mode="all", existed=True, dry_run=dry_run)

    wanted = _resolve_suffixes(suffixes)
    removed_files: list[Path] = []
    kept_files: list[Path] = []
    for path in sorted(root_path.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in wanted:
            removed_files.append(path)
            if not dry_run:
                path.unlink()
        else:
            kept_files.append(path)

    removed_dirs = _prune_empty_dirs(root_path, dry_run=dry_run, ghosts=removed_files)
    return CleanReport(
        root=root_path,
        mode="figures",
        existed=True,
        removed_files=tuple(removed_files),
        removed_dirs=tuple(removed_dirs),
        kept_files=tuple(kept_files),
        dry_run=dry_run,
    )


def _resolve_suffixes(suffixes: Iterable[str] | None) -> frozenset[str]:
    if suffixes is None:
        return FIGURE_SUFFIXES
    normalized = {s.lower() if s.startswith(".") else f".{s.lower()}" for s in suffixes}
    if not normalized:
        raise ValueError("suffixes must contain at least one extension.")
    return frozenset(normalized)


def _prune_empty_dirs(root: Path, *, dry_run: bool, ghosts: Sequence[Path]) -> list[Path]:
    """Remove directories under *root* left empty, deepest first.

    *root* itself is kept: the caller is about to write into it, and a batch
    run that cleaned its own output directory out of existence would be a
    surprising thing to explain.

    Under ``dry_run`` the files in *ghosts* are still on disk, so emptiness is
    judged as if they were already gone — otherwise a dry run would report
    zero directories where a real run prunes the whole tree.
    """
    doomed = {p.resolve() for p in ghosts} if dry_run else set()
    removed: list[Path] = []
    gone: set[Path] = set()

    for directory in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not directory.is_dir():
            continue
        remaining = [
            child
            for child in directory.iterdir()
            if child.resolve() not in doomed and child.resolve() not in gone
        ]
        if remaining:
            continue
        removed.append(directory)
        gone.add(directory.resolve())
        if not dry_run:
            directory.rmdir()
    return removed
