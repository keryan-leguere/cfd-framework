"""Symmetry groups: folding, parities, deflection classification, mesh assignment."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_traj.core.symmetry import (
    OUT_OF_PLANE_COMPONENTS,
    RELATIVE_COST,
    CalcConfig,
    DeflectionSymmetry,
    SymmetryGroup,
    SymmetrySpec,
    azimuth_levels,
    calc_config,
    classify_deflection,
    fold_phi,
    relative_cost,
    wind_plane_is_mirror,
    zero_components,
)

ALL_GROUPS = tuple(SymmetryGroup)


class TestFolding:
    @pytest.mark.parametrize("group", ALL_GROUPS)
    def test_folding_is_idempotent(self, group):
        spec = SymmetrySpec(group=group)
        rng = np.random.default_rng(1)
        phi = rng.uniform(-1000.0, 1000.0, 10_000)

        once = fold_phi(phi, spec)
        twice = fold_phi(once, spec)

        assert np.allclose(twice, once, atol=1e-12)

    @pytest.mark.parametrize("group", ALL_GROUPS)
    def test_folding_is_periodic(self, group):
        spec = SymmetrySpec(group=group)
        rng = np.random.default_rng(2)
        phi = rng.uniform(0.0, 360.0, 5_000)

        assert np.allclose(fold_phi(phi + spec.period_deg, spec), fold_phi(phi, spec), atol=1e-10)

    @pytest.mark.parametrize("group", ALL_GROUPS)
    def test_folded_values_land_in_the_fundamental_domain(self, group):
        spec = SymmetrySpec(group=group)
        rng = np.random.default_rng(3)

        folded = fold_phi(rng.uniform(-720.0, 720.0, 10_000), spec)

        low, high = spec.fundamental_domain_deg
        assert np.all(folded >= low - 1e-12)
        if spec.domain_is_closed:
            assert np.all(folded <= high + 1e-12)
        else:
            assert np.all(folded < high)

    @pytest.mark.parametrize(
        ("phi", "expected"),
        [
            (0, 0),
            (22.5, 22.5),
            (45, 45),
            (46, 44),
            (90, 0),
            (135, 45),
            (180, 0),
            (200, 20),
            (337.5, 22.5),
        ],
    )
    def test_tabulated_c4v_folding(self, phi, expected):
        spec = SymmetrySpec(group=SymmetryGroup.C4V)

        assert float(fold_phi(phi, spec)) == pytest.approx(expected, abs=1e-9)

    @pytest.mark.parametrize(("phi", "expected"), [(0, 0), (89, 89), (90, 0), (91, 1), (180, 0)])
    def test_tabulated_c4_folding(self, phi, expected):
        assert float(fold_phi(phi, SymmetrySpec(group=SymmetryGroup.C4))) == pytest.approx(
            expected, abs=1e-9
        )

    @pytest.mark.parametrize(
        ("phi", "expected"), [(0, 0), (90, 90), (180, 180), (181, 179), (270, 90), (359, 1)]
    )
    def test_tabulated_cs_folding(self, phi, expected):
        assert float(fold_phi(phi, SymmetrySpec(group=SymmetryGroup.CS))) == pytest.approx(
            expected, abs=1e-9
        )

    def test_c1_only_wraps(self):
        spec = SymmetrySpec(group=SymmetryGroup.C1)
        rng = np.random.default_rng(4)
        phi = rng.uniform(-1000, 1000, 1000)

        assert np.allclose(fold_phi(phi, spec), np.mod(phi, 360.0))

    def test_a_body_of_revolution_collapses_every_azimuth(self):
        spec = SymmetrySpec(group=SymmetryGroup.CINFV)

        assert np.all(fold_phi([0.0, 37.0, 180.0, 359.0], spec) == 0.0)

    def test_the_reference_plane_shifts_the_origin(self):
        spec = SymmetrySpec(group=SymmetryGroup.C4V, reference_plane_deg=45.0)

        assert float(fold_phi(45.0, spec)) == pytest.approx(0.0)
        assert float(fold_phi(0.0, spec)) == pytest.approx(45.0)


class TestMirrors:
    @pytest.mark.parametrize(
        ("group", "phi", "expected"),
        [
            (SymmetryGroup.CINFV, 0.0, True),
            (SymmetryGroup.CINFV, 37.0, True),
            (SymmetryGroup.C4V, 0.0, True),
            (SymmetryGroup.C4V, 22.5, False),
            (SymmetryGroup.C4V, 45.0, True),
            (SymmetryGroup.CS, 0.0, True),
            (SymmetryGroup.CS, 90.0, False),
            (SymmetryGroup.CS, 180.0, True),
            (SymmetryGroup.C4, 0.0, False),
            (SymmetryGroup.C4, 45.0, False),
            (SymmetryGroup.C1, 0.0, False),
            (SymmetryGroup.C1, 180.0, False),
        ],
    )
    def test_wind_plane_mirror_truth_table(self, group, phi, expected):
        got = wind_plane_is_mirror(np.asarray(phi), SymmetrySpec(group=group))

        assert bool(got) is expected


class TestDeflectionClassification:
    @pytest.mark.parametrize(
        ("dl", "dm", "dn", "expected"),
        [
            (0.0, 0.0, 0.0, DeflectionSymmetry.NULLE),
            (1e-12, 0.0, 0.0, DeflectionSymmetry.NULLE),
            (0.0, 15.0, 0.0, DeflectionSymmetry.SYMETRIQUE),
            (0.0, -15.0, 0.0, DeflectionSymmetry.SYMETRIQUE),
            (15.0, 0.0, 0.0, DeflectionSymmetry.ANTISYMETRIQUE),
            (0.0, 0.0, 15.0, DeflectionSymmetry.ANTISYMETRIQUE),
            (8.0, 12.0, 4.0, DeflectionSymmetry.QUELCONQUE),
            (0.0, 12.0, 4.0, DeflectionSymmetry.QUELCONQUE),
        ],
    )
    def test_classification(self, dl, dm, dn, expected):
        assert classify_deflection(dl, dm, dn) is expected


class TestZeroComponents:
    def test_out_of_plane_components_vanish_on_a_mirror_with_symmetric_deflections(self):
        spec = SymmetrySpec(group=SymmetryGroup.C4V)

        assert zero_components(0.0, spec, DeflectionSymmetry.NULLE) == OUT_OF_PLANE_COMPONENTS
        assert zero_components(45.0, spec, DeflectionSymmetry.SYMETRIQUE) == OUT_OF_PLANE_COMPONENTS

    def test_nothing_vanishes_away_from_a_mirror(self):
        spec = SymmetrySpec(group=SymmetryGroup.C4V)

        assert zero_components(22.5, spec, DeflectionSymmetry.NULLE) == ()

    def test_a_roll_deflection_destroys_the_theorem_even_on_a_mirror(self):
        spec = SymmetrySpec(group=SymmetryGroup.C4V)

        assert zero_components(0.0, spec, DeflectionSymmetry.ANTISYMETRIQUE) == ()


class TestCalcConfig:
    @pytest.mark.parametrize(
        ("group", "expected"),
        [
            (SymmetryGroup.CINFV, CalcConfig.AXI_2D),
            (SymmetryGroup.C4V, CalcConfig.SECTEUR_45),
            (SymmetryGroup.C4, CalcConfig.QUART_90),
            (SymmetryGroup.CS, CalcConfig.DEMI),
            (SymmetryGroup.C1, CalcConfig.COMPLETE),
        ],
    )
    def test_zero_incidence_with_neutral_deflections(self, group, expected):
        got = calc_config(
            alpha_tot_deg=0.0,
            phi_folded_deg=0.0,
            spec=SymmetrySpec(group=group),
            deflection=DeflectionSymmetry.NULLE,
        )

        assert got is expected

    @pytest.mark.parametrize("group", [SymmetryGroup.C4V, SymmetryGroup.CS, SymmetryGroup.CINFV])
    def test_a_mirror_plus_symmetric_deflections_allows_a_half_configuration(self, group):
        got = calc_config(
            alpha_tot_deg=5.0,
            phi_folded_deg=0.0,
            spec=SymmetrySpec(group=group),
            deflection=DeflectionSymmetry.SYMETRIQUE,
        )

        assert got is CalcConfig.DEMI

    def test_an_intermediate_azimuth_needs_the_full_configuration(self):
        got = calc_config(
            alpha_tot_deg=5.0,
            phi_folded_deg=22.5,
            spec=SymmetrySpec(group=SymmetryGroup.C4V),
            deflection=DeflectionSymmetry.NULLE,
        )

        assert got is CalcConfig.COMPLETE

    def test_a_roll_deflection_never_gets_a_half_configuration(self):
        # The trap this module exists for: on a half configuration the solver
        # would silently impose a symmetry the roll deflection has destroyed.
        got = calc_config(
            alpha_tot_deg=5.0,
            phi_folded_deg=0.0,
            spec=SymmetrySpec(group=SymmetryGroup.C4V),
            deflection=classify_deflection(15.0, 0.0, 0.0),
        )

        assert got is CalcConfig.COMPLETE

    def test_deflections_at_zero_incidence_still_break_the_sector(self):
        got = calc_config(
            alpha_tot_deg=0.0,
            phi_folded_deg=0.0,
            spec=SymmetrySpec(group=SymmetryGroup.C4V),
            deflection=classify_deflection(0.0, 10.0, 0.0),
        )

        assert got is CalcConfig.DEMI

    @pytest.mark.parametrize("group", ALL_GROUPS)
    def test_c1_style_deflections_always_cost_the_full_configuration(self, group):
        got = calc_config(
            alpha_tot_deg=5.0,
            phi_folded_deg=0.0,
            spec=SymmetrySpec(group=group),
            deflection=DeflectionSymmetry.QUELCONQUE,
        )

        assert got is CalcConfig.COMPLETE


class TestCosts:
    def test_costs_increase_strictly_with_domain_size(self):
        order = [
            CalcConfig.AXI_2D,
            CalcConfig.SECTEUR_45,
            CalcConfig.QUART_90,
            CalcConfig.DEMI,
            CalcConfig.COMPLETE,
        ]
        costs = [RELATIVE_COST[c] for c in order]

        assert costs == sorted(costs)
        assert len(set(costs)) == len(costs)
        assert relative_cost(CalcConfig.COMPLETE) == 1.0


class TestAzimuthLevels:
    @pytest.mark.parametrize(
        ("group", "n"),
        [
            (SymmetryGroup.CINFV, 1),
            (SymmetryGroup.C4V, 3),
            (SymmetryGroup.C4, 5),
            (SymmetryGroup.CS, 5),
            (SymmetryGroup.C1, 8),
        ],
    )
    def test_default_level_counts(self, group, n):
        assert len(azimuth_levels(SymmetrySpec(group=group))) == n

    @pytest.mark.parametrize("group", ALL_GROUPS)
    def test_levels_stay_in_the_fundamental_domain(self, group):
        spec = SymmetrySpec(group=group)
        low, high = spec.fundamental_domain_deg

        levels = azimuth_levels(spec)

        assert all(low - 1e-12 <= x for x in levels)
        assert all(x <= high + 1e-12 for x in levels)
        assert list(levels) == sorted(levels)

    def test_c4v_brackets_both_mirror_planes(self):
        assert azimuth_levels(SymmetrySpec(group=SymmetryGroup.C4V)) == (0.0, 22.5, 45.0)

    def test_c4_excludes_the_open_end_of_its_domain(self):
        levels = azimuth_levels(SymmetrySpec(group=SymmetryGroup.C4))

        assert 90.0 not in levels
        assert max(levels) < 90.0

    def test_the_level_count_can_be_overridden(self):
        spec = SymmetrySpec(group=SymmetryGroup.C4V, n_azimuths=5)

        assert len(azimuth_levels(spec)) == 5

    def test_a_body_of_revolution_ignores_the_override(self):
        spec = SymmetrySpec(group=SymmetryGroup.CINFV, n_azimuths=7)

        assert azimuth_levels(spec) == (0.0,)


class TestSpecValidation:
    def test_a_non_positive_azimuth_count_is_refused(self):
        with pytest.raises(ValueError, match="n_azimuths"):
            SymmetrySpec(group=SymmetryGroup.C4V, n_azimuths=0)

    def test_an_unknown_group_is_refused(self):
        with pytest.raises(ValueError, match="unknown symmetry group"):
            SymmetrySpec(group="C7v")  # type: ignore[arg-type]

    def test_a_non_finite_reference_plane_is_refused(self):
        with pytest.raises(ValueError, match="finite"):
            SymmetrySpec(group=SymmetryGroup.C4V, reference_plane_deg=float("nan"))
