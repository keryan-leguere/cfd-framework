"""Les planches : la table et le modèle superposés, point fautif en rouge.

Une configuration = **une source de vérité**. Il y en a deux et deux
seulement : ``TABLE``, ce qui est écrit dans le COMMON block, et ``MODELE``, ce
que le code en a relu. Les superposer sur les mêmes axes est ce qui rend la
panne *visible* — une courbe seule, même fausse, reste lisse et n'alarme
personne.

Un appel de ``cfd_plot.batch_plot`` par table, et dans chaque appel une polaire
par variable indépendante : les autres variables deviennent des niveaux de
répertoire. C'est la structure que ``batch_plot`` produit naturellement, et on
ne fait ici que la nourrir.

Deux points mécaniques, tirés du fonctionnement de ``batch_plot`` et qu'il ne
faut pas défaire :

``values`` **restreint** les boucles
    Une table 20×15×7 donnerait de l'ordre de deux mille planches. On
    échantillonne donc les variables **épinglées** (jamais l'abscisse, qui
    montre toujours tous ses points) et le rapport le dit.

le hook doit être **picklable**
    ``batch_plot`` sérialise ``on_before_save`` pour ses processus de travail et
    **retombe silencieusement sur ``n_jobs=1``** quand il n'y arrive pas — un
    simple ``UserWarning``. Une fermeture capturant un cadre de données coûterait
    donc tous les cœurs de la machine sans le dire. D'où une dataclass gelée de
    niveau module.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from cfd_validation.data.spec import SpecTable
from cfd_validation.engine.tables import RapportTables, ResultatTable
from cfd_validation.report._plotting_lib import get_plotting
from cfd_validation.report.theme import COULEUR_VERDICT

__all__ = [
    "MAX_VALEURS",
    "HookEcarts",
    "dictionnaires",
    "planches_prevues",
    "points_fautifs",
    "tracer_rapport",
    "tracer_table",
]

#: Nombre de valeurs retenues, par défaut, pour une variable **épinglée**.
#: L'abscisse, elle, montre toujours tous ses points.
MAX_VALEURS = 5

#: Colonnes internes du cadre des points fautifs. Préfixées, pour ne jamais
#: entrer en collision avec une colonne de l'utilisateur.
COL_GRANDEUR = "_grandeur"
COL_TABLE = "_table"
COL_MODELE = "_modele"
COL_RELATIF = "_relatif"


# ---------------------------------------------------------------------------
# Le hook : marquer ce qui ne va pas
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HookEcarts:
    """Entoure en rouge les points hors tolérance de la planche en cours.

    Le sous-ensemble à marquer est **re-dérivé du contexte**, avec le filtre
    d'égalité stricte de ``batch_plot`` lui-même : le marquage porte donc
    provablement sur les points de la courbe tracée, sans tolérance à régler.
    C'est possible parce que les deux cadres — table et modèle — partagent leurs
    abscisses au bit près (voir :mod:`cfd_validation.data.entrees`).
    """

    fautifs: pd.DataFrame
    couleur: str = COULEUR_VERDICT[False]
    taille: float = 90.0
    etiquette: str = "hors tolérance"

    def __call__(self, figure: Any, axes: Any, contexte: Any) -> None:
        if getattr(contexte, "fold_layout", None) == "overlay":
            # Les courbes y sont réétiquetées et empilées : un marquage par
            # point n'y voudrait plus rien dire.
            return

        grandeur = _colonne(getattr(contexte, "y_spec", None), contexte.y_key)
        abscisse = _colonne(getattr(contexte, "x_spec", None), contexte.sweep_key)
        sous = self.sous_tableau(contexte, grandeur)
        if sous.empty or abscisse not in sous.columns:
            return

        x = sous[abscisse].to_numpy(dtype=float)
        axes.scatter(
            x,
            sous[COL_MODELE].to_numpy(dtype=float),
            s=self.taille,
            facecolors="none",
            edgecolors=self.couleur,
            linewidths=1.4,
            zorder=5,
            label=self.etiquette,
        )
        axes.vlines(
            x,
            sous[COL_TABLE].to_numpy(dtype=float),
            sous[COL_MODELE].to_numpy(dtype=float),
            colors=self.couleur,
            linewidths=0.9,
            zorder=4,
        )
        pire = float(np.nanmax(sous[COL_RELATIF].to_numpy(dtype=float)))
        plot = get_plotting()
        plot.add_textbox(
            axes,
            f"{len(sous)} point(s) hors tolérance\nécart relatif jusqu'à {pire:.3g}",
            loc="lower right",
            color=self.couleur,
        )
        # `batch_plot` ne légende que le premier panneau d'une planche repliée :
        # là où il n'y a pas de légende, il n'y a rien à rafraîchir.
        if getattr(contexte, "fold_kind", None) is None or axes.get_legend() is not None:
            plot.make_legend(axes)

    def sous_tableau(self, contexte: Any, grandeur: str) -> pd.DataFrame:
        """Les points fautifs de la planche en cours.

        Même filtre que ``batch_plot._filter_df_by_context`` : égalité stricte,
        aucune tolérance.
        """
        if self.fautifs.empty:
            return self.fautifs
        sous = self.fautifs[self.fautifs[COL_GRANDEUR] == grandeur]
        situation: dict[str, Any] = {
            **dict(getattr(contexte, "flight_point", {}) or {}),
            **dict(getattr(contexte, "fixed_sweeps", {}) or {}),
        }
        for colonne, valeur in situation.items():
            if colonne in sous.columns:
                sous = sous[sous[colonne] == valeur]
        return sous


def points_fautifs(resultat: ResultatTable) -> pd.DataFrame:
    """Les points hors tolérance d'une table, en cadre long.

    Une ligne par couple (nœud, grandeur) fautif : ses coordonnées, la valeur
    tabulée, celle rendue, et l'écart relatif.
    """
    spec = resultat.spec
    morceaux: list[pd.DataFrame] = []
    for grandeur in resultat.grandeurs:
        indices = grandeur.ecart.indices_fautifs
        if indices.size == 0:
            continue
        morceau = resultat.cadre_table.iloc[indices].loc[:, list(spec.entrees_attendues)].copy()
        morceau[COL_GRANDEUR] = grandeur.qoi
        morceau[COL_TABLE] = grandeur.ecart.reference[indices]
        morceau[COL_MODELE] = grandeur.ecart.obtenu[indices]
        morceau[COL_RELATIF] = grandeur.ecart.relatif[indices]
        morceaux.append(morceau)
    if not morceaux:
        colonnes = [*list(spec.entrees_attendues), COL_GRANDEUR, COL_TABLE, COL_MODELE, COL_RELATIF]
        return pd.DataFrame(columns=colonnes)
    return pd.concat(morceaux, ignore_index=True)


# ---------------------------------------------------------------------------
# Les quatre dictionnaires de batch_plot
# ---------------------------------------------------------------------------


def dictionnaires(
    resultat: ResultatTable, *, max_valeurs: int | None = MAX_VALEURS
) -> dict[str, Any]:
    """Les quatre dictionnaires que ``batch_plot`` attend, pour une table.

    Rendus séparément du tracé pour qu'un utilisateur puisse les reprendre,
    les amender et appeler ``batch_plot`` lui-même — c'est une bibliothèque de
    tracé maison, pas une boîte noire.
    """
    spec = resultat.spec
    configuration_dict = {
        "TABLE": {
            "name": "TABLE",
            "label": "table",
            "df": resultat.cadre_table,
            "color": "C0",
            "marker": "o",
            "linestyle": "-",
        },
        "MODELE": {
            "name": "MODELE",
            "label": "modèle",
            "df": resultat.cadre_modele,
            "color": "C1",
            "marker": "x",
            "linestyle": "--",
        },
    }

    y_axis_dict = {
        qoi: {
            "col_name": qoi,
            # Vide à dessein : cfd-plot compose « littéral, symbole (unité) », et
            # un libellé répété donnerait « CN, CN (-) ».
            "literal_name": "",
            "symbol": spec.libelle(qoi),
            "unit": spec.unite(qoi),
            "y_save_name": qoi,
        }
        for qoi in spec.qoi
    }

    sweep_dict = {
        variable: {
            "col_name": variable,
            "literal_name": "",
            "symbol": spec.libelle(variable),
            "unit": spec.unite(variable),
            "x_save_name": variable,
            "polar_prefix": f"{variable.upper()}_POLAR",
            "label": spec.libelle(variable),
            "save_name": variable.upper(),
        }
        for variable in spec.independantes
    }

    # Une variable déclarée dans les deux dictionnaires est pilotée par le
    # balayage, mais garde les `values` écrites ici : elles disent où elle est
    # **épinglée** sur les autres polaires, jamais ce que son abscisse montre.
    flight_point_dict = {
        variable: {
            "values": _echantillon(resultat.cadre_table[variable], max_valeurs),
            "label": spec.libelle(variable),
            "save_name": variable.upper(),
            "unit": spec.unite(variable),
        }
        for variable in spec.independantes
    }

    return {
        "configuration_dict": configuration_dict,
        "y_axis_dict": y_axis_dict,
        "sweep_dict": sweep_dict,
        "flight_point_dict": flight_point_dict,
    }


def _echantillon(colonne: pd.Series, combien: int | None) -> list[float]:
    """Jusqu'à *combien* valeurs distinctes, réparties, bornes comprises.

    Les valeurs sont prises **dans** la colonne : ``batch_plot`` avertit sur une
    valeur qu'aucune ligne ne porte, et une valeur recalculée tomberait à côté
    du dernier bit.
    """
    valeurs = np.unique(colonne.to_numpy(dtype=float))
    if combien is None or valeurs.size <= combien:
        return [float(valeur) for valeur in valeurs]
    if combien <= 1:
        return [float(valeurs[0])]
    positions = np.unique(np.linspace(0, valeurs.size - 1, combien).round().astype(int))
    return [float(valeurs[position]) for position in positions]


def _colonne(spec: Any, cle: str) -> str:
    """Le nom de colonne d'une spec cfd-plot, la clé à défaut."""
    if isinstance(spec, Mapping):
        nom = spec.get("col_name")
        if nom:
            return str(nom)
    return cle


