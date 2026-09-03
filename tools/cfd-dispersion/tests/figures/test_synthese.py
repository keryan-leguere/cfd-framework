"""Synthèse : damier, taux de validation, points de vol rejetés."""

from __future__ import annotations

from collections.abc import Iterator

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from cfd_dispersion.core.lois import JeuDeLois, charger_lois
from cfd_dispersion.core.tirage import tirer_lot
from cfd_dispersion.core.validation import valider_lot
from cfd_dispersion.figures.synthese import (
    colonnes_pdv,
    figure_synthese,
    pdv_rejetes,
    synthese,
    table_rich,
    tableau_par_pdv,
)


@pytest.fixture(autouse=True)
def _fermer_les_figures() -> Iterator[None]:
    yield
    plt.close("all")


@pytest.fixture
def verdicts(lois: JeuDeLois, table: dict[str, dict[str, float]]) -> pd.DataFrame:
    """Quatre points de vol, dont un où le FE de Cn_beta est mal tiré."""
    faux = {c: dict(s) for c, s in table.items()}
    faux["Cn_beta"]["FE_ET"] = 0.16
    lois_fausses = charger_lois(faux)

    morceaux = []
    for i, mach in enumerate([0.7, 0.8, 0.85, 0.9]):
        source = lois_fausses if i == 2 else lois
        lot = tirer_lot(source, 600, graine=200 + i)
        lot["Mach"] = mach
        morceaux.append(lot)
    return valider_lot(pd.concat(morceaux, ignore_index=True), lois, par=("Mach",))


class TestColonnesPdv:
    def test_retrouve_les_cles_de_groupement(self, verdicts: pd.DataFrame) -> None:
        assert colonnes_pdv(verdicts) == ["Mach"]

    def test_sans_groupement_il_n_y_en_a_aucune(self, lois: JeuDeLois) -> None:
        lot = tirer_lot(lois, 200, graine=1)
        assert colonnes_pdv(valider_lot(lot, lois)) == []


class TestTableauParPdv:
    def test_une_ligne_par_point_de_vol_une_colonne_par_composante(
        self, verdicts: pd.DataFrame, lois: JeuDeLois
    ) -> None:
        damier = tableau_par_pdv(verdicts)
        assert damier.shape == (4, 2 * len(lois))

    def test_la_case_porte_le_verdict_ou_le_motif(self, verdicts: pd.DataFrame) -> None:
        valeurs = set(tableau_par_pdv(verdicts).to_numpy().ravel())
        assert "VALIDÉ" in valeurs
        assert valeurs - {"VALIDÉ"}  # au moins un motif de rejet

    def test_l_ordre_des_composantes_est_celui_de_la_table(self, verdicts: pd.DataFrame) -> None:
        assert list(tableau_par_pdv(verdicts).columns)[:2] == ["Cm_alpha_Biais", "Cm_alpha_FE"]

    def test_un_tableau_vide_rend_un_tableau_vide(self) -> None:
        vide = pd.DataFrame(columns=["coefficient", "composante", "valide", "motif"])
        assert tableau_par_pdv(vide).empty


class TestSynthese:
    def test_une_ligne_par_composante(self, verdicts: pd.DataFrame, lois: JeuDeLois) -> None:
        assert len(synthese(verdicts)) == 2 * len(lois)

    def test_les_taux_se_completent(self, verdicts: pd.DataFrame) -> None:
        resume = synthese(verdicts)
        total = (resume["taux_validation"] + resume["taux_rejet"]).to_numpy()
        assert total == pytest.approx(100.0)

    def test_les_comptes_se_completent(self, verdicts: pd.DataFrame) -> None:
        resume = synthese(verdicts)
        assert (resume["n_valides"] + resume["n_rejetes"] == resume["n_pdv"]).all()

    def test_le_coefficient_fautif_est_celui_qui_a_un_taux_degrade(
        self, verdicts: pd.DataFrame
    ) -> None:
        resume = synthese(verdicts).set_index(["coefficient", "composante"])
        assert float(resume["taux_rejet"].loc[("Cn_beta", "FE")]) > 0.0

    def test_les_motifs_sont_comptes(self, verdicts: pd.DataFrame) -> None:
        resume = synthese(verdicts).set_index(["coefficient", "composante"])
        assert "×" in str(resume.loc[("Cn_beta", "FE"), "motifs"])

    def test_une_composante_sans_rejet_n_a_pas_de_motif(self, verdicts: pd.DataFrame) -> None:
        resume = synthese(verdicts)
        propres = resume.loc[resume["n_rejetes"] == 0, "motifs"]
        assert (propres == "").all()

    def test_un_tableau_vide_rend_les_bonnes_colonnes(self) -> None:
        vide = pd.DataFrame(columns=["coefficient", "composante", "valide", "motif"])
        assert "taux_validation" in synthese(vide).columns


