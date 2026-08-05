"""Rapports Rich."""

from __future__ import annotations

import io
import re

import pytest
from rich.console import Console

from cfd_traj.core.symmetry import SymmetryGroup, SymmetrySpec
from cfd_traj.data.columns import build_specs
from cfd_traj.data.study import BandSpec, DoeMethod, DoeSpec, EnvelopeSpec, default_study
from cfd_traj.engine.bands import build_bands
from cfd_traj.engine.coverage import check_coverage
from cfd_traj.engine.doe import build_plan
from cfd_traj.engine.envelope import build_envelope
from cfd_traj.engine.inspect import inspect
from cfd_traj.report import console as report

C4V = SymmetrySpec(group=SymmetryGroup.C4V)

#: Vocabulaire proscrit : l'outil traite de trajectoires, pas d'un phénomène
#: physique particulier. Recherché sur des mots entiers — « jet » en
#: sous-chaîne se retrouve dans « rejeté » ou « objet ».
FORBIDDEN = ("jet", "jets", "tuyère", "tuyere", "panache", "npr", "p0j")
FORBIDDEN_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in FORBIDDEN) + r")\b", re.IGNORECASE
)


def render(renderable, width: int = 110) -> str:
    """Rend un renderable Rich en texte."""
    con = Console(file=io.StringIO(), record=True, width=width, legacy_windows=False)
    con.print(renderable)
    return con.export_text()


@pytest.fixture
def contexte(dataset_realiste):
    """Enveloppe, plan et couverture d'un lot réaliste."""
    specs, _ = build_specs(dataset_realiste.columns, dataset_realiste.column_values(), {})
    bands = build_bands(dataset_realiste.values("Mach"), BandSpec(n_bands=4, min_points=50))
    envelope = build_envelope(
        dataset_realiste, band_set=bands, specs=specs, spec=EnvelopeSpec(), symmetry=C4V
    )
    plan = build_plan(
        envelope,
        doe=DoeSpec(method=DoeMethod.LHS, n_lhs_per_band=5, max_nodes=100_000),
        symmetry=C4V,
        ds=dataset_realiste,
    )
    coverage = check_coverage(dataset_realiste, envelope=envelope)
    inspection = inspect(dataset_realiste, specs=specs)
    return specs, envelope, plan, coverage, inspection


class TestFormatting:
    def test_numbers_use_a_french_decimal_comma(self):
        thin = report.THIN_SPACE

        assert report.fr(1234.5, 1) == f"1{thin}234,5"
        assert report.fr(-0.25, 2) == "-0,25"
        assert report.fr_int(1_000_000) == f"1{thin}000{thin}000"

    def test_percentages_are_french(self):
        assert report.pct(0.9987, 2) == "99,87 %"

    def test_a_missing_value_shows_a_dash(self):
        assert report.fr(float("nan")) == "—"
        assert report.compact(float("nan")) == "—"

    def test_large_numbers_are_compacted(self):
        assert report.compact(5.4e7) == "5,40e7"
        assert report.compact(12.5) == "12,50"


class TestInspection:
    def test_the_report_answers_the_headline_questions(self, contexte):
        specs, _, _, _, inspection = contexte

        text = render(report.render_inspection(inspection, specs))

        assert "tirs" in text
        assert "points de vol" in text
        assert "dimension intrinsèque" in text

    def test_auto_detected_roles_are_flagged(self, contexte):
        specs, _, _, _, inspection = contexte

        text = render(report.render_inspection(inspection, specs))

        assert "auto-détectés" in text

    def test_the_verbose_report_is_longer(self, contexte):
        specs, _, _, _, inspection = contexte

        short = render(report.render_inspection(inspection, specs, verbose=False))
        long = render(report.render_inspection(inspection, specs, verbose=True))

        assert len(long) >= len(short)

    def test_the_suggested_block_is_pastable_yaml(self, contexte):
        import yaml

        specs, _, _, _, _ = contexte

        block = report.suggest_parameters_block(specs)

        assert block.startswith("parametres:")
        assert isinstance(yaml.safe_load(block), dict)

    def test_the_azimuth_levels_are_not_offered_as_a_free_choice(self, contexte):
        specs, _, _, _, _ = contexte

        block = report.suggest_parameters_block(specs)

        line = next(line for line in block.splitlines() if "phi_fold" in line)
        assert "niveaux:" not in line
        assert "imposés par le groupe" in line


class TestSymmetry:
    @pytest.mark.parametrize("group", list(SymmetryGroup))
    def test_the_report_spells_out_what_the_group_implies(self, group):
        text = render(report.render_symmetry(SymmetrySpec(group=group)))

        assert str(group) in text
        assert "domaine de" in text
        assert "azimuts calculés" in text
        assert "composantes stockées" in text

    def test_a_cruciform_reports_its_half_turn_eighth(self):
        text = render(report.render_symmetry(C4V))

        assert "45,0°" in text
        assert "22,5°" in text


