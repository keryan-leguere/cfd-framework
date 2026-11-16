"""Figures qualitatives du domaine réduit (``cfd-doe domaine --figures``), prêtes pour un article.

Deux figures, chacune sur deux rangées superposées, **cartésien en haut,
polaire en bas**, pour les comparer au même endroit :

- ``domaine_reperes`` : le plan des angles (α, β). En haut, le rectangle
  demandé et la part que le cartésien calcule ; en bas, le même rectangle, le
  disque d'αt qui le couvre et le secteur fondamental (45° en cruciforme).
  Hachuré bleu : calculé ; gris : déduit par symétrie. Chaque morceau du
  domaine réduit porte une lettre, et la légende à droite dit pour chacune les
  braquages calculés : **tous** à l'intérieur, **une partie** seulement sur un
  plan de symétrie ou sur l'axe — c'est là que le miroir agit encore, sur les
  braquages, une fois qu'il ne peut plus rien sur les angles.
- ``domaine_braquages`` : pour chacune de ces lettres, le plan des braquages
  (δm, δn) — (δmB, δnB) en polaire —, la part calculée et la part déduite.
  Écrite seulement s'il y a au moins un braquage latéral libre.

Tout est lu des sous-domaines de :func:`~cfd_doe.engine.reduction.reduire` ;
rien n'est dessiné qu'ils ne contiennent. Les deux repères sont réduits ici,
quel que soit celui que l'étude retient : la figure sert précisément à les
comparer. Si le polaire est impossible (aucun angle libre…), la rangée du bas
est absente et la figure le dit.
"""

from __future__ import annotations

import math
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from cfd_doe.core.domaine_fondamental import Disque, Secteur
from cfd_doe.core.intervalle import TOLERANCE, Intervalle
from cfd_doe.data.etude import ErreurEtude, Etude
from cfd_doe.data.format import formater_intervalle, formater_nombre
from cfd_doe.data.variables import SYMBOLES
from cfd_doe.engine.reduction import (
    Reduction,
    SousDomaine,
    reduire,
    symetries_exportees,
    vol_plan,
)
from cfd_doe.report import figures
from cfd_doe.report.figures import (
    BLEU,
    PAGE,
    TRAIT_PLAN,
    ZONE_CALCUL,
    ZONE_SYMETRIE,
    _enregistrer,
    _style,
    _titre,
    _virgule,
)

__all__ = ["FORMATS_DOMAINE", "Comparaison", "comparer_reperes", "tracer_figures_domaine"]

#: SVG par défaut : vectoriel, éditable, et il s'insère tel quel dans un article ou une page.
FORMATS_DOMAINE: tuple[str, ...] = ("svg",)

_LETTRES = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
#: Bleu des hachures du calculé : celui du trait, un peu plus clair.
_HACHURE = "#3D8BC7"
_ECHANTILLONS = 181


# ---------------------------------------------------------------------------
# Les deux réductions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Comparaison:
    """La même étude réduite dans les deux repères ; ``polaire`` vaut ``None`` s'il est refusé."""

    etude: Etude
    cartesien: Reduction
    polaire: Reduction | None
    #: Pourquoi le polaire manque.
    sans_polaire: str = ""
    #: Le repère que l'étude retient (``repere: auto`` résolu).
    retenu: str = "cartesien"


def comparer_reperes(etude: Etude) -> Comparaison:
    """Réduit l'étude en cartésien et en polaire."""
    retenu = reduire(etude).repere
    cartesien = reduire(etude.avec(repere="cartesien"))
    try:
        polaire: Reduction | None = reduire(etude.avec(repere="polaire"))
        raison = ""
    except ErreurEtude as erreur:
        polaire, raison = None, str(erreur)
    return Comparaison(etude, cartesien, polaire, raison, retenu)


# ---------------------------------------------------------------------------
# Morceaux du domaine dans le plan des angles
# ---------------------------------------------------------------------------


def _angles(r: Reduction) -> tuple[str, str]:
    return ("alpha", "beta") if r.repere == "cartesien" else ("alphat", "phia")


def _braquages(r: Reduction) -> tuple[str, ...]:
    return ("DM", "DN", "DL") if r.repere == "cartesien" else ("DMB", "DNB", "DL")


def _enveloppe(r: Reduction, v: str) -> Intervalle:
    """L'étendue d'une variable sur tous les sous-domaines (bornes fermées)."""
    bas = min(sd.bornes[v].bas for sd in r.sous_domaines)
    haut = max(sd.bornes[v].haut for sd in r.sous_domaines)
    return Intervalle(bas, haut)


@dataclass
class _Morceau:
    """Un morceau du plan des angles : un même couple d'intervalles d'angles."""

    lettre: str
    angles: tuple[Intervalle, Intervalle]
    sous_domaines: list[SousDomaine] = field(default_factory=list)

    @property
    def dimension(self) -> int:
        return sum(not i.est_point for i in self.angles)