class TestPdvRejetes:
    def test_liste_les_points_de_vol_fautifs(self, verdicts: pd.DataFrame) -> None:
        assert pdv_rejetes(verdicts) == [{"Mach": 0.85}]

    def test_se_restreint_a_un_coefficient(self, verdicts: pd.DataFrame) -> None:
        assert pdv_rejetes(verdicts, coefficient="Cm_alpha") == []

    def test_se_restreint_a_une_composante(self, verdicts: pd.DataFrame) -> None:
        assert pdv_rejetes(verdicts, coefficient="Cn_beta", composante="FE") == [{"Mach": 0.85}]

    def test_sans_rejet_la_liste_est_vide(self, lois: JeuDeLois) -> None:
        lot = tirer_lot(lois, 600, graine=1)
        lot["Mach"] = 0.8
        assert pdv_rejetes(valider_lot(lot, lois, par=("Mach",))) == []

    def test_le_resultat_se_passe_a_figures_par_pdv(
        self, verdicts: pd.DataFrame, lois: JeuDeLois, table: dict[str, dict[str, float]]
    ) -> None:
        """Le raccord entre 2.2 et 2.1 : ne tracer que ce qui a échoué."""
        from cfd_dispersion.figures.monte_carlo import figures_par_pdv

        faux = {c: dict(s) for c, s in table.items()}
        faux["Cn_beta"]["FE_ET"] = 0.16
        morceaux = []
        for i, mach in enumerate([0.7, 0.8, 0.85, 0.9]):
            lot = tirer_lot(charger_lois(faux) if i == 2 else lois, 600, graine=200 + i)
            lot["Mach"] = mach
            morceaux.append(lot)
        df = pd.concat(morceaux, ignore_index=True)

        produites = list(figures_par_pdv(df, lois, par=("Mach",), seulement=pdv_rejetes(verdicts)))
        assert {cles["Mach"] for cles, _, _ in produites} == {0.85}


class TestFigureSynthese:
    def test_rend_une_figure(self, verdicts: pd.DataFrame) -> None:
        figure, _ = figure_synthese(verdicts)
        assert figure is not None

    def test_la_figure_porte_le_damier_et_la_ligne_de_taux(self, verdicts: pd.DataFrame) -> None:
        _, ax = figure_synthese(verdicts)
        # Les cellules d'une `Table` ne sont pas atteintes par `findobj` :
        # il faut passer par la table elle-même.
        textes = {
            cellule.get_text().get_text()
            for table in ax.get_children()
            if table.__class__.__name__ == "Table"
            for cellule in table.get_celld().values()
        }
        assert "VALIDÉ" in textes
        assert "taux de validation" in textes
        assert any(texte.endswith(" %") for texte in textes)

    def test_un_tableau_vide_est_refuse(self) -> None:
        vide = pd.DataFrame(columns=["coefficient", "composante", "valide", "motif"])
        with pytest.raises(ValueError, match="aucun verdict"):
            figure_synthese(vide)


class TestTableRich:
    def test_rend_une_table_rich(self, verdicts: pd.DataFrame) -> None:
        from rich.table import Table

        assert isinstance(table_rich(verdicts), Table)

    def test_la_table_porte_une_ligne_par_composante(
        self, verdicts: pd.DataFrame, lois: JeuDeLois
    ) -> None:
        assert table_rich(verdicts).row_count == 2 * len(lois)


class TestVerification:
    def test_un_tableau_qui_n_est_pas_des_verdicts_est_refuse(self) -> None:
        with pytest.raises(ValueError, match="valider_lot"):
            synthese(pd.DataFrame({"a": [1]}))
