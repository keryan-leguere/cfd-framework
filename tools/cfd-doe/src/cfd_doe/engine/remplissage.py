"""Remplir les sous-domaines : de l'étude réduite au DOE prêt à lancer.

Chaque méthode de 00_DOC/02_REMPLISSAGE.md est un *constructeur de plan* : il
propose des points dans le repère de travail, et le socle commun décide de
leur sort —

1. un point n'est gardé que s'il tombe dans un **sous-domaine** de la
   réduction (sinon il est l'image d'un autre par une symétrie, ou il est hors
   des contraintes) ;
2. les **exclusions** de l'utilisateur l'écartent éventuellement ;
3. un même point demandé par deux tables n'est compté qu'une fois.

Le résultat, :class:`PlanDOE`, porte pour chaque point son **rôle** (``calcul``,
``controle``, ``test``), sa **table** et son sous-domaine, plus la démarche à
suivre : c'est ce que le rapport affiche et ce que ``doe.csv`` contient.
"""

from __future__ import annotations

import csv
import math
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations, product
from pathlib import Path
from typing import Any

import numpy as np

from cfd_doe.core import plans as generateurs
from cfd_doe.core.angles import (
    braquages_engin,
    braquages_mixtes,
    normaliser_angle,
    vers_alpha_beta,
    vers_alphat_phia,
)
from cfd_doe.core.domaine_fondamental import Disque
from cfd_doe.core.expression import Condition, compiler
from cfd_doe.core.intervalle import Intervalle
from cfd_doe.data.remplissage import (
    ErreurRemplissage,
    Parametre,
    PlanSpec,
    Remplissage,
    resoudre_niveaux,
)
from cfd_doe.data.variables import SYMBOLES
from cfd_doe.engine.reduction import Reduction, SousDomaine, reduire, symetries_exportees

__all__ = [
    "ROLES",
    "Bloc",
    "Contexte",
    "PlanDOE",
    "PointDOE",
    "Resultat",
    "code_table",
    "colonnes_csv",
    "ecrire_csv",
    "preparer",
    "remplir",
]

ROLE_CALCUL, ROLE_CONTROLE, ROLE_TEST = "calcul", "controle", "test"
ROLES: tuple[str, ...] = (ROLE_CALCUL, ROLE_CONTROLE, ROLE_TEST)

#: Part du budget placée sur les plans de symétrie par les plans tirés (§2.4, §7.2).
PART_PLANS = 0.25
#: Part de points de test indépendants des plans à métamodèle (§7.3).
PART_TEST = 0.15


@dataclass(frozen=True)
class PointDOE:
    """Un calcul CFD à lancer."""

    valeurs: dict[str, float]
    role: str
    table: str
    sous_domaine: int
    fidelite: str = ""


@dataclass(frozen=True)
class Bloc:
    """Une table du plan : son nom, son rôle, ce qu'elle balaie."""

    nom: str
    role: str
    detail: str = ""


@dataclass(frozen=True)
class Contexte:
    """Ce que tous les plans partagent : domaine, grille de référence, conditions."""

    remplissage: Remplissage
    reduction: Reduction
    variables: tuple[str, ...]
    libres: tuple[str, ...]
    boite: dict[str, Intervalle]
    niveaux: dict[str, tuple[float, ...]]
    reference: dict[str, float]
    retournees: frozenset[str]
    notes: tuple[str, ...]
    #: Le groupe complet, identité exclue (voir ``symetries_exportees``).
    symetries: tuple[dict[str, Any], ...] = ()

    @property
    def machs(self) -> tuple[float, ...]:
        """Les Mach du plan (vide : pas de colonne Mach)."""
        return self.remplissage.mach

    @property
    def parametres(self) -> tuple[Parametre, ...]:
        """Les paramètres indépendants."""
        return self.remplissage.parametres

    @property
    def colonnes(self) -> tuple[str, ...]:
        """Colonnes numériques d'un point : Mach, paramètres, variables du repère de travail."""
        mach = ("mach",) if self.machs else ()
        return (*mach, *(p.nom for p in self.parametres), *self.variables)

    @property
    def sous_domaines(self) -> tuple[SousDomaine, ...]:
        """Les sous-domaines de la réduction."""
        return self.reduction.sous_domaines

    @property
    def ordre_groupe(self) -> int:
        """Facteur de réduction du volume par les symétries (1 si aucune, ou révolution)."""
        return self.reduction.ordre_groupe or 1

    def placer(self, point: Mapping[str, float]) -> int | None:
        """Numéro du sous-domaine qui contient le point, ou ``None``."""
        for sd in self.sous_domaines:
            if sd.contient(point):
                return sd.numero
        return None

    def replier(self, point: Mapping[str, float]) -> tuple[dict[str, float], int] | None:
        """Le représentant du point dans les sous-domaines, et son numéro.

        Un point hors des sous-domaines y est ramené par la symétrie qui
        convient ; c'est le même calcul CFD, au signe de quelques coefficients
        près. En polaire, sur l'axe αt = 0, φa n'est qu'une convention : le
        point est ramené à φa = 0, braquages tournés en repère engin (§2.5).
        ``None`` si aucune image ne tombe dans un sous-domaine (hors contraintes).
        """
        images = [dict(point), *(_image(s, point) for s in self.symetries)]
        for image in images:
            numero = self.placer(image)
            if numero is not None:
                return image, numero
        if "alphat" in point and abs(point["alphat"]) <= 1e-9:
            for image in images:
                dm, dn = braquages_engin(image["DMB"], image["DNB"], image["phia"])
                ramene = {**image, "phia": 0.0, "DMB": dm, "DNB": dn}
                numero = self.placer(ramene)
                if numero is not None:
                    return ramene, numero
        return None

    def symbole(self, nom: str) -> str:
        """α, δm… ou le nom du paramètre."""
        return SYMBOLES.get(nom, nom)


def _image(symetrie: Mapping[str, Any], point: Mapping[str, float]) -> dict[str, float]:
    """L'image d'un point par une symétrie de l'export."""
    image = {v: (-x if v in symetrie["variables"] else x) for v, x in point.items()}
    action = symetrie.get("phia")
    if action and "phia" in image:
        if "rotation" in action:
            image["phia"] = normaliser_angle(point["phia"] + action["rotation"])
        else:
            image["phia"] = normaliser_angle(2.0 * action["miroir"] - point["phia"])
    return image


