"""The study file: schema, validation, round-trip."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cfd_traj.core.symmetry import DeflectionSymmetry, SymmetryGroup
from cfd_traj.data.columns import Role, Scale
from cfd_traj.data.study import (
    DeflectionSet,
    DoeMethod,
    StudyError,
    default_study,
    load_study,
    parse_study,
    study_to_dict,
    write_study,
)

MINIMAL = {
    "etude": {"nom": "LOT", "source": "TRAJECTOIRES"},
    "reference": {"longueur_m": 2.5},
}


def _write(tmp_path: Path, data: dict, name: str = "ETUDE.yaml") -> Path:
    target = tmp_path / name
    target.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return target


class TestMinimalStudy:
    def test_a_minimal_study_applies_every_default(self):
        study = parse_study(MINIMAL)

        assert study.name == "LOT"
        assert study.output_dir == "SORTIE"
        assert study.symmetry.group is SymmetryGroup.C4V
        assert study.bands.edges is None
        assert study.bands.min_points == 30
        assert study.envelope.q_low == 0.001
        assert study.doe.method is DoeMethod.TENSORIEL
        assert study.doe.include_corners is True
        assert study.delta_t_k == 0.0
        assert study.declared_columns == {}

    def test_the_default_study_needs_no_file(self):
        study = default_study("TRAJ", name="essai")

        assert study.name == "essai"
        assert study.reference.length_m > 0

    def test_a_full_study_parses(self):
        study = parse_study(
            {
                **MINIMAL,
                "atmosphere": {"delta_t_K": 12.0},
                "symetrie": {"groupe": "C4", "plan_reference_deg": 22.5, "n_azimuts": 6},
                "bandes": {"bornes": [0.5, 0.9, 1.4], "points_min": 10},
                "enveloppe": {"quantile_bas": 0.01, "quantile_haut": 0.99, "marge": 0.1},
                "parametres": {
                    "PARA1": {
                        "role": "conditionnel",
                        "niveaux": 4,
                        "echelle": "log",
                        "unite": "-",
                        "libelle": "rapport",
                        "min_physique": 0.0,
                        "quantile_bas": 0.005,
                        "quantile_haut": 0.995,
                        "marge": 0.2,
                    },
                    "dl": {"role": "mecanique", "plage": [-20.0, 20.0], "niveaux": 3},
                },
                "doe": {
                    "methode": "lhs",
                    "coins": False,
                    "n_lhs_par_bande": 12,
                    "graine": 7,
                    "noeuds_max": 500,
                    "fraction_discret": 0.5,
                    "braquages": [
                        {"nom": "neutre"},
                        {"nom": "roulis", "dl": 15.0},
                    ],
                },
            }
        )

        assert study.delta_t_k == 12.0
        assert study.symmetry.group is SymmetryGroup.C4
        assert study.symmetry.n_azimuths == 6
        assert study.bands.edges == (0.5, 0.9, 1.4)
        assert study.envelope.margin == 0.1
        assert study.doe.method is DoeMethod.LHS
        assert not study.doe.include_corners
        assert len(study.doe.deflections) == 2

        para = study.declared_columns["PARA1"]
        assert para.role is Role.CONDITIONNEL
        assert para.scale is Scale.LOG
        assert para.levels == 4
        assert para.margin == 0.2


class TestValidation:
    def test_an_unknown_top_level_section_lists_the_valid_ones(self):
        with pytest.raises(StudyError) as excinfo:
            parse_study({**MINIMAL, "inconnue": {}})

        assert "inconnue" in str(excinfo.value)
        assert "enveloppe" in str(excinfo.value)

    def test_an_unknown_key_inside_a_section_is_refused(self):
        with pytest.raises(StudyError, match="symetrie"):
            parse_study({**MINIMAL, "symetrie": {"groupe": "C4v", "typo": 1}})

    @pytest.mark.parametrize("key", ["nom", "source"])
    def test_a_missing_required_study_key_is_named(self, key):
        etude = {k: v for k, v in MINIMAL["etude"].items() if k != key}

        with pytest.raises(StudyError, match=key):
            parse_study({"etude": etude, "reference": {"longueur_m": 1.0}})

    def test_a_missing_reference_length_is_named(self):
        with pytest.raises(StudyError, match="longueur_m"):
            parse_study({"etude": MINIMAL["etude"], "reference": {}})

    def test_an_unknown_symmetry_group_lists_the_five(self):
        with pytest.raises(StudyError) as excinfo:
            parse_study({**MINIMAL, "symetrie": {"groupe": "D4h"}})

        message = str(excinfo.value)
        assert all(g.value in message for g in SymmetryGroup)

    def test_an_unknown_role_lists_the_five(self):
        with pytest.raises(StudyError) as excinfo:
            parse_study({**MINIMAL, "parametres": {"PARA1": {"role": "dimension"}}})

        message = str(excinfo.value)
        assert all(r.value in message for r in Role)

    def test_an_unknown_method_lists_both(self):
        with pytest.raises(StudyError) as excinfo:
            parse_study({**MINIMAL, "doe": {"methode": "krigeage"}})

        assert "tensoriel" in str(excinfo.value)
        assert "lhs" in str(excinfo.value)

    @pytest.mark.parametrize("edges", [[1.0, 0.5], [1.0], [0.5, 0.5]])
    def test_bad_band_edges_are_refused(self, edges):
        with pytest.raises(StudyError, match="bornes"):
            parse_study({**MINIMAL, "bandes": {"bornes": edges}})

    def test_inverted_quantiles_are_refused(self):
        with pytest.raises(StudyError, match="quantile"):
            parse_study({**MINIMAL, "enveloppe": {"quantile_bas": 0.9, "quantile_haut": 0.1}})

    def test_a_negative_margin_is_refused(self):
        with pytest.raises(StudyError, match="marge"):
            parse_study({**MINIMAL, "enveloppe": {"marge": -0.1}})

    def test_a_mechanical_column_without_a_range_names_the_column(self):
        with pytest.raises(StudyError, match="dl"):
            parse_study({**MINIMAL, "parametres": {"dl": {"role": "mecanique"}}})

    def test_an_inverted_mechanical_range_is_refused(self):
        with pytest.raises(StudyError, match="plage"):
            parse_study(
                {**MINIMAL, "parametres": {"dl": {"role": "mecanique", "plage": [5.0, -5.0]}}}
            )

    def test_a_column_entry_without_a_role_is_refused(self):
        with pytest.raises(StudyError, match="role"):
            parse_study({**MINIMAL, "parametres": {"PARA1": {"niveaux": 3}}})

    def test_a_deflection_without_a_name_is_refused(self):
        with pytest.raises(StudyError, match="nom"):
            parse_study({**MINIMAL, "doe": {"braquages": [{"dl": 1.0}]}})

    def test_duplicate_deflection_names_are_refused(self):
        with pytest.raises(StudyError, match="double"):
            parse_study({**MINIMAL, "doe": {"braquages": [{"nom": "a"}, {"nom": "a", "dm": 5.0}]}})

    def test_a_non_numeric_value_is_refused(self):
        with pytest.raises(StudyError, match="nombre"):
            parse_study({"etude": MINIMAL["etude"], "reference": {"longueur_m": "long"}})

    @pytest.mark.parametrize(
        ("section", "payload"),
        [
            ("doe", {"n_lhs_par_bande": 0}),
            ("doe", {"noeuds_max": 0}),
            ("doe", {"fraction_discret": 1.5}),
            ("bandes", {"n_bandes": 0}),
            ("bandes", {"points_min": 0}),
            ("bandes", {"raffinement_transsonique": 0}),
            ("bandes", {"transsonique": [1.2, 0.8]}),
        ],
    )
    def test_out_of_range_settings_are_refused(self, section, payload):
        with pytest.raises(StudyError):
            parse_study({**MINIMAL, section: payload})

    def test_a_section_that_is_not_a_mapping_is_refused(self):
        with pytest.raises(StudyError, match="section"):
            parse_study({**MINIMAL, "doe": [1, 2, 3]})


class TestFileHandling:
    def test_a_missing_file_carries_its_path(self, tmp_path):
        with pytest.raises(StudyError) as excinfo:
            load_study(tmp_path / "absent.yaml")

        assert "absent.yaml" in str(excinfo.value)
        assert "introuvable" in str(excinfo.value)

    def test_malformed_yaml_carries_its_path(self, tmp_path):
        target = tmp_path / "ETUDE.yaml"
        target.write_text("etude: [\n  nom: x\n", encoding="utf-8")

        with pytest.raises(StudyError) as excinfo:
            load_study(target)

        assert "ETUDE.yaml" in str(excinfo.value)

    def test_an_empty_file_is_refused(self, tmp_path):
        target = tmp_path / "ETUDE.yaml"
        target.write_text("", encoding="utf-8")

        with pytest.raises(StudyError, match="vide"):
            load_study(target)

    def test_the_source_resolves_against_the_study_file_not_the_cwd(self, tmp_path, monkeypatch):
        nested = tmp_path / "etude"
        nested.mkdir()
        target = _write(nested, MINIMAL)
        monkeypatch.chdir(tmp_path)

        study = load_study(target)

        assert study.resolved_source() == nested.resolve() / "TRAJECTOIRES"
        assert study.resolved_output() == nested.resolve() / "SORTIE"

    def test_an_absolute_source_is_left_alone(self, tmp_path):
        target = _write(tmp_path, {**MINIMAL, "etude": {"nom": "L", "source": "/data/traj"}})

        assert load_study(target).resolved_source() == Path("/data/traj")


class TestRoundTrip:
    def test_a_study_survives_write_then_load(self, tmp_path):
        original = parse_study(
            {
                **MINIMAL,
                "symetrie": {"groupe": "Cs", "n_azimuts": 4},
                "bandes": {"bornes": [0.4, 1.0, 2.0]},
                "atmosphere": {"delta_t_K": -5.0},
                "parametres": {"PARA1": {"role": "conditionnel", "niveaux": 3, "echelle": "log"}},
                "doe": {"graine": 42, "braquages": [{"nom": "tangage", "dm": 12.0}]},
            }
        )

        reloaded = load_study(write_study(original, tmp_path / "ETUDE.yaml"))

        assert reloaded.name == original.name
        assert reloaded.symmetry == original.symmetry
        assert reloaded.bands.edges == original.bands.edges
        assert reloaded.envelope == original.envelope
        assert reloaded.doe.seed == original.doe.seed
        assert reloaded.doe.deflections == original.doe.deflections
        assert reloaded.delta_t_k == original.delta_t_k
        assert reloaded.declared_columns["PARA1"].scale is Scale.LOG

    def test_auto_detected_columns_can_be_promoted_to_declared(self, tmp_path):
        from cfd_traj.data.columns import ColumnSpec

        study = parse_study(MINIMAL)
        promoted = [ColumnSpec(name="PARA9", role=Role.PRINCIPAL, levels=4, unit="bar")]

        reloaded = load_study(write_study(study, tmp_path / "ETUDE.yaml", columns=promoted))

        assert reloaded.declared_columns["PARA9"].levels == 4
        assert reloaded.declared_columns["PARA9"].unit == "bar"

    def test_a_header_comment_is_kept_at_the_top(self, tmp_path):
        target = write_study(parse_study(MINIMAL), tmp_path / "ETUDE.yaml", header="# bonjour\n")

        assert target.read_text().startswith("# bonjour\n")

    def test_the_serialised_shape_uses_the_french_keys(self):
        payload = study_to_dict(parse_study(MINIMAL))

        assert set(payload) >= {"etude", "reference", "symetrie", "bandes", "enveloppe", "doe"}
        assert payload["etude"]["nom"] == "LOT"


class TestDeflectionSet:
    def test_the_symmetry_matches_the_core_classification(self):
        assert DeflectionSet("neutre").symmetry is DeflectionSymmetry.NULLE
        assert DeflectionSet("tangage", dm=15.0).symmetry is DeflectionSymmetry.SYMETRIQUE
        assert DeflectionSet("roulis", dl=15.0).symmetry is DeflectionSymmetry.ANTISYMETRIQUE
        assert DeflectionSet("mixte", dl=1.0, dm=2.0).symmetry is DeflectionSymmetry.QUELCONQUE

    def test_the_values_come_out_in_roll_pitch_yaw_order(self):
        assert DeflectionSet("x", dl=1.0, dm=2.0, dn=3.0).values == (1.0, 2.0, 3.0)

    def test_a_nameless_set_is_refused(self):
        with pytest.raises(ValueError, match="nom"):
            DeflectionSet("")
