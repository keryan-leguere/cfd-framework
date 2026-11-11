"""Des résultats CFD d'un plan aux tables du simulateur : une table carrée par coefficient.

Une fois le DOE calculé, chaque plan se lit à sa façon (00_DOC/02_REMPLISSAGE.md) :

========================  ================================================================
``table``                 factoriel : lecture des nœuds, images par symétrie, interpolation
                          multilinéaire si la grille du plan est plus lâche que la cible
``somme``                 étoile, décomposition : C(x) = Σ signe · C(x restreint aux
                          facteurs du terme), chaque terme interpolé dans sa table
``polynome``              composite centré, Box-Behnken : polynôme de degré 2
``smolyak``               grille creuse : polynôme de l'espace de la grille
``krigeage``              LHS, Halton, Sobol, krigeage, adaptatif
``co-krigeage``           multi-fidélité : BF krigée, plus l'écart HF − BF krigé
========================  ================================================================

Les symétries entrent partout de la même façon : chaque calcul vaut aussi en
ses images, au signe des coefficients près (clé ``symetries`` de l'export).
Un métamodèle les voit toutes ; une table les lit.

La cible est la **grille de référence** du fichier de remplissage, sur le
domaine complet (symétrique) : Mach × paramètres × variables libres. Un nœud
qu'aucun calcul n'atteint (exclusion, contrainte) reste ``NaN``.

Repère cartésien seulement : en polaire, φa est périodique et l'axe αt = 0
singulier, ce que ces modèles ne savent pas traiter ; pour les plans sur
grille, ``01_EXEMPLE/completer_table.py`` fait la complétion dans les deux repères.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path

import numpy as np

from cfd_doe.core.expression import compiler
from cfd_doe.core.metamodeles import (
    Krigeage,
    Polynome,
    indices_degre_total,
    indices_smolyak,
    plan_variance_maximale,
)
from cfd_doe.data.remplissage import ErreurRemplissage
from cfd_doe.engine.remplissage import (
    _DERIVEES,
    RECONSTRUCTIONS,
    ROLE_CALCUL,
    Contexte,
    PlanDOE,
    PointDOE,
    _derivees,
    _orbite,
    _quotas,
    _tirer_dans,
)

__all__ = [
    "GrilleCarree",
    "Mesures",
    "Tables",
    "ecrire_mesures",
    "ecrire_tables",
    "grille_carree",
    "lire_mesures",
    "lot_suivant",
    "reconstruire",
]

_CLE = 9  # arrondi des clés de nœud


# ---------------------------------------------------------------------------
# Les résultats
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Mesures:
    """Les résultats CFD d'un plan : une entrée par calcul, dans l'ordre des points."""

    points: tuple[PointDOE, ...]
    coefficients: dict[str, np.ndarray]

    def __post_init__(self) -> None:
        for nom, valeurs in self.coefficients.items():
            if len(valeurs) != len(self.points):
                raise ValueError(f"{nom} : {len(valeurs)} valeurs pour {len(self.points)} points")

    @property
    def noms(self) -> tuple[str, ...]:
        """Les coefficients mesurés."""
        return tuple(self.coefficients)

    def selection(self, garder: Callable[[PointDOE], bool]) -> Mesures:
        """Les mesures des points retenus par ``garder``."""
        indices = [i for i, p in enumerate(self.points) if garder(p)]
        return Mesures(
            tuple(self.points[i] for i in indices),
            {c: v[indices] for c, v in self.coefficients.items()},
        )

    def __add__(self, autre: Mesures) -> Mesures:
        return Mesures(
            self.points + autre.points,
            {c: np.concatenate([v, autre.coefficients[c]]) for c, v in self.coefficients.items()},
        )


#: Colonnes du fichier DOE qui ne sont pas des coefficients.
_COLONNES_DOE = frozenset(
    {"id", "role", "table", "sous_domaine", "fidelite", "alpha", "beta", "DM", "DN"}
)


def ecrire_mesures(mesures: Mesures, contexte: Contexte, chemin: Path) -> Path:
    """Le DOE avec ses résultats : les colonnes de ``doe.csv`` puis une par coefficient."""
    colonnes = ["role", "table", "sous_domaine", "fidelite", *contexte.colonnes, *mesures.noms]
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open("w", encoding="utf-8", newline="") as fichier:
        ecrivain = csv.writer(fichier, delimiter="\t", lineterminator="\n")
        ecrivain.writerow(colonnes)
        for i, p in enumerate(mesures.points):
            ecrivain.writerow(
                [
                    p.role,
                    p.table,
                    p.sous_domaine,
                    p.fidelite,
                    *(_nombre(p.valeurs[c]) for c in contexte.colonnes),
                    *(_nombre(float(mesures.coefficients[c][i])) for c in mesures.noms),
                ]
            )
    return chemin


def lire_mesures(
    chemin: Path, contexte: Contexte, coefficients: Sequence[str] | None = None
) -> Mesures:
    """Relit un DOE complété de ses résultats (tabulations).

    Les colonnes attendues sont celles de ``doe.csv`` (``role``, ``fidelite``
    facultative, Mach, paramètres, variables) ; les coefficients sont les
    colonnes nommées dans ``coefficients``, par défaut toutes les autres.
    """
    with chemin.open(encoding="utf-8", newline="") as fichier:
        lignes = list(csv.DictReader(fichier, delimiter="\t"))
    if not lignes:
        raise ErreurRemplissage(f"{chemin} : aucun résultat")
    entete = list(lignes[0])
    manquantes = [c for c in contexte.colonnes if c not in entete]
    if manquantes:
        raise ErreurRemplissage(f"{chemin} : colonne(s) absente(s) {', '.join(manquantes)}")
    if coefficients is None:
        coefficients = [c for c in entete if c not in _COLONNES_DOE and c not in contexte.colonnes]
    points = tuple(
        PointDOE(
            valeurs={c: float(ligne[c]) for c in contexte.colonnes},
            role=ligne.get("role") or ROLE_CALCUL,
            table=ligne.get("table", ""),
            sous_domaine=int(ligne.get("sous_domaine") or 0),
            fidelite=ligne.get("fidelite") or "",
        )
        for ligne in lignes
    )
    valeurs = {c: np.array([float(ligne[c] or "nan") for ligne in lignes]) for c in coefficients}
    return Mesures(points, valeurs)


# ---------------------------------------------------------------------------
# La grille cible
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GrilleCarree:
    """Produit cartésien des axes : la table que lit le simulateur."""

    axes: dict[str, tuple[float, ...]]

    @property
    def colonnes(self) -> tuple[str, ...]:
        """Mach, paramètres, variables libres."""
        return tuple(self.axes)

    @property
    def taille(self) -> int:
        """Nombre de nœuds."""
        return math.prod(len(a) for a in self.axes.values())

    def points(self) -> np.ndarray:
        """Les nœuds, (taille, colonnes), le dernier axe variant le plus vite."""
        maillage = np.meshgrid(*(np.asarray(a) for a in self.axes.values()), indexing="ij")
        return np.stack([m.ravel() for m in maillage], axis=-1)


def grille_carree(contexte: Contexte) -> GrilleCarree:
    """La grille de référence sur le domaine complet : Mach × paramètres × variables libres."""
    axes: dict[str, tuple[float, ...]] = {}
    if contexte.machs:
        axes["mach"] = tuple(contexte.machs)
    for p in contexte.parametres:
        axes[p.nom] = p.niveaux
    for v in contexte.libres:
        axes[v] = contexte.niveaux[v]
    return GrilleCarree(axes)


# ---------------------------------------------------------------------------
# Symétries
# ---------------------------------------------------------------------------


#: Pour chaque symétrie : les variables qu'elle retourne, le signe de chaque coefficient.
Signes = list[tuple[list[str], np.ndarray]]


def _signes(contexte: Contexte, noms: Sequence[str]) -> Signes:
    """Pour chaque symétrie : variables retournées, signe de chaque coefficient."""
    return [
        (
            list(s["variables"]),
            np.array([-1.0 if c in s["coefficients"] else 1.0 for c in noms]),
        )
        for s in contexte.symetries
    ]


def _avec_images(
    signes_symetries: Signes, lignes: np.ndarray, y: np.ndarray, colonnes: Sequence[str]
) -> tuple[np.ndarray, np.ndarray]:
    """Ajoute les images de chaque point (``lignes`` : (n, colonnes), ``y`` : (n, m)).

    Une image confondue avec un point déjà présent n'est pas ajoutée : sur un
    plan de symétrie, le point est sa propre image.
    """
    x_tout, y_tout = [lignes], [y]
    for variables, signes in signes_symetries:
        image = lignes.copy()
        for v in variables:
            if v in colonnes:
                image[:, colonnes.index(v)] *= -1.0
        x_tout.append(image)
        y_tout.append(y * signes[None, :])
    x = np.vstack(x_tout)
    yy = np.vstack(y_tout)
    _, uniques = np.unique(np.round(x, _CLE), axis=0, return_index=True)
    uniques.sort()
    return x[uniques], yy[uniques]


# ---------------------------------------------------------------------------
# Reconstruction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tables:
    """Les tables reconstruites d'un plan."""

    plan: PlanDOE
    grille: GrilleCarree
    valeurs: dict[str, np.ndarray]
    #: Rôle (« controle », « test ») → coefficient → prédiction − mesure à ces points.
    ecarts: dict[str, dict[str, np.ndarray]] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    _exclus: np.ndarray | None = None

    @property
    def methode(self) -> str:
        """Comment la table a été obtenue."""
        return RECONSTRUCTIONS[self.plan.reconstruction]

    @property
    def exclus(self) -> int:
        """Nœuds écartés par les exclusions du fichier de remplissage (laissés vides)."""
        return int(self._exclus.sum()) if self._exclus is not None else 0

    @property
    def trous(self) -> int:
        """Nœuds sans valeur (NaN) pour au moins un coefficient."""
        if not self.valeurs:
            return 0
        pile = np.vstack(list(self.valeurs.values()))
        return int(np.isnan(pile).any(axis=0).sum())


