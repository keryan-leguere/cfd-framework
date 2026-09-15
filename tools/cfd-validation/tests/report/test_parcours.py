"""Le plan avant, le bilan après.

Ces fonctions impriment, contrairement à ``report/console.py`` : un parcours
est une commande, pas une valeur, et son plan doit paraître *avant* que le
travail commence. On vérifie donc la sortie capturée.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cfd_validation.engine.tables import valider_tables
from cfd_validation.report.parcours import (
    MAX_VALEURS,
    imprimer_bilan,
    imprimer_note,
    imprimer_plan,
    resume_valeurs,
)


@pytest.fixture
def rapport(module: Any, specs: Any, modele: Any) -> Any:
    return valider_tables(module, specs, modele=modele)


class TestResumeValeurs:
    def test_une_liste_courte_sort_entiere(self) -> None:
        assert resume_valeurs([0.3, 0.5]) == "0.3, 0.5"

    def test_une_liste_longue_est_abregee_en_disant_combien_manquent(self) -> None:
        texte = resume_valeurs(list(range(MAX_VALEURS + 4)))
        assert texte.endswith("(+4)")

    def test_les_nombres_sortent_sans_bruit_de_representation(self) -> None:
        """Un plan qui affiche 0.30000000000000004 n'est pas un plan."""
        assert resume_valeurs([0.1 + 0.2]) == "0.3"

    def test_les_noms_de_colonne_passent_tels_quels(self) -> None:
        """La même fonction sert aux valeurs d'une variable et à leurs noms."""
        assert resume_valeurs(["mach", "alpha"]) == "mach, alpha"

    def test_une_liste_vide_donne_un_tiret(self) -> None:
        assert resume_valeurs([]) == "—"

    def test_un_booleen_n_est_pas_traite_comme_un_nombre(self) -> None:
        assert resume_valeurs([True]) == "True"


class TestPlan:
    def test_le_plan_annonce_les_tables_et_les_planches(
        self, rapport: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        imprimer_plan(rapport, sortie=Path("FIGURE"), planches=42, max_valeurs=5)
        texte = capsys.readouterr().out
        assert "tables" in texte
        assert "42" in texte
        assert "FIGURE" in texte

    def test_le_plan_dit_quand_rien_ne_sera_ecrit(
        self, rapport: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        imprimer_plan(rapport, a_blanc=True)
        assert "rien ne sera écrit" in capsys.readouterr().out

    def test_le_plan_liste_les_variables_de_chaque_table(
        self, rapport: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        imprimer_plan(rapport)
        texte = capsys.readouterr().out
        assert "mach" in texte and "delta" in texte


class TestBilan:
    def test_le_bilan_compte_les_fichiers_par_table(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        imprimer_bilan(
            {
                "CN": [Path("F/CN/a.png"), Path("F/CN/b.png")],
                "CA": [Path("F/CA/c.png")],
            }
        )
        texte = capsys.readouterr().out
        assert "3 fichier(s) écrits" in texte
        assert "CN" in texte

    def test_le_bilan_distingue_le_trace_a_blanc(self, capsys: pytest.CaptureFixture[str]) -> None:
        imprimer_bilan({"CN": [Path("F/CN/a.png")]}, a_blanc=True)
        assert "seraient écrits" in capsys.readouterr().out

    def test_un_bilan_vide_ne_leve_pas(self, capsys: pytest.CaptureFixture[str]) -> None:
        imprimer_bilan({})
        assert "0 fichier" in capsys.readouterr().out

    def test_le_repertoire_commun_est_trouve_sur_plusieurs_niveaux(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        imprimer_bilan(
            {"CN": [Path("F/CN/M_1/a.png"), Path("F/CN/M_2/b.png")]},
        )
        assert "F/CN" in capsys.readouterr().out


class TestNote:
    def test_une_note_sort_telle_quelle(self, capsys: pytest.CaptureFixture[str]) -> None:
        imprimer_note("attention à la marche")
        assert "attention à la marche" in capsys.readouterr().out
