"""Le contrôle sur du Fortran réellement compilé.

Marqué ``compilateur`` : ces tests réclament gfortran **et** le moteur de
compilation de f2py, ce qu'un calculateur isolé n'a pas forcément. Tout le
reste de la suite tourne sans.

    pytest -m "not compilateur"     # explicitement, sur site isolé

Ils valent la peine malgré tout, parce qu'ils sont les seuls à éprouver ce que
f2py produit vraiment : un COMMON block est un objet **appelable**, ses noms
sont en minuscules, ses tableaux sont Fortran-contigus, et un entier du bloc
arrive en tableau à zéro dimension. Rien de tout cela ne se devine.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd
import pytest

from cfd_validation.data.spec import charger_fichier
from cfd_validation.engine.tables import valider_tables
from cfd_validation.paths import EXEMPLE_DIR, FORTRAN_DIR
from cfd_validation.wrap.bloc import blocs_exposes
from cfd_validation.wrap.construire import charger_module, construire
from cfd_validation.wrap.toolchain import inspecter_toolchain

pytestmark = pytest.mark.compilateur

CHAINE = inspecter_toolchain()

sans_chaine = pytest.mark.skipif(
    not CHAINE.pret,
    reason=f"chaîne de compilation incomplète : {', '.join(CHAINE.manques) or '—'}",
)


@pytest.fixture(scope="module")
def aero(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """Le modèle Fortran de l'exemple, compilé et chargé."""
    if not CHAINE.pret:
        pytest.skip("chaîne de compilation incomplète")
    atelier = tmp_path_factory.mktemp("fortran")
    produit = construire(FORTRAN_DIR / "aero.f", nom_module="aero", destination=atelier)
    module = charger_module(produit)
    module.init_tables()
    return module


@pytest.fixture
def specs() -> Any:
    return charger_fichier(EXEMPLE_DIR / "TABLES.yaml")


def _appeler(aero: Any) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def modele(entrees: pd.DataFrame) -> pd.DataFrame:
        rendu = entrees.copy()
        if "delta" in entrees.columns:
            rendu["CN"] = aero.eval_cn(
                entrees["mach"].to_numpy(),
                entrees["alpha"].to_numpy(),
                entrees["delta"].to_numpy(),
            )
        else:
            rendu["CA"] = aero.eval_ca(entrees["mach"].to_numpy(), entrees["alpha"].to_numpy())
        return rendu

    return modele


@sans_chaine
class TestCompilation:
    def test_le_module_se_compile_et_se_charge(self, aero: Any) -> None:
        assert hasattr(aero, "eval_cn")

    def test_les_common_blocks_sont_detectes(self, aero: Any) -> None:
        """Ils sont **appelables**, comme les routines : seul leur contenu les sépare."""
        blocs = blocs_exposes(aero)
        assert "tab_cn" in blocs
        assert set(blocs["tab_cn"]) == {"tab_cn", "npt_cn"}

    def test_une_routine_n_est_pas_prise_pour_un_bloc(self, aero: Any) -> None:
        assert "eval_cn" not in blocs_exposes(aero)

    def test_le_tableau_arrive_fortran_contigu_et_se_lit_quand_meme(
        self, aero: Any, specs: Any
    ) -> None:
        import numpy as np

        from cfd_validation.wrap.bloc import lire_table

        assert np.asarray(aero.tab_cn.tab_cn).flags["F_CONTIGUOUS"]
        assert len(lire_table(aero, specs["CN"])) == 294


@sans_chaine
class TestControle:
    def test_le_fortran_juste_relit_ses_tables_sans_un_ecart(self, aero: Any, specs: Any) -> None:
        aero.regler_bug(0)
        rapport = valider_tables(aero, specs, modele=_appeler(aero))
        assert rapport.conforme
        assert rapport.n_points == 336

    @pytest.mark.parametrize(
        "mode,attendu",
        [(1, "facteur_echelle"), (2, "axes_transposes"), (3, "ecretage")],
    )
    def test_une_panne_reelle_du_fortran_est_nommee(
        self, aero: Any, specs: Any, mode: int, attendu: str
    ) -> None:
        """Une vraie erreur de lecture dans le code compilé, pas une simulation."""
        aero.regler_bug(mode)
        try:
            rapport = valider_tables(aero, specs, modele=_appeler(aero))
            motif = rapport["CN"].grandeur("CN").motif_principal
            assert motif is not None
            assert motif.nom == attendu
        finally:
            aero.regler_bug(0)

    def test_le_compteur_du_bloc_rogne_bien_la_queue(self, aero: Any, specs: Any) -> None:
        """Sans quoi les 26 lignes de remplissage sortiraient en écarts."""
        from dataclasses import replace

        aero.regler_bug(0)
        sans = valider_tables(
            aero, {"CN": replace(specs["CN"], lignes=None)}, modele=_appeler(aero)
        )
        motif = sans["CN"].grandeur("CN").motif_principal
        assert motif is not None
        assert motif.nom == "queue_non_renseignee"


class TestSansChaine:
    def test_l_etat_de_la_chaine_est_rapporte_quoi_qu_il_arrive(self) -> None:
        """Le test qui tourne partout : savoir pourquoi les autres sont sautés."""
        assert CHAINE.backend in {"meson", "distutils"}
        if not CHAINE.pret:
            assert CHAINE.remede, "un manque sans remède ne sert à rien"
