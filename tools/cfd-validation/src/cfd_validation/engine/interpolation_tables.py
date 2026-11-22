"""Le test d'interpolation de table : appeler le code entre les nœuds, vérifier l'interpolation.

Pour chaque table, deux familles de points, chacune un **groupe** du rapport :

1. **par axe** (groupe ``alpha``, ``mach``…) : l'axe placé dans chacune de ses
   mailles à chaque ``fraction`` (¼, ½, ¾ par défaut), les autres axes sur
   **tous** leurs nœuds. Vérifie l'interpolation le long de l'axe, maille par
   maille — une recherche de maille décalée, un poids faux se localisent ;
2. **centres** (dès deux axes) : le centre de chaque maille de la table, tous
   les axes à mi-maille. Les 2ᵈ coins y pèsent autant : c'est là que se voit un
   couplage faux entre axes (une somme d'interpolations 1D au lieu d'une
   interpolation multilinéaire), invisible sur les groupes par axe.

La valeur **attendue** est l'interpolation multilinéaire de la table
(:func:`cfd_validation.core.bornes.interpoler`, point dans la grille : la
consigne hors bornes n'y joue pas). Le comportement **observé** de chaque groupe
est établi en comparant la sonde à l'attendu et aux coins de la maille :
« linéaire », « palier » (le code rend la valeur d'un coin : plus proche nœud,
nœud bas…), « indiscernable » (mailles plates), « ni l'un ni l'autre » ou
« sonde non atteinte ».

Tolérance : celle de la table si elle en déclare une, sinon
``TOLERANCE_INTERPOLATION`` (l'oracle refait le calcul du code, pas forcément
dans le même ordre d'opérations : quelques ULP).
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from cfd_validation.core import statuts as st
from cfd_validation.core.bornes import EXTRAPOLE, interpoler
from cfd_validation.core.ecarts import comparer_numerique
from cfd_validation.core.mailles import points_mailles, verifier_fractions
from cfd_validation.core.tolerance import ORIGINE_DEFAUT, Tolerance
from cfd_validation.data.tables import ErreurTable, TableReference
from cfd_validation.engine.bornes_tables import _json, _nanmax
from cfd_validation.engine.environnement import (
    Empreinte,
    Environnement,
    capturer_environnement,
    empreinte_table,
)
from cfd_validation.engine.injection import appeler, verifier_defauts
from cfd_validation.engine.lecture_tables import Evaluateur

__all__ = [
    "CENTRES",
    "FRACTIONS_DEFAUT",
    "IDENTIFIANT_DEFAUT",
    "LINEAIRE",
    "PALIER",
    "TOLERANCE_INTERPOLATION",
    "BilanGroupe",
    "BilanInterpolation",
    "Groupe",
    "ResultatInterpolationTables",
    "tolerance_interpolation",
    "verifier_interpolation",
]

IDENTIFIANT_DEFAUT = "INTERPOLATION-TABLES"
DESCRIPTION_DEFAUT = (
    "Le code, appelé entre les nœuds de chaque table, rend l'interpolation "
    "multilinéaire de la table : le long de chaque axe, et au centre des mailles."
)
#: Position des points dans chaque maille d'un axe.
FRACTIONS_DEFAUT: tuple[float, ...] = (0.25, 0.5, 0.75)
#: Nom du groupe des centres de maille.
CENTRES = "centres"
TOLERANCE_INTERPOLATION = Tolerance(
    rtol=1e-12, atol=1e-15, origine=ORIGINE_DEFAUT,
    justification=(
        "L'oracle refait l'interpolation Σ Π (1 − t | t)·V sur les coins de la maille ; "
        "le code peut ordonner autrement les opérations : quelques ULP."
    ),
)

#: Comportements observés d'un groupe.
LINEAIRE = "linéaire"
PALIER = "palier"
OBSERVE_INDISCERNABLE = "indiscernable"
OBSERVE_AUTRE = "ni l'un ni l'autre"
OBSERVE_NAN = "sonde non atteinte"


@dataclass(frozen=True)
class Groupe:
    """Une famille de points : les axes placés dans leurs mailles, les autres sur leurs nœuds."""

    nom: str
    mobiles: tuple[str, ...]

    @property
    def description(self) -> str:
        if self.nom == CENTRES:
            return "centre de chaque maille, tous les axes à mi-maille"
        return f"{self.mobiles[0]} dans ses mailles, les autres axes sur leurs nœuds"


@dataclass(frozen=True)
class BilanGroupe:
    groupe: Groupe
    tolerance: Tolerance
    n_points: int
    n_mailles: int
    n_identiques: int
    n_toleres: int
    n_echecs: int
    max_abs: float
    max_ulp: float
    observe: str
    mailles_en_echec: tuple[str, ...]

    @property
    def conforme(self) -> bool:
        return self.n_echecs == 0


@dataclass(frozen=True)
class BilanInterpolation:
    """Le résultat d'une table : une ligne de ``resultats`` par appel du code."""

    table: TableReference
    resultats: pd.DataFrame
    groupes: tuple[BilanGroupe, ...]
    entrees_pilotees: tuple[str, ...]
    empreinte: Empreinte

    @property
    def nom(self) -> str:
        return self.table.nom

    @property
    def n_valeurs(self) -> int:
        return len(self.resultats)

    @property
    def n_identiques(self) -> int:
        return sum(g.n_identiques for g in self.groupes)

    @property
    def n_toleres(self) -> int:
        return sum(g.n_toleres for g in self.groupes)

    @property
    def n_echecs(self) -> int:
        return sum(g.n_echecs for g in self.groupes)

    @property
    def conforme(self) -> bool:
        return self.n_echecs == 0

    @property
    def verdict(self) -> str:
        if not self.conforme:
            return "NON CONFORME"
        return "CONFORME — identique bit pour bit" if self.n_toleres == 0 else "CONFORME — dans la tolérance"

    def echecs(self) -> pd.DataFrame:
        return self.resultats.loc[~self.resultats["conforme"]]

    def resume(self) -> dict[str, Any]:
        t = self.table
        return {
            "nom": t.nom,
            "description": t.description,
            "forme": list(t.forme),
            "sonde": t.sonde,
            "inversion": t.vers_entrees is not None,
            "fixes": {k: _json(v) for k, v in t.fixes.items()},
            "sha256_table": self.empreinte.sha256,
            "groupes": [
                {
                    "groupe": g.groupe.nom, "axes": list(g.groupe.mobiles), "observe": g.observe,
                    "tolerance": {"rtol": g.tolerance.rtol, "atol": g.tolerance.atol,
                                  "origine": g.tolerance.origine, "justification": g.tolerance.justification},
                    "points": g.n_points, "mailles": g.n_mailles, "echecs": g.n_echecs,
                    "mailles_en_echec": list(g.mailles_en_echec),
                    "max_abs_ecart": _json(g.max_abs), "max_ulp": _json(g.max_ulp), "conforme": g.conforme,
                }
                for g in self.groupes
            ],
            "appels": self.n_valeurs,
            "identiques": self.n_identiques,
            "tolerees": self.n_toleres,
            "echecs": self.n_echecs,
            "conforme": self.conforme,
            "verdict": self.verdict,
        }


