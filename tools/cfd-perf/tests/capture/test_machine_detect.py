"""Tests de la détection automatique de la machine."""

from __future__ import annotations

import textwrap

import pytest

from cfd_perf.capture import machine_detect
from cfd_perf.capture.machine_detect import MachineOverrides, detect_machine


@pytest.fixture
def hotes_file(tmp_path):
    p = tmp_path / "hotes.yaml"
    p.write_text(
        textwrap.dedent(
            """
            defaut:
              cores_per_node: 1
            cluster-a:
              cores_per_node: 48
              ram_per_node_gb: 192
              max_nodes: 32
              max_walltime_hours: 24
            """
        )
    )
    return p


def _no_tools(monkeypatch):
    """Simule un poste sans SLURM ni /proc : la détection ne renvoie rien.

    On neutralise directement les détecteurs (et non Path.is_file) pour ne pas
    empêcher la lecture de hotes.yaml.
    """
    monkeypatch.setattr(machine_detect, "_detect_cores_per_node", lambda: None)
    monkeypatch.setattr(machine_detect, "_detect_ram_per_node_gb", lambda: None)


class TestOverrides:
    def test_cli_overrides_win(self, monkeypatch, hotes_file):
        monkeypatch.setattr(machine_detect.socket, "gethostname", lambda: "cluster-a-login")
        m = detect_machine(
            overrides=MachineOverrides(cores_per_node=7, ram_per_node_gb=13.0),
            hotes_path=hotes_file,
        )
        assert m.cores_per_node == 7
        assert m.ram_per_node_gb == 13.0


class TestDetection:
    def test_scontrol_is_used_when_present(self, monkeypatch, hotes_file):
        def fake_run(cmd):
            if cmd[0] == "scontrol":
                return "NodeName=n1 CPUTot=64 RealMemory=131072 State=IDLE"
            return None

        monkeypatch.setattr(machine_detect, "_run", fake_run)
        monkeypatch.setattr(machine_detect.socket, "gethostname", lambda: "whatever")
        m = detect_machine(hotes_path=hotes_file)
        assert m.cores_per_node == 64
        assert m.ram_per_node_gb == pytest.approx(128.0, abs=0.1)  # 131072 Mo / 1024


class TestHotesFallback:
    def test_hostname_prefix_match(self, monkeypatch, hotes_file):
        _no_tools(monkeypatch)
        monkeypatch.setattr(machine_detect.socket, "gethostname", lambda: "cluster-a-node042")
        m = detect_machine(hotes_path=hotes_file)
        assert m.cores_per_node == 48
        assert m.ram_per_node_gb == 192
        assert m.max_nodes == 32
        assert m.max_walltime_hours == 24

    def test_falls_back_to_defaut(self, monkeypatch, hotes_file):
        _no_tools(monkeypatch)
        monkeypatch.setattr(machine_detect.socket, "gethostname", lambda: "hote-inconnu")
        m = detect_machine(hotes_path=hotes_file)
        assert m.cores_per_node == 1
        assert m.ram_per_node_gb is None

    def test_missing_hotes_file_yields_defaults(self, monkeypatch, tmp_path):
        _no_tools(monkeypatch)
        monkeypatch.setattr(machine_detect.socket, "gethostname", lambda: "x")
        m = detect_machine(hotes_path=tmp_path / "absent.yaml")
        assert m.cores_per_node == 1

    def test_never_raises_off_cluster(self, monkeypatch, tmp_path):
        _no_tools(monkeypatch)
        monkeypatch.setattr(machine_detect.socket, "gethostname", lambda: "x")
        # Doit produire un Machine valide, jamais lever.
        m = detect_machine(hotes_path=tmp_path / "absent.yaml", name="essai")
        assert m.name == "essai"
        assert m.cores_per_node >= 1
