"""Le test des bornes de table : appeler le code au-delà des grilles, vérifier la consigne.

Pour chaque table, chaque axe et chaque côté (une **face**) :

1. le point hors bornes est à ``ecart × étendue`` au-delà de la borne, sur cet
   axe seulement ; les autres axes parcourent **tous** leurs nœuds (ordre de
   lecture Fortran) — une face de la table, déplacée vers l'extérieur ;
2. la valeur **attendue** suit la consigne déclarée (``sature`` / ``extrapole``),
   calculée sur la table par :func:`cfd_validation.core.bornes.interpoler` ;
   une face ``inatteignable`` n'est pas appelée, et le rapport le dit ;
3. un appel de l'évaluateur par table ; la sonde est comparée à l'attendu ;
4. le comportement **observé** de chaque face est établi en comparant la sonde
   aux deux consignes possibles : « sature », « extrapole », « indiscernable »
   (la dernière maille est plate : les deux donnent la même valeur), « ni l'un
   ni l'autre », ou « sonde non atteinte ». C'est ce qui dit, en cas d'échec, ce
   que le code fait à la place de ce qu'on lui demande.

Tolérance : celle de la table si elle en déclare une ; sinon l'identité bit pour
bit sur une face saturée (le code y relit un nœud) et ``TOLERANCE_EXTRAPOLATION``
sur une face extrapolée (l'oracle refait le calcul du code, pas forcément dans
le même ordre d'opérations).
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from cfd_validation.core import statuts as st
from cfd_validation.core.bornes import (
    COTES,
    EXTRAPOLE,
    INATTEIGNABLE,
    SATURE,
    interpoler,
    point_hors_bornes,
)
from cfd_validation.core.ecarts import comparer_numerique
from cfd_validation.core.tolerance import ORIGINE_DECLAREE, ORIGINE_DEFAUT, Tolerance
from cfd_validation.data.tables import ErreurTable, TableReference
from cfd_validation.engine.environnement import (
    Empreinte,
    Environnement,
    capturer_environnement,
    empreinte_table,
)
from cfd_validation.engine.injection import appeler, verifier_defauts
from cfd_validation.engine.lecture_tables import Evaluateur

__all__ = [
    "ECART_DEFAUT",
    "IDENTIFIANT_DEFAUT",
    "TOLERANCE_EXTRAPOLATION",
    "BilanBornes",
    "BilanFace",
    "Face",
    "ResultatBornesTables",
    "tolerance_face",
    "verifier_bornes",
]

IDENTIFIANT_DEFAUT = "BORNES-TABLES"
DESCRIPTION_DEFAUT = (
    "Le code, appelé au-delà des bornes de chaque table, sature ou extrapole "
    "comme le demande la consigne déclarée pour chaque axe et chaque côté."
)
#: Distance des points hors bornes, en fraction de l'étendue de l'axe.
ECART_DEFAUT = 0.10
#: Tolérance par défaut d'une face extrapolée.
TOLERANCE_EXTRAPOLATION = Tolerance(
    rtol=1e-12, atol=1e-15, origine=ORIGINE_DEFAUT,
    justification=(
        "L'oracle refait l'extrapolation (1 − t)·V(i) + t·V(i+1) avec t hors de [0, 1] ; "
        "le code peut ordonner autrement les opérations : quelques ULP."
    ),
)
TOLERANCE_SATURATION = Tolerance(
    rtol=0.0, atol=0.0, origine=ORIGINE_DEFAUT,
    justification="Saturé, le code relit un nœud de la table : identité bit pour bit.",
)

#: Comportements observés d'une face.
OBSERVE_INDISCERNABLE = "indiscernable"
OBSERVE_AUTRE = "ni l'un ni l'autre"
OBSERVE_NAN = "sonde non atteinte"
FLECHE = {"min": "−", "max": "+"}


@dataclass(frozen=True)
class Face:
    """Un axe, un côté : la consigne, d'où elle vient, et où l'on appelle."""

    axe: str
    cote: str
    consigne: str
    origine: str
    borne: float
    valeur: float

    @property
    def nom(self) -> str:
        """``alpha−`` / ``alpha+``."""
        return f"{self.axe}{FLECHE[self.cote]}"


@dataclass(frozen=True)
class BilanFace:
    face: Face
    tolerance: Tolerance
    n_points: int
    n_identiques: int
    n_toleres: int
    n_echecs: int
    max_abs: float
    max_ulp: float
    observe: str

    @property
    def conforme(self) -> bool:
        return self.n_echecs == 0


def _nanmax(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    x = x[~np.isnan(x)]
    return float(x.max()) if x.size else math.nan


def _json(v: Any) -> Any:
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return None if math.isnan(v) else ("inf" if v > 0 else "-inf")
    return v


@dataclass(frozen=True)
class BilanBornes:
    """Le résultat d'une table : une ligne de ``resultats`` par appel du code."""

    table: TableReference
    resultats: pd.DataFrame
    faces: tuple[BilanFace, ...]
    non_testees: tuple[Face, ...]
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
        return sum(f.n_identiques for f in self.faces)

    @property
    def n_toleres(self) -> int:
        return sum(f.n_toleres for f in self.faces)

    @property
    def n_echecs(self) -> int:
        return sum(f.n_echecs for f in self.faces)

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
            "faces": [
                {
                    "face": b.face.nom, "axe": b.face.axe, "cote": b.face.cote,
                    "consigne": b.face.consigne, "origine": b.face.origine,
                    "borne": b.face.borne, "valeur": b.face.valeur, "observe": b.observe,
                    "tolerance": {"rtol": b.tolerance.rtol, "atol": b.tolerance.atol,
                                  "origine": b.tolerance.origine, "justification": b.tolerance.justification},
                    "points": b.n_points, "echecs": b.n_echecs,
                    "max_abs_ecart": _json(b.max_abs), "max_ulp": _json(b.max_ulp), "conforme": b.conforme,
                }
                for b in self.faces
            ],
            "non_testees": [{"face": f.nom, "consigne": f.consigne, "origine": f.origine} for f in self.non_testees],
            "appels": self.n_valeurs,
            "identiques": self.n_identiques,
            "tolerees": self.n_toleres,
            "echecs": self.n_echecs,
            "conforme": self.conforme,
            "verdict": self.verdict,
        }


