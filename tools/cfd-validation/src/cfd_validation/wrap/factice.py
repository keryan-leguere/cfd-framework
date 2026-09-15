"""Un faux modèle à tables, pour éprouver le contrôle sans compilateur.

Le paquet ne demande au code enveloppé qu'un accès par attribut
``module.<bloc>.<tableau>``. Un objet Python quelconque portant les mêmes
attributs fait donc l'affaire — et c'est ce que construit ce module.

Ce n'est pas un pis-aller de test, c'est une pièce du produit, pour trois
raisons :

* la suite de tests tourne **partout**, y compris là où ``f2py -c`` ne peut pas
  compiler (voir :mod:`cfd_validation.wrap.toolchain`) — même raison d'être que
  l'adaptateur ``mock`` du framework bash ;
* chaque motif de panne est **démontrable** : :class:`ModeleFactice` sait
  reproduire à volonté la transposition d'axes, le décalage d'indice, le
  facteur d'unité, l'axe ignoré, l'indice saturé — donc chaque détecteur a un
  cas de référence plutôt qu'un raisonnement ;
* qui déploie le paquet sur un calculateur isolé peut vérifier son installation
  sans sortir son propre modèle du coffre.

Les deux tables imitent une base aérodynamique ordinaire : un ``CN`` fonction
de (mach, incidence, braquage) et un ``CA`` fonction de (mach, incidence).
L'incidence et le braquage partagent leur jeu de valeurs — des degrés, sur la
même plage — ce qui est banal en pratique, et ce qui rend une transposition de
ces deux axes possible **et** détectable.

Le tableau ``CN`` est dimensionné plus large que son remplissage, et la queue
est mise à ``-999``, la valeur de remplissage la plus répandue en Fortran :
c'est ainsi qu'on démontre le motif ``queue_non_renseignee``, en omettant la
clé ``lignes`` de la déclaration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

__all__ = [
    "BUGS",
    "TABLES",
    "BlocCommun",
    "ModeleFactice",
    "ModuleFactice",
    "module_factice",
]

#: Nombres de Mach de la base.
MACH: tuple[float, ...] = (0.3, 0.5, 0.7, 0.8, 0.9, 0.95)

#: Incidences **et** braquages, en degrés : le même jeu de valeurs pour les
#: deux, ce qui rend une transposition de ces deux axes possible.
ANGLES: tuple[float, ...] = (-4.0, -2.0, 0.0, 2.0, 4.0, 6.0, 8.0)

#: Le tableau CN est dimensionné plus large que son remplissage, comme en vrai.
CAPACITE_CN = 320

#: La valeur qui traîne dans les lignes jamais écrites.
REMPLISSAGE = -999.0

Tableau = npt.NDArray[np.float64]


def _cn(mach: float, alpha: float, delta: float) -> float:
    """Le coefficient normal de la base factice. Dépend vraiment des trois axes."""
    return 0.02 + 0.105 * alpha + 0.030 * delta + 0.45 * mach**2 + 0.0012 * alpha * delta


def _ca(mach: float, alpha: float) -> float:
    """Le coefficient axial de la base factice."""
    return 0.021 + 0.015 * mach**4 + 0.00025 * alpha**2


# ---------------------------------------------------------------------------
# Le faux module
# ---------------------------------------------------------------------------


class BlocCommun:
    """Imite un COMMON block tel que f2py l'expose : des attributs, rien d'autre."""

    def __init__(self, **membres: Any) -> None:
        for nom, valeur in membres.items():
            setattr(self, nom, valeur)

    def __getattr__(self, nom: str) -> Any:
        """Déclaré pour le vérificateur de types, jamais atteint à l'exécution.

        Les membres d'un COMMON block sont posés dans ``__init__`` et varient
        d'un bloc à l'autre — exactement comme ceux d'un objet f2py, qu'aucune
        annotation ne peut décrire à l'avance.
        """
        raise AttributeError(f"{type(self).__name__} ne porte pas « {nom} »")

    def __repr__(self) -> str:  # pragma: no cover - confort de débogage
        membres = ", ".join(sorted(vars(self)))
        return f"<BlocCommun {membres}>"


class ModuleFactice:
    """Imite un module d'extension f2py portant deux COMMON blocks."""

    def __init__(self, tab_cn: BlocCommun, tab_ca: BlocCommun) -> None:
        self.tab_cn = tab_cn
        self.tab_ca = tab_ca

    def __repr__(self) -> str:  # pragma: no cover - confort de débogage
        return "<ModuleFactice tab_cn, tab_ca>"


