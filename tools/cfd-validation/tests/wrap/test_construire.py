"""La compilation par f2py : ses refus, et le chargement par chemin.

La compilation elle-même est éprouvée par ``tests/test_fortran.py``, qui ne
tourne que là où la chaîne est complète. Ici on fixe ce qui doit marcher
**partout** : les refus, et leurs messages.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cfd_validation.wrap import construire as module_construire
from cfd_validation.wrap.construire import ErreurConstruction, charger_module, construire
from cfd_validation.wrap.toolchain import Toolchain


class TestRefus:
    def test_une_source_absente_est_refusee_avant_toute_compilation(self, tmp_path: Path) -> None:
        with pytest.raises(ErreurConstruction, match="introuvable"):
            construire(tmp_path / "nulle-part.f")

    def test_une_liste_vide_est_refusee(self) -> None:
        with pytest.raises(ErreurConstruction, match="aucune source"):
            construire([])

    def test_une_chaine_incomplete_est_refusee_en_nommant_le_remede(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Le point de tout ce module : jamais une trace de compilation.

        Ce que produit ``f2py -c`` sans meson est illisible et ne nomme nulle
        part ce qu'il faut installer.
        """
        source = tmp_path / "aero.f"
        source.write_text("      END\n", encoding="utf-8")

        monkeypatch.setattr(
            module_construire,
            "inspecter_toolchain",
            lambda: Toolchain(
                numpy="2.1.0",
                backend="meson",
                gfortran=None,
                gcc=None,
                meson=None,
                ninja=None,
                distutils=False,
                manques=("meson", "ninja", "gfortran"),
            ),
        )
        with pytest.raises(ErreurConstruction) as capture:
            construire(source)
        message = str(capture.value)
        assert "meson" in message
        assert "Remède" in message
        assert "pip install" in message


class TestChargement:
    def test_un_module_absent_est_refuse(self, tmp_path: Path) -> None:
        with pytest.raises(ErreurConstruction, match="introuvable"):
            charger_module(tmp_path / "aero.so")

    def test_un_fichier_qui_n_est_pas_un_module_est_refuse(self, tmp_path: Path) -> None:
        fichier = tmp_path / "donnees.txt"
        fichier.write_text("bonjour", encoding="utf-8")
        with pytest.raises(ErreurConstruction, match="importable"):
            charger_module(fichier)

    def test_un_module_python_se_charge_par_son_chemin(self, tmp_path: Path) -> None:
        """Le chargement par chemin sert à faire coexister deux versions d'un modèle."""
        fichier = tmp_path / "faux_modele.py"
        fichier.write_text("VALEUR = 42\n", encoding="utf-8")
        assert charger_module(fichier).VALEUR == 42
