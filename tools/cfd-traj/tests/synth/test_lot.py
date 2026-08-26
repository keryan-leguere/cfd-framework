"""The Monte-Carlo lot as written to disk."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_traj._compat import zip_strict
from cfd_traj.data.dataset import load_dataset
from cfd_traj.synth.lot import BASE_COLUMNS, LotSpec, generate_lot, summarise, write_lot
from cfd_traj.synth.parametres import ParameterModel, default_models


class TestFilesWritten:
    def test_the_requested_number_of_files_appears(self, tmp_path):
        written = write_lot(tmp_path / "lot", LotSpec(n_shots=5, seed=1))

        assert len(written) == 5
        assert len(list((tmp_path / "lot").glob("*.csv"))) == 5

    def test_the_header_is_the_mandatory_columns_then_the_extras(self, tmp_path):
        spec = LotSpec(n_shots=1, seed=1, parameters=default_models(3))

        written = write_lot(tmp_path / "lot", spec)

        header = written[0].read_text().splitlines()[0]
        assert header == ",".join([*BASE_COLUMNS, "PARA1", "PARA2", "PARA3"])

    def test_numbers_are_written_with_a_machine_decimal_point(self, tmp_path):
        written = write_lot(tmp_path / "lot", LotSpec(n_shots=1, seed=1))

        body = written[0].read_text().splitlines()[1]
        assert ";" not in body
        assert body.count(",") == len(BASE_COLUMNS) + 1

    def test_a_missing_output_directory_is_created(self, tmp_path):
        write_lot(tmp_path / "a" / "b" / "c", LotSpec(n_shots=1, seed=1))

        assert (tmp_path / "a" / "b" / "c").is_dir()


class TestDispersion:
    def test_the_shots_have_different_lengths(self, tmp_path):
        shots = generate_lot(LotSpec(n_shots=8, seed=3))

        assert len({s.n_rows for s in shots}) > 1

    def test_the_apogee_actually_disperses(self, tmp_path):
        stats = summarise(generate_lot(LotSpec(n_shots=10, seed=4)))

        assert stats["apogee_std_m"] / stats["apogee_mean_m"] > 0.01

    def test_no_two_shots_are_identical(self, tmp_path):
        shots = generate_lot(LotSpec(n_shots=6, seed=5))

        signatures = {float(s.trajectory.apogee_m) for s in shots}
        assert len(signatures) == 6


class TestReproducibility:
    def test_the_same_seed_gives_byte_identical_files(self, tmp_path):
        first = write_lot(tmp_path / "a", LotSpec(n_shots=3, seed=99))
        second = write_lot(tmp_path / "b", LotSpec(n_shots=3, seed=99))

        for left, right in zip_strict(first, second):
            assert left.read_bytes() == right.read_bytes()

    def test_different_seeds_give_different_files(self, tmp_path):
        first = write_lot(tmp_path / "a", LotSpec(n_shots=3, seed=1))
        second = write_lot(tmp_path / "b", LotSpec(n_shots=3, seed=2))

        assert first[0].read_bytes() != second[0].read_bytes()


class TestGenericity:
    @pytest.mark.parametrize("n_extra", [0, 1, 2, 12])
    def test_any_number_of_parameter_columns_round_trips(self, tmp_path, n_extra):
        spec = LotSpec(n_shots=2, seed=6, parameters=default_models(n_extra))

        write_lot(tmp_path / "lot", spec)

        ds = load_dataset(tmp_path / "lot")
        assert ds.extra_columns == tuple(f"PARA{i + 1}" for i in range(n_extra))

    def test_arbitrary_column_names_survive_the_round_trip(self, tmp_path):
        names = ("X", "rapport_pression", "TEMP 42", "é_accentué")
        spec = LotSpec(
            n_shots=2,
            seed=7,
            parameters=tuple(ParameterModel(name=n, archetype="rampe") for n in names),
        )

        write_lot(tmp_path / "lot", spec)

        assert load_dataset(tmp_path / "lot").extra_columns == names

    def test_a_lot_without_any_parameter_column_still_loads(self, tmp_path):
        write_lot(tmp_path / "lot", LotSpec(n_shots=2, seed=8, parameters=()))

        ds = load_dataset(tmp_path / "lot")
        assert ds.extra_columns == ()
        assert ds.source_columns == BASE_COLUMNS


class TestQuality:
    def test_the_lot_loads_without_any_consistency_note(self, tmp_path):
        write_lot(tmp_path / "lot", LotSpec(n_shots=4, seed=10))

        assert load_dataset(tmp_path / "lot").notes == ()

    def test_no_generated_value_is_missing(self, tmp_path):
        write_lot(tmp_path / "lot", LotSpec(n_shots=3, seed=11, parameters=default_models(4)))

        ds = load_dataset(tmp_path / "lot")
        for name in ds.source_columns:
            assert np.all(np.isfinite(ds.values(name)))

    def test_the_summary_reports_the_lot_size(self, tmp_path):
        stats = summarise(generate_lot(LotSpec(n_shots=4, seed=12)))

        assert stats["n_shots"] == 4.0
        assert stats["n_rows"] > 0.0
        assert stats["rows_min"] <= stats["rows_max"]


class TestSpecValidation:
    def test_a_non_positive_shot_count_is_refused(self):
        with pytest.raises(ValueError, match="n_shots"):
            LotSpec(n_shots=0)

    def test_duplicate_parameter_names_are_refused(self):
        with pytest.raises(ValueError, match="double"):
            LotSpec(
                parameters=(
                    ParameterModel(name="A", archetype="rampe"),
                    ParameterModel(name="A", archetype="discret"),
                )
            )

    def test_a_parameter_shadowing_a_mandatory_column_is_refused(self):
        with pytest.raises(ValueError, match="déjà utilisé"):
            LotSpec(parameters=(ParameterModel(name="Mach", archetype="rampe"),))