@dataclass(frozen=True)
class ResultatInterpolationTables:
    """Toutes les tables d'un test d'interpolation."""

    identifiant: str
    description: str
    environnement: Environnement
    metadonnees: Mapping[str, str]
    defauts: Mapping[str, Any]
    fractions: tuple[float, ...]
    centres: bool
    tables: tuple[BilanInterpolation, ...]
    fichiers: tuple[Path, ...] = field(default=())

    @property
    def conforme(self) -> bool:
        return all(b.conforme for b in self.tables)

    @property
    def bit_identique(self) -> bool:
        return self.conforme and all(b.n_toleres == 0 for b in self.tables)

    @property
    def verdict(self) -> str:
        if not self.conforme:
            return "NON CONFORME"
        return "CONFORME — identique bit pour bit" if self.bit_identique else "CONFORME — dans les tolérances"

    @property
    def n_appels(self) -> int:
        return sum(b.n_valeurs for b in self.tables)

    @property
    def motifs_non_conformite(self) -> list[str]:
        motifs = []
        for b in self.tables:
            for g in b.groupes:
                if not g.conforme:
                    k = len(g.mailles_en_echec)
                    motifs.append(f"{b.nom} {g.groupe.nom} : attendu {LINEAIRE}, observé {g.observe} "
                                  f"({g.n_echecs}/{g.n_points} hors tolérance, {k}/{g.n_mailles} maille(s))")
        return motifs

    def bilan(self, nom: str) -> BilanInterpolation:
        for b in self.tables:
            if b.nom == nom:
                return b
        raise KeyError(nom)

    def resume(self) -> dict[str, Any]:
        env = self.environnement
        return {
            "controle": "interpolation des tables",
            "identifiant": self.identifiant,
            "description": self.description,
            "verdict": self.verdict,
            "conforme": self.conforme,
            "environnement": {
                "date": env.date, "hote": env.hote, "utilisateur": env.utilisateur,
                "systeme": env.systeme, "python": env.python, "versions": dict(env.versions),
            },
            "metadonnees": dict(self.metadonnees),
            "defauts": {k: _json(v) for k, v in self.defauts.items()},
            "fractions": list(self.fractions),
            "centres": self.centres,
            "appels": self.n_appels,
            "tables": [b.resume() for b in self.tables],
            "motifs_non_conformite": self.motifs_non_conformite,
            "fichiers": [str(f) for f in self.fichiers],
        }


