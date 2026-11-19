"""Moteur de rendu PyVista (VTK) hors écran — le seul module qui importe pyvista/vtk.

Sans écran, VTK passe par EGL : sur le GPU s'il y en a un, sinon en logiciel
(llvmpipe). OSMesa n'est pas dans la roue VTK de PyPI (bilan J0). Le module se
lance aussi comme sonde : ``python -m cfd_trajcast.engine.rendu.pyvista_ --sonde``
rend une sphère et affiche le pilote OpenGL — ``cfd-trajcast diagnostic`` l'exécute
dans un sous-processus, parce qu'une fenêtre OpenGL impossible fait planter le
processus au lieu de lever une exception.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.core import rotations as rot
from cfd_trajcast.core.camera import (
    ENU_VERS_NED,
    boite_ensemble,
    cadre_ensemble,
    echelle_ensemble,
    vers_ned,
)
from cfd_trajcast.engine.effets import Ciel, composer_ciel, lueur
from cfd_trajcast.engine.jets import coques_flamme, fumee, lumiere_jets, phase_active, scintillement
from cfd_trajcast.engine.scene import THEMES_ENSEMBLE, Plan, Scene
from cfd_trajcast.engine.textures import texture_damier, texture_terrain

__all__ = ["THEMES_ENSEMBLE", "MoteurPyVista", "sonde"]

#: Préfixe des lignes que la sonde imprime pour le diagnostic.
PREFIXE_SONDE = "SONDE:"


def _pv() -> Any:
    # Sans écran, aller droit à EGL : sinon VTK essaie X d'abord et le dit en rouge.
    # Un choix explicite de l'utilisateur (VTK_DEFAULT_OPENGL_WINDOW) prime.
    # VTK ne parle qu'à X ou à EGL : WAYLAND_DISPLAY ne compte pas.
    if not os.environ.get("DISPLAY"):
        os.environ.setdefault("VTK_DEFAULT_OPENGL_WINDOW", "vtkEGLRenderWindow")
    import pyvista as pv

    pv.OFF_SCREEN = True
    return pv


class MoteurPyVista:
    """Rend les vues d'un plan ; un ``Plotter`` hors écran par taille d'image demandée."""

    def __init__(self, scene: Scene, plan: Plan) -> None:
        self._pv = _pv()
        self.plan = plan
        self.scene = scene
        #: Ciel peint en NumPy derrière un rendu transparent (étoiles) plutôt que par VTK.
        self._ciel_compose = scene.style.ciel_etoiles > 0
        self._plotters: dict[tuple[int, int], tuple[Any, Any, list[tuple[Any, NDArray[np.float64]]]]] = {}
        self._ensembles: dict[tuple[str, tuple[int, int]], tuple[Any, Any, Any, float]] = {}
        self._jets: dict[tuple[int, int], dict[str, Any] | None] = {}

    def _plotter(self, taille: tuple[int, int]) -> tuple[Any, Any, list[tuple[Any, NDArray[np.float64]]]]:
        if taille in self._plotters:
            return self._plotters[taille]
        pv, scene, style = self._pv, self.scene, self.scene.style
        p = pv.Plotter(off_screen=True, window_size=taille)
        if self._ciel_compose:
            # Fond transparent : le ciel (et ses étoiles) est peint derrière, par effets.composer_ciel.
            p.set_background("black")
        elif style.ciel_haut != style.ciel_bas:
            p.set_background(style.ciel_bas, top=style.ciel_haut)
        else:
            p.set_background(style.ciel_bas)
        m = scene.maquette
        faces = np.hstack([np.full((len(m.faces), 1), 3), m.faces]).ravel()
        materiau: dict[str, Any] = (
            {"pbr": True, "metallic": style.fusee_metal, "roughness": style.fusee_rugosite}
            if style.fusee_metal > 0
            # Phong : le terme ambiant garde une maquette à contre-jour lisible (en PBR, sans carte
            # d'environnement, elle devient noire).
            else {"ambient": 0.2 if style.soleil is not None else 0.0,
                  "diffuse": 0.7 if style.soleil is not None else 1.0,
                  "specular": 0.3 if style.soleil is not None else 0.4, "specular_power": 25}
        )
        fusee = p.add_mesh(pv.PolyData(m.sommets, faces), color=scene.couleur_fusee, smooth_shading=True,
                           split_sharp_edges=True, **materiau)
        # Éléments translatés à chaque image : (maillage, points en coordonnées absolues).
        mobiles: list[tuple[Any, NDArray[np.float64]]] = []
        if scene.trace is not None and style.trace:
            trace = pv.lines_from_points(scene.trace)
            p.add_mesh(trace, color="#5a6b7d", line_width=2)
            mobiles.append((trace, scene.trace))
        if style.sol == "grille" and scene.sol is not None:
            points_sol, segments = scene.sol
            lignes = np.hstack([np.full((len(segments), 1), 2), segments]).ravel()
            sol = pv.PolyData(points_sol.copy(), lines=lignes)
            p.add_mesh(sol, color=style.sol_couleur, line_width=1)
            mobiles.append((sol, points_sol))
        elif style.sol in ("terrain", "damier", "uni") and scene.trace is not None:
            plan_sol, absolus = self._sol_texture(p)
            mobiles.append((plan_sol, absolus))
        if style.soleil is not None:
            p.remove_all_lights()
            az, el = np.radians(style.soleil[0]), np.radians(style.soleil[1])
            direction = np.array([np.sin(az) * np.cos(el), np.cos(az) * np.cos(el), np.sin(el)])
            soleil = pv.Light(position=tuple(direction), focal_point=(0, 0, 0), light_type="scene light",
                              intensity=style.intensite, color=style.lumiere_couleur)
            soleil.positional = False
            p.add_light(soleil)
            p.add_light(pv.Light(light_type="headlight", intensity=style.ambiance))
        self._jets[taille] = self._creer_jets(p) if scene.propulsion is not None else None
        if self._jets[taille] is not None and style.lumiere_jets > 0:
            # Lumière ponctuelle derrière la tuyère : elle éclaire le culot, la fumée et le sol au
            # décollage. Atténuation quadratique : moitié moins à une taille de maquette.
            lampe = pv.Light(light_type="scene light", intensity=0.0, color="#ffb060")
            lampe.positional = True
            lampe.cone_angle = 180
            lampe.attenuation_values = (1.0, 0.0, 1.0 / max(scene.maquette.taille, 1e-3) ** 2)
            p.add_light(lampe)
            self._jets[taille]["lampe"] = lampe  # type: ignore[index]
        if style.antialiasing != "aucun":
            # Sous EGL, VTK n'a ni FXAA ni MSAA utiles (mesuré au J4b) : seul le SSAA lisse les bords.
            p.enable_anti_aliasing("ssaa")
        self._plotters[taille] = (p, fusee, mobiles)
        return self._plotters[taille]

    def _sol_texture(self, p: Any) -> tuple[Any, NDArray[np.float64]]:
        """Grand plan texturé à z = 0 ; la texture se répète toutes les ``maille`` m."""
        pv, style = self._pv, self.scene.style
        assert self.scene.trace is not None
        horizontal = self.scene.trace[:, :2]
        centre = (horizontal.min(axis=0) + horizontal.max(axis=0)) / 2
        cote = max(40_000.0, 8 * float(np.max(np.ptp(horizontal, axis=0))))
        sol = pv.Plane(center=(centre[0], centre[1], style.sol_altitude), direction=(0, 0, 1), i_size=cote,
                       j_size=cote)
        if style.sol == "uni":
            p.add_mesh(sol, color=style.sol_couleur, ambient=0.3)
        else:
            maille = style.sol_maille or (400.0 if style.sol == "terrain" else 100.0)
            image = texture_terrain(style.sol_couleur) if style.sol == "terrain" else texture_damier(style.sol_couleur)
            sol.active_texture_coordinates = np.asarray(sol.active_texture_coordinates) * (cote / maille)
            texture = pv.Texture(image)
            texture.repeat = True
            texture.mipmap = True
            texture.interpolate = True
            p.add_mesh(sol, texture=texture, ambient=0.3)
        return sol, np.asarray(sol.points, dtype=float).copy()

    def _creer_jets(self, p: Any) -> dict[str, Any]:
        """Acteurs des flammes (un par phase × tuyère × coque) et des fumées (un par tuyère)."""
        pv, prop = self._pv, self.scene.propulsion
        assert prop is not None
        flammes = []
        for i, phase in enumerate(prop.phases):
            if phase.jet.flamme is None:
                continue
            for n, tuyere in enumerate(prop.tuyeres):
                for coque in coques_flamme(phase.jet.flamme, prop.rayon):
                    faces = np.hstack([np.full((len(coque.faces), 1), 3), coque.faces]).ravel()
                    mesh = pv.PolyData(coque.points, faces)
                    mesh.point_data["rgba"] = coque.rgba
                    acteur = p.add_mesh(mesh, scalars="rgba", rgba=True, lighting=False,
                                        show_scalar_bar=False)
                    acteur.SetVisibility(False)
                    flammes.append((i, n, tuyere, acteur, phase.jet.flamme.scintillement))
        fumees = []
        if any(ph.jet.fumee is not None for ph in prop.phases):
            for tuyere in prop.tuyeres:
                mesh = pv.PolyData(np.zeros((2, 3)), lines=np.array([2, 0, 1]))
                mesh.point_data["rgba"] = np.zeros((2, 4), dtype=np.uint8)
                # La fumée est éclairée comme le reste : la nuit (ambiance faible), elle reste sombre
                # sauf près de la flamme, qui l'éclaire (lumiere_jets).
                ambiant = 0.55 * min(1.0, self.scene.style.ambiance / 0.25)
                p.add_mesh(mesh, scalars="rgba", rgba=True, ambient=ambiant, diffuse=0.6, specular=0.0,
                           show_scalar_bar=False)
                fumees.append((tuyere, mesh))
        # Tri des couches translucides : sans lui, un matériau PBR vu à travers la fumée ou la
        # flamme laisse des fantômes de ses ailettes (constaté au J4).
        p.enable_depth_peeling(number_of_peels=6)
        return {"flammes": flammes, "fumees": fumees}

    def _jets_image(self, k: int, taille: tuple[int, int]) -> None:
        jets = self._jets.get(taille)
        scene, plan, prop = self.scene, self.plan, self.scene.propulsion
        if jets is None or prop is None:
            return
        t = float(plan.t_vol[k])
        r = rot.vers_matrice(plan.attitudes[k])
        actives = dict(phase_active(t, prop.phases, prop.fondu))
        if "lampe" in jets:
            lumiere = lumiere_jets(t, prop.phases, prop.tuyeres, prop.rayon, prop.fondu, plan.attitudes[k])
            lampe = jets["lampe"]
            if lumiere is None:
                lampe.intensity = 0.0
            else:
                position, couleur, poids = lumiere
                lampe.position = tuple(position)
                lampe.focal_point = tuple(position + r @ np.array([-1.0, 0.0, 0.0]))
                lampe.diffuse_color = couleur
                lampe.intensity = self.scene.style.lumiere_jets * poids
        for i, n, tuyere, acteur, amplitude in jets["flammes"]:
            poids = actives.get(i, 0.0)
            acteur.SetVisibility(poids > 0.01)
            if poids <= 0.01:
                continue
            # Scintillement : la flamme s'allonge et se raccourcit, un peu plus en long qu'en large.
            k_long = scintillement(t, amplitude, graine=7 * i + n)
            echelle = np.diag([k_long, 1 + 0.3 * (k_long - 1), 1 + 0.3 * (k_long - 1)])
            m = np.eye(4)
            m[:3, :3] = r @ echelle * poids ** 0.5
            m[:3, 3] = r @ tuyere
            acteur.user_matrix = m
            acteur.GetProperty().SetOpacity(poids)
        if scene.trace is None or scene.trace_t is None or scene.trace_attitudes is None:
            return
        vide = None
        for n, (tuyere, mesh) in enumerate(jets["fumees"]):
            ligne = fumee(t, scene.trace_t, scene.trace, scene.trace_attitudes, tuyere, prop.rayon,
                          prop.phases, prop.fondu, plan.positions[k], plan.attitudes[k], graine=n)
            if ligne is None:
                if vide is None:
                    vide = self._pv.PolyData(np.zeros((2, 3)), lines=np.array([2, 0, 1]))
                    vide.point_data["rgba"] = np.zeros((2, 4), dtype=np.uint8)
                mesh.copy_from(vide)
                continue
            points, rayons, rgba = ligne
            poly = self._pv.lines_from_points(points)
            poly.point_data["rayon"] = rayons
            poly.point_data["rgba"] = rgba
            tube = poly.tube(scalars="rayon", absolute=True, n_sides=20, capping=False)
            tube.set_active_scalars("rgba")
            mesh.copy_from(tube)

    def _plotter_ensemble(self, nom: str, taille: tuple[int, int]) -> tuple[Any, Any, Any, float]:
        """Vue d'ensemble : scène en coordonnées NED absolues, caméra fixe."""
        cle = (nom, taille)
        if cle in self._ensembles:
            return self._ensembles[cle]
        pv, scene = self._pv, self.scene
        if scene.trace is None or scene.trace_t is None:
            raise ValueError("la vue d'ensemble demande le tracé du vol dans la scène")
        params = self.plan.ensembles[nom]
        largeur, hauteur = taille
        u = hauteur / 1080
        p = pv.Plotter(off_screen=True, window_size=taille)
        th = THEMES_ENSEMBLE[scene.style.ensemble_theme]
        p.set_background(th["fond"])
        trace = vers_ned(scene.trace)
        boite = boite_ensemble(scene.trace, scene.style.sol_altitude)
        mini, maxi, bas_sol, marge = boite.mini, boite.maxi, boite.sol, boite.marge
        # Sol (D = 0) sous l'emprise du vol, et trace au sol.
        p.add_mesh(pv.Plane(center=((mini[0] + maxi[0]) / 2, (mini[1] + maxi[1]) / 2, bas_sol),
                            direction=(0, 0, 1), i_size=maxi[0] - mini[0] + 2 * marge,
                            j_size=maxi[1] - mini[1] + 2 * marge),
                   color=th["sol"], opacity=0.7)
        au_sol = trace.copy()
        au_sol[:, 2] = bas_sol
        p.add_mesh(pv.lines_from_points(au_sol), color=th["trace_sol"], line_width=max(1, round(1.5 * u)))
        p.add_mesh(pv.lines_from_points(trace), color=th["trace"], line_width=max(1, round(2 * u)), opacity=0.6)
        parcouru = pv.lines_from_points(trace[:2])
        p.add_mesh(parcouru, color=th["parcouru"], line_width=max(2, round(4 * u)))
        if scene.evenements:
            points = vers_ned(np.array([pos for _, pos in scene.evenements]))
            p.add_point_labels(points, [nom_e for nom_e, _ in scene.evenements],
                               point_size=max(4, round(10 * u)), font_size=max(8, round(18 * u)),
                               point_color=th["evenement"], text_color=th["texte"], shape_color=th["etiquette"],
                               shape_opacity=0.6,
                               always_visible=True)
        m = scene.maquette
        echelle = echelle_ensemble(scene.trace, m.taille, params)
        faces = np.hstack([np.full((len(m.faces), 1), 3), m.faces]).ravel()
        fusee = p.add_mesh(pv.PolyData(m.sommets, faces), color=th["fusee"], smooth_shading=True,
                           split_sharp_edges=True)
        # Graduations rondes : bornes arrondies au multiple d'un pas « rond » commun aux trois axes.
        bas_g, haut_g = boite.bas, boite.haut
        n_grad = [len(boite.graduations(i)) for i in range(3)]
        bornes = (bas_g[0], haut_g[0], bas_g[1], haut_g[1], bas_g[2], haut_g[2])
        p.show_grid(bounds=bornes, xtitle="Nord (m)", ytitle="Est (m)", ztitle="Bas (m)",
                    n_xlabels=n_grad[0], n_ylabels=n_grad[1], n_zlabels=n_grad[2],
                    color=th["grille"], font_size=max(8, round(14 * u)), fmt="%.0f")
        if echelle > 1:
            p.add_text(f"maquette agrandie × {echelle:.0f}", position="lower_right",
                       font_size=max(7, round(12 * u)), color=th["grille"])
        position, vise, haut = cadre_ensemble(scene.trace, params, largeur / hauteur, (bas_g, haut_g))
        c = p.camera
        c.position, c.focal_point, c.up = tuple(position), tuple(vise), tuple(haut)
        c.view_angle = params.champ
        self._ensembles[cle] = (p, fusee, parcouru, echelle)
        return self._ensembles[cle]

    def _image_ensemble(self, k: int, nom: str, taille: tuple[int, int]) -> NDArray[np.uint8]:
        p, fusee, parcouru, echelle = self._plotter_ensemble(nom, taille)
        plan, scene = self.plan, self.scene
        t = float(plan.t_vol[k])
        assert scene.trace is not None and scene.trace_t is not None
        dedans = scene.trace_t <= t
        points = vers_ned(np.vstack([scene.trace[dedans], plan.positions[k]]))
        if len(points) < 2:
            points = np.vstack([points, points])
        parcouru.copy_from(self._pv.lines_from_points(points))
        matrice = np.eye(4)
        matrice[:3, :3] = echelle * (ENU_VERS_NED @ rot.vers_matrice(plan.attitudes[k]))
        matrice[:3, 3] = vers_ned(plan.positions[k])
        fusee.user_matrix = matrice
        p.renderer.ResetCameraClippingRange()
        p.render()
        image = p.screenshot(return_img=True)
        return np.ascontiguousarray(np.asarray(image, dtype=np.uint8)[..., :3])

    def image(self, k: int, vue: str | None = None, taille: tuple[int, int] | None = None) -> NDArray[np.uint8]:
        """Image ``k`` vue par ``vue`` (la première par défaut), RGB ``(hauteur, largeur, 3)``."""
        plan = self.plan
        nom = vue if vue is not None else next(iter(plan.cameras))
        if nom in plan.ensembles:
            return self._image_ensemble(k, nom, taille or (plan.largeur, plan.hauteur))
        cam = plan.cameras[nom]
        p, fusee, mobiles = self._plotter(taille or (plan.largeur, plan.hauteur))
        origine = plan.positions[k]
        matrice = np.eye(4)
        matrice[:3, :3] = rot.vers_matrice(plan.attitudes[k])
        fusee.user_matrix = matrice
        # Origine flottante : tout est translaté pour que la fusée reste en (0, 0, 0).
        for maillage, absolus in mobiles:
            maillage.points = absolus - origine
        self._jets_image(k, taille or (plan.largeur, plan.hauteur))
        c = p.camera
        c.position = tuple(cam.decalage[k])
        c.focal_point = tuple(cam.visee[k])
        c.up = tuple(cam.haut[k])
        c.view_angle = float(cam.champ[k])
        # Plans de découpe : la fusée est à |decalage| de la caméra ; une caméra embarquée en est
        # tout près, une caméra au sol à des kilomètres (précision du tampon de profondeur).
        distance = float(np.linalg.norm(cam.decalage[k]))
        longueur = self.scene.maquette.taille
        c.clipping_range = (max(0.01, 0.05 * (distance - longueur)), distance + 1e5)
        p.render()
        style = self.scene.style
        if self._ciel_compose:
            rgba = np.asarray(p.screenshot(return_img=True, transparent_background=True), dtype=np.uint8)
            camera = (cam.decalage[k], cam.visee[k], cam.haut[k], float(cam.champ[k]))
            image = composer_ciel(rgba, Ciel(style.ciel_haut, style.ciel_bas, style.ciel_etoiles),
                                  camera=camera, t=float(plan.t_vol[k]))
        else:
            image = np.ascontiguousarray(np.asarray(p.screenshot(return_img=True), dtype=np.uint8)[..., :3])
        return lueur(image, style.lueur)

    def fermer(self) -> None:
        """Libère les contextes OpenGL."""
        for p, _, _ in self._plotters.values():
            p.close()
        for p, _, _, _ in self._ensembles.values():
            p.close()
        self._plotters.clear()
        self._ensembles.clear()

    def __enter__(self) -> MoteurPyVista:
        return self

    def __exit__(self, *exc: object) -> None:
        self.fermer()


def sonde() -> int:
    """Rend une sphère 64×64 ; imprime le pilote OpenGL et si l'image est non vide."""
    pv = _pv()
    p = pv.Plotter(off_screen=True, window_size=(64, 64))
    p.add_mesh(pv.Sphere(), color="red")
    image = np.asarray(p.screenshot(return_img=True))
    for ligne in p.ren_win.ReportCapabilities().splitlines():
        if "renderer string" in ligne or "version string" in ligne:
            print(PREFIXE_SONDE, ligne.strip())
    print(PREFIXE_SONDE, "classe", p.ren_win.GetClassName())
    print(PREFIXE_SONDE, "image", "non vide" if image.std() > 1 else "vide")
    p.close()
    return 0 if image.std() > 1 else 1


if __name__ == "__main__":
    if "--sonde" in sys.argv:
        sys.exit(sonde())
