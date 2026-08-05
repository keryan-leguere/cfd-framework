"""Writing and reading back the plan, the envelope and the offender list."""

from __future__ import annotations

import numpy as np
import pytest
import yaml

from cfd_traj.core.adim import Reference
from cfd_traj.core.symmetry import SymmetryGroup, SymmetrySpec
from cfd_traj.data.columns import build_specs
from cfd_traj.data.dataset import load_dataset
from cfd_traj.data.derive import add_derived_columns
from cfd_traj.data.plan_io import (
    LEADING_COLUMNS,
    TRAILING_COLUMNS,
    plan_columns,
    read_plan_csv,
    write_envelope_csv,
    write_offenders_csv,
    write_plan_csv,
    write_plan_yaml,
)
from cfd_traj.data.study import BandSpec, DoeMethod, DoeSpec, EnvelopeSpec
from cfd_traj.engine.bands import build_bands
from cfd_traj.engine.doe import build_plan
from cfd_traj.engine.envelope import build_envelope

C4V = SymmetrySpec(group=SymmetryGroup.C4V)


def _plan(directory, extra=("PARA1", "PARA2")):
    """A small plan over a lot. Latin hypercube throughout: these tests are
    about serialisation, and a tensor grid over twelve generic columns would
    (rightly) be refused by the node ceiling."""
    ds = add_derived_columns(
        load_dataset(directory), reference=Reference(length_m=2.5), symmetry=C4V
    )
    specs, _ = build_specs(ds.columns, ds.column_values(), {})
    bands = build_bands(ds.values("Mach"), BandSpec(n_bands=2, min_points=10))
    envelope = build_envelope(ds, band_set=bands, specs=specs, spec=EnvelopeSpec(), symmetry=C4V)
    doe = DoeSpec(method=DoeMethod.LHS, n_lhs_per_band=4, max_nodes=500_000)
    return build_plan(envelope, doe=doe, symmetry=C4V, ds=ds), envelope


class TestPlanColumns:
    def test_the_order_frames_the_variables(self):
        columns = plan_columns(("Mach", "PARA1"))

        assert columns[: len(LEADING_COLUMNS)] == LEADING_COLUMNS
        assert columns[-len(TRAILING_COLUMNS) :] == TRAILING_COLUMNS
        assert columns[len(LEADING_COLUMNS) : len(LEADING_COLUMNS) + 2] == ("Mach", "PARA1")

    def test_no_variable_names_still_gives_a_valid_order(self):
        assert plan_columns(()) == (*LEADING_COLUMNS, *TRAILING_COLUMNS)


class TestPlanRoundTrip:
    def test_a_plan_survives_write_then_read(self, tmp_path, make_lot):
        plan, _ = _plan(make_lot(n_shots=3))
        original = plan.to_frame()

        reloaded = read_plan_csv(write_plan_csv(original, tmp_path / "PLAN.csv"))

        assert list(reloaded.columns) == list(original.columns)
        assert len(reloaded) == len(original)
        for column in original.columns:
            if original[column].dtype.kind == "f":
                assert np.allclose(
                    reloaded[column].to_numpy(dtype=float),
                    original[column].to_numpy(dtype=float),
                    equal_nan=True,
                )

    def test_every_expected_column_is_present(self, tmp_path, make_lot):
        plan, _ = _plan(make_lot(n_shots=3))

        frame = read_plan_csv(write_plan_csv(plan.to_frame(), tmp_path / "PLAN.csv"))

        for name in (
            "node_id",
            "bande",
            "braquage",
            "dl",
            "dm",
            "dn",
            "configuration",
            "cout_relatif",
            "composantes_nulles",
            "origine",
        ):
            assert name in frame.columns

    def test_numbers_use_a_machine_decimal_point(self, tmp_path, make_lot):
        plan, _ = _plan(make_lot(n_shots=2))

        target = write_plan_csv(plan.to_frame(), tmp_path / "PLAN.csv")

        body = target.read_text().splitlines()[1]
        assert ";" not in body

    def test_a_missing_output_directory_is_created(self, tmp_path, make_lot):
        plan, _ = _plan(make_lot(n_shots=2))

        target = write_plan_csv(plan.to_frame(), tmp_path / "a" / "b" / "PLAN.csv")

        assert target.exists()

    def test_reading_a_missing_plan_is_refused(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="introuvable"):
            read_plan_csv(tmp_path / "absent.csv")


class TestGenericity:
    @pytest.mark.parametrize("n_extra", [0, 1, 12])
    def test_the_column_count_follows_the_data_not_a_hardcoded_list(
        self, tmp_path, make_lot, n_extra
    ):
        extra = tuple(f"COL{i}" for i in range(n_extra))
        plan, _ = _plan(make_lot(n_shots=2, extra=extra), extra=extra)

        frame = read_plan_csv(write_plan_csv(plan.to_frame(), tmp_path / "PLAN.csv"))

        for name in extra:
            assert name in frame.columns

    def test_the_column_order_is_deterministic(self, tmp_path, make_lot):
        directory = make_lot(n_shots=2, extra=("Z", "A", "M"))
        first, _ = _plan(directory, extra=("Z", "A", "M"))
        second, _ = _plan(directory, extra=("Z", "A", "M"))

        assert first.column_names() == second.column_names()


class TestYamlExport:
    def test_the_payload_reloads_and_groups_by_band(self, tmp_path, make_lot):
        plan, envelope = _plan(make_lot(n_shots=3))

        target = write_plan_yaml(plan.to_yaml_payload(), tmp_path / "PLAN.yaml")

        payload = yaml.safe_load(target.read_text())
        assert payload["n_noeuds"] == plan.n_nodes
        assert len(payload["bandes"]) == len(envelope.bands)


class TestEnvelopeExport:
    def test_one_row_per_band_and_variable(self, tmp_path, make_lot):
        _, envelope = _plan(make_lot(n_shots=3))
        rows = envelope.table_rows()

        target = write_envelope_csv(rows, tmp_path / "ENVELOPPE.csv")

        import pandas as pd

        assert len(pd.read_csv(target)) == len(rows)


class TestOffenderExport:
    def test_an_empty_offender_list_still_writes_a_valid_file(self, tmp_path):
        import pandas as pd

        target = write_offenders_csv([], tmp_path / "HORS.csv")

        frame = pd.read_csv(target)
        assert frame.empty
        assert "tir" in frame.columns

    def test_offenders_are_written_with_their_french_headers(self, tmp_path):
        import pandas as pd

        rows = [
            {
                "tir": "tir_0001",
                "ligne": 3,
                "temps": 1.5,
                "mach": 0.9,
                "variable": "PARA1",
                "valeur": 12.0,
                "borne": 10.0,
                "cote": "haut",
                "exces": 0.2,
            }
        ]

        frame = pd.read_csv(write_offenders_csv(rows, tmp_path / "HORS.csv"))

        assert list(frame.columns) == list(rows[0])
        assert frame.iloc[0]["tir"] == "tir_0001"
