"""Lecture de la table ``{coeff: {Biais_*, FE_*}}``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import openturns as ot
import pytest

from cfd_dispersion.core.lois import (
    CLES_ATTENDUES,
    COMPOSANTES,
    JeuDeLois,
    LoiCoefficient,
    charger_lois,
    charger_lois_yaml,
)


class TestChargement:
    def test_chaque_coefficient_devient_une_loi(
        self, lois: JeuDeLois, table: dict[str, dict[str, float]]
    ) -> None:
        assert set(lois) == set(table)
        assert all(isinstance(lois[c], LoiCoefficient) for c in lois)

    def test_les_six_cles_sont_lues_dans_les_bonnes_composantes(self, lois: JeuDeLois) -> None:
        biais = lois["Cm_alpha"].biais
        fe = lois["Cm_alpha"].fe
        assert (biais.type_loi, biais.M, biais.ET) == (5, 0.0, 0.015)
        assert (fe.type_loi, fe.M, fe.ET) == (6, 0.0, 0.10)

    def test_l_ordre_de_la_table_est_conserve(self, table: dict[str, dict[str, float]]) -> None:
        """Figures et tableaux suivent l'ordre écrit, pas un tri alphabétique."""
        assert list(charger_lois(table)) == list(table)

    def test_les_colonnes_suivent_l_ordre_coefficient_puis_composante(
        self, lois: JeuDeLois
    ) -> None:
        assert lois.colonnes == (
            "Cm_alpha_Biais",
            "Cm_alpha_FE",
            "Cn_beta_Biais",
            "Cn_beta_FE",
            "CA_Biais",
            "CA_FE",
        )

    def test_le_jeu_se_comporte_comme_un_mapping(self, lois: JeuDeLois) -> None:
        assert len(lois) == 3
        assert "Cm_alpha" in lois
        assert [nom for nom, _ in lois["Cm_alpha"]] == list(COMPOSANTES)

    def test_composantes_aplatit_le_jeu(self, lois: JeuDeLois) -> None:
        aplati = lois.composantes()
        assert len(aplati) == 6
        assert aplati[0][:2] == ("Cm_alpha", "Biais")

    def test_composante_par_nom(self, lois: JeuDeLois) -> None:
        assert lois["Cm_alpha"].composante("FE") is lois["Cm_alpha"].fe

    def test_une_composante_inconnue_est_refusee(self, lois: JeuDeLois) -> None:
        with pytest.raises(ValueError, match="composante inconnue"):
            lois["Cm_alpha"].composante("Echelle")

    def test_le_resume_nomme_les_deux_lois(self, lois: JeuDeLois) -> None:
        resume = lois["Cm_alpha"].resume
        assert "Gaussienne ±3σ" in resume and "Gaussienne ±2σ" in resume


class TestErreursDeTable:
    def test_une_table_vide_est_refusee(self) -> None:
        with pytest.raises(ValueError, match="vide"):
            charger_lois({})

    def test_une_cle_manquante_nomme_le_coefficient_et_la_cle(self) -> None:
        with pytest.raises(ValueError, match=r"'CN'.*Biais_ET"):
            charger_lois(
                {"CN": {"Biais_Type": 4, "Biais_M": 0.0, "FE_Type": 4, "FE_M": 0.0, "FE_ET": 0.1}}
            )

    def test_une_cle_superflue_est_refusee(self, table: dict[str, dict[str, float]]) -> None:
        table["Cm_alpha"]["Biais_Sigma"] = 0.01
        with pytest.raises(ValueError, match="inconnue"):
            charger_lois(table)

    def test_un_type_non_entier_est_refuse(self, table: dict[str, dict[str, float]]) -> None:
        table["Cm_alpha"]["Biais_Type"] = 4.5
        with pytest.raises(ValueError, match="entier"):
            charger_lois(table)

    def test_une_valeur_non_numerique_est_refusee(self, table: dict[str, dict[str, float]]) -> None:
        fautive: dict[str, Any] = dict(table["Cm_alpha"])
        fautive["Biais_M"] = "zéro"
        with pytest.raises(ValueError, match="nombre"):
            charger_lois({"Cm_alpha": fautive})

    def test_un_type_hors_bornes_est_refuse(self, table: dict[str, dict[str, float]]) -> None:
        table["Cn_beta"]["FE_Type"] = 9
        with pytest.raises(ValueError, match="type de loi inconnu"):
            charger_lois(table)

    def test_une_specification_non_dictionnaire_est_refusee(self) -> None:
        with pytest.raises(ValueError, match="dictionnaire"):
            charger_lois({"CN": [4, 0.0, 0.1]})  # type: ignore[dict-item]

    def test_un_coefficient_inconnu_a_la_lecture_liste_les_disponibles(
        self, lois: JeuDeLois
    ) -> None:
        with pytest.raises(KeyError, match="Cm_alpha"):
            lois["CL"]

    def test_les_six_cles_attendues_sont_celles_du_format(self) -> None:
        assert set(CLES_ATTENDUES) == {
            "Biais_Type",
            "Biais_M",
            "Biais_ET",
            "FE_Type",
            "FE_M",
            "FE_ET",
        }


