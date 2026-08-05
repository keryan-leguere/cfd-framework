"""Column roles, and the genericity of the extra parameter columns."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_traj.data.columns import (
    DEFAULT_LEVELS,
    ColumnError,
    ColumnSpec,
    Role,
    Scale,
    build_specs,
    default_mechanical_range,
    detect_role,
)

MACH = np.linspace(0.3, 3.0, 400)


def _values(**extra: np.ndarray) -> dict[str, np.ndarray]:
    """A minimal column-values mapping with the mandatory columns present."""
    base = {
        "time": np.linspace(0.0, 100.0, 400),
        "Mach": MACH,
        "Altitude": np.linspace(0.0, 20_000.0, 400),
        "alpha": np.zeros(400),
        "beta": np.zeros(400),
        "dl": np.linspace(-4.0, 4.0, 400),
        "dm": np.linspace(-9.0, 9.0, 400),
        "dn": np.linspace(-2.0, 2.0, 400),
    }
    base.update(extra)
    return base


class TestSpecValidation:
    def test_the_yaml_facing_values_are_the_french_ones(self):
        assert [r.value for r in Role] == [
            "principal",
            "conditionnel",
            "discret",
            "mecanique",
            "ignore",
        ]
        assert [s.value for s in Scale] == ["lineaire", "log"]

    def test_a_non_positive_level_count_is_refused(self):
        with pytest.raises(ValueError, match="niveaux"):
            ColumnSpec(name="x", role=Role.PRINCIPAL, levels=0)

    def test_a_mechanical_role_without_a_range_is_refused(self):
        with pytest.raises(ValueError, match="plage"):
            ColumnSpec(name="dl", role=Role.MECANIQUE)

    @pytest.mark.parametrize("bad", [(5.0, 1.0), (2.0, 2.0), (float("nan"), 1.0)])
    def test_an_invalid_mechanical_range_is_refused(self, bad):
        with pytest.raises(ValueError, match="plage"):
            ColumnSpec(name="dl", role=Role.MECANIQUE, mechanical_range=bad)

    def test_inverted_quantiles_are_refused(self):
        with pytest.raises(ValueError, match="quantiles"):
            ColumnSpec(name="x", role=Role.PRINCIPAL, q_low=0.9, q_high=0.1)

    def test_a_negative_margin_is_refused(self):
        with pytest.raises(ValueError, match="marge"):
            ColumnSpec(name="x", role=Role.PRINCIPAL, margin=-0.1)

    def test_an_unknown_role_is_refused_and_lists_the_valid_ones(self):
        with pytest.raises(ValueError, match="principal"):
            ColumnSpec(name="x", role="dimension")  # type: ignore[arg-type]

    def test_an_unknown_scale_is_refused(self):
        with pytest.raises(ValueError, match="échelle"):
            ColumnSpec(name="x", role=Role.PRINCIPAL, scale="logarithmique")  # type: ignore[arg-type]

    @pytest.mark.parametrize("role", list(Role))
    def test_the_level_count_falls_back_to_the_role_default(self, role):
        kw = {"mechanical_range": (-1.0, 1.0)} if role is Role.MECANIQUE else {}
        spec = ColumnSpec(name="x", role=role, **kw)

        assert spec.n_levels == DEFAULT_LEVELS[role]

    def test_the_display_label_gathers_name_unit_and_text(self):
        spec = ColumnSpec(name="PARA1", role=Role.PRINCIPAL, unit="bar", label="pression")

        assert spec.display == "PARA1 [bar] pression"


class TestAutoDetection:
    def test_two_distinct_values_make_a_discrete_factor(self):
        values = np.where(np.arange(400) < 200, 0.0, 1.0)

        got = detect_role("whatever", values, MACH)

        assert got.role is Role.DISCRET
        assert got.n_unique == 2

    def test_a_single_value_is_still_a_discrete_factor(self):
        got = detect_role("whatever", np.full(400, 3.0), MACH)

        assert got.role is Role.DISCRET
        assert got.n_unique == 1

    def test_a_column_tracking_mach_is_conditioned_on_mach(self):
        got = detect_role("whatever", 42.0 * MACH + 3.0, MACH)

        assert got.role is Role.CONDITIONNEL
        assert got.rho_mach == pytest.approx(1.0, abs=1e-9)

    def test_a_column_independent_of_mach_is_a_dimension_of_its_own(self):
        rng = np.random.default_rng(1)

        got = detect_role("whatever", rng.normal(0, 1, 400), MACH)

        assert got.role is Role.PRINCIPAL
        assert abs(got.rho_mach) < 0.7

    def test_a_positive_column_spanning_decades_gets_a_log_scale(self):
        rng = np.random.default_rng(2)

        got = detect_role("whatever", 10.0 ** rng.uniform(0, 4, 400), MACH)

        assert got.scale is Scale.LOG

    def test_a_narrow_positive_column_stays_linear(self):
        rng = np.random.default_rng(3)

        assert detect_role("whatever", rng.uniform(1.0, 3.0, 400), MACH).scale is Scale.LINEAIRE

    def test_a_wide_column_crossing_zero_stays_linear(self):
        rng = np.random.default_rng(4)

        got = detect_role("whatever", rng.uniform(-1e4, 1e4, 400), MACH)

        assert got.scale is Scale.LINEAIRE

    @pytest.mark.parametrize("name", ["time", "Altitude", "alpha", "beta"])
    def test_the_columns_absorbed_by_the_derived_quantities_are_ignored(self, name):
        assert detect_role(name, MACH, MACH).role is Role.IGNORE

    def test_mach_keeps_its_forced_role(self):
        assert detect_role("Mach", MACH, MACH).role is Role.PRINCIPAL

    @pytest.mark.parametrize("name", ["dl", "dm", "dn"])
    def test_deflections_are_mechanical(self, name):
        assert detect_role(name, np.linspace(-5, 5, 400), MACH).role is Role.MECANIQUE

    @pytest.mark.parametrize(
        "name", ["PARA1", "X", "rapport", "TEMP_42", "é_àccentué", "avec espace", "1er"]
    )
    def test_the_same_values_get_the_same_role_whatever_the_column_is_called(self, name):
        # The critical anti-hardcoding property: nothing may key off a name.
        values = 42.0 * MACH + 3.0

        got = detect_role(name, values, MACH)

        assert got.role is Role.CONDITIONNEL
        assert got.scale is Scale.LINEAIRE


class TestMechanicalRange:
    def test_the_fallback_range_brackets_the_observed_excursion(self):
        low, high = default_mechanical_range(np.array([-8.0, 3.0, 7.5]))

        assert low <= -8.0
        assert high >= 7.5
        assert low == -high

    def test_an_empty_column_still_gets_a_usable_range(self):
        low, high = default_mechanical_range(np.array([]))

        assert low < high


class TestBuildSpecs:
    def test_every_column_gets_a_spec_in_file_order(self):
        values = _values(PARA1=42.0 * MACH, PARA2=np.ones(400))

        specs, _ = build_specs(list(values), values, {})

        assert [s.name for s in specs] == list(values)

    def test_auto_detected_specs_are_flagged_and_explained(self):
        values = _values(PARA1=42.0 * MACH)

        specs, notes = build_specs(list(values), values, {})

        para = next(s for s in specs if s.name == "PARA1")
        assert para.auto
        assert para.detection
        assert any("PARA1" in n for n in notes)

    def test_a_declaration_beats_auto_detection(self):
        values = _values(PARA1=42.0 * MACH)
        declared = {"PARA1": ColumnSpec(name="PARA1", role=Role.IGNORE)}

        specs, _ = build_specs(list(values), values, declared)

        para = next(s for s in specs if s.name == "PARA1")
        assert para.role is Role.IGNORE
        assert not para.auto

    def test_a_declared_mechanical_column_without_a_range_gets_the_fallback(self):
        values = _values()
        declared = {"dl": ColumnSpec(name="dl", role=Role.MECANIQUE, mechanical_range=(-1.0, 1.0))}

        specs, _ = build_specs(list(values), values, declared)

        assert next(s for s in specs if s.name == "dl").mechanical_range == (-1.0, 1.0)

    def test_declaring_a_column_that_is_not_there_names_the_ones_that_are(self):
        values = _values(PARA1=np.ones(400))
        declared = {"PARA9": ColumnSpec(name="PARA9", role=Role.PRINCIPAL)}

        with pytest.raises(ColumnError) as excinfo:
            build_specs(list(values), values, declared)

        assert "PARA9" in str(excinfo.value)
        assert "PARA1" in str(excinfo.value)

    @pytest.mark.parametrize("n_extra", [0, 1, 3, 12])
    def test_any_number_of_generic_columns_is_handled(self, n_extra):
        rng = np.random.default_rng(5)
        extra = {f"COL_{i}": rng.normal(0, 1, 400) for i in range(n_extra)}
        values = _values(**extra)

        specs, _ = build_specs(list(values), values, {})

        assert len({s.name for s in specs} & set(extra)) == n_extra
