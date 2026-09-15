"""Le contrôle « le modèle relit-il ses propres tables ? ».

Une table interpolée vaut **exactement** la valeur tabulée à chacun de ses
nœuds : c'est vrai de toute interpolation, linéaire ou non, et cela ne dépend
d'aucun réglage. Évaluer le modèle sur les nœuds de sa propre table et
retrouver autre chose signifie donc, sans discussion possible, que le modèle ne
lit pas la table qu'on croit.

C'est le contrôle le plus rentable qu'on puisse écrire sur un code à tables :
il ne demande aucune référence extérieure — la table *est* la référence — et il
attrape des pannes qu'une courbe ne montre pas, parce qu'une courbe fausse est
lisse elle aussi.

Le déroulé, pour chaque table :

1. lire le tableau dans son COMMON block (:mod:`cfd_validation.wrap.bloc`) ;
2. en retirer les QOI pour composer les entrées du modèle ;
3. appeler le modèle et vérifier qu'il a tenu son contrat ;
4. comparer point à point, grandeur par grandeur ;
5. nommer les motifs de panne.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from cfd_validation.core.ecart import Ecart, comparer
from cfd_validation.core.motifs import Motif
from cfd_validation.data.entrees import cadre_modele, cadre_table, entrees, verifier_sortie
from cfd_validation.data.spec import SpecTable, charger_tables
from cfd_validation.engine.controle import Verdict
from cfd_validation.engine.diagnostic import diagnostiquer
from cfd_validation.wrap.bloc import lire_table

__all__ = [
    "ControleTables",
    "RapportTables",
    "ResultatQOI",
    "ResultatTable",
    "valider_tables",
]

#: Ce que le paquet attend d'un modèle : un cadre de données en entrée, un
#: cadre de données en sortie. Voir ``00_DOC/03_BRANCHER_SON_MODELE.md``.
Modele = Callable[[pd.DataFrame], Any]

#: Le nom du contrôle, tel qu'il apparaît dans le rapport.
NOM = "relecture de tables"


@dataclass(frozen=True)
class ResultatQOI:
    """Le contrôle d'une grandeur d'une table."""

    qoi: str
    ecart: Ecart
    motifs: tuple[Motif, ...]

    @property
    def conforme(self) -> bool:
        """Vrai si aucun point n'est hors tolérance."""
        return self.ecart.conforme

    @property
    def motif_principal(self) -> Motif | None:
        """Le motif le plus explicatif, s'il y en a un."""
        return self.motifs[0] if self.motifs else None


@dataclass(frozen=True)
class ResultatTable:
    """Le contrôle d'une table, toutes grandeurs confondues.

    Porte aussi les deux cadres de données — « table » et « modèle » — sous la
    forme exacte que ``cfd_plot.batch_plot`` consomme : mêmes colonnes, mêmes
    abscisses au bit près. C'est ce qui permet de tracer sans rien recalculer.
    """

    spec: SpecTable
    table: pd.DataFrame
    cadre_table: pd.DataFrame
    cadre_modele: pd.DataFrame
    grandeurs: tuple[ResultatQOI, ...]

    @property
    def nom(self) -> str:
        """Nom de la table."""
        return self.spec.nom

    @property
    def conforme(self) -> bool:
        """Vrai si toutes les grandeurs sont conformes."""
        return all(grandeur.conforme for grandeur in self.grandeurs)

    @property
    def n_points(self) -> int:
        """Nombre de nœuds de la table."""
        return len(self.table)

    @property
    def n_fautifs(self) -> int:
        """Nombre de couples (nœud, grandeur) hors tolérance."""
        return sum(grandeur.ecart.n_fautifs for grandeur in self.grandeurs)

    def grandeur(self, qoi: str) -> ResultatQOI:
        """Le résultat d'une grandeur, par son nom."""
        for resultat in self.grandeurs:
            if resultat.qoi == qoi:
                return resultat
        raise KeyError(
            f"table « {self.nom} » : aucune grandeur « {qoi} ». "
            f"Contrôlées : {[r.qoi for r in self.grandeurs]}."
        )

    def verdicts(self) -> tuple[Verdict, ...]:
        """Un verdict par grandeur, pour l'agrégation en suite."""
        return tuple(
            Verdict(
                controle=NOM,
                sujet=self.nom,
                grandeur=resultat.qoi,
                conforme=resultat.conforme,
                total=resultat.ecart.n,
                fautifs=resultat.ecart.n_fautifs,
                message=_phrase(resultat),
            )
            for resultat in self.grandeurs
        )


