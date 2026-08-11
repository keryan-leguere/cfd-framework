"""Le lanceur de secours : la commande doit rester utilisable.

Scénario visé, courant sur calculateur : Python vient d'une image conteneur
chargée par ``module load``. ``pip install`` grave dans le script console un
chemin d'interpréteur *interne à l'image*, que l'hôte ne voit pas ; la commande
existe, elle est exécutable, et elle meurt en « bad interpreter ».

Ces tests reproduisent les trois formes de shebang que pip peut écrire, et
vérifient que le lanceur, lui, ne dépend d'aucun chemin gravé.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from rich.console import Console

from cfd_perf.cli import main as cli_main
from cfd_perf.cli import shim
from cfd_perf.cli.main import main


@pytest.fixture
def console_large(monkeypatch):
    """Panneaux rendus larges : les chemins de tmp_path ne coupent plus les phrases."""
    monkeypatch.setattr(cli_main, "console", Console(width=200))
    monkeypatch.setattr(cli_main, "err_console", Console(stderr=True, width=200))


def _script(chemin: Path, contenu: str) -> Path:
    chemin.write_text(contenu, encoding="utf-8")
    chemin.chmod(chemin.stat().st_mode | stat.S_IXUSR)
    return chemin


class TestLectureDuShebang:
    def test_chemin_absolu(self, tmp_path):
        s = _script(tmp_path / "cfd-perf", "#!/usr/bin/python3\nprint(1)\n")
        assert shim.interpreter_of(s) == "/usr/bin/python3"

    def test_env_designe_python_pas_env(self, tmp_path):
        """« #!/usr/bin/env python3 » : c'est python3 qu'il faut savoir trouver."""
        s = _script(tmp_path / "cfd-perf", "#!/usr/bin/env python3\nprint(1)\n")
        assert shim.interpreter_of(s) == "python3"

    def test_forme_shebang_long(self, tmp_path):
        """Au-delà de 127 octets, pip passe par /bin/sh : le vrai chemin est ligne 2."""
        s = _script(
            tmp_path / "cfd-perf",
            "#!/bin/sh\n'''exec' /opt/image/python3.9 \"$0\" \"$@\"\n' '''\nprint(1)\n",
        )
        assert shim.interpreter_of(s) == "/opt/image/python3.9"

    def test_forme_shebang_long_avec_espaces(self, tmp_path):
        s = _script(
            tmp_path / "cfd-perf",
            "#!/bin/sh\n'''exec' \"/opt/mon image/python3\" \"$0\" \"$@\"\n' '''\n",
        )
        assert shim.interpreter_of(s) == "/opt/mon image/python3"

    def test_sans_shebang(self, tmp_path):
        assert shim.interpreter_of(_script(tmp_path / "x", "echo bonjour\n")) is None

    def test_fichier_absent(self, tmp_path):
        assert shim.interpreter_of(tmp_path / "absent") is None


class TestDiagnostic:
    def test_interpreteur_absent_est_detecte(self, tmp_path):
        s = _script(tmp_path / "cfd-perf", "#!/opt/image/inexistant/python3\n")
        assert shim.is_runnable(s) is False

    def test_interpreteur_present_est_accepte(self, tmp_path):
        s = _script(tmp_path / "cfd-perf", f"#!{sys.executable}\n")
        assert shim.is_runnable(s) is True

    def test_un_lanceur_shell_est_toujours_lancable(self, tmp_path):
        lanceur = shim.write_launcher(tmp_path)
        assert shim.interpreter_of(lanceur) is None
        assert shim.is_runnable(lanceur) is True

    def test_les_commandes_du_path_sont_dans_lordre_du_shell(self, tmp_path, monkeypatch):
        premier, second = tmp_path / "a", tmp_path / "b"
        premier.mkdir()
        second.mkdir()
        _script(premier / "cfd-perf", "#!/bin/sh\n")
        _script(second / "cfd-perf", "#!/bin/sh\n")
        monkeypatch.setenv("PATH", f"{premier}{os.pathsep}{second}")
        assert shim.commands_on_path() == [premier / "cfd-perf", second / "cfd-perf"]

    def test_un_fichier_non_executable_est_ignore(self, tmp_path, monkeypatch):
        (tmp_path / "cfd-perf").write_text("#!/bin/sh\n")
        (tmp_path / "cfd-perf").chmod(0o644)
        monkeypatch.setenv("PATH", str(tmp_path))
        assert shim.commands_on_path() == []

    def test_repertoire_sur_le_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}/usr/bin")
        assert shim.dir_is_on_path(tmp_path) is True
        assert shim.dir_is_on_path(tmp_path / "ailleurs") is False


