"""Figures de vent : rose Nord/Est + profil vertical, figure paper et vidéo sans rendu.

Ce qu'une relecture ne voit pas : la convention de l'azimut (Nord = 0, Est = 90°,
sens horaire), le retournement ``depuis``, l'interpolation par composante (pas de
tour de cadran entre 359° et 1°), la flèche dessinée au vent de l'instant, le rayon
commun, et l'absence de glyphe manquant dans la police du profil ``paper``.
"""

from __future__ import annotations

import math
import warnings
from pathlib import Path

import numpy as np
import pytest
from conftest import dataframe_enu_quaternion

from cfd_trajcast.cli.main import EXIT_ERREUR_ENTREE, EXIT_OK, main
from cfd_trajcast.core.vent_polaire import azimut_module, rayon_polaire, vent_a
from cfd_trajcast.data.configuration import ConfigVideo
from cfd_trajcast.data.trajectoire import Evenement, Trajectoire
from cfd_trajcast.data.vent import DeclarationVent, ErreurVent

cfd_plot = pytest.importorskip("cfd_plot")

from cfd_trajcast import VueVent  # noqa: E402
from cfd_trajcast.engine import figure_vent as fv  # noqa: E402

EVENEMENTS = [Evenement(3.744, "Mach 1"), Evenement(4.0, "Fin de propulsion"), Evenement(40.565, "Apogée")]


def _traj(vn: np.ndarray | float = 3.0, ve: np.ndarray | float = 4.0, vz: np.ndarray | float = 0.5) -> Trajectoire:
    df = dataframe_enu_quaternion()
    n = len(df)
    df = df.assign(VN=np.broadcast_to(vn, n).copy(), VE=np.broadcast_to(ve, n).copy(),
                   VZ=np.broadcast_to(vz, n).copy())
    return Trajectoire.depuis_dataframe(df, repere="ENU", attitude="quaternion", evenements=EVENEMENTS)


DECL = DeclarationVent(colonnes=("VN", "VE", "VZ"), vz="haut")


