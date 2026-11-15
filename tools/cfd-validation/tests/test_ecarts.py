from __future__ import annotations

import math

import numpy as np
import pytest

from cfd_validation.core import statuts as st
from cfd_validation.core.ecarts import comparer_exact, comparer_numerique, distance_ulp
from cfd_validation.core.format import formater, formater_court, pourcentage
from cfd_validation.core.tolerance import Tolerance


class TestDistanceUlp:
    def test_voisins_a_un_ulp(self) -> None:
        x = np.array([1.0, -1.0, 1e-300, 0.0, 3.5e10])
        assert np.all(distance_ulp(x, np.nextafter(x, np.inf)) == 1)
        assert np.all(distance_ulp(x, np.nextafter(x, -np.inf)) == 1)

    def test_traverse_zero(self) -> None:
        petit = np.nextafter(0.0, 1.0)
        assert distance_ulp(np.array([-petit]), np.array([petit]))[0] == 2

    def test_zeros_signes_et_egalite(self) -> None:
        assert distance_ulp(np.array([0.0]), np.array([-0.0]))[0] == 0
        assert distance_ulp(np.array([2.0]), np.array([2.0]))[0] == 0

    def test_nan(self) -> None:
        assert math.isnan(distance_ulp(np.array([np.nan]), np.array([1.0]))[0])

    def test_symetrique(self) -> None:
        a, b = np.array([1.0, -3.0]), np.array([1.5, 2.0])
        assert np.array_equal(distance_ulp(a, b), distance_ulp(b, a))


class TestComparerNumerique:
    tol = Tolerance(rtol=1e-6, atol=1e-12)

    def test_statuts(self) -> None:
        r = np.array([1.0, 1.0, 1.0, np.nan, np.nan, np.inf, np.inf, 0.0])
        t = np.array([1.0, 1.0 + 1e-7, 1.1, np.nan, 1.0, np.inf, -np.inf, 1e-13])
        e = comparer_numerique(r, t, self.tol)
        attendu = [st.IDENTIQUE, st.TOLERE, st.ECART, st.IDENTIQUE, st.NON_FINI, st.IDENTIQUE, st.NON_FINI, st.TOLERE]
        assert e.statut.tolist() == attendu

    def test_marge_signee_et_infinie_pour_non_fini(self) -> None:
        e = comparer_numerique(np.array([2.0, 1.0, 1.0]), np.array([2.0 - 4e-6, np.nan, 1.0]), self.tol)
        assert e.marge[0] == pytest.approx(-4e-6 / (1e-12 + 2e-6))
        assert e.marge[1] == np.inf
        assert e.marge[2] == 0.0

    def test_frontiere_incluse(self) -> None:
        tol = Tolerance(rtol=0.0, atol=0.5)
        e = comparer_numerique(np.array([1.0]), np.array([1.5]), tol)
        assert e.statut[0] == st.TOLERE

    def test_tolerance_nulle_exige_l_identite(self) -> None:
        e = comparer_numerique(np.array([1.0, 0.0]), np.array([np.nextafter(1.0, 2.0), 0.0]), Tolerance(0.0, 0.0))
        assert e.statut.tolist() == [st.ECART, st.IDENTIQUE]
        assert e.marge[0] == np.inf

    def test_reference_nulle(self) -> None:
        e = comparer_numerique(np.array([0.0]), np.array([1e-20]), Tolerance(rtol=1e-9, atol=0.0))
        assert e.statut[0] == st.ECART
        assert e.ecart_rel[0] == np.inf

    def test_ecart_signe_test_moins_ref(self) -> None:
        e = comparer_numerique(np.array([1.0]), np.array([3.0]), self.tol)
        assert e.ecart[0] == 2.0

    def test_longueurs(self) -> None:
        with pytest.raises(ValueError, match="longueurs"):
            comparer_numerique(np.zeros(2), np.zeros(3), self.tol)


def test_comparer_exact() -> None:
    r = np.array(["a", "b", None, None, "c"], dtype=object)
    t = np.array(["a", "x", None, "d", float("nan")], dtype=object)
    assert comparer_exact(r, t).statut.tolist() == [st.IDENTIQUE, st.ECART, st.IDENTIQUE, st.ECART, st.ECART]


class TestTolerance:
    def test_refuse_negatif_et_infini(self) -> None:
        with pytest.raises(ValueError):
            Tolerance(rtol=-1.0)
        with pytest.raises(ValueError):
            Tolerance(atol=math.inf)
        with pytest.raises(TypeError):
            Tolerance(rtol=True)  # type: ignore[arg-type]

    def test_decrire(self) -> None:
        assert Tolerance(1e-9, 1e-12).decrire() == "|Δ| ≤ 1e-12 + 1e-9·|réf|"
        assert Tolerance(0.0, 0.0).decrire() == "identité bit pour bit"
        assert Tolerance(2.5e-7, 0.0).decrire() == "|Δ| ≤ 2.5e-7·|réf|"


def test_format() -> None:
    assert formater(0.0) == "0"
    assert formater(float("nan")) == "—"
    assert formater(1.234e-12) == "1.23e-12"
    assert formater(-99999.99) == "-1.00e+05"  # l'arrondi ne doit pas changer de forme
    assert formater_court(1e-12) == "1e-12"
    assert formater_court(1e5) == "100000"
    assert pourcentage(0, 3) == "0 %"
    assert pourcentage(3, 3) == "100 %"
    assert pourcentage(999, 1000) == "99.9 %"
    assert pourcentage(9999, 10000) == "> 99.9 %"