def _table_cn() -> tuple[Tableau, int]:
    """Le tableau CN, dimensionné large et rempli en partie."""
    lignes = [
        (mach, alpha, delta, _cn(mach, alpha, delta))
        for mach in MACH
        for alpha in ANGLES
        for delta in ANGLES
    ]
    tableau = np.full((CAPACITE_CN, 4), REMPLISSAGE, dtype=np.float64)
    tableau[: len(lignes)] = np.asarray(lignes, dtype=np.float64)
    return tableau, len(lignes)


def _table_ca() -> tuple[Tableau, int]:
    """Le tableau CA, exactement à sa taille : pas de queue à rogner ici."""
    lignes = [(mach, alpha, _ca(mach, alpha)) for mach in MACH for alpha in ANGLES]
    return np.asarray(lignes, dtype=np.float64), len(lignes)


def module_factice() -> ModuleFactice:
    """Un faux module f2py portant les deux tables."""
    tableau_cn, remplies_cn = _table_cn()
    tableau_ca, remplies_ca = _table_ca()
    return ModuleFactice(
        tab_cn=BlocCommun(tab_cn=tableau_cn, npt_cn=np.array(remplies_cn, dtype=np.int32)),
        tab_ca=BlocCommun(tab_ca=tableau_ca, npt_ca=np.array(remplies_ca, dtype=np.int32)),
    )


#: La déclaration qui va avec :func:`module_factice`. Le ``lignes`` de ``CN``
#: est bien là : c'est en le retirant qu'on démontre ``queue_non_renseignee``.
TABLES: dict[str, dict[str, Any]] = {
    "CN": {
        "bloc": "tab_cn",
        "tableau": "tab_cn",
        "colonnes": ["mach", "alpha", "delta", "CN"],
        "qoi": ["CN"],
        "lignes": "npt_cn",
        "libelles": {"mach": "Mach", "alpha": "incidence", "delta": "braquage"},
        "unites": {"alpha": "°", "delta": "°"},
    },
    "CA": {
        "bloc": "tab_ca",
        "tableau": "tab_ca",
        "colonnes": ["mach", "alpha", "CA"],
        "qoi": ["CA"],
        "lignes": "npt_ca",
        "libelles": {"mach": "Mach", "alpha": "incidence"},
        "unites": {"alpha": "°"},
    },
}


# ---------------------------------------------------------------------------
# Le faux modèle, et ses pannes
# ---------------------------------------------------------------------------

#: Les pannes que :class:`ModeleFactice` sait reproduire, et le motif que le
#: diagnostic doit alors nommer en tête. C'est ce tableau qui relie une panne à
#: son détecteur, et c'est lui que la suite de tests parcourt.
BUGS: dict[str, str] = {
    "echelle": "facteur_echelle",
    "decalage": "decalage_constant",
    "transpose": "axes_transposes",
    "axe_ignore": "axe_ignore",
    "indice": "decalage_indice",
    "ecretage": "ecretage",
    "bruit": "diffus",
}


