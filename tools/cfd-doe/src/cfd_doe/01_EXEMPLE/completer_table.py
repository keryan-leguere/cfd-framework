"""Compléter par symétrie une table de résultats CFD, pour un lecteur de tables « carrées ».

Le plan de ``cfd-doe`` ne fait calculer qu'**un représentant par orbite** : sur un
plan de symétrie, la moitié des braquages ; sur l'axe αt = 0, une fraction du
plan (δm, δn). Un lecteur qui exploite les symétries *globales* (secteur
φa ∈ [0 ; 45°], β ≥ 0…) mais qui attend un **seul grand domaine** — une grille
produit, chaque variable sur toutes ses valeurs — y trouve des trous. Ce script
les bouche avec les lignes que les symétries donnent gratuitement.

Principe
--------
1. **Grille cible** : pour chaque variable, les valeurs de la table (et leurs
   images par le groupe) comprises dans le **domaine cible** — par défaut
   l'enveloppe des sous-domaines (φa ∈ [0 ; 45°], α ≥ 0 et β ≥ 0…). Si votre
   code lit plus large (β ≥ 0 seulement, α complet), le dire :
   ``domaine={"alpha": (-20, 20)}``. La grille est le produit de ces valeurs.
2. Pour chaque nœud absent de la table, on cherche dans son **orbite** un point
   calculé : ``x = g·y`` avec ``y`` calculé donne ``C(x) = s_g · C(y)``, ``s_g``
   changeant le signe des coefficients que ``g`` retourne. Symétries et signes
   sont lus dans le ``.yaml`` exporté (clé ``symetries``) : aucune convention
   n'est réécrite ici.
3. **Axe αt = 0 (polaire)** : φa n'y est qu'une convention (§2.5), la CFD n'a
   calculé que φa = 0. Le nœud (0, φa, δmB, δnB) est le même point physique que
   (0, 0, δm, δn), braquages ramenés en repère engin ; ses coefficients en
   repère mixte s'en déduisent par la rotation de φa (§3.2, §7.1). Quand
   (δm, δn) ne tombe pas sur un nœud — φa = 15° sur une grille carrée — la
   valeur est **interpolée** (bilinéaire dans le plan (δm, δn) de l'axe
   complété) et la ligne le dit (``origine``).
4. Ce qui n'a aucune image calculée reste un **trou** : NaN par défaut, pour que
   la table reste carrée et que le trou se voie. Typiquement les coins du carré
   des braquages hors du disque √(δm² + δn²) ≤ δmax : jamais calculés.

Contrôle gratuit : quand deux lignes *calculées* sont images l'une de l'autre
(dont un point sur son propre plan de symétrie, où CY, Cl, Cn doivent être
nuls), l'écart à la symétrie est mesuré et affiché. C'est là qu'une convention
de signe fausse se voit.

Usage
-----
::

    cfd-doe domaine ETUDE.yaml --export SD.yaml
    python completer_table.py SD.yaml RESULTATS.csv -o TABLE_COMPLETE.csv --cles Mach

ou depuis Python ::

    from completer_table import completer_table
    complet = completer_table(df, "SD.yaml", cles=["Mach"],
                              coefficients={"CN": "CNB", "CY": "CYB"})

**À adapter** : les dictionnaires ``COLONNES_VARIABLES`` et
``COLONNES_COEFFICIENTS`` ci-dessous (ou les arguments ``colonnes=`` et
``coefficients=``). Toute autre colonne (hors clés) est recopiée telle quelle
depuis la ligne source : elle est supposée invariante par symétrie.

Conventions (00_DOC/01_BASE_AERO.md) : angles en degrés ; CN = −CZ, CA = −CX ;
en polaire, coefficients et braquages en **repère mixte** (CNB, CYB, CmB, CnB,
δmB, δnB) ; (CN, CY), (Cm, Cn) et (δm, δn) tournent de la même façon. Seul le
traitement de l'axe αt = 0 dépend de ces conventions ; les miroirs et rotations
du ``.yaml``, eux, ne font que changer des signes.

Dépendances : numpy, pandas, pyyaml, rich. Ce fichier n'importe pas ``cfd_doe``.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

__all__ = [
    "COLONNES_COEFFICIENTS",
    "COLONNES_VARIABLES",
    "Bilan",
    "Plan",
    "completer_table",
    "lire_plan",
]

# ============================================================================
# À ADAPTER : noms de vos colonnes
# ============================================================================

#: Variable du plan (noms du .yaml) → colonne de votre DataFrame. Une variable
#: fixée à 0 dans tout le plan peut manquer du DataFrame.
COLONNES_VARIABLES: dict[str, str] = {
    # polaire (αt, φa), braquages en repère mixte
    "alphat": "alphat",
    "phia": "phia",
    "DMB": "DMB",
    "DNB": "DNB",
    "DL": "DL",
    # cartésien (α, β), repère engin
    "alpha": "alpha",
    "beta": "beta",
    "DM": "DM",
    "DN": "DN",
}

#: Rôle du coefficient → colonne. Un rôle dont la colonne est absente est ignoré.
#: Polaire : repère mixte (CAB, CNB, CYB, ClB, CmB, CnB). Cartésien : repère engin.
COLONNES_COEFFICIENTS: dict[str, str] = {
    "CA": "CA",
    "CN": "CN",
    "CY": "CY",
    "Cl": "Cl",
    "Cm": "Cm",
    "Cn": "Cn",
}

#: Colonne ajoutée : d'où vient chaque ligne (``None`` pour ne pas l'ajouter).
COLONNE_ORIGINE = "origine"

#: Deux valeurs d'une variable sont le même nœud à cette distance près (degrés).
TOLERANCE = 1e-6

# ============================================================================

#: Couples qui tournent comme (δm, δn) dans un changement de repère (§3.2, §7.1).
_PAIRES = (("CN", "CY"), ("Cm", "Cn"))

ORIGINE_CALCUL = "calcul"
ORIGINE_SYMETRIE = "symétrie"
ORIGINE_AXE = "αt = 0, repère"
ORIGINE_INTERPOLE = "αt = 0, interpolé"
ORIGINE_HORS_DISQUE = "trou : hors disque"
ORIGINE_BORD_AXE = "trou : αt = 0, maille incomplète"
ORIGINE_AXE_NON_INTERPOLE = "trou : αt = 0, non interpolé"
ORIGINE_SANS_IMAGE = "trou : sans image calculée"


# ---------------------------------------------------------------------------
# Lecture du plan (.yaml exporté par cfd-doe domaine --export)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Borne:
    """Un intervalle, bornes ouvertes ou fermées."""

    bas: float
    haut: float
    bas_inclus: bool = True
    haut_inclus: bool = True

    @property
    def est_point(self) -> bool:
        """Vrai pour une variable fixée."""
        return abs(self.haut - self.bas) <= TOLERANCE

    def contient(self, x: float, tol: float = TOLERANCE) -> bool:
        """Appartenance, bornes ouvertes respectées."""
        if x < self.bas - tol or x > self.haut + tol:
            return False
        if not self.bas_inclus and abs(x - self.bas) <= tol:
            return False
        return self.haut_inclus or abs(x - self.haut) > tol


def _angle(x: float) -> float:
    """Ramène un angle dans [0, 360[."""
    a = math.fmod(x, 360.0)
    if a < 0.0:
        a += 360.0
    return 0.0 if a > 360.0 - TOLERANCE else a


@dataclass(frozen=True)
class SousDomaine:
    """Un sous-domaine du plan : bornes, plus d'éventuelles contraintes (disque, secteur)."""

    numero: int
    nom: str
    bornes: dict[str, Borne]
    contraintes: tuple[dict[str, Any], ...] = ()

    def contient(self, point: Mapping[str, float], tol: float = TOLERANCE) -> bool:
        """Le point (variables du repère de travail) est-il dans le sous-domaine ?"""
        if not all(b.contient(point[v], tol) for v, b in self.bornes.items()):
            return False
        for c in self.contraintes:
            x, y = point[c["x"]], point[c["y"]]
            if c["type"] == "disque":
                if math.hypot(x, y) > c["rayon"] + tol:
                    return False
            elif c["type"] == "secteur":
                if math.hypot(x, y) <= tol:
                    return False
                angle = Borne(c["angle_min"], c["angle_max"], c["min_inclus"], c["max_inclus"])
                if not angle.contient(_angle(math.degrees(math.atan2(y, x))), 1e-7):
                    return False
        return True


@dataclass(frozen=True)
class Symetrie:
    """Une symétrie de l'engin, telle que le .yaml la décrit."""

    nom: str
    variables: frozenset[str] = frozenset()
    coefficients: frozenset[str] = frozenset()
    #: Action sur φa : ``("rotation", θ)`` → φa + θ ; ``("miroir", φs)`` → 2φs − φa.
    phia: tuple[str, float] | None = None

    def image(self, point: Mapping[str, float]) -> dict[str, float]:
        """L'image d'un point."""
        resultat = {v: (-x if v in self.variables else x) for v, x in point.items()}
        if self.phia is not None and "phia" in resultat:
            type_, angle = self.phia
            phi = point["phia"]
            resultat["phia"] = _angle(phi + angle if type_ == "rotation" else 2.0 * angle - phi)
        return resultat

    def signes(self, coefs: Mapping[str, float]) -> dict[str, float]:
        """Les coefficients, ceux que la symétrie retourne changés de signe."""
        return {r: (-c if r in self.coefficients else c) for r, c in coefs.items()}


IDENTITE = Symetrie("identité")


@dataclass(frozen=True)
class Plan:
    """Ce que le script lit du .yaml."""

    etude: str
    repere: str
    groupe: str
    variables: tuple[str, ...]
    sous_domaines: tuple[SousDomaine, ...]
    symetries: tuple[Symetrie, ...]
    source: str = ""

    @property
    def groupe_complet(self) -> tuple[Symetrie, ...]:
        """Identité en tête, puis les symétries du fichier."""
        return (IDENTITE, *self.symetries)

    @property
    def enveloppe(self) -> dict[str, Borne]:
        """Le domaine que lit un lecteur « carré » : l'enveloppe fermée des sous-domaines."""
        return {
            v: Borne(
                min(sd.bornes[v].bas for sd in self.sous_domaines),
                max(sd.bornes[v].haut for sd in self.sous_domaines),
            )
            for v in self.variables
        }

    @property
    def rayon_disque(self) -> float | None:
        """Le rayon de la limite des braquages, s'il y en a une."""
        rayons = [
            c["rayon"] for sd in self.sous_domaines for c in sd.contraintes if c["type"] == "disque"
        ]
        return max(rayons) if rayons else None

    def dans_le_plan(self, point: Mapping[str, float], tol: float = TOLERANCE) -> bool:
        """Le point est-il dans un des sous-domaines (ce que la CFD calcule) ?"""
        return any(sd.contient(point, tol) for sd in self.sous_domaines)


def _borne(d: Mapping[str, Any]) -> Borne:
    return Borne(float(d["bas"]), float(d["haut"]), bool(d["bas_inclus"]), bool(d["haut_inclus"]))


def lire_plan(source: str | Path | Mapping[str, Any] | Plan) -> Plan:
    """Lit le .yaml (ou .json) exporté par ``cfd-doe domaine --export``, ou son contenu."""
    if isinstance(source, Plan):
        return source
    nom = ""
    if isinstance(source, (str, Path)):
        nom = str(source)
        donnees = yaml.safe_load(Path(source).read_text(encoding="utf-8"))
    else:
        donnees = dict(source)
    if "symetries" not in donnees:
        raise ValueError(
            f"{nom or 'le plan'} ne décrit pas ses symétries (clé « symetries ») : "
            "le régénérer avec une version récente de « cfd-doe domaine … --export »"
        )
    symetries = []
    for s in donnees["symetries"]:
        phia = s.get("phia")
        action = None
        if phia:
            ((type_, angle),) = phia.items()
            action = (str(type_), float(angle))
        symetries.append(
            Symetrie(str(s["nom"]), frozenset(s["variables"]), frozenset(s["coefficients"]), action)
        )
    sous_domaines = tuple(
        SousDomaine(
            int(sd["numero"]),
            str(sd["nom"]),
            {v: _borne(b) for v, b in sd["bornes"].items()},
            tuple(sd.get("contraintes", ())),
        )
        for sd in donnees["sous_domaines"]
    )
    return Plan(
        etude=str(donnees.get("etude", "")),
        repere=str(donnees["repere"]),
        groupe=str(donnees.get("groupe", "")),
        variables=tuple(donnees["variables"]),
        sous_domaines=sous_domaines,
        symetries=tuple(symetries),
        source=nom,
    )


# ---------------------------------------------------------------------------
# Changement de repère à αt = 0
# ---------------------------------------------------------------------------


def _tourner(x: float, y: float, angle: float) -> tuple[float, float]:
    """Repère engin → repère mixte tourné de ``angle`` : comme (δm, δn) → (δmB, δnB) (§7.1)."""
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return c * x - s * y, s * x + c * y


def _tourner_coefs(coefs: Mapping[str, float], angle: float) -> dict[str, float]:
    """Coefficients en repère engin → repère mixte de ``angle`` ; CA et Cl inchangés."""
    resultat = dict(coefs)
    for a, b in _PAIRES:
        if a in coefs:
            resultat[a], resultat[b] = _tourner(coefs[a], coefs[b], angle)
    return resultat


# ---------------------------------------------------------------------------
# Complétion
# ---------------------------------------------------------------------------


@dataclass
class Bilan:
    """Ce qui s'est passé, pour le rapport (sommé sur les groupes de clés)."""

    plan: Plan
    entree: int = 0
    doublons: int = 0
    hors_enveloppe: int = 0
    #: Domaine cible : l'enveloppe du plan, sauf variables imposées par ``domaine=``.
    cible: dict[str, Borne] = field(default_factory=dict)
    imposees: list[str] = field(default_factory=list)
    groupes: int = 0
    noeuds: int = 0
    origines: Counter[str] = field(default_factory=Counter)
    detail: Counter[str] = field(default_factory=Counter)
    #: rôle → (nombre de paires, écart max) sur les lignes calculées.
    coherence: dict[str, tuple[int, float]] = field(default_factory=dict)
    grille: dict[str, list[float]] = field(default_factory=dict)
    colonnes_variables: dict[str, str] = field(default_factory=dict)
    colonnes_coefficients: dict[str, str] = field(default_factory=dict)
    fixees: dict[str, float] = field(default_factory=dict)
    recopiees: list[str] = field(default_factory=list)
    ignorees: list[str] = field(default_factory=list)
    cles: list[str] = field(default_factory=list)

    @property
    def sortie(self) -> int:
        """Lignes de la table complète, trous compris."""
        return sum(self.origines.values())


class _Contexte:
    """Une table (un groupe de clés) indexée par nœud."""

    def __init__(self, plan: Plan, tol: float) -> None:
        self.plan = plan
        self.tol = tol
        self.index: dict[tuple[int, ...], int] = {}

    def cle(self, point: Mapping[str, float]) -> tuple[int, ...]:
        return tuple(
            round((_angle(point[v]) if v == "phia" else point[v]) / self.tol)
            for v in self.plan.variables
        )


def _grille(
    points: Sequence[Mapping[str, float]], plan: Plan, cible: Mapping[str, Borne], tol: float
) -> dict[str, list[float]]:
    """Valeurs de chaque variable, et de leurs images, dans le domaine cible."""
    enveloppe = cible
    valeurs: dict[str, dict[int, float]] = {v: {} for v in plan.variables}
    for p in points:
        for g in plan.groupe_complet:
            q = g.image(p)
            for v in plan.variables:
                x = q[v]
                if enveloppe[v].contient(x, tol):
                    valeurs[v].setdefault(round(x / tol), x)
    return {v: sorted(d.values()) for v, d in valeurs.items()}


def _interpoler(
    axe: Mapping[tuple[int, int, int], dict[str, float]],
    xs: Sequence[float],
    ys: Sequence[float],
    x: float,
    y: float,
    dl: float,
    tol: float,
) -> tuple[dict[str, float], tuple[int, int, int]] | None:
    """Interpolation dans le plan (δm, δn) de l'axe, à δl fixé.

    Bilinéaire si les quatre coins de la maille sont connus ; sinon linéaire
    sur un triangle de la maille dont les trois coins le sont (bord du disque
    des braquages, où un coin manque) ; sinon ``None``.
    """

    def encadrer(valeurs: Sequence[float], v: float) -> tuple[float, float] | None:
        for a, b in zip(valeurs, valeurs[1:]):
            if a - tol <= v <= b + tol:
                return a, b
        return None

    cx, cy = encadrer(xs, x), encadrer(ys, y)
    if cx is None or cy is None:
        return None
    (x0, x1), (y0, y1) = cx, cy
    tx, ty = (x - x0) / (x1 - x0), (y - y0) / (y1 - y0)
    # Coins numérotés 2·iy + ix : 0 = (x0, y0), 1 = (x1, y0), 2 = (x0, y1), 3 = (x1, y1).
    coins = [
        (round(xi / tol), round(yi / tol), round(dl / tol)) for yi in (y0, y1) for xi in (x0, x1)
    ]
    connus = [k in axe for k in coins]
    poids = [0.0] * 4
    if all(connus):
        poids = [(1 - tx) * (1 - ty), tx * (1 - ty), (1 - tx) * ty, tx * ty]
    else:
        # Triangle sans le coin ``absent`` : son angle droit est le coin opposé.
        for absent in range(4):
            if not all(connus[i] for i in range(4) if i != absent):
                continue
            droit = 3 - absent
            dx, dy = abs(tx - (droit & 1)), abs(ty - (droit >> 1))
            if dx + dy <= 1 + 1e-9:
                poids[droit], poids[droit ^ 1], poids[droit ^ 2] = 1 - dx - dy, dx, dy
                break
        else:
            return None
    utiles = [(w, k) for w, k in zip(poids, coins) if k in axe]
    resultat = {r: sum(w * axe[k][r] for w, k in utiles) for r in axe[utiles[0][1]]}
    return resultat, max(utiles)[1]


def _completer_groupe(
    points: list[dict[str, float]],
    coefs: list[dict[str, float]],
    autres: list[dict[str, Any]],
    plan: Plan,
    bilan: Bilan,
    *,
    interpoler_axe: bool,
    tol: float,
) -> list[tuple[dict[str, float], dict[str, float], dict[str, Any], str]]:
    """Complète une table ; renvoie (point, coefficients, autres colonnes, origine) par nœud."""
    ctx = _Contexte(plan, tol)
    enveloppe = bilan.cible
    gardes: list[int] = []
    for i, p in enumerate(points):
        if not all(enveloppe[v].contient(p[v], tol) for v in plan.variables):
            bilan.hors_enveloppe += 1
            continue
        k = ctx.cle(p)
        if k in ctx.index:
            bilan.doublons += 1
            continue
        ctx.index[k] = i
        gardes.append(i)

    # Contrôle : lignes calculées images l'une de l'autre (points fixes compris).
    for i in gardes:
        for g in plan.symetries:
            j = ctx.index.get(ctx.cle(g.image(points[i])))
            if j is None:
                continue
            attendu = g.signes(coefs[j])
            for r, valeur in coefs[i].items():
                n, ecart = bilan.coherence.get(r, (0, 0.0))
                bilan.coherence[r] = (n + 1, max(ecart, abs(valeur - attendu[r])))

    grille = _grille([points[i] for i in gardes], plan, enveloppe, tol)
    for v, valeurs in grille.items():
        connues = {round(x / tol) for x in bilan.grille.get(v, [])}
        bilan.grille[v] = sorted(
            [*bilan.grille.get(v, []), *(x for x in valeurs if round(x / tol) not in connues)]
        )
    polaire = plan.repere == "polaire"
    noeuds = [dict(zip(plan.variables, n)) for n in product(*(grille[v] for v in plan.variables))]
    bilan.noeuds = max(bilan.noeuds, len(noeuds))

    lignes: list[tuple[dict[str, float], dict[str, float], dict[str, Any], str] | None] = []
    en_attente: list[int] = []
    for noeud in noeuds:
        trouve = None
        j = ctx.index.get(ctx.cle(noeud))
        if j is not None:
            trouve = (coefs[j], autres[j], ORIGINE_CALCUL)
        else:
            for g in plan.symetries:
                j = ctx.index.get(ctx.cle(g.image(noeud)))
                if j is not None:
                    trouve = (g.signes(coefs[j]), autres[j], f"{ORIGINE_SYMETRIE} : {g.nom}")
                    break
        if trouve is None and polaire and abs(noeud["alphat"]) <= tol:
            # φa n'est qu'une convention à αt = 0 : on revient au φa = 0 calculé.
            for g in plan.groupe_complet:
                q = g.image(noeud)
                dm, dn = _tourner(q["DMB"], q["DNB"], -q["phia"])
                j = ctx.index.get(ctx.cle({**q, "phia": 0.0, "DMB": dm, "DNB": dn}))
                if j is not None:
                    deduits = g.signes(_tourner_coefs(coefs[j], q["phia"]))
                    trouve = (deduits, autres[j], f"{ORIGINE_AXE} : {g.nom}")
                    break
        if trouve is None:
            en_attente.append(len(lignes))
            lignes.append(None)
        else:
            lignes.append((noeud, *trouve))

    if polaire and interpoler_axe and en_attente:
        # Le plan (δm, δn) de l'axe, complété ci-dessus, sert de table d'interpolation.
        axe: dict[tuple[int, int, int], dict[str, float]] = {}
        sources: dict[tuple[int, int, int], dict[str, Any]] = {}
        for ligne in lignes:
            if ligne is None:
                continue
            p, connus, source, _ = ligne
            if abs(p["alphat"]) <= tol and abs(p["phia"]) <= tol:
                k = (round(p["DMB"] / tol), round(p["DNB"] / tol), round(p["DL"] / tol))
                axe[k], sources[k] = connus, source
        for indice in list(en_attente):
            noeud = noeuds[indice]
            if abs(noeud["alphat"]) > tol:
                continue
            for g in plan.groupe_complet:
                q = g.image(noeud)
                dm, dn = _tourner(q["DMB"], q["DNB"], -q["phia"])
                interpole = _interpoler(axe, grille["DMB"], grille["DNB"], dm, dn, q["DL"], tol)
                if interpole is not None:
                    c_engin, coin = interpole
                    deduits = g.signes(_tourner_coefs(c_engin, q["phia"]))
                    lignes[indice] = (noeud, deduits, sources[coin], ORIGINE_INTERPOLE)
                    en_attente.remove(indice)
                    break

    rayon = plan.rayon_disque
    roles = list(coefs[gardes[0]]) if gardes else []
    resultat = []
    for noeud, ligne in zip(noeuds, lignes):
        if ligne is None:
            if (
                polaire
                and rayon is not None
                and math.hypot(noeud["DMB"], noeud["DNB"]) > rayon + tol
            ):
                origine = ORIGINE_HORS_DISQUE
            elif polaire and abs(noeud["alphat"]) <= tol:
                origine = ORIGINE_BORD_AXE if interpoler_axe else ORIGINE_AXE_NON_INTERPOLE
            else:
                origine = ORIGINE_SANS_IMAGE
            ligne = (noeud, {r: math.nan for r in roles}, {}, origine)
        resultat.append(ligne)
        bilan.detail[ligne[3]] += 1
        bilan.origines[_categorie(ligne[3])] += 1
    return resultat


def _categorie(origine: str) -> str:
    """« symétrie : miroir φs = 0° » → « symétrie » ; les autres origines sont leur catégorie."""
    for prefixe in (ORIGINE_SYMETRIE, ORIGINE_AXE):
        if origine.startswith(prefixe + " : "):
            return prefixe
    return origine


def completer_table(
    df: pd.DataFrame,
    plan: str | Path | Mapping[str, Any] | Plan,
    *,
    cles: Sequence[str] = (),
    domaine: Mapping[str, tuple[float, float]] | None = None,
    colonnes: Mapping[str, str] | None = None,
    coefficients: Mapping[str, str] | None = None,
    colonne_origine: str | None = COLONNE_ORIGINE,
    trous: str = "nan",
    interpoler_axe: bool = True,
    tol: float = TOLERANCE,
    rapport: bool = True,
    console: Console | None = None,
    retour_bilan: bool = False,
) -> Any:
    """Ajoute à ``df`` les lignes que les symétries du plan permettent de déduire.

    Parameters
    ----------
    df
        Une ligne par point de vol calculé : variables du repère de travail,
        coefficients, et toute autre colonne (recopiée depuis la ligne source).
    plan
        Le .yaml exporté par ``cfd-doe domaine … --export`` (chemin ou contenu).
    cles
        Colonnes qui séparent des tables indépendantes (Mach, altitude…) :
        chacune est complétée à part, sur sa propre grille.
    domaine
        Plage lue par votre code, par variable du plan, quand elle dépasse
        l'enveloppe des sous-domaines : ``{"alpha": (-20, 20)}`` pour un lecteur
        qui n'exploite que β ≥ 0. Les autres variables gardent l'enveloppe.
    colonnes, coefficients
        Surcharges de ``COLONNES_VARIABLES`` et ``COLONNES_COEFFICIENTS``.
    colonne_origine
        Colonne ajoutée qui dit d'où vient chaque ligne ; ``None`` pour s'en passer.
    trous
        ``"nan"`` (défaut) : un nœud sans image reste une ligne de NaN, la table
        reste carrée ; ``"omettre"`` : il n'apparaît pas.
    interpoler_axe
        Polaire, αt = 0 : interpoler quand le changement de repère ne tombe pas
        sur un nœud (sinon, trou).
    rapport
        Afficher le rapport (Rich).
    retour_bilan
        Rendre aussi le :class:`Bilan` (comptes, contrôle des symétries).

    Returns
    -------
    La table complète, triée par clés puis variables (et le bilan si
    ``retour_bilan``). Les lignes calculées y sont reprises telles quelles.
    """
    if trous not in ("nan", "omettre"):
        raise ValueError(f"trous : « nan » ou « omettre », pas {trous!r}")
    plan = lire_plan(plan)
    noms_var = {**COLONNES_VARIABLES, **(colonnes or {})}
    noms_coef = dict(coefficients) if coefficients is not None else dict(COLONNES_COEFFICIENTS)

    manquantes = [c for c in cles if c not in df.columns]
    if manquantes:
        raise ValueError(f"clé(s) absente(s) du DataFrame : {', '.join(manquantes)}")
    enveloppe = dict(plan.enveloppe)
    inconnues = [v for v in (domaine or {}) if v not in plan.variables]
    if inconnues:
        raise ValueError(
            f"domaine : variable(s) {', '.join(inconnues)} absente(s) du plan "
            f"(variables : {', '.join(plan.variables)})"
        )
    for v, (bas, haut) in (domaine or {}).items():
        enveloppe[v] = Borne(float(bas), float(haut))
    var_cols: dict[str, str] = {}
    fixees: dict[str, float] = {}
    for v in plan.variables:
        col = noms_var.get(v, v)
        if col in df.columns:
            var_cols[v] = col
        elif enveloppe[v].est_point:
            fixees[v] = enveloppe[v].bas
        else:
            raise ValueError(
                f"variable {v} : colonne « {col} » absente du DataFrame "
                "(adapter COLONNES_VARIABLES, passer colonnes={…} ou, en ligne de commande, --noms)"
            )
    coef_cols = {r: c for r, c in noms_coef.items() if c in df.columns}
    if not coef_cols:
        raise ValueError(
            "aucun coefficient trouvé : adapter COLONNES_COEFFICIENTS, passer coefficients={…} ou --noms"
        )
    if plan.repere == "polaire":
        for a, b in _PAIRES:
            if (a in coef_cols) != (b in coef_cols):
                present, absent = (a, b) if a in coef_cols else (b, a)
                raise ValueError(
                    f"{present} sans {absent} : à αt = 0, le changement de repère les fait "
                    "tourner ensemble (§3.2) ; déclarer les deux colonnes"
                )
    connues = {*cles, *var_cols.values(), *coef_cols.values()}
    if colonne_origine:
        connues.add(colonne_origine)
    recopiees = [c for c in df.columns if c not in connues]

    bilan = Bilan(
        plan=plan,
        entree=len(df),
        colonnes_variables=var_cols,
        colonnes_coefficients=coef_cols,
        fixees=fixees,
        recopiees=recopiees,
        ignorees=[r for r, c in noms_coef.items() if c not in df.columns],
        cles=list(cles),
        cible=enveloppe,
        imposees=list(domaine or {}),
    )
    groupes = [((), df)] if not cles else list(df.groupby(list(cles), sort=True, dropna=False))

    enregistrements: list[dict[str, Any]] = []
    for valeurs_cles, sous in groupes:
        bilan.groupes += 1
        if not isinstance(valeurs_cles, tuple):
            valeurs_cles = (valeurs_cles,)
        lignes = sous.to_dict("records")
        points = [
            {v: float(ligne[var_cols[v]]) if v in var_cols else fixees[v] for v in plan.variables}
            for ligne in lignes
        ]
        coefs = [{r: float(ligne[c]) for r, c in coef_cols.items()} for ligne in lignes]
        autres = [{c: ligne[c] for c in recopiees} for ligne in lignes]
        resultat = _completer_groupe(
            points, coefs, autres, plan, bilan, interpoler_axe=interpoler_axe, tol=tol
        )
        for noeud, valeurs_coefs, valeurs_autres, origine in resultat:
            if trous == "omettre" and origine.startswith("trou"):
                continue
            ligne_sortie: dict[str, Any] = dict(zip(cles, valeurs_cles))
            ligne_sortie.update({col: noeud[v] for v, col in var_cols.items()})
            ligne_sortie.update(
                {col: valeurs_coefs.get(r, math.nan) for r, col in coef_cols.items()}
            )
            ligne_sortie.update({col: valeurs_autres.get(col) for col in recopiees})
            if colonne_origine:
                ligne_sortie[colonne_origine] = origine
            enregistrements.append(ligne_sortie)

    ordre = [*cles, *var_cols.values(), *coef_cols.values(), *recopiees]
    if colonne_origine:
        ordre.append(colonne_origine)
    sortie = pd.DataFrame.from_records(enregistrements, columns=ordre)
    sortie = sortie.sort_values([*cles, *var_cols.values()], kind="stable").reset_index(drop=True)
    if rapport:
        (console or Console(highlight=False)).print(rendre_bilan(bilan, trous=trous))
    return (sortie, bilan) if retour_bilan else sortie


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------

_SYMBOLES = {
    "alphat": "αt",
    "phia": "φa",
    "DMB": "δmB",
    "DNB": "δnB",
    "DL": "δl",
    "alpha": "α",
    "beta": "β",
    "DM": "δm",
    "DN": "δn",
}
_TITRE, _ACCENT, _DISCRET, _ATTENTION, _ERREUR = "cyan", "green", "dim", "yellow", "red"


#: Séparateur des milliers (espace fine insécable).
_ESPACE_FINE = chr(0x202F)


def _n(x: int) -> str:
    """Entier à la française : 12 345."""
    return f"{x:,}".replace(",", _ESPACE_FINE)


def _f(x: float, decimales: int = 2) -> str:
    texte = f"{x:.{decimales}f}".rstrip("0").rstrip(".")
    return ("0" if texte in ("-0", "") else texte).replace("-", "−").replace(".", ",")


def _e(x: float) -> str:
    """Un écart : notation scientifique au-delà de trois décimales."""
    if x == 0.0:
        return "0"
    return _f(x, 4) if x >= 1e-3 else f"{x:.1e}".replace("-", "−").replace(".", ",")


def _valeurs(valeurs: Sequence[float], largeur: int = 7) -> str:
    if len(valeurs) <= largeur:
        return " · ".join(_f(v) for v in valeurs)
    tete = " · ".join(_f(v) for v in valeurs[:3])
    return f"{tete} · … · {_f(valeurs[-1])}"


def _en_tete(bilan: Bilan) -> Panel:
    plan = bilan.plan
    grille = Table.grid(padding=(0, 2))
    grille.add_column(style=_DISCRET, no_wrap=True)
    grille.add_column()
    if plan.source:
        grille.add_row("Plan", Path(plan.source).name)
    repere = "polaire (αt, φa), repère mixte" if plan.repere == "polaire" else "cartésien (α, β)"
    grille.add_row(
        "Repère",
        Text.assemble(
            (repere, "default"), (f"  {plan.groupe}, {len(plan.symetries)} symétries", _DISCRET)
        ),
    )
    if bilan.cles:
        grille.add_row("Clés", f"{', '.join(bilan.cles)}  ({bilan.groupes} tables)")
    grille.add_row(
        "Variables",
        "  ".join(f"{_SYMBOLES.get(v, v)} → {c}" for v, c in bilan.colonnes_variables.items())
        + "".join(f"  {_SYMBOLES.get(v, v)} = {_f(x)}" for v, x in bilan.fixees.items()),
    )
    grille.add_row(
        "Coefficients",
        "  ".join(f"{r} → {c}" for r, c in bilan.colonnes_coefficients.items()),
    )
    retournes = sorted({c for s in plan.symetries for c in s.coefficients})
    if retournes:
        grille.add_row("Signes", f"changés par une symétrie au moins : {', '.join(retournes)}")
    if bilan.recopiees:
        grille.add_row("Recopiées", ", ".join(bilan.recopiees))
    return Panel(
        grille,
        title=Text(f"completer_table · {plan.etude}", style=_TITRE),
        title_align="left",
        box=box.ROUNDED,
        border_style=_DISCRET,
        padding=(0, 1),
    )


def _table_grille(bilan: Bilan) -> Table:
    table = Table(
        title=Text(f"Grille cible ({_n(bilan.noeuds)} nœuds par table)", style=_TITRE),
        title_justify="left",
        box=box.SIMPLE_HEAD,
        header_style=_TITRE,
        pad_edge=False,
    )
    table.add_column("variable")
    table.add_column("domaine", justify="center")
    table.add_column("n", justify="right")
    table.add_column("valeurs", style=_DISCRET)
    for v, valeurs in bilan.grille.items():
        b = bilan.cible[v]
        env = _f(b.bas) if b.est_point else f"[{_f(b.bas)};{_f(b.haut)}]"
        if v in bilan.imposees:
            env += "*"
        table.add_row(_SYMBOLES.get(v, v), env, str(len(valeurs)), _valeurs(valeurs))
    if bilan.imposees:
        table.caption = Text(
            "* imposé par domaine=, au-delà de l'enveloppe du plan", style=_DISCRET
        )
        table.caption_justify = "left"
    return table


def _table_origines(bilan: Bilan) -> Table:
    total = bilan.sortie
    table = Table(
        title=Text("Lignes de la table complète", style=_TITRE),
        title_justify="left",
        box=box.SIMPLE_HEAD,
        header_style=_TITRE,
        pad_edge=False,
        show_footer=True,
    )
    table.add_column("origine", footer="total")
    table.add_column("lignes", justify="right", footer=_n(total))
    table.add_column("%", justify="right", footer="100")

    def ligne(libelle: str, n: int, style: str = "default", retrait: bool = False) -> None:
        if n:
            table.add_row(
                Text(("  " if retrait else "") + libelle, style=style),
                Text(_n(n), style=style),
                Text(_f(100 * n / total, 1), style=style),
            )

    ligne("calculées (entrée)", bilan.origines[ORIGINE_CALCUL])
    for categorie, libelle in (
        (ORIGINE_SYMETRIE, "par symétrie"),
        (ORIGINE_AXE, "αt = 0, changement de repère"),
    ):
        ligne(libelle, bilan.origines[categorie], _ACCENT)
        for g in bilan.plan.groupe_complet:
            ligne(g.nom, bilan.detail[f"{categorie} : {g.nom}"], _DISCRET, retrait=True)
    ligne("αt = 0, interpolées (δm, δn)", bilan.origines[ORIGINE_INTERPOLE], _ATTENTION)
    ligne(ORIGINE_HORS_DISQUE, bilan.origines[ORIGINE_HORS_DISQUE], _DISCRET)
    ligne(ORIGINE_BORD_AXE, bilan.origines[ORIGINE_BORD_AXE], _DISCRET)
    ligne(ORIGINE_AXE_NON_INTERPOLE, bilan.origines[ORIGINE_AXE_NON_INTERPOLE], _DISCRET)
    ligne(ORIGINE_SANS_IMAGE, bilan.origines[ORIGINE_SANS_IMAGE], _ERREUR)
    return table


def _table_coherence(bilan: Bilan) -> Group | Text:
    if not bilan.coherence:
        return Text(
            "Aucune paire de lignes calculées liées par une symétrie : rien à contrôler.",
            style=_DISCRET,
        )
    table = Table(
        title=Text("Contrôle des symétries", style=_TITRE),
        title_justify="left",
        box=box.SIMPLE_HEAD,
        header_style=_TITRE,
        pad_edge=False,
    )
    table.add_column("coefficient")
    table.add_column("colonne", style=_DISCRET)
    table.add_column("paires", justify="right")
    table.add_column("écart max", justify="right")
    for r, (n, ecart) in bilan.coherence.items():
        style = _ACCENT if ecart <= 1e-9 else _ATTENTION
        table.add_row(r, bilan.colonnes_coefficients[r], _n(n), Text(_e(ecart), style=style))
    note = _puces(
        [
            "écart |C(x) − s·C(g·x)| entre lignes calculées images l'une de l'autre, "
            "points fixes compris (les coefficients retournés y sont nuls) ; non nul, il "
            "trahit une convention de signe différente de celle du .yaml"
        ],
        puce="",
        style=_DISCRET,
    )
    return Group(table, note)


def _puces(lignes: Sequence[str], *, puce: str = "!", style: str = _ATTENTION) -> Table:
    """Liste à puces dont les lignes repliées gardent leur retrait."""
    grille = Table.grid(padding=(0, 1))
    grille.add_column(no_wrap=True, justify="right", min_width=3)
    grille.add_column()
    for texte in lignes:
        grille.add_row(Text(puce, style=style), Text(texte, style=style))
    return grille


def rendre_bilan(bilan: Bilan, *, trous: str = "nan") -> Group:
    """Le rapport complet, prêt pour ``Console.print``."""
    morceaux: list[Any] = [
        _en_tete(bilan),
        Text(),
        _table_grille(bilan),
        Text(),
        _table_origines(bilan),
        _table_coherence(bilan),
        Text(),
    ]
    avertissements = []
    if bilan.doublons:
        avertissements.append(f"{_n(bilan.doublons)} ligne(s) en double : la première est gardée")
    if bilan.hors_enveloppe:
        avertissements.append(
            f"{_n(bilan.hors_enveloppe)} ligne(s) hors du domaine cible : ignorées"
        )
    if bilan.ignorees:
        avertissements.append(
            "coefficient(s) sans colonne, ignoré(s) : " + ", ".join(bilan.ignorees)
        )
    rayon = bilan.plan.rayon_disque
    if bilan.origines[ORIGINE_HORS_DISQUE] and rayon is not None:
        avertissements.append(
            f"{_n(bilan.origines[ORIGINE_HORS_DISQUE])} nœud(s) hors du disque "
            f"√(δmB² + δnB²) ≤ {_f(rayon)}° : hors débattement, jamais calculés (§7.6)"
        )
    if bilan.origines[ORIGINE_INTERPOLE]:
        avertissements.append(
            f"{_n(bilan.origines[ORIGINE_INTERPOLE])} ligne(s) à αt = 0, φa ≠ 0 interpolées : "
            "(δm, δn) ramené en repère engin tombe entre les nœuds ; exactes seulement si C "
            "est linéaire en braquages (interpoler_axe=False pour en faire des trous)"
        )
    if bilan.origines[ORIGINE_BORD_AXE]:
        avertissements.append(
            f"{_n(bilan.origines[ORIGINE_BORD_AXE])} nœud(s) à αt = 0 sans maille complète "
            "autour de leur image en repère engin (bord du disque des braquages) : trous"
        )
    if bilan.origines[ORIGINE_SANS_IMAGE]:
        avertissements.append(
            f"{_n(bilan.origines[ORIGINE_SANS_IMAGE])} nœud(s) sans aucune image calculée : "
            "points du plan manquants dans la table ?"
        )
    if avertissements:
        morceaux += [_puces(avertissements), Text()]

    trous_n = sum(n for o, n in bilan.origines.items() if o.startswith("trou"))
    deduites = bilan.sortie - bilan.origines[ORIGINE_CALCUL] - trous_n
    synthese = Text.assemble(
        (_n(bilan.origines[ORIGINE_CALCUL]), _ACCENT),
        (" lignes calculées → ", _DISCRET),
        (_n(bilan.sortie), _ACCENT),
        (f" lignes ({bilan.groupes} × {_n(bilan.noeuds)} nœuds)", _DISCRET),
        (" · ", _DISCRET),
        (_n(deduites), _ACCENT),
        (" déduites", _DISCRET),
    )
    if trous_n:
        synthese.append(" · ", style=_DISCRET)
        synthese.append(_n(trous_n), style=_ATTENTION)
        synthese.append(" trous " + ("(NaN)" if trous == "nan" else "(omis)"), style=_DISCRET)
    morceaux.append(synthese)
    return Group(*morceaux)


# ---------------------------------------------------------------------------
# Ligne de commande
# ---------------------------------------------------------------------------


def _noms(paires: Sequence[str]) -> tuple[dict[str, str], dict[str, str]]:
    """``alphat=ALPHAT CN=CNB`` → (variables, coefficients), d'après le nom de gauche."""
    variables: dict[str, str] = {}
    coefficients: dict[str, str] = dict(COLONNES_COEFFICIENTS)
    for paire in paires:
        nom, egal, colonne = paire.partition("=")
        if not egal or not colonne:
            raise ValueError(f"--noms : « {paire} » n'est pas de la forme NOM=COLONNE")
        if nom in COLONNES_VARIABLES:
            variables[nom] = colonne
        elif nom in COLONNES_COEFFICIENTS:
            coefficients[nom] = colonne
        else:
            admis = ", ".join([*COLONNES_VARIABLES, *COLONNES_COEFFICIENTS])
            raise ValueError(f"--noms : « {nom} » inconnu ; admis : {admis}")
    return variables, coefficients


def main(argv: Sequence[str] | None = None) -> int:
    """``python completer_table.py SD.yaml RESULTATS.csv -o COMPLET.csv``."""
    parser = argparse.ArgumentParser(
        description="Compléter par symétrie une table de résultats CFD (plan cfd-doe)."
    )
    parser.add_argument("plan", type=Path, help="le .yaml exporté par cfd-doe domaine --export")
    parser.add_argument("resultats", type=Path, help="table de résultats (.csv)")
    parser.add_argument("-o", "--sortie", type=Path, help="table complète à écrire (.csv)")
    parser.add_argument("--cles", nargs="*", default=[], help="colonnes de conditions (Mach…)")
    parser.add_argument(
        "--noms",
        nargs="*",
        default=[],
        metavar="NOM=COLONNE",
        help="vos noms de colonnes : alphat=ALPHAT phia=PHIA CN=CNB …",
    )
    parser.add_argument(
        "--domaine",
        nargs=3,
        action="append",
        default=[],
        metavar=("VAR", "BAS", "HAUT"),
        help="plage lue par votre code au-delà de l'enveloppe : --domaine alpha -20 20",
    )
    parser.add_argument("--sep", default=",", help="séparateur CSV (défaut : ,)")
    parser.add_argument("--omettre-trous", action="store_true", help="ne pas écrire les trous")
    args = parser.parse_args(argv)
    console = Console(highlight=False)
    try:
        variables, coefficients = _noms(args.noms)
        df = pd.read_csv(args.resultats, sep=args.sep)
        complet = completer_table(
            df,
            args.plan,
            cles=args.cles,
            domaine={v: (float(b), float(h)) for v, b, h in args.domaine},
            colonnes=variables,
            coefficients=coefficients,
            trous="omettre" if args.omettre_trous else "nan",
            console=console,
        )
    except (ValueError, OSError) as erreur:
        console.print(
            Panel(
                Text(str(erreur), style=_ERREUR),
                title=Text("completer_table · erreur", style=_ERREUR),
                title_align="left",
                border_style=_ERREUR,
                box=box.ROUNDED,
            )
        )
        return 1
    if args.sortie is not None:
        complet.to_csv(args.sortie, sep=args.sep, index=False)
        console.print(f"[{_ACCENT}]écrit :[/] {args.sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
