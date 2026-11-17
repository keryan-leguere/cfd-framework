"""Test d'intégration : le code intégré restitue-t-il les sorties du code de référence ?

On dispose de deux tables de même format, entrées et sorties : la
**référence** (le code exécuté dans l'environnement où il est validé) et le
**test** (le même code exécuté ailleurs : autre machine, autre compilateur,
intégré à un workflow). :func:`comparer` les confronte à trois échelles :

1. **structure** — colonnes, lignes appariées, absentes, en trop, types ;
2. **par sortie** (le bilan global) — combien de valeurs identiques bit pour
   bit, dans la tolérance, hors tolérance ; écarts max absolu, relatif, en ULP ;
   biais ; marge (écart en unités de tolérance) ; le pire point ;
3. **par ligne** — le statut de chaque cas, sa sortie la plus en écart ;

puis **attribue** les échecs aux entrées (voir :mod:`cfd_validation.core.attribution`) :
une régression ne frappe presque jamais au hasard, elle suit une branche du
code, donc une plage d'entrée.

Le moteur ne fait que calculer : ni affichage, ni fichier. Le rendu est dans
:mod:`cfd_validation.report`, l'enchaînement complet dans
:func:`cfd_validation.integration.valider_integration`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from cfd_validation.core import statuts as st
from cfd_validation.core.attribution import (
    MAX_NIVEAUX,
    N_CLASSES,
    comptes_par_niveau,
    discretiser,
    v_cramer,
)
from cfd_validation.core.ecarts import Ecarts, comparer_exact, comparer_numerique
from cfd_validation.core.tolerance import ORIGINE_DEFAUT, Tolerance
from cfd_validation.data.specification import ErreurSpecification, Specification
from cfd_validation.engine.appariement import Appariement, apparier
from cfd_validation.engine.environnement import (
    Empreinte,
    Environnement,
    capturer_environnement,
    empreinte_table,
)

__all__ = [
    "DESCRIPTION_DEFAUT",
    "IDENTIFIANT_DEFAUT",
    "AttributionEntree",
    "BilanSortie",
    "Niveau",
    "PirePoint",
    "ResultatIntegration",
    "Structure",
    "comparer",
]

IDENTIFIANT_DEFAUT = "INT-01"
DESCRIPTION_DEFAUT = (
    "Le code exécuté dans l'environnement testé restitue les sorties de la référence, "
    "ligne à ligne, dans les tolérances déclarées."
)
#: En dessous, le V de Cramér est trop instable pour classer les entrées ; le rapport le dit.
EFFECTIF_MIN_ATTRIBUTION = 30


# ---------------------------------------------------------------------------
# Résultats
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PirePoint:
    """La ligne où une sortie est la plus en écart (ou la plus proche de sa tolérance)."""

    ligne_ref: int
    ligne_test: int
    entrees: Mapping[str, Any]
    reference: Any
    test: Any
    marge: float
    statut: int


@dataclass(frozen=True)
class BilanSortie:
    """Bilan d'une colonne de sortie sur toutes les lignes comparées."""

    nom: str
    tolerance: Tolerance
    #: Comparée numériquement (sinon : égalité stricte).
    numerique: bool
    #: La colonne existe dans le test.
    presente: bool
    type_ref: str
    type_test: str
    n: int = 0
    n_identiques: int = 0
    n_toleres: int = 0
    n_ecarts: int = 0
    n_non_finis: int = 0
    #: Paires où les deux côtés valent NaN (comptées identiques).
    n_nan_communs: int = 0
    max_abs: float = math.nan
    max_rel: float = math.nan
    max_ulp: float = math.nan
    rms: float = math.nan
    biais: float = math.nan
    #: max |écart| / tolérance : < 1 conforme.
    marge_max: float = math.nan
    pire: PirePoint | None = None

    @property
    def n_echecs(self) -> int:
        return self.n_ecarts + self.n_non_finis

    @property
    def statut(self) -> int:
        """Pire statut de la colonne (``ABSENTE`` si elle manque au test)."""
        if not self.presente:
            return st.ABSENTE
        if self.n_non_finis:
            return st.NON_FINI
        if self.n_ecarts:
            return st.ECART
        if self.n_toleres:
            return st.TOLERE
        return st.IDENTIQUE