@dataclass(frozen=True)
class PlanDOE:
    """Un plan construit : ses points, ses tables, sa démarche."""

    spec: PlanSpec
    titre: str
    hypothese: str
    table_directe: str
    blocs: tuple[Bloc, ...]
    points: tuple[PointDOE, ...]
    demarche: tuple[str, ...]
    avertissements: tuple[str, ...] = ()
    #: Facteurs continus d'un plan à métamodèle (vide pour un plan sur grille).
    facteurs: tuple[str, ...] = ()
    #: Points écartés par les exclusions de l'utilisateur.
    exclus: int = 0

    @property
    def nom(self) -> str:
        """Le nom donné par l'utilisateur."""
        return self.spec.nom

    def compter(self, role: str | None = None, fidelite: str | None = None) -> int:
        """Nombre de calculs, éventuellement d'un rôle ou d'une fidélité."""
        return sum(
            (role is None or p.role == role) and (fidelite is None or p.fidelite == fidelite)
            for p in self.points
        )

    def par_bloc(self) -> list[tuple[Bloc, int]]:
        """(table, nombre de calculs), dans l'ordre de construction."""
        comptes = Counter((p.role, p.table) for p in self.points)
        return [(b, comptes[(b.role, b.nom)]) for b in self.blocs]

    def par_mach(self) -> dict[float, int]:
        """Mach → nombre de calculs (vide sans Mach)."""
        comptes: Counter[float] = Counter(
            p.valeurs["mach"] for p in self.points if "mach" in p.valeurs
        )
        return dict(sorted(comptes.items()))

    def par_sous_domaine(self) -> dict[int, int]:
        """Numéro de sous-domaine → nombre de calculs."""
        return dict(sorted(Counter(p.sous_domaine for p in self.points).items()))

    @property
    def fidelites(self) -> tuple[str, ...]:
        """Les niveaux de fidélité présents (vide en mono-fidélité)."""
        return tuple(sorted({p.fidelite for p in self.points if p.fidelite}))


@dataclass(frozen=True)
class Resultat:
    """Tous les plans demandés, sur un même contexte."""

    contexte: Contexte
    plans: tuple[PlanDOE, ...]

    @property
    def retenu(self) -> PlanDOE:
        """Le plan qui part dans le fichier DOE."""
        return self.plan(self.contexte.remplissage.retenu)

    def plan(self, nom: str) -> PlanDOE:
        """Un plan par son nom."""
        for p in self.plans:
            if p.nom == nom:
                return p
        raise KeyError(nom)


# ---------------------------------------------------------------------------
# Contexte
# ---------------------------------------------------------------------------


def preparer(remplissage: Remplissage) -> Contexte:
    """Réduit l'étude et résout la grille de référence."""
    reduction = reduire(remplissage.etude)
    variables = reduction.variables
    symetries = tuple(symetries_exportees(reduction))
    retournees = frozenset(v for s in symetries for v in s["variables"])

    boite: dict[str, Intervalle] = {}
    for v in variables:
        bas = min(sd.bornes[v].bas for sd in reduction.sous_domaines)
        haut = max(sd.bornes[v].haut for sd in reduction.sous_domaines)
        if v in retournees:
            bas, haut = -max(abs(bas), abs(haut)), max(abs(bas), abs(haut))
        boite[v] = Intervalle(bas, haut)
    libres = tuple(v for v in variables if not boite[v].est_point)
    reference = {v: 0.0 if boite[v].contient(0.0) else boite[v].bas for v in variables}

    niveaux: dict[str, tuple[float, ...]] = {}
    notes: list[str] = []
    autres = sorted(set(remplissage.niveaux) - set(variables))
    if autres:
        # Un même fichier peut porter les niveaux des deux repères.
        notes.append(
            f"niveaux de {', '.join(autres)} ignorés : ces variables ne sont pas celles du "
            f"repère {reduction.repere} ({', '.join(variables)})"
        )
    for v in variables:
        if v in libres:
            niveaux[v], ajouts = resoudre_niveaux(
                v,
                remplissage.niveaux.get(v),
                boite[v],
                symetrique=v in retournees,
                reference=reference[v],
            )
            notes += ajouts
        else:
            niveaux[v] = (reference[v],)
            if v in remplissage.niveaux:
                notes.append(f"{v} : fixée à {reference[v]:g} par la réduction, niveaux ignorés")
    return Contexte(
        remplissage=remplissage,
        reduction=reduction,
        variables=variables,
        libres=libres,
        boite=boite,
        niveaux=niveaux,
        reference=reference,
        retournees=retournees,
        notes=tuple(notes),
        symetries=symetries,
    )


# ---------------------------------------------------------------------------
# Socle commun des constructeurs
# ---------------------------------------------------------------------------


#: Grandeurs de l'autre repère, utilisables dans « exclure » : une condition
#: écrite en (α, β) reste valable si l'étude passe en polaire, et inversement.
_DERIVEES = {
    "cartesien": frozenset({"alphat", "phia", "DMB", "DNB"}),
    "polaire": frozenset({"alpha", "beta", "DM", "DN"}),
}


def _derivees(repere: str, valeurs: Mapping[str, float]) -> dict[str, float]:
    """Le point dans l'autre repère (§2.2, §7.1)."""
    if repere == "polaire":
        alpha, beta = vers_alpha_beta(valeurs["alphat"], valeurs["phia"])
        dm, dn = braquages_engin(valeurs["DMB"], valeurs["DNB"], valeurs["phia"])
        return {"alpha": alpha, "beta": beta, "DM": dm, "DN": dn}
    alphat, phia = vers_alphat_phia(valeurs["alpha"], valeurs["beta"])
    dmb, dnb = braquages_mixtes(valeurs["DM"], valeurs["DN"], phia)
    return {"alphat": alphat, "phia": phia, "DMB": dmb, "DNB": dnb}


#: Variables de l'autre repère, et leur équivalent dans chaque sens.
_AUTRE_REPERE = {
    "cartesien": frozenset({"alphat", "phia", "DMB", "DNB"}),
    "polaire": frozenset({"alpha", "beta", "DM", "DN"}),
}
_PAIRES_REPERES = (("alpha", "alphat"), ("beta", "phia"), ("DM", "DMB"), ("DN", "DNB"))
_EQUIVALENT = {**dict(_PAIRES_REPERES), **{b: a for a, b in _PAIRES_REPERES}}


