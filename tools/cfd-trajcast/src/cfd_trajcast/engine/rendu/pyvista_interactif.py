"""Vue d'ensemble **interactive** en VTK (pyvistaqt) — le pendant OpenGL de ``engine/vue3d_mpl.py``.

Même contrat que :class:`~cfd_trajcast.engine.vue3d_mpl.VueMpl` (``poser``, ``regler``,
``instant_proche``, ``options``), mêmes couches, mêmes couleurs de repères, même
repère (NED classique ou local, :func:`~cfd_trajcast.core.camera.origine_ensemble`) ;
la caméra de départ est celle de la vidéo (:func:`~cfd_trajcast.core.camera.cadre_ensemble`).
La scène est en coordonnées NED : VTK n'inverse pas d'axe, l'image n'est donc pas un
miroir, et le haut de l'écran est le ciel (``up = −D``).

Seul module, avec ``pyvista_.py``, à importer pyvista ; seul à importer pyvistaqt. Il
demande une ``QApplication`` déjà créée (par ``gui``) et un OpenGL qui fonctionne :
l'interface le vérifie d'abord dans un sous-processus (``python -m
cfd_trajcast.gui.sonde_vtk``), parce qu'un OpenGL cassé fait planter le processus.

Un **double-clic** place le temps sur le point du vol le plus proche : le simple clic
appartient à la rotation de la caméra.

Zoom : la molette est celle de VTK (la caméra avance vers le point visé) ; :meth:`VueVtk.zoomer`,
:meth:`~VueVtk.cadrer_engin`, :meth:`~VueVtk.vue_entiere` et :attr:`~VueVtk.suivre` font
la même chose que pour la vue Matplotlib, en déplaçant la caméra. Le zoom vaut la distance de départ
divisée par la distance courante.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.core.camera import (
    ParametresEnsemble,
    boite_ensemble,
    cadre_ensemble,
    echelle_ensemble,
    ned_ensemble,
    origine_ensemble,
    titres_axes_ensemble,
    vers_ned,
)
from cfd_trajcast.engine.etat_vol import EtatVol
from cfd_trajcast.engine.vue3d_mpl import (
    CADRAGE_ENGIN,
    COULEURS_REPERES,
    FLECHES_VENT,
    NOMS_AXES,
    PART_VENT,
    RAYON_CLIC_PX,
    ZOOM_MIN,
    OptionsVue,
)

__all__ = ["VueVtk"]

Tableau = NDArray[np.float64]


def _base_orthonormee(axes: Tableau, k: int) -> Tableau:
    """Colonnes (axe k, axe k+1, axe k+2) : une base directe dont le premier vecteur est l'axe k."""
    return np.stack([axes[:, k], axes[:, (k + 1) % 3], axes[:, (k + 2) % 3]], axis=1)