@dataclass(frozen=True)
class Niveau:
    """Un niveau d'une entrée et ses lignes de référence."""

    libelle: str
    n: int
    #: Lignes en échec (hors tolérance, non fini, divergentes ou absentes du test).
    n_echecs: int
    #: Dont absentes du test.
    n_absentes: int
    marge_max: float

    @property
    def taux(self) -> float:
        return self.n_echecs / self.n if self.n else math.nan


@dataclass(frozen=True)
class AttributionEntree:
    """Liaison entre une entrée et les échecs."""

    entree: str
    en_classes: bool
    niveaux: tuple[Niveau, ...]
    #: V de Cramér (niveau × ligne en échec) ; NaN si sans objet.
    v: float
    #: Même chose, sortie par sortie.
    v_par_sortie: Mapping[str, float]

    def niveaux_en_cause(self, taux_global: float, nombre: int = 3) -> list[Niveau]:
        """Les niveaux où l'on échoue plus qu'en moyenne, les pires d'abord."""
        en_cause = [n for n in self.niveaux if n.n and n.n_echecs and n.taux > taux_global]
        en_cause.sort(key=lambda n: (-n.taux, -n.n_echecs))
        return en_cause[:nombre]


@dataclass(frozen=True)
class Structure:
    """Ce qui a pu être comparé."""

    n_ref: int
    n_test: int
    n_appariees: int
    n_comparees: int
    n_absentes: int
    n_en_trop: int
    n_divergentes: int
    n_cles_dupliquees: int
    meme_ordre: bool
    sorties_absentes: tuple[str, ...]
    ignorees_ref: tuple[str, ...]
    ignorees_test: tuple[str, ...]
    #: ``(colonne, type référence, type test)`` des colonnes déclarées de types différents.
    types_differents: tuple[tuple[str, str, str], ...]
    entrees_en_texte: tuple[str, ...]