class _Chantier:
    """Un plan en construction : points dédoublonnés, tables, exclusions."""

    def __init__(self, contexte: Contexte, spec: PlanSpec) -> None:
        self.c = contexte
        self.spec = spec
        self.points: dict[tuple[Any, ...], PointDOE] = {}
        self.blocs: list[Bloc] = []
        self.avertissements: list[str] = []
        self.exclus = 0
        noms = frozenset(contexte.colonnes) | _DERIVEES[contexte.reduction.repere]
        textes = (*contexte.remplissage.exclure, *spec.exclure)
        try:
            self.exclusions: list[Condition] = [compiler(t, noms) for t in textes]
        except ValueError as erreur:
            raise ErreurRemplissage(f"exclure : {erreur}") from None

    # --- options -------------------------------------------------------------

    def option(self, cle: str, defaut: Any) -> Any:
        valeur = self.spec.options.get(cle)
        return defaut if valeur is None else valeur

    def entier(self, cle: str, defaut: int, minimum: int = 0) -> int:
        try:
            valeur = int(self.option(cle, defaut))
        except (TypeError, ValueError):
            raise ErreurRemplissage(f"plan {self.spec.nom} : {cle} doit être un entier") from None
        if valeur < minimum:
            raise ErreurRemplissage(f"plan {self.spec.nom} : {cle} ≥ {minimum} attendu")
        return valeur

    def reel(self, cle: str, defaut: float, bas: float = 0.0, haut: float = math.inf) -> float:
        try:
            valeur = float(self.option(cle, defaut))
        except (TypeError, ValueError):
            raise ErreurRemplissage(f"plan {self.spec.nom} : {cle} doit être un nombre") from None
        if not bas <= valeur <= haut:
            raise ErreurRemplissage(
                f"plan {self.spec.nom} : {cle} = {valeur:g} hors de [{bas:g} ; {haut:g}]"
            )
        return valeur

    def niveaux(self) -> dict[str, tuple[float, ...]]:
        """La grille de référence, surchargée par l'option ``niveaux`` du plan."""
        surcharge = self.option("niveaux", {})
        if not isinstance(surcharge, Mapping):
            raise ErreurRemplissage(f"plan {self.spec.nom} : niveaux doit être un dictionnaire")
        autres = sorted(set(surcharge) & _AUTRE_REPERE[self.c.reduction.repere])
        if autres:
            self.avertissements.append(
                f"niveaux de {', '.join(autres)} ignorés (repère {self.c.reduction.repere})"
            )
            surcharge = {v: x for v, x in surcharge.items() if v not in autres}
        inconnues = sorted(set(surcharge) - set(self.c.libres))
        if inconnues:
            raise ErreurRemplissage(
                f"plan {self.spec.nom}, niveaux : {', '.join(inconnues)} n'est pas une variable "
                f"libre ({', '.join(self.c.libres)})"
            )
        niveaux = dict(self.c.niveaux)
        for v, spec in surcharge.items():
            niveaux[v], notes = resoudre_niveaux(
                v,
                spec,
                self.c.boite[v],
                symetrique=v in self.c.retournees,
                reference=self.c.reference[v],
            )
            self.avertissements += notes
        return niveaux

    # --- points --------------------------------------------------------------

    def bloc(self, nom: str, role: str = ROLE_CALCUL, detail: str = "") -> str:
        if not any(b.nom == nom and b.role == role for b in self.blocs):
            self.blocs.append(Bloc(nom, role, detail))
        return nom

    def ajouter(
        self,
        variables: Mapping[str, float],
        parametres: Mapping[str, float] | None = None,
        *,
        table: str,
        role: str = ROLE_CALCUL,
        machs: Sequence[float] | None = None,
        fidelite: str = "",
        replier: bool = False,
    ) -> int:
        """Ajoute le point à chaque Mach ; renvoie le nombre de calculs réellement ajoutés.

        Les variables absentes prennent leur valeur de référence, les paramètres
        absents leur nominal. Un point hors des sous-domaines est **écarté**
        (plans sur grille : son image est un autre nœud de la grille) ou, avec
        ``replier``, **ramené** sur son représentant (plans structurés, dont
        l'image d'un point n'est pas toujours dans le plan).
        """
        angles = {v: float(variables.get(v, self.c.reference[v])) for v in self.c.variables}
        if replier:
            ramene = self.c.replier(angles)
            if ramene is None:
                return 0
            angles, numero = ramene
        else:
            place = self.c.placer(angles)
            if place is None:
                return 0
            numero = place
        params = {p.nom: float((parametres or {}).get(p.nom, p.nominal)) for p in self.c.parametres}
        ajoutes = 0
        for mach in self.c.machs if machs is None else machs:
            valeurs = {"mach": float(mach), **params, **angles}
            ajoutes += self._inscrire(valeurs, role, table, numero, fidelite)
        if not self.c.machs:
            ajoutes += self._inscrire({**params, **angles}, role, table, numero, fidelite)
        return ajoutes

    def _inscrire(
        self, valeurs: dict[str, float], role: str, table: str, numero: int, fidelite: str
    ) -> int:
        if self.exclusions:
            visibles = {**valeurs, **_derivees(self.c.reduction.repere, valeurs)}
            if any(condition(visibles) for condition in self.exclusions):
                self.exclus += 1
                return 0
        cle = (fidelite, *(round(valeurs[col], 9) + 0.0 for col in self.c.colonnes))
        if cle in self.points:
            return 0
        self.points[cle] = PointDOE(valeurs, role, table, numero, fidelite)
        return 1

    def contient(
        self, variables: Mapping[str, float], parametres: Mapping[str, float], mach: float | None
    ) -> bool:
        """Le point est-il déjà dans le plan (à ce Mach) ?"""
        valeurs = {**parametres, **variables}
        if mach is not None:
            valeurs["mach"] = mach
        return ("", *(round(valeurs[col], 9) + 0.0 for col in self.c.colonnes)) in self.points

    def conditions(self) -> list[float | None]:
        """Les Mach, ou une condition unique sans Mach."""
        return list(self.c.machs) if self.c.machs else [None]

    def par_condition(self, role: str = ROLE_CALCUL) -> int:
        """Calculs du rôle au premier Mach (référence pour dimensionner contrôle et test)."""
        if not self.c.machs:
            return sum(p.role == role for p in self.points.values())
        mach = self.c.machs[0]
        return sum(p.role == role and p.valeurs["mach"] == mach for p in self.points.values())

    def clore(
        self,
        titre: str,
        hypothese: str,
        table_directe: str,
        demarche: Sequence[str],
        facteurs: Sequence[str] = (),
    ) -> PlanDOE:
        if self.exclus:
            self.avertissements.append(f"{self.exclus} point(s) écarté(s) par « exclure »")
        if not self.points:
            self.avertissements.append("aucun point : vérifier les niveaux et les exclusions")
        return PlanDOE(
            spec=self.spec,
            titre=titre,
            hypothese=hypothese,
            table_directe=table_directe,
            blocs=tuple(self.blocs),
            points=tuple(self.points.values()),
            demarche=tuple(demarche),
            avertissements=tuple(dict.fromkeys(self.avertissements)),
            facteurs=tuple(facteurs),
            exclus=self.exclus,
        )


def _liste(c: Contexte, noms: Iterable[str]) -> str:
    return ", ".join(c.symbole(n) for n in noms)


def _n(x: int) -> str:
    return f"{x:,}".replace(",", chr(0x202F))


# ---------------------------------------------------------------------------
# Plans sur grille
# ---------------------------------------------------------------------------


