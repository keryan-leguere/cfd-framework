"""Derived columns: aeroballistic angles, folded azimuth, free-stream state."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_traj.core.adim import Reference, nondimensionalise
from cfd_traj.core.angles import to_aeroballistic
from cfd_traj.core.symmetry import SymmetryGroup, SymmetrySpec
from cfd_traj.data.columns import DERIVED_COLUMNS
from cfd_traj.data.dataset import load_dataset
from cfd_traj.data.derive import add_derived_columns

REF = Reference(length_m=2.5)
C4V = SymmetrySpec(group=SymmetryGroup.C4V)


class TestDerivedColumns:
    def test_exactly_the_declared_columns_are_added(self, lot_simple):
        derived = add_derived_columns(lot_simple, reference=REF, symmetry=C4V)

        assert set(derived.columns) - set(lot_simple.columns) == set(DERIVED_COLUMNS)
        assert set(derived.derived_columns) == set(DERIVED_COLUMNS)

    def test_deriving_twice_is_idempotent(self, lot_simple):
        once = add_derived_columns(lot_simple, reference=REF, symmetry=C4V)
        twice = add_derived_columns(once, reference=REF, symmetry=C4V)

        assert twice.columns == once.columns
        for name in DERIVED_COLUMNS:
            assert np.allclose(twice.values(name), once.values(name), equal_nan=True)

    def test_the_angles_match_a_direct_call_to_the_core(self, lot_derive):
        alpha_tot, phi, defined = to_aeroballistic(
            lot_derive.values("alpha"), lot_derive.values("beta")
        )

        assert np.allclose(lot_derive.values("alpha_tot"), alpha_tot)
        assert np.allclose(lot_derive.values("phi"), phi)
        assert np.array_equal(lot_derive.values("phi_defined").astype(bool), defined)

    def test_the_free_stream_state_matches_a_direct_call_to_the_core(self, lot_derive):
        expected = nondimensionalise(
            lot_derive.values("Mach"), lot_derive.values("Altitude"), reference=REF
        )

        for key, values in expected.items():
            assert np.allclose(lot_derive.values(key), values)

    def test_the_reference_reynolds_scales_with_the_reference_length(self, lot_simple):
        short = add_derived_columns(lot_simple, reference=Reference(length_m=1.0), symmetry=C4V)
        long = add_derived_columns(lot_simple, reference=Reference(length_m=4.0), symmetry=C4V)

        assert np.allclose(long.values("Re_ref"), 4.0 * short.values("Re_ref"))


class TestFolding:
    @pytest.mark.parametrize("group", list(SymmetryGroup))
    def test_the_folded_azimuth_lands_in_the_group_domain(self, lot_simple, group):
        spec = SymmetrySpec(group=group)

        derived = add_derived_columns(lot_simple, reference=REF, symmetry=spec)

        low, high = spec.fundamental_domain_deg
        phi = derived.values("phi_fold")
        assert np.all(phi >= low - 1e-9)
        assert np.all(phi <= high + 1e-9)

    def test_changing_the_group_changes_the_fold_but_not_the_raw_azimuth(self, lot_simple):
        c4v = add_derived_columns(lot_simple, reference=REF, symmetry=C4V)
        c1 = add_derived_columns(
            lot_simple, reference=REF, symmetry=SymmetrySpec(group=SymmetryGroup.C1)
        )

        assert np.allclose(c4v.values("phi"), c1.values("phi"))
        assert not np.allclose(c4v.values("phi_fold"), c1.values("phi_fold"))


class TestEdgeCases:
    def test_zero_incidence_rows_report_an_undefined_azimuth(self, make_lot):
        directory = make_lot(
            n_shots=1,
            overrides={
                "alpha": lambda d: np.zeros(d["time"].size),
                "beta": lambda d: np.zeros(d["time"].size),
            },
        )

        derived = add_derived_columns(load_dataset(directory), reference=REF, symmetry=C4V)

        assert np.all(derived.values("phi_defined") == 0.0)
        assert np.all(derived.values("alpha_tot") == 0.0)
        assert np.all(derived.values("phi_fold") == 0.0)

    def test_nan_angles_propagate_without_breaking_the_other_columns(self, make_lot):
        def spoil(data):
            out = data["alpha"].copy()
            out[:3] = np.nan
            return out

        derived = add_derived_columns(
            load_dataset(make_lot(n_shots=1, overrides={"alpha": spoil})),
            reference=REF,
            symmetry=C4V,
        )

        assert np.isnan(derived.values("alpha_tot")[:3]).all()
        assert np.isfinite(derived.values("q_inf")).all()

    def test_an_isa_offset_moves_the_thermodynamics_but_not_the_mach(self, lot_simple):
        cold = add_derived_columns(lot_simple, reference=REF, symmetry=C4V, delta_t_k=0.0)
        warm = add_derived_columns(lot_simple, reference=REF, symmetry=C4V, delta_t_k=25.0)

        assert np.allclose(warm.values("Mach"), cold.values("Mach"))
        assert np.allclose(warm.values("T_inf"), cold.values("T_inf") + 25.0)
        # Warm air is thinner only low down: higher up the larger scale height
        # wins and the warm column ends up denser, so restrict the comparison.
        low = cold.values("Altitude") < 3_000.0
        assert low.any()
        assert np.all(warm.values("rho_inf")[low] < cold.values("rho_inf")[low])