@dataclass(frozen=True)
class ResultatIntegration:
    """Tout ce que le test a établi ; de quoi rendre le rapport sans rien recalculer."""

    identifiant: str
    description: str
    metadonnees: Mapping[str, str]
    specification: Specification
    environnement: Environnement
    empreinte_ref: Empreinte
    empreinte_test: Empreinte
    structure: Structure
    sorties: tuple[BilanSortie, ...]
    attributions: tuple[AttributionEntree, ...]
    #: Une ligne par cas (référence, puis lignes en trop du test) ; voir :func:`comparer`.
    lignes: pd.DataFrame
    #: Une ligne par (cas comparé × sortie présente) ; voir :func:`comparer`.
    ecarts: pd.DataFrame
    avertissements: tuple[str, ...]
    #: Pièces écrites par :func:`cfd_validation.integration.valider_integration`.
    fichiers: tuple[Path, ...] = field(default=())

    # -- verdict ------------------------------------------------------------

    @property
    def motifs_non_conformite(self) -> list[str]:
        """Pourquoi le test échoue ; vide s'il est conforme."""
        s = self.structure
        motifs = []
        if s.sorties_absentes:
            motifs.append(f"sortie(s) absente(s) du test : {', '.join(s.sorties_absentes)}")
        if s.n_absentes:
            motifs.append(f"{s.n_absentes} ligne(s) de référence absente(s) du test")
        if s.n_en_trop:
            motifs.append(f"{s.n_en_trop} ligne(s) du test sans correspondant dans la référence")
        if s.n_divergentes:
            motifs.append(f"{s.n_divergentes} ligne(s) appariée(s) par position aux entrées divergentes")
        for b in self.sorties:
            if b.presente and b.n_echecs:
                detail = []
                if b.n_ecarts:
                    detail.append(f"{b.n_ecarts} hors tolérance")
                if b.n_non_finis:
                    detail.append(f"{b.n_non_finis} non fini(s) divergent(s)")
                motifs.append(f"{b.nom} : {', '.join(detail)} sur {b.n}")
        if s.n_comparees == 0 and not motifs:
            motifs.append("aucune ligne comparée")
        return motifs

    @property
    def conforme(self) -> bool:
        return not self.motifs_non_conformite

    @property
    def bit_identique(self) -> bool:
        """Conforme et toutes les valeurs égales bit pour bit."""
        return self.conforme and all(b.n_toleres == 0 for b in self.sorties)

    @property
    def verdict(self) -> str:
        if not self.conforme:
            return "NON CONFORME"
        return "CONFORME — identique bit pour bit" if self.bit_identique else "CONFORME — dans les tolérances"

    @property
    def n_lignes_echec(self) -> int:
        """Lignes de référence en échec (comparées hors tolérance, divergentes, absentes)."""
        codes = self.lignes["code"].to_numpy()
        de_ref = self.lignes["ligne_ref"].notna().to_numpy()
        return int(((codes >= st.ECART) & de_ref).sum())

    def entrees_par_pertinence(self, sortie: str | None = None) -> list[str]:
        """Les entrées, les plus liées aux échecs d'abord (V de Cramér décroissant).

        ``sortie`` : la liaison avec les échecs de cette sortie seulement. Les
        entrées sans objet (aucun échec) gardent l'ordre de déclaration, en
        dernier. Sert à choisir quoi montrer quand la place manque (terminal,
        pages de figures) : 10 entrées ne tiennent pas en 80 colonnes, et
        celle qu'on cherche doit passer en premier.
        """

        def v(a: AttributionEntree) -> float:
            x = a.v if sortie is None else a.v_par_sortie.get(sortie, math.nan)
            return -1.0 if math.isnan(x) else x

        return [a.entree for a in sorted(self.attributions, key=lambda a: -v(a))]

    @property
    def taux_echec(self) -> float:
        n = self.structure.n_ref
        return self.n_lignes_echec / n if n else math.nan

    def resume(self) -> dict[str, Any]:
        """Le résultat en types JSON (``resume.json``), sans les tables ligne à ligne."""
        s = self.structure

        def nombre(x: float) -> float | str | None:
            if x is None or (isinstance(x, float) and math.isnan(x)):
                return None
            if isinstance(x, float) and math.isinf(x):
                return "inf" if x > 0 else "-inf"
            return float(x)

        return {
            "identifiant": self.identifiant,
            "description": self.description,
            "verdict": self.verdict,
            "conforme": self.conforme,
            "bit_identique": self.bit_identique,
            "motifs_non_conformite": self.motifs_non_conformite,
            "metadonnees": dict(self.metadonnees),
            "environnement": {
                "date": self.environnement.date,
                "hote": self.environnement.hote,
                "utilisateur": self.environnement.utilisateur,
                "systeme": self.environnement.systeme,
                "python": self.environnement.python,
                "versions": dict(self.environnement.versions),
            },
            "donnees": {
                "reference": {"lignes": self.empreinte_ref.n_lignes, "colonnes": self.empreinte_ref.n_colonnes, "sha256": self.empreinte_ref.sha256},
                "test": {"lignes": self.empreinte_test.n_lignes, "colonnes": self.empreinte_test.n_colonnes, "sha256": self.empreinte_test.sha256},
            },
            "specification": {
                "entrees": list(self.specification.entrees),
                "sorties": list(self.specification.sorties),
                "alignement": self.specification.alignement,
                "chiffres_cle": self.specification.chiffres_cle,
                "renommage_test": dict(self.specification.renommage_test),
                "tolerances": {
                    nom: {
                        "rtol": t.rtol,
                        "atol": t.atol,
                        "critere": t.decrire(),
                        "origine": t.origine,
                        "justification": t.justification,
                    }
                    for nom, t in self.specification.tolerances.items()
                },
            },
            "structure": {
                "lignes_reference": s.n_ref,
                "lignes_test": s.n_test,
                "appariees": s.n_appariees,
                "comparees": s.n_comparees,
                "absentes": s.n_absentes,
                "en_trop": s.n_en_trop,
                "entrees_divergentes": s.n_divergentes,
                "cles_dupliquees": s.n_cles_dupliquees,
                "meme_ordre": s.meme_ordre,
                "sorties_absentes": list(s.sorties_absentes),
                "colonnes_ignorees_reference": list(s.ignorees_ref),
                "colonnes_ignorees_test": list(s.ignorees_test),
                "types_differents": [list(t) for t in s.types_differents],
            },
            "sorties": [
                {
                    "nom": b.nom,
                    "statut": st.NOMS[b.statut],
                    "numerique": b.numerique,
                    "n": b.n,
                    "identiques": b.n_identiques,
                    "toleres": b.n_toleres,
                    "hors_tolerance": b.n_ecarts,
                    "non_finis": b.n_non_finis,
                    "nan_communs": b.n_nan_communs,
                    "max_abs": nombre(b.max_abs),
                    "max_rel": nombre(b.max_rel),
                    "max_ulp": nombre(b.max_ulp),
                    "rms": nombre(b.rms),
                    "biais": nombre(b.biais),
                    "marge_max": nombre(b.marge_max),
                    "pire": None
                    if b.pire is None
                    else {
                        "ligne_ref": b.pire.ligne_ref,
                        "ligne_test": b.pire.ligne_test,
                        "entrees": {k: _json(v) for k, v in b.pire.entrees.items()},
                        "reference": _json(b.pire.reference),
                        "test": _json(b.pire.test),
                        "marge": nombre(b.pire.marge),
                    },
                }
                for b in self.sorties
            ],
            "attribution": [
                {
                    "entree": a.entree,
                    "v_cramer": nombre(a.v),
                    "v_par_sortie": {k: nombre(v) for k, v in a.v_par_sortie.items()},
                    "niveaux": [
                        {"niveau": n.libelle, "lignes": n.n, "echecs": n.n_echecs, "absentes": n.n_absentes}
                        for n in a.niveaux
                    ],
                }
                for a in self.attributions
            ],
            "avertissements": list(self.avertissements),
            "fichiers": [str(p) for p in self.fichiers],
        }


