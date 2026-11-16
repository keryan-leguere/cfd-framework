"""Moteur de rendu Blender (``bpy``) — le seul module qui importe bpy.

Même contrat que :class:`~cfd_trajcast.engine.rendu.pyvista_.MoteurPyVista` (le
:class:`~cfd_trajcast.engine.rendu.interface.Moteur`), autre qualité : ombres,
matériaux physiques, flammes émissives, fumée éclairée, avec EEVEE (GPU) ou Cycles
(lancer de rayons). Plus lent : compter de 0,3 à quelques secondes par vue et par image.

Ce que Blender fait, ce qu'il ne fait pas :

* la scène 3D (maquette, sol texturé, soleil, flammes, fumées, lumière des jets) est
  rendue sur **film transparent** ; le ciel, les étoiles et la lueur sont ceux de
  :mod:`cfd_trajcast.engine.effets` — mêmes couleurs, même ciel qu'avec PyVista ;
* les vues d'**ensemble** (schéma NED gradué) restent dessinées par PyVista : ce sont
  des graphiques, pas des plans de cinéma ;
* origine flottante comme partout : la maquette est à l'origine, le monde bouge.

Installation : ``pip install bpy`` — une roue par version de Python (bpy 5.x : Python
3.13 ; bpy 4.x / 5.0 : 3.11). Piège réglé ici : la roue embarque sa propre TBB, plus
récente que celle du système ; sans préchargement, ``import bpy`` échoue sur un symbole
``tbb::detail::r1::get_thread_reference_vertex`` introuvable.
"""

from __future__ import annotations

import contextlib
import ctypes
import importlib.util
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.core import rotations as rot
from cfd_trajcast.data.configuration import ConfigMoteur
from cfd_trajcast.engine.effets import Ciel, composer_ciel, lueur
from cfd_trajcast.engine.jets import (
    coques_flamme,
    fumee,
    lumiere_jets,
    phase_active,
    scintillement,
    tube,
)
from cfd_trajcast.engine.scene import Plan, Scene
from cfd_trajcast.engine.textures import teinte, texture_damier, texture_terrain

__all__ = ["MoteurBlender", "bpy_disponible", "importer_bpy"]

Tableau = NDArray[np.float64]
_BPY: list[Any] = []


#: Dossiers internes de Blender que ``import bpy`` ajoute à ``sys.path`` (``…/bpy/5.3/scripts/…``).
_INTERNE_BLENDER = re.compile(r"[/\\]bpy[/\\]\d+\.\d+[/\\]scripts([/\\]|$)")


def _nettoyer_chemins() -> None:
    """Retire de ``sys.path`` les dossiers internes de Blender.

    Un processus lancé en « spawn » hérite du ``sys.path`` de son parent : s'il contient
    ``…/bpy/5.3/scripts/modules``, ``import bpy`` y trouve le module *interne* de Blender
    (qui exige ``_bpy``, intégré à l'exécutable) au lieu de la roue — « No module named
    '_bpy' » dans chaque processus de rendu (constaté au J6).
    """
    if not _BPY:
        sys.path[:] = [p for p in sys.path if not _INTERNE_BLENDER.search(p)]


def bpy_disponible() -> bool:
    """bpy est-il installé (sans l'importer : c'est lent) ?"""
    _nettoyer_chemins()
    return importlib.util.find_spec("bpy") is not None


def importer_bpy() -> Any:
    """``import bpy``, après avoir préchargé la TBB qu'embarque la roue."""
    if _BPY:
        return _BPY[0]
    _nettoyer_chemins()
    spec = importlib.util.find_spec("bpy")
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError("moteur blender : bpy absent — pip install bpy (Python 3.13 pour bpy 5.x)")
    lib = Path(next(iter(spec.submodule_search_locations))) / "lib"
    for nom in ("libtbb.so.12", "libtbbmalloc.so.2"):
        if (lib / nom).is_file():
            ctypes.CDLL(str(lib / nom), mode=ctypes.RTLD_GLOBAL)
    import bpy

    _BPY.append(bpy)
    return bpy


def _rgb(hexa: str) -> tuple[float, float, float, float]:
    r, g, b = (float(v) for v in teinte(hexa))
    # Blender travaille en linéaire : les couleurs « écran » sont converties (sRGB → linéaire).
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (lin(r), lin(g), lin(b), 1.0)