@dataclass(frozen=True)
class ResultatBornesTables:
    """Toutes les tables d'un test des bornes."""

    identifiant: str
    description: str
    environnement: Environnement
    metadonnees: Mapping[str, str]
    defauts: Mapping[str, Any]
    ecart: float
    ecarts: Mapping[str, float]
    consigne_defaut: str
    tables: tuple[BilanBornes, ...]
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
            for f in b.faces:
                if not f.conforme:
                    motifs.append(f"{b.nom} {f.face.nom} : attendu {f.face.consigne}, observé {f.observe} "
                                  f"({f.n_echecs}/{f.n_points} hors tolérance)")
        return motifs

    def bilan(self, nom: str) -> BilanBornes:
        for b in self.tables:
            if b.nom == nom:
                return b
        raise KeyError(nom)

    def resume(self) -> dict[str, Any]:
        env = self.environnement
        return {
            "controle": "bornes des tables",
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
            "ecart": self.ecart,
            "ecarts": dict(self.ecarts),
            "consigne_defaut": self.consigne_defaut,
            "appels": self.n_appels,
            "tables": [b.resume() for b in self.tables],
            "motifs_non_conformite": self.motifs_non_conformite,
            "fichiers": [str(f) for f in self.fichiers],
        }


# ---------------------------------------------------------------------------
# Plan d'appels
# ---------------------------------------------------------------------------


def _faces(table: TableReference, ecart: float, ecarts: Mapping[str, float], consigne_defaut: str) -> list[Face]:
    faces = []
    for axe, grille in table.axes.items():
        declaree = table.bornes.get(axe)
        for k, cote in enumerate(COTES):
            consigne = declaree[k] if declaree else consigne_defaut
            origine = ORIGINE_DECLAREE if declaree else ORIGINE_DEFAUT
            borne = float(grille[0] if cote == "min" else grille[-1])
            try:
                valeur = point_hors_bornes(grille, cote, ecarts.get(axe, ecart))
            except ValueError as erreur:
                raise ErreurTable(f"table {table.nom}, axe {axe} : {erreur}") from None
            faces.append(Face(axe, cote, consigne, origine, borne, valeur))
    return faces