def reconstruire(
    plan: PlanDOE,
    contexte: Contexte,
    mesures: Mesures,
    grille: GrilleCarree | None = None,
    *,
    portees_communes: bool = False,
) -> Tables:
    """Les tables du plan sur ``grille`` (par défaut la grille de référence complète).

    ``portees_communes`` : un krigeage pour tous les coefficients (une
    factorisation, environ m fois plus rapide) au lieu d'un par coefficient,
    au prix de portées de compromis entre coefficients plus ou moins réguliers.
    """
    if contexte.reduction.repere != "cartesien":
        raise ErreurRemplissage(
            "reconstruction : repère cartésien seulement (polaire : completer_table.py "
            "pour les plans sur grille)"
        )
    grille = grille or grille_carree(contexte)
    noms = list(mesures.noms)
    if not noms:
        raise ErreurRemplissage("reconstruction : aucun coefficient dans les mesures")
    modele = _MODELES[plan.reconstruction](plan, contexte, mesures, portees_communes)

    cibles = _completer(contexte, grille.colonnes, grille.points())
    predites = modele.predire(cibles)
    # Un nœud exclu par l'utilisateur n'est pas demandé : trou, quelle que soit la méthode
    # (un métamodèle y extrapolerait sans qu'aucun calcul ne le contrôle).
    exclus = _exclus(contexte, cibles)
    predites[exclus] = np.nan
    valeurs = {c: predites[:, j] for j, c in enumerate(noms)}
    notes = list(dict.fromkeys(modele.notes))
    manquants = int((np.isnan(predites).any(axis=1) & ~exclus).sum())
    if manquants:
        notes.append(
            f"{manquants} nœud(s) sans calcul ni image (contrainte, plan incomplet) : laissés vides"
        )

    ecarts: dict[str, dict[str, np.ndarray]] = {}
    for role in ("controle", "test"):
        verif = mesures.selection(_du_role(role))
        if verif.points:
            lignes = np.array([[p.valeurs[c] for c in contexte.colonnes] for p in verif.points])
            prevu = modele.predire(lignes)
            ecarts[role] = {c: prevu[:, j] - verif.coefficients[c] for j, c in enumerate(noms)}
    return Tables(plan, grille, valeurs, ecarts, tuple(_regrouper(notes)), exclus)


