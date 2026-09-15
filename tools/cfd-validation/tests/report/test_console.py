"""Le rapport terminal.

Les fonctions rendent un objet Rich plutôt que d'imprimer : on peut donc les
inspecter sans capturer une sortie standard, et un script appelant peut les
composer dans sa propre console. Ces tests vérifient le **contenu**, parce que
c'est lui qu'un ingénieur lit pour décider.
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from rich.console import Console

from cfd_validation.engine.tables import valider_tables
from cfd_validation.report import theme
from cfd_validation.report.console import (
    imprimer_rapport,
    panneau_erreur,
    panneau_toolchain,
    panneau_verdict,
    rapport_tables,
    tableau_blocs,
    tableau_motifs,
    tableau_tables,
    tableau_verdicts,
)
from cfd_validation.wrap.factice import ModeleFactice
from cfd_validation.wrap.toolchain import Toolchain


def rendu(objet: Any, largeur: int = 200) -> str:
    """Le texte qu'une console produirait, sans les couleurs."""
    console = Console(width=largeur, no_color=True, force_terminal=False)
    with console.capture() as capture:
        console.print(objet)
    return capture.get()


@pytest.fixture
def rapport_ok(module: Any, specs: Any, modele: Any) -> Any:
    return valider_tables(module, specs, modele=modele)


@pytest.fixture
def rapport_ko(module: Any, specs: Any) -> Any:
    return valider_tables(module, specs, modele=ModeleFactice(module, bug="ecretage"))


class TestVerdict:
    def test_le_verdict_dit_conforme_quand_tout_va_bien(self, rapport_ok: Any) -> None:
        texte = rendu(panneau_verdict(rapport_ok))
        assert "relues correctement" in texte
        assert "aucun" in texte

    def test_le_verdict_compte_les_points_fautifs(self, rapport_ko: Any) -> None:
        texte = rendu(panneau_verdict(rapport_ko))
        assert "des écarts subsistent" in texte
        assert str(rapport_ko.n_fautifs) in texte


class TestRecapitulatif:
    def test_une_ligne_par_grandeur_controlee(self, rapport_ok: Any) -> None:
        texte = rendu(tableau_tables(rapport_ok))
        assert "CN" in texte and "CA" in texte
        assert "conforme" in texte

    def test_le_motif_principal_tient_lieu_de_verdict_court(self, rapport_ko: Any) -> None:
        assert "ecretage" in rendu(tableau_tables(rapport_ko))

    def test_un_nan_est_signale_plutot_qu_affiche_en_nombre(self, module: Any, specs: Any) -> None:
        import numpy as np

        def casse(df: Any) -> Any:
            colonne = "CN" if "delta" in df.columns else "CA"
            return df.assign(**{colonne: np.nan})

        rapport = valider_tables(module, specs, modele=casse)
        assert "NaN" in rendu(tableau_tables(rapport))


class TestDiagnostic:
    def test_une_table_conforme_n_a_pas_de_tableau_de_diagnostic(self, rapport_ok: Any) -> None:
        """Un tableau vide ferait croire qu'on a cherché et trouvé quelque chose."""
        assert tableau_motifs(rapport_ok["CN"]) is None

    def test_le_diagnostic_porte_le_message_du_motif(self, rapport_ko: Any) -> None:
        texte = rendu(tableau_motifs(rapport_ko["CN"]))
        assert "indice est saturé" in texte

    def test_le_diagnostic_montre_la_part_expliquee(self, rapport_ko: Any) -> None:
        assert "100%" in rendu(tableau_motifs(rapport_ko["CN"]))

    def test_le_motif_descriptif_n_affiche_pas_de_part(self, rapport_ko: Any) -> None:
        """Il n'explique rien : afficher « 0 % » suggérerait une hypothèse faible."""
        texte = rendu(tableau_motifs(rapport_ko["CN"]))
        ligne = next(ligne for ligne in texte.splitlines() if "diffus" in ligne)
        assert "—" in ligne
        assert "%" not in ligne.split("diffus")[1].split("Écart")[0]


