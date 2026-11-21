"""Courbes de l'interface, sans Qt : télémétrie en fonction du temps, et panneau Vent.

:class:`Courbes` trace les séries choisies d'un :class:`EtatVol` en sous-graphes
empilés qui partagent l'axe du temps, avec un curseur vertical commun et un trait
pointillé par événement ; :meth:`Courbes.instant` traduit un clic en instant.

:class:`PanneauVent` : à gauche l'hodographe du vent (VE en abscisse, VN en
ordonnée, couleur = altitude, la rose se lit comme une carte), à droite la composante
verticale en fonction de l'altitude ; le point courant est marqué sur les deux.

Style ``paper`` de cfd-plot, comme le reste. Les deux dessinent dans une ``Figure``
donnée — celle d'un canevas Qt dans l'interface, une figure Agg dans les tests et
pour les exports.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cfd_trajcast.engine import figure_ensemble as fe
from cfd_trajcast.engine.etat_vol import EtatVol

__all__ = ["Courbes", "PanneauVent", "exporter_figure", "libelle_serie"]


def exporter_figure(figure: Any, chemin: str | Path, dpi: int = 300) -> Path:
    """Une figure de l'interface (courbes, panneau vent) telle qu'affichée, rognée."""
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(chemin, dpi=dpi, bbox_inches="tight", pad_inches=0.05, facecolor="white")
    return chemin

COULEURS = ("#000000", "#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9")


def libelle_serie(etat: EtatVol, cle: str) -> str:
    serie = etat.series[cle]
    return f"{serie.libelle} ({serie.unite})" if serie.unite else serie.libelle


class Courbes:
    """Sous-graphes empilés des séries choisies, curseur de temps commun."""

    def __init__(self, figure: Any, etat: EtatVol) -> None:
        self.figure, self.etat = figure, etat
        self.cles: list[str] = []
        self.axes: list[Any] = []
        self.curseurs: list[Any] = []
        self.t = etat.debut

    def choisir(self, cles: Sequence[str]) -> None:
        """Redessine pour ces séries (dans cet ordre) ; une liste vide laisse un message."""
        cp = fe._cfd_plot()
        inconnues = [c for c in cles if c not in self.etat.series]
        if inconnues:
            raise KeyError(f"séries inconnues : {', '.join(inconnues)}")
        self.cles = list(cles)
        fig = self.figure
        fig.clear()
        self.axes, self.curseurs = [], []
        with cp.style_context("paper"):
            fig.set_layout_engine("none")
            if not self.cles:
                fig.text(0.5, 0.5, "Cocher des grandeurs dans la liste", ha="center", va="center", color="0.5")
                return
            n = len(self.cles)
            haut, bas, gauche, droite = 0.98, 0.10 if n < 4 else 0.06, 0.11, 0.98
            h = (haut - bas) / n
            for k, cle in enumerate(self.cles):
                ax = fig.add_axes((gauche, haut - (k + 1) * h + 0.012, droite - gauche, h - 0.024),
                                  sharex=self.axes[0] if self.axes else None)
                serie = self.etat.series[cle]
                ax.plot(self.etat.t, serie.valeurs, color=COULEURS[k % len(COULEURS)], linewidth=1.1)
                for _, te in ((e.nom, e.t) for e in self.etat.trajectoire.evenements):
                    ax.axvline(te, color="0.75", linewidth=0.6, linestyle=":")
                self.curseurs.append(ax.axvline(self.t, color="#D55E00", linewidth=1.0))
                ax.text(0.01, 0.95, libelle_serie(self.etat, cle), transform=ax.transAxes, fontsize=8,
                        va="top", ha="left", bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.8, "pad": 1})
                ax.tick_params(labelsize=7)
                ax.minorticks_off()
                if k < n - 1:
                    ax.tick_params(labelbottom=False)
                self.axes.append(ax)
            self.axes[-1].set_xlabel("t (s)", fontsize=8)
            self.axes[0].set_xlim(self.etat.debut, self.etat.fin)

    def poser(self, t: float) -> None:
        self.t = t
        for c in self.curseurs:
            c.set_xdata([t, t])

    def instant(self, ax: Any, x: float | None) -> float | None:
        """L'instant d'un clic dans un des sous-graphes (abscisse en données), sinon None."""
        if ax not in self.axes or x is None:
            return None
        return self.etat.borner(float(x))


class PanneauVent:
    """Hodographe (VE, VN) coloré par l'altitude, et VZ en fonction de l'altitude."""

    def __init__(self, figure: Any, etat: EtatVol) -> None:
        if etat.vent is None:
            raise ValueError("pas de vent déclaré (section vent du YAML)")
        cp = fe._cfd_plot()
        self.figure, self.etat = figure, etat
        vent = etat.vent
        altitude = etat.trajectoire.positions[:, 2]
        with cp.style_context("paper"):
            figure.set_layout_engine("none")
            self.hodo = figure.add_axes((0.10, 0.17, 0.38, 0.72))
            self.vz = figure.add_axes((0.62, 0.17, 0.34, 0.72))
            nuage = self.hodo.scatter(vent[:, 0], vent[:, 1], c=altitude, s=4, cmap="viridis", linewidths=0)
            self.hodo.axhline(0, color="0.8", linewidth=0.6)
            self.hodo.axvline(0, color="0.8", linewidth=0.6)
            self.hodo.set_aspect("equal", adjustable="datalim")
            self.hodo.set_xlabel("vers l'Est (m/s)", fontsize=8)
            self.hodo.set_ylabel("vers le Nord (m/s)", fontsize=8)
            self.hodo.set_title("Vent horizontal", fontsize=9)
            barre = figure.colorbar(nuage, ax=self.hodo, fraction=0.06, pad=0.02)
            barre.set_label("altitude (m)", fontsize=7)
            barre.ax.tick_params(labelsize=7)
            self.vz.plot(vent[:, 2], altitude, color="#0072B2", linewidth=1.0)
            self.vz.axvline(0, color="0.8", linewidth=0.6)
            self.vz.set_xlabel("vertical, > 0 vers le haut (m/s)", fontsize=8)
            self.vz.set_ylabel("altitude (m)", fontsize=8)
            self.vz.set_title("Vent vertical", fontsize=9)
            for ax in (self.hodo, self.vz):
                ax.tick_params(labelsize=7)
                ax.minorticks_off()
            (self.point_hodo,) = self.hodo.plot([0], [0], "o", color="#D55E00", markeredgecolor="black",
                                                markersize=6, zorder=5)
            (self.point_vz,) = self.vz.plot([0], [0], "o", color="#D55E00", markeredgecolor="black",
                                            markersize=6, zorder=5)
        self.poser(etat.debut)

    def poser(self, t: float) -> None:
        i = self.etat.a(t)
        assert i.vent is not None
        self.point_hodo.set_data([i.vent[0]], [i.vent[1]])
        self.point_vz.set_data([i.vent[2]], [i.position[2]])
