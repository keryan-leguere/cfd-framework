"""Tests du pont Python → adaptateur bash (contre l'adaptateur mock)."""

from __future__ import annotations

import pytest

from cfd_perf.capture.adapter import BashAdapter, CaptureError


@pytest.fixture
def mock_adapter():
    return BashAdapter("mock")


class TestResolution:
    def test_mock_is_found(self, mock_adapter):
        assert mock_adapter.path.name == "mock.sh"
        assert mock_adapter.nom() == "mock"

    def test_unknown_adapter_raises(self):
        with pytest.raises(CaptureError, match="introuvable"):
            BashAdapter("solveur_inexistant")


class TestContract:
    def test_installation_ok(self, mock_adapter):
        assert mock_adapter.verifier_installation() is True

    def test_elements_a_copier(self, mock_adapter):
        assert mock_adapter.elements_a_copier() == ["constant", "system"]

    def test_full_capture_cycle(self, mock_adapter, tmp_path):
        run_dir = tmp_path / "run_16"
        mock_adapter.preparer(run_dir, 16)
        job_id = mock_adapter.soumettre(run_dir, 16)
        assert job_id == "LOCAL"
        assert mock_adapter.etat(run_dir, job_id) == "DONE"

        temps = mock_adapter.temps_total_s(run_dir)
        n_iter = mock_adapter.nb_iterations(run_dir)
        ram = mock_adapter.ram_crete_gb(run_dir, job_id)
        assert temps > 0
        assert n_iter == 200
        assert ram is not None and ram > 0

    def test_numbers_are_dot_decimal_despite_locale(self, mock_adapter, tmp_path):
        """Le point décimal doit être imposé quelle que soit la locale de l'hôte."""
        run_dir = tmp_path / "run"
        mock_adapter.soumettre(run_dir, 8)
        # Ne lève pas : la conversion float réussit (pas de virgule décimale).
        assert isinstance(mock_adapter.temps_total_s(run_dir), float)

    def test_time_per_iter_decreases_with_cores(self, mock_adapter, tmp_path):
        """La loi synthétique doit donner un temps/itér qui baisse d'abord."""
        tpi = {}
        for cores in (8, 16, 32):
            run_dir = tmp_path / f"r{cores}"
            mock_adapter.soumettre(run_dir, cores)
            tpi[cores] = mock_adapter.temps_total_s(run_dir) / mock_adapter.nb_iterations(run_dir)
        assert tpi[16] < tpi[8]
        assert tpi[32] < tpi[16]

    def test_mesh_and_target_iterations(self, mock_adapter, tmp_path):
        assert mock_adapter.nb_cellules(tmp_path) == 2_000_000
        assert mock_adapter.cible_iterations(tmp_path) == 5000

    def test_mesh_reads_marker_when_present(self, mock_adapter, tmp_path):
        (tmp_path / ".mock_cells").write_text("750000\n")
        assert mock_adapter.nb_cellules(tmp_path) == 750_000


class TestRamNonePath:
    def test_slurm_default_returns_none_without_scheduler(self, tmp_path):
        """L'implémentation SLURM par défaut (héritée) renvoie None hors scheduler.

        OF n'override pas adapt_pilote_ram_crete : avec un job « LOCAL », le
        défaut de interface.sh écrit une chaîne vide → None côté Python.
        """
        of = BashAdapter("OF")
        assert of.ram_crete_gb(tmp_path, "LOCAL") is None


class TestErrors:
    def test_missing_run_log_surfaces_as_capture_error(self, mock_adapter, tmp_path):
        # temps_total sur un run sans log : awk lit un fichier absent -> échec.
        with pytest.raises(CaptureError):
            mock_adapter.temps_total_s(tmp_path / "inexistant")