def _exclus(contexte: Contexte, lignes: np.ndarray) -> np.ndarray:
    """Les nœuds que les exclusions du fichier de remplissage écartent."""
    textes = contexte.remplissage.exclure
    if not textes:
        return np.zeros(len(lignes), dtype=bool)
    noms = frozenset(contexte.colonnes) | _DERIVEES[contexte.reduction.repere]
    conditions = [compiler(texte, noms) for texte in textes]
    exclus = np.zeros(len(lignes), dtype=bool)
    for i, ligne in enumerate(lignes):
        valeurs = dict(zip(contexte.colonnes, (float(x) for x in ligne)))
        valeurs.update(_derivees(contexte.reduction.repere, valeurs))
        exclus[i] = any(condition(valeurs) for condition in conditions)
    return exclus


def _regrouper(notes: Sequence[str]) -> list[str]:
    """« [Mach 2] texte » répété par condition → « texte (Mach 2, Mach 3) »."""
    groupes: dict[str, list[str]] = {}
    for note in notes:
        if note.startswith("[") and "] " in note:
            condition, texte = note[1:].split("] ", 1)
            groupes.setdefault(texte, []).append(condition)
        else:
            groupes.setdefault(note, [])
    return [
        f"{texte} ({'; '.join(conditions)})" if conditions else texte
        for texte, conditions in groupes.items()
    ]


