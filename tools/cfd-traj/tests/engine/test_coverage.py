"""Replaying trajectories through the envelope."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_traj.core.adim import Reference
from cfd_traj.core.symmetry import SymmetryGroup, SymmetrySpec
from cfd_traj.data.columns import ColumnSpec, Role, build_specs
from cfd_traj.data.dataset import load_dataset
from cfd_traj.data.derive import add_derived_columns
from cfd_traj.data.study import BandSpec, EnvelopeSpec
from cfd_traj.engine.bands import build_bands
from cfd_traj.engine.coverage import check_coverage
from cfd_traj.engine.envelope import build_envelope

C4V = SymmetrySpec(group=SymmetryGroup.C4V)


class TestTheGuarantee:
    def test_the_full_range_envelope_covers_its_own_lot_exactly(
        self, dataset_realiste, envelope_exacte
    ):
        # The one case where 100% is a theorem, not a measurement.
        result = check_coverage(dataset_realiste, envelope=envelope_exacte)

        assert result.rate == 1.0
        assert result.offenders == ()
        assert result.is_complete

    def test_adding_a_margin_keeps_it_at_one_hundred_percent(
        self, dataset_realiste, band_set, specs
    ):
        envelope = build_envelope(
            dataset_realiste,
            band_set=band_set,
            specs=specs,
            spec=EnvelopeSpec(q_low=0.0, q_high=1.0, margin=0.05),
            symmetry=C4V,
        )

        assert check_coverage(dataset_realiste, envelope=envelope).rate == 1.0

    def test_the_default_quantiles_leave_a_measurable_shortfall(self, dataset_realiste, envelope):
        # This is exactly why the command measures instead of promising.
        result = check_coverage(dataset_realiste, envelope=envelope)

        assert result.rate >= 0.98
        assert result.rate <= 1.0

    def test_tight_quantiles_without_margin_are_detected_as_a_shortfall(
        self, dataset_realiste, band_set, specs
    ):
        envelope = build_envelope(
            dataset_realiste,
            band_set=band_set,
            specs=specs,
            spec=EnvelopeSpec(q_low=0.10, q_high=0.90, margin=0.0),
            symmetry=C4V,
        )

        result = check_coverage(dataset_realiste, envelope=envelope)

        assert result.rate < 1.0
        assert result.offenders
        assert not result.is_complete


class TestOffenders:
    def test_every_offender_is_genuinely_outside_its_bound(self, dataset_realiste, band_set, specs):
        envelope = build_envelope(
            dataset_realiste,
            band_set=band_set,
            specs=specs,
            spec=EnvelopeSpec(q_low=0.2, q_high=0.8, margin=0.0),
            symmetry=C4V,
        )

        result = check_coverage(dataset_realiste, envelope=envelope, max_offenders=50)

        for offender in result.offenders:
            if offender.side == "bas":
                assert offender.value < offender.bound
            else:
                assert offender.value > offender.bound

    def test_offenders_come_out_worst_first(self, dataset_realiste, band_set, specs):
        envelope = build_envelope(
            dataset_realiste,
            band_set=band_set,
            specs=specs,
            spec=EnvelopeSpec(q_low=0.2, q_high=0.8, margin=0.0),
            symmetry=C4V,
        )

        result = check_coverage(dataset_realiste, envelope=envelope, max_offenders=30)

        excesses = [o.excess for o in result.offenders]
        assert excesses == sorted(excesses, reverse=True)

    def test_the_offender_list_is_capped(self, dataset_realiste, band_set, specs):
        envelope = build_envelope(
            dataset_realiste,
            band_set=band_set,
            specs=specs,
            spec=EnvelopeSpec(q_low=0.3, q_high=0.7, margin=0.0),
            symmetry=C4V,
        )

        assert (
            len(check_coverage(dataset_realiste, envelope=envelope, max_offenders=4).offenders) == 4
        )

    def test_a_deliberately_displaced_point_tops_the_list(self, dataset_realiste, envelope_exacte):
        # Build the envelope on the clean lot, then move one point well outside
        # it and replay: that point must be named, and named first.
        moved = dataset_realiste.values("PARA2").copy()
        variable = envelope_exacte.bands[0].get("PARA2")
        assert variable is not None
        target = int(
            np.flatnonzero(envelope_exacte.bands[0].band.contains(dataset_realiste.values("Mach")))[
                3
            ]
        )
        moved[target] = variable.bounds.high + 50.0 * max(variable.bounds.width, 1.0)
        spiked = dataset_realiste.with_columns({"PARA2": moved})

        result = check_coverage(spiked, envelope=envelope_exacte)

        assert result.offenders
        assert result.offenders[0].variable == "PARA2"
        assert result.offenders[0].side == "haut"
        assert result.offenders[0].row == target
        assert result.offenders[0].shot == str(dataset_realiste.shot_labels()[target])

    def test_an_offender_serialises_with_french_keys(self, dataset_realiste, band_set, specs):
        envelope = build_envelope(
            dataset_realiste,
            band_set=band_set,
            specs=specs,
            spec=EnvelopeSpec(q_low=0.3, q_high=0.7, margin=0.0),
            symmetry=C4V,
        )

        row = check_coverage(dataset_realiste, envelope=envelope).offenders[0].as_row()

        assert set(row) == {
            "tir",
            "ligne",
            "temps",
            "mach",
            "variable",
            "valeur",
            "borne",
            "cote",
            "exces",
        }


class TestMechanicalVariables:
    def test_mechanical_variables_never_enter_the_rate(self, dataset_realiste, band_set):
        # A deliberately tiny mechanical range: the trajectory leaves it, but
        # the coverage rate must not move -- it is a study-file error instead.
        declared = {
            "dm": ColumnSpec(name="dm", role=Role.MECANIQUE, mechanical_range=(-0.01, 0.01))
        }
        specs, _ = build_specs(dataset_realiste.columns, dataset_realiste.column_values(), declared)
        envelope = build_envelope(
            dataset_realiste,
            band_set=band_set,
            specs=specs,
            spec=EnvelopeSpec(q_low=0.0, q_high=1.0, margin=0.0),
            symmetry=C4V,
        )

        result = check_coverage(dataset_realiste, envelope=envelope)

        assert result.rate == 1.0
        assert result.mechanical_violations
        assert all(v.variable == "dm" for v in result.mechanical_violations)

    def test_a_generous_mechanical_range_produces_no_violation(self, dataset_realiste, envelope):
        result = check_coverage(dataset_realiste, envelope=envelope)

        assert result.mechanical_violations == ()


class TestSpecialRows:
    def test_the_folded_azimuth_is_always_covered(self, dataset_realiste, band_set, specs):
        for group in SymmetryGroup:
            spec = SymmetrySpec(group=group)
            ds = add_derived_columns(
                dataset_realiste, reference=Reference(length_m=2.5), symmetry=spec
            )
            envelope = build_envelope(
                ds, band_set=band_set, specs=specs, spec=EnvelopeSpec(), symmetry=spec
            )

            result = check_coverage(ds, envelope=envelope)

            assert result.failures_by_variable().get("phi_fold", 0) == 0

    def test_rows_at_zero_incidence_count_as_covered(self, make_lot):
        directory = make_lot(
            n_shots=2,
            overrides={
                "alpha": lambda d: np.zeros(d["time"].size),
                "beta": lambda d: np.zeros(d["time"].size),
            },
        )
        ds = add_derived_columns(
            load_dataset(directory), reference=Reference(length_m=2.5), symmetry=C4V
        )
        specs, _ = build_specs(ds.columns, ds.column_values(), {})
        bands = build_bands(ds.values("Mach"), BandSpec(n_bands=2, min_points=10))
        envelope = build_envelope(
            ds, band_set=bands, specs=specs, spec=EnvelopeSpec(), symmetry=C4V
        )

        result = check_coverage(ds, envelope=envelope)

        assert result.failures_by_variable().get("phi_fold", 0) == 0

    def test_missing_values_are_counted_apart(self, make_lot):
        def spoil(data):
            out = data["PARA1"].copy()
            out[:5] = np.nan
            return out

        ds = add_derived_columns(
            load_dataset(make_lot(n_shots=2, overrides={"PARA1": spoil})),
            reference=Reference(length_m=2.5),
            symmetry=C4V,
        )
        specs, _ = build_specs(ds.columns, ds.column_values(), {})
        bands = build_bands(ds.values("Mach"), BandSpec(n_bands=2, min_points=10))
        envelope = build_envelope(
            ds, band_set=bands, specs=specs, spec=EnvelopeSpec(), symmetry=C4V
        )

        result = check_coverage(ds, envelope=envelope)

        assert result.n_skipped_nan >= 10
        assert result.failures_by_variable().get("PARA1", 0) == 0


class TestOutOfBands:
    def test_points_beyond_the_declared_bands_are_counted_and_reported(
        self, dataset_realiste, specs
    ):
        mach = dataset_realiste.values("Mach")
        middle = 0.5 * (float(mach.min()) + float(mach.max()))
        bands = build_bands(mach, BandSpec(edges=(float(mach.min()), middle)))
        envelope = build_envelope(
            dataset_realiste, band_set=bands, specs=specs, spec=EnvelopeSpec(), symmetry=C4V
        )

        result = check_coverage(dataset_realiste, envelope=envelope)

        assert result.n_out_of_bands > 0
        assert not result.is_complete
        assert any("hors des bandes" in n for n in result.notes)


class TestAggregation:
    def test_the_band_rates_reconstruct_the_overall_rate(self, dataset_realiste, envelope):
        result = check_coverage(dataset_realiste, envelope=envelope)

        inside = sum(b.n_inside for b in result.bands)
        points = sum(b.n_points for b in result.bands)
        assert inside == result.n_inside
        assert points == result.n_points

    def test_a_band_holding_no_point_is_reported_as_fully_covered(self, dataset_realiste, specs):
        mach = dataset_realiste.values("Mach")
        bands = build_bands(
            mach, BandSpec(edges=(float(mach.max()) + 1.0, float(mach.max()) + 2.0))
        )
        envelope = build_envelope(
            dataset_realiste, band_set=bands, specs=specs, spec=EnvelopeSpec(), symmetry=C4V
        )

        result = check_coverage(dataset_realiste, envelope=envelope)

        assert result.bands[0].rate == 1.0
        assert result.n_out_of_bands == dataset_realiste.n_rows

    def test_a_single_shot_lot_works(self, make_lot):
        ds = add_derived_columns(
            load_dataset(make_lot(n_shots=1)), reference=Reference(length_m=2.5), symmetry=C4V
        )
        specs, _ = build_specs(ds.columns, ds.column_values(), {})
        bands = build_bands(ds.values("Mach"), BandSpec(n_bands=2, min_points=10))
        envelope = build_envelope(
            ds,
            band_set=bands,
            specs=specs,
            spec=EnvelopeSpec(q_low=0.0, q_high=1.0, margin=0.0),
            symmetry=C4V,
        )

        assert check_coverage(ds, envelope=envelope).rate == pytest.approx(1.0)
