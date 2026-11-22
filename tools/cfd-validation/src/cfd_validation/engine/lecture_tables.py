"""Le test de lecture de table : appeler le code sur les nœuds, comparer à la table.

Pour chaque table, en ordre de lecture Fortran :

1. les nœuds deviennent des **points d'entrée du modèle** : le vecteur des
   ``defauts``, les entrées ``fixes`` de la table, puis les colonnes de la table
   — directement quand une colonne porte le nom d'une entrée, sinon par
   ``vers_entrees`` ;
2. option ``combinaisons`` : chaque nœud est rejoué pour toutes les
   combinaisons des valeurs déclarées des entrées que la table ne pilote pas
   (ni fixées). La lecture d'une table ne doit pas en dépendre ;
3. un seul appel de l'**évaluateur** par table, sur toutes les lignes ; la
   colonne ``sonde`` est la valeur que le code a lue ;
4. comparaison par :func:`cfd_validation.core.ecarts.comparer_numerique` :
   référence = la table (l'oracle), test = le code.

La combinaison 0 est toujours celle des défauts. Une sonde que le code n'a pas
atteinte (NaN) est ``NON_FINI`` : elle ne passe jamais pour une lecture juste.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from cfd_validation.core import statuts as st
from cfd_validation.core.ecarts import comparer_numerique
from cfd_validation.core.noeuds import coordonnees_noeuds
from cfd_validation.core.tolerance import Tolerance
from cfd_validation.data.tables import ErreurTable, TableReference
from cfd_validation.engine.environnement import (
    Empreinte,
    Environnement,
    capturer_environnement,
    empreinte_table,
)
from cfd_validation.engine.injection import piloter

__all__ = [
    "COLONNES_COMPARAISON",
    "IDENTIFIANT_DEFAUT",
    "BilanTable",
    "Evaluateur",
    "ResultatLectureTables",
    "relire_tables",
]

#: ``evaluer(df_entrees) -> df`` : une ligne par point, même ordre ; doit porter la colonne de sonde.
Evaluateur = Callable[[pd.DataFrame], pd.DataFrame]

IDENTIFIANT_DEFAUT = "LECTURE-TABLES"
DESCRIPTION_DEFAUT = (
    "Le code, appelé sur chaque nœud de chaque table, lit la valeur de la table "
    "dans la tolérance déclarée."
)
#: Colonnes de comparaison des CSV de résultats, après les axes et les entrées injectées.
COLONNES_COMPARAISON = ("valeur_TAB", "valeur_CODE", "ecart", "ulp", "marge", "statut", "conforme")


# ---------------------------------------------------------------------------
# Résultats
# ---------------------------------------------------------------------------


def _nanmax(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    x = x[~np.isnan(x)]
    return float(x.max()) if x.size else math.nan


@dataclass(frozen=True)
class BilanTable:
    """Le résultat d'une table : une ligne de ``resultats`` par appel du code."""

    table: TableReference
    resultats: pd.DataFrame
    entrees_pilotees: tuple[str, ...]
    entrees_injectees: Mapping[str, Any]
    combinaisons: tuple[Mapping[str, Any], ...]
    combinaisons_ignorees: tuple[str, ...]
    empreinte: Empreinte
    #: Les défauts ne sont pas un élément du produit des combinaisons (combinaison 0 en plus).
    defauts_hors_produit: bool = False

    @property
    def nom(self) -> str:
        return self.table.nom

    @property
    def tolerance(self) -> Tolerance:
        return self.table.tolerance

    @property
    def n_valeurs(self) -> int:
        return len(self.resultats)

    def _compte(self, *codes: str) -> int:
        return int(self.resultats["statut"].isin(codes).sum())

    @property
    def n_identiques(self) -> int:
        return self._compte(st.NOMS[st.IDENTIQUE])

    @property
    def n_toleres(self) -> int:
        return self._compte(st.NOMS[st.TOLERE])

    @property
    def n_echecs(self) -> int:
        return int((~self.resultats["conforme"]).sum())

    @property
    def n_non_finis(self) -> int:
        return self._compte(st.NOMS[st.NON_FINI])

    @property
    def max_abs(self) -> float:
        return _nanmax(np.abs(self.resultats["ecart"].to_numpy(dtype=np.float64)))

    @property
    def max_ulp(self) -> float:
        return _nanmax(self.resultats["ulp"].to_numpy(dtype=np.float64))

    @property
    def marge_max(self) -> float:
        m = np.abs(self.resultats["marge"].to_numpy(dtype=np.float64))
        return float(np.max(m)) if m.size else 0.0

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

    def decrire_combinaison(self, numero: int) -> str:
        """``défauts`` (et ses valeurs combinées) pour la combinaison 0, ``beta=5, ipropu=1`` sinon."""
        c = self.combinaisons[numero]
        texte = ", ".join(f"{k}={v:g}" if isinstance(v, float) else f"{k}={v}" for k, v in c.items())
        if numero == 0:
            return f"défauts ({texte})" if texte else "défauts"
        return texte

    def echecs_par_combinaison(self) -> pd.Series:
        """Nombre d'échecs par combinaison (combinaisons sans échec omises)."""
        e = self.echecs()
        return e.groupby("combinaison").size() if len(e) else pd.Series(dtype=np.int64)

    @property
    def entrees_combinees(self) -> tuple[str, ...]:
        """Les entrées que les combinaisons font varier, dans l'ordre de déclaration."""
        return tuple(dict.fromkeys(k for c in self.combinaisons for k in c))

    def dependances(self) -> dict[str, dict[Any, tuple[int, int]]]:
        """Entrées combinées dont dépend la lecture : ``{entrée: {valeur: (échecs, appels)}}``.

        Le plan est un produit complet : une entrée sans effet a le **même** taux
        d'échec pour chacune de ses valeurs. Une entrée dont le taux varie d'une
        valeur à l'autre est celle dont la lecture dépend (sonde placée après
        l'incrément propulsif : échecs pour ``ipropu = 1`` seulement).
        """
        if self.conforme or len(self.combinaisons) < 2:
            return {}
        # Sur le produit complet seulement : des défauts hors produit (xg = 1.2 contre
        # {1.0, 1.4}) n'apparaîtraient qu'une fois et prendraient un taux propre sans
        # rien dire de l'entrée.
        r = self.resultats
        produit = r[r["combinaison"] > 0] if self.defauts_hors_produit else r
        echec = ~produit["conforme"].to_numpy()
        liees: dict[str, dict[Any, tuple[int, int]]] = {}
        for k in self.entrees_combinees:
            valeurs = produit[k].to_numpy()
            par_valeur = {v.item() if isinstance(v, np.generic) else v: (int(echec[valeurs == v].sum()), int((valeurs == v).sum()))
                          for v in pd.unique(valeurs)}
            taux = {round(e / n, 12) for e, n in par_valeur.values() if n}
            if len(taux) > 1:
                liees[k] = par_valeur
        return liees

    def resume(self) -> dict[str, Any]:
        t = self.table
        return {
            "nom": t.nom,
            "description": t.description,
            "forme": list(t.forme),
            "axes": {a: g.tolist() for a, g in t.axes.items()},
            "sonde": t.sonde,
            "inversion": t.vers_entrees is not None,
            "entrees_pilotees": list(self.entrees_pilotees),
            "fixes": {k: _json(v) for k, v in t.fixes.items()},
            "combinaisons": len(self.combinaisons),
            "combinaisons_ignorees": list(self.combinaisons_ignorees),
            "dependances": {k: {str(v): {"echecs": e, "appels": n} for v, (e, n) in d.items()}
                            for k, d in self.dependances().items()},
            "tolerance": {
                "rtol": self.tolerance.rtol,
                "atol": self.tolerance.atol,
                "origine": self.tolerance.origine,
                "justification": self.tolerance.justification,
            },
            "sha256_table": self.empreinte.sha256,
            "noeuds": t.n_noeuds,
            "appels": self.n_valeurs,
            "identiques": self.n_identiques,
            "tolerees": self.n_toleres,
            "echecs": self.n_echecs,
            "non_finis": self.n_non_finis,
            "max_abs_ecart": _json(self.max_abs),
            "max_ulp": _json(self.max_ulp),
            "marge_max": _json(self.marge_max),
            "conforme": self.conforme,
            "verdict": self.verdict,
        }


