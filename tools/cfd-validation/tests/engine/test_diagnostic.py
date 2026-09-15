"""Le pont entre les cadres de données et les détecteurs.

Mince à dessein : les détecteurs travaillent sur des tableaux NumPy et ne
doivent rien savoir de pandas.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from cfd_validation.core.ecart import comparer
from cfd_validation.data.spec import SpecTable
from cfd_validation.engine.diagnostic import contexte_de, diagnostiquer
from cfd_validation.wrap.bloc import lire_table
from cfd_validation.wrap.factice import ModeleFactice, ModuleFactice


class TestContexte:
    def test_le_contexte_ne_porte_que_les_colonnes_independantes(
        self, module: ModuleFactice, spec_cn: SpecTable
    ) -> None:
        table = lire_table(module, spec_cn)
        ecart = comparer(table["CN"], table["CN"])
        contexte = contexte_de(table, spec_cn, ecart)
        assert contexte.noms == ("mach", "alpha", "delta")
        assert contexte.noeuds.shape == (len(table), 3)

    def test_les_colonnes_gardent_l_ordre_declare(
        self, module: ModuleFactice, spec_cn: SpecTable
    ) -> None:
        """Les détecteurs nomment un axe par sa position ; l'ordre est donc porteur."""
        table = lire_table(module, spec_cn)
        contexte = contexte_de(table, spec_cn, comparer(table["CN"], table["CN"]))
        assert np.array_equal(contexte.noeuds[:, 1], table["alpha"].to_numpy())


class TestDiagnostic:
    def test_rien_a_diagnostiquer_quand_tout_est_conforme(
        self, module: ModuleFactice, spec_cn: SpecTable
    ) -> None:
        table = lire_table(module, spec_cn)
        assert diagnostiquer(table, spec_cn, comparer(table["CN"], table["CN"])) == ()

    def test_un_ecart_produit_au_moins_le_motif_descriptif(
        self, module: ModuleFactice, spec_cn: SpecTable, modele: Any
    ) -> None:
        from cfd_validation.data.entrees import entrees

        table = lire_table(module, spec_cn)
        rendu = ModeleFactice(module, bug="bruit")(entrees(table, spec_cn))
        motifs = diagnostiquer(table, spec_cn, comparer(table["CN"], rendu["CN"]))
        assert motifs
        assert motifs[-1].nom == "diffus"
