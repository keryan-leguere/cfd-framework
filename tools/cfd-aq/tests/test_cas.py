"""Reading and refusing YAML cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from cfd_aq.core.atmosphere import HAS_CFD_ATM
from cfd_aq.core.marches import TypeAsperite
from cfd_aq.data.cas import CasError, charger_cas
from cfd_aq.paths import EXEMPLE_DIR

MINIMAL = """
ecoulement:
  altitude: 11000
  mach: 0.82
couche_limite:
  distance_bord_attaque: 10.0
asperites:
  - nom: "Marche"
    type: montante
    hauteur: 0.001
    envergure: 2.0
"""


def _ecrire(tmp_path: Path, texte: str) -> Path:
    chemin = tmp_path / "cas.yaml"
    chemin.write_text(texte, encoding="utf-8")
    return chemin


def test_cas_minimal(tmp_path: Path) -> None:
    cas = charger_cas(_ecrire(tmp_path, MINIMAL))
    assert cas.etat.mach == 0.82
    assert len(cas.asperites) == 1
    nom, asperite = cas.asperites[0]
    assert nom == "Marche"
    assert asperite.type_asperite is TypeAsperite.MONTANTE
    assert cas.surface_reference is None
    assert cas.amplification == 1.0


def test_exemple_livre_est_valide() -> None:
    """The example shipped as package data must load — it is the first thing a user runs."""
    cas = charger_cas(EXEMPLE_DIR / "CAS_VOILURE.yaml")
    assert len(cas.asperites) == 5
    assert cas.surface_reference == pytest.approx(122.6)
    types = {a.type_asperite for _, a in cas.asperites}
    assert types == {TypeAsperite.MONTANTE, TypeAsperite.DESCENDANTE, TypeAsperite.ARETE}


def test_conditions_statiques_explicites(tmp_path: Path) -> None:
    texte = MINIMAL.replace("  altitude: 11000", "  temperature: 220.0\n  pression: 25000.0")
    cas = charger_cas(_ecrire(tmp_path, texte))
    assert cas.etat.temperature == 220.0
    assert cas.etat.pression == 25000.0


def test_altitude_et_statiques_ensemble_refusees(tmp_path: Path) -> None:
    texte = MINIMAL.replace("  mach: 0.82", "  mach: 0.82\n  temperature: 220.0")
    with pytest.raises(CasError, match="pas les deux"):
        charger_cas(_ecrire(tmp_path, texte))


@pytest.mark.parametrize("cle", ("cf: 0.0016", "cisaillement_paroi: 16.5"))
def test_couche_limite_par_cf_ou_tau(tmp_path: Path, cle: str) -> None:
    texte = MINIMAL.replace("  distance_bord_attaque: 10.0", f"  {cle}")
    cas = charger_cas(_ecrire(tmp_path, texte))
    assert cas.couche_limite.cf > 0.0


def test_deux_descriptions_de_couche_limite_refusees(tmp_path: Path) -> None:
    texte = MINIMAL.replace(
        "  distance_bord_attaque: 10.0", "  distance_bord_attaque: 10.0\n  cf: 0.0016"
    )
    with pytest.raises(CasError, match="exactement une"):
        charger_cas(_ecrire(tmp_path, texte))


def test_aucune_description_de_couche_limite_refusee(tmp_path: Path) -> None:
    texte = MINIMAL.replace("  distance_bord_attaque: 10.0", "  temperature_paroi: 250.0")
    with pytest.raises(CasError, match="exactement une"):
        charger_cas(_ecrire(tmp_path, texte))


def test_cle_inconnue_refusee_en_nommant_les_admises(tmp_path: Path) -> None:
    """A mistyped key must not silently keep its default — it changes the answer."""
    texte = MINIMAL.replace("    hauteur: 0.001", "    hauteur: 0.001\n    rayon: 0.3")
    with pytest.raises(CasError) as erreur:
        charger_cas(_ecrire(tmp_path, texte))
    assert "rayon" in str(erreur.value)
    assert "rayon_sur_h" in str(erreur.value)


def test_cle_racine_inconnue_refusee(tmp_path: Path) -> None:
    with pytest.raises(CasError, match="surface_ref"):
        charger_cas(_ecrire(tmp_path, MINIMAL + "\nsurface_ref: 100.0\n"))


def test_type_inconnu_refuse(tmp_path: Path) -> None:
    texte = MINIMAL.replace("    type: montante", "    type: bosse")
    with pytest.raises(CasError) as erreur:
        charger_cas(_ecrire(tmp_path, texte))
    assert "bosse" in str(erreur.value)
    assert "montante" in str(erreur.value)


def test_cle_obligatoire_absente_refusee(tmp_path: Path) -> None:
    texte = MINIMAL.replace("    envergure: 2.0\n", "")
    with pytest.raises(CasError, match="envergure"):
        charger_cas(_ecrire(tmp_path, texte))


def test_valeur_non_numerique_refusee(tmp_path: Path) -> None:
    texte = MINIMAL.replace("    hauteur: 0.001", "    hauteur: un millimètre")
    with pytest.raises(CasError, match="hauteur"):
        charger_cas(_ecrire(tmp_path, texte))


def test_geometrie_non_physique_remontee_en_cas_error(tmp_path: Path) -> None:
    texte = MINIMAL.replace("    hauteur: 0.001", "    hauteur: -0.001")
    with pytest.raises(CasError, match="hauteur"):
        charger_cas(_ecrire(tmp_path, texte))


def test_liste_d_asperites_vide_refusee(tmp_path: Path) -> None:
    texte = MINIMAL.split("asperites:")[0] + "asperites: []\n"
    with pytest.raises(CasError, match="liste non vide"):
        charger_cas(_ecrire(tmp_path, texte))


def test_bloc_absent_refuse(tmp_path: Path) -> None:
    texte = MINIMAL.split("couche_limite:")[0] + MINIMAL.split("asperites:")[1]
    chemin = tmp_path / "cas.yaml"
    chemin.write_text("ecoulement:\n  altitude: 11000\n  mach: 0.8\n", encoding="utf-8")
    with pytest.raises(CasError, match="couche_limite"):
        charger_cas(chemin)
    assert texte  # garde l'intention lisible


def test_yaml_invalide_refuse(tmp_path: Path) -> None:
    with pytest.raises(CasError, match="YAML invalide"):
        charger_cas(_ecrire(tmp_path, "ecoulement: [unclosed\n"))


def test_fichier_absent_refuse(tmp_path: Path) -> None:
    with pytest.raises(CasError, match="impossible de lire"):
        charger_cas(tmp_path / "pas_la.yaml")


def test_racine_non_dictionnaire_refusee(tmp_path: Path) -> None:
    with pytest.raises(CasError, match="dictionnaire YAML"):
        charger_cas(_ecrire(tmp_path, "- un\n- deux\n"))


@pytest.mark.skipif(not HAS_CFD_ATM, reason="cfd-atm n'est pas installé")
def test_vitesse_conventionnelle(tmp_path: Path) -> None:
    """Vc instead of Mach — the conversion goes through cfd-atm."""
    texte = MINIMAL.replace("  mach: 0.82", "  vitesse_conventionnelle: 140.437")
    cas = charger_cas(_ecrire(tmp_path, texte))
    assert cas.etat.mach == pytest.approx(0.82, abs=1e-4)


@pytest.mark.skipif(not HAS_CFD_ATM, reason="cfd-atm n'est pas installé")
def test_journee_chaude_et_altitude_pression(tmp_path: Path) -> None:
    texte = MINIMAL.replace(
        "  altitude: 11000", "  altitude: 11000\n  delta_isa: 15\n  type_altitude: pression"
    )
    cas = charger_cas(_ecrire(tmp_path, texte))
    assert cas.etat.temperature == pytest.approx(216.65 + 15.0, abs=1e-6)


def test_sans_vitesse_refuse(tmp_path: Path) -> None:
    texte = MINIMAL.replace("  mach: 0.82\n", "")
    with pytest.raises(CasError, match="exactement une vitesse"):
        charger_cas(_ecrire(tmp_path, texte))


def test_deux_vitesses_refusees(tmp_path: Path) -> None:
    texte = MINIMAL.replace("  mach: 0.82", "  mach: 0.82\n  vitesse_vraie: 240.0")
    with pytest.raises(CasError, match="exactement une vitesse"):
        charger_cas(_ecrire(tmp_path, texte))


def test_delta_isa_avec_conditions_imposees_refuse(tmp_path: Path) -> None:
    """ΔT has no meaning once T and p are given outright."""
    texte = MINIMAL.replace(
        "  altitude: 11000", "  temperature: 220.0\n  pression: 25000.0\n  delta_isa: 15"
    )
    with pytest.raises(CasError, match="delta_isa"):
        charger_cas(_ecrire(tmp_path, texte))
