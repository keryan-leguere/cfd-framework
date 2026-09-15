"""L'agrégation de plusieurs contrôles en un rapport.

Le point à tenir est que la suite ne sait **rien** des contrôles qu'elle
agrège : elle ne voit que des verdicts. C'est ce qui permettra d'ajouter un
deuxième contrôle sans toucher au rapport.
"""

from __future__ import annotations

from typing import Any

from cfd_validation.engine.controle import Verdict
from cfd_validation.engine.suite import Rapport, Suite, rapport_de
from cfd_validation.engine.tables import ControleTables


def _verdict(**surcharges: Any) -> Verdict:
    base: dict[str, Any] = {
        "controle": "essai",
        "sujet": "T",
        "grandeur": "A",
        "conforme": True,
        "total": 10,
        "fautifs": 0,
        "message": "conforme",
    }
    base.update(surcharges)
    return Verdict(**base)


class ControleMuet:
    """Un contrôle minimal : le protocole n'exige rien de plus."""

    def __init__(self, verdicts: tuple[Verdict, ...]) -> None:
        self._verdicts = verdicts

    @property
    def nom(self) -> str:
        return "muet"

    def executer(self) -> tuple[Verdict, ...]:
        return self._verdicts


class TestRapport:
    def test_un_rapport_vide_est_conforme(self) -> None:
        """Rien à reprocher n'est pas un échec."""
        assert Rapport().conforme
        assert Rapport().code_retour() == 0

    def test_un_seul_verdict_fautif_suffit_a_faire_echouer(self) -> None:
        rapport = rapport_de([_verdict(), _verdict(conforme=False, fautifs=3)])
        assert not rapport.conforme
        assert rapport.fautifs == 3
        assert rapport.total == 20

    def test_le_code_de_retour_distingue_l_echec_de_l_erreur(self) -> None:
        """2 et non 1 : la commande a abouti, c'est son résultat qui exige une action."""
        assert rapport_de([_verdict(conforme=False)]).code_retour() == 2

    def test_les_echecs_se_lisent_seuls(self) -> None:
        rapport = rapport_de([_verdict(sujet="A"), _verdict(sujet="B", conforme=False)])
        assert [verdict.sujet for verdict in rapport.echecs] == ["B"]

    def test_le_regroupement_par_controle_garde_l_ordre_d_apparition(self) -> None:
        rapport = rapport_de(
            [
                _verdict(controle="premier"),
                _verdict(controle="second"),
                _verdict(controle="premier"),
            ]
        )
        groupes = rapport.par_controle()
        assert list(groupes) == ["premier", "second"]
        assert len(groupes["premier"]) == 2

    def test_la_part_fautive_d_un_verdict_vide_ne_divise_pas_par_zero(self) -> None:
        assert _verdict(total=0, fautifs=0).part_fautive == 0.0


class TestSuite:
    def test_une_suite_execute_ses_controles_dans_l_ordre(self) -> None:
        suite = Suite(
            [
                ControleMuet((_verdict(sujet="premier"),)),
                ControleMuet((_verdict(sujet="second"),)),
            ]
        )
        assert [verdict.sujet for verdict in suite.executer()] == ["premier", "second"]

    def test_ajouter_rend_la_suite_pour_enchainer(self) -> None:
        suite = Suite().ajouter(ControleMuet((_verdict(),))).ajouter(ControleMuet(()))
        assert len(suite) == 2

    def test_une_suite_vide_s_execute_sans_lever(self) -> None:
        assert Suite().executer().conforme

    def test_le_controle_de_tables_s_agrege_comme_un_autre(
        self, module: Any, specs: Any, modele: Any
    ) -> None:
        """La démonstration que le protocole n'est pas décoratif."""
        suite = Suite([ControleTables(module=module, specs=specs, modele=modele)])
        rapport = suite.executer()
        assert rapport.conforme
        assert list(rapport.par_controle()) == ["relecture de tables"]

    def test_deux_controles_de_natures_differentes_cohabitent(
        self, module: Any, specs: Any, modele: Any
    ) -> None:
        suite = Suite(
            [
                ControleTables(module=module, specs=specs, modele=modele),
                ControleMuet((_verdict(controle="autre", conforme=False, fautifs=1),)),
            ]
        )
        rapport = suite.executer()
        assert not rapport.conforme
        assert set(rapport.par_controle()) == {"relecture de tables", "autre"}