class TestCorrelation:
    def test_sans_argument_les_composantes_sont_independantes(self, lois: JeuDeLois) -> None:
        assert lois.independantes

    def test_declarer_une_correlation_le_signale(self, table: dict[str, dict[str, float]]) -> None:
        jeu = charger_lois(table, correlation={("Cm_alpha", "Cn_beta"): 0.6})
        assert not jeu.independantes

    def test_nommer_deux_coefficients_apparie_les_composantes_de_meme_nature(
        self, table: dict[str, dict[str, float]]
    ) -> None:
        """Biais avec biais, FE avec FE — pas les quatre croisements.

        Appliquer le même rho aux quatre paires en laissant les couples
        internes à zéro donne une matrice non définie positive dès deux
        coefficients : aucune loi jointe ne la réalise.
        """
        jeu = charger_lois(table, correlation={("Cm_alpha", "Cn_beta"): 0.6})
        decrit = jeu._decrire_correlation()
        assert "(Cm_alpha_Biais, Cn_beta_Biais) = 0.6" in decrit
        assert "(Cm_alpha_FE, Cn_beta_FE) = 0.6" in decrit
        assert "Cn_beta_FE) = 0.6" in decrit and "Cm_alpha_Biais, Cn_beta_FE" not in decrit

    def test_nommer_deux_composantes_cible_cette_seule_paire(
        self, table: dict[str, dict[str, float]]
    ) -> None:
        jeu = charger_lois(table, correlation={("Cm_alpha_Biais", "Cn_beta_FE"): 0.4})
        assert jeu._decrire_correlation() == "(Cm_alpha_Biais, Cn_beta_FE) = 0.4"

    def test_la_correlation_se_retrouve_dans_le_tirage(
        self, table: dict[str, dict[str, float]]
    ) -> None:
        jeu = charger_lois(table, correlation={("Cm_alpha", "Cn_beta"): 0.6})
        ot.RandomGenerator.SetSeed(1)
        echantillon = np.asarray(jeu.distribution_jointe().getSample(20_000))

        # Les colonnes 0 et 2 sont les deux biais ; 0 et 3 un biais et un FE.
        assert np.corrcoef(echantillon[:, 0], echantillon[:, 2])[0, 1] == pytest.approx(
            0.6, abs=0.05
        )
        assert np.corrcoef(echantillon[:, 0], echantillon[:, 3])[0, 1] == pytest.approx(
            0.0, abs=0.05
        )

    def test_une_matrice_pleine_est_acceptee(self, table: dict[str, dict[str, float]]) -> None:
        assert not charger_lois(table, correlation=np.eye(6).tolist()).independantes

    def test_une_matrice_de_mauvaise_taille_est_refusee(
        self, table: dict[str, dict[str, float]]
    ) -> None:
        with pytest.raises(ValueError, match="6×6"):
            charger_lois(table, correlation=np.eye(3).tolist())

    def test_un_nom_inconnu_est_refuse(self, table: dict[str, dict[str, float]]) -> None:
        with pytest.raises(ValueError, match="ni un coefficient ni une composante"):
            charger_lois(table, correlation={("Cm_alpha", "inexistant"): 0.5})

    def test_un_rho_hors_bornes_est_refuse(self, table: dict[str, dict[str, float]]) -> None:
        with pytest.raises(ValueError, match=r"hors de \[-1, 1\]"):
            charger_lois(table, correlation={("Cm_alpha", "Cn_beta"): 3.0})

    def test_une_matrice_non_definie_positive_est_refusee_clairement(
        self, table: dict[str, dict[str, float]]
    ) -> None:
        """Le message doit parler de matrice, pas remonter l'exception SWIG."""
        petite = {c: table[c] for c in ("Cm_alpha", "Cn_beta")}
        impossible = [
            [1.0, 0.9, 0.9, 0.9],
            [0.9, 1.0, 0.9, -0.9],
            [0.9, 0.9, 1.0, 0.9],
            [0.9, -0.9, 0.9, 1.0],
        ]
        with pytest.raises(ValueError, match="définie positive"):
            charger_lois(petite, correlation=impossible)

    def test_une_correlation_fautive_echoue_au_chargement(
        self, table: dict[str, dict[str, float]]
    ) -> None:
        """Pas mille tirages plus tard."""
        with pytest.raises(ValueError):
            charger_lois(table, correlation={("Cm_alpha", "Cn_beta"): 5.0})


