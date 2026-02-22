"""Low-level wrapper around Slurm CLI commands.

Every public function runs a Slurm binary via *subprocess* and returns
parsed stdout lines.  Errors are surfaced as :class:`SlurmCommandError`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field


class SlurmCommandError(RuntimeError):
    """Raised when a Slurm command fails or is not found."""


@dataclass(frozen=True)
class SlurmResult:
    """Raw result from a Slurm command."""

    returncode: int
    stdout: str
    stderr: str
    command: list[str] = field(repr=False)


def _find_binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise SlurmCommandError(
            f"'{name}' not found on PATH. Are you on a Slurm login/submit node?"
        )
    return path


def run_slurm(
    argv: list[str],
    *,
    check: bool = True,
    timeout: int = 30,
) -> SlurmResult:
    """Run *argv* (e.g. ``["squeue", "-u", "me"]``) and return a :class:`SlurmResult`.

    Parameters
    ----------
    argv:
        Full argument vector.  The first element must be a Slurm binary name.
    check:
        If *True* (default), raise :class:`SlurmCommandError` on non-zero exit.
    timeout:
        Seconds before the subprocess is killed.
    """
    binary = _find_binary(argv[0])
    argv = [binary, *argv[1:]]

    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ},
        )
    except subprocess.TimeoutExpired as exc:
        raise SlurmCommandError(
            f"Command timed out after {timeout}s: {' '.join(argv)}"
        ) from exc

    result = SlurmResult(
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        command=argv,
    )

    if check and proc.returncode != 0:
        msg = proc.stderr.strip() or f"exit code {proc.returncode}"
        raise SlurmCommandError(f"{argv[0]} failed: {msg}")

    return result


def current_user() -> str:
    """Return the current Unix username."""
    return os.environ.get("USER") or os.getlogin()