def _morceaux(r: Reduction) -> list[_Morceau]:
    """Les sous-domaines regroupés par leurs angles, dans l'ordre des numéros."""
    a, b = _angles(r)
    morceaux: list[_Morceau] = []
    for sd in r.sous_domaines:
        cle = (sd.bornes[a], sd.bornes[b])
        if r.repere == "polaire" and sd.bornes["alphat"].est_nul:
            cle = (sd.bornes["alphat"], Intervalle.point(0.0))
        for m in morceaux:
            if m.angles == cle:
                m.sous_domaines.append(sd)
                break
        else:
            morceaux.append(_Morceau(_LETTRES[len(morceaux) % 26], cle, [sd]))
    return morceaux


def _condition(v: str, i: Intervalle, plein: Intervalle) -> str:
    """« δnB > 0 », « δl ≥ 0 », « φa = 45° », sinon la borne écrite en entier."""
    s = SYMBOLES.get(v, v)
    if i.est_point:
        return f"{s} = {formater_nombre(i.bas)}" + ("°" if v == "phia" else "")
    # « > 0 » ne dit que la moitié gardée par un changement de signe : plage pleine symétrique.
    moitie = plein.bas < -TOLERANCE and abs(plein.bas + plein.haut) <= TOLERANCE
    if moitie and abs(i.bas) <= TOLERANCE and abs(i.haut - plein.haut) <= TOLERANCE:
        return f"{s} {'≥' if i.bas_inclus else '>'} 0"
    # « ∈ » manque à la police des figures (TeX Gyre Termes) : « dans ».
    return f"{s} dans {formater_intervalle(i)}°"


def _nature(r: Reduction, m: _Morceau) -> str:
    """« intérieur », « plan φa = 0° », « axe αt = 0 »…, suivi des conditions sur les angles."""
    a, b = _angles(r)
    pleins = [_enveloppe(r, a), _enveloppe(r, b)]
    libres = sum(not p.est_point for p in pleins)
    if r.repere == "polaire" and m.angles[0].est_nul:
        return "axe αt = 0"
    conditions = [
        _condition(v, i, p) for v, i, p in zip((a, b), m.angles, pleins) if not p.est_point
    ]
    if m.dimension == libres:
        quoi = "intérieur"
    elif m.dimension == 0:
        quoi = "origine"
    else:
        quoi = "plan"
    return f"{quoi} " + ", ".join(conditions) if conditions else quoi


def _disque(r: Reduction) -> Disque | None:
    for sd in r.sous_domaines:
        for c in sd.contraintes:
            if isinstance(c, Disque):
                return c
    return None


def _restrictions(r: Reduction, sd: SousDomaine) -> list[str]:
    """Ce qui distingue les braquages de ce sous-domaine des braquages complets."""
    textes = []
    for v in _braquages(r):
        plein, i = _enveloppe(r, v), sd.bornes[v]
        if plein.est_point:
            continue
        if not (
            abs(i.bas - plein.bas) <= TOLERANCE
            and abs(i.haut - plein.haut) <= TOLERANCE
            and i.bas_inclus
            and i.haut_inclus
        ):
            textes.append(_condition(v, i, plein))
    for c in sd.contraintes:
        if isinstance(c, Secteur):
            couple = f"({SYMBOLES.get(c.x, c.x)}, {SYMBOLES.get(c.y, c.y)})"
            if abs(c.angle_max - c.angle_min) <= TOLERANCE:
                textes.append(f"{couple} sur la demi-droite à {formater_nombre(c.angle_min)}°")
            else:
                secteur = Intervalle(c.angle_min, c.angle_max, c.min_inclus, c.max_inclus)
                textes.append(f"{couple} dans le secteur {formater_intervalle(secteur)}°")
    return textes


def _braquages_complets(r: Reduction) -> str:
    """« δm, δn ∈ [−20 ; 20]° (disque ≤ 20°), δl ∈ [−10 ; 10]° »."""
    groupes: dict[str, list[str]] = {}
    for v in _braquages(r):
        plein = _enveloppe(r, v)
        if not plein.est_point:
            groupes.setdefault(formater_intervalle(plein), []).append(SYMBOLES[v])
    morceaux = [f"{', '.join(vs)} dans {i}°" for i, vs in groupes.items()]
    disque = _disque(r)
    if disque is not None and morceaux:
        morceaux[0] += f" (disque ≤ {formater_nombre(disque.rayon)}°)"
    return ", ".join(morceaux)


def _tous(r: Reduction, m: _Morceau) -> bool:
    """Le morceau calcule-t-il tous les braquages ?"""
    return len(m.sous_domaines) == 1 and not _restrictions(r, m.sous_domaines[0])


def _a_des_braquages(r: Reduction) -> bool:
    return any(not _enveloppe(r, v).est_point for v in _braquages(r))


# ---------------------------------------------------------------------------
# Géométrie dans le plan (α, β)
# ---------------------------------------------------------------------------


