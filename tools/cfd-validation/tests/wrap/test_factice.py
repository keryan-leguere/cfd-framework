"""Le faux module livré avec le paquet.

Il sert de double de test à toute la suite, donc ses propres invariants doivent
tenir en premier : les tables sont bien remplies, la queue est bien du
remplissage, et chaque panne annoncée se produit réellement.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cfd_validation.data.entrees import entrees
from cfd_validation.data.spec import SpecTable, charger_tables
from cfd_validation.wrap.bloc import lire_table
from cfd_validation.wrap.factice import (
    ANGLES,
    BUGS,
    CAPACITE_CN,
    REMPLISSAGE,
    TABLES,
    ModeleFactice,
    ModuleFactice,
)


class TestLesTables:
    def test_le_tableau_cn_est_dimensionne_plus_large_que_son_remplissage(
        self, module: ModuleFactice
    ) -> None:
        """C'est la situation réelle, et c'est elle qui rend « lignes » nécessaire."""
        tableau = np.asarray(module.tab_cn.tab_cn)
        remplies = int(np.asarray(module.tab_cn.npt_cn))
        assert tableau.shape == (CAPACITE_CN, 4)
        assert remplies < CAPACITE_CN

    def test_la_queue_porte_la_valeur_de_remplissage(self, module: ModuleFactice) -> None:
        tableau = np.asarray(module.tab_cn.tab_cn)
        remplies = int(np.asarray(module.tab_cn.npt_cn))
        assert np.all(tableau[remplies:] == REMPLISSAGE)

    def test_incidence_et_braquage_partagent_leur_jeu_de_valeurs(
        self, module: ModuleFactice, spec_cn: SpecTable
    ) -> None:
        """Sans quoi une transposition de ces deux axes serait indétectable.

        Un nœud transposé n'existerait tout simplement pas dans la table.
        """
        table = lire_table(module, spec_cn)
        assert set(table["alpha"].unique()) == set(ANGLES)
        assert set(table["delta"].unique()) == set(ANGLES)

    def test_la_declaration_livree_lit_bien_les_tables(
        self, module: ModuleFactice, specs: dict[str, SpecTable]
    ) -> None:
        assert len(lire_table(module, specs["CN"])) == 294
        assert len(lire_table(module, specs["CA"])) == 42

    def test_la_valeur_tabulee_depend_vraiment_des_trois_axes(
        self, module: ModuleFactice, spec_cn: SpecTable
    ) -> None:
        """Un axe sans effet rendrait ``axe_ignore`` indétectable."""
        table = lire_table(module, spec_cn)
        for axe in ("mach", "alpha", "delta"):
            autres = [colonne for colonne in ("mach", "alpha", "delta") if colonne != axe]
            groupe = table.groupby(autres)["CN"].nunique()
            assert groupe.max() > 1, f"CN ne dépend pas de {axe}"


class TestLeModele:
    def test_sans_panne_le_modele_relit_exactement(
        self, module: ModuleFactice, spec_cn: SpecTable
    ) -> None:
        table = lire_table(module, spec_cn)
        rendu = ModeleFactice(module)(entrees(table, spec_cn))
        assert np.array_equal(rendu["CN"].to_numpy(), table["CN"].to_numpy())

    def test_le_modele_rend_les_lignes_dans_l_ordre_recu(
        self, module: ModuleFactice, spec_cn: SpecTable
    ) -> None:
        table = lire_table(module, spec_cn)
        demande = entrees(table, spec_cn)
        rendu = ModeleFactice(module)(demande)
        assert rendu.index.tolist() == demande.index.tolist()
        assert np.array_equal(rendu["mach"].to_numpy(), demande["mach"].to_numpy())

    @pytest.mark.parametrize("panne", sorted(BUGS))
    def test_chaque_panne_change_effectivement_le_resultat(
        self, panne: str, module: ModuleFactice, spec_cn: SpecTable
    ) -> None:
        """Une panne qui ne casse rien ferait passer son détecteur pour bon."""
        table = lire_table(module, spec_cn)
        demande = entrees(table, spec_cn)
        juste = ModeleFactice(module)(demande)["CN"].to_numpy()
        casse = ModeleFactice(module, bug=panne)(demande)["CN"].to_numpy()
        assert not np.array_equal(juste, casse)

    def test_une_panne_inconnue_est_refusee_en_listant_les_connues(
        self, module: ModuleFactice
    ) -> None:
        with pytest.raises(ValueError, match="panne inconnue"):
            ModeleFactice(module, bug="inexistante")

    def test_le_bruit_est_reproductible_a_graine_egale(
        self, module: ModuleFactice, spec_cn: SpecTable
    ) -> None:
        demande = entrees(lire_table(module, spec_cn), spec_cn)
        premier = ModeleFactice(module, bug="bruit", graine=7)(demande)["CN"].to_numpy()
        second = ModeleFactice(module, bug="bruit", graine=7)(demande)["CN"].to_numpy()
        assert np.array_equal(premier, second)

    def test_le_modele_rend_bien_un_dataframe(
        self, module: ModuleFactice, spec_cn: SpecTable
    ) -> None:
        rendu = ModeleFactice(module)(entrees(lire_table(module, spec_cn), spec_cn))
        assert isinstance(rendu, pd.DataFrame)


class TestCoherenceAvecLaDocumentation:
    def test_chaque_panne_annonce_un_motif_existant(self) -> None:
        from cfd_validation.core.motifs import ORDRE_SPECIFICITE

        assert set(BUGS.values()) <= set(ORDRE_SPECIFICITE)

    def test_la_declaration_livree_est_valide(self) -> None:
        assert set(charger_tables(TABLES)) == {"CN", "CA"}
