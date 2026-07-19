"""Tests du script d'exemple ``01_EXEMPLE/enrichir_dataframe_cfd.py``.

Le script vit hors du package (dossier ``01_EXEMPLE/``) ; on l'ajoute au
``sys.path`` pour l'importer et tester la fonction de complétion.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "01_EXEMPLE"))

import enrichir_dataframe_cfd as ex  # noqa: E402

from cfd_atm.core import isa  # noqa: E402

PROFIL = RACINE / "01_EXEMPLE" / "profil_T_custom.yaml"

# Colonnes attendues en sortie (un sous-ensemble représentatif).
COLS_ATTENDUES = {
    "z_m",
    "H_m",
    "zp_m",
    "zrho_m",
    "z_ft",
    "H_ft",
    "zp_ft",
    "zrho_ft",
    "T_K",
    "rho_kgm3",
    "a_ms",
    "mach",
    "cas_ms",
    "eas_ms",
    "tas_ms",
    "cas_kt",
    "eas_kt",
    "tas_kt",
    "q_Pa",
    "coherent",
    "ecart_rel_max",
}


def _df_pression_mach() -> pd.DataFrame:
    zp_ft = [0.0, 25000.0, 41000.0]
    p = [float(isa.isa_pressure(z * ex.units.METRES_PER_FOOT)) for z in zp_ft]
    return pd.DataFrame({"p_statique": p, "mach": [0.2, 0.7, 0.84]})


class TestModeles:
    def test_toutes_colonnes_ajoutees(self) -> None:
        cols = ex.Colonnes(pression="p_statique", mach="mach")
        out = ex.enrichir_atmosphere(_df_pression_mach(), "ISA", cols, verbose=False)
        assert COLS_ATTENDUES.issubset(out.columns)

    def test_isa_zp_egale_h(self) -> None:
        cols = ex.Colonnes(pression="p_statique", mach="mach")
        out = ex.enrichir_atmosphere(_df_pression_mach(), "ISA", cols, verbose=False)
        # Sous ISA, altitude-pression et géopotentielle coïncident.
        assert np.allclose(out["zp_m"], out["H_m"], atol=1.0)

    def test_offset_temperature_referencee_zp(self) -> None:
        cols = ex.Colonnes(pression="p_statique", mach="mach")
        df = _df_pression_mach()
        out = ex.enrichir_atmosphere(df, "ISA+20", cols, verbose=False)
        # Convention aéro : T = T_ISA(zp) + 20 (référencée à l'altitude-pression).
        attendu = isa.isa_temperature(out["zp_m"].to_numpy()) + 20.0
        assert np.allclose(out["T_K"], attendu)
        # Air plus chaud -> la surface de pression est plus haute : H > zp (sauf sol).
        assert (out["H_m"].to_numpy()[1:] > out["zp_m"].to_numpy()[1:]).all()

    def test_custom_via_chemin_yaml(self) -> None:
        cols = ex.Colonnes(pression="p_statique", mach="mach")
        out = ex.enrichir_atmosphere(_df_pression_mach(), PROFIL, cols, verbose=False)
        assert COLS_ATTENDUES.issubset(out.columns)
        assert out["T_K"].iloc[0] == pytest.approx(295.0)  # T sol du profil custom


class TestEntreesVariees:
    def test_entree_par_altitude_geopotentielle_en_pieds(self) -> None:
        # On fournit H (ft) au lieu d'une pression : tout doit se reconstruire.
        df = pd.DataFrame({"H": [0.0, 30000.0], "cas_noeuds": [150.0, 280.0]})
        cols = ex.Colonnes(H="H", cas="cas_noeuds", unite_altitude="ft", unite_vitesse="kt")
        out = ex.enrichir_atmosphere(df, "ISA", cols, verbose=False)
        assert out["H_ft"].iloc[1] == pytest.approx(30000.0, abs=1.0)
        # La CAS reconstruite doit retomber sur l'entrée (aller-retour).
        assert out["cas_kt"].iloc[1] == pytest.approx(280.0, abs=0.5)

    def test_entree_par_altitude_densite(self) -> None:
        # zρ en entrée : résolu par bissection interne. Sous ISA les quatre
        # altitudes coïncident, donc zρ = 8000 doit redonner zp = H = 8000.
        df = pd.DataFrame({"zrho": [8000.0], "mach": [0.6]})
        cols = ex.Colonnes(zrho="zrho", mach="mach")
        out = ex.enrichir_atmosphere(df, "ISA", cols, verbose=False)
        assert out["zp_m"].iloc[0] == pytest.approx(8000.0, abs=1.0)
        assert out["H_m"].iloc[0] == pytest.approx(8000.0, abs=1.0)

    def test_vitesse_manquante_laisse_nan_et_signale(self) -> None:
        df = pd.DataFrame({"p_statique": [float(isa.isa_pressure(3000.0))]})
        cols = ex.Colonnes(pression="p_statique")
        out = ex.enrichir_atmosphere(df, "ISA", cols, verbose=False)
        assert np.isnan(out["mach"].iloc[0])
        assert np.isnan(out["tas_ms"].iloc[0])
        # Les altitudes, elles, sont bien remplies.
        assert out["zp_m"].iloc[0] == pytest.approx(3000.0, abs=1.0)
        diag = out.attrs["diagnostic"]
        assert diag.groupes_manquants  # non vide : le manque est signalé

    def test_aucune_verticale_leve_erreur(self) -> None:
        df = pd.DataFrame({"mach": [0.5]})
        cols = ex.Colonnes(mach="mach")
        with pytest.raises(ValueError, match="verticale"):
            ex.enrichir_atmosphere(df, "ISA", cols, verbose=False)


class TestCoherence:
    def test_redondance_coherente_ok(self) -> None:
        # pression ET zp cohérents : aucun écart, coherent partout.
        df = _df_pression_mach()
        df["zp_calc"] = [float(isa.geopotential_from_pressure(p)) for p in df["p_statique"]]
        cols = ex.Colonnes(pression="p_statique", zp="zp_calc", mach="mach")
        out = ex.enrichir_atmosphere(df, "ISA", cols, verbose=False)
        assert out["coherent"].all()
        assert out.attrs["diagnostic"].coherent

    def test_incoherence_detectee(self) -> None:
        df = _df_pression_mach()
        ref = ex.enrichir_atmosphere(
            df, "ISA", ex.Colonnes(pression="p_statique", mach="mach"), verbose=False
        )
        df = df.copy()
        df["tas_ms"] = ref["tas_ms"].to_numpy()
        df.loc[1, "tas_ms"] *= 1.20  # 20 % d'erreur sur une ligne
        cols = ex.Colonnes(pression="p_statique", mach="mach", tas="tas_ms")
        out = ex.enrichir_atmosphere(df, "ISA", cols, verbose=False)
        assert not out["coherent"].iloc[1]
        assert out["coherent"].iloc[0]
        assert out["coherent"].iloc[2]
        diag = out.attrs["diagnostic"]
        assert not diag.coherent
        assert any(v.grandeur == "tas" and not v.ok for v in diag.verifications)


class TestConstruireModele:
    def test_parsing_specs(self) -> None:
        assert ex.construire_modele("ISA").label == "ISA"
        assert ex.construire_modele("ISA+20").label == "ISA+20"
        assert ex.construire_modele("ISA-10").label == "ISA−10"
        assert ex.construire_modele(PROFIL).kind.value == "CUSTOM"