def _vers_ab(alphat: np.ndarray, phia: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(αt, φa) → (α, β), vectorisé (même formule que core.angles.vers_alpha_beta)."""
    at, ph = np.radians(alphat), np.radians(phia)
    alpha = np.degrees(np.arctan2(np.sin(at) * np.cos(ph), np.cos(at)))
    beta = np.degrees(np.arcsin(np.clip(np.sin(at) * np.sin(ph), -1.0, 1.0)))
    return alpha, beta


def _contour_polaire(r_: Intervalle, p: Intervalle) -> tuple[np.ndarray, np.ndarray]:
    """Le bord d'un secteur de couronne, en (αt, φa)."""
    phi = np.linspace(p.bas, p.haut, _ECHANTILLONS)
    rayon = np.full_like(phi, r_.haut)
    if r_.bas <= TOLERANCE:
        at = np.concatenate([[0.0], rayon, [0.0]])
        ph = np.concatenate([[p.bas], phi, [p.haut]])
    else:
        at = np.concatenate([rayon, np.full_like(phi, r_.bas)])
        ph = np.concatenate([phi, phi[::-1]])
    return at, ph


def _forme(r: Reduction, angles: tuple[Intervalle, Intervalle]) -> tuple[int, np.ndarray]:
    """(dimension, points (n, 2) en coordonnées (α, β) — ou (αt, φa) en polaire).

    Les points restent dans le repère de la réduction : c'est là qu'on leur
    applique les symétries, avant de passer en (α, β).
    """
    a, b = angles
    if r.repere == "cartesien":
        if not a.est_point and not b.est_point:
            xs = [a.bas, a.haut, a.haut, a.bas]
            ys = [b.bas, b.bas, b.haut, b.haut]
            return 2, np.column_stack([xs, ys])
        if a.est_point and b.est_point:
            return 0, np.array([[a.bas, b.bas]])
        t = np.linspace(0.0, 1.0, 2)
        return 1, np.column_stack([a.bas + t * a.largeur, b.bas + t * b.largeur])
    if a.est_nul:
        return 0, np.array([[0.0, 0.0]])
    if b.est_point:
        rayons = np.linspace(a.bas, a.haut, _ECHANTILLONS)
        return 1, np.column_stack([rayons, np.full_like(rayons, b.bas)])
    at, ph = _contour_polaire(a, b)
    return 2, np.column_stack([at, ph])


def _en_ab(r: Reduction, points: np.ndarray) -> np.ndarray:
    if r.repere == "cartesien":
        return points
    alpha, beta = _vers_ab(points[:, 0], points[:, 1])
    return np.column_stack([alpha, beta])


def _images(r: Reduction, points: np.ndarray) -> list[np.ndarray]:
    """Les images d'une forme par chaque symétrie du groupe complet."""
    images = []
    if r.repere == "polaire" and r.etude.geometrie.revolution:
        # Toute rotation : on balaie le tour par pas fins.
        for theta in np.arange(5.0, 360.0, 5.0):
            images.append(np.column_stack([points[:, 0], points[:, 1] + theta]))
        return images
    for s in symetries_exportees(r):
        image = points.copy()
        if r.repere == "cartesien":
            for k, v in enumerate(("alpha", "beta")):
                if v in s["variables"]:
                    image[:, k] = -image[:, k]
        else:
            action = s.get("phia") or {}
            if "rotation" in action:
                image[:, 1] = image[:, 1] + action["rotation"]
            elif "miroir" in action:
                image[:, 1] = 2.0 * action["miroir"] - image[:, 1]
        images.append(image)
    return images


def _centroide(xy: np.ndarray) -> tuple[float, float]:
    """Centre d'aire d'un polygone (la moyenne des sommets penche vers l'arc échantillonné)."""
    x, y = xy[:, 0], xy[:, 1]
    xs, ys = np.roll(x, -1), np.roll(y, -1)
    croix = x * ys - xs * y
    aire = croix.sum() / 2.0
    if abs(aire) <= 1e-12:
        return float(x.mean()), float(y.mean())
    return float(((x + xs) * croix).sum() / (6 * aire)), float(
        ((y + ys) * croix).sum() / (6 * aire)
    )


def _rayon(c: Comparaison) -> float:
    """αt maximal : ce qu'il faut voir, rectangle et disque compris."""
    d = c.cartesien.domaine_entree
    return math.hypot(d["alpha"].amplitude, d["beta"].amplitude)


def _patch(ax: Any, xy: np.ndarray, **kw: Any) -> Any:
    """Un polygone ; la couleur de hachure passe par ``hatchcolor`` quand Matplotlib l'a (≥ 3.10)."""
    from matplotlib.patches import Polygon

    couleur = kw.pop("hatchcolor", None)
    try:
        patch = Polygon(xy, closed=True, hatchcolor=couleur, **kw) if couleur else None
    except (AttributeError, TypeError):
        patch = None
    if patch is None:
        if couleur:
            kw["edgecolor"] = couleur
        patch = Polygon(xy, closed=True, **kw)
    ax.add_patch(patch)
    return patch


# ---------------------------------------------------------------------------
# Figure 1 : le plan des angles
# ---------------------------------------------------------------------------


def _etiquette(ax: Any, x: float, y: float, lettre: str, dx: float = 0.0, dy: float = 0.0) -> None:
    ax.annotate(
        lettre,
        (x, y),
        xytext=(dx, dy),
        textcoords="offset points",
        ha="center",
        va="center",
        fontsize=7.5,
        color=BLEU,
        zorder=8,
        bbox={"boxstyle": "circle,pad=0.18", "fc": "white", "ec": BLEU, "lw": 0.6},
        arrowprops=(
            {"arrowstyle": "-", "color": BLEU, "lw": 0.5, "shrinkA": 0, "shrinkB": 0}
            if dx or dy
            else None
        ),
    )


def _plans_symetrie(ax: Any, r: Reduction, rayon: float) -> None:
    """Les plans de symétrie qui coupent le plan des angles, en tireté."""
    style = {"color": TRAIT_PLAN, "linestyle": (0, (4, 3)), "linewidth": 0.6, "zorder": 2}
    if r.repere == "cartesien":
        retournes = {v for s in symetries_exportees(r) for v in s["variables"]}
        if "alpha" in retournes:
            ax.plot([0, 0], [-rayon, rayon], **style)
        if "beta" in retournes:
            ax.plot([-rayon, rayon], [0, 0], **style)
        return
    for phis in r.etude.geometrie.plans_phia:
        t = np.linspace(-rayon, rayon, _ECHANTILLONS)
        x, y = _vers_ab(np.abs(t), np.where(t >= 0, phis, phis + 180.0))
        ax.plot(x, y, **style)


def _panneau_angles(ax: Any, c: Comparaison, r: Reduction, morceaux: list[_Morceau]) -> list[str]:
    """Dessine un repère ; renvoie les remarques à mettre sous la légende."""
    rayon = _rayon(c)
    d = c.cartesien.domaine_entree
    remarques: list[str] = []

    # Disque d'αt (polaire) et secteur fondamental, en fond.
    geo = r.etude.geometrie
    if r.repere == "polaire":
        cercle = np.linspace(0.0, 360.0, 361)
        x, y = _vers_ab(np.full_like(cercle, rayon), cercle)
        ax.plot(x, y, color="0.55", linewidth=0.6, zorder=2)
        if geo.secteur_phia is not None:
            at, ph = _contour_polaire(Intervalle(0.0, rayon), Intervalle(0.0, geo.secteur_phia))
            xy = np.column_stack(_vers_ab(at, ph))
            _patch(
                ax,
                xy,
                facecolor="none",
                edgecolor=BLEU,
                linewidth=0.8,
                linestyle=(0, (2, 2)),
                zorder=6,
            )
            fin = _vers_ab(np.array([rayon * 1.04]), np.array([geo.secteur_phia / 2]))
            ax.text(
                float(fin[0][0]),
                float(fin[1][0]),
                f"secteur fondamental\nφa dans [0 ; {formater_nombre(geo.secteur_phia)}]°",
                fontsize=6.5,
                color=BLEU,
                ha="left",
                va="bottom",
                zorder=8,
            )

    # Déduit : images des morceaux calculés. En vol plan, seules comptent celles
    # qui restent dans le plan de vol : les autres sont hors du domaine.
    plan = vol_plan(c.cartesien.domaine_entree)
    for m in morceaux:
        dim, pts = _forme(r, m.angles)
        for image in _images(r, pts):
            xy = _en_ab(r, image)
            if plan is not None and np.abs(xy[:, 1 if plan == "tangage" else 0]).max() > 1e-6:
                continue
            if dim == 2:
                _patch(ax, xy, facecolor=ZONE_SYMETRIE, edgecolor="none", zorder=1)
            elif dim == 1:
                ax.plot(
                    xy[:, 0],
                    xy[:, 1],
                    color="0.7",
                    linewidth=2.4,
                    zorder=1.5,
                    solid_capstyle="butt",
                )

    _plans_symetrie(ax, r, rayon)

    # Calculé. Les étiquettes des plans s'écartent de l'intérieur, pour ne pas y heurter la sienne.
    hors_rectangle = False
    interieurs = [_en_ab(r, p) for dim, p in (_forme(r, m.angles) for m in morceaux) if dim == 2]
    centre = np.mean([_centroide(xy) for xy in interieurs], axis=0) if interieurs else None
    for m in morceaux:
        dim, pts = _forme(r, m.angles)
        xy = _en_ab(r, pts)
        dehors = (np.abs(xy[:, 1]) > d["beta"].amplitude + 1e-6) | (
            np.abs(xy[:, 0]) > d["alpha"].amplitude + 1e-6
        )
        hors_rectangle |= bool(dehors.any())
        if dim == 2:
            _patch(
                ax,
                xy,
                facecolor=ZONE_CALCUL,
                edgecolor=BLEU,
                linewidth=0.9,
                hatch="////",
                hatchcolor=_HACHURE,
                zorder=3,
            )
            cx, cy = _centroide(xy)
            _etiquette(ax, cx, cy, m.lettre)
        elif dim == 1:
            ax.plot(xy[:, 0], xy[:, 1], color=BLEU, linewidth=2.6, zorder=4, solid_capstyle="butt")
            tx, ty = xy[-1] - xy[0]
            norme = math.hypot(tx, ty) or 1.0
            px, py = xy[0] + 0.62 * (xy[-1] - xy[0])
            nx, ny = -ty / norme, tx / norme
            if centre is not None and nx * (centre[0] - px) + ny * (centre[1] - py) > 0:
                nx, ny = -nx, -ny
            _etiquette(ax, float(px), float(py), m.lettre, dx=11 * nx, dy=11 * ny)
        else:
            ax.plot(
                *xy[0],
                marker="o",
                markersize=4.5,
                color=BLEU,
                zorder=5,
                markeredgecolor="white",
                markeredgewidth=0.6,
            )
            _etiquette(ax, float(xy[0, 0]), float(xy[0, 1]), m.lettre, dx=-10, dy=-10)

    # Le rectangle demandé, par-dessus tout.
    a, b = d["alpha"], d["beta"]
    if b.est_point:
        ax.plot(
            [a.bas, a.haut],
            [b.bas, b.bas],
            color="black",
            linewidth=0.8,
            zorder=7,
            marker="|",
            markersize=6,
        )
    else:
        ax.add_patch(_rectangle(a, b))
    if hors_rectangle:
        remarques.append(
            "le secteur déborde du rectangle : ces points sont calculés aussi, "
            "le polaire couvre un disque d'αt (§5.4)"
        )
    if r.repere == "polaire" and vol_plan(r.domaine_entree) is not None:
        remarques.append(
            "vol plan : seule la direction du plan de vol est atteinte — le secteur "
            "n'est parcouru que sur son bord"
        )

    marge = 1.12 * rayon
    ax.set_xlim(-marge, marge)
    ax.set_ylim(-marge, marge)
    ax.set_aspect("equal")
    ax.set_xlabel("α (°)")
    ax.set_ylabel("β (°)")
    _virgule(ax)
    return remarques


def _rectangle(a: Intervalle, b: Intervalle) -> Any:
    from matplotlib.patches import Rectangle

    return Rectangle(
        (a.bas, b.bas),
        a.largeur,
        b.largeur,
        facecolor="none",
        edgecolor="black",
        linewidth=0.9,
        zorder=7,
    )


def _legende_morceaux(
    ax: Any, r: Reduction, morceaux: list[_Morceau], remarques: list[str]
) -> None:
    """La légende à droite : chaque lettre, sa nature, ses braquages."""
    ax.set_axis_off()
    lignes: list[tuple[str, str, str]] = []  # (lettre, texte, style)
    largeur = 58
    for m in morceaux:
        numeros = ", ".join(f"#{sd.numero}" for sd in m.sous_domaines)
        lignes.append((m.lettre, f"{_nature(r, m)}  ({numeros})", "titre"))
        if not _a_des_braquages(r):
            continue
        if _tous(r, m):
            texte = "tous les braquages : " + _braquages_complets(r)
            for morceau in textwrap.wrap(texte, largeur):
                lignes.append(("", morceau, "tous"))
        else:
            lignes.append(("", "une partie des braquages seulement :", "partie"))
            for sd in m.sous_domaines:
                restr = _restrictions(r, sd) or ["braquages entiers"]
                texte = f"#{sd.numero} : " + ", ".join(restr)
                for k, morceau in enumerate(textwrap.wrap(texte, largeur - 2)):
                    lignes.append(("", ("  " if k else "") + morceau, "detail"))
    if remarques:
        lignes.append(("", "", "vide"))
        for remarque in remarques:
            for k, morceau in enumerate(textwrap.wrap(remarque, largeur)):
                lignes.append(("", ("" if k == 0 else "  ") + morceau, "remarque"))

    pas = min(0.075, 0.98 / max(len(lignes), 1))
    y = 0.99
    couleurs = {
        "titre": "black",
        "tous": BLEU,
        "partie": "#B5651D",
        "detail": "0.25",
        "remarque": "0.4",
        "vide": "black",
    }
    for lettre, texte, style in lignes:
        if lettre:
            ax.text(
                0.0,
                y,
                lettre,
                transform=ax.transAxes,
                fontsize=7.5,
                color=BLEU,
                ha="center",
                va="top",
                bbox={"boxstyle": "circle,pad=0.18", "fc": "white", "ec": BLEU, "lw": 0.6},
            )
        ax.text(
            0.06,
            y,
            texte,
            transform=ax.transAxes,
            fontsize=7.2,
            ha="left",
            va="top",
            color=couleurs[style],
            style="italic" if style == "remarque" else "normal",
        )
        y -= pas


def _titre_repere(c: Comparaison, r: Reduction) -> tuple[str, str]:
    n = len(r.sous_domaines)
    nom = "Repère cartésien (α, β)" if r.repere == "cartesien" else "Repère polaire (αt, φa)"
    retenu = " — retenu" if r.repere == c.retenu else ""
    ordre = "∞" if r.ordre_groupe is None else str(r.ordre_groupe)
    sous = f"{n} sous-domaine{'s' if n > 1 else ''}, groupe {r.groupe} (ordre {ordre})"
    return nom + retenu, sous


def _figure_reperes(c: Comparaison, dossier: Path, formats: Sequence[str]) -> Path:
    import matplotlib.pyplot as plt

    reductions = [r for r in (c.cartesien, c.polaire) if r is not None]
    with _style() as cp:
        fig = plt.figure(figsize=(PAGE, 3.15 * len(reductions) + 0.5), layout="constrained")
        grille = fig.add_gridspec(len(reductions), 2, width_ratios=(1.0, 1.15))
        for i, r in enumerate(reductions):
            morceaux = _morceaux(r)
            ax = fig.add_subplot(grille[i, 0])
            remarques = _panneau_angles(ax, c, r, morceaux)
            titre, sous = _titre_repere(c, r)
            _titre(ax, f"({'ab'[i]}) {titre}", sous)
            _legende_morceaux(fig.add_subplot(grille[i, 1]), r, morceaux, remarques)
        _legende_zones(fig, c)
        cp.set_suptitle(fig, f"{c.etude.nom} : domaine réduit, cartésien et polaire", fontsize=10)
        return _enregistrer(fig, dossier / "domaine_reperes", formats)


def _legende_zones(fig: Any, c: Comparaison) -> None:
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    entrees = [
        Patch(facecolor=ZONE_CALCUL, edgecolor=BLEU, hatch="////", label="calculé (intérieur)"),
        Line2D([], [], color=BLEU, linewidth=2.6, label="calculé sur un plan / l'axe"),
        Patch(facecolor=ZONE_SYMETRIE, edgecolor="none", label="déduit par symétrie"),
        Line2D([], [], color="black", linewidth=0.9, label="domaine demandé"),
        Line2D(
            [], [], color=TRAIT_PLAN, linestyle=(0, (4, 3)), linewidth=0.6, label="plan de symétrie"
        ),
    ]
    if c.polaire is None:
        entrees.append(
            Patch(facecolor="none", edgecolor="none", label=f"pas de polaire : {c.sans_polaire}")
        )
    fig.legend(handles=entrees, loc="outside lower center", ncol=3, frameon=False, fontsize=7.5)


# ---------------------------------------------------------------------------
# Figure 2 : le plan des braquages, morceau par morceau
# ---------------------------------------------------------------------------


def _demi_plans(contrainte: Secteur) -> list[tuple[float, float, float]]:
    """Un secteur (≤ 180°) comme intersection de deux demi-plans ``a·x + b·y ≥ 0``."""
    t0, t1 = math.radians(contrainte.angle_min), math.radians(contrainte.angle_max)
    return [(-math.sin(t0), math.cos(t0), 0.0), (math.sin(t1), -math.cos(t1), 0.0)]


def _couper(poly: np.ndarray, a: float, b: float, c0: float) -> np.ndarray:
    """Sutherland–Hodgman : la partie du polygone où ``a·x + b·y + c0 ≥ 0``."""
    if len(poly) == 0:
        return poly
    sortie = []
    for k in range(len(poly)):
        p, q = poly[k], poly[(k + 1) % len(poly)]
        fp, fq = a * p[0] + b * p[1] + c0, a * q[0] + b * q[1] + c0
        if fp >= -1e-12:
            sortie.append(p)
        if (fp >= -1e-12) != (fq >= -1e-12):
            t = fp / (fp - fq)
            sortie.append(p + t * (q - p))
    return np.array(sortie)


def _region(sd: SousDomaine, u: str, v: str) -> np.ndarray:
    """La projection convexe d'un sous-domaine sur (u, v) : pavé ∩ disque ∩ secteur."""
    iu, iv = sd.bornes[u], sd.bornes[v]
    poly = np.array([[iu.bas, iv.bas], [iu.haut, iv.bas], [iu.haut, iv.haut], [iu.bas, iv.haut]])
    for c in sd.contraintes:
        if {c.x, c.y} != {u, v}:
            continue
        if isinstance(c, Disque):
            for t in np.linspace(0.0, 2 * math.pi, 129)[:-1]:
                a, b = math.cos(t), math.sin(t)
                poly = _couper(poly, -a, -b, c.rayon)
        elif abs(c.angle_max - c.angle_min) <= 180.0:
            for a, b, c0 in _demi_plans(c):
                poly = _couper(poly, a, b, c0)
    return poly


def _plein(r: Reduction, u: str, v: str) -> np.ndarray:
    """Le domaine complet des braquages : enveloppe ∩ disque."""
    iu, iv = _enveloppe(r, u), _enveloppe(r, v)
    disque = _disque(r)
    sd = SousDomaine(0, "plein", {u: iu, v: iv}, () if disque is None else (disque,), ())
    return _region(sd, u, v)


def _panneau_braquages(
    ax: Any, r: Reduction, m: _Morceau, u: str, v: str | None, autres: Sequence[str]
) -> None:
    """Le plan (u, v) des braquages pour un morceau ; ``v`` absent : un axe."""
    pu = _enveloppe(r, u)
    if v is None:
        ax.axhspan(-0.3, 0.3, xmin=0, xmax=1, facecolor="none")
        ax.plot(
            [pu.bas, pu.haut], [0, 0], color="0.7", linewidth=5, solid_capstyle="butt", zorder=1
        )
        for k, sd in enumerate(m.sous_domaines):
            i = sd.bornes[u]
            y = 0.0
            if i.est_point:
                ax.plot(i.bas, y, marker="o", color=BLEU, markersize=5, zorder=4)
            else:
                ax.plot(
                    [i.bas, i.haut],
                    [y, y],
                    color=BLEU,
                    linewidth=5,
                    solid_capstyle="butt",
                    zorder=3,
                )
            ax.annotate(
                f"#{sd.numero}",
                ((i.bas + i.haut) / 2, y),
                xytext=(0, 7 + 9 * k),
                textcoords="offset points",
                ha="center",
                fontsize=6.5,
                color=BLEU,
            )
        ax.set_ylim(-1, 1)
        ax.set_yticks([])
        ax.set_xlim(pu.bas - 0.08 * pu.largeur, pu.haut + 0.08 * pu.largeur)
        ax.set_xlabel(f"{SYMBOLES[u]} (°)")
        for cote in ("left", "right", "top"):
            ax.spines[cote].set_visible(False)
        _virgule(ax)
        return

    pv = _enveloppe(r, v)
    _patch(ax, _plein(r, u, v), facecolor=ZONE_SYMETRIE, edgecolor="0.55", linewidth=0.6, zorder=1)
    for sd in m.sous_domaines:
        iu, iv = sd.bornes[u], sd.bornes[v]
        region = _region(sd, u, v)
        if len(region) == 0:
            continue
        if not iu.est_point and not iv.est_point and not _demi_droite(sd):
            _patch(
                ax,
                region,
                facecolor=ZONE_CALCUL,
                edgecolor=BLEU,
                linewidth=0.8,
                hatch="////",
                hatchcolor=_HACHURE,
                zorder=3,
            )
            cx, cy = _centroide(region)
        else:
            # Strate mince : un segment (ou un point) du plan des braquages.
            xs, ys = region[:, 0], region[:, 1]
            if _demi_droite(sd):
                c = next(k for k in sd.contraintes if isinstance(k, Secteur))
                rmax = max(pu.haut, pv.haut)
                disque = _disque(r)
                if disque is not None:
                    rmax = disque.rayon
                t = math.radians(c.angle_min)
                xs, ys = np.array([0.0, rmax * math.cos(t)]), np.array([0.0, rmax * math.sin(t)])
            if np.ptp(xs) + np.ptp(ys) <= TOLERANCE:
                ax.plot(xs[0], ys[0], marker="o", color=BLEU, markersize=4.5, zorder=5)
            else:
                ordre = np.lexsort((ys, xs))
                ax.plot(
                    xs[ordre][[0, -1]],
                    ys[ordre][[0, -1]],
                    color=BLEU,
                    linewidth=2.6,
                    solid_capstyle="butt",
                    zorder=4,
                )
            cx, cy = float(np.mean(xs)), float(np.mean(ys))
        ax.annotate(
            f"#{sd.numero}",
            (cx, cy),
            ha="center",
            va="center",
            fontsize=6.5,
            color=BLEU,
            zorder=8,
            bbox={"boxstyle": "round,pad=0.12", "fc": "white", "ec": "none", "alpha": 0.85},
        )
    marge = 0.1 * max(pu.largeur, pv.largeur)
    ax.set_xlim(pu.bas - marge, pu.haut + marge)
    ax.set_ylim(pv.bas - marge, pv.haut + marge)
    ax.set_aspect("equal")
    ax.set_xlabel(f"{SYMBOLES[u]} (°)", labelpad=1)
    ax.set_ylabel(f"{SYMBOLES[v]} (°)", labelpad=1)
    _virgule(ax)


def _demi_droite(sd: SousDomaine) -> bool:
    return any(
        isinstance(c, Secteur) and abs(c.angle_max - c.angle_min) <= TOLERANCE
        for c in sd.contraintes
    )


def _texte_autres(r: Reduction, m: _Morceau, autres: Sequence[str]) -> str:
    """Ce que le panneau ne montre pas (δl…), sous-domaine par sous-domaine."""
    lignes = []
    for w in autres:
        plein = _enveloppe(r, w)
        valeurs = []
        for sd in m.sous_domaines:
            i = sd.bornes[w]
            entier = abs(i.bas - plein.bas) <= TOLERANCE and abs(i.haut - plein.haut) <= TOLERANCE
            quoi = "entier" if entier else _condition(w, i, plein).split(" ", 1)[1]
            valeurs.append(f"#{sd.numero} {quoi}")
        lignes.append(f"{SYMBOLES[w]} : " + ", ".join(valeurs))
    return "\n".join(lignes)


def _figure_braquages(c: Comparaison, dossier: Path, formats: Sequence[str]) -> Path | None:
    import matplotlib.pyplot as plt

    reductions = [r for r in (c.cartesien, c.polaire) if r is not None and _a_des_braquages(r)]
    if not reductions:
        return None
    rangees = []
    for r in reductions:
        libres = [w for w in _braquages(r) if not _enveloppe(r, w).est_point]
        lateraux = [w for w in libres if w != "DL"]
        # Le plan (δm, δn) s'il est libre ; sinon le braquage latéral et δl ; sinon un axe.
        u, v = ([*lateraux, *(w for w in libres if w == "DL"), None, None])[:2]
        autres = [w for w in libres if w not in (u, v)]
        rangees.append((r, _morceaux(r), u, v, autres))
    colonnes = max(len(m) for _, m, _, _, _ in rangees)
    une_dim = all(v is None for _, _, _, v, _ in rangees)
    # Panneaux à l'échelle : leur hauteur suit leur largeur et le rapport des plages.
    largeur_panneau = 0.82 * PAGE / colonnes
    if une_dim:
        hauteur = 0.45
    else:
        rapports = [
            _enveloppe(r, v).largeur / (_enveloppe(r, u).largeur or 1.0)
            for r, _, u, v, _ in rangees
            if u is not None and v is not None
        ]
        hauteur = min(2.2, max(0.7, largeur_panneau * max(rapports)))

    with _style() as cp:
        fig = plt.figure(
            figsize=(PAGE, (hauteur + 1.4) * len(rangees) + 0.35), layout="constrained"
        )
        sous = fig.subfigures(len(rangees), 1, squeeze=False)[:, 0]
        for sf, (r, morceaux, u, v, autres) in zip(sous, rangees):
            titre, detail = _titre_repere(c, r)
            sf.suptitle(f"{titre} : {detail}", x=0.0, ha="left", fontsize=9)
            axes = sf.subplots(1, colonnes, squeeze=False)[0]
            for k, ax in enumerate(axes):
                if k >= len(morceaux):
                    ax.set_axis_off()
                    continue
                m = morceaux[k]
                assert u is not None
                _panneau_braquages(ax, r, m, u, v, autres)
                etat = "tous les braquages" if _tous(r, m) else "une partie des braquages"
                nature = textwrap.fill(_nature(r, m), 104 // colonnes)
                ax.set_title(
                    f"{m.lettre} · {nature}\n{etat}",
                    fontsize=7.5,
                    loc="left",
                    color=BLEU if _tous(r, m) else "#B5651D",
                )
                texte = _texte_autres(r, m, autres)
                if texte:
                    ax.text(
                        0.0,
                        -0.32 if v is not None else -1.1,
                        texte,
                        transform=ax.transAxes,
                        fontsize=6.5,
                        color="0.3",
                        va="top",
                        ha="left",
                        wrap=True,
                    )
        cp.set_suptitle(
            fig, f"{c.etude.nom} : braquages calculés, morceau par morceau", fontsize=10
        )
        return _enregistrer(fig, dossier / "domaine_braquages", formats)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------


def tracer_figures_domaine(
    etude: Etude, dossier: Path, formats: Sequence[str] = FORMATS_DOMAINE
) -> list[Path]:
    """Écrit les figures du domaine réduit dans ``dossier`` ; renvoie un fichier par figure.

    Lève :class:`~cfd_doe.report.figures.FiguresIndisponibles` sans cfd-plot,
    :class:`~cfd_doe.data.etude.ErreurEtude` si aucun angle n'est libre (il
    n'y a alors pas de plan des angles à montrer).
    """
    figures._cfd_plot()  # par le module : un test peut le simuler absent
    c = comparer_reperes(etude)
    d = c.cartesien.domaine_entree
    if d["alpha"].est_point and d["beta"].est_point:
        raise ErreurEtude("figures du domaine : α et β fixés, pas de plan des angles à montrer")
    dossier.mkdir(parents=True, exist_ok=True)
    fichiers = [_figure_reperes(c, dossier, formats)]
    braquages = _figure_braquages(c, dossier, formats)
    if braquages is not None:
        fichiers.append(braquages)
    return fichiers