@dataclass(frozen=True)
class ResultatLectureTables:
    """Toutes les tables d'un test de lecture."""

    identifiant: str
    description: str
    environnement: Environnement
    metadonnees: Mapping[str, str]
    defauts: Mapping[str, Any]
    combinaisons: Mapping[str, tuple[Any, ...]]
    tables: tuple[BilanTable, ...]
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
            if not b.conforme:
                detail = f"dont {b.n_non_finis} sonde(s) non atteinte(s) (NaN)" if b.n_non_finis else ""
                motifs.append(f"{b.nom} : {b.n_echecs} valeur(s) sur {b.n_valeurs} hors tolérance {detail}".rstrip())
        return motifs

    def bilan(self, nom: str) -> BilanTable:
        for b in self.tables:
            if b.nom == nom:
                return b
        raise KeyError(nom)

    def resume(self) -> dict[str, Any]:
        env = self.environnement
        return {
            "controle": "lecture de table",
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
            "combinaisons": {k: [_json(x) for x in v] for k, v in self.combinaisons.items()},
            "appels": self.n_appels,
            "tables": [b.resume() for b in self.tables],
            "fichiers": [str(f) for f in self.fichiers],
        }


def _json(v: Any) -> Any:
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return None if math.isnan(v) else ("inf" if v > 0 else "-inf")
    return v