class TestRapportComplet:
    def test_le_rapport_enchaine_verdict_recapitulatif_et_diagnostics(
        self, rapport_ko: Any
    ) -> None:
        texte = rendu(rapport_tables(rapport_ko))
        assert "Relecture de tables" in texte
        assert "Contrôle table par table" in texte
        assert "Diagnostic" in texte

    def test_un_rapport_conforme_n_affiche_aucun_diagnostic(self, rapport_ok: Any) -> None:
        assert "Diagnostic" not in rendu(rapport_tables(rapport_ok))

    def test_imprimer_rend_le_code_de_retour(self, rapport_ok: Any, rapport_ko: Any) -> None:
        with open(os.devnull, "w", encoding="utf-8") as nulle:
            console = Console(width=200, no_color=True, file=nulle)
            assert imprimer_rapport(rapport_ok, console) == 0
            assert imprimer_rapport(rapport_ko, console) == 2


class TestPanneaux:
    def test_une_erreur_sort_encadree_avec_son_indice(self) -> None:
        """Le public est un ingénieur, pas un développeur qui débogue cet outil."""
        texte = rendu(panneau_erreur("tout est perdu", indice="essayez ceci"))
        assert "tout est perdu" in texte
        assert "essayez ceci" in texte

    def test_le_panneau_de_toolchain_affiche_le_remede_quand_il_manque_quelque_chose(
        self,
    ) -> None:
        chaine = Toolchain(
            numpy="2.1.0",
            backend="meson",
            gfortran="/usr/bin/gfortran",
            gcc="/usr/bin/gcc",
            meson=None,
            ninja=None,
            distutils=False,
            manques=("meson", "ninja"),
        )
        texte = rendu(panneau_toolchain(chaine))
        assert "manque" in texte
        assert "pip install" in texte

    def test_le_panneau_de_toolchain_se_tait_quand_tout_est_la(self) -> None:
        chaine = Toolchain(
            numpy="2.1.0",
            backend="meson",
            gfortran="/usr/bin/gfortran",
            gcc="/usr/bin/gcc",
            meson="/usr/bin/meson",
            ninja="/usr/bin/ninja",
            distutils=False,
            manques=(),
        )
        texte = rendu(panneau_toolchain(chaine))
        assert "prête à compiler" in texte
        assert "remède" not in texte


class TestBlocs:
    def test_les_blocs_sont_listes_avec_leurs_tableaux(self, module: Any) -> None:
        from cfd_validation.wrap.bloc import blocs_exposes

        texte = rendu(tableau_blocs(blocs_exposes(module)))
        assert "tab_cn" in texte and "npt_cn" in texte

    def test_un_module_sans_bloc_le_dit(self) -> None:
        assert "aucun COMMON block" in rendu(tableau_blocs({}))


class TestVerdictsDeSuite:
    def test_le_tableau_de_suite_porte_le_nom_du_controle(self, rapport_ok: Any) -> None:
        texte = rendu(tableau_verdicts(rapport_ok.verdicts()))
        assert "relecture de tables" in texte


class TestTheme:
    def test_le_gras_est_absent_par_defaut(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Beaucoup de terminaux rendent le gras en plus clair, donc en délavé.

        C'est précisément le texte le plus important qui disparaîtrait.
        """
        monkeypatch.delenv(theme.ENV_GRAS, raising=False)
        import importlib

        recharge = importlib.reload(theme)
        assert "bold" not in recharge.TITRE
        assert "bold" not in recharge.ERREUR

    def test_la_variable_d_environnement_retablit_le_gras(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(theme.ENV_GRAS, "1")
        import importlib

        recharge = importlib.reload(theme)
        assert "bold" in recharge.TITRE
        monkeypatch.delenv(theme.ENV_GRAS, raising=False)
        importlib.reload(theme)

    def test_l_attenuation_n_est_jamais_emphatisee(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """C'est le fond du texte : l'emphatiser annulerait la hiérarchie."""
        monkeypatch.setenv(theme.ENV_GRAS, "1")
        import importlib

        recharge = importlib.reload(theme)
        assert recharge.DISCRET == "dim"
        monkeypatch.delenv(theme.ENV_GRAS, raising=False)
        importlib.reload(theme)
