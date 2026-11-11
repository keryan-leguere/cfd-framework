"""Figures du remplissage et de la reconstruction, tracées avec ``cfd-plot`` (profil « paper »).

Chaque figure est écrite en PNG (300 dpi) et en PDF vectoriel, prête pour un
rapport. Sur **chaque** panneau, le fond dit d'où viendra la valeur :

- **zone calculée** (bleu clair) : couverte par les sous-domaines, on y lance la CFD ;
- **déduite par symétrie** (gris hachuré) : obtenue des calculs par une
  symétrie de l'engin, au signe de quelques coefficients près ;
- **hors domaine** (blanc croisé) : une contrainte l'exclut (disque des braquages) ;

les plans de symétrie sont en tireté, et ceux qui sont des sous-domaines à
eux seuls (β = 0…) en trait bleu épais. Les figures :

- ``domaine`` : coupes exactes du domaine, chaque zone déduite nommée par sa symétrie ;
- ``plan_<nom>`` : un plan projeté sur chaque couple de facteurs, à un Mach ;
- ``comparaison_calculs`` : calculs par plan et par rôle ;
- ``comparaison_plans`` : tous les plans dans la même projection ;
- ``precision_cout`` et ``coupes_<coef>`` : la reconstruction des tables
  (engine/reconstruction.py) — erreur contre nombre de calculs, et coupes.

Une coupe est exacte (les autres variables fixées) ; une projection montre
l'ombre des sous-domaines sur le plan (les autres variables libres).

``cfd-plot`` est un paquet frère de ce dépôt, pas une dépendance : sans lui,
:func:`tracer_figures` lève :class:`FiguresIndisponibles` et le reste de la
commande (rapport, fichier DOE) n'est pas affecté. ::

    pip install -e ../cfd-plot
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import numpy as np

from cfd_doe.core.domaine_fondamental import Disque, Secteur
from cfd_doe.core.intervalle import TOLERANCE, Intervalle
from cfd_doe.data.format import formater_nombre
from cfd_doe.engine.reconstruction import Tables
from cfd_doe.engine.reduction import SousDomaine
from cfd_doe.engine.remplissage import (
    ROLE_CALCUL,
    ROLE_CONTROLE,
    ROLE_TEST,
    Contexte,
    PlanDOE,
    PointDOE,
    Resultat,
)

__all__ = [
    "FORMATS",
    "FiguresIndisponibles",
    "Precision",
    "coupe_par_defaut",
    "figure_comparaison_calculs",
    "figure_comparaison_plans",
    "figure_coupes",
    "figure_domaine",
    "figure_plan",
    "figure_precision",
    "tracer_figures",
]

PROFIL = "paper"
DPI = 300
FORMATS: tuple[str, ...] = ("png", "pdf")
#: Largeur utile d'une page de rapport (pouces).
PAGE = 7.0
#: Résolution des fonds de zone (cellules par côté).
RESOLUTION = 120

# Okabe-Ito : lisible en cas de daltonisme ; zones lisibles en niveaux de gris (hachures).
BLEU, ORANGE, VERT, VERMILLON, NOIR = "#0072B2", "#E69F00", "#009E73", "#D55E00", "#000000"
ZONE_CALCUL, ZONE_SYMETRIE, ZONE_HORS = "#D6E6F4", "#EDEDED", "#FFFFFF"
TRAIT_ZONE, TRAIT_PLAN = "#6E8FB0", "0.35"

_COULEUR_ROLE = {ROLE_CALCUL: BLEU, ROLE_CONTROLE: VERMILLON, ROLE_TEST: VERT}
_NOM_ROLE = {ROLE_CALCUL: "calcul", ROLE_CONTROLE: "contrôle", ROLE_TEST: "test"}
_MARQUEUR_ROLE = {ROLE_CALCUL: "o", ROLE_CONTROLE: "D", ROLE_TEST: "^"}
_FAMILLE = {"oui": "sur grille", "oui, par somme": "décomposition", "non": "métamodèle"}
_COULEUR_FAMILLE = {"oui": BLEU, "oui, par somme": ORANGE, "non": VERT}
_LETTRES = "abcdefghijklmnop"


class FiguresIndisponibles(RuntimeError):
    """``cfd-plot`` (ou Matplotlib) n'est pas installé."""


@lru_cache(maxsize=1)
def _cfd_plot() -> ModuleType:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import cfd_plot
    except ImportError as erreur:
        raise FiguresIndisponibles(
            f"figures indisponibles ({erreur.name} manquant) : pip install -e ../cfd-plot"
        ) from None
    return cast(ModuleType, cfd_plot)


@contextmanager
def _style() -> Iterator[ModuleType]:
    """Profil « paper » de cfd-plot, titres en maigre, tailles d'article."""
    import matplotlib as mpl

    cp = _cfd_plot()
    reglages: dict[str, Any] = {
        "axes.titleweight": "normal",
        "axes.titlesize": 9.5,
        "axes.labelsize": 9.5,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "figure.dpi": 100,
        "savefig.dpi": DPI,
        "hatch.linewidth": 0.5,
        "hatch.color": "0.6",
    }
    with cp.style_context(PROFIL), mpl.rc_context(reglages):  # type: ignore[arg-type]
        yield cp


def _n(x: int) -> str:
    return f"{x:,}".replace(",", chr(0x202F))


def _fichier(nom: str) -> str:
    return re.sub(r"[^0-9A-Za-z_-]+", "_", nom).strip("_") or "plan"


def _enregistrer(fig: Any, chemin: Path, formats: Sequence[str]) -> Path:
    """Écrit la figure dans chaque format ; renvoie le premier fichier."""
    import matplotlib.pyplot as plt

    fichiers = _cfd_plot().save_figure(fig, chemin, formats=tuple(formats), dpi=DPI)
    plt.close(fig)
    return Path(fichiers[0])


def _titre(ax: Any, titre: str, sous_titre: str = "") -> None:
    """Titre aligné à gauche, et un sous-titre gris en dessous."""
    import matplotlib as mpl
    from matplotlib.transforms import ScaledTranslation

    taille = float(mpl.rcParams["axes.titlesize"])
    pad = float(mpl.rcParams["axes.titlepad"])
    lignes = sous_titre.count("\n") + 1 if sous_titre else 0
    if getattr(ax, "name", "") == "polar":
        pad += 14.0  # au-dessus des graduations de φa
    _cfd_plot().set_title(ax, titre, loc="left", pad=pad + lignes * (taille + 0.5))
    if sous_titre:
        decalage = ScaledTranslation(0, pad / 72.0, ax.figure.dpi_scale_trans)
        ax.text(
            0.0,
            1.0,
            sous_titre,
            transform=ax.transAxes + decalage,
            ha="left",
            va="bottom",
            fontsize=taille - 1.5,
            linespacing=1.15,
            color="0.4",
            fontfamily=_cfd_plot().TITLE_FONT,
        )


def _virgule(ax: Any) -> None:
    """Graduations à virgule décimale, comme le texte."""
    from matplotlib.ticker import FuncFormatter

    def formater(x: float, _: Any) -> str:
        return f"{x:g}".replace(".", ",").replace("-", "−")

    for axe in (ax.xaxis, ax.yaxis):
        if axe.get_scale() == "linear":
            axe.set_major_formatter(FuncFormatter(formater))