def _du_role(role: str) -> Callable[[PointDOE], bool]:
    """Les points de vérification d'un rôle, haute fidélité (ou mono-fidélité)."""
    return lambda p: p.role == role and p.fidelite != "BF"


def _completer(contexte: Contexte, colonnes: Sequence[str], lignes: np.ndarray) -> np.ndarray:
    """Passe des colonnes de la grille à celles du contexte (variables figées à la référence)."""
    sortie = np.empty((len(lignes), len(contexte.colonnes)))
    for j, c in enumerate(contexte.colonnes):
        sortie[:, j] = lignes[:, colonnes.index(c)] if c in colonnes else contexte.reference[c]
    return sortie


class _Modele:
    """Un prédicteur sur les colonnes du contexte : (n, colonnes) → (n, coefficients)."""

    notes: list[str]

    def predire(self, lignes: np.ndarray) -> np.ndarray:
        raise NotImplementedError


def _calculs(mesures: Mesures, fidelite: str | None = None) -> Mesures:
    return mesures.selection(
        lambda p: p.role == ROLE_CALCUL and (fidelite is None or p.fidelite == fidelite)
    )


def _matrice(mesures: Mesures, contexte: Contexte) -> tuple[np.ndarray, np.ndarray]:
    x = np.array([[p.valeurs[c] for c in contexte.colonnes] for p in mesures.points])
    y = np.column_stack([mesures.coefficients[c] for c in mesures.noms])
    return x.reshape(len(mesures.points), len(contexte.colonnes)), y


# --- tables et sommes --------------------------------------------------------


class _Somme(_Modele):
    """Σ signe · C(x restreint aux facteurs du terme), chaque terme interpolé dans sa table."""

    def __init__(
        self, plan: PlanDOE, contexte: Contexte, mesures: Mesures, communes: bool = False
    ) -> None:
        self.c, self.plan, self.notes = contexte, plan, []
        calculs = _calculs(mesures)
        x, y = _matrice(calculs, contexte)
        x, y = _avec_images(_signes(contexte, mesures.noms), x, y, list(contexte.colonnes))
        self.connus = {tuple(np.round(ligne, _CLE) + 0.0): y[i] for i, ligne in enumerate(x)}
        self.m = y.shape[1]
        assert plan.niveaux is not None
        self.niveaux = plan.niveaux
        self.nominal = {p.nom: p.nominal for p in contexte.parametres}
        self.termes = plan.termes
        self._tables: dict[tuple[float | None, tuple[str, ...]], np.ndarray] = {}

    def _reference(self, f: str) -> float:
        return self.nominal[f] if f in self.nominal else self.c.reference[f]

    def _table(self, mach: float | None, facteurs: tuple[str, ...]) -> np.ndarray:
        cle_table = (mach, facteurs)
        if cle_table not in self._tables:
            axes = [self.niveaux[f] for f in facteurs]
            table = np.full((*(len(a) for a in axes), self.m), np.nan)
            for indices in product(*(range(len(a)) for a in axes)):
                valeurs = {f: axes[j][i] for j, (f, i) in enumerate(zip(facteurs, indices))}
                noeud = []
                for col in self.c.colonnes:
                    if col == "mach":
                        noeud.append(mach)
                    else:
                        noeud.append(valeurs.get(col, self._reference(col)))
                cle = tuple(np.round(np.array(noeud, dtype=float), _CLE) + 0.0)
                if cle in self.connus:
                    table[indices] = self.connus[cle]
            self._tables[cle_table] = table
        return self._tables[cle_table]

    def predire(self, lignes: np.ndarray) -> np.ndarray:
        colonnes = list(self.c.colonnes)
        sortie = np.zeros((len(lignes), self.m))
        machs = lignes[:, colonnes.index("mach")] if "mach" in colonnes else None
        for mach in self.c.machs or (None,):
            masque = (
                np.ones(len(lignes), bool)
                if machs is None or mach is None
                else np.isclose(machs, mach)
            )
            if not masque.any():
                continue
            sous = lignes[masque]
            total = np.zeros((len(sous), self.m))
            for signe, facteurs in self.termes:
                if not facteurs:
                    total += signe * self._table(mach, facteurs)[None, :]
                    continue
                q = np.column_stack([sous[:, colonnes.index(f)] for f in facteurs])
                total += signe * _multilineaire(
                    [np.asarray(self.niveaux[f]) for f in facteurs], self._table(mach, facteurs), q
                )
            sortie[masque] = total
        if machs is not None:
            hors = ~np.isin(np.round(machs, _CLE), np.round(self.c.machs, _CLE))
            sortie[hors] = np.nan
        return sortie


