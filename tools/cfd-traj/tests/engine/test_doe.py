"""Building the design of experiments."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_traj.core.symmetry import CalcConfig, SymmetryGroup, SymmetrySpec, calc_config
from cfd_traj.data.columns import build_specs
from cfd_traj.data.study import BandSpec, DeflectionSet, DoeMethod, DoeSpec, EnvelopeSpec
from cfd_traj.engine.bands import build_bands
from cfd_traj.engine.doe import NodeOrigin, PlanTooLarge, build_plan
from cfd_traj.engine.envelope import build_envelope

C4V = SymmetrySpec(group=SymmetryGroup.C4V)
BIG = 500_000
NEUTRAL = (DeflectionSet("neutre"),)


def _spec(**kw) -> DoeSpec:
    kw.setdefault("max_nodes", BIG)
    kw.setdefault("deflections", NEUTRAL)
    return DoeSpec(**kw)


class TestInvariants:
    def test_every_corner_lies_inside_its_band(self, envelope):
        plan = build_plan(envelope, doe=_spec(), symmetry=C4V)

        corners = [n for n in plan.nodes if n.is_corner]
        assert corners
        for node in corners:
            band = envelope.bands[node.band_index]
            assert band.contains({k: v for k, v in node.values.items() if np.isfinite(v)})

    def test_every_node_lies_inside_its_band(self, envelope):
        plan = build_plan(envelope, doe=_spec(), symmetry=C4V)

        for node in plan.nodes:
            band = envelope.bands[node.band_index]
            assert band.contains({k: v for k, v in node.values.items() if np.isfinite(v)})

    def test_every_node_carries_the_mach_of_its_own_band(self, envelope):
        plan = build_plan(envelope, doe=_spec(), symmetry=C4V)

        for node in plan.nodes:
            band = envelope.bands[node.band_index].band
            assert band.mach_low - 1e-9 <= node.values["Mach"] <= band.mach_high + 1e-9

    def test_node_identifiers_are_unique(self, envelope):
        plan = build_plan(envelope, doe=_spec(), symmetry=C4V)

        assert len({n.node_id for n in plan.nodes}) == plan.n_nodes

    def test_no_two_nodes_share_a_point_and_a_deflection(self, envelope):
        plan = build_plan(
            envelope,
            doe=_spec(deflections=(DeflectionSet("neutre"), DeflectionSet("tangage", dm=10.0))),
            symmetry=C4V,
        )

        keys = {
            (
                tuple(round(v, 9) for v in n.values.values()),
                n.deflection.name,
            )
            for n in plan.nodes
        }
        assert len(keys) == plan.n_nodes


class TestSymmetryAssignment:
    def test_the_configuration_matches_the_core_decision(self, envelope):
        plan = build_plan(
            envelope,
            doe=_spec(deflections=(DeflectionSet("neutre"), DeflectionSet("roulis", dl=15.0))),
            symmetry=C4V,
        )

        for node in plan.nodes:
            expected = calc_config(
                alpha_tot_deg=node.values["alpha_tot"],
                phi_folded_deg=node.values["phi_fold"],
                spec=C4V,
                deflection=node.deflection.symmetry,
            )
            assert node.calc_config is expected

    def test_the_cost_is_never_worse_than_the_naive_one(self, envelope):
        plan = build_plan(envelope, doe=_spec(), symmetry=C4V)

        assert plan.total_cost <= plan.naive_cost
        assert 0.0 <= plan.saving < 1.0

    def test_the_cost_breakdown_adds_back_up(self, envelope):
        plan = build_plan(envelope, doe=_spec(), symmetry=C4V)

        breakdown = plan.cost_by_config()
        assert sum(c for c, _ in breakdown.values()) == plan.n_nodes
        assert sum(cost for _, cost in breakdown.values()) == pytest.approx(plan.total_cost)

    def test_a_cruciform_with_neutral_deflections_mostly_avoids_the_full_configuration(
        self, envelope
    ):
        plan = build_plan(envelope, doe=_spec(), symmetry=C4V)

        reduced = sum(1 for n in plan.nodes if n.calc_config is not CalcConfig.COMPLETE)
        assert reduced > plan.n_nodes / 2

    def test_an_asymmetric_configuration_pays_full_price_everywhere(self, envelope):
        plan = build_plan(envelope, doe=_spec(), symmetry=SymmetrySpec(group=SymmetryGroup.C1))

        under_incidence = [n for n in plan.nodes if n.values["alpha_tot"] > 1e-6]
        assert under_incidence
        assert all(n.calc_config is CalcConfig.COMPLETE for n in under_incidence)

    def test_a_body_of_revolution_gets_axisymmetric_cases_at_zero_incidence(self, envelope):
        plan = build_plan(envelope, doe=_spec(), symmetry=SymmetrySpec(group=SymmetryGroup.CINFV))

        assert any(n.calc_config is CalcConfig.AXI_2D for n in plan.nodes)

    def test_a_roll_deflection_forces_the_full_configuration(self, envelope):
        plan = build_plan(
            envelope, doe=_spec(deflections=(DeflectionSet("roulis", dl=15.0),)), symmetry=C4V
        )

        assert all(n.calc_config is CalcConfig.COMPLETE for n in plan.nodes)

    def test_a_pitch_deflection_keeps_the_half_configuration_on_a_mirror(self, envelope):
        plan = build_plan(
            envelope, doe=_spec(deflections=(DeflectionSet("tangage", dm=15.0),)), symmetry=C4V
        )

        on_mirror = [n for n in plan.nodes if n.values["phi_fold"] in (0.0, 45.0)]
        assert on_mirror
        assert all(n.calc_config is CalcConfig.DEMI for n in on_mirror)

    def test_zero_components_are_recorded_where_the_theorem_applies(self, envelope):
        plan = build_plan(envelope, doe=_spec(), symmetry=C4V)

        on_mirror = [n for n in plan.nodes if n.values["phi_fold"] == 0.0]
        assert all(n.zero_components == ("CY", "Cn", "Cl") for n in on_mirror)
        off_mirror = [n for n in plan.nodes if n.values["phi_fold"] == 22.5]
        assert all(n.zero_components == () for n in off_mirror)


class TestMethods:
    def test_the_tensor_count_follows_the_level_product(self, envelope):
        plan = build_plan(envelope, doe=_spec(include_corners=False), symmetry=C4V)

        n_phi = 3
        expected = sum(
            int(np.prod([len(v.levels) for v in band.grid_variables()] or [1])) * n_phi
            for band in envelope.bands
        )
        assert plan.n_nodes == expected

    def test_the_latin_hypercube_is_far_smaller(self, envelope, dataset_realiste):
        tensor = build_plan(envelope, doe=_spec(), symmetry=C4V)
        latin = build_plan(
            envelope,
            doe=_spec(method=DoeMethod.LHS, n_lhs_per_band=8),
            symmetry=C4V,
            ds=dataset_realiste,
        )

        assert latin.n_nodes < tensor.n_nodes
        assert latin.method is DoeMethod.LHS

    def test_the_latin_hypercube_still_brackets_the_domain(self, envelope, dataset_realiste):
        plan = build_plan(
            envelope,
            doe=_spec(method=DoeMethod.LHS, n_lhs_per_band=8),
            symmetry=C4V,
            ds=dataset_realiste,
        )

        assert any(n.is_corner for n in plan.nodes)

    def test_corners_can_be_switched_off(self, envelope):
        plan = build_plan(envelope, doe=_spec(include_corners=False), symmetry=C4V)

        assert all(n.origin is not NodeOrigin.COIN for n in plan.nodes)


class TestReproducibility:
    @pytest.mark.parametrize("method", list(DoeMethod))
    def test_the_same_seed_gives_the_same_plan(self, envelope, dataset_realiste, method):
        kw = {"method": method, "n_lhs_per_band": 6, "seed": 7}
        first = build_plan(envelope, doe=_spec(**kw), symmetry=C4V, ds=dataset_realiste)
        second = build_plan(envelope, doe=_spec(**kw), symmetry=C4V, ds=dataset_realiste)

        assert [n.as_row() for n in first.nodes] == [n.as_row() for n in second.nodes]

    def test_a_different_seed_moves_the_latin_hypercube(self, envelope, dataset_realiste):
        kw = {"method": DoeMethod.LHS, "n_lhs_per_band": 6}
        first = build_plan(envelope, doe=_spec(seed=1, **kw), symmetry=C4V, ds=dataset_realiste)
        second = build_plan(envelope, doe=_spec(seed=2, **kw), symmetry=C4V, ds=dataset_realiste)

        assert [n.as_row() for n in first.nodes] != [n.as_row() for n in second.nodes]

    def test_the_seed_does_not_move_the_tensor_grid(self, envelope):
        first = build_plan(envelope, doe=_spec(seed=1), symmetry=C4V)
        second = build_plan(envelope, doe=_spec(seed=999), symmetry=C4V)

        assert [n.as_row() for n in first.nodes] == [n.as_row() for n in second.nodes]


class TestCeiling:
    def test_an_oversized_plan_is_refused_before_it_is_built(self, envelope):
        with pytest.raises(PlanTooLarge) as excinfo:
            build_plan(envelope, doe=_spec(max_nodes=5), symmetry=C4V)

        assert excinfo.value.ceiling == 5
        assert excinfo.value.requested > 5
        assert "noeuds_max" in str(excinfo.value)

    def test_the_latin_hypercube_fits_where_the_grid_does_not(self, envelope, dataset_realiste):
        ceiling = 900
        with pytest.raises(PlanTooLarge):
            build_plan(envelope, doe=_spec(max_nodes=ceiling), symmetry=C4V)

        plan = build_plan(
            envelope,
            doe=_spec(method=DoeMethod.LHS, n_lhs_per_band=6, max_nodes=ceiling),
            symmetry=C4V,
            ds=dataset_realiste,
        )
        assert plan.n_nodes <= ceiling


class TestDiscreteFactors:
    def test_a_share_of_the_nodes_carries_the_second_level(self, envelope):
        plan = build_plan(envelope, doe=_spec(discrete_fraction=0.25), symmetry=C4V)

        variable = envelope.bands[0].get("Re_ref")
        assert variable is not None
        values = np.array([n.values["Re_ref"] for n in plan.nodes_of_band(0)])
        share = float(np.mean(values > np.min(values)))
        assert 0.20 <= share <= 0.30

    def test_a_zero_fraction_keeps_every_node_on_the_first_level(self, envelope):
        plan = build_plan(envelope, doe=_spec(discrete_fraction=0.0), symmetry=C4V)

        values = {n.values["Re_ref"] for n in plan.nodes_of_band(0)}
        assert len(values) == 1


class TestExport:
    def test_the_frame_has_one_row_per_node_in_a_stable_column_order(self, envelope):
        plan = build_plan(envelope, doe=_spec(), symmetry=C4V)

        frame = plan.to_frame()
        assert len(frame) == plan.n_nodes
        assert tuple(frame.columns) == plan.column_names()
        assert frame.columns[0] == "node_id"

    def test_the_variable_columns_are_the_envelope_variables(self, envelope):
        plan = build_plan(envelope, doe=_spec(), symmetry=C4V)

        for name in ("Mach", "alpha_tot", "phi_fold", "PARA1", "PARA2"):
            assert name in plan.variable_names

    def test_the_yaml_payload_groups_nodes_by_band(self, envelope):
        plan = build_plan(envelope, doe=_spec(), symmetry=C4V)

        payload = plan.to_yaml_payload()
        assert len(payload["bandes"]) == len(envelope.bands)
        assert sum(len(b["noeuds"]) for b in payload["bandes"]) == plan.n_nodes


class TestGenericity:
    @pytest.mark.parametrize("n_extra", [0, 1, 3])
    def test_any_number_of_generic_columns_produces_a_valid_plan(self, make_lot, n_extra):
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
        bands = build_bands(ds.values("Mach"), BandSpec(n_bands=2, min_points=10))
        envelope = build_envelope(
            ds, band_set=bands, specs=specs, spec=EnvelopeSpec(), symmetry=C4V
        )

        plan = build_plan(envelope, doe=_spec(), symmetry=C4V)

        assert plan.n_nodes > 0
        for name in extra:
            assert name in plan.variable_names

    def test_a_single_band_envelope_produces_a_plan(self, dataset_realiste, specs):
        mach = dataset_realiste.values("Mach")
        bands = build_bands(mach, BandSpec(edges=(float(mach.min()), float(mach.max()))))
        envelope = build_envelope(
            dataset_realiste, band_set=bands, specs=specs, spec=EnvelopeSpec(), symmetry=C4V
        )

        plan = build_plan(envelope, doe=_spec(), symmetry=C4V)

        assert plan.n_nodes > 0
        assert {n.band_index for n in plan.nodes} == {0}
