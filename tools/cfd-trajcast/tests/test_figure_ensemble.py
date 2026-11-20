"""Vue d'ensemble : repère NED local, figure paper (Matplotlib + cfd-plot), animation sans rendu.

La figure n'a pas de moteur 3D : Matplotlib projette. Ce qui est vérifié ici, c'est
ce qu'une relecture ne voit pas — le décalage du NED local, l'image **non miroir**
(un trièdre affiché direct), l'absence de glyphe manquant dans la police du profil
``paper``, et que la vidéo sans rendu a le nombre d'images du plan.
"""

from __future__ import annotations

import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import yaml
from conftest import dataframe_enu_quaternion

from cfd_trajcast.cli import main as cli
from cfd_trajcast.cli.main import EXIT_OK, main
from cfd_trajcast.core.camera import (
    ParametresEnsemble,
    boite_ensemble,
    origine_ensemble,
    titres_axes_ensemble,
)
from cfd_trajcast.data.configuration import ConfigVideo, ErreurConfiguration, charger_configuration
from cfd_trajcast.data.maquette import Maquette
from cfd_trajcast.data.trajectoire import Evenement, Trajectoire
from cfd_trajcast.engine.ensemble import VueEnsemble

cfd_plot = pytest.importorskip("cfd_plot")

from cfd_trajcast.engine import figure_ensemble as fe  # noqa: E402

EVENEMENTS = [Evenement(3.744, "Mach 1"), Evenement(4.0, "Fin de propulsion"), Evenement(40.565, "Apogée")]


@pytest.fixture
def maquette(exemple: Path) -> Maquette:
    return Maquette.depuis_fichier(exemple / "MAQUETTE" / "Aim9.stl", unite="mm", axe_nez="-X",
                                   axe_haut="+Z", origine=(19.05, 0, 0), longueur_imposee=2.87)


def _traj(altitude_depart: float = 0.0) -> Trajectoire:
    df = dataframe_enu_quaternion()
    df["z"] = df["z"] + altitude_depart
    return Trajectoire.depuis_dataframe(df, repere="ENU", attitude="quaternion", evenements=EVENEMENTS)


@pytest.fixture
def traj() -> Trajectoire:
    return _traj()


@pytest.fixture(autouse=True)
def _glyphes() -> object:
    """Un glyphe absent de la police est un UserWarning : ici, une erreur (pas les dépréciations)."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        warnings.simplefilter("default", DeprecationWarning)
        yield


# -- repère NED local ----------------------------------------------------------------------
def test_origine_ned_local_ne_decale_que_la_verticale() -> None:
    pos = np.array([[10.0, 20.0, 1500.0], [50.0, 80.0, 3000.0]])  # ENU
    assert np.array_equal(origine_ensemble(pos, "ned"), np.zeros(3))
    np.testing.assert_allclose(origine_ensemble(pos, "ned_local"), [0.0, 0.0, -1500.0])
    with pytest.raises(ValueError, match="repere"):
        origine_ensemble(pos, "enu")


def test_ned_local_d_un_vol_qui_part_d_altitude_est_le_vol_parti_du_sol() -> None:
    haut, bas = _traj(1500.0), _traj(0.0)
    b_local = boite_ensemble(haut.positions, sol_altitude=1500.0, origine=origine_ensemble(haut.positions, "ned_local"))
    b_ref = boite_ensemble(bas.positions, sol_altitude=0.0)
    np.testing.assert_allclose(b_local.mini, b_ref.mini, atol=1e-9)
    np.testing.assert_allclose(b_local.maxi, b_ref.maxi, atol=1e-9)
    assert b_local.sol == pytest.approx(b_ref.sol)
    b_classique = boite_ensemble(haut.positions, sol_altitude=1500.0)
    assert b_classique.mini[2] == pytest.approx(b_ref.mini[2] - 1500.0)  # NED classique : Bas absolu


def test_titres_et_parametres() -> None:
    assert titres_axes_ensemble("ned") == ("Nord (m)", "Est (m)", "Bas (m)")
    assert titres_axes_ensemble("ned_local")[2] == "Bas local (m)"
    with pytest.raises(ValueError, match="repere"):
        ParametresEnsemble(repere="local")


def test_repere_lu_dans_le_yaml(tmp_path: Path, exemple: Path) -> None:
    import shutil

    shutil.copytree(exemple, tmp_path / "ex")
    cfg = tmp_path / "ex" / "CONFIG_ENSEMBLE.yaml"
    d = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    d["vues"]["ensemble"]["repere"] = "ned_local"
    cfg.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    vue = dict(charger_configuration(cfg).vues)["ensemble"]
    assert isinstance(vue, ParametresEnsemble) and vue.repere == "ned_local"
    d["vues"]["ensemble"]["repere"] = "enu"
    cfg.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ErreurConfiguration, match="repere"):
        charger_configuration(cfg)


# -- figure --------------------------------------------------------------------------------
def test_nombres_a_la_francaise() -> None:
    assert fe._nombre(-1250) == "−1\u2009250"
    assert fe._nombre(-0.2) == "0" and fe._secondes(0.0) == "0,0\u00a0s"
    assert fe._secondes(40.565) == "40,6\u00a0s"


def test_image_non_miroir(traj: Trajectoire, maquette: Maquette) -> None:
    """Est, Nord, Haut affichés forment un trièdre direct : vu d'en haut, on tourne de l'Est
    au Nord dans le sens trigonométrique, et le Haut monte à l'écran."""
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import proj3d

    for azimut in (0.0, 70.0, 200.0):
        scene = fe._Scene(traj, maquette, ParametresEnsemble(azimut=azimut, elevation=30.0), 0.0, 200)
        fig = plt.figure(figsize=(4, 4))
        ax = fe._axes(cfd_plot, fig, scene, (0, 0, 1, 1), "ortho")
        fig.canvas.draw()
        c = (scene.bas + scene.haut) / 2
        pts = c + np.array([[0, 0, 0], [100.0, 0, 0], [0, 100.0, 0], [0, 0, -100.0]])  # O, Est, Nord, Haut
        xs, ys, _ = proj3d.proj_transform(pts[:, 0], pts[:, 1], pts[:, 2], ax.get_proj())
        ecran = ax.transData.transform(np.column_stack([xs, ys]))
        est, nord, haut = ecran[1] - ecran[0], ecran[2] - ecran[0], ecran[3] - ecran[0]
        assert est[0] * nord[1] - est[1] * nord[0] > 0, azimut
        assert haut[1] > 0
        plt.close(fig)