def _factoriel(ch: _Chantier) -> PlanDOE:
    c = ch.c
    niveaux = ch.niveaux()
    inegaux = any(niveaux[v] != c.niveaux[v] for v in c.libres)
    table = ch.bloc("factoriel", detail=f"tous les nœuds de ({_liste(c, c.libres)})")
    combinaisons = list(product(*(p.niveaux for p in c.parametres)))
    for noeud in product(*(niveaux[v] for v in c.libres)):
        angles = dict(zip(c.libres, noeud))
        for combinaison in combinaisons:
            ch.ajouter(angles, dict(zip((p.nom for p in c.parametres), combinaison)), table=table)
    n = len(ch.points)
    return ch.clore(
        "Factoriel, niveaux inégaux" if inegaux else "Factoriel complet",
        "linéaire par morceaux entre les niveaux retenus"
        if inegaux
        else "aucune, au-delà du pas de grille",
        "oui",
        [
            f"Lancer les {_n(n)} calculs (rôle « calcul »).",
            "Compléter la table par symétrie (01_EXEMPLE/completer_table.py) : elle est "
            "directement lisible par le simulateur.",
            *(
                [
                    "Contrôler la linéarité supposée : quelques polaires à niveaux fins sur les "
                    "variables allégées, à deux ou trois Mach."
                ]
                if inegaux
                else []
            ),
        ],
    )


def _etoile(ch: _Chantier) -> PlanDOE:
    c = ch.c
    niveaux = ch.niveaux()
    ch.ajouter({}, table=ch.bloc("centre", detail="tout à la référence"))
    for v in c.libres:
        table = ch.bloc(f"balayage {c.symbole(v)}", detail="les autres variables à la référence")
        for x in niveaux[v]:
            ch.ajouter({v: x}, table=table)
    for p in c.parametres:
        table = ch.bloc(f"balayage {p.nom}", detail="angles à la référence")
        for x in p.niveaux:
            ch.ajouter({}, {p.nom: x}, table=table)
    return ch.clore(
        "Étoile : un facteur à la fois",
        "tous les effets s'ajoutent, incidence comprise",
        "non",
        [
            f"Lancer les {_n(len(ch.points))} calculs.",
            "Lire chaque balayage : quelles variables comptent, où sont les non-linéarités.",
            "Ne pas en tirer une base aéro : c'est un dégrossissage, qui sert à choisir les "
            "niveaux et les couplages d'un plan sérieux (décomposition, factoriel).",
        ],
    )


# ---------------------------------------------------------------------------
# Décomposition
# ---------------------------------------------------------------------------


def _noms(ch: _Chantier, cle: str, valeur: object, admis: Sequence[str]) -> tuple[str, ...]:
    if isinstance(valeur, str):
        valeur = [valeur]
    if not isinstance(valeur, (list, tuple)):
        raise ErreurRemplissage(f"plan {ch.spec.nom} : {cle} doit être une liste de noms")
    # Un effet nommé dans l'autre repère désigne son équivalent : DM ↔ DMB, alpha ↔ alphat.
    noms = tuple(_EQUIVALENT.get(str(v), str(v)) if str(v) not in admis else str(v) for v in valeur)
    inconnus = [n for n in noms if n not in admis]
    if inconnus:
        raise ErreurRemplissage(
            f"plan {ch.spec.nom}, {cle} : {', '.join(inconnus)} inconnu(s) ; "
            f"admis : {', '.join(admis)}"
        )
    return noms


def _decomposition(ch: _Chantier) -> PlanDOE:
    c = ch.c
    niveaux = ch.niveaux()
    ordre = ch.entier("ordre", 1, minimum=1)
    if ordre > 2:
        raise ErreurRemplissage(f"plan {ch.spec.nom} : ordre 1 ou 2")
    primaires = _noms(ch, "primaires", ch.option("primaires", c.libres[:2]), c.libres)
    croises = _noms(ch, "croiser", ch.option("croiser", ()), [p.nom for p in c.parametres])
    parametres = {p.nom: p for p in c.parametres}
    effets = [v for v in c.libres if v not in primaires]
    effets += [p.nom for p in c.parametres if p.nom not in croises]

    def non_reference(effet: str) -> tuple[float, ...]:
        if effet in parametres:
            p = parametres[effet]
            return tuple(x for x in p.niveaux if abs(x - p.nominal) > 1e-9)
        return tuple(x for x in niveaux[effet] if abs(x - c.reference[effet]) > 1e-9)

    # De quoi dépend chaque incrément.
    defaut_variables = primaires if ordre == 2 else primaires[:1]
    globale = ch.spec.options.get("increments_fonction_de")
    if globale is not None:
        defaut_variables = _noms(ch, "increments_fonction_de", globale, primaires)
    particuliers = ch.option("increments", {})
    if not isinstance(particuliers, Mapping):
        raise ErreurRemplissage(f"plan {ch.spec.nom} : increments doit associer effet → variables")
    particuliers = {
        _noms(ch, "increments", [effet], effets)[0]: dependances
        for effet, dependances in particuliers.items()
    }
    fonction_de = {
        e: _noms(ch, f"increments.{e}", particuliers[e], primaires)
        if e in particuliers
        else (primaires if e in parametres else defaut_variables)
        for e in effets
    }

    combinaisons_croisees = list(product(*(parametres[n].niveaux for n in croises)))

    def table(nom: str, axes: Mapping[str, Sequence[float]], detail: str) -> None:
        """Produit des axes (variables et paramètres), le reste à la référence."""
        nom = ch.bloc(nom, detail=detail)
        noms_axes = list(axes)
        for noeud in product(*axes.values()):
            valeurs = dict(zip(noms_axes, noeud))
            angles = {k: x for k, x in valeurs.items() if k not in parametres}
            params = {k: x for k, x in valeurs.items() if k in parametres}
            for combinaison in combinaisons_croisees:
                ch.ajouter(angles, {**params, **dict(zip(croises, combinaison))}, table=nom)

    table(
        "base",
        {v: niveaux[v] for v in primaires},
        f"({_liste(c, primaires)}), effets à la référence",
    )
    for e in effets:
        if not non_reference(e):
            continue
        axes = {**{v: niveaux[v] for v in fonction_de[e]}, e: non_reference(e)}
        table(f"Δ{c.symbole(e)}", axes, f"({_liste(c, axes)}), {c.symbole(e)} seul")

    # Couplages : paires d'effets braqués ensemble.
    demande = ch.option("couplages", "tous" if ordre == 2 else [])
    paires: list[tuple[tuple[str, str], tuple[str, ...]]] = []
    if demande == "tous":
        paires = [((a, b), primaires[:1]) for a, b in combinations(effets, 2)]
    elif isinstance(demande, (list, tuple)):
        for element in demande:
            dependances: object = primaires[:1]
            if isinstance(element, Mapping):
                if set(element) - {"paire", "fonction_de"} or "paire" not in element:
                    raise ErreurRemplissage(
                        f"plan {ch.spec.nom}, couplages : {{paire: [a, b], fonction_de: […]}}"
                    )
                dependances = element.get("fonction_de", dependances)
                element = element["paire"]
            paire = _noms(ch, "couplages", element, effets)
            if len(paire) != 2 or paire[0] == paire[1]:
                raise ErreurRemplissage(f"plan {ch.spec.nom}, couplages : paires de deux effets")
            paires.append(((paire[0], paire[1]), _noms(ch, "couplages", dependances, primaires)))
    else:
        raise ErreurRemplissage(f"plan {ch.spec.nom} : couplages = « tous » ou une liste de paires")
    for (a, b), dependances in paires:
        if not non_reference(a) or not non_reference(b):
            continue
        axes = {**{v: niveaux[v] for v in dependances}, a: non_reference(a), b: non_reference(b)}
        table(
            f"Δ{c.symbole(a)}×{c.symbole(b)}",
            axes,
            f"({_liste(c, axes)}), {c.symbole(a)} et {c.symbole(b)} ensemble",
        )

    n_calcul = len(ch.points)
    n_controle = _controle_croise(ch, niveaux, effets, parametres)

    hypotheses = (
        "aucune interaction entre effets"
        if not paires
        else "interactions limitées aux couplages retenus"
    )
    independants = [
        c.symbole(e) for e in effets if e not in parametres and len(fonction_de[e]) < len(primaires)
    ]
    if independants:
        autres = [
            v
            for v in primaires
            if any(v not in fonction_de[e] for e in effets if e not in parametres)
        ]
        hypotheses += (
            f" ; incréments de {', '.join(independants)} indépendants de {_liste(c, autres)}"
        )
    demarche = [
        f"Lancer les {_n(n_calcul)} calculs « calcul » : la base, puis une table par effet.",
        "Compléter chaque table par symétrie (completer_table.py), puis former les incréments "
        "par différence : ΔC = C(effet braqué) − C(base au même point).",
    ]
    if n_controle:
        demarche += [
            f"Lancer les {_n(n_controle)} calculs « controle » : des nœuds où plusieurs effets "
            "sont actifs à la fois, que la décomposition reconstruit sans les avoir calculés.",
            "Comparer chaque contrôle à la somme base + incréments, coefficient par "
            "coefficient. L'écart mesure l'erreur d'additivité.",
            "Écart sous l'incertitude CFD : la décomposition est validée. Sinon, repérer la "
            "paire d'effets en cause et l'ajouter à « couplages », puis relancer ce plan : "
            "seule la nouvelle table est à calculer.",
        ]
    else:
        demarche.append(
            "Aucun point de contrôle demandé : l'additivité reste une hypothèse non vérifiée "
            "(controle: {fraction: 0.15} pour en ajouter)."
        )
    demarche.append(
        "Livrer les tables d'incréments (le simulateur fait la somme), ou la table carrée "
        "reconstruite par somme, avec une colonne d'origine."
    )
    return ch.clore(f"Décomposition, ordre {ordre}", hypotheses, "oui, par somme", demarche)