def _axe(c: Contexte, nom: str) -> str:
    unite = " (°)" if nom in c.boite else ""
    return f"{c.symbole(nom)}{unite}"


def _plage(c: Contexte, nom: str) -> tuple[float, float]:
    """L'étendue affichée d'une colonne : le domaine complet, φa sur le tour entier."""
    if nom == "phia":
        return 0.0, 360.0
    if nom in c.boite:
        return c.boite[nom].bas, c.boite[nom].haut
    for p in c.parametres:
        if p.nom == nom:
            return p.plage.bas, p.plage.haut
    raise KeyError(nom)


def _cadrer(ax: Any, c: Contexte, x: str, y: str | None) -> None:
    """Le domaine complet, sans marge : le fond de zone touche le cadre."""
    for nom, fixer in ((x, ax.set_xlim), (y, ax.set_ylim)):
        if nom is None:
            continue
        bas, haut = _plage(c, nom)
        if haut > bas:
            fixer(bas, haut)
    ax.set_xlabel(_axe(c, x))
    if y is not None:
        ax.set_ylabel(_axe(c, y))
    _virgule(ax)
    for ligne in ax.get_lines():
        if ligne.get_marker() not in ("", "None", None):
            ligne.set_clip_on(False)


def _mach(c: Contexte) -> float | None:
    return c.machs[0] if c.machs else None


def _a_ce_mach(plan: PlanDOE, mach: float | None) -> list[PointDOE]:
    if mach is None:
        return list(plan.points)
    return [p for p in plan.points if p.valeurs["mach"] == mach]


def _titre_mach(mach: float | None) -> str:
    return "" if mach is None else f" à Mach {formater_nombre(mach)}"


# ---------------------------------------------------------------------------
# Appartenance vectorisée
# ---------------------------------------------------------------------------


def _dans_intervalle(i: Intervalle, x: np.ndarray) -> np.ndarray:
    bas = x >= i.bas - TOLERANCE if i.bas_inclus else x > i.bas + TOLERANCE
    haut = x <= i.haut + TOLERANCE if i.haut_inclus else x < i.haut - TOLERANCE
    return np.asarray(bas & haut)


def _satisfait(contrainte: Disque | Secteur, valeurs: Mapping[str, np.ndarray]) -> np.ndarray:
    x, y = valeurs[contrainte.x], valeurs[contrainte.y]
    if isinstance(contrainte, Disque):
        return np.asarray(np.hypot(x, y) <= contrainte.rayon + TOLERANCE)
    angle = np.mod(np.degrees(np.arctan2(y, x)), 360.0)
    angle = np.where(angle > 360.0 - 1e-7, 0.0, angle)
    intervalle = Intervalle(
        contrainte.angle_min, contrainte.angle_max, contrainte.min_inclus, contrainte.max_inclus
    )
    return np.asarray(_dans_intervalle(intervalle, angle) & (np.hypot(x, y) > TOLERANCE))


def _dans(sd: SousDomaine, valeurs: Mapping[str, np.ndarray]) -> np.ndarray:
    """Les points dans le sous-domaine ; une variable absente de ``valeurs`` est libre (ombre)."""
    n = len(next(iter(valeurs.values())))
    masque = np.ones(n, dtype=bool)
    for v, i in sd.bornes.items():
        if v in valeurs:
            masque &= _dans_intervalle(i, valeurs[v])
    for k in sd.contraintes:
        if k.x in valeurs and k.y in valeurs:
            masque &= _satisfait(k, valeurs)
    return masque


