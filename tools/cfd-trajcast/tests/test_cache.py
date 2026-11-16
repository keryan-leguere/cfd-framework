"""Cache disque : empreintes, aller-retour, désactivation, maillage STEP."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cfd_trajcast.data import cache


def test_empreinte_sans_ambiguite() -> None:
    assert cache.empreinte("ab", "c") != cache.empreinte("a", "bc")
    assert cache.empreinte(b"x") == cache.empreinte("x")


def test_aller_retour(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CFD_TRAJCAST_CACHE", str(tmp_path))
    assert cache.lire("essai", "k") is None
    cache.ecrire("essai", "k", {"a": np.arange(3.0), "noms": np.array(["é", "b"])})
    lu = cache.lire("essai", "k")
    assert lu is not None and np.array_equal(lu["a"], np.arange(3.0)) and list(lu["noms"]) == ["é", "b"]
    (tmp_path / "essai" / "k.npz").write_bytes(b"abime")
    assert cache.lire("essai", "k") is None  # entrée abîmée : recalcul


def test_desactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CFD_TRAJCAST_CACHE", "0")
    assert cache.dossier() is None
    assert cache.ecrire("essai", "k", {"a": np.zeros(1)}) is None


def test_dossier_par_defaut(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CFD_TRAJCAST_CACHE")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert cache.dossier() == tmp_path / "cfd-trajcast"


def test_maillage_step_en_cache(exemple: Path) -> None:
    pytest.importorskip("cascadio")
    from cfd_trajcast.data.maquette import Maquette

    kw = {"axe_nez": "-X", "axe_haut": "+Z", "longueur_imposee": 2.87}
    a = Maquette.depuis_fichier(exemple / "MAQUETTE" / "Aim9.stp", **kw)
    b = Maquette.depuis_fichier(exemple / "MAQUETTE" / "Aim9.stp", **kw)
    assert np.array_equal(a.sommets, b.sommets) and np.array_equal(a.faces, b.faces)
    assert any(c.code == "cache" for c in b.constats)
