"""The shipped example must actually run — it is the package's first contact."""

from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from cfd_nozzle.paths import EXEMPLE_DIR


def test_example_directory_is_complete() -> None:
    for name in ("CAS_MOTEUR.yaml", "RUN_EXEMPLE.sh", "balayage_altitude.py"):
        assert (EXEMPLE_DIR / name).is_file(), name


def _run_sweep(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> str:
    """Execute the example script as ``__main__`` and return what it printed."""
    script = EXEMPLE_DIR / "balayage_altitude.py"
    sys.argv = [str(script), str(tmp_path)]
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(script), run_name="__main__")
    assert excinfo.value.code == 0
    return capsys.readouterr().out


def test_altitude_sweep_runs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = _run_sweep(tmp_path, capsys)
    assert "alt. adaptation" in out
    data = tmp_path / "balayage_altitude.dat"
    assert data.exists()
    rows = [line for line in data.read_text(encoding="utf-8").splitlines() if not line.startswith("#")]
    assert len(rows) == 60


def test_altitude_sweep_shows_the_area_ratio_trade_off(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A larger ε must gain in vacuum and risk separation at sea level."""
    out = _run_sweep(tmp_path, capsys)
    assert "décollement probable" in out
    lines = [line.split() for line in out.splitlines() if line.strip().startswith(("8", "16", "30"))]
    vacuum_isp = [float(parts[-2]) for parts in lines]
    assert vacuum_isp[0] < vacuum_isp[1] < vacuum_isp[2]


def test_run_exemple_script_is_executable() -> None:
    script = EXEMPLE_DIR / "RUN_EXEMPLE.sh"
    result = subprocess.run(
        ["bash", "-n", str(script)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
