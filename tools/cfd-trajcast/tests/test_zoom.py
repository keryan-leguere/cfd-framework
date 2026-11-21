"""Zoom de la vue 3D Matplotlib (``VueMpl``) — sans Qt.

Ce qui doit tenir à tout zoom : les proportions vraies (même échelle sur les trois axes),
l'axe Bas inversé (le ciel en haut), le point visé qui reste sous la souris, et le CDG
au centre quand la vue suit l'engin.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytest.importorskip("cfd_plot")

from cfd_trajcast.data.configuration import charger_configuration
from cfd_trajcast.engine.etat_vol import EtatVol
from cfd_trajcast.engine.vue3d_mpl import CADRAGE_ENGIN, PAS_ZOOM, ZOOM_MIN, OptionsVue, VueMpl
from cfd_trajcast.paths import EXEMPLE_DIR

CONFIG = Path(EXEMPLE_DIR) / "CONFIG_GUI.yaml"


@pytest.fixture(scope="module")
def etat_cfg() -> tuple[EtatVol, Any]:
    cfg = charger_configuration(CONFIG)
    return EtatVol.depuis_configuration(cfg), cfg


@pytest.fixture
def vue(etat_cfg: tuple[EtatVol, Any]) -> VueMpl:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    etat, cfg = etat_cfg
    figure = Figure(figsize=(8, 6))
    FigureCanvasAgg(figure)
    parametres = next(p for _, p in cfg.vues if hasattr(p, "repere"))
    v = VueMpl(figure, etat, parametres, options=OptionsVue(reperes=frozenset({"corps"}), vent=True))
    v.poser(15.0)
    return v


def _etendues(vue: VueMpl) -> np.ndarray:
    return np.array([b - a for a, b in (vue.ax.get_xlim(), vue.ax.get_ylim(), vue.ax.get_zlim())])


def _meme_echelle(vue: VueMpl) -> bool:
    """Proportions vraies : étendue de chaque axe / côté de la boîte, identique sur les trois."""
    rapport = np.abs(_etendues(vue)) / np.asarray(vue.ax.get_box_aspect(), dtype=float)
    return bool(np.allclose(rapport, rapport[0], rtol=1e-3))


def test_depart_vol_entier(vue: VueMpl) -> None:
    assert vue.zoom == pytest.approx(1.0)
    assert not vue.suivre
    assert _etendues(vue)[2] < 0  # Bas inversé


@pytest.mark.parametrize("facteur", [PAS_ZOOM, 3.0, 40.0])
def test_zoom_garde_les_proportions_et_le_bas_inverse(vue: VueMpl, facteur: float) -> None:
    centre = vue.centre()
    assert vue.zoomer(facteur) == pytest.approx(facteur)
    assert vue.zoom == pytest.approx(facteur)
    assert _meme_echelle(vue)
    assert _etendues(vue)[2] < 0
    np.testing.assert_allclose(vue.centre(), centre, atol=1e-6 * float(np.abs(centre).max() + 1))


def test_de_pres_la_boite_devient_cubique(vue: VueMpl) -> None:
    """Le vol d'exemple est presque vertical : la boîte du vol entier est une colonne."""
    depart = np.abs(_etendues(vue))
    assert depart.max() / depart.min() > 2
    vue.zoomer(depart.max() / depart.min() * 2)
    e = np.abs(_etendues(vue))
    np.testing.assert_allclose(e, e[0], rtol=1e-9)
    assert _meme_echelle(vue)


def test_bornes(vue: VueMpl) -> None:
    assert vue.zoomer(0.1) == pytest.approx(ZOOM_MIN)
    assert vue.zoomer(1e9) == pytest.approx(vue.zoom_max)
    # Au zoom maximal, la demi-largeur visible vaut une demi-maquette réelle.
    assert np.abs(_etendues(vue)).max() / 2 == pytest.approx(0.5 * vue.etat.maquette.taille, rel=1e-6)


def test_le_point_vise_reste_sous_la_souris(vue: VueMpl) -> None:
    vue.figure.canvas.draw()
    point = np.asarray(vue.scene.xyz[len(vue.scene.xyz) // 4], dtype=float)
    avant = vue._ecran(point)
    for _ in range(4):  # la forme de la boîte change à chaque cran
        vue.zoomer(PAS_ZOOM, vers=point)
        np.testing.assert_allclose(vue._ecran(point), avant, atol=0.5)


def test_cadrer_l_engin_puis_le_suivre(vue: VueMpl) -> None:
    zoom = vue.cadrer_engin()
    assert vue.suivre and zoom > 1
    np.testing.assert_allclose(vue.centre(), vue.cdg(), atol=1e-6)
    demi = np.abs(_etendues(vue)).max() / 2
    assert demi == pytest.approx(CADRAGE_ENGIN * vue.echelle * vue.etat.maquette.taille, rel=1e-6)
    for t in (20.0, 40.0):
        vue.poser(t)
        np.testing.assert_allclose(vue.centre(), vue.cdg(), atol=1e-6)
        assert vue.zoom == pytest.approx(zoom)
    vue.vue_entiere()
    assert not vue.suivre and vue.zoom == pytest.approx(1.0)


def test_suivre_sans_changer_le_zoom(vue: VueMpl) -> None:
    vue.zoomer(2.0)
    vue.suivre_engin(True)
    assert vue.zoom == pytest.approx(2.0)
    np.testing.assert_allclose(vue.centre(), vue.cdg(), atol=1e-6)
    vue.suivre_engin(False)
    vue.poser(40.0)
    assert not np.allclose(vue.centre(), vue.cdg())


def test_le_sol_est_coupe_a_la_boite(vue: VueMpl) -> None:
    assert vue.sol is not None and vue.sol.get_visible()
    vue.cadrer_engin()
    vue.poser(30.0)  # en altitude : le sol est hors champ
    assert not vue.sol.get_visible()
    vue.vue_entiere()
    assert vue.sol.get_visible()


def test_zoom_dessine_et_exporte(vue: VueMpl, tmp_path: Path) -> None:
    vue.cadrer_engin()
    vue.figure.canvas.draw()
    assert vue.exporter(tmp_path / "zoom.png", dpi=60).stat().st_size > 0