# ---------------------------------------------------------------------------
# Plan d'appels
# ---------------------------------------------------------------------------


def _combinaisons(
    table: TableReference, combinaisons: Mapping[str, tuple[Any, ...]], pilotees: Sequence[str], base: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], tuple[str, ...], bool]:
    """``(liste, ignorées, défauts_hors_produit)`` ; la combinaison 0 est toujours celle des défauts.

    Le produit des valeurs des entrées libres reste **complet** : si les défauts en
    sont un élément, il devient la combinaison 0 ; sinon la combinaison 0 s'y
    ajoute. Un produit amputé d'un élément ferait varier, sous l'attribution, le
    taux d'échec d'une entrée sans effet.
    """
    libres = [k for k in combinaisons if k not in pilotees and k not in table.fixes]
    ignorees = tuple(k for k in combinaisons if k not in libres)
    if not libres:
        return [{}], ignorees, False
    produit = [dict(zip(libres, v)) for v in itertools.product(*(combinaisons[k] for k in libres))]
    for i, c in enumerate(produit):
        if all(base[k] == v for k, v in c.items()):
            return [c, *produit[:i], *produit[i + 1:]], ignorees, False
    return [{}, *produit], ignorees, True


def _plan(
    table: TableReference, defauts: Mapping[str, Any], combinaisons: Mapping[str, tuple[Any, ...]]
) -> tuple[pd.DataFrame, pd.DataFrame, tuple[str, ...], list[dict[str, Any]], tuple[str, ...], bool]:
    """``(cles, entrees, pilotees, combinaisons, ignorees, defauts_hors_produit)`` ; ``cles`` = nœud, combinaison, axes."""
    entrees_modele = list(defauts)
    _, coords = coordonnees_noeuds(table.grilles)
    n = len(coords)
    axes_df = pd.DataFrame(coords, columns=list(table.noms_axes))
    pilote, pilotees = piloter(table, defauts, axes_df)

    base = {**defauts, **table.fixes}
    liste, ignorees, hors_produit = _combinaisons(table, combinaisons, pilotees, base)
    blocs_entrees, blocs_cles = [], []
    for numero, c in enumerate(liste):
        e = pd.DataFrame({k: (pilote[k] if k in pilote else np.full(n, c.get(k, base[k]))) for k in entrees_modele})
        blocs_entrees.append(e)
        k_df = axes_df.copy()
        k_df.insert(0, "combinaison", numero)
        k_df.insert(0, "noeud", np.arange(n))
        blocs_cles.append(k_df)
    entrees = pd.concat(blocs_entrees, ignore_index=True)
    cles_df = pd.concat(blocs_cles, ignore_index=True)
    return cles_df, entrees, pilotees, liste, ignorees, hors_produit