def _controle_croise(
    ch: _Chantier,
    niveaux: Mapping[str, tuple[float, ...]],
    effets: Sequence[str],
    parametres: Mapping[str, Parametre],
) -> int:
    """Tire des nœuds de la grille où au moins deux effets sont actifs, hors du plan."""
    c = ch.c
    demande = ch.option("controle", {})
    if demande is False or demande == 0:
        return 0
    if demande is True:
        demande = {}
    if isinstance(demande, (int, float)):
        demande = {"fraction": demande}
    if not isinstance(demande, Mapping) or set(demande) - {"fraction", "minimum", "graine"}:
        raise ErreurRemplissage(
            f"plan {ch.spec.nom} : controle = {{fraction: …, minimum: …, graine: …}} ou false"
        )
    fraction = float(demande.get("fraction", 0.15))
    if fraction <= 0:
        return 0
    cible = max(int(demande.get("minimum", 5)), math.ceil(fraction * ch.par_condition()))
    rng = np.random.default_rng(int(demande.get("graine", 0)))

    candidats: list[tuple[dict[str, float], dict[str, float]]] = []
    noms_params = [p.nom for p in c.parametres]
    for noeud in product(*(niveaux[v] for v in c.libres)):
        angles = dict(zip(c.libres, noeud))
        if c.placer({**c.reference, **angles}) is None:
            continue
        for combinaison in product(*(p.niveaux for p in c.parametres)):
            params = dict(zip(noms_params, combinaison))
            actifs = sum(
                abs(params[e] - parametres[e].nominal) > 1e-9
                if e in parametres
                else abs(angles[e] - c.reference[e]) > 1e-9
                for e in effets
            )
            if actifs >= 2:
                candidats.append((angles, params))
    if not candidats:
        ch.avertissements.append("contrôle : aucun nœud où deux effets sont actifs ensemble")
        return 0

    table = ch.bloc(
        "contrôle croisé",
        ROLE_CONTROLE,
        f"nœuds de la grille, ≥ 2 effets actifs, {cible} par Mach",
    )
    total = 0
    for mach in ch.conditions():
        ajoutes = 0
        for i in rng.permutation(len(candidats)):
            if ajoutes >= cible:
                break
            angles, params = candidats[int(i)]
            if ch.contient({**c.reference, **angles}, params, mach):
                continue
            ajoutes += ch.ajouter(
                angles,
                params,
                table=table,
                role=ROLE_CONTROLE,
                machs=None if mach is None else [mach],
            )
        total += ajoutes
    return total


# ---------------------------------------------------------------------------
# Plans à métamodèle : facteurs continus
# ---------------------------------------------------------------------------


def _facteurs(c: Contexte) -> tuple[list[str], list[Parametre], list[Parametre]]:
    """(facteurs continus, paramètres continus, paramètres discrets)."""
    continus = [p for p in c.parametres if p.continu]
    discrets = [p for p in c.parametres if not p.continu]
    return [*c.libres, *(p.nom for p in continus)], continus, discrets


def _combinaisons_discretes(discrets: Sequence[Parametre]) -> list[dict[str, float]]:
    return [
        dict(zip((p.nom for p in discrets), x)) for x in product(*(p.niveaux for p in discrets))
    ]


def _hors_contraintes(c: Contexte, angles: Mapping[str, float]) -> bool:
    """Le point viole-t-il un disque de braquages (aucune symétrie ne l'y ramène) ?"""
    disques = {k for sd in c.sous_domaines for k in sd.contraintes if isinstance(k, Disque)}
    return any(not d.contient(angles) for d in disques)


