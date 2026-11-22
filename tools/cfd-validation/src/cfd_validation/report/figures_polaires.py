"""Polaires des tables, tracées par ``cfd_plot.batch_plot`` (profil « paper », SVG).

Une figure par table, par abscisse et par condition (les autres axes sur un de
leurs nœuds) :

- **trait vermillon** : le code, appelé finement de ``ecart × étendue`` avant
  la première borne à autant après la dernière ;
- **points bleus** : les nœuds de la table, par-dessus ;
- **zones grisées** : au-delà des bornes, avec la consigne déclarée du côté
  (« sature », « extrapole ») ; pointillés aux bornes.

Ce que les trois tests vérifient s'y lit d'un coup d'œil : la courbe passe par
les points (lecture), elle est droite entre eux (interpolation), elle est plate
ou prolonge la dernière maille dans la zone grisée (bornes).

En option (``superposer``, le ``fold`` « overlay » de ``batch_plot``), toutes les
valeurs d'un axe de condition sur une même figure, sous ``SUPERPOSITION/`` : une
couleur par valeur, le trait pour le code, les points pour la table.

Arborescence, sous le dossier donné ::

    <TABLE>/POLAIRE_<AXE>/<COND>_<v>/…/<TABLE>_vs_<axe>.svg
    <TABLE>/POLAIRE_<AXE>/SUPERPOSITION/…/<TABLE>_vs_<axe>_by_<COND>.svg
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cfd_validation.engine.polaires import COLONNE_VALEUR, Polaire
from cfd_validation.report.figures import BLEU, VERMILLON, _cfd_plot, _fichier
from cfd_validation.report.figures_tables import FORMATS_TABLES

__all__ = ["DOSSIER_SUPERPOSITION", "HabillagePolaire", "Libelles", "tracer_polaires"]

#: Sous-dossier des figures superposées, dans chaque ``POLAIRE_<AXE>``.
DOSSIER_SUPERPOSITION = "SUPERPOSITION"
#: Libellé affiché d'un axe ou d'une table : ``"α"`` ou ``("α", "°")``.
Libelles = Mapping[str, "str | tuple[str, str]"]
#: Condition fictive des tables 1D : ``batch_plot`` veut au moins un point de vol.
_SEULE = "_seule"
ZONE = "#EDEDED"
SOURCE_CODE = "code"
SOURCE_TABLE = "table"


def _libelle(libelles: Libelles, nom: str) -> tuple[str, str | None]:
    v = libelles.get(nom)
    if v is None:
        return nom, None
    if isinstance(v, str):
        return v, None
    return str(v[0]), (str(v[1]) if v[1] else None)


def _texte_valeur(v: float) -> str:
    return f"{v:g}".replace("-", "−")


def _unite(unite: str | None) -> str:
    if not unite:
        return ""
    return unite if unite.startswith("°") or unite == "%" else f" {unite}"


@dataclass(frozen=True)
class HabillagePolaire:
    """Le crochet ``on_before_save`` : zones hors bornes, consignes, légende, titres.

    Une dataclass de module, gelée : elle se sérialise, et ``batch_plot`` garde
    ses processus parallèles.
    """

    nom: str
    abscisse: str
    bornes: tuple[float, float]
    consignes: tuple[str | None, str | None]
    prolongements: tuple[float, float]
    superpose: str | None
    unidim: bool
    #: ``(colonne, libellé, unité)`` de chaque axe de condition.
    conditions: tuple[tuple[str, str, str | None], ...] = ()

    def _limites(self) -> tuple[float, float]:
        b0, b1 = self.bornes
        e = b1 - b0
        lo, hi = b0 - self.prolongements[0] * e, b1 + self.prolongements[1] * e
        marge = 0.015 * (hi - lo)
        return lo - marge, hi + marge

    def _zones(self, ax: Any) -> None:
        from matplotlib.transforms import blended_transform_factory

        lo, hi = self._limites()
        trans = blended_transform_factory(ax.transData, ax.transAxes)
        for k, (debut, fin) in enumerate(((lo, self.bornes[0]), (self.bornes[1], hi))):
            ax.axvline(self.bornes[k], color="0.45", lw=0.6, ls=(0, (1.5, 1.5)), zorder=1)
            if self.prolongements[k] <= 0:
                continue
            ax.axvspan(debut, fin, facecolor=ZONE, edgecolor="none", zorder=0)
            consigne = self.consignes[k]
            if consigne:
                ax.text((debut + fin) / 2, 0.97, consigne, transform=trans, rotation=90, ha="center", va="top",
                        fontsize=6.5, color="0.35", style="italic", zorder=5,
                        bbox={"facecolor": ZONE, "edgecolor": "none", "pad": 0.8})
        ax.set_xlim(lo, hi)

    def _legende_simple(self, cp: Any, ax: Any) -> None:
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch

        poignees: list[Any] = [
            Line2D([], [], color=VERMILLON, lw=1.2, label="code"),
            Line2D([], [], color=BLEU, marker="o", ls="", ms=4, label="table (nœuds)"),
        ]
        if any(p > 0 for p in self.prolongements):
            poignees.append(Patch(facecolor=ZONE, edgecolor="none", label="hors des bornes"))
        cp.make_legend(ax, handles=poignees, fontsize=7)

    def _legende_superposee(self, cp: Any, ax: Any) -> None:
        from matplotlib.lines import Line2D

        prefixe = f"{SOURCE_TABLE} · "
        poignees = []
        for ligne in ax.get_lines():
            etiquette = str(ligne.get_label())
            if etiquette.startswith(prefixe):
                poignees.append(Line2D([], [], color=ligne.get_color(), marker="o", ms=3.5, lw=1.0,
                                       label=etiquette[len(prefixe):]))
        cp.make_legend(ax, handles=poignees, fontsize=6.5, title="trait : code — points : table",
                       title_fontsize=6.5, loc="center left", bbox_to_anchor=(1.02, 0.5),
                       ncol=2 if len(poignees) > 12 else 1)

    def __call__(self, fig: Any, ax: Any, context: Any) -> None:
        cp = _cfd_plot()
        self._zones(ax)
        for ligne in ax.get_lines():  # les nœuds de la table : des points pleins
            if str(ligne.get_label()).startswith(SOURCE_TABLE):
                ligne.set_markerfacecolor(ligne.get_color())
        if context.fold_layout == "overlay":
            valeurs = {**context.flight_point, **context.fixed_sweeps}
            superpose = ""
            restant = []
            for col, libelle, unite in self.conditions:
                if col == self.superpose:
                    superpose = libelle
                elif col in valeurs:
                    restant.append(f"{libelle} = {_texte_valeur(valeurs[col])}{_unite(unite)}")
            n = len(str(context.fold_label or "").split(" / "))
            ligne2 = f"{n} valeurs de {superpose} superposées" + (f" — {', '.join(restant)}" if restant else "")
            cp.set_suptitle(fig, f"{self.nom} vs. {self.abscisse}\n{ligne2}", fontsize=10)
            self._legende_superposee(cp, ax)
        else:
            if self.unidim:
                cp.set_title(ax, f"{self.nom} vs. {self.abscisse}")
            self._legende_simple(cp, ax)


def _dictionnaires(p: Polaire, libelles: Libelles) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """``configuration_dict``, ``y_axis_dict``, ``sweep_dict``, ``flight_point_dict`` de ``batch_plot``."""
    code, noeuds = p.code.copy(), p.noeuds.copy()
    conditions = list(p.conditions)
    if not conditions:
        code[_SEULE] = 0.0
        noeuds[_SEULE] = 0.0
        conditions = [_SEULE]
    configuration = {
        SOURCE_CODE: {"df": code, "label": SOURCE_CODE, "color": VERMILLON, "marker": "", "linewidth": 1.2},
        SOURCE_TABLE: {"df": noeuds, "label": SOURCE_TABLE, "color": BLEU, "marker": "o", "linestyle": "none",
                       "markersize": 3.5, "markeredgewidth": 0.0},
    }
    nom_y, unite_y = _libelle(libelles, p.nom)
    y = {p.nom: {"col_name": COLONNE_VALEUR, "literal_name": nom_y, "y_save_name": _fichier(p.nom),
                 **({"unit": unite_y} if unite_y else {})}}
    nom_x, unite_x = _libelle(libelles, p.axe)
    balayage = {p.axe: {"col_name": p.axe, "literal_name": nom_x, "label": nom_x, "x_save_name": _fichier(p.axe),
                        "polar_prefix": f"POLAIRE_{_fichier(p.axe).upper()}",
                        **({"unit": unite_x} if unite_x else {})}}
    points = {}
    for c in conditions:
        nom_c, unite_c = _libelle(libelles, c) if c != _SEULE else ("", None)
        points[c] = {"label": nom_c, "save_name": _fichier(c).upper(), **({"unit": unite_c} if unite_c else {})}
    return configuration, y, balayage, points


def tracer_polaires(
    polaires: Sequence[Polaire],
    dossier: str | Path,
    *,
    libelles: Libelles | None = None,
    superposer: bool = True,
    formats: Sequence[str] = FORMATS_TABLES,
    n_jobs: int = 1,
) -> list[Path]:
    """Les polaires sous ``dossier/<TABLE>/`` ; lève ``FiguresIndisponibles`` sans cfd-plot."""
    import matplotlib as mpl

    cp = _cfd_plot()
    libelles = dict(libelles or {})
    racine = Path(dossier)
    fichiers: list[Path] = []
    for p in polaires:
        configuration, y, balayage, points = _dictionnaires(p, libelles)
        nom_x, _ = _libelle(libelles, p.axe)
        habillage = HabillagePolaire(
            nom=_libelle(libelles, p.nom)[0], abscisse=nom_x, bornes=p.bornes, consignes=p.consignes,
            prolongements=p.prolongements, superpose=p.superpose, unidim=not p.conditions,
            conditions=tuple((c, *_libelle(libelles, c)) for c in p.conditions),
        )
        fold = None
        if superposer and p.superpose is not None:
            n = int(p.noeuds[p.superpose].nunique())
            fold = cp.FoldSpec(kind="context", layout="overlay", over=(p.superpose,), max_panels=max(2, n),
                               folder=DOSSIER_SUPERPOSITION)
        with mpl.rc_context():  # batch_plot applique son profil globalement : on le rend en sortant
            fichiers += cp.batch_plot(
                configuration_dict=configuration, y_axis_dict=y, sweep_dict=balayage, flight_point_dict=points,
                output_base=racine / _fichier(p.nom), style_profile="paper", formats=tuple(formats),
                on_before_save=habillage, report=False, verbose=False, n_jobs=n_jobs, fold=fold,
            )
    return [Path(f) for f in fichiers]