class TestEnvelope:
    def test_one_row_per_band(self, contexte):
        _, envelope, _, _, _ = contexte

        text = render(report.render_envelope(envelope))

        for band in envelope.bands:
            assert band.band.label.split("–")[0] in text

    def test_the_mechanical_ranges_are_stated_once_not_per_band(self, contexte):
        _, envelope, _, _, _ = contexte

        text = render(report.render_envelope(envelope))

        assert "plages mécaniques" in text
        assert text.count("dl") <= 2

    def test_the_quantiles_and_margin_are_shown(self, contexte):
        _, envelope, _, _, _ = contexte

        text = render(report.render_envelope(envelope))

        assert "quantiles" in text
        assert "marge" in text


class TestPlan:
    def test_the_answer_comes_first(self, contexte):
        _, _, plan, _, _ = contexte

        text = render(report.render_plan(plan))

        assert "cas de calcul" in text
        assert "équivalents configuration complète" in text
        assert "économie" in text

    def test_the_configurations_are_named_in_french(self, contexte):
        _, _, plan, _, _ = contexte

        text = render(report.render_plan(plan))

        assert "demi-configuration" in text or "configuration complète" in text

    def test_the_corner_count_is_explained(self, contexte):
        _, _, plan, _, _ = contexte

        text = render(report.render_plan(plan))

        assert "coins du domaine conditionnel" in text
        assert "extrapolation" in text


class TestCoverage:
    def test_the_rate_leads_the_report(self, contexte):
        _, _, _, coverage, _ = contexte

        text = render(report.render_coverage(coverage))

        assert "%" in text
        assert "interpolation stricte" in text

    def test_a_complete_coverage_says_so_without_offenders(self, dataset_realiste, envelope_exacte):
        result = check_coverage(dataset_realiste, envelope=envelope_exacte)

        text = render(report.render_coverage(result))

        assert "100,00 %" in text
        assert "les plus éloignés" not in text

    def test_a_single_offender_is_reported_in_the_singular(self, dataset_realiste, envelope_exacte):
        import numpy as np

        variable = envelope_exacte.bands[0].get("PARA2")
        assert variable is not None
        moved = dataset_realiste.values("PARA2").copy()
        index = int(
            np.flatnonzero(envelope_exacte.bands[0].band.contains(dataset_realiste.values("Mach")))[
                0
            ]
        )
        moved[index] = variable.bounds.high + 10.0
        result = check_coverage(
            dataset_realiste.with_columns({"PARA2": moved}), envelope=envelope_exacte
        )

        text = render(report.render_coverage(result))

        assert "Le point le plus éloigné" in text

    def test_a_mechanical_violation_gets_its_own_panel(self, dataset_realiste, band_set):
        from cfd_traj.data.columns import ColumnSpec, Role

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

        text = render(report.render_coverage(check_coverage(dataset_realiste, envelope=envelope)))

        assert "Plages mécaniques" in text
        assert "erreur du fichier d'étude" in text


class TestStudy:
    def test_the_study_summary_names_its_source(self, tmp_path):
        study = default_study(tmp_path / "TRAJ", name="essai")

        text = render(report.render_study(study))

        assert "essai" in text
        assert "TRAJ" in text


class TestVocabulary:
    def test_no_report_uses_the_forbidden_vocabulary(self, contexte):
        specs, envelope, plan, coverage, inspection = contexte

        everything = " ".join(
            render(renderable)
            for renderable in (
                report.render_inspection(inspection, specs, verbose=True),
                report.render_symmetry(C4V),
                report.render_envelope(envelope, verbose=True),
                report.render_plan(plan, verbose=True),
                report.render_coverage(coverage, verbose=True),
            )
        ).lower()

        found = FORBIDDEN_PATTERN.findall(everything)
        assert not found, f"vocabulaire proscrit dans les rapports : {sorted(set(found))}"


class TestGenericity:
    def test_a_lot_without_generic_columns_still_renders(self, make_lot):
        from cfd_traj.core.adim import Reference
        from cfd_traj.data.dataset import load_dataset
        from cfd_traj.data.derive import add_derived_columns

        ds = add_derived_columns(
            load_dataset(make_lot(n_shots=2, extra=())),
            reference=Reference(length_m=2.5),
            symmetry=C4V,
        )
        specs, _ = build_specs(ds.columns, ds.column_values(), {})
        bands = build_bands(ds.values("Mach"), BandSpec(n_bands=2, min_points=10))
        envelope = build_envelope(
            ds, band_set=bands, specs=specs, spec=EnvelopeSpec(), symmetry=C4V
        )

        assert render(report.render_envelope(envelope))
        assert render(report.render_inspection(inspect(ds, specs=specs), specs))

    def test_many_generic_columns_are_truncated_with_a_notice(self, make_lot):
        from cfd_traj.core.adim import Reference
        from cfd_traj.data.dataset import load_dataset
        from cfd_traj.data.derive import add_derived_columns

        extra = tuple(f"COL{i}" for i in range(12))
        ds = add_derived_columns(
            load_dataset(make_lot(n_shots=2, extra=extra)),
            reference=Reference(length_m=2.5),
            symmetry=C4V,
        )
        specs, _ = build_specs(ds.columns, ds.column_values(), {})
        bands = build_bands(ds.values("Mach"), BandSpec(n_bands=2, min_points=10))
        envelope = build_envelope(
            ds, band_set=bands, specs=specs, spec=EnvelopeSpec(), symmetry=C4V
        )

        text = render(report.render_envelope(envelope, verbose=False))

        assert "de plus" in text
