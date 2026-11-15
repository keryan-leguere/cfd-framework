from __future__ import annotations

import math

import numpy as np

from cfd_validation.core.attribution import comptes_par_niveau, discretiser, v_cramer


class TestDiscretiser:
    def test_valeurs_distinctes(self) -> None:
        d = discretiser(np.array([0.3, 1.2, 0.3, 2.0]))
        assert d.libelles == ("0.3", "1.2", "2")
        assert d.codes.tolist() == [0, 1, 0, 2]
        assert not d.en_classes

    def test_classes_au_dela_du_plafond(self) -> None:
        x = np.linspace(0.0, 1.0, 200)
        d = discretiser(x, max_niveaux=12, n_classes=8)
        assert d.en_classes
        assert d.n_niveaux == 8
        assert np.bincount(d.codes).min() >= 24  # classes de quantiles : effectifs équilibrés
        assert d.codes.max() == 7  # le maximum tombe dans la dernière classe, fermée

    def test_nan_forme_un_niveau(self) -> None:
        d = discretiser(np.array([1.0, np.nan, 2.0]))
        assert d.libelles[-1] == "NaN"
        assert d.codes[1] == d.n_niveaux - 1

    def test_categories_plus_frequentes_d_abord_et_reliquat(self) -> None:
        v = np.array(["b", "a", "a", "c", "d", "a", "b"], dtype=object)
        d = discretiser(v, max_niveaux=3)
        assert d.libelles == ("a", "b", "autres")
        assert d.codes.tolist() == [1, 0, 0, 2, 2, 0, 1]

    def test_pd_na(self) -> None:
        import pandas as pd

        d = discretiser(np.array(["x", pd.NA, None], dtype=object))
        assert "NaN" in d.libelles


class TestVCramer:
    codes = np.repeat(np.arange(4), 25)

    def test_liaison_parfaite(self) -> None:
        echec = self.codes == 2
        assert v_cramer(self.codes, echec, 4) == 1.0

    def test_independance(self) -> None:
        echec = np.tile([True, False, False, False, False], 20)
        assert v_cramer(self.codes, echec, 4) < 0.05

    def test_sans_objet(self) -> None:
        assert math.isnan(v_cramer(self.codes, np.zeros(100, dtype=bool), 4))
        assert math.isnan(v_cramer(self.codes, np.ones(100, dtype=bool), 4))
        assert math.isnan(v_cramer(np.zeros(10, dtype=np.int64), np.arange(10) < 3, 1))

    def test_comptes(self) -> None:
        n, e = comptes_par_niveau(np.array([0, 0, 1, 2]), np.array([True, False, True, False]), 4)
        assert n.tolist() == [2, 1, 1, 0]
        assert e.tolist() == [1, 1, 0, 0]