def _structure(
    ch: _Chantier, bruts: Sequence[tuple[float, ...]], table: str, detail: str
) -> list[str]:
    """Place un plan défini sur [-1, 1]^k ; renvoie les facteurs."""
    c = ch.c
    facteurs, continus, discrets = _facteurs(c)
    plages = {**c.boite, **{p.nom: p.plage for p in continus}}
    # Un plan structuré vit dans un pavé : celui des braquages est inscrit dans le disque.
    for disque in {k for sd in c.sous_domaines for k in sd.contraintes if isinstance(k, Disque)}:
        cote = disque.rayon / math.sqrt(2.0)
        for v in (disque.x, disque.y):
            if plages[v].amplitude > cote + 1e-9:
                plages[v] = Intervalle(-cote, cote)
                ch.avertissements.append(
                    f"{c.symbole(v)} limité à ±{cote:.3g}° : le pavé du plan est inscrit dans le "
                    f"disque des braquages (rayon {disque.rayon:g}°)"
                )
    nom = ch.bloc(table, detail=detail)
    hors = 0
    for u in bruts:
        valeurs = {
            f: (plages[f].bas + plages[f].haut) / 2 + x * plages[f].largeur / 2
            for f, x in zip(facteurs, u)
        }
        angles = {**c.reference, **{f: x for f, x in valeurs.items() if f in c.boite}}
        if _hors_contraintes(c, angles):
            hors += 1
            continue
        params = {f: x for f, x in valeurs.items() if f not in c.boite}
        for combinaison in _combinaisons_discretes(discrets):
            ch.ajouter(angles, {**params, **combinaison}, table=nom, replier=True)
    if hors:
        ch.avertissements.append(
            f"{hors} point(s) du plan sur {len(bruts)} hors du disque des braquages : le plan "
            "est incomplet, le modèle y extrapole"
        )
    return facteurs


def _test(
    ch: _Chantier, facteurs: Sequence[str], fidelite: str = "", base: int | None = None
) -> int:
    """Points de test indépendants (hypercube latin), proportionnels au plan (ou à ``base``)."""
    part = ch.reel("test", PART_TEST, 0.0, 1.0)
    if part <= 0:
        return 0
    n = max(3, math.ceil(part * (ch.par_condition() if base is None else base)))
    graine = ch.entier("graine", 0) + 7919
    decale = bool(ch.option("decale_par_mach", True))
    return _tirage(ch, n, "lhs", graine, ROLE_TEST, "test", 0.0, decale, fidelite)


def _demarche_modele(ch: _Chantier, modele: str, n_test: int) -> list[str]:
    n_calcul = sum(p.role == ROLE_CALCUL for p in ch.points.values())
    etapes = [
        f"Lancer les {_n(n_calcul)} calculs « calcul ».",
        "Donner au modèle les images de chaque point par les symétries (clé « symetries » de "
        "l'export) : il voit plusieurs fois plus de points et respecte les symétries.",
        f"Ajuster {modele}, à chaque Mach.",
    ]
    if n_test:
        etapes += [
            f"Lancer les {_n(n_test)} calculs « test », qui n'ont pas servi à l'ajustement.",
            "Comparer la prédiction du modèle à ces calculs (et en validation croisée) : "
            "c'est la seule mesure de l'erreur de la table.",
        ]
    else:
        etapes.append(
            "Aucun point de test demandé (test: 0.15 pour en ajouter) : valider au moins en "
            "validation croisée."
        )
    etapes.append(
        "Erreur acceptable : évaluer le modèle sur la grille du simulateur pour produire la "
        "table. Sinon : ajouter des points (plan plus riche) et recommencer."
    )
    return etapes


def _composite_centre(ch: _Chantier) -> PlanDOE:
    facteurs, _, _ = _facteurs(ch.c)
    k = len(facteurs)
    if k < 2:
        raise ErreurRemplissage(f"plan {ch.spec.nom} : il faut au moins 2 facteurs continus")
    fraction = ch.entier("fraction", 1 if k >= 5 else 0)
    if fraction not in (0, 1):
        raise ErreurRemplissage(f"plan {ch.spec.nom} : fraction 0 (complet) ou 1 (demi)")
    bruts = generateurs.composite_centre(k, fraction)
    _structure(ch, bruts, "composite centré", f"{len(bruts)} points bruts sur {k} facteurs")
    n_test = _test(ch, facteurs)
    return ch.clore(
        "Composite centré" + (" ½" if fraction else ""),
        "réponse quadratique sur tout le domaine, à chaque Mach",
        "non",
        _demarche_modele(ch, f"un polynôme de degré 2 ({(k + 1) * (k + 2) // 2} termes)", n_test),
        facteurs,
    )


def _box_behnken(ch: _Chantier) -> PlanDOE:
    facteurs, _, _ = _facteurs(ch.c)
    k = len(facteurs)
    if k < 3:
        raise ErreurRemplissage(f"plan {ch.spec.nom} : il faut au moins 3 facteurs continus")
    bruts = generateurs.box_behnken(k)
    _structure(ch, bruts, "Box-Behnken", f"{len(bruts)} points bruts sur {k} facteurs")
    n_test = _test(ch, facteurs)
    return ch.clore(
        "Box-Behnken",
        "réponse quadratique ; les coins du domaine sont extrapolés",
        "non",
        _demarche_modele(ch, f"un polynôme de degré 2 ({(k + 1) * (k + 2) // 2} termes)", n_test),
        facteurs,
    )


def _grille_creuse(ch: _Chantier) -> PlanDOE:
    facteurs, _, _ = _facteurs(ch.c)
    niveau = ch.entier("niveau", 2, minimum=1)
    if niveau > 5:
        raise ErreurRemplissage(f"plan {ch.spec.nom} : niveau ≤ 5")
    bruts = generateurs.grille_creuse(len(facteurs), niveau)
    _structure(
        ch,
        bruts,
        f"grille creuse niveau {niveau}",
        f"{len(bruts)} points bruts sur {len(facteurs)} facteurs",
    )
    n_test = _test(ch, facteurs)
    demarche = _demarche_modele(ch, "l'interpolant creux (base hiérarchique)", n_test)
    demarche.insert(
        3,
        "Regarder les surplus hiérarchiques (écart d'un point à l'interpolant du niveau "
        "précédent) : grands sur un axe, ils disent où raffiner. Le niveau suivant réutilise "
        "tous les calculs.",
    )
    return ch.clore(
        f"Grille creuse, niveau {niveau}",
        "régularité : dérivées croisées bornées",
        "non",
        demarche,
        facteurs,
    )


# ---------------------------------------------------------------------------
# Remplissage d'espace
# ---------------------------------------------------------------------------


def _repartir(total: int, poids: Sequence[float]) -> list[int]:
    """Répartit ``total`` proportionnellement aux poids (plus forts restes)."""
    somme = sum(poids)
    if total <= 0 or somme <= 0:
        return [0] * len(poids)
    parts = [total * w / somme for w in poids]
    entiers = [int(x) for x in parts]
    restes = sorted(range(len(poids)), key=lambda i: parts[i] - entiers[i], reverse=True)
    for i in restes[: total - sum(entiers)]:
        entiers[i] += 1
    return entiers


def _volume(sd: SousDomaine) -> float:
    volume = 1.0
    for intervalle in sd.bornes.values():
        if not intervalle.est_point:
            volume *= intervalle.largeur
    return volume


