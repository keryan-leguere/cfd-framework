"""``cfd-trajcast check`` et ``exemple`` : codes de retour."""

from __future__ import annotations

from pathlib import Path

import pytest

from cfd_trajcast.cli.main import EXIT_CONTROLE, EXIT_ERREUR_ENTREE, EXIT_OK, main


def test_exemple_puis_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dest = tmp_path / "ex"
    assert main(["exemple", str(dest)]) == EXIT_OK
    assert (dest / "MAQUETTE" / "Aim9.stl").is_file()
    assert main(["exemple", str(dest)]) == EXIT_ERREUR_ENTREE
    assert main(["check", str(dest / "CONFIG.yaml")]) == EXIT_OK
    assert "conforme" in capsys.readouterr().out


def test_check_coherence_optionnelle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["exemple", str(tmp_path / "ex")])
    cfg = tmp_path / "ex" / "CONFIG.yaml"
    assert main(["check", str(cfg)]) == EXIT_OK
    assert "cohérent" not in capsys.readouterr().out
    assert main(["check", "--coherence", str(cfg)]) == EXIT_OK
    assert "axe du nez cohérent" in capsys.readouterr().out


def test_check_erreur_controle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from cfd_trajcast.cli import main as module
    from cfd_trajcast.data.constats import ERREUR, Constat

    main(["exemple", str(tmp_path / "ex")])
    monkeypatch.setattr(module, "verifier", lambda *a, **k: [Constat(ERREUR, "x", "faux")])
    assert main(["check", str(tmp_path / "ex" / "CONFIG.yaml")]) == EXIT_CONTROLE


def test_check_fichier_absent(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", "nexiste_pas.yaml"]) == EXIT_ERREUR_ENTREE
    assert "introuvable" in capsys.readouterr().err


def _petit(tmp_path: Path) -> Path:
    main(["exemple", str(tmp_path / "ex")])
    cfg = tmp_path / "ex" / "CONFIG.yaml"
    texte = cfg.read_text(encoding="utf-8").replace("resolution: 1080p", "resolution: [160, 90]")
    cfg.write_text(texte.replace("preset: medium", "preset: ultrafast"), encoding="utf-8")
    return cfg


@pytest.mark.usefixtures("rendu")
def test_rendre_et_image(tmp_path: Path) -> None:
    from cfd_trajcast.engine.encodage import sonder_video

    cfg = _petit(tmp_path)
    assert main(["rendre", str(cfg), "--de", "2", "--a", "3"]) == EXIT_OK
    info = sonder_video(cfg.with_suffix(".mp4"))
    assert (info.largeur, info.hauteur, info.n_images) == (160, 90, 30)
    assert main(["image", str(cfg), "--t", "12.5"]) == EXIT_OK
    assert (cfg.parent / "CONFIG_t12.5.png").is_file()


def test_rendre_intervalle_invalide(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = _petit(tmp_path)
    assert main(["rendre", str(cfg), "--de", "5", "--a", "2"]) == EXIT_ERREUR_ENTREE
    assert "intervalle" in capsys.readouterr().err


@pytest.mark.usefixtures("rendu")
def test_diagnostic(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["diagnostic"]) == EXIT_OK
    assert "rendu possible" in capsys.readouterr().out


def test_rendre_colonne_absente(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["exemple", str(tmp_path / "ex")])
    cfg = tmp_path / "ex" / "CONFIG_ENSEMBLE.yaml"
    cfg.write_text(cfg.read_text(encoding="utf-8").replace("colonne: roulis", "colonne: DN"), encoding="utf-8")
    assert main(["rendre", str(cfg), "--apercu"]) == EXIT_ERREUR_ENTREE
    assert "« DN » absente" in capsys.readouterr().err