def _points_face(table: TableReference, face: Face) -> pd.DataFrame:
    """L'axe de la face hors bornes, les autres sur tous leurs nœuds (premier axe le plus rapide)."""
    autres = [a for a in table.noms_axes if a != face.axe]
    grilles = [table.axes[a] for a in autres]
    # itertools.product fait varier le dernier le plus vite : on renverse pour l'ordre Fortran.
    lignes = [tuple(reversed(p)) for p in itertools.product(*reversed(grilles))] if grilles else [()]
    df = pd.DataFrame(lignes, columns=autres) if autres else pd.DataFrame(index=range(1))
    df[face.axe] = face.valeur
    return df[list(table.noms_axes)]


def _observe(code: np.ndarray, sature: np.ndarray, extrapole: np.ndarray, tol: Tolerance) -> str:
    if np.isnan(code).any():
        return OBSERVE_NAN

    def colle(v: np.ndarray) -> bool:
        return bool(np.all(np.abs(code - v) <= tol.seuil(v)))

    s, e = colle(sature), colle(extrapole)
    if s and e:
        return OBSERVE_INDISCERNABLE
    return SATURE if s else EXTRAPOLE if e else OBSERVE_AUTRE


def tolerance_face(table: TableReference, consigne: str) -> Tolerance:
    """La tolérance d'une face : celle de la table si déclarée, sinon selon la consigne."""
    if table.rtol is not None or table.atol is not None:
        return table.tolerance
    return TOLERANCE_SATURATION if consigne == SATURE else TOLERANCE_EXTRAPOLATION


def _verifier_table(
    table: TableReference, evaluer: Evaluateur, defauts: Mapping[str, Any],
    ecart: float, ecarts: Mapping[str, float], consigne_defaut: str,
) -> BilanBornes:
    verifier_defauts(table, defauts)
    faces = _faces(table, ecart, ecarts, consigne_defaut)
    testees = [f for f in faces if f.consigne != INATTEIGNABLE]
    non_testees = tuple(f for f in faces if f.consigne == INATTEIGNABLE)
    if not testees:
        raise ErreurTable(f"table {table.nom} : toutes les faces sont inatteignables, rien à tester")

    blocs = []
    for numero, f in enumerate(testees):
        pts = _points_face(table, f)
        pts.insert(0, "point", np.arange(len(pts)))
        pts.insert(0, "face", f.nom)
        pts.insert(0, "num_face", numero)
        blocs.append(pts)
    cles = pd.concat(blocs, ignore_index=True)
    axes_df = cles[list(table.noms_axes)].reset_index(drop=True)
    appel = appeler(table, evaluer, defauts, axes_df)
    entrees, code, pilotees = appel.entrees, appel.code, appel.pilotees

    coords = axes_df.to_numpy(dtype=np.float64)
    d = len(table.noms_axes)
    regles_sat = [(SATURE, SATURE)] * d
    regles_ext = [(EXTRAPOLE, EXTRAPOLE)] * d
    v_sat = interpoler(table.valeurs, table.grilles, coords, regles_sat)
    v_ext = interpoler(table.valeurs, table.grilles, coords, regles_ext)
    consignes = np.array([testees[i].consigne for i in cles["num_face"]])
    attendu = np.where(consignes == SATURE, v_sat, v_ext)

    resultats = cles.drop(columns="num_face").copy()
    resultats.insert(2, "consigne", consignes)
    for k in entrees.columns:
        if k not in resultats.columns:
            resultats[k] = entrees[k].to_numpy()
    for col in ("valeur_ATTENDUE", "valeur_SATURATION", "valeur_EXTRAPOLATION", "valeur_CODE",
                "ecart", "ulp", "marge"):
        resultats[col] = np.nan
    resultats["statut"] = ""
    resultats["conforme"] = True

    bilans = []
    for numero, f in enumerate(testees):
        dans = (cles["num_face"] == numero).to_numpy()
        tol = tolerance_face(table, f.consigne)
        e = comparer_numerique(attendu[dans], code[dans], tol)
        idx = resultats.index[dans]
        resultats.loc[idx, "valeur_ATTENDUE"] = attendu[dans]
        resultats.loc[idx, "valeur_SATURATION"] = v_sat[dans]
        resultats.loc[idx, "valeur_EXTRAPOLATION"] = v_ext[dans]
        resultats.loc[idx, "valeur_CODE"] = code[dans]
        resultats.loc[idx, "ecart"] = e.ecart
        resultats.loc[idx, "ulp"] = e.ulp
        resultats.loc[idx, "marge"] = e.marge
        resultats.loc[idx, "statut"] = [st.NOMS[int(s)] for s in e.statut]
        resultats.loc[idx, "conforme"] = e.statut < st.ECART
        # « observé » se juge avec la tolérance d'une extrapolation, qui admet les deux calculs.
        tol_obs = tol if not tol.exacte else TOLERANCE_EXTRAPOLATION
        bilans.append(BilanFace(
            face=f, tolerance=tol, n_points=int(dans.sum()),
            n_identiques=int((e.statut == st.IDENTIQUE).sum()), n_toleres=int((e.statut == st.TOLERE).sum()),
            n_echecs=int((e.statut >= st.ECART).sum()),
            max_abs=_nanmax(np.abs(e.ecart)), max_ulp=_nanmax(e.ulp),
            observe=_observe(code[dans], v_sat[dans], v_ext[dans], tol_obs),
        ))
    resultats["conforme"] = resultats["conforme"].astype(bool)

    return BilanBornes(
        table=table, resultats=resultats, faces=tuple(bilans), non_testees=non_testees,
        entrees_pilotees=pilotees, empreinte=empreinte_table(table.table_plate()),
    )


