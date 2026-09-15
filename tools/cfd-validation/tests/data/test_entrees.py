"""Les entrées du modèle, et le contrôle de ce qu'il rend.

Deux invariants portent tout le reste du paquet :

* le modèle ne reçoit **jamais** la réponse ;
* les cadres « table » et « modèle » partagent leurs abscisses **au bit près**,
  sans quoi le filtre par égalité stricte de ``batch_plot`` perdrait des
  courbes en silence.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cfd_validation.data.entrees import (
    ErreurModele,
    cadre_modele,
    cadre_table,
    entrees,
    verifier_sortie,
)
from cfd_validation.data.spec import SpecTable, charger_tables


@pytest.fixture
def spec() -> SpecTable:
    return charger_tables(
        {
            "CN": {
                "bloc": "b",
                "colonnes": ["mach", "alpha", "CN"],
                "qoi": ["CN"],
                "constantes": {"beta": 0.0},
            }
        }
    )["CN"]


@pytest.fixture
def table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "mach": [0.3, 0.3, 0.8, 0.8],
            "alpha": [0.0, 4.0, 0.0, 4.0],
            "CN": [0.1, 0.5, 0.2, 0.6],
        }
    )


class TestEntrees:
    def test_les_qoi_ne_sont_jamais_passees_au_modele(
        self, table: pd.DataFrame, spec: SpecTable
    ) -> None:
        """C'est ce retrait qui fait du contrôle un contrôle."""
        demande = entrees(table, spec)
        assert "CN" not in demande.columns

    def test_les_constantes_declarees_completent_le_cadre(
        self, table: pd.DataFrame, spec: SpecTable
    ) -> None:
        demande = entrees(table, spec)
        assert list(demande.columns) == ["mach", "alpha", "beta"]
        assert (demande["beta"] == 0.0).all()

    def test_l_index_de_la_table_est_conserve(self, table: pd.DataFrame, spec: SpecTable) -> None:
        """Pour que le rapport désigne un point par sa ligne dans le tableau Fortran."""
        demande = entrees(table, spec)
        assert demande.index.tolist() == table.index.tolist()

    def test_une_colonne_declaree_mais_absente_de_la_table_est_refusee(
        self, spec: SpecTable
    ) -> None:
        with pytest.raises(ErreurModele, match="absente"):
            entrees(pd.DataFrame({"mach": [0.3]}), spec)


class TestVerificationDuRendu:
    def test_un_rendu_conforme_passe(self, table: pd.DataFrame, spec: SpecTable) -> None:
        demande = entrees(table, spec)
        rendu = demande.assign(CN=[1.0, 2.0, 3.0, 4.0])
        assert list(verifier_sortie(demande, rendu, spec)["CN"]) == [1.0, 2.0, 3.0, 4.0]

    def test_un_objet_qui_n_est_pas_un_dataframe_est_refuse(
        self, table: pd.DataFrame, spec: SpecTable
    ) -> None:
        demande = entrees(table, spec)
        with pytest.raises(ErreurModele, match="DataFrame"):
            verifier_sortie(demande, {"CN": [1.0]}, spec)

    def test_un_mauvais_nombre_de_lignes_est_refuse(
        self, table: pd.DataFrame, spec: SpecTable
    ) -> None:
        demande = entrees(table, spec)
        with pytest.raises(ErreurModele, match="a rendu"):
            verifier_sortie(demande, demande.head(2).assign(CN=1.0), spec)

    def test_une_qoi_absente_est_refusee_en_listant_ce_qui_a_ete_rendu(
        self, table: pd.DataFrame, spec: SpecTable
    ) -> None:
        demande = entrees(table, spec)
        with pytest.raises(ErreurModele) as capture:
            verifier_sortie(demande, demande.assign(CY=1.0), spec)
        assert "CY" in str(capture.value)

    def test_des_lignes_reordonnees_sont_refusees(
        self, table: pd.DataFrame, spec: SpecTable
    ) -> None:
        """Un tri glissé dans la chaîne d'appel comparerait chaque point au voisin.

        Sans ce refus, le contrôle sortirait rouge sur un modèle juste — et
        c'est le genre de faux positif qui fait abandonner un outil.
        """
        demande = entrees(table, spec)
        rendu = demande.iloc[::-1].assign(CN=[4.0, 3.0, 2.0, 1.0]).reset_index(drop=True)
        with pytest.raises(ErreurModele, match="dans l'ordre reçu"):
            verifier_sortie(demande, rendu, spec)

    def test_un_aller_retour_en_simple_precision_reste_accepte(
        self, table: pd.DataFrame, spec: SpecTable
    ) -> None:
        """La tolérance d'alignement doit absorber le Fortran, pas un tri."""
        demande = entrees(table, spec)
        rendu = demande.astype(np.float32).astype(float).assign(CN=1.0)
        verifier_sortie(demande, rendu, spec)

    def test_un_index_different_mais_ordonne_est_realigne(
        self, table: pd.DataFrame, spec: SpecTable
    ) -> None:
        """Un modèle qui rend un index neuf est courant, et ce n'est pas une faute."""
        demande = entrees(table, spec)
        rendu = demande.reset_index(drop=True).assign(CN=1.0)
        rendu.index = pd.Index([10, 11, 12, 13])
        aligne = verifier_sortie(demande, rendu, spec)
        assert aligne.index.tolist() == demande.index.tolist()

    def test_une_qoi_non_numerique_est_refusee(self, table: pd.DataFrame, spec: SpecTable) -> None:
        demande = entrees(table, spec)
        with pytest.raises(ErreurModele, match="pas numérique"):
            verifier_sortie(demande, demande.assign(CN="beaucoup"), spec)


class TestCadres:
    def test_les_deux_cadres_partagent_leurs_abscisses_au_bit_pres(
        self, table: pd.DataFrame, spec: SpecTable
    ) -> None:
        """L'invariant sur lequel repose tout le tracé.

        ``batch_plot`` filtre ses points de vol par **égalité stricte** : un
        aller-retour en simple précision côté Fortran suffirait à faire
        disparaître une courbe entière d'une planche, sans erreur.
        """
        demande = entrees(table, spec)
        rendu = demande.astype(np.float32).astype(float).assign(CN=[1.0, 2.0, 3.0, 4.0])
        aligne = verifier_sortie(demande, rendu, spec)

        reference = cadre_table(table, spec)
        obtenu = cadre_modele(table, aligne, spec)

        for colonne in spec.entrees_attendues:
            assert reference[colonne].to_numpy().tobytes() == obtenu[colonne].to_numpy().tobytes()

    def test_le_cadre_modele_porte_la_qoi_du_modele(
        self, table: pd.DataFrame, spec: SpecTable
    ) -> None:
        demande = entrees(table, spec)
        rendu = demande.assign(CN=[9.0, 9.0, 9.0, 9.0])
        obtenu = cadre_modele(table, rendu, spec)
        assert obtenu["CN"].tolist() == [9.0, 9.0, 9.0, 9.0]

    def test_le_cadre_table_porte_la_qoi_tabulee(
        self, table: pd.DataFrame, spec: SpecTable
    ) -> None:
        assert cadre_table(table, spec)["CN"].tolist() == table["CN"].tolist()

    def test_les_deux_cadres_ont_exactement_les_memes_colonnes(
        self, table: pd.DataFrame, spec: SpecTable
    ) -> None:
        demande = entrees(table, spec)
        rendu = demande.assign(CN=1.0)
        assert list(cadre_table(table, spec).columns) == list(
            cadre_modele(table, rendu, spec).columns
        )