def _multilineaire(axes: Sequence[np.ndarray], table: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Interpolation multilinéaire de ``table`` (axes…, m) aux points ``q`` (n, len(axes)).

    Hors des axes : valeur du bord. Un sommet de poids nul ne propage pas son NaN.
    """
    n, m = len(q), table.shape[-1]
    indices, poids = [], []
    for j, axe in enumerate(axes):
        if len(axe) == 1:
            indices.append(np.zeros(n, int))
            poids.append(np.zeros(n))
            continue
        x = np.clip(q[:, j], axe[0], axe[-1])
        i = np.clip(np.searchsorted(axe, x, side="right") - 1, 0, len(axe) - 2)
        indices.append(i)
        poids.append((x - axe[i]) / (axe[i + 1] - axe[i]))
    sortie = np.zeros((n, m))
    for coin in product((0, 1), repeat=len(axes)):
        w = np.ones(n)
        index = []
        for j, bit in enumerate(coin):
            w = w * (poids[j] if bit else 1.0 - poids[j])
            index.append(np.minimum(indices[j] + bit, table.shape[j] - 1))
        valeurs = table[tuple(index)]
        sortie += np.where(w[:, None] > 0, w[:, None] * np.nan_to_num(valeurs), 0.0)
        sortie[(w > 0) & np.isnan(valeurs).any(-1)] = np.nan
    return sortie


# --- métamodèles ------------------------------------------------------------


class _ParCondition(_Modele):
    """Un métamodèle par Mach et par combinaison de paramètres discrets, sur les facteurs continus."""

    def __init__(
        self, plan: PlanDOE, contexte: Contexte, mesures: Mesures, communes: bool = False
    ) -> None:
        self.c, self.plan, self.notes = contexte, plan, []
        self.communes = communes
        self.signes = _signes(contexte, mesures.noms)
        continus = [p for p in contexte.parametres if p.continu]
        self.discrets = [p.nom for p in contexte.parametres if not p.continu]
        self.cles = [*(["mach"] if contexte.machs else []), *self.discrets]
        self.facteurs = [*contexte.libres, *(p.nom for p in continus)]
        self.plages = {
            **{v: (contexte.boite[v].bas, contexte.boite[v].largeur) for v in contexte.libres},
            **{p.nom: (p.plage.bas, p.plage.largeur) for p in continus},
        }
        self.modeles: dict[tuple[float, ...], Callable[[np.ndarray], np.ndarray]] = {}
        self.m = len(mesures.noms)
        colonnes = list(contexte.colonnes)
        for cle in dict.fromkeys(self._cle(p.valeurs) for p in mesures.points):
            sous = mesures.selection(self._de_la_condition(cle))
            if any(p.role == ROLE_CALCUL for p in sous.points):
                self.modeles[cle] = self.ajuster(sous, colonnes)

    def _condition(self, mesures: Mesures) -> str:
        """« Mach 2, moteur = 1 » : la condition d'un groupe de mesures."""
        if not mesures.points:
            return "?"
        valeurs = mesures.points[0].valeurs
        morceaux = [
            f"Mach {valeurs['mach']:g}" if k == "mach" else f"{k} = {valeurs[k]:g}"
            for k in self.cles
        ]
        return ", ".join(morceaux) or "unique"

    def _de_la_condition(self, cle: tuple[float, ...]) -> Callable[[PointDOE], bool]:
        """Le filtre des points d'une condition (Mach, paramètres discrets)."""
        return lambda p: self._cle(p.valeurs) == cle

    def _cle(self, valeurs: Mapping[str, float]) -> tuple[float, ...]:
        return tuple(round(float(valeurs[k]), _CLE) + 0.0 for k in self.cles)

    def unites(self, lignes: np.ndarray, colonnes: Sequence[str]) -> np.ndarray:
        """Les facteurs continus de ``lignes``, ramenés dans [0, 1]."""
        return np.column_stack(
            [
                (lignes[:, colonnes.index(f)] - self.plages[f][0]) / (self.plages[f][1] or 1.0)
                for f in self.facteurs
            ]
        )

    def donnees(self, mesures: Mesures, colonnes: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
        """Calculs et leurs images : (unités, coefficients)."""
        x, y = _matrice(mesures, self.c)
        x, y = _avec_images(self.signes, x, y, colonnes)
        return self.unites(x, colonnes), y

    def ajuster(
        self, mesures: Mesures, colonnes: Sequence[str]
    ) -> Callable[[np.ndarray], np.ndarray]:
        raise NotImplementedError

    def predire(self, lignes: np.ndarray) -> np.ndarray:
        colonnes = list(self.c.colonnes)
        sortie = np.full((len(lignes), self.m), np.nan)
        cles = (
            [
                tuple(round(float(x), _CLE) + 0.0 for x in ligne)
                for ligne in lignes[:, [colonnes.index(k) for k in self.cles]]
            ]
            if self.cles
            else [()] * len(lignes)
        )
        groupes: dict[tuple[float, ...], list[int]] = {}
        for i, cle in enumerate(cles):
            groupes.setdefault(cle, []).append(i)
        for cle, indices in groupes.items():
            if cle in self.modeles:
                sortie[indices] = self.modeles[cle](self.unites(lignes[indices], colonnes))
        return sortie


class _Polynomial(_ParCondition):
    def ajuster(
        self, mesures: Mesures, colonnes: Sequence[str]
    ) -> Callable[[np.ndarray], np.ndarray]:
        u, y = self.donnees(_calculs(mesures), colonnes)
        k = len(self.facteurs)
        if self.plan.reconstruction == "smolyak":
            niveau = int(self.plan.spec.options.get("niveau") or 2)
            indices = indices_smolyak(k, niveau)
        else:
            indices = indices_degre_total(k, 2)
        polynomes = [Polynome(indices).ajuster(2 * u - 1, y[:, j]) for j in range(y.shape[1])]
        if polynomes and polynomes[0].rang < len(indices):
            self.notes.append(
                f"[{self._condition(mesures)}] polynôme sous-déterminé (base de {len(indices)} "
                "termes, rang inférieur) : des points du plan manquent, écartés par "
                "« exclure » ? Solution de norme minimale, à ne pas croire loin des calculs"
            )
        return lambda q: np.column_stack([p.predire(2 * q - 1) for p in polynomes])


class _Krigeage(_ParCondition):
    def ajuster(
        self, mesures: Mesures, colonnes: Sequence[str]
    ) -> Callable[[np.ndarray], np.ndarray]:
        u, y = self.donnees(_calculs(mesures), colonnes)
        return _krigeage(u, y, self.communes)


class _CoKrigeage(_ParCondition):
    def ajuster(
        self, mesures: Mesures, colonnes: Sequence[str]
    ) -> Callable[[np.ndarray], np.ndarray]:
        u_bf, y_bf = self.donnees(_calculs(mesures, "BF"), colonnes)
        basse = _krigeage(u_bf, y_bf, self.communes)
        u_hf, y_hf = self.donnees(_calculs(mesures, "HF"), colonnes)
        correction = _krigeage(u_hf, y_hf - basse(u_hf), self.communes)
        return lambda q: basse(q) + correction(q)


def _krigeage(u: np.ndarray, y: np.ndarray, communes: bool) -> Callable[[np.ndarray], np.ndarray]:
    """Un krigeage multi-sorties (portées communes) ou un par coefficient."""
    if communes:
        commun = Krigeage().ajuster(u, y)
        return lambda q: np.asarray(commun.predire(q))
    modeles = [Krigeage().ajuster(u, y[:, j]) for j in range(y.shape[1])]
    return lambda q: np.column_stack([np.asarray(k.predire(q)) for k in modeles])


_MODELES: dict[str, Callable[[PlanDOE, Contexte, Mesures, bool], _Modele]] = {
    "table": _Somme,
    "somme": _Somme,
    "polynome": _Polynomial,
    "smolyak": _Polynomial,
    "krigeage": _Krigeage,
    "co-krigeage": _CoKrigeage,
}


# ---------------------------------------------------------------------------
# Enrichissement adaptatif
# ---------------------------------------------------------------------------


def lot_suivant(
    plan: PlanDOE,
    contexte: Contexte,
    mesures: Mesures,
    n: int,
    *,
    candidats: int = 600,
    graine: int = 0,
) -> list[PointDOE]:
    """Le lot d'enrichissement d'un plan à krigeage : ``n`` points par condition.

    Les portées sont réestimées sur les résultats (communes aux coefficients,
    par Mach) ; chaque point est placé où la variance de
    prédiction est maximale, compte tenu des calculs déjà faits et de leurs
    images. Les candidats sont tirés dans les sous-domaines.
    """
    modele = _Krigeage(plan, contexte, mesures, True)
    continus = [p for p in contexte.parametres if p.continu]
    colonnes = list(contexte.colonnes)
    lot: list[PointDOE] = []
    quotas, _, _ = _quotas(contexte, candidats, 0.25)
    for cle in modele.modeles:
        fixes = dict(zip(modele.cles, cle))
        deja = mesures.selection(modele._de_la_condition(cle))
        u_deja, _ = modele.donnees(_calculs(deja), colonnes)
        portees = _portees(modele, deja, colonnes)
        tires: list[tuple[dict[str, float], dict[str, float]]] = []
        for sd, quota in quotas:
            tires += _tirer_dans(contexte, sd, quota, continus, "halton", graine + sd.numero, 1)
        orbites = []
        for angles, params in tires:
            images = _orbite(contexte, angles)
            lignes = np.array(
                [
                    [
                        {**image, **params, **fixes}.get(c, contexte.reference.get(c, 0.0))
                        for c in colonnes
                    ]
                    for image in images
                ]
            )
            orbites.append(modele.unites(lignes, colonnes))
        choisis = plan_variance_maximale(orbites, n, portees, connus=u_deja)
        for i in choisis:
            angles, params = tires[i]
            nominaux = {p.nom: p.nominal for p in contexte.parametres}
            valeurs = {**nominaux, **params, **fixes, **angles}
            numero = contexte.placer(angles) or 0
            lot.append(PointDOE(valeurs, ROLE_CALCUL, "enrichissement", numero))
    return lot


def _portees(modele: _Krigeage, mesures: Mesures, colonnes: Sequence[str]) -> np.ndarray:
    u, y = modele.donnees(_calculs(mesures), colonnes)
    krigeage = Krigeage().ajuster(u, y)
    assert krigeage.portees is not None
    return krigeage.portees


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------


def _nombre(x: float) -> str:
    if isinstance(x, float) and math.isnan(x):
        return "nan"
    return f"{round(float(x), 10) + 0.0:.10g}"


def ecrire_tables(
    tables: Tables, dossier: Path, coefficients: Iterable[str] | None = None
) -> list[Path]:
    """Une table par coefficient, ``<coef>.csv`` séparé par des tabulations.

    Colonnes : Mach, paramètres, variables libres, puis le coefficient ; une
    ligne par nœud de la grille, le dernier axe variant le plus vite.
    """
    dossier.mkdir(parents=True, exist_ok=True)
    points = tables.grille.points()
    fichiers = []
    for coef in coefficients or tables.valeurs:
        chemin = dossier / f"{coef}.csv"
        with chemin.open("w", encoding="utf-8", newline="") as fichier:
            ecrivain = csv.writer(fichier, delimiter="\t", lineterminator="\n")
            ecrivain.writerow([*tables.grille.colonnes, coef])
            for ligne, valeur in zip(points, tables.valeurs[coef]):
                ecrivain.writerow([*(_nombre(float(x)) for x in ligne), _nombre(float(valeur))])
        fichiers.append(chemin)
    return fichiers