def _json(v: Any) -> Any:
    if isinstance(v, (np.generic,)):
        v = v.item()
    if isinstance(v, float):
        if math.isnan(v):
            return None
        if math.isinf(v):
            return "inf" if v > 0 else "-inf"
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    return str(v)


# ---------------------------------------------------------------------------
# Calcul
# ---------------------------------------------------------------------------


def _est_numerique(s: pd.Series) -> bool:
    return bool(pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s))


def _valeurs(s: pd.Series) -> NDArray[Any]:
    """Les valeurs d'une colonne en NumPy : float64 (NaN pour les manquants) si numérique."""
    if _est_numerique(s):
        return s.to_numpy(dtype=np.float64, na_value=np.nan)
    return s.to_numpy(dtype=object)


def _verifier(reference: pd.DataFrame, test: pd.DataFrame, spec: Specification) -> None:
    for nom, df in (("référence", reference), ("test", test)):
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"la table {nom} doit être un pandas.DataFrame, reçu {type(df).__name__}")
        doublons = sorted({str(c) for c in df.columns[df.columns.duplicated()]})
        if doublons:
            raise ErreurSpecification(f"colonnes en double dans la table {nom} : {', '.join(doublons)}")
    if len(reference) == 0:
        raise ErreurSpecification("la table de référence est vide")
    manquantes = [c for c in (*spec.entrees, *spec.sorties) if c not in reference.columns]
    if manquantes:
        raise ErreurSpecification(
            f"colonne(s) déclarée(s) absente(s) de la référence : {', '.join(manquantes)} "
            f"(colonnes disponibles : {', '.join(map(str, reference.columns))})"
        )
    entrees_manquantes = [c for c in spec.entrees if c not in test.columns]
    if entrees_manquantes:
        raise ErreurSpecification(
            f"entrée(s) absente(s) du test : {', '.join(entrees_manquantes)} — sans elles les lignes "
            "ne peuvent être appariées (renommage_test={'nom_test': 'nom_ref'} ?)"
        )


def _nanmax(x: NDArray[np.float64]) -> float:
    x = x[~np.isnan(x)]
    return float(x.max()) if x.size else math.nan


def _nanmean(x: NDArray[np.float64]) -> float:
    x = x[np.isfinite(x)]
    return float(x.mean()) if x.size else math.nan


