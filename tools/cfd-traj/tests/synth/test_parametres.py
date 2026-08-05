"""Generic parameter columns: archetypes, arbitrary names, arbitrary counts."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_traj.synth.parametres import (
    ARCHETYPES,
    ArchetypeError,
    ParameterModel,
    default_models,
    generate,
    parse_models,
)

N = 400
TIME = np.linspace(0.0, 90.0, N)
MACH = 0.3 + 3.0 * np.sin(np.pi * np.linspace(0, 1, N)) ** 0.7
ALTITUDE = np.linspace(150.0, 40_000.0, N)


def _make(archetype: str, name: str = "X", seed: int = 1) -> np.ndarray:
    return generate(
        ParameterModel(name=name, archetype=archetype),
        time_s=TIME,
        mach=MACH,
        altitude_m=ALTITUDE,
        rng=np.random.default_rng(seed),
    )


class TestArchetypes:
    @pytest.mark.parametrize("archetype", sorted(ARCHETYPES))
    def test_every_archetype_produces_a_clean_column(self, archetype):
        values = _make(archetype)

        assert values.shape == (N,)
        assert np.all(np.isfinite(values))

    def test_a_ramp_decreases(self):
        values = _make("rampe")

        assert values[-1] < values[0]
        assert np.polyfit(TIME, values, 1)[0] < 0.0

    def test_a_noisy_plateau_stays_around_its_nominal(self):
        model = ParameterModel(name="X", archetype="plateau_bruite", nominal=100.0, amplitude=0.1)
        values = generate(
            model, time_s=TIME, mach=MACH, altitude_m=ALTITUDE, rng=np.random.default_rng(2)
        )

        assert float(values.mean()) == pytest.approx(100.0, rel=0.05)
        assert float(values.std()) == pytest.approx(10.0, rel=0.25)

    def test_a_damped_sine_decays_and_crosses_zero(self):
        values = _make("sinus_amorti")

        early = np.abs(values[: N // 4]).max()
        late = np.abs(values[-N // 4 :]).max()
        assert late < early
        assert np.any(values > 0) and np.any(values < 0)

    def test_the_altitude_archetype_tracks_altitude(self):
        values = _make("correle_altitude")

        assert abs(np.corrcoef(values, ALTITUDE)[0, 1]) > 0.8

    def test_the_mach_archetype_tracks_mach(self):
        values = _make("correle_mach")

        assert abs(np.corrcoef(values, MACH)[0, 1]) > 0.8

    def test_the_discrete_archetype_takes_exactly_two_values(self):
        values = _make("discret")

        assert np.unique(values).size == 2

    def test_the_dispersion_scale_moves_the_whole_column(self):
        model = ParameterModel(name="X", archetype="plateau_bruite")
        base = generate(
            model, time_s=TIME, mach=MACH, altitude_m=ALTITUDE, rng=np.random.default_rng(3)
        )
        scaled = generate(
            model,
            time_s=TIME,
            mach=MACH,
            altitude_m=ALTITUDE,
            rng=np.random.default_rng(3),
            scale=2.0,
        )

        assert float(scaled.mean()) == pytest.approx(2.0 * float(base.mean()), rel=0.1)

    def test_the_same_seed_gives_the_same_column(self):
        assert np.array_equal(_make("plateau_bruite", seed=9), _make("plateau_bruite", seed=9))


class TestNaming:
    @pytest.mark.parametrize("name", ["X", "rapport_pression", "TEMP 42", "π_1", "PARA1", "1er"])
    def test_any_column_name_is_accepted_and_kept(self, name):
        model = ParameterModel(name=name, archetype="rampe")

        assert model.name == name
        assert _make("rampe", name=name).shape == (N,)

    def test_an_empty_name_is_refused(self):
        with pytest.raises(ValueError, match="name"):
            ParameterModel(name="", archetype="rampe")

    def test_an_unknown_archetype_lists_the_valid_ones(self):
        with pytest.raises(ArchetypeError) as excinfo:
            ParameterModel(name="X", archetype="inexistant")

        assert "rampe" in str(excinfo.value)
        assert "correle_mach" in str(excinfo.value)


class TestParsing:
    def test_a_two_column_specification_parses(self):
        models = parse_models("A:rampe,B:plateau_bruite")

        assert [m.name for m in models] == ["A", "B"]
        assert [m.archetype for m in models] == ["rampe", "plateau_bruite"]

    def test_the_archetype_may_be_omitted(self):
        assert parse_models("A")[0].archetype == "plateau_bruite"

    def test_spaces_around_the_separators_are_tolerated(self):
        models = parse_models(" A : rampe , B : discret ")

        assert [m.name for m in models] == ["A", "B"]

    def test_an_unknown_archetype_is_reported(self):
        with pytest.raises(ArchetypeError, match="inconnu"):
            parse_models("A:inconnu")

    def test_an_empty_specification_is_refused(self):
        with pytest.raises(ValueError, match="aucun paramètre"):
            parse_models("  ,  ")

    def test_a_nameless_entry_is_refused(self):
        with pytest.raises(ValueError, match="invalide"):
            parse_models(":rampe")


class TestDefaults:
    @pytest.mark.parametrize("n", [0, 1, 2, 12, 30])
    def test_any_count_of_default_columns_is_produced(self, n):
        models = default_models(n)

        assert len(models) == n
        assert [m.name for m in models] == [f"PARA{i + 1}" for i in range(n)]

    def test_the_archetypes_cycle_deterministically(self):
        first = default_models(12)
        second = default_models(12)

        assert [m.archetype for m in first] == [m.archetype for m in second]

    def test_the_prefix_can_be_changed(self):
        assert default_models(2, prefix="COL")[0].name == "COL1"

    def test_a_negative_count_is_refused(self):
        with pytest.raises(ValueError, match="non-negative"):
            default_models(-1)
