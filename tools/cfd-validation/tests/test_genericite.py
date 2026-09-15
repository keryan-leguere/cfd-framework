"""Aucune couche ne reconnaît une colonne à son nom.

Un détecteur qui saurait ce qu'est un « mach » ne marcherait que sur les tables
de celui qui l'a écrit. Les noms de colonne viennent tous de la déclaration de
l'utilisateur, et ne servent qu'à composer des messages.

La vérification est double : par lecture du source, et par l'usage — on rejoue
le contrôle complet sur des tables dont les colonnes portent des noms
volontairement exotiques, et tout doit se comporter à l'identique.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from cfd_validation.data.spec import charger_tables
from cfd_validation.engine.tables import valider_tables

RACINE = Path(__file__).resolve().parents[1]
SOURCE = RACINE / "src" / "cfd_validation"

#: Noms de grandeurs qu'aucune couche ne doit connaître. Ils apparaissent
#: légitimement dans le faux modèle et dans l'exemple, qui sont des données.
NOMS_METIER = ("mach", "alpha", "delta", "beta", "altitude", "incidence", "braquage")

#: Les fichiers qui ont le droit de nommer une grandeur : ce sont des données
#: d'exemple, pas de la logique.
DISPENSES = {"factice.py"}


def _modules_de_logique() -> list[Path]:
    return sorted(
        chemin
        for chemin in SOURCE.rglob("*.py")
        if "__pycache__" not in chemin.parts
        and "01_EXEMPLE" not in chemin.parts
        and chemin.name not in DISPENSES
    )


def _code_sans_commentaires(chemin: Path) -> str:
    """Le source, docstrings et commentaires retirés.

    Une docstring a le droit de dire « mach » pour illustrer ; du code, non.
    """
    contenu = chemin.read_text(encoding="utf-8")
    contenu = re.sub(r'"""(?:.|\n)*?"""', "", contenu)
    contenu = re.sub(r"'''(?:.|\n)*?'''", "", contenu)
    return re.sub(r"#.*", "", contenu)


class TestParLecture:
    @pytest.mark.parametrize("chemin", _modules_de_logique(), ids=lambda p: str(p.name))
    def test_aucun_module_ne_nomme_une_grandeur_dans_son_code(self, chemin: Path) -> None:
        code = _code_sans_commentaires(chemin).lower()
        fautifs = [nom for nom in NOMS_METIER if re.search(rf"\b{nom}\b", code)]
        assert not fautifs, f"{chemin.name} reconnaît {fautifs}"


class TestParLUsage:
    """La même vérification, mais en faisant tourner le contrôle."""

    @staticmethod
    def _module(colonnes: list[str]) -> Any:
        """Un module portant une table à deux axes, sous les noms donnés."""
        axe = np.array([0.0, 1.0, 2.0, 3.0])
        lignes = [(x, y, 1.0 + 2.0 * x + 0.5 * y + 0.1 * x * x) for x in axe for y in axe]

        class Bloc:
            tab = np.asarray(lignes, dtype=float)

        class Faux:
            bloc = Bloc()

        return Faux()

    @pytest.mark.parametrize(
        "colonnes",
        [
            ["mach", "alpha", "CN"],
            ["Θ", "φ", "coefficient"],
            ["a", "b", "c"],
            ["colonne avec espaces", "UNE_AUTRE", "sortie"],
        ],
    )
    def test_le_controle_se_comporte_a_l_identique_quels_que_soient_les_noms(
        self, colonnes: list[str]
    ) -> None:
        specs = charger_tables({"T": {"bloc": "bloc", "tableau": "tab", "colonnes": colonnes}})
        module = self._module(colonnes)

        def juste(df: pd.DataFrame) -> pd.DataFrame:
            table = np.asarray(module.bloc.tab)
            return df.assign(**{colonnes[-1]: table[:, 2]})

        rapport = valider_tables(module, specs, modele=juste)
        assert rapport.conforme
        assert rapport.n_points == 16

    @pytest.mark.parametrize(
        "colonnes",
        [["mach", "alpha", "CN"], ["Θ", "φ", "coefficient"], ["a", "b", "c"]],
    )
    def test_le_diagnostic_nomme_le_bon_axe_quels_que_soient_les_noms(
        self, colonnes: list[str]
    ) -> None:
        """Le message doit citer le nom déclaré, pas un nom deviné."""
        specs = charger_tables({"T": {"bloc": "bloc", "tableau": "tab", "colonnes": colonnes}})
        module = self._module(colonnes)

        def transpose(df: pd.DataFrame) -> pd.DataFrame:
            table = np.asarray(module.bloc.tab)
            cle = {(ligne[0], ligne[1]): ligne[2] for ligne in table}
            valeurs = [
                cle[(ligne[1], ligne[0])] for ligne in df.loc[:, colonnes[:2]].to_numpy(dtype=float)
            ]
            return df.assign(**{colonnes[-1]: valeurs})

        rapport = valider_tables(module, specs, modele=transpose)
        motif = rapport["T"].grandeur(colonnes[-1]).motif_principal
        assert motif is not None
        assert motif.nom == "axes_transposes"
        assert motif.preuve["axes"] == (colonnes[0], colonnes[1])
