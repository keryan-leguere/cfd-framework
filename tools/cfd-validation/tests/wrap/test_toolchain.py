"""L'inspection de la chaîne de compilation.

Ce module existe pour qu'un échec de compilation soit **nommable avant** la
tentative. Les tests fixent donc surtout des messages : un remède qui ne dit
pas quoi taper ne vaut pas mieux que la trace qu'il remplace.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cfd_validation.wrap import toolchain
from cfd_validation.wrap.toolchain import Toolchain, inspecter_toolchain


def _chaine(**surcharges: object) -> Toolchain:
    base: dict[str, object] = {
        "numpy": "2.1.0",
        "backend": "meson",
        "gfortran": "/usr/bin/gfortran",
        "gcc": "/usr/bin/gcc",
        "meson": "/usr/bin/meson",
        "ninja": "/usr/bin/ninja",
        "distutils": False,
        "manques": (),
        "hors_path": (),
    }
    base.update(surcharges)
    return Toolchain(**base)  # type: ignore[arg-type]


class TestEtat:
    def test_une_chaine_complete_est_prete_et_sans_remede(self) -> None:
        chaine = _chaine()
        assert chaine.pret
        assert chaine.remede == ""

    def test_l_inspection_reelle_ne_leve_jamais(self) -> None:
        """Elle est appelée dans un panneau de rapport : elle ne doit rien casser."""
        chaine = inspecter_toolchain()
        assert chaine.backend in {"meson", "distutils"}
        assert isinstance(chaine.pret, bool)


class TestRemede:
    def test_un_outil_absent_donne_la_commande_pip(self) -> None:
        chaine = _chaine(meson=None, ninja=None, manques=("meson", "ninja"))
        assert "pip install meson ninja" in chaine.remede

    def test_un_outil_installe_hors_path_donne_le_bon_remede(self) -> None:
        """Le piège réel : les outils sont là, mais f2py les lance par leur nom.

        L'échec brut est un ``FileNotFoundError: 'meson'`` qui ne dit nulle part
        d'activer son environnement virtuel.
        """
        chaine = _chaine(meson=None, manques=("meson",), hors_path=("meson",))
        remede = chaine.remede
        assert "PATH" in remede
        assert "pip install" not in remede  # il est déjà installé

    def test_les_deux_cas_coexistent_dans_un_meme_remede(self) -> None:
        chaine = _chaine(meson=None, ninja=None, manques=("meson", "ninja"), hors_path=("meson",))
        remede = chaine.remede
        assert "PATH" in remede
        assert "pip install ninja" in remede

    def test_un_compilateur_absent_est_nomme(self) -> None:
        chaine = _chaine(gfortran=None, manques=("gfortran",))
        assert "gfortran" in chaine.remede

    def test_l_accord_suit_le_nombre_d_outils(self) -> None:
        un = _chaine(meson=None, manques=("meson",), hors_path=("meson",))
        deux = _chaine(
            meson=None, ninja=None, manques=("meson", "ninja"), hors_path=("meson", "ninja")
        )
        assert "est installé" in un.remede
        assert "sont installés" in deux.remede


class TestDetection:
    def test_le_repertoire_de_scripts_n_est_pas_celui_de_l_interpreteur_resolu(self) -> None:
        """Dans un venv, ``sys.executable`` est un lien vers le Python système.

        Le résoudre désignerait ``/usr/bin`` — c'est-à-dire tout sauf le
        répertoire où pip a déposé meson.
        """
        scripts = toolchain._bin_interpreteur()
        assert isinstance(scripts, Path)
        assert scripts.exists()

    def test_numpy_2_impose_le_moteur_meson(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import numpy

        monkeypatch.setattr(numpy, "__version__", "2.4.0", raising=False)
        assert inspecter_toolchain().backend == "meson"

    def test_un_outil_absent_du_path_figure_dans_les_manques(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("cfd_validation.wrap.toolchain.shutil.which", lambda nom: None)
        chaine = inspecter_toolchain()
        assert not chaine.pret
        assert "gfortran" in chaine.manques