def _bilan(
    nom: str,
    tol: Tolerance,
    numerique: bool,
    type_ref: str,
    type_test: str,
    e: Ecarts,
    a: NDArray[Any],
    b: NDArray[Any],
    pos_ref: NDArray[np.int64],
    pos_test: NDArray[np.int64],
    entrees_ref: pd.DataFrame,
) -> BilanSortie:
    n = int(e.statut.size)
    compte = np.bincount(e.statut, minlength=4)
    if numerique:
        nan_communs = int((np.isnan(a.astype(float)) & np.isnan(b.astype(float))).sum())
    else:
        nan_communs = 0
    pire = None
    if n:
        if numerique:
            score = np.where(np.isnan(e.marge), -1.0, np.abs(e.marge))
            score = np.where(e.statut == st.NON_FINI, np.inf, score)
        else:
            score = e.statut.astype(np.float64)
        i = int(np.argmax(score))
        pire = PirePoint(
            ligne_ref=int(pos_ref[i]),
            ligne_test=int(pos_test[i]),
            entrees={str(k): v for k, v in entrees_ref.iloc[int(pos_ref[i])].items()},
            reference=a[i],
            test=b[i],
            marge=float(e.marge[i]),
            statut=int(e.statut[i]),
        )
    ecart_fini = e.ecart[np.isfinite(e.ecart)]
    return BilanSortie(
        nom=nom,
        tolerance=tol,
        numerique=numerique,
        presente=True,
        type_ref=type_ref,
        type_test=type_test,
        n=n,
        n_identiques=int(compte[st.IDENTIQUE]),
        n_toleres=int(compte[st.TOLERE]),
        n_ecarts=int(compte[st.ECART]),
        n_non_finis=int(compte[st.NON_FINI]),
        n_nan_communs=nan_communs,
        max_abs=_nanmax(np.abs(e.ecart)),
        max_rel=_nanmax(e.ecart_rel),
        max_ulp=_nanmax(e.ulp),
        rms=float(np.sqrt(np.mean(ecart_fini**2))) if ecart_fini.size else math.nan,
        biais=_nanmean(e.ecart),
        marge_max=_nanmax(np.abs(e.marge)),
        pire=pire,
    )