def test_figure_ecrit_les_trois_formats(tmp_path: Path, traj: Trajectoire, maquette: Maquette) -> None:
    f = fe.figure_ensemble(traj, maquette, ParametresEnsemble(repere="ned_local"), tmp_path / "vol_M0.85",
                           largeur_cm=10.0)
    assert [p.name for p in f.fichiers] == ["vol_M0.85.pdf", "vol_M0.85.svg", "vol_M0.85.png"]
    assert all(p.stat().st_size > 1000 for p in f.fichiers)
    assert f.fichiers[0].read_bytes()[:5] == b"%PDF-"
    # Largeur demandée tenue (la légende en fait partie), hauteur dictée par les proportions du vol.
    assert 8.0 <= f.taille_cm[0] <= 12.0 and f.taille_cm[1] > f.taille_cm[0]
    # Mach 1 et la fin de propulsion sont à quelques mètres : une seule maquette pour les deux.
    assert f.poses == (3.744, 40.565)
    assert "NED local" in f.legende and "agrandie" in f.legende and "3,7\u00a0s" in f.legende


def test_figure_poses_explicites_et_erreurs(tmp_path: Path, traj: Trajectoire, maquette: Maquette) -> None:
    f = fe.figure_ensemble(traj, maquette, None, tmp_path / "a", poses=[3.744, 4.0], formats=("svg",),
                           projection="persp", legende=False)
    assert f.poses == (3.744, 4.0) and f.projection == "persp" and len(f.fichiers) == 1
    with pytest.raises(fe.ErreurFigure, match="formats"):
        fe.figure_ensemble(traj, maquette, None, tmp_path / "b", formats=("jpg",))
    with pytest.raises(fe.ErreurFigure, match="projection"):
        fe.figure_ensemble(traj, maquette, None, tmp_path / "b", projection="iso")


def test_sans_cfd_plot_message_clair(monkeypatch: pytest.MonkeyPatch, traj: Trajectoire,
                                     maquette: Maquette) -> None:
    import builtins

    vrai_import = builtins.__import__

    def sans(nom: str, *a: object, **k: object) -> object:
        if nom == "cfd_plot":
            raise ImportError("absent")
        return vrai_import(nom, *a, **k)

    monkeypatch.setattr(builtins, "__import__", sans)
    assert not fe.cfd_plot_disponible()
    with pytest.raises(fe.ErreurFigure, match="cfd-plot"):
        fe.figure_ensemble(traj, maquette)


# -- animation -------------------------------------------------------------------------------
@pytest.mark.skipif(not cfd_plot.ffmpeg_available(), reason="ffmpeg absent")
def test_animation_sans_rendu(tmp_path: Path, exemple: Path) -> None:
    from cfd_trajcast.engine.encodage import sonder_video

    vue = VueEnsemble.depuis_yaml(exemple / "CONFIG_ENSEMBLE.yaml")
    vue.video = ConfigVideo(resolution=(320, 180), ips=10, crf=30)
    vue.parametres = replace(vue.parametres, repere="ned_local")
    vus: list[tuple[int, int]] = []
    a = vue.animer(tmp_path / "a.mp4", duree=1.5, progression=lambda k, n: vus.append((k, n)))
    info = sonder_video(a.chemin)
    assert (info.largeur, info.hauteur) == (320, 180)
    assert vus[-1] == (15, 15) and a.images == 15 + 10  # 1 s de pause sur la dernière image
    assert info.n_images == a.images and a.encodeur == "ffmpeg-stream" and a.repere == "ned_local"


# -- ligne de commande ---------------------------------------------------------------------
def test_cli_figure_par_defaut(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["exemple", str(tmp_path / "ex")])
    cfg = tmp_path / "ex" / "CONFIG_ENSEMBLE.yaml"
    assert main(["ensemble", str(cfg), "--formats", "svg,png", "--largeur-cm", "8"]) == EXIT_OK
    assert {p.name for p in (tmp_path / "ex").glob("CONFIG_ENSEMBLE_ensemble.*")} == {
        "CONFIG_ENSEMBLE_ensemble.svg", "CONFIG_ENSEMBLE_ensemble.png"}
    assert "légende" in capsys.readouterr().out


def test_cli_repli_sur_le_schema_sans_cfd_plot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    main(["exemple", str(tmp_path / "ex")])
    monkeypatch.setattr(cli, "cfd_plot_disponible", lambda: False)
    assert main(["ensemble", str(tmp_path / "ex" / "CONFIG_ENSEMBLE.yaml")]) == EXIT_OK
    assert (tmp_path / "ex" / "CONFIG_ENSEMBLE_ensemble.svg").is_file()
    assert "cfd-plot absent" in capsys.readouterr().out


def test_cli_formats_invalides() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["ensemble", "x.yaml", "--formats", "jpg"])