class TestDistributionJointe:
    def test_la_dimension_vaut_le_nombre_de_composantes(self, lois: JeuDeLois) -> None:
        assert lois.distribution_jointe().getDimension() == 6

    def test_la_jointe_existe_meme_sans_correlation(self, lois: JeuDeLois) -> None:
        """C'est elle qui rend possibles les plans LHS et Sobol."""
        assert lois.distribution_jointe().getSample(5).getSize() == 5

    def test_une_composante_degeneree_ne_gene_pas_la_jointe(self, lois: JeuDeLois) -> None:
        """``CA_Biais`` est un Dirac : la loi jointe doit l'accepter."""
        ot.RandomGenerator.SetSeed(3)
        echantillon = np.asarray(lois.distribution_jointe().getSample(10))
        assert np.allclose(echantillon[:, 4], 0.001)


class TestYaml:
    def _ecrire(self, tmp_path: Path, texte: str) -> Path:
        chemin = tmp_path / "LOIS.yaml"
        chemin.write_text(texte, encoding="utf-8")
        return chemin

    def test_table_directe(self, tmp_path: Path) -> None:
        chemin = self._ecrire(
            tmp_path,
            """
CN:
  Biais_Type: 4
  Biais_M: 0.0
  Biais_ET: 0.01
  FE_Type: 6
  FE_M: 0.0
  FE_ET: 0.05
""",
        )
        jeu = charger_lois_yaml(chemin)
        assert jeu["CN"].fe.label == "Gaussienne ±2σ"

    def test_table_sous_la_cle_lois(self, tmp_path: Path) -> None:
        chemin = self._ecrire(
            tmp_path,
            """
etude: demo
lois:
  CN:
    Biais_Type: 4
    Biais_M: 0.0
    Biais_ET: 0.01
    FE_Type: 6
    FE_M: 0.0
    FE_ET: 0.05
""",
        )
        assert list(charger_lois_yaml(chemin)) == ["CN"]

    def test_correlation_lue_depuis_le_yaml(self, tmp_path: Path) -> None:
        chemin = self._ecrire(
            tmp_path,
            """
lois:
  CN:
    Biais_Type: 4
    Biais_M: 0.0
    Biais_ET: 0.01
    FE_Type: 6
    FE_M: 0.0
    FE_ET: 0.05
  CA:
    Biais_Type: 4
    Biais_M: 0.0
    Biais_ET: 0.01
    FE_Type: 6
    FE_M: 0.0
    FE_ET: 0.05
correlation:
  "CN, CA": 0.5
""",
        )
        jeu = charger_lois_yaml(chemin)
        assert not jeu.independantes
        assert "(CN_Biais, CA_Biais) = 0.5" in jeu._decrire_correlation()

    def test_un_fichier_absent_est_signale(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="introuvable"):
            charger_lois_yaml(tmp_path / "absent.yaml")

    def test_un_yaml_qui_n_est_pas_une_table_est_refuse(self, tmp_path: Path) -> None:
        chemin = self._ecrire(tmp_path, "- un\n- deux\n")
        with pytest.raises(ValueError, match="attendu une table"):
            charger_lois_yaml(chemin)


class TestRepr:
    def test_le_repr_dit_l_independance(self, lois: JeuDeLois) -> None:
        assert "independantes=True" in repr(lois)

    def test_jeu_de_lois_construit_directement(self, lois: JeuDeLois) -> None:
        copie = JeuDeLois(dict(lois))
        assert list(copie) == list(lois)