def comparer(
    reference: pd.DataFrame,
    test: pd.DataFrame,
    spec: Specification,
    *,
    identifiant: str = IDENTIFIANT_DEFAUT,
    description: str | None = None,
    metadonnees: Mapping[str, Any] | None = None,
    max_niveaux: int = MAX_NIVEAUX,
    n_classes: int = N_CLASSES,
) -> ResultatIntegration:
    """Compare ``test`` à ``reference`` selon ``spec``.

    Tables produites
    ----------------
    ``lignes`` : ``ligne_ref``, ``ligne_test`` (rangs 0, 1… dans chaque table,
    vides pour une ligne absente ou en trop), les entrées, ``statut`` (nom
    stable, voir :mod:`cfd_validation.core.statuts`), ``code``,
    ``sortie_pire``, ``marge_max``, ``ecart_rel_max``, ``ulp_max``,
    ``n_hors_tolerance``.

    ``ecarts`` : ``ligne_ref``, ``ligne_test``, les entrées, ``sortie``,
    ``reference``, ``test``, ``ecart`` (test − réf), ``ecart_rel``, ``ulp``,
    ``seuil`` (écart admissible), ``marge`` (écart / seuil), ``statut``.
    """
    # L'empreinte porte sur les tables telles qu'on les a reçues ; le renommage
    # précède la vérification, qui cherche les noms de la référence.
    for nom, df in (("référence", reference), ("test", test)):
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"la table {nom} doit être un pandas.DataFrame, reçu {type(df).__name__}")
    environnement = capturer_environnement()
    empreinte_ref, empreinte_test = empreinte_table(reference), empreinte_table(test)
    if spec.renommage_test:
        test = test.rename(columns=dict(spec.renommage_test))
    _verifier(reference, test, spec)
    ref = reference.reset_index(drop=True)
    tst = test.reset_index(drop=True)
    entrees = list(spec.entrees)

    app: Appariement = apparier(ref, tst, entrees, alignement=spec.alignement, chiffres_cle=spec.chiffres_cle)
    garde = ~app.divergentes
    pr, pt = app.ref[garde], app.test[garde]
    entrees_ref = ref[entrees]

    # -- par sortie ---------------------------------------------------------
    presentes = [s for s in spec.sorties if s in tst.columns]
    bilans: list[BilanSortie] = []
    ecarts_par_sortie: dict[str, Ecarts] = {}
    valeurs: dict[str, tuple[NDArray[Any], NDArray[Any]]] = {}
    for nom in spec.sorties:
        tol = spec.tolerance(nom)
        type_ref = str(ref[nom].dtype)
        if nom not in tst.columns:
            bilans.append(BilanSortie(nom, tol, _est_numerique(ref[nom]), False, type_ref, "—"))
            continue
        numerique = _est_numerique(ref[nom]) and _est_numerique(tst[nom])
        a = _valeurs(ref[nom])[pr] if numerique else ref[nom].to_numpy(dtype=object)[pr]
        b = _valeurs(tst[nom])[pt] if numerique else tst[nom].to_numpy(dtype=object)[pt]
        e = comparer_numerique(a, b, tol) if numerique else comparer_exact(a, b)
        ecarts_par_sortie[nom], valeurs[nom] = e, (a, b)
        bilans.append(
            _bilan(nom, tol, numerique, type_ref, str(tst[nom].dtype), e, a, b, pr, pt, entrees_ref)
        )

    # -- par ligne comparée -------------------------------------------------
    n_cmp = pr.size
    code = np.zeros(n_cmp, dtype=np.int8)
    marge_max = np.full(n_cmp, np.nan)
    rel_max = np.full(n_cmp, np.nan)
    ulp_max = np.full(n_cmp, np.nan)
    n_hors = np.zeros(n_cmp, dtype=np.int64)
    pire = np.full(n_cmp, "", dtype=object)
    score_pire = np.full(n_cmp, -np.inf)
    for nom in presentes:
        e = ecarts_par_sortie[nom]
        code = np.maximum(code, e.statut)
        n_hors += e.statut >= st.ECART
        m = np.abs(e.marge)
        marge_max = np.fmax(marge_max, m)
        rel_max = np.fmax(rel_max, e.ecart_rel)
        ulp_max = np.fmax(ulp_max, e.ulp)
        # La sortie la plus grave, puis la plus loin de sa tolérance.
        score = e.statut * 1e300 + np.where(np.isnan(m), 0.0, np.minimum(m, 1e299))
        plus = score > score_pire
        pire[plus], score_pire[plus] = nom, score[plus]
    pire[code == st.IDENTIQUE] = ""

    lignes = _table_lignes(ref, tst, entrees, app, pr, pt, code, pire, marge_max, rel_max, ulp_max, n_hors)

    # -- table longue des écarts -------------------------------------------
    morceaux = []
    for nom in presentes:
        e = ecarts_par_sortie[nom]
        a, b = valeurs[nom]
        bilan = next(x for x in bilans if x.nom == nom)
        seuil = spec.tolerance(nom).seuil(np.where(np.isfinite(a.astype(float)), a.astype(float), 0.0)) if bilan.numerique else np.full(n_cmp, np.nan)
        morceaux.append(
            pd.DataFrame(
                {
                    "ligne_ref": pr,
                    "ligne_test": pt,
                    **{c: ref[c].to_numpy()[pr] for c in entrees},
                    "sortie": nom,
                    "reference": a,
                    "test": b,
                    "ecart": e.ecart,
                    "ecart_rel": e.ecart_rel,
                    "ulp": e.ulp,
                    "seuil": seuil,
                    "marge": e.marge,
                    "statut": pd.Series(e.statut).map(st.NOMS).to_numpy(),
                }
            )
        )
    ecarts = (
        pd.concat(morceaux, ignore_index=True)
        if morceaux
        else pd.DataFrame(columns=["ligne_ref", "ligne_test", *entrees, "sortie", "reference", "test", "ecart", "ecart_rel", "ulp", "seuil", "marge", "statut"])
    )

    # -- attribution aux entrées -------------------------------------------
    attributions = _attribuer(ref, entrees, spec, app, pr, ecarts_par_sortie, presentes, code, marge_max, max_niveaux, n_classes)

    # -- structure et avertissements ---------------------------------------
    declarees = set(spec.entrees) | set(spec.sorties)
    types_diff = tuple(
        (c, str(ref[c].dtype), str(tst[c].dtype))
        for c in (*spec.entrees, *presentes)
        if str(ref[c].dtype) != str(tst[c].dtype)
    )
    structure = Structure(
        n_ref=len(ref),
        n_test=len(tst),
        n_appariees=int(app.ref.size),
        n_comparees=int(n_cmp),
        n_absentes=int(app.absentes.size),
        n_en_trop=int(app.en_trop.size),
        n_divergentes=int(app.divergentes.sum()),
        n_cles_dupliquees=app.n_cles_dupliquees,
        meme_ordre=app.meme_ordre,
        sorties_absentes=tuple(s for s in spec.sorties if s not in tst.columns),
        ignorees_ref=tuple(str(c) for c in ref.columns if c not in declarees),
        ignorees_test=tuple(str(c) for c in tst.columns if c not in declarees),
        types_differents=types_diff,
        entrees_en_texte=app.entrees_en_texte,
    )
    avertissements = _avertissements(spec, structure)

    return ResultatIntegration(
        identifiant=identifiant,
        description=description or DESCRIPTION_DEFAUT,
        metadonnees={str(k): str(v) for k, v in (metadonnees or {}).items()},
        specification=spec,
        environnement=environnement,
        empreinte_ref=empreinte_ref,
        empreinte_test=empreinte_test,
        structure=structure,
        sorties=tuple(bilans),
        attributions=attributions,
        lignes=lignes,
        ecarts=ecarts,
        avertissements=avertissements,
    )