# ---------------------------------------------------------------------------
# Plan d'appels
# ---------------------------------------------------------------------------


def groupes_table(table: TableReference, centres: bool = True) -> list[Groupe]:
    """Un groupe par axe, puis les centres (dès deux axes, si demandés)."""
    groupes = [Groupe(a, (a,)) for a in table.noms_axes]
    if centres and len(table.noms_axes) > 1:
        groupes.append(Groupe(CENTRES, table.noms_axes))
    return groupes


def _positions(table: TableReference, groupe: Groupe, fractions: Sequence[float]) -> list[tuple[np.ndarray, np.ndarray, np.ndarray | None]]:
    """Par axe, ``(valeurs, indice, fraction)`` : nœuds (fraction None) ou points de maille."""
    positions: list[tuple[np.ndarray, np.ndarray, np.ndarray | None]] = []
    for a, g in table.axes.items():
        if a in groupe.mobiles:
            x, i, t = points_mailles(g, (0.5,) if groupe.nom == CENTRES else fractions)
            positions.append((x, i, t))
        else:
            positions.append((g, np.arange(len(g)), None))
    return positions


def _points_groupe(table: TableReference, groupe: Groupe, fractions: Sequence[float]) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Points du groupe en ordre de lecture Fortran (premier axe le plus rapide).

    Rend ``(df, indices, poids)`` : ``indices[n, k]`` est l'indice du nœud (axe
    fixe) ou du nœud bas de la maille (axe mobile), ``poids[n, k]`` la fraction
    (NaN sur un axe fixe).
    """
    positions = _positions(table, groupe, fractions)
    rangs = [np.arange(len(x)) for x, _, _ in positions]
    # itertools.product fait varier le dernier le plus vite : on renverse pour l'ordre Fortran.
    combinaisons = np.array([tuple(reversed(p)) for p in itertools.product(*reversed(rangs))], dtype=np.int64)
    d = len(positions)
    coords = np.empty((len(combinaisons), d))
    indices = np.empty((len(combinaisons), d), dtype=np.int64)
    poids = np.full((len(combinaisons), d), np.nan)
    for k, (x, i, t) in enumerate(positions):
        r = combinaisons[:, k]
        coords[:, k] = x[r]
        indices[:, k] = i[r]
        if t is not None:
            poids[:, k] = t[r]
    return pd.DataFrame(coords, columns=list(table.noms_axes)), indices, poids


def _maille(indices: np.ndarray, poids: np.ndarray) -> list[str]:
    """``"3-4"`` (base 1, comme le Fortran) par axe mobile, séparés d'une espace."""
    mobiles = ~np.isnan(poids[0])
    return [" ".join(f"{i + 1}-{i + 2}" for i in ligne[mobiles]) for ligne in indices]


def _coins(table: TableReference, indices: np.ndarray, poids: np.ndarray) -> np.ndarray:
    """Valeurs de la table aux 2ᵏ coins de la maille de chaque point (k axes mobiles)."""
    mobiles = np.flatnonzero(~np.isnan(poids[0]))
    colonnes = []
    for coin in itertools.product((0, 1), repeat=len(mobiles)):
        idx = indices.copy()
        for k, b in zip(mobiles, coin):
            idx[:, k] += b
        colonnes.append(table.valeurs[tuple(idx.T)])
    return np.stack(colonnes, axis=1)


def _observe(code: np.ndarray, attendu: np.ndarray, coins: np.ndarray, tol: Tolerance) -> str:
    if np.isnan(code).any():
        return OBSERVE_NAN
    lin = bool(np.all(np.abs(code - attendu) <= tol.seuil(attendu)))
    pal = bool(np.all(np.any(np.abs(code[:, None] - coins) <= tol.seuil(coins), axis=1)))
    if lin and pal:
        return OBSERVE_INDISCERNABLE
    return LINEAIRE if lin else PALIER if pal else OBSERVE_AUTRE


def tolerance_interpolation(table: TableReference) -> Tolerance:
    """Celle de la table si elle en déclare une, sinon ``TOLERANCE_INTERPOLATION``."""
    if table.rtol is not None or table.atol is not None:
        return table.tolerance
    return TOLERANCE_INTERPOLATION