def _lineaire(rgb: NDArray[np.floating[Any]]) -> NDArray[np.float64]:
    c = np.asarray(rgb, dtype=float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


class MoteurBlender:
    """Rend les vues d'un plan avec Blender ; les vues d'ensemble passent par PyVista."""

    def __init__(self, scene: Scene, plan: Plan, config: ConfigMoteur | None = None) -> None:
        self.bpy = importer_bpy()
        self.scene, self.plan = scene, plan
        self.config = config or ConfigMoteur(type="blender")
        self._pyvista: Any = None
        self._dossier = Path(tempfile.mkdtemp(prefix="cfd_trajcast_blender_"))
        self._construire()

    # -- construction de la scène ---------------------------------------------------------
    def _construire(self) -> None:
        bpy, style, cfg = self.bpy, self.scene.style, self.config
        bpy.ops.wm.read_factory_settings(use_empty=True)
        sc = bpy.context.scene
        self._sc = sc
        if cfg.rendu == "cycles":
            bpy.ops.preferences.addon_enable(module="cycles")
            sc.render.engine = "CYCLES"
            sc.cycles.device = "CPU"
            sc.cycles.samples = cfg.echantillons
            sc.cycles.use_denoising = True
        else:
            sc.render.engine = "BLENDER_EEVEE"
            sc.eevee.taa_render_samples = cfg.echantillons
        sc.render.film_transparent = True
        sc.render.resolution_percentage = 100
        sc.render.image_settings.file_format = "PNG"
        sc.render.image_settings.color_mode = "RGBA"
        sc.render.image_settings.compression = 0
        # Pas de courbe « filmique » : les couleurs du style doivent sortir telles quelles.
        sc.view_settings.view_transform = "Standard"
        sc.view_settings.look = "None"
        # Monde : invisible (film transparent) mais il éclaire — c'est le terme ambiant.
        monde = bpy.data.worlds.new("monde")
        sc.world = monde
        monde.use_nodes = True
        fond = monde.node_tree.nodes.get("Background")
        moyenne = 0.5 * (np.array(_rgb(style.ciel_haut)[:3]) + np.array(_rgb(style.ciel_bas)[:3]))
        fond.inputs["Color"].default_value = (*moyenne, 1.0)
        fond.inputs["Strength"].default_value = 2.0 * style.ambiance
        self._maquette()
        self._sol()
        self._soleil()
        self._jets()
        cam = bpy.data.cameras.new("camera")
        cam.sensor_fit = "VERTICAL"
        self._camera = bpy.data.objects.new("camera", cam)
        sc.collection.objects.link(self._camera)
        sc.camera = self._camera

    def _objet(self, nom: str, sommets: Tableau, faces: NDArray[np.int64]) -> Any:
        bpy = self.bpy
        mesh = bpy.data.meshes.new(nom)
        mesh.from_pydata(np.asarray(sommets, dtype=float).tolist(), [], np.asarray(faces).tolist())
        mesh.update()
        obj = bpy.data.objects.new(nom, mesh)
        self._sc.collection.objects.link(obj)
        return obj

    def _materiau(self, nom: str) -> tuple[Any, Any, Any]:
        mat = self.bpy.data.materials.new(nom)
        mat.use_nodes = True
        nodes, liens = mat.node_tree.nodes, mat.node_tree.links
        return mat, nodes, liens

    def _maquette(self) -> None:
        m, style = self.scene.maquette, self.scene.style
        obj = self._objet("maquette", m.sommets, m.faces)
        mesh = obj.data
        if hasattr(mesh, "shade_smooth"):
            mesh.shade_smooth()
        if hasattr(mesh, "set_sharp_from_angle"):
            mesh.set_sharp_from_angle(angle=np.radians(35.0))
        mat, nodes, _ = self._materiau("peinture")
        bsdf = nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = _rgb(style.fusee_couleur)
        bsdf.inputs["Metallic"].default_value = style.fusee_metal
        bsdf.inputs["Roughness"].default_value = style.fusee_rugosite
        mesh.materials.append(mat)
        self._fusee = obj

    def _sol(self) -> None:
        sc, style = self.scene, self.scene.style
        self._plan_sol = None
        if sc.trace is None:
            return
        horizontal = sc.trace[:, :2]
        centre = (horizontal.min(axis=0) + horizontal.max(axis=0)) / 2
        cote = max(40_000.0, 8 * float(np.max(np.ptp(horizontal, axis=0))))
        h = cote / 2
        obj = self._objet("sol", np.array([[-h, -h, 0], [h, -h, 0], [h, h, 0], [-h, h, 0]]),
                          np.array([[0, 1, 2, 3]]))
        uv = obj.data.uv_layers.new(name="UVMap")
        maille = style.sol_maille or (400.0 if style.sol == "terrain" else 100.0)
        n = cote / maille
        for i, (u, v) in enumerate(((0, 0), (n, 0), (n, n), (0, n))):
            uv.data[i].uv = (u, v)
        mat, nodes, liens = self._materiau("sol")
        bsdf = nodes.get("Principled BSDF")
        bsdf.inputs["Roughness"].default_value = 1.0
        if style.sol in ("terrain", "damier"):
            pixels = texture_terrain(style.sol_couleur) if style.sol == "terrain" else texture_damier(style.sol_couleur)
            hauteur, largeur = pixels.shape[:2]
            img = self.bpy.data.images.new("texture_sol", largeur, hauteur, alpha=False)
            rgba = np.concatenate([pixels[::-1] / 255.0, np.ones((hauteur, largeur, 1))], axis=2)
            img.pixels.foreach_set(rgba.astype(np.float32).ravel())
            img.pack()
            tex = nodes.new("ShaderNodeTexImage")
            tex.image = img
            tex.interpolation = "Cubic"
            liens.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        else:
            bsdf.inputs["Base Color"].default_value = _rgb(style.sol_couleur)
        obj.data.materials.append(mat)
        self._plan_sol = obj
        self._centre_sol = np.array([centre[0], centre[1], style.sol_altitude])

    def _soleil(self) -> None:
        bpy, style = self.bpy, self.scene.style
        if style.soleil is None:
            # Pas de soleil déclaré : une lumière douce venant de la caméra (comme le « headlight »
            # de VTK), mise à jour à chaque image.
            self._lampe_camera = bpy.data.objects.new("lampe", bpy.data.lights.new("lampe", "SUN"))
            self._lampe_camera.data.energy = 3.0
            self._sc.collection.objects.link(self._lampe_camera)
            return
        self._lampe_camera = None
        az, el = np.radians(style.soleil[0]), np.radians(style.soleil[1])
        vers_soleil = np.array([np.sin(az) * np.cos(el), np.cos(az) * np.cos(el), np.sin(el)])
        lum = bpy.data.lights.new("soleil", "SUN")
        lum.energy = 4.0 * style.intensite
        lum.color = _rgb(style.lumiere_couleur)[:3]
        lum.angle = np.radians(1.0)
        obj = bpy.data.objects.new("soleil", lum)
        obj.matrix_world = self._regard(np.zeros(3), -vers_soleil, np.array([0.0, 0.0, 1.0]))
        self._sc.collection.objects.link(obj)

    def _jets(self) -> None:
        bpy, prop = self.bpy, self.scene.propulsion
        self._flammes: list[tuple[int, int, Tableau, Any, float]] = []
        self._fumees: list[tuple[Tableau, Any]] = []
        self._lampe_jet = None
        if prop is None:
            return
        mat, nodes, liens = self._materiau("flamme")
        attr = nodes.new("ShaderNodeAttribute")
        attr.attribute_name = "rgba"
        poids = nodes.new("ShaderNodeAttribute")
        poids.attribute_type = "OBJECT"
        poids.attribute_name = "poids"
        emission = nodes.new("ShaderNodeEmission")
        # Au-delà de 1, la vue « Standard » écrête au blanc : la couleur de la flamme doit survivre,
        # c'est la lueur (effets.lueur) qui fait le halo.
        emission.inputs["Strength"].default_value = 1.6
        liens.new(attr.outputs["Color"], emission.inputs["Color"])
        fois = nodes.new("ShaderNodeMath")
        fois.operation = "MULTIPLY"
        liens.new(attr.outputs["Alpha"], fois.inputs[0])
        liens.new(poids.outputs["Fac"], fois.inputs[1])
        transparent = nodes.new("ShaderNodeBsdfTransparent")
        melange = nodes.new("ShaderNodeMixShader")
        liens.new(fois.outputs["Value"], melange.inputs["Fac"])
        liens.new(transparent.outputs["BSDF"], melange.inputs[1])
        liens.new(emission.outputs["Emission"], melange.inputs[2])
        sortie = nodes.get("Material Output")
        liens.new(melange.outputs["Shader"], sortie.inputs["Surface"])
        nodes.remove(nodes.get("Principled BSDF"))
        self._transparent(mat)
        for i, phase in enumerate(prop.phases):
            if phase.jet.flamme is None:
                continue
            for n, tuyere in enumerate(prop.tuyeres):
                for c, coque in enumerate(coques_flamme(phase.jet.flamme, prop.rayon)):
                    obj = self._objet(f"flamme_{i}_{n}_{c}", coque.points, coque.faces)
                    self._couleurs(obj.data, coque.rgba.astype(float) / 255.0)
                    obj.data.materials.append(mat)
                    obj["poids"] = 0.0
                    obj.hide_render = True
                    self._flammes.append((i, n, tuyere, obj, phase.jet.flamme.scintillement))
        if any(ph.jet.fumee is not None for ph in prop.phases):
            mat_f, nodes, liens = self._materiau("fumee")
            bsdf = nodes.get("Principled BSDF")
            attr = nodes.new("ShaderNodeAttribute")
            attr.attribute_name = "rgba"
            liens.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
            liens.new(attr.outputs["Alpha"], bsdf.inputs["Alpha"])
            bsdf.inputs["Roughness"].default_value = 1.0
            self._transparent(mat_f, faces_arriere=False)
            for n, tuyere in enumerate(prop.tuyeres):
                obj = self._objet(f"fumee_{n}", np.zeros((3, 3)), np.array([[0, 1, 2]]))
                obj.data.materials.append(mat_f)
                obj.hide_render = True
                self._fumees.append((tuyere, obj))
        if self.scene.style.lumiere_jets > 0:
            lum = bpy.data.lights.new("lumiere_jets", "POINT")
            lum.shadow_soft_size = prop.rayon
            # Pas d'ombres pour la lampe du jet : collée au culot, elle n'en ferait que du grain.
            lum.use_shadow = False
            self._lampe_jet = bpy.data.objects.new("lumiere_jets", lum)
            self._sc.collection.objects.link(self._lampe_jet)

    def _transparent(self, mat: Any, faces_arriere: bool = True) -> None:
        # EEVEE (4.2+) : mélange trié plutôt que tramage ; ignoré par Cycles. La fumée ne montre
        # pas ses faces arrière : vues à travers l'avant, elles dessinent des anneaux sombres.
        for attribut, valeur in (("surface_render_method", "BLENDED"), ("use_backface_culling", not faces_arriere),
                                 ("use_transparency_overlap", faces_arriere)):
            if hasattr(mat, attribut):
                setattr(mat, attribut, valeur)

    @staticmethod
    def _couleurs(mesh: Any, rgba: NDArray[np.float64]) -> None:
        couleurs = np.array(rgba, dtype=float)
        couleurs[:, :3] = _lineaire(couleurs[:, :3])
        attr = mesh.color_attributes.new(name="rgba", type="FLOAT_COLOR", domain="POINT")
        attr.data.foreach_set("color", couleurs.astype(np.float32).ravel())

    @staticmethod
    def _regard(position: Tableau, direction: Tableau, haut: Tableau) -> Any:
        """Matrice monde d'un objet qui regarde selon ``direction`` (−Z local), ``haut`` ≈ +Y local."""
        from mathutils import Matrix

        f = direction / np.linalg.norm(direction)
        r = np.cross(f, haut)
        if np.linalg.norm(r) < 1e-9:
            r = np.cross(f, np.array([0.0, 1.0, 0.0]))
        r /= np.linalg.norm(r)
        u = np.cross(r, f)
        m = np.eye(4)
        m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = r, u, -f, position
        return Matrix(m.tolist())

    # -- une image ---------------------------------------------------------------------------
    def _poser(self, k: int) -> None:
        from mathutils import Matrix

        plan, scene, prop = self.plan, self.scene, self.scene.propulsion
        origine = plan.positions[k]
        r = rot.vers_matrice(plan.attitudes[k])
        m = np.eye(4)
        m[:3, :3] = r
        self._fusee.matrix_world = Matrix(m.tolist())
        if self._plan_sol is not None:
            self._plan_sol.location = tuple(self._centre_sol - origine)
        if prop is None:
            return
        t = float(plan.t_vol[k])
        actives = dict(phase_active(t, prop.phases, prop.fondu))
        for i, n, tuyere, obj, amplitude in self._flammes:
            poids = actives.get(i, 0.0)
            obj.hide_render = poids <= 0.01
            if poids <= 0.01:
                continue
            k_long = scintillement(t, amplitude, graine=7 * i + n)
            echelle = np.diag([k_long, 1 + 0.3 * (k_long - 1), 1 + 0.3 * (k_long - 1)])
            mf = np.eye(4)
            mf[:3, :3] = r @ echelle * poids**0.5
            mf[:3, 3] = r @ tuyere
            obj.matrix_world = Matrix(mf.tolist())
            obj["poids"] = poids
        if self._lampe_jet is not None:
            lumiere = lumiere_jets(t, prop.phases, prop.tuyeres, prop.rayon, prop.fondu, plan.attitudes[k])
            self._lampe_jet.hide_render = lumiere is None
            if lumiere is not None:
                position, couleur, poids = lumiere
                self._lampe_jet.location = tuple(position)
                self._lampe_jet.data.color = tuple(couleur)
                self._lampe_jet.data.energy = 40.0 * scene.style.lumiere_jets * poids * scene.maquette.taille**2
        if scene.trace is None or scene.trace_t is None or scene.trace_attitudes is None:
            return
        for n, (tuyere, obj) in enumerate(self._fumees):
            ligne = fumee(t, scene.trace_t, scene.trace, scene.trace_attitudes, tuyere, prop.rayon,
                          prop.phases, prop.fondu, plan.positions[k], plan.attitudes[k], graine=n)
            obj.hide_render = ligne is None
            if ligne is None:
                continue
            points, rayons, rgba = ligne
            sommets, faces = tube(points, rayons, 16)
            mesh = obj.data
            mesh.clear_geometry()
            mesh.from_pydata(sommets.tolist(), [], faces.tolist())
            if "rgba" in mesh.color_attributes:
                mesh.color_attributes.remove(mesh.color_attributes["rgba"])
            self._couleurs(mesh, np.repeat(rgba.astype(float) / 255.0, 16, axis=0))
            mesh.update()

    def _lire(self, chemin: Path, taille: tuple[int, int]) -> NDArray[np.uint8]:
        """PNG RGBA (alpha droit) écrit par Blender → RGBA prémultiplié, de haut en bas."""
        img = self.bpy.data.images.load(str(chemin), check_existing=False)
        try:
            largeur, hauteur = taille
            buf = np.empty(largeur * hauteur * 4, dtype=np.float32)
            img.pixels.foreach_get(buf)
        finally:
            self.bpy.data.images.remove(img)
        rgba = buf.reshape(hauteur, largeur, 4)[::-1]
        rgba[..., :3] *= rgba[..., 3:4]
        return np.asarray(np.clip(rgba * 255 + 0.5, 0, 255), dtype=np.uint8)

    def image(self, k: int, vue: str | None = None, taille: tuple[int, int] | None = None) -> NDArray[np.uint8]:
        """Image ``k`` vue par ``vue``, RGB ``(hauteur, largeur, 3)``."""
        plan = self.plan
        nom = vue if vue is not None else next(iter(plan.cameras))
        taille = taille or (plan.largeur, plan.hauteur)
        if nom in plan.ensembles:
            if self._pyvista is None:
                from cfd_trajcast.engine.rendu.pyvista_ import MoteurPyVista

                self._pyvista = MoteurPyVista(self.scene, plan)
            return self._pyvista.image(k, nom, taille)  # type: ignore[no-any-return]
        cam = plan.cameras[nom]
        self._poser(k)
        position, visee, haut = cam.decalage[k], cam.visee[k], cam.haut[k]
        self._camera.matrix_world = self._regard(position, visee - position, haut)
        donnees = self._camera.data
        donnees.angle_y = np.radians(float(cam.champ[k]))
        distance = float(np.linalg.norm(position))
        donnees.clip_start = max(0.01, 0.05 * (distance - self.scene.maquette.taille))
        donnees.clip_end = distance + 1e5
        if self._lampe_camera is not None:
            self._lampe_camera.matrix_world = self._regard(position, visee - position, haut)
        sc = self._sc
        sc.render.resolution_x, sc.render.resolution_y = taille
        chemin = self._dossier / f"{os.getpid()}_{nom}.png"
        sc.render.filepath = str(chemin)
        self.bpy.ops.render.render(write_still=True)
        rgba = self._lire(chemin, taille)
        style = self.scene.style
        image = composer_ciel(rgba, Ciel(style.ciel_haut, style.ciel_bas, style.ciel_etoiles),
                              camera=(position, visee, haut, float(cam.champ[k])), t=float(plan.t_vol[k]))
        return lueur(image, style.lueur)

    def fermer(self) -> None:
        """Libère le moteur PyVista éventuel et les fichiers temporaires."""
        if self._pyvista is not None:
            self._pyvista.fermer()
            self._pyvista = None
        for p in self._dossier.glob("*"):
            p.unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            self._dossier.rmdir()

    def __enter__(self) -> MoteurBlender:
        return self

    def __exit__(self, *exc: object) -> None:
        self.fermer()