def _table_lignes(
    ref: pd.DataFrame,
    tst: pd.DataFrame,
    entrees: list[str],
    app: Appariement,
    pr: NDArray[np.int64],
    pt: NDArray[np.int64],
    code: NDArray[np.int8],
    pire: NDArray[Any],
    marge_max: NDArray[np.float64],
    rel_max: NDArray[np.float64],
    ulp_max: NDArray[np.float64],
    n_hors: NDArray[np.int64],
) -> pd.DataFrame:
    """Une ligne par cas : comparés, divergents, absents du test, puis en trop dans le test."""

    def bloc(
        p_ref: NDArray[np.int64] | None,
        p_test: NDArray[np.int64] | None,
        source: pd.DataFrame,
        p_source: NDArray[np.int64],
        statut: NDArray[np.int8] | int,
        **mesures: Any,
    ) -> pd.DataFrame:
        n = p_source.size
        manque = pd.array([pd.NA] * n, dtype="Int64")
        return pd.DataFrame(
            {
                "ligne_ref": manque if p_ref is None else pd.array(p_ref, dtype="Int64"),
                "ligne_test": manque if p_test is None else pd.array(p_test, dtype="Int64"),
                **{c: source[c].to_numpy()[p_source] for c in entrees},
                "code": np.broadcast_to(np.asarray(statut, dtype=np.int64), (n,)).copy(),
                "sortie_pire": mesures.get("sortie_pire", np.full(n, "", dtype=object)),
                "marge_max": mesures.get("marge_max", np.full(n, np.nan)),
                "ecart_rel_max": mesures.get("ecart_rel_max", np.full(n, np.nan)),
                "ulp_max": mesures.get("ulp_max", np.full(n, np.nan)),
                "n_hors_tolerance": mesures.get("n_hors_tolerance", np.zeros(n, dtype=np.int64)),
            }
        )

    div = app.divergentes
    blocs = [
        bloc(pr, pt, ref, pr, code, sortie_pire=pire, marge_max=marge_max,
             ecart_rel_max=rel_max, ulp_max=ulp_max, n_hors_tolerance=n_hors),
        bloc(app.ref[div], app.test[div], ref, app.ref[div], st.ENTREES_DIVERGENTES),
        bloc(app.absentes, None, ref, app.absentes, st.ABSENTE),
        bloc(None, app.en_trop, tst, app.en_trop, st.EN_TROP),
    ]
    lignes = pd.concat([b for b in blocs if len(b)] or blocs[:1], ignore_index=True)
    lignes.insert(len(entrees) + 2, "statut", lignes["code"].map(st.NOMS))
    return lignes.sort_values(
        ["ligne_ref", "ligne_test"], na_position="last", kind="stable"
    ).reset_index(drop=True)