@dataclass(frozen=True)
class RapportTables:
    """Le contrôle de toutes les tables d'une étude."""

    resultats: tuple[ResultatTable, ...]

    @property
    def conforme(self) -> bool:
        """Vrai si toutes les tables sont conformes."""
        return all(resultat.conforme for resultat in self.resultats)

    @property
    def n_points(self) -> int:
        """Nombre total de nœuds contrôlés."""
        return sum(resultat.n_points for resultat in self.resultats)

    @property
    def n_fautifs(self) -> int:
        """Nombre total de couples (nœud, grandeur) hors tolérance."""
        return sum(resultat.n_fautifs for resultat in self.resultats)

    def verdicts(self) -> tuple[Verdict, ...]:
        """Tous les verdicts, table par table puis grandeur par grandeur."""
        return tuple(verdict for resultat in self.resultats for verdict in resultat.verdicts())

    def __getitem__(self, nom: str) -> ResultatTable:
        for resultat in self.resultats:
            if resultat.nom == nom:
                return resultat
        raise KeyError(
            f"aucune table « {nom} » dans ce rapport. "
            f"Contrôlées : {[r.nom for r in self.resultats]}."
        )

    def __iter__(self) -> Any:
        return iter(self.resultats)

    def __len__(self) -> int:
        return len(self.resultats)


@dataclass(frozen=True)
class ControleTables:
    """La relecture de tables, sous la forme d'un :class:`~.controle.Controle`."""

    module: Any
    specs: Mapping[str, SpecTable]
    modele: Modele

    @property
    def nom(self) -> str:
        """Nom affichable du contrôle."""
        return NOM

    def executer(self) -> tuple[Verdict, ...]:
        """Exécute le contrôle et rend un verdict par grandeur de chaque table."""
        return self.rapport().verdicts()

    def rapport(self) -> RapportTables:
        """Le résultat détaillé, cadres de données compris."""
        return RapportTables(
            resultats=tuple(
                _une_table(self.module, spec, self.modele) for spec in self.specs.values()
            )
        )


def valider_tables(
    module: Any,
    tables: Mapping[str, Mapping[str, Any]] | Mapping[str, SpecTable],
    *,
    modele: Modele,
) -> RapportTables:
    """Contrôle que *module* relit bien les tables déclarées dans *tables*.

    Parameters
    ----------
    module:
        Le modèle enveloppé. Doit exposer ``module.<bloc>.<tableau>``, ce que
        f2py produit pour un COMMON block — ou n'importe quel objet Python
        portant les mêmes attributs.
    tables:
        Le dictionnaire ``TABLES``, brut ou déjà validé par
        :func:`~cfd_validation.data.spec.charger_tables`.
    modele:
        Votre fonction ``modele(df) -> df``. Elle reçoit un cadre portant les
        colonnes indépendantes de la table et les constantes déclarées, et doit
        rendre un cadre de même longueur, dans le même ordre, portant les QOI.

    Returns
    -------
    RapportTables
        À afficher avec :func:`cfd_validation.report.console.rapport_tables`, et
        à tracer avec :func:`cfd_validation.report.figures.tracer_rapport`.
    """
    specs = _specs(tables)
    return ControleTables(module=module, specs=specs, modele=modele).rapport()


# ---------------------------------------------------------------------------
# Le déroulé, pour une table
# ---------------------------------------------------------------------------


def _specs(
    tables: Mapping[str, Mapping[str, Any]] | Mapping[str, SpecTable],
) -> dict[str, SpecTable]:
    """Accepte indifféremment des specs validées ou le dictionnaire brut."""
    if tables and all(isinstance(valeur, SpecTable) for valeur in tables.values()):
        return {nom: valeur for nom, valeur in tables.items() if isinstance(valeur, SpecTable)}
    brut: Mapping[str, Mapping[str, Any]] = tables  # type: ignore[assignment]
    return charger_tables(brut)


def _une_table(module: Any, spec: SpecTable, modele: Modele) -> ResultatTable:
    """Lit, appelle, compare et diagnostique une table."""
    table = lire_table(module, spec)
    demande = entrees(table, spec)
    rendu = verifier_sortie(demande, modele(demande), spec)

    reference = cadre_table(table, spec)
    obtenu = cadre_modele(table, rendu, spec)

    grandeurs: list[ResultatQOI] = []
    for qoi in spec.qoi:
        rtol, atol = spec.tolerance(qoi)
        ecart = comparer(
            reference[qoi].to_numpy(dtype=float),
            obtenu[qoi].to_numpy(dtype=float),
            rtol=rtol,
            atol=atol,
        )
        grandeurs.append(
            ResultatQOI(qoi=qoi, ecart=ecart, motifs=diagnostiquer(table, spec, ecart))
        )

    return ResultatTable(
        spec=spec,
        table=table,
        cadre_table=reference,
        cadre_modele=obtenu,
        grandeurs=tuple(grandeurs),
    )


def _phrase(resultat: ResultatQOI) -> str:
    """La ligne de tableau d'une grandeur."""
    if resultat.conforme:
        return f"relue à {resultat.ecart.absolu_max:.3g} près"
    principal = resultat.motif_principal
    if principal is not None and principal.nom != "diffus":
        return f"{principal.nom} ({principal.part_expliquee:.0%})"
    return f"écart relatif jusqu'à {resultat.ecart.relatif_max:.3g}"