def _tirer_dans(
    c: Contexte,
    sd: SousDomaine,
    n: int,
    continus: Sequence[Parametre],
    methode: str,
    graine: int,
    essais: int,
) -> list[tuple[dict[str, float], dict[str, float]]]:
    """``n`` points dans un sous-domaine : (variables, paramètres continus)."""
    if n <= 0:
        return []
    libres = [v for v in c.variables if not sd.bornes[v].est_point]
    k = len(libres) + len(continus)
    fixes = {v: sd.bornes[v].bas for v in c.variables if sd.bornes[v].est_point}
    if k == 0:
        return [(dict(fixes), {})]
    m, depart = n, 1 + graine * 1009
    for tentative in range(12):
        if methode == "halton":
            unites = generateurs.halton(m, k, depart)
        else:
            unites = generateurs.hypercube_latin(m, k, graine + tentative, essais)
        gardes = []
        for u in unites:
            angles = dict(fixes)
            for v, x in zip(libres, u):
                b = sd.bornes[v]
                angles[v] = b.bas + x * b.largeur
            if sd.contient(angles):
                params = {
                    p.nom: p.plage.bas + x * p.plage.largeur
                    for p, x in zip(continus, u[len(libres) :])
                }
                gardes.append((angles, params))
        if len(gardes) >= n:
            if len(gardes) == n or methode == "halton":
                return gardes[:n]
            cles = [tuple(a[v] for v in libres) + tuple(p.values()) for a, p in gardes]
            return [gardes[i] for i in sorted(generateurs.sous_ensemble_maximin(cles, n))]
        m = math.ceil(1.3 * m * n / max(len(gardes), 1)) + 1
    return gardes


def _tirage(
    ch: _Chantier,
    n: int,
    methode: str,
    graine: int,
    role: str,
    table: str,
    part_plans: float,
    decale: bool,
    fidelite: str = "",
) -> int:
    """Tire ``n`` points par condition dans les sous-domaines ; renvoie le total ajouté."""
    c = ch.c
    _, continus, discrets = _facteurs(c)
    essais = ch.entier("essais", 50, minimum=1)
    dimension = max(sd.dimension for sd in c.sous_domaines)
    principaux = [sd for sd in c.sous_domaines if sd.dimension == dimension]
    plans = [sd for sd in c.sous_domaines if sd.dimension == dimension - 1] if dimension > 0 else []
    n_plans = round(part_plans * n) if plans else 0
    quotas = [
        *zip(principaux, _repartir(n - n_plans, [_volume(sd) for sd in principaux])),
        *zip(plans, _repartir(n_plans, [_volume(sd) for sd in plans])),
    ]
    oublies = len(c.sous_domaines) - len(principaux) - (len(plans) if n_plans else 0)
    if oublies and role == ROLE_CALCUL:
        ch.avertissements.append(
            f"{oublies} sous-domaine(s) de petite dimension non échantillonné(s) par le tirage "
            "(axes, plans secondaires) : le modèle les atteint par continuité et par les images"
        )
    nom = ch.bloc(
        table,
        role,
        f"{n} par condition, dont {n_plans} sur les plans de symétrie"
        if n_plans
        else f"{n} par condition",
    )
    total, rang = 0, 0
    for mach in ch.conditions():
        for combinaison in _combinaisons_discretes(discrets):
            decalage = rang if decale else 0
            rang += 1
            for sd, quota in quotas:
                tires = _tirer_dans(
                    c, sd, quota, continus, methode, graine + 31 * decalage + sd.numero, essais
                )
                for angles, params in tires:
                    total += ch.ajouter(
                        angles,
                        {**params, **combinaison},
                        table=nom,
                        role=role,
                        machs=None if mach is None else [mach],
                        fidelite=fidelite,
                    )
    return total


def _points_par_condition(
    ch: _Chantier, regle_defaut: float, cle: str = "points_par_mach", cle_regle: str = "regle"
) -> int:
    """Nombre de points par condition : explicite, ou règle « regle · d » divisée par les symétries."""
    c = ch.c
    facteurs, _, _ = _facteurs(c)
    if ch.spec.options.get(cle) is not None:
        return ch.entier(cle, 0, minimum=1)
    regle = ch.reel(cle_regle, regle_defaut, 0.1)
    return max(1, math.ceil(regle * len(facteurs) / c.ordre_groupe))


def _remplissage_espace(ch: _Chantier, methode: str) -> PlanDOE:
    facteurs, _, _ = _facteurs(ch.c)
    n = _points_par_condition(ch, 30.0)
    _tirage(
        ch,
        n,
        methode,
        ch.entier("graine", 0),
        ROLE_CALCUL,
        "hypercube latin" if methode == "lhs" else "suite de Halton",
        ch.reel("part_plans", PART_PLANS, 0.0, 1.0),
        bool(ch.option("decale_par_mach", True)),
    )
    n_test = _test(ch, facteurs)
    return ch.clore(
        "Hypercube latin" if methode == "lhs" else "Suite de Halton",
        "régularité à l'échelle de la distance entre points ; métamodèle validé",
        "non",
        _demarche_modele(ch, "un métamodèle (krigeage par défaut)", n_test),
        facteurs,
    )


def _adaptatif(ch: _Chantier) -> PlanDOE:
    facteurs, _, _ = _facteurs(ch.c)
    n = _points_par_condition(ch, 10.0)
    n_initial = _tirage(
        ch,
        n,
        "lhs",
        ch.entier("graine", 0),
        ROLE_CALCUL,
        "lot initial",
        ch.reel("part_plans", PART_PLANS, 0.0, 1.0),
        bool(ch.option("decale_par_mach", True)),
    )
    n_test = _test(ch, facteurs)
    return ch.clore(
        "Adaptatif (lot initial)",
        "régularité ; la précision vient du critère d'arrêt, non du plan",
        "non",
        [
            f"Lancer le lot initial ({_n(n_initial)} calculs « calcul »)"
            + (f" et les {_n(n_test)} calculs « test »." if n_test else "."),
            "Ajuster un krigeage par Mach, images par symétrie comprises.",
            "Choisir le lot suivant là où le modèle se trompe le plus : variance de "
            "prédiction maximale, ou erreur de validation croisée, agrégée sur les "
            "coefficients (le pire, rapporté à sa tolérance).",
            "Lancer ce lot, réajuster, et recommencer jusqu'à ce que l'erreur sur les points "
            "« test » passe sous la tolérance : c'est ce critère qui fixe le nombre de calculs.",
            "Ce fichier ne contient que le lot initial : les lots d'enrichissement dépendent "
            "des résultats, ils se construisent hors de cfd-doe. Compter en général 1 à 2 fois "
            "le lot initial en plus.",
        ],
        facteurs,
    )