def _attribuer(
    ref: pd.DataFrame,
    entrees: list[str],
    spec: Specification,
    app: Appariement,
    pr: NDArray[np.int64],
    ecarts_par_sortie: Mapping[str, Ecarts],
    presentes: list[str],
    code: NDArray[np.int8],
    marge_max: NDArray[np.float64],
    max_niveaux: int,
    n_classes: int,
) -> tuple[AttributionEntree, ...]:
    """Liaison de chaque entrée avec l'échec, sur **toutes** les lignes de référence.

    Une ligne absente du test (le cas a planté, ou n'a pas été lancé) ou aux
    entrées divergentes compte comme en échec, pour chaque sortie : c'est
    souvent l'échec le plus localisé de tous.
    """
    n = len(ref)
    perdue = np.zeros(n, dtype=bool)
    perdue[app.absentes] = True
    perdue[app.ref[app.divergentes]] = True
    absente = np.zeros(n, dtype=bool)
    absente[app.absentes] = True

    echec = perdue.copy()
    echec[pr] |= code >= st.ECART
    marge = np.full(n, np.nan)
    marge[pr] = marge_max
    echec_sortie = {}
    for nom in presentes:
        e = perdue.copy()
        e[pr] |= ecarts_par_sortie[nom].statut >= st.ECART
        echec_sortie[nom] = e

    resultat = []
    for nom in entrees:
        d = discretiser(_valeurs(ref[nom]), max_niveaux=max_niveaux, n_classes=n_classes)
        n_niv, n_ech = comptes_par_niveau(d.codes, echec, d.n_niveaux)
        _, n_abs = comptes_par_niveau(d.codes, absente, d.n_niveaux)
        niveaux = []
        for k, libelle in enumerate(d.libelles):
            dans = d.codes == k
            m = marge[dans]
            m = m[~np.isnan(m)]
            niveaux.append(
                Niveau(
                    libelle=libelle,
                    n=int(n_niv[k]),
                    n_echecs=int(n_ech[k]),
                    n_absentes=int(n_abs[k]),
                    marge_max=float(m.max()) if m.size else math.nan,
                )
            )
        resultat.append(
            AttributionEntree(
                entree=nom,
                en_classes=d.en_classes,
                niveaux=tuple(niveaux),
                v=v_cramer(d.codes, echec, d.n_niveaux),
                v_par_sortie={s: v_cramer(d.codes, echec_sortie[s], d.n_niveaux) for s in presentes},
            )
        )
    return tuple(resultat)


def _avertissements(spec: Specification, s: Structure) -> tuple[str, ...]:
    av = []
    par_defaut = [n for n, t in spec.tolerances.items() if t.origine == ORIGINE_DEFAUT]
    if par_defaut:
        t = spec.tolerances[par_defaut[0]]
        av.append(
            f"tolérance par défaut ({t.decrire()}) pour {', '.join(par_defaut)} : "
            "elle n'a pas été déclarée, donc pas justifiée"
        )
    sans_justif = [
        n for n, t in spec.tolerances.items() if t.origine != ORIGINE_DEFAUT and not t.justification
    ]
    if sans_justif:
        av.append(f"tolérance déclarée sans justification pour {', '.join(sans_justif)}")
    if not spec.entrees:
        av.append(
            "aucune entrée déclarée : les lignes sont appariées dans l'ordre, sans vérification — "
            "un cas manquant ou permuté décale toutes les lignes suivantes, qui sortent alors "
            "toutes en écart ; déclarer les entrées quand elles existent"
        )
    if s.n_cles_dupliquees:
        av.append(
            f"{s.n_cles_dupliquees} ligne(s) de référence répètent une combinaison d'entrées déjà vue : "
            "appariées dans l'ordre d'apparition — une entrée n'aurait-elle pas été déclarée ?"
        )
    if s.entrees_en_texte:
        av.append(
            f"entrée(s) numérique(s) d'un côté seulement, appariée(s) comme texte : {', '.join(s.entrees_en_texte)}"
        )
    for c, a, b in s.types_differents:
        av.append(f"type de « {c} » différent : {a} (référence) contre {b} (test)")
    if s.ignorees_test:
        av.append(f"colonne(s) du test non déclarée(s), ignorée(s) : {', '.join(s.ignorees_test)}")
    if spec.entrees and s.n_ref < EFFECTIF_MIN_ATTRIBUTION:
        av.append(
            f"{s.n_ref} lignes de référence : en dessous de {EFFECTIF_MIN_ATTRIBUTION}, "
            "le V de Cramér classe mal les entrées — lire les taux par niveau"
        )
    return tuple(av)