class TestEcriture:
    def test_le_lanceur_est_executable(self, tmp_path):
        lanceur = shim.write_launcher(tmp_path / "bin")
        assert lanceur == tmp_path / "bin" / "cfd-perf"
        assert os.access(str(lanceur), os.X_OK)

    def test_il_ne_grave_aucun_interpreteur(self, tmp_path):
        """Le point de tout l'exercice : aucun chemin absolu de python dedans."""
        texte = shim.write_launcher(tmp_path).read_text(encoding="utf-8")
        assert sys.executable not in texte
        assert "-m cfd_perf" in texte
        assert "${CFD_PERF_PYTHON:-python3}" in texte

    def test_il_refuse_decraser_sans_force(self, tmp_path):
        shim.write_launcher(tmp_path)
        with pytest.raises(FileExistsError):
            shim.write_launcher(tmp_path)

    def test_force_ecrase(self, tmp_path):
        (tmp_path / "cfd-perf").write_text("vieux lanceur\n")
        assert "cfd_perf" in shim.write_launcher(tmp_path, force=True).read_text()


class TestLanceurReel:
    """Le lanceur écrit doit vraiment lancer la CLI, via bash, sans script console."""

    def test_il_lance_la_cli(self, tmp_path):
        lanceur = shim.write_launcher(tmp_path)
        env = dict(os.environ, CFD_PERF_PYTHON=sys.executable)
        res = subprocess.run(
            [str(lanceur), "--help"], capture_output=True, text=True, env=env, timeout=120
        )
        assert res.returncode == 0, res.stderr
        assert "cfd-perf" in res.stdout

    def test_il_remonte_le_code_de_sortie(self, tmp_path):
        lanceur = shim.write_launcher(tmp_path)
        env = dict(os.environ, CFD_PERF_PYTHON=sys.executable)
        res = subprocess.run(
            [str(lanceur), "check", str(tmp_path / "absent.yaml")],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
        assert res.returncode == 1

    def test_interpreteur_introuvable_dit_quoi_faire(self, tmp_path):
        lanceur = shim.write_launcher(tmp_path)
        env = dict(os.environ, CFD_PERF_PYTHON="/opt/image/python-absent")
        res = subprocess.run(
            [str(lanceur), "--help"], capture_output=True, text=True, env=env, timeout=120
        )
        assert res.returncode == 127
        assert "CFD_PERF_PYTHON" in res.stderr


class TestSousCommande:
    @pytest.fixture(autouse=True)
    def _large(self, console_large):
        pass

    def test_elle_ecrit_le_lanceur(self, tmp_path, capsys):
        assert main(["shim", "-o", str(tmp_path)]) == 0
        assert (tmp_path / "cfd-perf").is_file()
        assert "Lanceur écrit" in capsys.readouterr().out

    def test_elle_previent_si_le_repertoire_nest_pas_sur_le_path(self, tmp_path, capsys):
        assert main(["shim", "-o", str(tmp_path)]) == 0
        assert "Ce répertoire n'est pas sur le PATH" in capsys.readouterr().out

    def test_elle_se_tait_si_le_repertoire_est_sur_le_path(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setenv("PATH", str(tmp_path))
        assert main(["shim", "-o", str(tmp_path)]) == 0
        assert "Ce répertoire n'est pas sur le PATH" not in capsys.readouterr().out

    def test_elle_signale_une_commande_cassee_qui_prend_le_dessus(
        self, tmp_path, capsys, monkeypatch
    ):
        """Le vrai piège : un script console mort placé plus tôt dans le PATH."""
        casse = tmp_path / "local"
        casse.mkdir()
        _script(casse / "cfd-perf", "#!/opt/image/python3.9\n")
        cible = tmp_path / "bin"
        monkeypatch.setenv("PATH", f"{casse}{os.pathsep}{cible}")
        assert main(["shim", "-o", str(cible)]) == 0
        sortie = capsys.readouterr().out
        assert "interpréteur absent" in sortie
        assert "elle est cassée" in sortie

    def test_elle_refuse_decraser_sans_force(self, tmp_path, capsys):
        main(["shim", "-o", str(tmp_path)])
        with pytest.raises(SystemExit) as exc:
            main(["shim", "-o", str(tmp_path)])
        assert exc.value.code == 1
        assert "--force" in capsys.readouterr().err