@dataclass(frozen=True)
class ModeleFactice:
    """Un modèle qui relit les tables du module — bien, ou mal exprès.

    Respecte le contrat du paquet : reçoit un cadre portant les colonnes
    indépendantes, rend un cadre de même longueur et dans le même ordre,
    portant les QOI.

    Avec ``bug=None`` il relit **exactement** : c'est ce qu'un code juste fait,
    puisqu'une interpolation vaut la valeur tabulée à ses nœuds. Toute autre
    valeur de *bug* injecte une panne de la liste :data:`BUGS`.
    """

    module: ModuleFactice
    bug: str | None = None
    graine: int = 12345

    def __post_init__(self) -> None:
        if self.bug is not None and self.bug not in BUGS:
            raise ValueError(f"panne inconnue : {self.bug!r}. Connues : {sorted(BUGS)}.")

    def __call__(self, entrees: pd.DataFrame) -> pd.DataFrame:
        rendu = entrees.copy()
        if "delta" in entrees.columns:
            rendu["CN"] = self._serie(entrees, grandeur="CN")
        else:
            rendu["CA"] = self._serie(entrees, grandeur="CA")
        return rendu

    # -- le détail de la relecture -------------------------------------------

    def _serie(self, entrees: pd.DataFrame, *, grandeur: str) -> Tableau:
        """Une valeur par ligne, panne comprise."""
        noeuds = _noeuds(grandeur, self.module)
        axes = ["mach", "alpha", "delta"] if grandeur == "CN" else ["mach", "alpha"]
        machs = np.unique([cle[0] for cle in noeuds])
        alphas = np.unique([cle[1] for cle in noeuds])

        valeurs = np.empty(len(entrees), dtype=np.float64)
        brut = entrees.loc[:, axes].to_numpy(dtype=float)
        for ligne in range(len(entrees)):
            cle = tuple(float(valeur) for valeur in brut[ligne])
            valeurs[ligne] = self._une_valeur(cle, noeuds, machs=machs, alphas=alphas)

        if self.bug == "echelle":
            valeurs *= np.pi / 180.0
        elif self.bug == "decalage":
            valeurs += 0.05
        elif self.bug == "bruit":
            generateur = np.random.default_rng(self.graine)
            valeurs = valeurs + generateur.normal(0.0, 0.05, size=valeurs.shape)
        return valeurs

    def _une_valeur(
        self,
        cle: tuple[float, ...],
        noeuds: dict[tuple[float, ...], float],
        *,
        machs: Tableau,
        alphas: Tableau,
    ) -> float:
        """La valeur lue pour un nœud, panne d'indexation comprise."""
        cherche = cle
        if self.bug == "transpose" and len(cle) == 3:
            cherche = (cle[0], cle[2], cle[1])
        elif self.bug == "axe_ignore" and len(cle) == 3:
            cherche = (cle[0], cle[1], float(min(ANGLES)))
        elif self.bug == "indice":
            position = int(np.searchsorted(alphas, cle[1]))
            if position + 1 < alphas.size:
                cherche = (cle[0], float(alphas[position + 1]), *cle[2:])
        elif self.bug == "ecretage":
            position = int(np.searchsorted(machs, cle[0]))
            if position == 0:
                cherche = (float(machs[1]), *cle[1:])
            elif position == machs.size - 1:
                cherche = (float(machs[-2]), *cle[1:])
        # Un nœud inconnu rend zéro : c'est ce que fait un code à qui l'on
        # demande un point qui n'est pas dans sa table, et c'est ce qui rend
        # visible une queue de tableau jamais renseignée.
        return noeuds.get(cherche, 0.0)


def _noeuds(grandeur: str, module: ModuleFactice) -> dict[tuple[float, ...], float]:
    """La table du module, sous forme de dictionnaire nœud → valeur.

    Seules les lignes **réellement renseignées** y entrent : le modèle factice
    est un code juste, c'est la déclaration qui peut être fautive.
    """
    if grandeur == "CN":
        tableau = np.asarray(module.tab_cn.tab_cn, dtype=np.float64)
        remplies = int(np.asarray(module.tab_cn.npt_cn).reshape(-1)[0])
        tableau = tableau[:remplies]
        return {
            (float(ligne[0]), float(ligne[1]), float(ligne[2])): float(ligne[3])
            for ligne in tableau
        }
    tableau = np.asarray(module.tab_ca.tab_ca, dtype=np.float64)
    return {(float(ligne[0]), float(ligne[1])): float(ligne[2]) for ligne in tableau}
