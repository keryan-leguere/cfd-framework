"""Vue d'ensemble **interactive** en Matplotlib 3D — ce que l'interface affiche en grand.

Même scène que la figure paper (:mod:`cfd_trajcast.engine.figure_ensemble` : NED, Bas
inversé, proportions vraies, image non miroir, nombres en français), mais vivante :
:meth:`VueMpl.poser` met à jour, pour un instant ``t``, la maquette (placée autour du
CDG, :meth:`EtatVol.placer`), la partie parcourue du vol, les événements atteints et
les repères locaux au CDG. Les couches s'allument et s'éteignent par
:meth:`VueMpl.regler`. Aucune dépendance à Qt : la vue dessine dans n'importe quelle
``Figure`` — l'interface lui donne celle de son canevas, les tests une figure Agg.

Repères (une couleur Okabe-Ito par repère, axes nommés au bout des flèches) :
corps ``x_b y_b z_b``, NED local ``N E D``, aérodynamique ``x_a y_a z_a``, trajectoire
``x_k y_k z_k``. Leur longueur est celle de la maquette agrandie, ×1,3.

Vent le long du vol : :data:`FLECHES_VENT` flèches réparties en temps ; le plus fort
vent mesure :data:`PART_VENT` de la plus grande dimension de la boîte, et l'échelle est
écrite dans un coin.

Zoom (:meth:`VueMpl.zoomer`, :meth:`~VueMpl.cadrer_engin`, :meth:`~VueMpl.vue_entiere`) :
les **limites** des trois axes rétrécissent du même facteur autour d'un centre, la boîte
reste à sa place. Les proportions restent vraies et les graduations se refont pour
l'étendue visible. Un zoom vers un point du vol garde ce point sous le curseur : la
projection est orthographique, donc linéaire. :attr:`~VueMpl.suivre` recentre la vue sur
le CDG à chaque instant. Ce qui sort de la boîte est coupé avec Matplotlib ≥ 3.10
(``axlim_clip``) ; avant, il déborde de la boîte, sans conséquence sur les données. Le
sol est coupé à la main dans tous les cas.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.core.camera import ParametresEnsemble, vers_ned
from cfd_trajcast.engine import figure_ensemble as fe
from cfd_trajcast.engine.etat_vol import EtatVol

__all__ = ["CADRAGE_ENGIN", "COULEURS_REPERES", "FLECHES_VENT", "NOMS_AXES", "PAS_ZOOM", "ZOOM_MIN", "OptionsVue",
           "VueMpl"]

Tableau = NDArray[np.float64]

COULEURS_REPERES = {"corps": "#D55E00", "ned": "#555555", "aero": "#0072B2", "trajectoire": "#009E73"}
NOMS_AXES = {"corps": ("x_b", "y_b", "z_b"), "ned": ("N", "E", "D"),
             "aero": ("x_a", "y_a", "z_a"), "trajectoire": ("x_k", "y_k", "z_k")}
LIBELLES_REPERES = {"corps": "Corps (FRD)", "ned": "NED local", "aero": "Aérodynamique",
                    "trajectoire": "Trajectoire"}
FLECHES_VENT = 30
PART_VENT = 0.06
#: Rayon (px) dans lequel un clic choisit le point du vol le plus proche.
RAYON_CLIC_PX = 10.0
#: Un cran de molette (ou un « + ») multiplie le zoom par tant.
PAS_ZOOM = 1.25
#: « Cadrer l'engin » : la demi-largeur de la vue vaut tant de fois la maquette affichée (agrandie).
CADRAGE_ENGIN = 1.5
#: Zoom minimal : le vol entier. Le zoom maximal montre une demi-maquette **réelle** par demi-largeur.
ZOOM_MIN = 1.0


@dataclass(frozen=True)
class OptionsVue:
    """Couches affichées."""

    reperes: frozenset[str] = field(default_factory=lambda: frozenset({"corps"}))
    vent: bool = False
    maquette: bool = True
    trace_sol: bool = True
    evenements: bool = True
    #: Agrandissement de la maquette ; None = celui de la vue d'ensemble (automatique).
    agrandissement: float | None = None


def _indice(nom: str) -> str:
    base, _, indice = nom.partition("_")
    return f"${base}_{{{indice}}}$" if indice else nom


class VueMpl:
    """La scène 3D animable d'un :class:`EtatVol`, dans une ``Figure`` Matplotlib donnée."""

    def __init__(self, figure: Any, etat: EtatVol, parametres: ParametresEnsemble | None = None, *,
                 sol_altitude: float = 0.0, options: OptionsVue | None = None) -> None:
        cp = fe._cfd_plot()
        self.figure, self.etat = figure, etat
        self.parametres = parametres or ParametresEnsemble()
        self.scene = fe.SceneEnsemble(etat.trajectoire, etat.maquette, self.parametres, sol_altitude,
                                      fe.FACES_ANIMATION)
        self.options = options or OptionsVue()
        self.t = etat.debut
        with cp.style_context("paper"):
            figure.set_layout_engine("none")
            self.ax = fe.axes_ensemble(cp, figure, self.scene, (0.02, 0.02, 0.96, 0.96), "ortho",
                                       ecart_titre_bas=50.0)
            zoom_boite = cp.fit_box3d(self.ax, fill=0.80)
            avant = len(self.ax.collections)
            self.trace_sol = fe.decor_ensemble(self.ax, self.scene)
            self.sol = self.ax.collections[avant] if len(self.ax.collections) > avant else None
            self.chemin = cp.PathReveal(
                self.ax, self.scene.t, *self.scene.xyz.T,
                ghost_kw={"color": "0.75", "linewidth": 1.0, "zorder": 1.8},
                trail_kw={"color": "black", "linewidth": 1.6, "zorder": 2.0},
                head_kw={"marker": "", "zorder": 2.1},
            )
            self.marqueurs = fe.marqueurs_ensemble(self.ax, self.scene)
            from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # type: ignore[import-untyped,unused-ignore]

            self.fusee = Poly3DCollection(np.zeros((1, 3, 3)), linewidths=0.15, zorder=3.0)
            self.ax.add_collection3d(self.fusee)
            self.reperes = self._creer_reperes()
            self.vent, self.texte_vent = self._creer_vent()
            self.horloge = self.ax.text2D(0.01, 0.99, "", transform=self.ax.transAxes, va="top", fontsize=11)
        # Zoom : les limites du vol entier sont la référence ; rotation au bouton gauche, translation
        # au bouton du milieu. Le zoom de Matplotlib (bouton droit) est retiré : il peut étirer un axe
        # plus que les autres, et donc fausser les proportions.
        self._limites0 = (self.ax.get_xlim(), self.ax.get_ylim(), self.ax.get_zlim())
        self._demi0 = np.array([abs(b - a) / 2 for a, b in self._limites0])
        # Zoom de la boîte (fit_box3d) pour chaque forme de boîte déjà ajustée : la forme change
        # avec le zoom (cf. _cadrer), et l'ajuster coûte quelques dessins.
        self._forme_courante = self._forme(self._demi0)
        self._boites: dict[tuple[float, ...], float] = {self._forme_courante: zoom_boite}
        self.suivre = False
        try:
            self.ax.mouse_init(rotate_btn=1, pan_btn=2, zoom_btn=[])
        except TypeError:  # Matplotlib < 3.7 : pas de translation
            self.ax.mouse_init(rotate_btn=1, zoom_btn=[])
        self.decoupe = self._activer_decoupe()
        self.regler(self.options)
        self.poser(self.t)

    # -- construction ---------------------------------------------------------------------
    @property
    def echelle(self) -> float:
        return self.options.agrandissement or self.scene.echelle

    def _longueur_reperes(self) -> float:
        return 1.3 * self.echelle * float(np.ptp(self.etat.maquette.sommets[:, 0]))

    def _creer_reperes(self) -> dict[str, list[tuple[Any, Any]]]:
        out: dict[str, list[tuple[Any, Any]]] = {}
        for nom, couleur in COULEURS_REPERES.items():
            axes = []
            for k, axe in enumerate(NOMS_AXES[nom]):
                (ligne,) = self.ax.plot([0, 0], [0, 0], [0, 0], color=couleur, linewidth=1.6,
                                        linestyle="-" if k == 0 else ("--" if k == 1 else ":"), zorder=4.0)
                texte = self.ax.text(0, 0, 0, _indice(axe), color=couleur, fontsize=9, zorder=5.0)
                axes.append((ligne, texte))
            out[nom] = axes
        return out

    def _creer_vent(self) -> tuple[Any, Any]:
        if self.etat.vent is None:
            return None, None
        i = np.linspace(0, len(self.etat.t) - 1, FLECHES_VENT).round().astype(int)
        base = self.scene.vers_trace(self.etat.trajectoire.positions[i])
        vecteurs = vers_ned(self.etat.vent[i])[:, [1, 0, 2]]
        fort = float(np.max(np.linalg.norm(self.etat.vent, axis=1)))
        if not fort > 0:
            return None, None
        boite = float(np.max(self.scene.haut - self.scene.bas))
        m_par_ms = PART_VENT * boite / fort
        fleches = self.ax.quiver(*base.T, *(vecteurs * m_par_ms).T, color="#56B4E9", linewidth=1.0,
                                 arrow_length_ratio=0.25, zorder=2.5)
        texte = self.ax.text2D(0.99, 0.01, f"vent : 10 m/s ↔ {fe.nombre_fr(10 * m_par_ms)} m",
                               transform=self.ax.transAxes, ha="right", va="bottom", fontsize=8, color="#2b7fb5")
        return fleches, texte

    # -- état -----------------------------------------------------------------------------------
    def regler(self, options: OptionsVue) -> None:
        """Change les couches affichées (puis redessine à l'instant courant)."""
        self.options = options
        self.fusee.set_visible(options.maquette)
        self.trace_sol.set_visible(options.trace_sol)
        for nom, axes in self.reperes.items():
            for ligne, texte in axes:
                ligne.set_visible(nom in options.reperes)
                texte.set_visible(nom in options.reperes)
        if self.vent is not None:
            self.vent.set_visible(options.vent)
            self.texte_vent.set_visible(options.vent)
        self.poser(self.t)

    def poser(self, t: float) -> None:
        """Met la scène à l'instant ``t`` (borné au vol). Ne redessine pas : ``canvas.draw_idle()``."""
        etat, scene = self.etat, self.scene
        self.t = t = etat.borner(t)
        instant = etat.a(t)
        self.chemin.update(t)
        if self.options.maquette:
            tri = scene.vers_trace(etat.placer(scene.sommets, t, self.echelle))[scene.faces]
            couleurs = fe.ombrer(tri)
            self.fusee.set_verts(tri)
            self.fusee.set_facecolor(couleurs)
            self.fusee.set_edgecolor(couleurs)
        for te, m in self.marqueurs:
            m.set_visible(self.options.evenements and t >= te - 1e-9)
        origine = scene.vers_trace(instant.position[None, :])[0]
        longueur = self._longueur_reperes()
        for nom, axes in self.reperes.items():
            if nom not in self.options.reperes:
                continue
            triedre = instant.axes.get(nom)
            for k, (ligne, texte) in enumerate(axes):
                if triedre is None or not np.isfinite(triedre).all():
                    ligne.set_visible(False)
                    texte.set_visible(False)
                    continue
                bout = origine + longueur * vers_ned(triedre[:, k])[[1, 0, 2]]
                segment = np.column_stack([origine, bout])  # tableaux : la découpe à la boîte les exige
                ligne.set_data_3d(segment[0], segment[1], segment[2])
                texte.set_position_3d(tuple(bout))
                ligne.set_visible(True)
                texte.set_visible(True)
        self.horloge.set_text(f"t = {fe._secondes(t)}")
        if self.suivre:
            self._cadrer(origine, self.zoom)

    # -- zoom -------------------------------------------------------------------------------------
    def _activer_decoupe(self) -> bool:
        """Coupe à la boîte tout ce qui est dessiné en 3D (Matplotlib ≥ 3.10), sauf le sol."""
        # Les textes 2D (horloge, échelle du vent) n'ont pas l'attribut : ils restent où ils sont.
        artistes = [a for a in (*self.ax.lines, *self.ax.collections, *self.ax.texts)
                    if a is not self.sol and hasattr(a, "_axlim_clip")]
        for a in artistes:
            a._axlim_clip = True
        return bool(artistes)

    @property
    def zoom(self) -> float:
        """1 = le vol entier ; 4 = le plus grand côté visible vaut le quart du plus grand côté du vol."""
        demi = max(abs(b - a) / 2 for a, b in (self.ax.get_xlim(), self.ax.get_ylim(), self.ax.get_zlim()))
        return float(self._demi0.max() / demi)

    @property
    def zoom_max(self) -> float:
        return max(ZOOM_MIN, float(self._demi0.max() / (0.5 * self.etat.maquette.taille)))

    @staticmethod
    def _forme(demi: Tableau) -> tuple[float, ...]:
        return tuple(round(float(v), 3) for v in demi / demi.max())

    def centre(self) -> Tableau:
        """Le centre de la vue (coordonnées du tracé : Est, Nord, Bas)."""
        return np.array([sum(lim) / 2 for lim in (self.ax.get_xlim(), self.ax.get_ylim(), self.ax.get_zlim())])

    def cdg(self) -> Tableau:
        """Le CDG à l'instant courant (coordonnées du tracé)."""
        return np.asarray(self.scene.vers_trace(self.etat.a(self.t).position[None, :])[0], dtype=float)

    def _cadrer(self, centre: Tableau, zoom: float) -> None:
        """Limites de demi-largeur ``min(demi₀, D/zoom)`` par axe, D le plus grand demi-côté du vol.

        Le plus long côté rétrécit d'abord, puis tous ensemble : un vol presque vertical, vu
        de près, donne une boîte **cubique** autour de l'engin, pas une fente haute de
        170 m et large de 60. L'échelle reste la même sur les trois axes (proportions vraies) ;
        quand la forme de la boîte change, elle est réajustée à la zone de dessin.
        """
        demi = np.minimum(self._demi0, self._demi0.max() / zoom)
        reglages = (self.ax.set_xlim, self.ax.set_ylim, self.ax.set_zlim)
        for k, (regler, (a, b)) in enumerate(zip(reglages, self._limites0)):
            d = float(np.sign(b - a) * demi[k])  # signé : l'axe Bas reste inversé
            regler(centre[k] - d, centre[k] + d)
        forme = self._forme(demi)
        if forme != self._forme_courante:
            self._forme_courante = forme
            if forme in self._boites:
                self.ax.set_box_aspect(tuple(2 * demi), zoom=self._boites[forme])
            else:
                self.ax.set_box_aspect(tuple(2 * demi))
                self._boites[forme] = fe._cfd_plot().fit_box3d(self.ax, fill=0.80, iterations=2)
        self._couper_sol()

    def _couper_sol(self) -> None:
        """Le sol réduit à la partie visible de la boîte (caché si son altitude est hors champ)."""
        if self.sol is None:
            return
        (x0, x1), (y0, y1), (z0, z1) = self.ax.get_xlim(), self.ax.get_ylim(), self.ax.get_zlim()
        b, h, s = self.scene.bas, self.scene.haut, self.scene.sol
        xa, xb = max(b[0], min(x0, x1)), min(h[0], max(x0, x1))
        ya, yb = max(b[1], min(y0, y1)), min(h[1], max(y0, y1))
        visible = xa < xb and ya < yb and min(z0, z1) <= s <= max(z0, z1)
        self.sol.set_visible(visible)
        if visible:
            self.sol.set_verts([[(xa, ya, s), (xb, ya, s), (xb, yb, s), (xa, yb, s)]])

    def zoomer(self, facteur: float, vers: Tableau | None = None) -> float:
        """Multiplie le zoom par ``facteur`` (borné entre le vol entier et :attr:`zoom_max`).

        ``vers`` : un point (coordonnées du tracé) qui reste où il est à l'écran, celui sous la
        souris. Sans lui, on zoome autour du centre de la vue, ou sur le CDG quand la vue suit
        l'engin. Renvoie le zoom obtenu.
        """
        ancien = self.zoom
        zoom = float(np.clip(ancien * facteur, ZOOM_MIN, self.zoom_max))
        if self.suivre:
            centre = self.cdg()
        elif zoom <= ZOOM_MIN:
            centre = np.array([sum(lim) / 2 for lim in self._limites0])  # le vol entier, bien centré
        elif vers is not None:
            point = np.asarray(vers, dtype=float)
            avant = self._ecran(point)
            centre = point + (self.centre() - point) * (ancien / zoom)
            self._cadrer(centre, zoom)
            # La boîte a pu changer de forme (donc d'échelle à l'écran) : le point a glissé. La
            # projection orthographique est linéaire, un seul pas de moindres carrés le remet en place.
            apres = self._ecran(point)
            pas = np.abs(np.array([b - a for a, b in (self.ax.get_xlim(), self.ax.get_ylim(), self.ax.get_zlim())]))
            jacobien = np.column_stack([(self._ecran(point + h * e) - apres) / h for h, e in zip(pas, np.eye(3))])
            ecart = np.linalg.lstsq(jacobien, avant - apres, rcond=None)[0]
            centre = centre - ecart
        else:
            centre = self.centre()
        self._cadrer(centre, zoom)
        return zoom

    def _ecran(self, point: Tableau) -> Tableau:
        """Position à l'écran (pixels du canevas) d'un point en coordonnées du tracé."""
        from mpl_toolkits.mplot3d import proj3d  # type: ignore[import-untyped,unused-ignore]

        xs, ys, _ = proj3d.proj_transform(np.array([point[0]]), np.array([point[1]]), np.array([point[2]]),
                                          self.ax.get_proj())
        return np.asarray(self.ax.transData.transform(np.column_stack([xs, ys]))[0], dtype=float)

    def vue_entiere(self) -> None:
        """Retour au vol entier ; la vue cesse de suivre l'engin."""
        self.suivre = False
        self._cadrer(np.array([sum(lim) / 2 for lim in self._limites0]), 1.0)

    def cadrer_engin(self) -> float:
        """Zoom sur la maquette (:data:`CADRAGE_ENGIN`), et la vue la suit. Renvoie le zoom."""
        self.suivre = True
        zoom = float(np.clip(self._demi0.max() / (CADRAGE_ENGIN * self.echelle * self.etat.maquette.taille),
                             ZOOM_MIN, self.zoom_max))
        self._cadrer(self.cdg(), zoom)
        return zoom

    def suivre_engin(self, oui: bool) -> None:
        """Recentre la vue sur le CDG à chaque instant (le zoom ne change pas)."""
        self.suivre = bool(oui)
        if self.suivre:
            self._cadrer(self.cdg(), self.zoom)

    def _indice_proche(self, x_px: float, y_px: float, rayon: float) -> int | None:
        from mpl_toolkits.mplot3d import proj3d  # type: ignore[import-untyped,unused-ignore]

        xyz = self.scene.xyz
        xs, ys, _ = proj3d.proj_transform(xyz[:, 0], xyz[:, 1], xyz[:, 2], self.ax.get_proj())
        ecran = self.ax.transData.transform(np.column_stack([xs, ys]))
        d = np.hypot(ecran[:, 0] - x_px, ecran[:, 1] - y_px)
        i = int(np.argmin(d))
        return i if d[i] <= rayon else None

    def instant_proche(self, x_px: float, y_px: float) -> float | None:
        """L'instant du point du vol le plus proche d'un clic (pixels du canevas), ou None."""
        i = self._indice_proche(x_px, y_px, RAYON_CLIC_PX)
        return None if i is None else float(self.scene.t[i])

    def point_proche(self, x_px: float, y_px: float, rayon: float = 4 * RAYON_CLIC_PX) -> Tableau | None:
        """Le point du vol (coordonnées du tracé) sous la souris, pour y zoomer ; None s'il est loin."""
        i = self._indice_proche(x_px, y_px, rayon)
        return None if i is None else np.asarray(self.scene.xyz[i], dtype=float)

    def exporter(self, chemin: str | Path, dpi: int = 300) -> Path:
        """La vue telle qu'elle est affichée (angle, couches, instant), rognée sur son contenu."""
        cp = fe._cfd_plot()
        chemin = Path(chemin)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        self.figure.savefig(chemin, dpi=dpi, bbox_inches=cp.bbox3d(self.figure, pad=0.05), facecolor="white")
        return chemin

    def avec(self, **changements: Any) -> OptionsVue:
        """Les options courantes modifiées (pour ``regler``)."""
        return replace(self.options, **changements)
