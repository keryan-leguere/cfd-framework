"""Le paquet doit être autonome : installé, il se suffit à lui-même.

Ces tests verrouillent ce qui casserait un ``pip install`` sans dépôt à côté :
les adaptateurs bash et l'exemple doivent être livrés *dans* le paquet, et
localisés depuis celui-ci et non depuis une arborescence voisine.
"""

from __future__ import annotations

import pytest

import cfd_perf
from cfd_perf import paths
from cfd_perf.capture.adapter import BashAdapter, CaptureError


class TestDonneesLivrees:
    def test_les_donnees_sont_dans_le_paquet(self):
        assert paths.ADAPTATEUR_DIR.parent == paths.PACKAGE_DIR
        assert paths.EXEMPLE_DIR.parent == paths.PACKAGE_DIR

    @pytest.mark.parametrize(
        "relatif",
        [
            "ADAPTATEUR/interface.sh",
            "ADAPTATEUR/mock.sh",
            "ADAPTATEUR/OF.sh",
            "ADAPTATEUR/hotes.yaml",
            "01_EXEMPLE/ONERA_M6_CRUISE.yaml",
            "01_EXEMPLE/RUN_EXEMPLE.sh",
            "py.typed",
        ],
    )
    def test_fichier_livre_present(self, relatif):
        assert (paths.PACKAGE_DIR / relatif).is_file()

    def test_aucun_chemin_ne_remonte_hors_du_paquet(self):
        for chemin in (paths.ADAPTATEUR_DIR, paths.EXEMPLE_DIR, paths.hotes_file()):
            assert paths.PACKAGE_DIR in chemin.parents

    def test_la_version_du_module_suit_celle_du_paquet(self):
        """Deux endroits déclarent la version : ils ne doivent pas diverger."""
        pyproject = paths.PACKAGE_DIR.parents[1] / "pyproject.toml"
        if not pyproject.is_file():  # paquet installé : plus de sources à côté
            pytest.skip("hors arborescence source")
        declaree = next(
            ligne.split("=", 1)[1].strip().strip('"')
            for ligne in pyproject.read_text().splitlines()
            if ligne.startswith("version =")
        )
        assert cfd_perf.__version__ == declaree


class TestRepertoireUtilisateur:
    def test_la_variable_denvironnement_prime(self, monkeypatch, tmp_path):
        perso = tmp_path / "mes_adaptateurs"
        perso.mkdir()
        monkeypatch.setenv(paths.ENV_ADAPTATEUR_DIR, str(perso))
        assert paths.adaptateur_dir() == perso

    def test_hotes_retombe_sur_celui_livre(self, monkeypatch, tmp_path):
        monkeypatch.setenv(paths.ENV_ADAPTATEUR_DIR, str(tmp_path))
        assert paths.hotes_file() == paths.ADAPTATEUR_DIR / "hotes.yaml"

    def test_hotes_prend_celui_de_lutilisateur(self, monkeypatch, tmp_path):
        (tmp_path / "hotes.yaml").write_text("defaut: {cores_per_node: 4}\n")
        monkeypatch.setenv(paths.ENV_ADAPTATEUR_DIR, str(tmp_path))
        assert paths.hotes_file() == tmp_path / "hotes.yaml"


class TestResolutionAdaptateur:
    def test_par_nom_dans_le_paquet(self):
        assert BashAdapter("mock").path == paths.ADAPTATEUR_DIR / "mock.sh"

    def test_par_chemin_explicite(self, tmp_path):
        script = tmp_path / "mon_solveur.sh"
        script.write_text('source "$CFD_PERF_INTERFACE"\nadapt_nom() { echo "maison"; }\n')
        adapter = BashAdapter(str(script))
        assert adapter.path == script
        assert adapter.nom() == "maison"

    def test_un_adaptateur_maison_source_le_contrat_livre(self, tmp_path, monkeypatch):
        """Sans copier interface.sh : c'est ce que garantit CFD_PERF_INTERFACE."""
        perso = tmp_path / "adaptateurs"
        perso.mkdir()
        (perso / "maison.sh").write_text(
            'source "$CFD_PERF_INTERFACE"\n'
            'adapt_nom() { echo "maison"; }\n'
            "adapt_verifier_installation() { return 0; }\n"
        )
        monkeypatch.setenv(paths.ENV_ADAPTATEUR_DIR, str(perso))
        adapter = BashAdapter("maison")
        assert adapter.nom() == "maison"
        assert adapter.verifier_installation() is True

    def test_repli_sur_les_adaptateurs_livres(self, monkeypatch, tmp_path):
        monkeypatch.setenv(paths.ENV_ADAPTATEUR_DIR, str(tmp_path))
        assert BashAdapter("mock").path == paths.ADAPTATEUR_DIR / "mock.sh"

    def test_chemin_inexistant_explique_le_probleme(self, tmp_path):
        with pytest.raises(CaptureError, match="introuvable"):
            BashAdapter(str(tmp_path / "absent.sh"))

    def test_nom_inconnu_indique_la_variable_denvironnement(self):
        with pytest.raises(CaptureError, match=paths.ENV_ADAPTATEUR_DIR):
            BashAdapter("solveur_inexistant")