@pytest.fixture(autouse=True)
def _glyphes() -> object:
    """Un glyphe absent de la police est un UserWarning : ici, une erreur (pas les dépréciations)."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        warnings.simplefilter("default", DeprecationWarning)
        yield


# -- conventions ---------------------------------------------------------------------------
@pytest.mark.parametrize(("est", "nord", "attendu"), [
    (0.0, 1.0, 0.0), (1.0, 0.0, 90.0), (0.0, -1.0, 180.0), (-1.0, 0.0, 270.0), (1.0, 1.0, 45.0),
])
def test_azimut_depuis_le_nord_sens_horaire(est: float, nord: float, attendu: float) -> None:
    az, module, vz = azimut_module([est, nord, 2.0])
    assert math.degrees(az[0]) == pytest.approx(attendu)
    assert module[0] == pytest.approx(math.hypot(est, nord)) and vz[0] == 2.0


def test_depuis_retourne_la_fleche_sans_changer_le_module() -> None:
    v = np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [3.0, 4.0, 0.0]])
    az_vers, m_vers, _ = azimut_module(v, "vers")
    az_dep, m_dep, _ = azimut_module(v, "depuis")
    np.testing.assert_allclose(np.mod(az_dep - az_vers, 2 * np.pi), np.pi)
    np.testing.assert_array_equal(m_vers, m_dep)
    assert np.all((az_dep >= 0) & (az_dep < 2 * np.pi))
    with pytest.raises(ValueError, match="sens"):
        azimut_module(v, "vers_le_haut")


def test_interpolation_par_composante_pas_de_tour_de_cadran() -> None:
    """359° puis 1° : à mi-chemin, le Nord (0°) — pas le Sud qu'une moyenne d'angles donnerait."""
    a, b = math.radians(359.0), math.radians(1.0)
    vent = np.array([[math.sin(a), math.cos(a), 0.0], [math.sin(b), math.cos(b), 0.0]]) * 10
    az, module, _ = azimut_module(vent_a(0.5, [0.0, 1.0], vent))
    assert math.degrees(az[0]) == pytest.approx(0.0, abs=1e-9) or math.degrees(az[0]) == pytest.approx(360.0)
    assert module[0] == pytest.approx(10 * math.cos(math.radians(1.0)))
    # Borné au vol.
    np.testing.assert_allclose(vent_a(-5.0, [0.0, 1.0], vent), vent[0])


@pytest.mark.parametrize(("vmax", "rayon"), [(0.0, 1.0), (4.0, 5.0), (5.0, 10.0), (15.5, 20.0), (16.2, 20.0),
                                             (19.5, 25.0), (0.3, 0.5), (120.0, 200.0)])
def test_rayon_arrondi_avec_marge(vmax: float, rayon: float) -> None:
    assert rayon_polaire([0.0, vmax]) == pytest.approx(rayon)


def test_direction_texte() -> None:
    assert fv.direction_texte(math.radians(235.0), 6.24, "vers") == "6,2\u00a0m/s vers 235°"
    assert fv.direction_texte(math.radians(5.0), 6.0, "depuis").endswith("depuis 005°")
    assert fv.direction_texte(1.0, 0.01, "vers") == "calme"


def test_evenements_rapproches_partagent_une_etiquette() -> None:
    groupes = fv._grouper_evenements([(n, e) for n, e in ((e.nom, e.t) for e in EVENEMENTS)], 2.0)
    assert [nom for _, nom in groupes] == ["Mach 1 / Fin de propulsion", "Apogée"]


# -- figure fixe -----------------------------------------------------------------------------
def _dessin(traj: Trajectoire, instants: object = None, sens: str = "vers", largeur_cm: float = 16.0) -> fv._Dessin:
    d = fv.DonneesVent(traj, DECL, sens)
    choisis = fv._resoudre_poses(traj, instants)  # type: ignore[arg-type]
    with cfd_plot.style_context("paper"):
        return fv._dessiner(cfd_plot, d, choisis, largeur_cm, "")


def test_fleche_au_vent_de_l_instant() -> None:
    t = np.asarray(_traj().t)
    vn, ve = 5 * np.cos(t / 10), 5 * np.sin(t / 10)  # vent qui tourne de 0,1 rad/s
    traj = _traj(vn, ve)
    dessin = _dessin(traj, [12.0, 30.0], sens="vers")
    for t_i, fleche in zip((12.0, 30.0), dessin.fleches):
        attendu = np.array([np.interp(t_i, t, ve), np.interp(t_i, t, vn)])
        theta, rho = fleche.xy
        np.testing.assert_allclose([rho * math.sin(theta), rho * math.cos(theta)], attendu, atol=1e-9)
        assert fleche.xyann == (0.0, 0.0)
    # Toutes les roses au même rayon.
    assert {ax.get_ylim()[1] for ax in dessin.roses} == {dessin.donnees.rayon}


def test_rose_nord_en_haut_est_a_droite() -> None:
    dessin = _dessin(_traj(), [10.0])
    rose = dessin.roses[0]
    assert rose.get_theta_offset() == pytest.approx(math.pi / 2) and rose.get_theta_direction() == -1
    assert [t.get_text() for t in rose.get_xticklabels()] == ["N", "E", "S", "O"]


def test_instants_rangees_et_profil() -> None:
    dessin = _dessin(_traj(), 9, largeur_cm=16.0)
    assert len(dessin.roses) == 9 and len(dessin.instants) == 9
    # 16 cm : quatre roses par rangée, les rangées ne se chevauchent pas.
    lignes = sorted({round(ax.get_position().y0, 6) for ax in dessin.roses}, reverse=True)
    assert len(lignes) == 3
    assert dessin.profil.get_xlabel() == "Temps (s)" and dessin.profil.get_ylabel() == "Altitude (m)"


def test_figure_ecrit_les_formats_et_propose_une_legende(tmp_path: Path) -> None:
    f = fv.figure_vent(_traj(), DECL, tmp_path / "vent_M0.85", sens="depuis")
    assert [p.name for p in f.fichiers] == ["vent_M0.85.pdf", "vent_M0.85.svg", "vent_M0.85.png"]
    assert all(p.stat().st_size > 0 for p in f.fichiers)
    assert f.instants == (3.744, 4.0, 40.565) and f.sens == "depuis" and f.rayon == 10.0
    assert "convention météo" in f.legende and 6 < f.taille_cm[0] <= 16.5


def test_figure_erreurs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="hors du vol"):
        fv.figure_vent(_traj(), DECL, tmp_path / "v", instants=[1e6])
    with pytest.raises(ValueError, match="inconnu"):
        fv.figure_vent(_traj(), DECL, tmp_path / "v", instants=["Parachute"])
    with pytest.raises(ValueError, match="au moins un"):
        fv.figure_vent(_traj(), DECL, tmp_path / "v", instants=0)
    with pytest.raises(fv.ErreurFigure, match="formats"):
        fv.figure_vent(_traj(), DECL, tmp_path / "v", formats=("jpg",))
    with pytest.raises(ValueError, match="sens"):
        fv.figure_vent(_traj(), DECL, tmp_path / "v", sens="nord")


# -- façade, vidéo, ligne de commande ------------------------------------------------------------
def test_vue_vent_sans_section_vent(exemple: Path) -> None:
    with pytest.raises(ErreurVent, match="section `vent`"):
        VueVent.depuis_yaml(exemple / "CONFIG.yaml")


@pytest.mark.skipif(not cfd_plot.ffmpeg_available(), reason="ffmpeg absent")
def test_animation_sans_rendu(tmp_path: Path, exemple: Path) -> None:
    from cfd_trajcast.engine.encodage import sonder_video

    vue = VueVent.depuis_yaml(exemple / "CONFIG_GUI.yaml")
    vue.video = ConfigVideo(resolution=(320, 180), ips=10, crf=30)
    vus: list[tuple[int, int]] = []
    a = vue.animer(tmp_path / "v.mp4", duree=1.5, sens="depuis", progression=lambda k, n: vus.append((k, n)))
    info = sonder_video(a.chemin)
    assert (info.largeur, info.hauteur) == (320, 180)
    assert vus[-1] == (15, 15) and a.images == 15 + 10  # 1 s de pause sur la dernière image
    assert info.n_images == a.images and a.sens == "depuis"
    with pytest.raises(ValueError, match="intervalle"):
        vue.animer(tmp_path / "w.mp4", de=10.0, a=5.0)


def test_cli_vent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["exemple", str(tmp_path / "ex")])
    cfg = tmp_path / "ex" / "CONFIG_GUI.yaml"
    assert main(["vent", str(cfg), "--formats", "svg", "--instants", "2,Apogée", "--sens", "depuis"]) == EXIT_OK
    assert (tmp_path / "ex" / "CONFIG_GUI_vent.svg").is_file()
    sortie = capsys.readouterr().out
    assert "depuis" in sortie and "40.6 s" in sortie
    assert main(["vent", str(tmp_path / "ex" / "CONFIG.yaml")]) == EXIT_ERREUR_ENTREE
    assert "section `vent`" in capsys.readouterr().err
