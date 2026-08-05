"""Loading a lot of trajectory CSVs."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_traj.data.columns import REQUIRED_COLUMNS, SHOT_COLUMN
from cfd_traj.data.dataset import DatasetError, load_dataset


class TestLoading:
    def test_a_directory_of_shots_loads(self, make_lot):
        directory = make_lot(n_shots=4)

        ds = load_dataset(directory)

        assert ds.n_shots == 4
        assert ds.n_rows == sum(s.n_rows for s in ds.shots)
        assert SHOT_COLUMN in ds.frame.columns

    def test_an_explicit_glob_loads(self, make_lot):
        directory = make_lot(n_shots=5)

        assert load_dataset(str(directory / "tir_000*.csv")).n_shots == 5

    def test_a_list_of_paths_loads(self, make_lot):
        directory = make_lot(n_shots=4)
        paths = sorted(directory.glob("*.csv"))[:2]

        assert load_dataset(paths).n_shots == 2

    def test_a_single_file_loads(self, make_lot):
        directory = make_lot(n_shots=3)

        ds = load_dataset(sorted(directory.glob("*.csv"))[0])

        assert ds.n_shots == 1

    def test_a_lot_of_exactly_one_shot_works(self, make_lot):
        ds = load_dataset(make_lot(n_shots=1))

        assert ds.n_shots == 1
        assert ds.n_rows > 0

    def test_max_shots_truncates_and_says_so(self, make_lot):
        ds = load_dataset(make_lot(n_shots=8), max_shots=3)

        assert ds.n_shots == 3
        assert any("retenus" in n for n in ds.notes)

    def test_shots_load_in_a_deterministic_order(self, make_lot):
        directory = make_lot(n_shots=5)

        first = load_dataset(directory)
        second = load_dataset(directory)

        assert [s.name for s in first.shots] == [s.name for s in second.shots]
        assert np.array_equal(first.values("Mach"), second.values("Mach"))

    def test_shots_of_different_lengths_are_accepted(self, make_lot):
        ds = load_dataset(make_lot(n_shots=4, vary_length=True))

        lengths = {s.n_rows for s in ds.shots}
        assert len(lengths) > 1
        assert ds.n_rows == sum(s.n_rows for s in ds.shots)


class TestGenericColumns:
    @pytest.mark.parametrize("n_extra", [0, 1, 2, 12])
    def test_any_number_of_generic_columns_survives_loading(self, make_lot, n_extra):
        extra = tuple(f"PARA{i + 1}" for i in range(n_extra))

        ds = load_dataset(make_lot(n_shots=2, extra=extra))

        assert ds.extra_columns == extra

    def test_exotic_column_names_are_preserved_verbatim(self, make_lot):
        extra = ("avec espace", "é_àccentué", "1er", "MiXeD_CaSe")

        ds = load_dataset(make_lot(n_shots=2, extra=extra))

        assert ds.extra_columns == extra

    def test_a_column_named_like_a_derived_one_is_refused(self, make_lot):
        directory = make_lot(n_shots=1, extra=("alpha_tot",))

        with pytest.raises(DatasetError, match="réservé"):
            load_dataset(directory)


class TestValidation:
    def test_an_empty_directory_is_refused(self, tmp_path):
        (tmp_path / "vide").mkdir()

        with pytest.raises(DatasetError, match="aucun fichier"):
            load_dataset(tmp_path / "vide")

    def test_a_missing_source_is_refused(self, tmp_path):
        with pytest.raises(DatasetError, match="introuvable"):
            load_dataset(tmp_path / "nulle-part")

    def test_a_missing_required_column_names_the_file_and_the_column(self, make_lot):
        directory = make_lot(n_shots=2)
        target = sorted(directory.glob("*.csv"))[0]
        lines = target.read_text().splitlines()
        header = lines[0].split(",")
        drop = header.index("beta")
        target.write_text(
            "\n".join(
                ",".join(v for i, v in enumerate(line.split(",")) if i != drop) for line in lines
            )
        )

        with pytest.raises(DatasetError) as excinfo:
            load_dataset(directory)

        assert "beta" in str(excinfo.value)
        assert target.name in str(excinfo.value)

    def test_files_disagreeing_about_columns_are_refused(self, make_lot, tmp_path):
        first = make_lot(n_shots=1, extra=("PARA1",), name="A")
        second = make_lot(n_shots=1, extra=("PARA1", "PARA2"), name="B")
        merged = tmp_path / "merged"
        merged.mkdir()
        for i, path in enumerate([*first.glob("*.csv"), *second.glob("*.csv")]):
            (merged / f"tir_{i:04d}.csv").write_text(path.read_text())

        with pytest.raises(DatasetError, match="incohérentes"):
            load_dataset(merged)

    def test_a_semicolon_separated_file_gets_an_explicit_message(self, tmp_path):
        directory = tmp_path / "semi"
        directory.mkdir()
        (directory / "tir.csv").write_text(
            "time;Mach;Altitude;alpha;beta;dl;dm;dn\n0;0,5;100;0;0;0;0;0\n"
        )

        with pytest.raises(DatasetError, match="virgule"):
            load_dataset(directory)

    def test_a_header_only_file_is_refused(self, tmp_path):
        directory = tmp_path / "entete"
        directory.mkdir()
        (directory / "tir.csv").write_text(",".join(REQUIRED_COLUMNS) + "\n")

        with pytest.raises(DatasetError, match="aucune ligne"):
            load_dataset(directory)

    def test_a_completely_empty_file_is_refused(self, tmp_path):
        directory = tmp_path / "vide2"
        directory.mkdir()
        (directory / "tir.csv").write_text("")

        with pytest.raises(DatasetError, match="vide"):
            load_dataset(directory)


class TestDataQuality:
    def test_nan_rows_are_counted_and_kept_by_default(self, make_lot):
        directory = make_lot(
            n_shots=2,
            overrides={"PARA1": lambda d: np.where(np.arange(d["time"].size) < 5, np.nan, 1.0)},
        )

        ds = load_dataset(directory)

        assert sum(s.n_nan_rows for s in ds.shots) == 10
        assert ds.n_dropped_rows == 0

    def test_nan_rows_can_be_dropped_on_request(self, make_lot):
        directory = make_lot(
            n_shots=2,
            overrides={"PARA1": lambda d: np.where(np.arange(d["time"].size) < 5, np.nan, 1.0)},
        )

        kept = load_dataset(directory)
        dropped = load_dataset(directory, drop_nan_rows=True)

        assert dropped.n_dropped_rows == 10
        assert dropped.n_rows == kept.n_rows - 10

    def test_an_all_nan_shot_is_reported_but_kept(self, make_lot):
        directory = make_lot(
            n_shots=2, overrides={"PARA1": lambda d: np.full(d["time"].size, np.nan)}
        )

        ds = load_dataset(directory)

        assert any("exploitable" in n for n in ds.notes)
        assert ds.n_shots == 2

    def test_non_monotone_time_is_a_note_not_an_error(self, make_lot):
        def bounce(data):
            t = data["time"].copy()
            t[10:20] = t[9]
            return t

        ds = load_dataset(make_lot(n_shots=2, overrides={"time": bounce}))

        assert any(not s.time_is_monotone for s in ds.shots)
        assert any("croissant" in n for n in ds.notes)

    def test_strictly_increasing_time_is_flagged_monotone(self, make_lot):
        ds = load_dataset(make_lot(n_shots=2))

        assert all(s.time_is_monotone for s in ds.shots)


class TestAccessors:
    def test_an_unknown_column_lists_the_available_ones(self, lot_simple):
        with pytest.raises(KeyError) as excinfo:
            lot_simple.values("nulle_part")

        assert "Mach" in str(excinfo.value)

    def test_the_matrix_respects_the_requested_order(self, lot_simple):
        matrix = lot_simple.matrix(["Mach", "time"])

        assert matrix.shape == (lot_simple.n_rows, 2)
        assert np.array_equal(matrix[:, 0], lot_simple.values("Mach"))

    def test_an_empty_matrix_has_the_right_height(self, lot_simple):
        assert lot_simple.matrix([]).shape == (lot_simple.n_rows, 0)

    def test_with_columns_leaves_the_original_untouched(self, lot_simple):
        added = lot_simple.with_columns({"extra": np.zeros(lot_simple.n_rows)})

        assert "extra" in added.columns
        assert "extra" not in lot_simple.columns
        assert added.derived_columns == ("extra",)

    def test_with_columns_does_not_duplicate_a_derived_name(self, lot_simple):
        once = lot_simple.with_columns({"extra": np.zeros(lot_simple.n_rows)})
        twice = once.with_columns({"extra": np.ones(lot_simple.n_rows)})

        assert twice.derived_columns == ("extra",)
        assert twice.values("extra").sum() == twice.n_rows

    def test_the_ranges_are_reported(self, lot_simple):
        lo, hi = lot_simple.mach_range
        t0, t1 = lot_simple.time_span

        assert lo < hi
        assert t0 < t1