# ---------------------------------------------------------------------------
# Le tracé
# ---------------------------------------------------------------------------


def tracer_table(
    resultat: ResultatTable,
    *,
    sortie: str | Path,
    formats: Sequence[str] = ("png",),
    max_valeurs: int | None = MAX_VALEURS,
    style_profile: str = "paper",
    marquer_fautifs: bool = True,
    options: Mapping[str, Any] | None = None,
) -> list[Path]:
    """Trace toutes les polaires d'une table, et rend les fichiers écrits."""
    plot = get_plotting()
    dicts = dictionnaires(resultat, max_valeurs=max_valeurs)
    hook = HookEcarts(points_fautifs(resultat)) if marquer_fautifs else None
    ecrits: list[Path] = plot.batch_plot(
        **dicts,
        output_base=Path(sortie) / resultat.nom,
        style_profile=style_profile,
        formats=tuple(formats),
        on_before_save=hook,
        **dict(options or {}),
    )
    return list(ecrits)


def tracer_rapport(
    rapport: RapportTables,
    *,
    sortie: str | Path,
    formats: Sequence[str] = ("png",),
    max_valeurs: int | None = MAX_VALEURS,
    style_profile: str = "paper",
    marquer_fautifs: bool = True,
    verbeux: bool = False,
    compte_rendu: bool = True,
    a_blanc: bool = False,
    n_jobs: int = 1,
    seulement_fautives: bool = False,
    **options: Any,
) -> dict[str, list[Path]]:
    """Trace toutes les tables d'un rapport, et rend les fichiers par table.

    Parameters
    ----------
    seulement_fautives:
        Ne tracer que les tables qui ont des points hors tolérance. Sur une
        étude qui passe, c'est le moyen de n'écrire aucune planche ; sur une
        étude qui échoue, de n'écrire que celles qu'on va regarder.
    verbeux, compte_rendu, a_blanc:
        Transposition des ``verbose`` / ``report`` / ``dry_run`` de
        ``batch_plot``, auxquels ils sont passés tels quels.
    """
    communes = {
        "verbose": verbeux,
        "report": compte_rendu,
        "dry_run": a_blanc,
        "n_jobs": n_jobs,
        **options,
    }
    ecrits: dict[str, list[Path]] = {}
    for resultat in rapport:
        if seulement_fautives and resultat.conforme:
            continue
        ecrits[resultat.nom] = tracer_table(
            resultat,
            sortie=sortie,
            formats=formats,
            max_valeurs=max_valeurs,
            style_profile=style_profile,
            marquer_fautifs=marquer_fautifs,
            options=communes,
        )
    return ecrits


def planches_prevues(rapport: RapportTables, *, max_valeurs: int | None = MAX_VALEURS) -> int:
    """Combien de planches un tracé complet écrirait, sans rien tracer.

    Sert au plan affiché avant le travail : deux mille planches se décident
    avant, pas après.
    """
    total = 0
    for resultat in rapport:
        spec: SpecTable = resultat.spec
        for variable in spec.independantes:
            epingles = [autre for autre in spec.independantes if autre != variable]
            combinaisons = 1
            for autre in epingles:
                combinaisons *= max(1, len(_echantillon(resultat.cadre_table[autre], max_valeurs)))
            total += combinaisons * len(spec.qoi)
    return total