def _relire(
    table: TableReference,
    evaluer: Evaluateur,
    defauts: Mapping[str, Any],
    combinaisons: Mapping[str, tuple[Any, ...]],
) -> BilanTable:
    cles, entrees, pilotees, liste, ignorees, hors_produit = _plan(table, defauts, combinaisons)
    sortie = evaluer(entrees.copy())
    if not isinstance(sortie, pd.DataFrame):
        raise ErreurTable(f"table {table.nom} : l'évaluateur doit rendre un DataFrame, reçu {type(sortie).__name__}")
    if len(sortie) != len(entrees):
        raise ErreurTable(f"table {table.nom} : l'évaluateur rend {len(sortie)} lignes pour {len(entrees)} points")
    if table.sonde not in sortie.columns:
        colonnes = ", ".join(map(str, list(sortie.columns)[:30]))
        raise ErreurTable(f"table {table.nom} : sonde « {table.sonde} » absente de la sortie de l'évaluateur ({colonnes})")

    ref = np.tile(np.asarray(table.valeurs, dtype=np.float64).ravel(order="F"), len(liste))
    code = pd.to_numeric(sortie[table.sonde], errors="coerce").to_numpy(dtype=np.float64)
    e = comparer_numerique(ref, code, table.tolerance)

    resultats = cles.copy()
    for k in entrees.columns:
        if k not in resultats.columns:
            resultats[k] = entrees[k].to_numpy()
    resultats["valeur_TAB"] = ref
    resultats["valeur_CODE"] = code
    resultats["ecart"] = e.ecart
    resultats["ulp"] = e.ulp
    resultats["marge"] = e.marge
    resultats["statut"] = [st.NOMS[int(s)] for s in e.statut]
    resultats["conforme"] = e.statut < st.ECART  # st.est_echec, vectorisé

    return BilanTable(
        table=table,
        resultats=resultats,
        entrees_pilotees=pilotees,
        entrees_injectees={**defauts, **table.fixes},
        combinaisons=tuple(liste),
        combinaisons_ignorees=ignorees,
        defauts_hors_produit=hors_produit,
        empreinte=empreinte_table(table.table_plate()),
    )


def _verifier(
    tables: Sequence[TableReference], defauts: Mapping[str, Any], combinaisons: Mapping[str, Iterable[Any]]
) -> dict[str, tuple[Any, ...]]:
    if not tables:
        raise ErreurTable("aucune table à relire")
    for t in tables:
        if not isinstance(t, TableReference):
            raise ErreurTable(f"TableReference attendue, reçu {type(t).__name__}")
    vus: dict[str, str] = {}
    for t in tables:
        cle = t.nom.lower()  # les fichiers CX.csv et cx.csv se confondent sur un disque insensible à la casse
        if cle in vus:
            raise ErreurTable(f"deux tables nommées {vus[cle]!r} et {t.nom!r}")
        vus[cle] = t.nom
    if not defauts:
        raise ErreurTable("vecteur des défauts vide : il donne la valeur de chaque entrée du modèle")
    propres: dict[str, tuple[Any, ...]] = {}
    for k, v in combinaisons.items():
        if k not in defauts:
            raise ErreurTable(f"combinaisons : {k} n'est pas une entrée du vecteur de défauts")
        valeurs = tuple(v) if not isinstance(v, (str, bytes)) and isinstance(v, Iterable) else (v,)
        if not valeurs:
            raise ErreurTable(f"combinaisons : aucune valeur pour {k}")
        propres[k] = valeurs
    return propres


def relire_tables(
    tables: Sequence[TableReference],
    evaluer: Evaluateur,
    defauts: Mapping[str, Any],
    *,
    combinaisons: Mapping[str, Iterable[Any]] | None = None,
    identifiant: str = IDENTIFIANT_DEFAUT,
    description: str | None = None,
    metadonnees: Mapping[str, Any] | None = None,
) -> ResultatLectureTables:
    """Relit chaque table sur ses nœuds par ``evaluer`` ; aucun fichier n'est écrit."""
    propres = _verifier(tables, defauts, combinaisons or {})
    defauts = dict(defauts)
    bilans = tuple(_relire(t, evaluer, defauts, propres) for t in tables)
    return ResultatLectureTables(
        identifiant=identifiant,
        description=description or DESCRIPTION_DEFAUT,
        environnement=capturer_environnement(),
        metadonnees={str(k): str(v) for k, v in (metadonnees or {}).items()},
        defauts=defauts,
        combinaisons=propres,
        tables=bilans,
    )
