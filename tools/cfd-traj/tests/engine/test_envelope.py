"""The conditional envelope, band by band."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_traj.core.stats import quantile_bounds
from cfd_traj.core.symmetry import SymmetryGroup, SymmetrySpec, azimuth_levels
from cfd_traj.data.columns import ColumnSpec, Role, build_specs
from cfd_traj.data.study import BandSpec, EnvelopeSpec
from cfd_traj.engine.bands import build_bands
from cfd_traj.engine.envelope import PHI_COLUMN, build_envelope

C4V = SymmetrySpec(group=SymmetryGroup.C4V)


class TestStructure:
    def test_one_entry_per_active_variable_per_band(self, envelope, specs):
        active = [s.name for s in specs if s.is_active]

        for band in envelope.bands:
            assert [v.name for v in band.variables] == active

    def test_ignored_variables_are_absent(self, envelope):
        for band in envelope.bands:
            assert band.get("time") is None
            assert band.get("Altitude") is None
            assert band.get("alpha") is None

    def test_the_table_has_one_row_per_band_and_variable(self, envelope):
        rows = envelope.table_rows()

        assert len(rows) == sum(len(b.variables) for b in envelope.bands)
        assert {"bande", "variable", "borne_basse", "borne_haute", "niveaux"} <= set(rows[0])

    def test_a_band_can_be_looked_up_by_mach(self, envelope):
        band = envelope.bands[1]

        assert envelope.band_of(band.band.mid) is band

    def test_mechanical_variables_are_excluded_from_the_tested_set(self, envelope):
        assert "dl" in envelope.active_names
        assert "dl" not in envelope.tested_names


class TestBounds:
    def test_the_bounds_bracket_the_quantiles_which_bracket_the_median(self, envelope):
        for band in envelope.bands:
            for variable in band.variables:
                bounds = variable.bounds
                if not np.isfinite(bounds.median):
                    continue
                assert bounds.low <= bounds.q_low_value + 1e-9
                assert bounds.q_low_value <= bounds.median + 1e-9
                assert bounds.median <= bounds.q_high_value + 1e-9
                assert bounds.q_high_value <= bounds.high + 1e-9

    def test_the_bounds_match_a_direct_call_on_the_band_subset(self, dataset_realiste, envelope):
        band = envelope.bands[2]
        mask = band.band.contains(dataset_realiste.values("Mach"))
        variable = band.get("PARA2")
        assert variable is not None

        expected = quantile_bounds(
            dataset_realiste.values("PARA2")[mask],
            q_low=envelope.spec.q_low,
            q_high=envelope.spec.q_high,
            margin=envelope.spec.margin,
            log_scaled=variable.spec.log_scaled,
            physical_min=variable.spec.physical_min,
        )
        assert variable.bounds.low == pytest.approx(expected.low)
        assert variable.bounds.high == pytest.approx(expected.high)

    def test_a_band_is_strictly_narrower_than_the_whole_lot(self, dataset_realiste, envelope):
        # The point of conditioning: a Mach-correlated parameter has a much
        # tighter range inside a band than over the whole flight.
        whole = quantile_bounds(dataset_realiste.values("PARA1"))
        band = envelope.bands[0].get("PARA1")
        assert band is not None

        assert band.bounds.width < whole.width

    def test_a_wider_margin_widens_every_bound(self, dataset_realiste, band_set, specs):
        narrow = build_envelope(
            dataset_realiste,
            band_set=band_set,
            specs=specs,
            spec=EnvelopeSpec(margin=0.05),
            symmetry=C4V,
        )
        wide = build_envelope(
            dataset_realiste,
            band_set=band_set,
            specs=specs,
            spec=EnvelopeSpec(margin=0.20),
            symmetry=C4V,
        )

        left = narrow.bands[1].get("PARA2")
        right = wide.bands[1].get("PARA2")
        assert left is not None and right is not None
        assert right.bounds.low < left.bounds.low
        assert right.bounds.high > left.bounds.high
        assert right.bounds.q_low_value == pytest.approx(left.bounds.q_low_value)


class TestLevels:
    def test_every_level_sits_inside_its_bounds_sorted_and_unique(self, envelope):
        for band in envelope.bands:
            for variable in band.variables:
                levels = variable.levels
                assert list(levels) == sorted(levels)
                assert len(set(levels)) == len(levels)
                assert all(variable.bounds.low - 1e-9 <= x for x in levels)
                assert all(x <= variable.bounds.high + 1e-9 for x in levels)

    def test_a_grid_axis_reaches_both_of_its_bounds(self, envelope):
        variable = envelope.bands[1].get("PARA2")
        assert variable is not None

        assert variable.levels[0] == pytest.approx(variable.bounds.low)
        assert variable.levels[-1] == pytest.approx(variable.bounds.high)

    def test_the_azimuth_levels_come_from_the_group_not_from_the_data(self, envelope):
        expected = azimuth_levels(C4V)

        for band in envelope.bands:
            variable = band.get(PHI_COLUMN)
            assert variable is not None
            assert variable.levels == expected

    def test_a_mechanical_variable_keeps_its_declared_range_in_every_band(
        self, dataset_realiste, band_set
    ):
        declared = {
            "dl": ColumnSpec(
                name="dl", role=Role.MECANIQUE, mechanical_range=(-20.0, 20.0), levels=3
            )
        }
        specs, _ = build_specs(dataset_realiste.columns, dataset_realiste.column_values(), declared)

        envelope = build_envelope(
            dataset_realiste,
            band_set=band_set,
            specs=specs,
            spec=EnvelopeSpec(),
            symmetry=C4V,
        )

        for band in envelope.bands:
            variable = band.get("dl")
            assert variable is not None
            assert (variable.bounds.low, variable.bounds.high) == (-20.0, 20.0)
            assert variable.levels == (-20.0, 0.0, 20.0)

    def test_a_discrete_variable_keeps_its_observed_values_when_it_has_few(
        self, dataset_realiste, band_set
    ):
        declared = {"PARA2": ColumnSpec(name="PARA2", role=Role.DISCRET, levels=2)}
        specs, _ = build_specs(dataset_realiste.columns, dataset_realiste.column_values(), declared)

        envelope = build_envelope(
            dataset_realiste, band_set=band_set, specs=specs, spec=EnvelopeSpec(), symmetry=C4V
        )

        variable = envelope.bands[0].get("PARA2")
        assert variable is not None
        assert len(variable.levels) == 2


class TestDegenerateBands:
    def test_a_thin_band_produces_bounds_and_a_warning(self, dataset_realiste, specs):
        mach = dataset_realiste.values("Mach")
        edges = (float(mach.min()), float(mach.min()) + 1e-4, float(mach.max()))
        band_set = build_bands(mach, BandSpec(edges=edges))

        envelope = build_envelope(
            dataset_realiste, band_set=band_set, specs=specs, spec=EnvelopeSpec(), symmetry=C4V
        )

        thin = envelope.bands[0]
        # Every shot launches from the same initial condition, so this sliver
        # of a band holds one identical point per shot and nothing else.
        assert thin.n_points <= envelope.bands[-1].n_points
        assert any("constante" in w for w in thin.warnings)
        assert all(v.bounds.width >= 0.0 for v in thin.variables)

    def test_a_constant_variable_still_gets_a_usable_width(self, make_lot, band_set):
        from cfd_traj.core.adim import Reference
        from cfd_traj.data.dataset import load_dataset
        from cfd_traj.data.derive import add_derived_columns

        directory = make_lot(n_shots=3, overrides={"PARA2": lambda d: np.full(d["time"].size, 7.0)})
        ds = add_derived_columns(
            load_dataset(directory), reference=Reference(length_m=2.5), symmetry=C4V
        )
        specs, _ = build_specs(ds.columns, ds.column_values(), {})
        bands = build_bands(ds.values("Mach"), BandSpec(n_bands=3, min_points=10))

        envelope = build_envelope(
            ds, band_set=bands, specs=specs, spec=EnvelopeSpec(), symmetry=C4V
        )

        variable = envelope.bands[0].get("PARA2")
        assert variable is not None
        assert variable.bounds.width > 0.0

    def test_an_all_nan_variable_is_noted_rather_than_fatal(self, make_lot):
        from cfd_traj.core.adim import Reference
        from cfd_traj.data.dataset import load_dataset
        from cfd_traj.data.derive import add_derived_columns

        directory = make_lot(
            n_shots=3, overrides={"PARA2": lambda d: np.full(d["time"].size, np.nan)}
        )
        ds = add_derived_columns(
            load_dataset(directory), reference=Reference(length_m=2.5), symmetry=C4V
        )
        specs, _ = build_specs(ds.columns, ds.column_values(), {})
        bands = build_bands(ds.values("Mach"), BandSpec(n_bands=3, min_points=10))

        envelope = build_envelope(
            ds, band_set=bands, specs=specs, spec=EnvelopeSpec(), symmetry=C4V
        )

        assert any("PARA2" in w for band in envelope.bands for w in band.warnings)


class TestGenericity:
    @pytest.mark.parametrize("n_extra", [0, 1, 5])
    def test_any_number_of_generic_columns_gets_an_envelope(self, make_lot, n_extra):
        from cfd_traj.core.adim import Reference
        from cfd_traj.data.dataset import load_dataset
        from cfd_traj.data.derive import add_derived_columns

        extra = tuple(f"COL{i}" for i in range(n_extra))
        ds = add_derived_columns(
            load_dataset(make_lot(n_shots=3, extra=extra)),
            reference=Reference(length_m=2.5),
            symmetry=C4V,
        )
        specs, _ = build_specs(ds.columns, ds.column_values(), {})
        bands = build_bands(ds.values("Mach"), BandSpec(n_bands=3, min_points=10))

        envelope = build_envelope(
            ds, band_set=bands, specs=specs, spec=EnvelopeSpec(), symmetry=C4V
        )

        for band in envelope.bands:
            assert all(band.get(name) is not None for name in extra)


class TestMembership:
    def test_the_median_of_a_band_is_inside_it(self, envelope):
        band = envelope.bands[1]
        point = {v.name: v.bounds.median for v in band.grid_variables()}

        assert band.contains(point)

    def test_a_point_ten_widths_away_is_outside(self, envelope):
        band = envelope.bands[1]
        point = {
            v.name: v.bounds.high + 10.0 * max(v.bounds.width, 1.0) for v in band.grid_variables()
        }

        assert not band.contains(point)

    def test_mechanical_variables_never_make_a_point_fail(self, envelope):
        band = envelope.bands[0]

        assert band.contains({"dl": 1e9})