class VueVtk:
    """La scène 3D d'un :class:`EtatVol` dans un ``QtInteractor`` (widget : :attr:`widget`)."""

    def __init__(self, parent: Any, etat: EtatVol, parametres: ParametresEnsemble | None = None, *,
                 sol_altitude: float = 0.0, options: OptionsVue | None = None) -> None:
        import pyvista as pv
        from pyvistaqt import QtInteractor  # type: ignore[import-not-found,unused-ignore]

        self.pv = pv
        self.etat = etat
        self.parametres = parametres or ParametresEnsemble()
        self.options = options or OptionsVue()
        self.plotter = QtInteractor(parent)
        self.widget = self.plotter.interactor
        self.t = etat.debut
        self._rappel_clic: Callable[[float], None] | None = None
        traj = etat.trajectoire
        p: Any = self.plotter
        p.set_background("white")
        self.origine = origine_ensemble(traj.positions, self.parametres.repere)
        self.trace = ned_ensemble(traj.positions, self.origine)
        boite = boite_ensemble(traj.positions, sol_altitude, self.origine)
        mini, maxi, marge = boite.mini, boite.maxi, boite.marge
        self.echelle_auto = echelle_ensemble(traj.positions, etat.maquette.taille, self.parametres)
        # Sol, trace au sol, vol entier en gris, partie parcourue en noir.
        p.add_mesh(pv.Plane(center=((mini[0] + maxi[0]) / 2, (mini[1] + maxi[1]) / 2, boite.sol),
                            direction=(0, 0, 1), i_size=maxi[0] - mini[0] + 2 * marge,
                            j_size=maxi[1] - mini[1] + 2 * marge), color="#eeeeee", opacity=0.8)
        au_sol = self.trace.copy()
        au_sol[:, 2] = boite.sol
        self.trace_sol = p.add_mesh(pv.lines_from_points(au_sol), color="#9e9e9e", line_width=1)
        p.add_mesh(pv.lines_from_points(self.trace), color="#bfbfbf", line_width=2)
        self.parcouru = pv.lines_from_points(self.trace[:2])
        p.add_mesh(self.parcouru, color="black", line_width=3)
        # Événements : un point et un nom chacun, allumés quand ils sont atteints.
        self.evenements: list[tuple[float, Any]] = []
        for nom, te in ((e.nom, float(e.t)) for e in traj.evenements):
            point = ned_ensemble(traj.etat(np.array([te]))[0], self.origine)
            acteur = p.add_point_labels(point, [nom], point_size=10, font_size=12, point_color="#0072B2",
                                        text_color="black", shape_opacity=0.0, always_visible=True)
            self.evenements.append((te, acteur))
        # Maquette : ses sommets sont recalculés à chaque instant (CDG variable, agrandissement).
        m = etat.maquette
        faces = np.hstack([np.full((len(m.faces), 1), 3), m.faces]).ravel()
        self.maillage = pv.PolyData(np.asarray(m.sommets, dtype=float).copy(), faces)
        self.fusee = p.add_mesh(self.maillage, color="#7f8c99", smooth_shading=True, split_sharp_edges=True)
        # Repères : une flèche unitaire par axe, posée par sa matrice ; un nom au bout.
        self.reperes: dict[str, list[Any]] = {}
        self.etiquettes: dict[str, Any] = {}
        fleche = pv.Arrow(start=(0, 0, 0), direction=(1, 0, 0), tip_length=0.12, tip_radius=0.03,
                          shaft_radius=0.008)
        for nom, couleur in COULEURS_REPERES.items():
            self.reperes[nom] = [p.add_mesh(fleche.copy(), color=couleur) for _ in range(3)]
            nuage = pv.PolyData(np.zeros((3, 3)))
            nuage["noms"] = np.array([a.replace("_", "") for a in NOMS_AXES[nom]])
            self.etiquettes[nom] = (nuage, p.add_point_labels(nuage, "noms", font_size=11, text_color=couleur,
                                                               shape_opacity=0.0, show_points=False,
                                                               always_visible=True))
        # Vent le long du vol.
        self.vent_acteur = None
        if etat.vent is not None:
            i = np.linspace(0, len(etat.t) - 1, FLECHES_VENT).round().astype(int)
            fort = float(np.max(np.linalg.norm(etat.vent, axis=1)))
            if fort > 0:
                nuage = pv.PolyData(self.trace[i])
                nuage["vent"] = vers_ned(etat.vent[i])
                facteur = PART_VENT * float(np.max(maxi - mini)) / fort
                self.vent_acteur = p.add_mesh(nuage.glyph(orient="vent", scale="vent", factor=facteur),
                                              color="#56B4E9")
        titres = titres_axes_ensemble(self.parametres.repere)
        p.show_grid(bounds=(boite.bas[0], boite.haut[0], boite.bas[1], boite.haut[1], boite.bas[2], boite.haut[2]),
                    xtitle=titres[0], ytitle=titres[1], ztitle=titres[2], color="#333333", fmt="%.0f",
                    n_xlabels=len(boite.graduations(0)), n_ylabels=len(boite.graduations(1)),
                    n_zlabels=len(boite.graduations(2)))
        self.horloge = p.add_text("", position="upper_left", font_size=11, color="black")
        position, vise, haut = cadre_ensemble(traj.positions, self.parametres, 1.4, (boite.bas, boite.haut))
        c = p.camera
        c.position, c.focal_point, c.up = (tuple(float(v) for v in x) for x in (position, vise, haut))
        c.view_angle = self.parametres.champ
        self._camera0 = (c.position, c.focal_point, c.up, c.view_angle)
        self._distance0 = float(c.distance)
        self.suivre = False
        p.track_click_position(self._double_clic, side="left", double=True)
        self.regler(self.options)

    # -- état -------------------------------------------------------------------------------
    @property
    def echelle(self) -> float:
        return self.options.agrandissement or self.echelle_auto

    def regler(self, options: OptionsVue) -> None:
        self.options = options
        self.fusee.SetVisibility(options.maquette)
        self.trace_sol.SetVisibility(options.trace_sol)
        for nom, fleches in self.reperes.items():
            for f in fleches:
                f.SetVisibility(nom in options.reperes)
            self.etiquettes[nom][1].SetVisibility(nom in options.reperes)
        if self.vent_acteur is not None:
            self.vent_acteur.SetVisibility(options.vent)
        self.poser(self.t)

    def poser(self, t: float, rendre: bool = True) -> None:
        etat = self.etat
        self.t = t = etat.borner(t)
        instant = etat.a(t)
        dedans = etat.t <= t
        position = ned_ensemble(instant.position, self.origine)
        points = np.vstack([self.trace[dedans], position])
        if len(points) < 2:
            points = np.vstack([points, points])
        self.parcouru.copy_from(self.pv.lines_from_points(points))
        if self.options.maquette:
            self.maillage.points = ned_ensemble(etat.placer(etat.maquette.sommets, t, self.echelle), self.origine)
        for te, acteur in self.evenements:
            acteur.SetVisibility(self.options.evenements and t >= te - 1e-9)
        longueur = 1.3 * self.echelle * float(np.ptp(etat.maquette.sommets[:, 0]))
        for nom, fleches in self.reperes.items():
            axes = instant.axes.get(nom)
            visible = nom in self.options.reperes and axes is not None and bool(np.isfinite(axes).all())
            for f in fleches:
                f.SetVisibility(visible)
            self.etiquettes[nom][1].SetVisibility(visible)
            if not visible or axes is None:
                continue
            axes_ned = vers_ned(axes.T).T  # colonnes en NED
            for k, f in enumerate(fleches):
                m = np.eye(4)
                m[:3, :3] = longueur * _base_orthonormee(axes_ned, k)
                m[:3, 3] = position
                f.user_matrix = m
            nuage = self.etiquettes[nom][0]
            nuage.points = position + 1.08 * longueur * axes_ned.T
        self.horloge.SetText(2, f"t = {t:.1f} s".replace(".", ","))
        if self.suivre:
            self._viser(position)
        if rendre:
            self.plotter.render()

    # -- zoom -------------------------------------------------------------------------------
    @property
    def zoom(self) -> float:
        return float(self._distance0 / self.plotter.camera.distance)

    @property
    def zoom_max(self) -> float:
        return max(ZOOM_MIN, float(self._distance0 / self._distance_engin(0.5 / CADRAGE_ENGIN)))

    def _distance_engin(self, longueurs: float) -> float:
        """Distance à laquelle la demi-largeur du champ vaut ``CADRAGE_ENGIN × longueurs`` maquettes."""
        demi_champ = np.radians(float(self.plotter.camera.view_angle)) / 2
        return CADRAGE_ENGIN * longueurs * self.etat.maquette.taille / float(np.tan(demi_champ))

    def cdg(self) -> Tableau:
        return np.asarray(ned_ensemble(self.etat.a(self.t).position, self.origine), dtype=float)

    def _viser(self, point: Tableau, distance: float | None = None) -> None:
        """Vise ``point`` sans changer la direction de regard (ni la distance, si elle n'est pas donnée)."""
        c = self.plotter.camera
        foyer, oeil = np.asarray(c.focal_point, dtype=float), np.asarray(c.position, dtype=float)
        regard = oeil - foyer
        if distance is not None:
            regard *= distance / float(np.linalg.norm(regard))
        c.focal_point = tuple(float(v) for v in point)
        c.position = tuple(float(v) for v in point + regard)
        self.plotter.renderer.ResetCameraClippingRange()

    def zoomer(self, facteur: float) -> float:
        """Multiplie le zoom (la caméra avance vers le point visé, ou le CDG si elle suit l'engin)."""
        zoom = float(np.clip(self.zoom * facteur, ZOOM_MIN, self.zoom_max))
        foyer = self.cdg() if self.suivre else np.asarray(self.plotter.camera.focal_point, dtype=float)
        self._viser(foyer, self._distance0 / zoom)
        self.plotter.render()
        return zoom

    def vue_entiere(self) -> None:
        self.suivre = False
        c = self.plotter.camera
        c.position, c.focal_point, c.up, c.view_angle = self._camera0
        self.plotter.renderer.ResetCameraClippingRange()
        self.plotter.render()

    def cadrer_engin(self) -> float:
        self.suivre = True
        zoom = float(np.clip(self._distance0 / self._distance_engin(self.echelle), ZOOM_MIN, self.zoom_max))
        self._viser(self.cdg(), self._distance0 / zoom)
        self.plotter.render()
        return zoom

    def suivre_engin(self, oui: bool) -> None:
        self.suivre = bool(oui)
        if self.suivre:
            self._viser(self.cdg())
            self.plotter.render()

    def instant_proche(self, x_px: float, y_px: float) -> float | None:
        """L'instant du point du vol le plus proche d'une position écran (pixels VTK, origine en bas)."""
        ren = self.plotter.renderer
        largeur, hauteur = ren.GetSize()
        if largeur == 0 or hauteur == 0:
            return None
        m = ren.GetActiveCamera().GetCompositeProjectionTransformMatrix(largeur / hauteur, -1, 1)
        mat = np.array([[m.GetElement(i, j) for j in range(4)] for i in range(4)])
        h = np.hstack([self.trace, np.ones((len(self.trace), 1))]) @ mat.T
        ndc = h[:, :2] / h[:, 3:4]
        ecran = np.column_stack([(ndc[:, 0] + 1) / 2 * largeur, (ndc[:, 1] + 1) / 2 * hauteur])
        d = np.hypot(ecran[:, 0] - x_px, ecran[:, 1] - y_px)
        i = int(np.argmin(d))
        return float(self.etat.t[i]) if d[i] <= 2 * RAYON_CLIC_PX else None

    def sur_double_clic(self, rappel: Callable[[float], None]) -> None:
        self._rappel_clic = rappel

    def _double_clic(self, *_: object) -> None:
        if self._rappel_clic is None:
            return
        x, y = self.plotter.iren.get_event_position()
        t = self.instant_proche(x, y)
        if t is not None:
            self._rappel_clic(t)

    def capture(self) -> NDArray[np.uint8]:
        return np.asarray(self.plotter.screenshot(return_img=True), dtype=np.uint8)

    def exporter(self, chemin: str | Path) -> Path:
        """Capture PNG de la vue (VTK ne fait pas de vectoriel : PDF/SVG viennent de Matplotlib)."""
        chemin = Path(chemin).with_suffix(".png") if Path(chemin).suffix.lower() != ".png" else Path(chemin)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        self.plotter.screenshot(str(chemin))
        return chemin

    def fermer(self) -> None:
        self.plotter.close()
