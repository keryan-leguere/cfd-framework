"""Describing a lot: statistics, correlations, intrinsic dimension."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_traj.core.adim import Reference
from cfd_traj.core.symmetry import SymmetryGroup, SymmetrySpec
from cfd_traj.data.columns import Role, build_specs
from cfd_traj.data.dataset import load_dataset
from cfd_traj.data.derive import add_derived_columns
from cfd_traj.engine.inspect import inspect

C4V = SymmetrySpec(group=SymmetryGroup.C4V)


def _inspect_lot(directory, **kw):
    ds = add_derived_columns(
        load_dataset(directory), reference=Reference(length_m=2.5), symmetry=C4V
    )
    specs, _ = build_specs(ds.columns, ds.column_values(), {})
    return inspect(ds, specs=specs, **kw), ds, specs


class TestStatistics:
    def test_one_entry_per_active_column(self, dataset_realiste, specs):
        result = inspect(dataset_realiste, specs=specs)

        assert {s.name for s in result.stats} == {s.name for s in specs if s.is_active}

    def test_the_counts_add_up_to_the_lot_height(self, dataset_realiste, specs):
        result = inspect(dataset_realiste, specs=specs)

        for stat in result.stats:
            assert stat.count + stat.n_nan == dataset_realiste.n_rows

    def test_the_quantiles_come_out_in_order(self, dataset_realiste, specs):
        result = inspect(dataset_realiste, specs=specs)

        for stat in result.stats:
            assert stat.minimum <= stat.q05 <= stat.median <= stat.q95 <= stat.maximum

    def test_a_constant_column_has_no_spread(self, make_lot):
        result, _, _ = _inspect_lot(
            make_lot(n_shots=2, overrides={"PARA2": lambda d: np.full(d["time"].size, 4.0)})
        )

        stat = next(s for s in result.stats if s.name == "PARA2")
        assert stat.std == 0.0
        assert stat.n_unique == 1

    def test_an_all_nan_column_does_not_raise(self, make_lot):
        result, ds, _ = _inspect_lot(
            make_lot(n_shots=2, overrides={"PARA2": lambda d: np.full(d["time"].size, np.nan)})
        )

        stat = next(s for s in result.stats if s.name == "PARA2")
        assert stat.count == 0
        assert stat.n_nan == ds.n_rows
        assert np.isnan(stat.median)

    def test_a_statistics_row_uses_french_keys(self, dataset_realiste, specs):
        row = inspect(dataset_realiste, specs=specs).stats[0].as_row()

        assert {"variable", "role", "n_valeurs", "mediane", "ecart_type"} <= set(row)


class TestCorrelation:
    def test_the_matrix_is_square_symmetric_with_a_unit_diagonal(self, dataset_realiste, specs):
        result = inspect(dataset_realiste, specs=specs)

        n = result.n_variables
        assert result.correlation.shape == (n, n)
        assert np.allclose(result.correlation, result.correlation.T)
        assert np.allclose(np.diag(result.correlation), 1.0)

    def test_mechanical_columns_stay_out_of_the_matrix(self, dataset_realiste, specs):
        result = inspect(dataset_realiste, specs=specs)

        assert "dl" not in result.correlation_names
        assert any(s.role is Role.MECANIQUE for s in specs)

    def test_the_strongest_pairs_are_distinct_and_sorted(self, dataset_realiste, specs):
        pairs = inspect(dataset_realiste, specs=specs).strongest_pairs(5)

        assert len(pairs) == 5
        assert all(a != b for a, b, _ in pairs)
        assert [abs(r) for _, _, r in pairs] == sorted([abs(r) for _, _, r in pairs], reverse=True)

    def test_the_mach_correlated_column_tops_the_list(self, dataset_realiste, specs):
        # PARA1 follows Mach by construction in the realistic lot.
        top = inspect(dataset_realiste, specs=specs).strongest_pairs(1)[0]

        assert {top[0], top[1]} == {"Mach", "PARA1"}


class TestPca:
    def test_the_cloud_occupies_fewer_directions_than_it_has_variables(
        self, dataset_realiste, specs
    ):
        # The diagnostic that justifies conditioning on Mach.
        result = inspect(dataset_realiste, specs=specs)

        assert result.pca is not None
        assert result.pca.intrinsic_dimension < result.pca.n_used
        assert result.dimension_is_reduced

    def test_the_analysis_can_be_switched_off(self, dataset_realiste, specs):
        assert inspect(dataset_realiste, specs=specs, with_pca=False).pca is None

    def test_a_stricter_threshold_needs_at_least_as_many_components(self, dataset_realiste, specs):
        loose = inspect(dataset_realiste, specs=specs, pca_threshold=0.80)
        strict = inspect(dataset_realiste, specs=specs, pca_threshold=0.999)

        assert loose.pca is not None and strict.pca is not None
        assert strict.pca.intrinsic_dimension >= loose.pca.intrinsic_dimension

    def test_too_few_variables_produce_no_analysis(self, dataset_realiste, specs):
        few = [s for s in specs if s.name in ("Mach",)]

        assert inspect(dataset_realiste, specs=few).pca is None


class TestConsistency:
    def test_a_non_monotone_shot_is_flagged(self, make_lot):
        def bounce(data):
            t = data["time"].copy()
            t[10:20] = t[9]
            return t

        result, _, _ = _inspect_lot(make_lot(n_shots=3, overrides={"time": bounce}))

        assert any("croissant" in note for note in result.consistency)

    def test_missing_values_are_flagged(self, make_lot):
        def spoil(data):
            out = data["PARA1"].copy()
            out[:4] = np.nan
            return out

        result, _, _ = _inspect_lot(make_lot(n_shots=3, overrides={"PARA1": spoil}))

        assert any("manquantes" in note for note in result.consistency)

    def test_a_clean_lot_produces_no_complaint(self, dataset_realiste, specs):
        assert inspect(dataset_realiste, specs=specs).consistency == ()


class TestGenericity:
    @pytest.mark.parametrize("n_extra", [0, 1, 12])
    def test_any_number_of_generic_columns_is_described(self, make_lot, n_extra):
        extra = tuple(f"COL{i}" for i in range(n_extra))

        result, _, _ = _inspect_lot(make_lot(n_shots=2, extra=extra))

        described = {s.name for s in result.stats}
        assert set(extra) <= described

    def test_the_headline_numbers_describe_the_lot(self, dataset_realiste, specs):
        result = inspect(dataset_realiste, specs=specs)

        assert result.n_shots == dataset_realiste.n_shots
        assert result.n_rows == dataset_realiste.n_rows
        assert result.mach_range[0] < result.mach_range[1]
        assert result.time_span[0] < result.time_span[1]