def _multi_fidelite(ch: _Chantier) -> PlanDOE:
    c = ch.c
    facteurs, _, _ = _facteurs(c)
    n_bf = _points_par_condition(ch, 30.0)
    n_hf = _points_par_condition(ch, 8.0, "points_hf_par_mach", "regle_hf")
    n_hf = min(n_hf, n_bf)
    _tirage(
        ch,
        n_bf,
        "lhs",
        ch.entier("graine", 0),
        ROLE_CALCUL,
        "basse fidélité",
        ch.reel("part_plans", PART_PLANS, 0.0, 1.0),
        bool(ch.option("decale_par_mach", True)),
        fidelite="BF",
    )
    # Haute fidélité : sous-plan emboîté, bien réparti, de chaque condition.
    _, _, discrets = _facteurs(c)
    cles_condition = [*(["mach"] if c.machs else []), *(p.nom for p in discrets)]
    par_condition: dict[tuple[float, ...], list[PointDOE]] = {}
    for p in list(ch.points.values()):
        par_condition.setdefault(tuple(p.valeurs[k] for k in cles_condition), []).append(p)
    table = ch.bloc(
        "haute fidélité", detail=f"{n_hf} par condition, emboîtés dans la basse fidélité"
    )
    for groupe in par_condition.values():
        coordonnees = [tuple(p.valeurs[f] for f in facteurs) for p in groupe]
        for i in generateurs.sous_ensemble_maximin(coordonnees, n_hf):
            p = groupe[i]
            ch._inscrire(dict(p.valeurs), ROLE_CALCUL, table, p.sous_domaine, "HF")
    n_test = _test(ch, facteurs, fidelite="HF", base=n_bf)
    bf = sum(p.fidelite == "BF" for p in ch.points.values())
    hf = sum(p.fidelite == "HF" and p.role == ROLE_CALCUL for p in ch.points.values())
    return ch.clore(
        "Multi-fidélité emboîtée",
        "les deux fidélités sont corrélées : leur écart est lisse",
        "non",
        [
            f"Lancer les {_n(bf)} calculs basse fidélité (fidelite = BF) : Euler, RANS grossier…",
            f"Lancer les {_n(hf)} calculs haute fidélité (fidelite = HF). Ce sont des points du "
            "plan BF : chacun est calculé aux deux fidélités, ce qui donne l'écart directement.",
            "Ajuster un co-krigeage par Mach : tendance par la BF, correction par l'écart HF − BF.",
            "Vérifier la corrélation estimée entre fidélités : faible, la BF ne capture pas la "
            "bonne physique (décollement, éclatement tourbillonnaire) et n'apporte rien.",
            *(
                [
                    f"Lancer les {_n(n_test)} calculs « test » haute fidélité et y mesurer l'erreur "
                    "du modèle."
                ]
                if n_test
                else []
            ),
            "Erreur acceptable : évaluer le modèle sur la grille du simulateur. Sinon : ajouter "
            "des points HF là où la variance est forte.",
        ],
        facteurs,
    )


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

_CONSTRUCTEURS = {
    "factoriel": _factoriel,
    "etoile": _etoile,
    "decomposition": _decomposition,
    "composite_centre": _composite_centre,
    "box_behnken": _box_behnken,
    "grille_creuse": _grille_creuse,
    "lhs": lambda ch: _remplissage_espace(ch, "lhs"),
    "halton": lambda ch: _remplissage_espace(ch, "halton"),
    "adaptatif": _adaptatif,
    "multi_fidelite": _multi_fidelite,
}


def remplir(remplissage: Remplissage, seulement: Sequence[str] | None = None) -> Resultat:
    """Construit les plans demandés (ou ``seulement`` ceux nommés)."""
    contexte = preparer(remplissage)
    if not contexte.libres:
        raise ErreurRemplissage("aucune variable libre : rien à remplir (trajectoire 1DOF ?)")
    plans = []
    for spec in remplissage.plans:
        if seulement is not None and spec.nom not in seulement:
            continue
        plans.append(_CONSTRUCTEURS[spec.type](_Chantier(contexte, spec)))
    return Resultat(contexte, tuple(plans))


# ---------------------------------------------------------------------------
# Fichier DOE
# ---------------------------------------------------------------------------


_VERS_ASCII = {
    **{symbole: nom for nom, symbole in sorted(SYMBOLES.items(), key=lambda t: len(t[1]))},
    "Δ": "d_",
    "×": "_x_",
}


def code_table(nom: str) -> str:
    """Le nom d'une table sans caractère spécial, pour le fichier DOE : ``Δδm×δn`` → ``d_DM_x_DN``."""
    for symbole in sorted(_VERS_ASCII, key=len, reverse=True):
        nom = nom.replace(symbole, _VERS_ASCII[symbole])
    nom = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode("ascii")
    return "_".join(nom.split())


def colonnes_csv(plan: PlanDOE, contexte: Contexte) -> list[str]:
    """Les colonnes du fichier DOE, dans l'ordre."""
    colonnes = ["id", "role", "table", "sous_domaine"]
    if plan.fidelites:
        colonnes.append("fidelite")
    colonnes += list(contexte.colonnes)
    if contexte.reduction.repere == "polaire":
        colonnes += ["alpha", "beta", "DM", "DN"]
    return colonnes


def _nombre(x: float) -> str:
    return f"{round(x, 9) + 0.0:.10g}"


def ecrire_csv(plan: PlanDOE, contexte: Contexte, chemin: Path) -> int:
    """Écrit le DOE, une ligne par calcul, séparé par des tabulations ; renvoie le nombre de lignes.

    Ordre : rôle (calcul, contrôle, test), fidélité, Mach, table, puis variables.
    La colonne ``table`` porte un code sans caractère spécial (:func:`code_table`).
    En polaire, les colonnes ``alpha``, ``beta``, ``DM``, ``DN`` donnent le
    point en repère engin : c'est lui qu'on impose au solveur.
    """
    ordre_tables = {b.nom: i for i, b in enumerate(plan.blocs)}
    points = sorted(
        plan.points,
        key=lambda p: (
            ROLES.index(p.role),
            p.fidelite,
            p.valeurs.get("mach", 0.0),
            ordre_tables.get(p.table, 0),
            tuple(p.valeurs[col] for col in contexte.colonnes if col != "mach"),
        ),
    )
    colonnes = colonnes_csv(plan, contexte)
    polaire = contexte.reduction.repere == "polaire"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open("w", encoding="utf-8", newline="") as fichier:
        ecrivain = csv.writer(fichier, delimiter="\t", lineterminator="\n")
        ecrivain.writerow(colonnes)
        for i, p in enumerate(points, start=1):
            ligne: dict[str, str] = {
                "id": str(i),
                "role": p.role,
                "table": code_table(p.table),
                "sous_domaine": str(p.sous_domaine),
                "fidelite": p.fidelite,
                **{col: _nombre(p.valeurs[col]) for col in contexte.colonnes},
            }
            if polaire:
                alpha, beta = vers_alpha_beta(p.valeurs["alphat"], p.valeurs["phia"])
                dm, dn = braquages_engin(p.valeurs["DMB"], p.valeurs["DNB"], p.valeurs["phia"])
                ligne.update(
                    alpha=_nombre(alpha), beta=_nombre(beta), DM=_nombre(dm), DN=_nombre(dn)
                )
            ecrivain.writerow([ligne[col] for col in colonnes])
    return len(points)
