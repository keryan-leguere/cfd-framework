"""Fixtures partagées : le vol de référence écrit sous diverses conventions."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cfd_trajcast.core import rotations as rot
from cfd_trajcast.core.reperes import matrice_vers_enu
from cfd_trajcast.core.vol_reference import VolReference
from cfd_trajcast.paths import EXEMPLE_DIR

VOL = VolReference()
T = np.round(np.arange(0.0, VOL.t_apogee + 10.0, 0.05), 6)


@pytest.fixture
def vol() -> VolReference:
    return VOL


@pytest.fixture
def t() -> np.ndarray:
    return T.copy()


def dataframe_enu_quaternion(t: np.ndarray = T) -> pd.DataFrame:
    p, q = VOL.position(t), VOL.quaternion(t)
    return pd.DataFrame({"t": t, "x": p[:, 0], "y": p[:, 1], "z": p[:, 2],
                         "q0": q[:, 0], "q1": q[:, 1], "q2": q[:, 2], "q3": q[:, 3]})


def dataframe_ned_euler(t: np.ndarray = T) -> pd.DataFrame:
    p = VOL.position(t) @ matrice_vers_enu("NED")
    e = np.degrees(VOL.euler_ned(t))
    return pd.DataFrame({"t": t, "n": p[:, 0], "e": p[:, 1], "d": p[:, 2],
                         "lacet": e[:, 0], "tangage": e[:, 1], "roulis": e[:, 2]})


def q_ned(t: np.ndarray = T) -> np.ndarray:
    """Quaternion corps FRD → NED exact."""
    return rot.depuis_euler(VOL.euler_ned(t), "ZYX")


@pytest.fixture
def exemple() -> Path:
    return EXEMPLE_DIR


def _sonde_rendu() -> bool:
    import subprocess
    import sys

    r = subprocess.run([sys.executable, "-m", "cfd_trajcast.engine.rendu.pyvista_", "--sonde"],
                       capture_output=True, timeout=120, check=False)
    return r.returncode == 0


_RENDU: list[bool] = []


@pytest.fixture
def rendu() -> None:
    """Saute le test si aucune fenêtre de rendu hors écran ne fonctionne ici."""
    if not _RENDU:
        _RENDU.append(_sonde_rendu())
    if not _RENDU[0]:
        pytest.skip("rendu hors écran indisponible (cfd-trajcast diagnostic)")


@pytest.fixture(autouse=True)
def _cache_isole(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Les tests n'écrivent jamais dans le cache de l'utilisateur."""
    monkeypatch.setenv("CFD_TRAJCAST_CACHE", str(tmp_path_factory.getbasetemp() / "cache"))
