"""Tests du manifeste de capture (aller-retour JSON)."""

from __future__ import annotations

import pytest

from cfd_perf.capture.manifest import CaptureManifest, CaptureRun


def _manifest():
    return CaptureManifest(
        adapter_id="mock",
        case_dir="/tmp/cas",
        title="cas",
        created_at="2026-07-17T00:00:00+00:00",
        queue="normal",
        runs=(
            CaptureRun(cores=8, run_dir="/tmp/cas/PILOTE/mock_8", job_id="LOCAL", submitted_at="t"),
            CaptureRun(cores=16, run_dir="/tmp/cas/PILOTE/mock_16", job_id="42", submitted_at="t"),
        ),
    )


class TestRoundTrip:
    def test_save_then_load(self, tmp_path):
        original = _manifest()
        original.save(tmp_path)
        loaded = CaptureManifest.load(tmp_path)
        assert loaded == original
        assert len(loaded.runs) == 2
        assert loaded.runs[1].job_id == "42"

    def test_load_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="manifeste introuvable"):
            CaptureManifest.load(tmp_path)

    def test_json_is_utf8_readable(self, tmp_path):
        path = _manifest().save(tmp_path)
        text = path.read_text()
        assert "mock" in text and "normal" in text