def verifier_bornes(
    tables: Sequence[TableReference],
    evaluer: Evaluateur,
    defauts: Mapping[str, Any],
    *,
    ecart: float = ECART_DEFAUT,
    ecarts: Mapping[str, float] | None = None,
    consigne_defaut: str = SATURE,
    identifiant: str = IDENTIFIANT_DEFAUT,
    description: str | None = None,
    metadonnees: Mapping[str, Any] | None = None,
) -> ResultatBornesTables:
    """Appelle le code au-delà des bornes de chaque table ; aucun fichier n'est écrit.

    ``ecart`` : distance hors bornes en fraction de l'étendue de l'axe (``ecarts``
    par nom d'axe pour l'ajuster) ; ``consigne_defaut`` : celle des axes que la
    table ne déclare pas (signalée « défaut » dans le rapport).
    """
    if not tables:
        raise ErreurTable("aucune table à vérifier")
    if consigne_defaut not in (SATURE, EXTRAPOLE, INATTEIGNABLE):
        raise ErreurTable(f"consigne par défaut {consigne_defaut!r} : attendu sature, extrapole ou inatteignable")
    if not defauts:
        raise ErreurTable("vecteur des défauts vide : il donne la valeur de chaque entrée du modèle")
    vus: dict[str, str] = {}
    for t in tables:
        if not isinstance(t, TableReference):
            raise ErreurTable(f"TableReference attendue, reçu {type(t).__name__}")
        if t.nom.lower() in vus:
            raise ErreurTable(f"deux tables nommées {vus[t.nom.lower()]!r} et {t.nom!r}")
        vus[t.nom.lower()] = t.nom
    ecarts = dict(ecarts or {})
    for valeur in (ecart, *ecarts.values()):
        if not (isinstance(valeur, (int, float)) and valeur > 0 and math.isfinite(valeur)):
            raise ErreurTable(f"écart {valeur!r} : une fraction strictement positive de l'étendue est attendue")
    defauts = dict(defauts)
    bilans = tuple(_verifier_table(t, evaluer, defauts, ecart, ecarts, consigne_defaut) for t in tables)
    return ResultatBornesTables(
        identifiant=identifiant,
        description=description or DESCRIPTION_DEFAUT,
        environnement=capturer_environnement(),
        metadonnees={str(k): str(v) for k, v in (metadonnees or {}).items()},
        defauts=defauts, ecart=float(ecart), ecarts=ecarts, consigne_defaut=consigne_defaut,
        tables=bilans,
    )