def _verifier_table(
    table: TableReference, evaluer: Evaluateur, defauts: Mapping[str, Any],
    fractions: Sequence[float], centres: bool,
) -> BilanInterpolation:
    verifier_defauts(table, defauts)
    groupes = groupes_table(table, centres)
    blocs, tous_indices, tous_poids = [], [], []
    for numero, g in enumerate(groupes):
        pts, indices, poids = _points_groupe(table, g, fractions)
        mobiles = list(g.mobiles)
        pts.insert(0, "fraction", np.nanmax(poids[:, [table.noms_axes.index(a) for a in mobiles]], axis=1))
        pts.insert(0, "maille", _maille(indices, poids))
        pts.insert(0, "point", np.arange(len(pts)))
        pts.insert(0, "groupe", g.nom)
        pts.insert(0, "num_groupe", numero)
        blocs.append(pts)
        tous_indices.append(indices)
        tous_poids.append(poids)
    cles = pd.concat(blocs, ignore_index=True)
    axes_df = cles[list(table.noms_axes)].reset_index(drop=True)
    appel = appeler(table, evaluer, defauts, axes_df)
    code = appel.code

    d = len(table.noms_axes)
    # Dans la grille, la règle de bord ne joue pas ; « extrapole » laisse t tel quel.
    attendu = interpoler(table.valeurs, table.grilles, axes_df.to_numpy(dtype=np.float64), [(EXTRAPOLE, EXTRAPOLE)] * d)
    tol = tolerance_interpolation(table)

    resultats = cles.drop(columns="num_groupe").copy()
    for k in appel.entrees.columns:
        if k not in resultats.columns:
            resultats[k] = appel.entrees[k].to_numpy()
    e = comparer_numerique(attendu, code, tol)
    resultats["valeur_ATTENDUE"] = attendu
    resultats["valeur_CODE"] = code
    resultats["ecart"] = e.ecart
    resultats["ulp"] = e.ulp
    resultats["marge"] = e.marge
    resultats["statut"] = [st.NOMS[int(s)] for s in e.statut]
    resultats["conforme"] = (e.statut < st.ECART).astype(bool)

    bilans = []
    for numero, g in enumerate(groupes):
        dans = (cles["num_groupe"] == numero).to_numpy()
        statut = e.statut[dans]
        mailles = resultats.loc[dans, "maille"].to_numpy()
        en_echec = statut >= st.ECART
        coins = _coins(table, tous_indices[numero], tous_poids[numero])
        bilans.append(BilanGroupe(
            groupe=g, tolerance=tol, n_points=int(dans.sum()), n_mailles=len(set(mailles)),
            n_identiques=int((statut == st.IDENTIQUE).sum()), n_toleres=int((statut == st.TOLERE).sum()),
            n_echecs=int(en_echec.sum()),
            max_abs=_nanmax(np.abs(e.ecart[dans])), max_ulp=_nanmax(e.ulp[dans]),
            observe=_observe(code[dans], attendu[dans], coins, tol),
            mailles_en_echec=tuple(dict.fromkeys(mailles[en_echec])),
        ))

    return BilanInterpolation(
        table=table, resultats=resultats, groupes=tuple(bilans),
        entrees_pilotees=appel.pilotees, empreinte=empreinte_table(table.table_plate()),
    )


def verifier_interpolation(
    tables: Sequence[TableReference],
    evaluer: Evaluateur,
    defauts: Mapping[str, Any],
    *,
    fractions: Sequence[float] = FRACTIONS_DEFAUT,
    centres: bool = True,
    identifiant: str = IDENTIFIANT_DEFAUT,
    description: str | None = None,
    metadonnees: Mapping[str, Any] | None = None,
) -> ResultatInterpolationTables:
    """Appelle le code entre les nœuds de chaque table ; aucun fichier n'est écrit.

    ``fractions`` : positions dans chaque maille des points des groupes par axe ;
    ``centres`` : ajoute le groupe des centres de maille (tables d'au moins deux axes).
    """
    if not tables:
        raise ErreurTable("aucune table à vérifier")
    if not defauts:
        raise ErreurTable("vecteur des défauts vide : il donne la valeur de chaque entrée du modèle")
    try:
        fractions = verifier_fractions(fractions)
    except ValueError as erreur:
        raise ErreurTable(str(erreur)) from None
    vus: dict[str, str] = {}
    for t in tables:
        if not isinstance(t, TableReference):
            raise ErreurTable(f"TableReference attendue, reçu {type(t).__name__}")
        if t.nom.lower() in vus:
            raise ErreurTable(f"deux tables nommées {vus[t.nom.lower()]!r} et {t.nom!r}")
        vus[t.nom.lower()] = t.nom
    defauts = dict(defauts)
    bilans = tuple(_verifier_table(t, evaluer, defauts, fractions, centres) for t in tables)
    return ResultatInterpolationTables(
        identifiant=identifiant,
        description=description or DESCRIPTION_DEFAUT,
        environnement=capturer_environnement(),
        metadonnees={str(k): str(v) for k, v in (metadonnees or {}).items()},
        defauts=defauts, fractions=tuple(fractions), centres=centres, tables=bilans,
    )