def _image(symetrie: Mapping[str, Any], valeurs: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    image = {v: (-x if v in symetrie["variables"] else x) for v, x in valeurs.items()}
    action = symetrie.get("phia")
    if action and "phia" in image:
        if "rotation" in action:
            image["phia"] = np.mod(valeurs["phia"] + action["rotation"], 360.0)
        else:
            image["phia"] = np.mod(2.0 * action["miroir"] - valeurs["phia"], 360.0)
    return image


def _calcule(c: Contexte, valeurs: Mapping[str, np.ndarray]) -> np.ndarray:
    masque = np.zeros(len(next(iter(valeurs.values()))), dtype=bool)
    for sd in c.sous_domaines:
        masque |= _dans(sd, valeurs)
    return masque


def _sur_axe(valeurs: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Polaire, αt = 0 : φa n'y est qu'une convention ; ramené à 0, braquages tournés (§2.5)."""
    valeurs = dict(valeurs)
    if not {"alphat", "phia", "DMB", "DNB"} <= set(valeurs):
        return valeurs
    axe = np.abs(valeurs["alphat"]) <= TOLERANCE
    if axe.any():
        phi = np.radians(valeurs["phia"])
        cos, sin = np.cos(phi), np.sin(phi)
        dmb, dnb = valeurs["DMB"], valeurs["DNB"]
        valeurs["DMB"] = np.where(axe, cos * dmb + sin * dnb, dmb)
        valeurs["DNB"] = np.where(axe, -sin * dmb + cos * dnb, dnb)
        valeurs["phia"] = np.where(axe, 0.0, valeurs["phia"])
    return valeurs


def _zones(c: Contexte, valeurs: Mapping[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Zone de chaque point (0 hors domaine, 1 calcul, 2 symétrie) et la symétrie qui l'y ramène.

    ``valeurs`` porte toutes les variables (coupe exacte) ou seulement certaines
    (projection : les autres sont libres).
    """
    # Même ordre que Contexte.replier : le point, ses images, puis la règle de l'axe αt = 0.
    zone = np.where(_calcule(c, valeurs), 1, 0)
    par = np.full(len(zone), -1)
    etapes: list[tuple[int, Mapping[str, Any] | None, bool]] = [
        (k, s, False) for k, s in enumerate(c.symetries)
    ]
    if "alphat" in valeurs:
        etapes += [(-1, None, True)] + [(k, s, True) for k, s in enumerate(c.symetries)]
    for k, s, axe in etapes:
        reste = zone == 0
        if not reste.any():
            break
        image = {v: x[reste] for v, x in valeurs.items()}
        if s is not None:
            image = _image(s, image)
        if axe:
            image = _sur_axe(image)
        indices = np.flatnonzero(reste)[_calcule(c, image)]
        zone[indices], par[indices] = 2, k
    return zone, par


def _valeurs(
    c: Contexte, axes: Mapping[str, np.ndarray], fixes: Mapping[str, float] | None
) -> dict[str, np.ndarray]:
    """Les variables du repère pour ces points : coupe (``fixes``) ou projection (``None``)."""
    n = len(next(iter(axes.values())))
    valeurs = {v: a for v, a in axes.items() if v in c.variables}
    if fixes is not None:
        for v in c.variables:
            valeurs.setdefault(v, np.full(n, fixes.get(v, c.reference[v])))
    return valeurs


# ---------------------------------------------------------------------------
# Fonds de zone
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Fond:
    """Un fond de zone sur une grille fine du plan (x, y)."""

    xs: np.ndarray  # centres
    ys: np.ndarray
    bx: np.ndarray  # bords
    by: np.ndarray
    zone: np.ndarray  # (ny, nx)
    par: np.ndarray  # (ny, nx)


def _fond(c: Contexte, x: str, y: str, fixes: Mapping[str, float] | None) -> _Fond:
    """Zones aux centres d'une grille de cellules couvrant exactement le plan affiché.

    Un nombre pair de cellules : sur une plage symétrique, aucun centre ne tombe
    sur un plan de symétrie (mesure nulle, tracé à part en trait).
    """
    (x0, x1), (y0, y1) = _plage(c, x), _plage(c, y)
    bx, by = np.linspace(x0, x1, RESOLUTION + 1), np.linspace(y0, y1, RESOLUTION + 1)
    xs, ys = (bx[1:] + bx[:-1]) / 2, (by[1:] + by[:-1]) / 2
    gx, gy = np.meshgrid(xs, ys)
    valeurs = _valeurs(c, {x: gx.ravel(), y: gy.ravel()}, fixes)
    if valeurs:
        zone, par = _zones(c, valeurs)
    else:  # deux paramètres : les symétries n'y touchent pas
        zone, par = np.ones(gx.size, int), np.full(gx.size, -1)
    return _Fond(xs, ys, bx, by, zone.reshape(gx.shape), par.reshape(gx.shape))


def _noter(ax: Any, *cles: str) -> None:
    """Retient, sur la figure, ce qui y est tracé (pour n'en légender que cela)."""
    fig = ax.figure
    if not hasattr(fig, "_cfd_doe_zones"):
        fig._cfd_doe_zones = set()
    fig._cfd_doe_zones.update(cles)


#: Sur-échantillonnage du fond pour y dessiner les hachures (cellules par cellule de zone).
_SUR = 4
#: Couleurs du fond : zone, puis la même zone sous son trait de hachure.
_TEINTES = (ZONE_HORS, "#B9B9B9", ZONE_CALCUL, ZONE_CALCUL, ZONE_SYMETRIE, "#A9A9A9")


def _hachures(zone: np.ndarray) -> np.ndarray:
    """Le fond sur-échantillonné, hachures comprises : indice dans :data:`_TEINTES`.

    Diagonales pour la zone déduite, croisillons pour le hors-domaine. Elles
    sont dessinées dans le raster lui-même : un ``contourf`` hachuré trace
    faux les zones trouées (carré privé d'un disque).
    """
    fine = np.repeat(np.repeat(zone, _SUR, axis=0), _SUR, axis=1)
    i, j = np.indices(fine.shape)
    # Une vingtaine de traits par panneau, quelle que soit sa taille.
    periode = max(4, fine.shape[1] // 22)
    diagonale = (i - j) % periode == 0
    croix = diagonale | ((i + j) % periode == 0)
    trait = np.where(fine == 2, diagonale, np.where(fine == 0, croix, False))
    return np.asarray(2 * np.where(fine == 0, 0, np.where(fine == 1, 1, 2)) + trait)


def _peindre(ax: Any, fond: _Fond, polaire: bool = False) -> None:
    """Fond coloré et hachuré, contour de la zone calculée."""
    from matplotlib.colors import ListedColormap

    if polaire:
        # En polaire, des hachures en indices deviendraient des spirales : teintes seules.
        bx, by = np.radians(fond.bx), fond.by
        image = 2 * fond.zone.astype(int)
    else:
        bx = np.linspace(fond.bx[0], fond.bx[-1], len(fond.xs) * _SUR + 1)
        by = np.linspace(fond.by[0], fond.by[-1], len(fond.ys) * _SUR + 1)
        image = _hachures(fond.zone)
    ax.pcolormesh(
        bx,
        by,
        image,
        cmap=ListedColormap(_TEINTES),
        vmin=-0.5,
        vmax=len(_TEINTES) - 0.5,
        shading="flat",
        rasterized=True,
        zorder=0,
    )
    for valeur, cle in ((2, "symetrie"), (0, "hors"), (1, "calcul")):
        if (fond.zone == valeur).any():
            _noter(ax, cle)
    if (fond.zone == 1).any() and not (fond.zone == 1).all():
        gx, gy = np.meshgrid(np.radians(fond.xs) if polaire else fond.xs, fond.ys)
        ax.contour(
            gx,
            gy,
            (fond.zone == 1).astype(float),
            levels=[0.5],
            colors=TRAIT_ZONE,
            linewidths=0.8,
            zorder=1,
        )


def _abreger(nom: str) -> str:
    """« rotation 90° » → « R90° », « miroir φs = 45° » → « M45° » (secteurs étroits)."""
    chiffres = re.findall(r"[-0-9.,]+°", nom)
    if not chiffres:
        return nom
    return ("R" if nom.startswith("rotation") else "M") + str(chiffres[-1])


def _nommer_symetries(
    ax: Any, c: Contexte, fond: _Fond, polaire: bool, noeuds: tuple[np.ndarray, np.ndarray]
) -> None:
    """Écrit, dans chaque zone déduite, la symétrie qui la ramène sur les calculs.

    L'étiquette va au cœur de la zone, en s'écartant des nœuds tracés.
    """
    gx, gy = np.meshgrid(fond.xs, fond.ys)
    ex, ey = (np.ptp(fond.xs) or 1.0), (np.ptp(fond.ys) or 1.0)
    for k in sorted(set(fond.par[fond.par >= 0].ravel().tolist())):
        masque = fond.par == k
        if masque.sum() < 0.03 * masque.size:
            continue
        cx, cy = gx[masque].mean(), gy[masque].mean()
        score = -np.hypot((gx - cx) / ex, (gy - cy) / ey)
        if len(noeuds[0]):
            dx = (gx[..., None] - noeuds[0]) / ex
            dy = (gy[..., None] - noeuds[1]) / ey
            # Le texte est large et bas : s'écarter surtout verticalement des nœuds.
            score = score + 2.0 * np.minimum(np.hypot(0.35 * dx, dy).min(-1), 0.08)
        # Et rester loin du bord de la zone.
        interieur = masque.copy()
        for decalage in ((0, 4), (0, -4), (4, 0), (-4, 0)):
            interieur &= np.roll(masque, decalage, axis=(0, 1))
        score[~(interieur if interieur.any() else masque)] = -np.inf
        j = np.unravel_index(int(np.argmax(score)), score.shape)
        px, py = gx[j], gy[j]
        ax.text(
            math.radians(px) if polaire else px,
            py,
            _abreger(c.symetries[k]["nom"]) if polaire else c.symetries[k]["nom"],
            ha="center",
            va="center",
            fontsize=7,
            style="italic",
            color="0.2",
            zorder=6,
            bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": "0.75", "lw": 0.4},
        )


def _plans_symetrie(ax: Any, c: Contexte, x: str, y: str | None) -> None:
    """Tiretés sur les plans de symétrie (variable retournée nulle)."""
    for nom, tracer in ((x, ax.axvline), (y, ax.axhline)):
        if nom is not None and nom in c.retournees:
            bas, haut = _plage(c, nom)
            if bas < 0 < haut:
                tracer(0.0, color=TRAIT_PLAN, linestyle=(0, (4, 3)), linewidth=0.7, zorder=1)
                _noter(ax, "plan")


def _strates_minces(
    ax: Any, c: Contexte, x: str, y: str, fixes: Mapping[str, float] | None
) -> None:
    """Un plan de symétrie qui est un sous-domaine à lui seul (β = 0…) : en trait épais.

    Seulement là où il borde une zone non calculée : noyé dans la zone
    calculée, il n'apprend rien.
    """
    for nom, autre in ((x, y), (y, x)):
        if nom not in c.retournees:
            continue
        t = np.linspace(*_plage(c, autre), 401)
        ecart = 1e-3 * (np.ptp(_plage(c, nom)) or 1.0)
        sur = [
            _valeurs(c, {nom: np.full_like(t, s), autre: t}, fixes) for s in (0.0, ecart, -ecart)
        ]
        if not sur[0]:
            continue
        plan, plus, moins = (_calcule(c, v) for v in sur)
        masque = plan & ~(plus & moins)
        if not masque.any():
            continue
        segments = np.where(masque, t, np.nan)
        zeros = np.zeros_like(t)
        xy = (zeros, segments) if nom == x else (segments, zeros)
        ax.plot(*xy, color=BLEU, linewidth=2.2, solid_capstyle="butt", zorder=2, alpha=0.85)
        _noter(ax, "mince")


def _legende_zones(fig: Any) -> list[Any]:
    """Les entrées de légende des zones, limitées à ce que la figure montre."""
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    presentes: set[str] = getattr(fig, "_cfd_doe_zones", set())
    entrees = {
        "calcul": Patch(
            facecolor=ZONE_CALCUL, edgecolor=TRAIT_ZONE, linewidth=0.8, label="zone calculée"
        ),
        "symetrie": Patch(
            facecolor=ZONE_SYMETRIE, edgecolor="0.6", hatch="////", label="déduite par symétrie"
        ),
        "hors": Patch(facecolor=ZONE_HORS, edgecolor="0.6", hatch="xx", label="hors domaine"),
        "mince": Line2D(
            [], [], color=BLEU, linewidth=2.2, alpha=0.85, label="plan de symétrie calculé"
        ),
        "plan": Line2D(
            [], [], color=TRAIT_PLAN, linestyle=(0, (4, 3)), linewidth=0.7, label="plan de symétrie"
        ),
    }
    return [e for cle, e in entrees.items() if cle in presentes]


def _poignees_marqueurs(fig: Any) -> list[Any]:
    """Les séries de points tracées sur la figure, une fois chacune."""
    poignees, vus = [], set()
    for ax in fig.axes:
        for ligne in ax.get_lines():
            nom = ligne.get_label()
            if (
                nom
                and not nom.startswith("_")
                and nom not in vus
                and ligne.get_marker() not in ("", "None", None)
            ):
                vus.add(nom)
                poignees.append(ligne)
    return poignees


# ---------------------------------------------------------------------------
# 1. Le domaine
# ---------------------------------------------------------------------------


def _niveaux_affiches(c: Contexte, v: str) -> tuple[float, ...]:
    if v == "phia":
        niveaux = c.niveaux[v]
        pas = float(min(np.diff(niveaux))) if len(niveaux) > 1 else 15.0
        return tuple(float(x) for x in np.arange(0.0, 360.0 - 1e-9, pas))
    if v in c.niveaux:
        return c.niveaux[v]
    return next(p.niveaux for p in c.parametres if p.nom == v)


def _coupe(
    ax: Any, c: Contexte, x: str, y: str, fixes: Mapping[str, float], titre: str, precision: str
) -> None:
    """Une coupe exacte : fond, symétries nommées, nœuds de la grille."""
    polaire = getattr(ax, "name", "") == "polar"
    fond = _fond(c, x, y, fixes)
    _peindre(ax, fond, polaire)
    if not polaire:
        _plans_symetrie(ax, c, x, y)
        _strates_minces(ax, c, x, y, fixes)
    nx = np.array([a for a in _niveaux_affiches(c, x) for _ in _niveaux_affiches(c, y)])
    ny = np.array([b for _ in _niveaux_affiches(c, x) for b in _niveaux_affiches(c, y)])
    zone, _ = _zones(c, _valeurs(c, {x: nx, y: ny}, fixes))
    _nommer_symetries(ax, c, fond, polaire, (nx, ny))
    cp = _cfd_plot()
    for code, face, bord, marqueur, nom in (
        (2, "white", "0.35", "o", "nœud déduit"),
        (1, BLEU, "white", "o", "nœud calculé"),
        (0, "none", "0.55", "x", "nœud hors domaine"),
    ):
        m = zone == code
        if m.any():
            ligne = cp.plot_line(
                ax,
                np.radians(nx[m]) if polaire else nx[m],
                ny[m],
                linestyle="none",
                marker=marqueur,
                markersize=4.2,
                markeredgewidth=0.7,
                color=bord,
                label=nom,
                zorder=4,
            )
            ligne.set_markerfacecolor(face)
    if polaire:
        ax.set_thetalim(0, 2 * math.pi)
        ax.set_rlim(0, _plage(c, y)[1])
        ax.set_xlabel(_axe(c, x))
        ax.set_rlabel_position(100)
        for ligne in ax.get_lines():
            ligne.set_clip_on(False)
    else:
        _cadrer(ax, c, x, y)
    calcules, total = int((zone == 1).sum()), int((zone > 0).sum())
    sous_titre = f"{precision}\n{calcules} nœuds calculés sur {total}"
    if polaire:
        sous_titre = f"{precision}, rayon {c.symbole(y)}\n{calcules} nœuds calculés sur {total} ; R rotation, M miroir"
    _titre(ax, titre, sous_titre)
    if not polaire:
        # Cadres carrés : titres alignés d'un panneau à l'autre ; à plages égales, un
        # disque de braquages reste un disque.
        ax.set_box_aspect(1)


def _panneaux_domaine(c: Contexte) -> list[tuple[str, str, dict[str, float], str, str]]:
    """Plan de l'écoulement, plan des braquages en un point générique, puis sur un plan.

    Chaque panneau : (x, y, valeurs fixées, titre court, précision).
    """
    libres = c.libres
    panneaux: list[tuple[str, str, dict[str, float], str, str]] = []

    def ou(fixes: Mapping[str, float]) -> str:
        return ", ".join(f"{c.symbole(k)} = {formater_nombre(x)}°" for k, x in fixes.items())

    if len(libres) >= 2:
        x, y = libres[0], libres[1]
        if c.reduction.repere == "polaire" and {x, y} == {"alphat", "phia"}:
            x, y = "phia", "alphat"
        reste = [v for v in libres if v not in (x, y)]
        precision = f"{', '.join(c.symbole(v) for v in reste)} nuls" if reste else "coupe complète"
        titre = "Écoulement" if y in ("beta", "alphat") else "Incidence et braquage"
        panneaux.append((x, y, {}, titre, precision))
    braquages = [v for v in ("DM", "DN", "DMB", "DNB", "DL") if v in libres]
    if len(libres) >= 3 and len(braquages) >= 2:
        u, v = braquages[0], braquages[1]
        ecoulement = [w for w in libres if w not in braquages][:2]
        generique = {}
        for w in ecoulement:
            haut = max(_niveaux_affiches(c, w))
            generique[w] = 22.5 if w == "phia" else haut / 2
        panneaux.append((u, v, generique, "Braquages", ou(generique)))
        sur_plan = dict(generique)
        for w in ecoulement:
            if w in c.retournees or w == "phia":
                sur_plan[w] = 0.0
                break
        if sur_plan != generique:
            panneaux.append((u, v, sur_plan, "Braquages, sur un plan", ou(sur_plan)))
    return panneaux


def figure_domaine(resultat: Resultat, dossier: Path, formats: Sequence[str] = FORMATS) -> Path:
    """Coupes exactes du domaine, zones nommées par leur symétrie."""
    c = resultat.contexte
    panneaux = _panneaux_domaine(c)
    if not panneaux:
        return _domaine_1d(resultat, dossier, formats)
    import matplotlib.pyplot as plt

    with _style() as cp:
        n = len(panneaux)
        largeur = PAGE if n > 2 else 2.6 * n + 0.8
        fig = plt.figure(figsize=(largeur, 3.9), layout="constrained")
        for i, (x, y, fixes, titre, precision) in enumerate(panneaux):
            ax = fig.add_subplot(1, n, i + 1, projection="polar" if x == "phia" else None)
            _coupe(ax, c, x, y, fixes, f"({_LETTRES[i]}) {titre}" if n > 1 else titre, precision)
        poignees = [*_legende_zones(fig), *_poignees_marqueurs(fig)]
        fig.legend(handles=poignees, loc="outside lower center", ncol=4, frameon=False)
        etude = c.reduction.etude
        repere = "repère cartésien" if c.reduction.repere == "cartesien" else "repère polaire"
        n_sd = len(c.sous_domaines)
        cp.set_suptitle(
            fig,
            f"{etude.nom} : {n_sd} sous-domaine{'s' if n_sd > 1 else ''}, groupe "
            f"{c.reduction.groupe}, {repere}",
            fontsize=10,
        )
        return _enregistrer(fig, dossier / "domaine", formats)


def _zones_1d(ax: Any, c: Contexte, x: str, fixes: Mapping[str, float] | None) -> None:
    """Fond d'une coupe 1D en ``x`` : zone calculée, zone déduite."""
    if x not in c.boite:
        return
    t = np.linspace(*_plage(c, x), 801)
    zone, _ = _zones(c, _valeurs(c, {x: t}, fixes if fixes is not None else {}))
    for code, couleur, hachure, cle in (
        (1, ZONE_CALCUL, None, "calcul"),
        (2, ZONE_SYMETRIE, "////", "symetrie"),
    ):
        masque = zone == code
        bords = np.flatnonzero(np.diff(np.concatenate([[0], masque.astype(int), [0]])))
        for debut, fin in zip(bords[::2], bords[1::2]):
            ax.axvspan(
                t[debut],
                t[fin - 1],
                facecolor=couleur,
                hatch=hachure,
                edgecolor="0.6" if hachure else "none",
                linewidth=0,
                zorder=0,
            )
            _noter(ax, cle)
    _plans_symetrie(ax, c, x, None)


def _domaine_1d(resultat: Resultat, dossier: Path, formats: Sequence[str]) -> Path:
    """Une seule variable libre : un axe."""
    c = resultat.contexte
    x = c.libres[0]
    with _style() as cp:
        fig, ax = cp.new_figure(figsize=(3.6, 1.9))
        _zones_1d(ax, c, x, {})
        niveaux = np.array(_niveaux_affiches(c, x))
        zone, _ = _zones(c, _valeurs(c, {x: niveaux}, {}))
        for code, face, nom in ((1, BLEU, "nœud calculé"), (2, "white", "nœud déduit")):
            if (zone == code).any():
                ligne = cp.plot_line(
                    ax,
                    niveaux[zone == code],
                    np.zeros((zone == code).sum()),
                    linestyle="none",
                    marker="o",
                    markersize=4.5,
                    color=BLEU if code == 1 else "0.35",
                    label=nom,
                )
                ligne.set_markerfacecolor(face)
        ax.set_yticks([])
        _cadrer(ax, c, x, None)
        _titre(
            ax, c.reduction.etude.nom, f"{int((zone == 1).sum())} nœuds calculés sur {zone.size}"
        )
        fig.legend(
            handles=[*_legende_zones(fig), *_poignees_marqueurs(fig)],
            loc="outside lower center",
            ncol=3,
            frameon=False,
        )
        return _enregistrer(fig, dossier / "domaine", formats)


# ---------------------------------------------------------------------------
# 2. Un plan, projeté sur chaque couple de facteurs
# ---------------------------------------------------------------------------


def _dimensions(c: Contexte, points: Sequence[PointDOE]) -> list[str]:
    """Les colonnes qui varient dans ces points (hors Mach)."""
    candidats = [*c.libres, *(p.nom for p in c.parametres)]
    return [d for d in candidats if len({round(p.valeurs[d], 9) for p in points}) > 1]


def _tracer_roles(
    ax: Any, points: Sequence[PointDOE], x: str, y: str | None, taille: float
) -> None:
    """Les points par rôle ; ``y = None`` : sur l'axe des abscisses."""
    cp = _cfd_plot()
    for role in (ROLE_CALCUL, ROLE_TEST, ROLE_CONTROLE):
        for fidelite in sorted({p.fidelite for p in points if p.role == role}):
            choisis = [p for p in points if p.role == role and p.fidelite == fidelite]
            couleur = ORANGE if fidelite == "HF" and role == ROLE_CALCUL else _COULEUR_ROLE[role]
            creux = role == ROLE_CONTROLE or fidelite == "BF"
            supplement = 1.6 if role == ROLE_CONTROLE else 0.6 if role == ROLE_TEST else 0.0
            ligne = cp.plot_line(
                ax,
                [p.valeurs[x] for p in choisis],
                [p.valeurs[y] if y else 0.0 for p in choisis],
                linestyle="none",
                marker=_MARQUEUR_ROLE[role],
                color=couleur,
                markersize=taille + supplement + (0.6 if fidelite == "HF" else 0.0),
                markeredgewidth=0.9 if creux else 0.35,
                label=_NOM_ROLE[role] + (f" {fidelite}" if fidelite else ""),
                zorder=4 if role == ROLE_CALCUL else 5,
            )
            ligne.set_markerfacecolor("white" if creux else couleur)
            if not creux:
                ligne.set_markeredgecolor("white")


def _projection(ax: Any, c: Contexte, x: str, y: str, fond: _Fond | None = None) -> None:
    """Fond de projection : l'ombre des sous-domaines sur le plan (x, y)."""
    _peindre(ax, fond or _fond(c, x, y, None))
    _plans_symetrie(ax, c, x, y)
    _strates_minces(ax, c, x, y, None)


def _resume_plan(plan: PlanDOE, c: Contexte, points: Sequence[PointDOE], mach: float | None) -> str:
    lignes = [f"{_n(len(points))} calculs{_titre_mach(mach)}"]
    if mach is not None:
        lignes.append(f"{_n(plan.compter())} sur les {len(c.machs)} Mach")
    roles = [
        f"{_n(plan.compter(r))} {_NOM_ROLE[r]}"
        for r in (ROLE_CONTROLE, ROLE_TEST)
        if plan.compter(r)
    ]
    if roles:
        lignes.append("dont " + ", ".join(roles))
    lignes.append(f"table : {_FAMILLE[plan.table_directe]}")
    return "\n".join(lignes)


def figure_plan(
    plan: PlanDOE, c: Contexte, dossier: Path, formats: Sequence[str] = FORMATS
) -> Path | None:
    """Matrice des projections d'un plan à un Mach, sur fond de zones."""
    mach = _mach(c)
    points = _a_ce_mach(plan, mach)
    dims = _dimensions(c, points)
    if not dims:
        return None
    if len(dims) == 1:
        return _plan_1d(plan, c, dims[0], points, mach, dossier, formats)
    k = len(dims) - 1
    taille = 2.6 if len(points) > 150 else 3.2
    with _style() as cp:
        cote = min(2.3, PAGE / k) if k > 1 else 3.4
        fig, axes = cp.new_figure(
            k,
            k,
            figsize=(cote * k + 0.4, cote * k + (1.0 if k == 1 else 0.35)),
            squeeze=False,
            sharex="col",
            sharey="row",
        )
        for i in range(k):
            for j in range(k):
                ax = axes[i][j]
                if j > i:
                    ax.axis("off")
                    continue
                x, y = dims[j], dims[i + 1]
                _projection(ax, c, x, y)
                _tracer_roles(ax, points, x, y, taille)
                _cadrer(ax, c, x, y)
                ax.tick_params(labelbottom=i == k - 1, labelleft=j == 0)
                ax.set_box_aspect(1)
                if i < k - 1:
                    ax.set_xlabel("")
                if j > 0:
                    ax.set_ylabel("")
        poignees = [*_legende_zones(fig), *_poignees_marqueurs(fig)]
        resume = _resume_plan(plan, c, points, mach)
        if k >= 3:
            axes[0][k - 1].legend(
                handles=poignees, loc="upper right", frameon=False, markerscale=1.5
            )
            axes[1][k - 1].text(
                1.0,
                1.0,
                resume,
                transform=axes[1][k - 1].transAxes,
                ha="right",
                va="top",
                fontsize=8,
                linespacing=1.4,
            )
        elif k == 2:
            coin = axes[0][1]
            coin.legend(handles=poignees, loc="upper left", frameon=False, fontsize=7)
            coin.text(
                0.0, -0.05, resume, transform=coin.transAxes, ha="left", va="top", fontsize=7.5
            )
        else:
            fig.legend(handles=poignees, loc="outside lower center", ncol=3, frameon=False)
            _titre(axes[0][0], "", resume.replace("\n", " ; "))
        cp.set_suptitle(fig, f"{plan.nom} : {plan.titre}", fontsize=10)
        return _enregistrer(fig, dossier / f"plan_{_fichier(plan.nom)}", formats)


def _plan_1d(
    plan: PlanDOE,
    c: Contexte,
    x: str,
    points: Sequence[PointDOE],
    mach: float | None,
    dossier: Path,
    formats: Sequence[str],
) -> Path:
    with _style() as cp:
        fig, ax = cp.new_figure(figsize=(3.8, 2.1))
        _zones_1d(ax, c, x, None)
        _tracer_roles(ax, points, x, None, 4.0)
        ax.set_yticks([])
        _cadrer(ax, c, x, None)
        _titre(
            ax,
            f"{plan.nom} : {plan.titre}",
            _resume_plan(plan, c, points, mach).replace("\n", " ; "),
        )
        fig.legend(
            handles=[*_legende_zones(fig), *_poignees_marqueurs(fig)],
            loc="outside lower center",
            ncol=3,
            frameon=False,
        )
        return _enregistrer(fig, dossier / f"plan_{_fichier(plan.nom)}", formats)


# ---------------------------------------------------------------------------
# 3. Comparaisons
# ---------------------------------------------------------------------------


def figure_comparaison_calculs(
    resultat: Resultat, dossier: Path, formats: Sequence[str] = FORMATS
) -> Path:
    """Calculs par plan, empilés par rôle, en barres horizontales (échelle log au besoin)."""
    from matplotlib.patches import Patch

    c = resultat.contexte
    plans = list(resultat.plans)
    retenu = c.remplissage.retenu
    totaux = np.array([max(p.compter(), 1) for p in plans], dtype=float)
    log = totaux.max() > 30 * totaux.min()
    series: list[tuple[str, Callable[[PlanDOE], int], str, str | None]] = [
        ("calcul", lambda p: p.compter(ROLE_CALCUL) - p.compter(ROLE_CALCUL, "HF"), BLEU, None),
        ("calcul HF", lambda p: p.compter(ROLE_CALCUL, "HF"), ORANGE, None),
        ("contrôle", lambda p: p.compter(ROLE_CONTROLE), VERMILLON, "////"),
        ("test", lambda p: p.compter(ROLE_TEST), VERT, "...."),
    ]
    with _style() as cp:
        fig, ax = cp.new_figure(figsize=(PAGE * 0.82, 0.3 * len(plans) + 1.35))
        y = np.arange(len(plans))[::-1]
        # En log, une barre ne peut partir de 0 : elle part d'un plancher sous l'axe.
        plancher = 0.5 if log else 0.0
        gauche = np.full(len(plans), float(plancher))
        for nom, compte, couleur, hachure in series:
            valeurs = np.array([compte(p) for p in plans], dtype=float)
            if not valeurs.any():
                continue
            ax.barh(
                y,
                valeurs,
                left=gauche,
                height=0.62,
                color=couleur,
                hatch=hachure,
                edgecolor="white",
                linewidth=0.4,
                label=nom,
            )
            gauche = gauche + valeurs
        for yi, plan, fin in zip(y, plans, gauche):
            ax.annotate(
                _n(plan.compter()),
                (fin, yi),
                xytext=(3, 0),
                textcoords="offset points",
                va="center",
                ha="left",
                fontsize=7.5,
            )
        ax.set_yticks(y)
        ax.set_yticklabels([p.nom + (" (retenu)" if p.nom == retenu else "") for p in plans])
        for etiquette, plan in zip(ax.get_yticklabels(), plans):
            etiquette.set_color(_COULEUR_FAMILLE[plan.table_directe])
        if log:
            ax.set_xscale("log")
            ax.set_xlim(max(1.0, totaux.min()) / 1.6, totaux.max() * 3.0)
        else:
            ax.set_xlim(0, totaux.max() * 1.16)
            _virgule(ax)
        ax.set_ylim(-0.6, len(plans) - 0.4)
        ax.tick_params(axis="y", which="both", left=False, right=False)
        conditions = f"{len(c.machs)} Mach" if c.machs else "une condition"
        ax.set_xlabel(f"calculs CFD, {conditions}")
        ax.grid(True, axis="x", which="major", linewidth=0.4, alpha=0.5)
        roles = ax.legend(loc="lower right", frameon=True, title="rôle", title_fontsize=7.5)
        ax.add_artist(roles)
        familles = list(dict.fromkeys(p.table_directe for p in plans))
        texte = ax.legend(
            handles=[
                Patch(facecolor="none", edgecolor="none", label=_FAMILLE[f]) for f in familles
            ],
            loc="center right",
            frameon=False,
            handlelength=0,
            handletextpad=0,
            title="table obtenue",
            title_fontsize=7.5,
        )
        for t, f in zip(texte.get_texts(), familles):
            t.set_color(_COULEUR_FAMILLE[f])
        _titre(
            ax, "Nombre de calculs par plan", "empilés par rôle ; nom coloré selon la table obtenue"
        )
        return _enregistrer(fig, dossier / "comparaison_calculs", formats)


def figure_comparaison_plans(
    resultat: Resultat, dossier: Path, formats: Sequence[str] = FORMATS
) -> Path | None:
    """Tous les plans dans la même projection, à un Mach, sur fond de zones."""
    c = resultat.contexte
    if len(c.libres) < 2:
        return None
    x = c.libres[0]
    y = c.libres[2] if len(c.libres) >= 3 else c.libres[1]
    mach = _mach(c)
    plans = resultat.plans
    colonnes = min(4, len(plans))
    lignes = math.ceil(len(plans) / colonnes)
    with _style() as cp:
        cote = PAGE / colonnes
        fig, axes = cp.new_figure(
            lignes,
            colonnes,
            figsize=(PAGE, cote * lignes + 0.75),
            squeeze=False,
            sharex=True,
            sharey=True,
        )
        fond = _fond(c, x, y, None)
        for i, (ax, plan) in enumerate(zip(axes.flat, plans)):
            points = _a_ce_mach(plan, mach)
            _projection(ax, c, x, y, fond)
            _tracer_roles(ax, points, x, y, 3.0)
            _cadrer(ax, c, x, y)
            _titre(ax, f"({_LETTRES[i % 16]}) {plan.nom}", f"{_n(len(points))} calculs")
        for ax in list(axes.flat)[len(plans) :]:
            ax.axis("off")
        for i, ligne in enumerate(axes):
            for j, ax in enumerate(ligne):
                if j > 0:
                    ax.set_ylabel("")
                if i * colonnes + j + colonnes < len(plans):
                    ax.set_xlabel("")
                else:
                    ax.tick_params(labelbottom=True)
        poignees = [*_legende_zones(fig), *_poignees_marqueurs(fig)]
        fig.legend(
            handles=poignees, loc="outside lower center", ncol=4, frameon=False, markerscale=1.6
        )
        cp.set_suptitle(
            fig,
            f"Plans projetés sur ({c.symbole(x)}, {c.symbole(y)}){_titre_mach(mach)}",
            fontsize=10,
        )
        return _enregistrer(fig, dossier / "comparaison_plans", formats)


# ---------------------------------------------------------------------------
# 4. Reconstruction : précision et coupes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Precision:
    """Ce qu'a coûté un plan, et ce qu'il donne."""

    plan: PlanDOE
    calculs: int
    #: Erreur RMS de la table, en % de l'étendue du coefficient (le pire coefficient).
    erreur: float
    #: Erreur maximale, même échelle (facultative).
    erreur_max: float | None = None


def figure_precision(
    entrees: Sequence[Precision],
    dossier: Path,
    *,
    titre: str = "",
    formats: Sequence[str] = FORMATS,
) -> Path:
    """Erreur de la table reconstruite contre nombre de calculs, un point par plan."""
    from matplotlib.lines import Line2D

    with _style() as cp:
        fig, ax = cp.new_figure(figsize=(PAGE * 0.72, 3.7))
        plancher = 1e-3
        etiquettes: list[Any] = []
        for e in entrees:
            couleur = _COULEUR_FAMILLE[e.plan.table_directe]
            erreur = max(e.erreur, plancher)
            if e.erreur_max is not None and e.erreur_max > erreur:
                ax.plot(
                    [e.calculs, e.calculs],
                    [erreur, e.erreur_max],
                    color=couleur,
                    linewidth=0.8,
                    alpha=0.55,
                    zorder=2,
                )
                ax.plot([e.calculs], [e.erreur_max], "_", color=couleur, ms=6, alpha=0.7)
            ax.plot(
                [e.calculs], [erreur], "o", color=couleur, mec="white", mew=0.5, ms=6.5, zorder=3
            )
            etiquettes.append(
                ax.annotate(
                    e.plan.nom + (" (exacte)" if e.erreur < plancher else ""),
                    (e.calculs, erreur),
                    xytext=(5, -2),
                    textcoords="offset points",
                    fontsize=7.5,
                    color="0.15",
                )
            )
        ax.set_xscale("log")
        ax.set_yscale("log")
        calculs = [e.calculs for e in entrees]
        ax.set_xlim(min(calculs) / 1.6, max(calculs) * 2.6)
        _desempiler(fig, etiquettes)
        ax.set_xlabel("calculs CFD, tous rôles")
        ax.set_ylabel("erreur de la table (% de l'étendue)")
        ax.grid(True, which="major", linewidth=0.4, alpha=0.5)
        familles = list(dict.fromkeys(e.plan.table_directe for e in entrees))
        poignees: list[Any] = [
            Line2D(
                [], [], marker="o", linestyle="none", color=_COULEUR_FAMILLE[f], label=_FAMILLE[f]
            )
            for f in familles
        ]
        poignees.append(
            Line2D([], [], color="0.5", linewidth=0.8, label="trait : jusqu'à l'erreur maximale")
        )
        ax.legend(handles=poignees, loc="best")
        _titre(
            ax,
            titre or "Précision contre coût",
            "erreur RMS du pire coefficient sur toute la grille ; plancher à 0,001 %",
        )
        return _enregistrer(fig, dossier / "precision_cout", formats)


def _desempiler(fig: Any, etiquettes: Sequence[Any]) -> None:
    """Place chaque étiquette autour de son point sans recouvrir ni étiquette ni marqueur.

    Positions essayées : à droite, à gauche, dessus, dessous, puis plus loin
    à droite ; l'emprise est mesurée au rendu.
    """
    from matplotlib.transforms import Bbox

    rendu = fig.canvas.get_renderer()
    marqueurs = []
    for etiquette in etiquettes:
        x, y = etiquette.axes.transData.transform(etiquette.xy)
        r = 5.0 * fig.dpi / 72.0
        marqueurs.append(Bbox([[x - r, y - r], [x + r, y + r]]))
    placees: list[Any] = []
    positions = [
        ((6, -3), "left"),
        ((-6, -3), "right"),
        ((0, 7), "center"),
        ((0, -13), "center"),
        *(((6, -3 - 10 * k), "left") for k in range(1, 6)),
        *(((-6, -3 - 10 * k), "right") for k in range(1, 6)),
    ]
    for etiquette in etiquettes:
        cadre = etiquette.axes.get_window_extent(rendu)
        for (dx, dy), alignement in positions:
            etiquette.set_position((dx, dy))
            etiquette.set_horizontalalignment(alignement)
            boite = etiquette.get_window_extent(rendu)
            dedans = cadre.x0 <= boite.x0 and boite.x1 <= cadre.x1 and cadre.y0 <= boite.y0
            if dedans and not any(boite.overlaps(autre) for autre in (*placees, *marqueurs)):
                break
        placees.append(etiquette.get_window_extent(rendu))


def coupe_par_defaut(c: Contexte, tables: Tables) -> tuple[str, dict[str, float]]:
    """L'abscisse et les valeurs fixées d'une coupe parlante.

    En abscisse la première variable libre ; les autres à mi-chemin de leur
    plus grand niveau (un point où les effets se croisent — à la référence,
    une décomposition est exacte par construction) ; paramètres au dernier
    niveau ; premier Mach.
    """
    x = c.libres[0]
    fixes: dict[str, float] = {}
    for nom, axe in tables.grille.axes.items():
        if nom == x:
            continue
        if nom == "mach":
            fixes[nom] = axe[0]
        elif nom in c.boite:
            cible = max(abs(a) for a in axe) / 2
            fixes[nom] = min(axe, key=lambda a: (abs(a - cible), -a))
        else:
            fixes[nom] = axe[-1]
    return x, fixes


def _coupe_grille(
    tables: Tables, x: str, fixes: Mapping[str, float]
) -> tuple[np.ndarray, np.ndarray]:
    """Indices des nœuds de la coupe (x varie, le reste fixé), triés selon x."""
    points = tables.grille.points()
    colonnes = list(tables.grille.colonnes)
    masque = np.ones(len(points), dtype=bool)
    for nom, valeur in fixes.items():
        masque &= np.isclose(points[:, colonnes.index(nom)], valeur)
    indices = np.flatnonzero(masque)
    ordre = np.argsort(points[indices, colonnes.index(x)])
    return indices[ordre], points[indices[ordre], colonnes.index(x)]


def figure_coupes(
    c: Contexte,
    tables: Sequence[Tables],
    coefficient: str,
    dossier: Path,
    *,
    reference: np.ndarray | None = None,
    coupe: tuple[str, Mapping[str, float]] | None = None,
    formats: Sequence[str] = FORMATS,
) -> Path:
    """Une coupe d'un coefficient, un panneau par plan, sur fond de zones.

    ``reference`` : la valeur vraie (ou une table de référence) aux nœuds de
    la grille, tracée en noir sous chaque reconstruction ; une bande d'écart
    (table − référence) s'ajoute alors sous chaque panneau, avec la plage
    ±1 % de l'étendue du coefficient sur la coupe.
    """
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    if not tables:
        raise ValueError("figure_coupes : aucune table")
    x, fixes = coupe or coupe_par_defaut(c, tables[0])
    colonnes = min(4, len(tables))
    lignes = math.ceil(len(tables) / colonnes)
    variables = {k: v for k, v in fixes.items() if k in c.variables}
    residus = reference is not None
    hauteurs = [3, 1.25] * lignes if residus else [1] * lignes
    with _style() as cp:
        fig = plt.figure(
            figsize=(PAGE, (PAGE / colonnes) * (1.05 if residus else 0.8) * lignes + 0.9),
            layout="constrained",
        )
        grille = fig.add_gridspec(len(hauteurs), colonnes, height_ratios=hauteurs)
        principal: Any = None
        ecart_partage: Any = None
        bande = None
        if residus:
            assert reference is not None
            indices0, _ = _coupe_grille(tables[0], x, fixes)
            bande = 0.01 * _etendue_finie(reference[indices0])
        for i, t in enumerate(tables):
            ligne, colonne = divmod(i, colonnes)
            rang = 2 * ligne if residus else ligne
            ax = fig.add_subplot(grille[rang, colonne], sharex=principal, sharey=principal)
            principal = principal or ax
            indices, xs = _coupe_grille(t, x, fixes)
            couleur = _COULEUR_FAMILLE[t.plan.table_directe]
            _zones_1d(ax, c, x, variables)
            if reference is not None:
                ax.plot(xs, reference[indices], color=NOIR, linewidth=1.0, zorder=3)
            ax.plot(
                xs,
                t.valeurs[coefficient][indices],
                color=couleur,
                linewidth=1.6,
                linestyle=(0, (5, 2)),
                zorder=4,
            )
            _titre(ax, f"({_LETTRES[i % 16]}) {t.plan.nom}")
            if len(xs):
                ax.set_xlim(xs.min(), xs.max())
            _virgule(ax)
            ax.set_ylabel(coefficient if colonne == 0 else "")
            ax.tick_params(labelleft=colonne == 0)
            if not residus:
                ax.set_xlabel(_axe(c, x) if i + colonnes >= len(tables) else "")
                ax.tick_params(labelbottom=i + colonnes >= len(tables))
                continue
            ax.tick_params(labelbottom=False)
            assert reference is not None and bande is not None
            bas = fig.add_subplot(grille[rang + 1, colonne], sharex=ax, sharey=ecart_partage)
            ecart_partage = ecart_partage or bas
            _zones_1d(bas, c, x, variables)
            bas.axhspan(-bande, bande, color="0.82", zorder=1, linewidth=0)
            bas.axhline(0.0, color=NOIR, linewidth=0.6, zorder=2)
            bas.plot(
                xs,
                t.valeurs[coefficient][indices] - reference[indices],
                color=couleur,
                linewidth=1.2,
                zorder=3,
            )
            bas.set_ylabel("écart" if colonne == 0 else "")
            bas.tick_params(labelleft=colonne == 0)
            bas.set_xlabel(_axe(c, x) if i + colonnes >= len(tables) else "")
            bas.tick_params(labelbottom=i + colonnes >= len(tables))
            _virgule(bas)
        if ecart_partage is not None:
            # Écarts : échelle commune, au moins la bande de ±1 %.
            plus_grand = max(
                [
                    float(np.nanmax(np.abs(ligne.get_ydata())))
                    for ax in fig.axes
                    for ligne in ax.get_lines()
                    if ax.get_shared_y_axes().joined(ax, ecart_partage)
                    and np.size(ligne.get_ydata()) > 2
                ]
                + [2.0 * (bande or 0.0)]
            )
            ecart_partage.set_ylim(-1.3 * plus_grand, 1.3 * plus_grand)
        poignees: list[Any] = []
        if reference is not None:
            poignees.append(Line2D([], [], color=NOIR, linewidth=1.0, label="référence"))
        familles = list(dict.fromkeys(t.plan.table_directe for t in tables))
        poignees += [
            Line2D(
                [],
                [],
                color=_COULEUR_FAMILLE[f],
                linewidth=1.6,
                linestyle=(0, (5, 2)),
                label=f"table reconstruite ({_FAMILLE[f]})",
            )
            for f in familles
        ]
        if residus:
            poignees.append(Patch(facecolor="0.82", label="écart ±1 % de l'étendue"))
        poignees += _legende_zones(fig)
        fig.legend(handles=poignees, loc="outside lower center", ncol=3, frameon=False)
        ou = ", ".join(
            ("Mach" if k == "mach" else c.symbole(k)) + f" = {formater_nombre(v)}"
            for k, v in fixes.items()
        )
        cp.set_suptitle(fig, f"{coefficient} selon {c.symbole(x)} ; {ou}", fontsize=10)
        return _enregistrer(fig, dossier / f"coupes_{_fichier(coefficient)}", formats)


def _etendue_finie(x: np.ndarray) -> float:
    finis = x[np.isfinite(x)]
    if not len(finis):
        return 1.0
    e = float(finis.max() - finis.min())
    return e if e > 1e-12 else max(1.0, float(np.abs(finis).max()))


# ---------------------------------------------------------------------------
# Tout
# ---------------------------------------------------------------------------


def tracer_figures(
    resultat: Resultat, dossier: Path, formats: Sequence[str] = FORMATS
) -> list[Path]:
    """Écrit les figures du remplissage dans ``dossier`` ; renvoie un fichier par figure."""
    _cfd_plot()
    dossier.mkdir(parents=True, exist_ok=True)
    fichiers: list[Path | None] = [figure_domaine(resultat, dossier, formats)]
    fichiers += [figure_plan(plan, resultat.contexte, dossier, formats) for plan in resultat.plans]
    if len(resultat.plans) > 1:
        fichiers += [
            figure_comparaison_calculs(resultat, dossier, formats),
            figure_comparaison_plans(resultat, dossier, formats),
        ]
    return [f for f in fichiers if f is not None]
