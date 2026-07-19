#!/usr/bin/env python3
"""Exemple cfd-atm : **compléter** un DataFrame de résultats CFD.

Idée : vous décrivez les colonnes que **vous avez** (leur nom, leur unité) et le
modèle de température (ISA, ISA±ΔT ou un profil custom). Le script complète le
DataFrame avec **tout le reste** :

- les **quatre altitudes** : géométrique ``z``, géopotentielle ``H``,
  altitude-pression ``zp``, altitude-densité ``zρ`` (en m **et** en ft) ;
- les **conditions de l'air** : ``T``, ``ρ``, vitesse du son ``a`` ;
- les **quatre vitesses** : ``Mach``, ``CAS`` (Vc), ``EAS``, ``TAS`` (SI **et**
  nœuds), plus la pression dynamique ``q``.

Peu importe l'information fournie : **une** grandeur verticale (pression statique,
ou l'une des altitudes ``z/H/zp/zρ``) suffit à reconstruire toutes les autres, et
**une** vitesse (Mach, TAS, CAS ou EAS) suffit à reconstruire les trois autres.

Si vous fournissez des colonnes **redondantes** (par ex. pression *et* altitude,
ou Mach *et* TAS), le script les utilise comme **contrôle de cohérence** : il
recalcule la grandeur depuis la source « pilote » et signale tout écart. S'il
manque de quoi remplir un groupe, il le dit clairement.

Chaîne de calcul (cf. ``00_DOC/01_MODELE_ATMOSPHERE.md`` §4 et 6) :

    grandeur verticale ─▶ état atmosphère (z, H, zp, zρ, T, ρ, a)
    (p, T) + 1 vitesse ─▶ airspeeds() ─▶ Mach, CAS, EAS, TAS

Nécessite ``pandas`` (déjà tiré par le package ``plotting``).

    python3 01_EXEMPLE/enrichir_dataframe_cfd.py
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import yaml

from cfd_atm.core import isa
from cfd_atm.core.airspeed import airspeeds
from cfd_atm.core.altitudes import pressure_altitude
from cfd_atm.core.atmosphere import (
    AtmosphereModel,
    AtmosphereState,
    temperature_profile_from_table,
)
from cfd_atm.core.constants import H_TOP, R_AIR
from cfd_atm.report import units

ICI = Path(__file__).resolve().parent
PROFIL_DEFAUT = ICI / "profil_T_custom.yaml"

# ─────────────────────────────────────────────────────────────────────────────
# À RENSEIGNER : les colonnes de VOTRE DataFrame (mettre None si absente).
# ─────────────────────────────────────────────────────────────────────────────
COL_PRESSION = "p_statique"  # pression statique
COL_Z = None  # altitude géométrique
COL_H = None  # altitude géopotentielle
COL_ZP = None  # altitude-pression
COL_ZRHO = None  # altitude-densité
COL_MACH = "mach"
COL_TAS = None
COL_CAS = None
COL_EAS = None
UNITE_ALTITUDE: Literal["m", "ft"] = "m"
UNITE_VITESSE: Literal["SI", "kt"] = "SI"
UNITE_PRESSION: Literal["Pa", "hPa"] = "Pa"
MODELE = "custom"  # "ISA" | "ISA+15" | "ISA-10" | chemin d'un profil .yaml

# Grandeurs verticales, par ordre de priorité pour désigner la source « pilote ».
_PRIORITE_VERT = ("pression", "zp", "H", "z", "zrho")
# Vitesses, même logique.
_PRIORITE_VIT = ("mach", "cas", "tas", "eas")
# Plancher (unité SI) évitant la division par ~0 dans l'écart relatif.
_PLANCHER = {
    "pression": 1.0,
    "z": 10.0,
    "H": 10.0,
    "zp": 10.0,
    "zrho": 10.0,
    "mach": 5e-3,
    "cas": 0.5,
    "eas": 0.5,
    "tas": 0.5,
}


@dataclass(frozen=True)
class Colonnes:
    """Noms (dans VOTRE DataFrame) des colonnes disponibles ; ``None`` si absente."""

    pression: str | None = None
    z: str | None = None
    H: str | None = None
    zp: str | None = None
    zrho: str | None = None
    mach: str | None = None
    tas: str | None = None
    cas: str | None = None
    eas: str | None = None
    unite_altitude: Literal["m", "ft"] = "m"
    unite_vitesse: Literal["SI", "kt"] = "SI"
    unite_pression: Literal["Pa", "hPa"] = "Pa"

    def nom(self, grandeur: str) -> str | None:
        """Nom de colonne associé à une grandeur (``pression``, ``z``, ``mach``…)."""
        return getattr(self, grandeur)


@dataclass
class Verif:
    """Résultat d'un contrôle de cohérence d'une colonne redondante."""

    grandeur: str
    colonne: str
    ecart_rel_max: float
    ok: bool


@dataclass
class Diagnostic:
    """Bilan de l'enrichissement : sources utilisées, contrôles, manques."""

    pilote_vertical: str | None = None
    pilote_vitesse: str | None = None
    sources: dict[str, str] = field(default_factory=dict)
    verifications: list[Verif] = field(default_factory=list)
    groupes_manquants: list[str] = field(default_factory=list)
    n_lignes: int = 0
    n_incoherentes: int = 0

    @property
    def coherent(self) -> bool:
        return self.n_incoherentes == 0 and all(v.ok for v in self.verifications)


# ─────────────────────────────────────────────────────────────────────────────
# Construction du modèle
# ─────────────────────────────────────────────────────────────────────────────
def charger_modele_custom(profil_yaml: str | Path) -> AtmosphereModel:
    """Construit un ``AtmosphereModel`` custom depuis un YAML ``{altitude_m, temperature_K}``."""
    data = yaml.safe_load(Path(profil_yaml).read_text(encoding="utf-8"))
    rows = data["profil"]
    h = [float(r["altitude_m"]) for r in rows]
    t = [float(r["temperature_K"]) for r in rows]
    label = str(data.get("nom", "custom")).split(" —")[0]
    return AtmosphereModel.custom(temperature_profile_from_table(h, t), label=label)


def construire_modele(spec: str | Path | AtmosphereModel) -> AtmosphereModel:
    """Interprète ``spec`` : ``"ISA"``, ``"ISA+15"``, ``"ISA-10"`` ou un chemin YAML.

    Un ``AtmosphereModel`` déjà construit est renvoyé tel quel ; un ``Path`` est
    traité comme un profil custom.
    """
    if isinstance(spec, AtmosphereModel):
        return spec
    if isinstance(spec, Path):
        return charger_modele_custom(spec)
    texte = spec.strip()
    if texte.upper() == "ISA":
        return AtmosphereModel.isa()
    if texte.upper().startswith("ISA"):
        try:
            return AtmosphereModel.isa_offset(float(texte[3:]))
        except ValueError:
            pass  # pas un "ISA±ΔT" : on tente un chemin de fichier
    return charger_modele_custom(texte)


# ─────────────────────────────────────────────────────────────────────────────
# Résolveurs (une grandeur -> l'état / les vitesses complètes)
# ─────────────────────────────────────────────────────────────────────────────
def _etat_depuis_zrho(model: AtmosphereModel, zrho: float) -> AtmosphereState:
    """État à partir d'une altitude-densité : on retrouve ``H`` par bissection."""
    rho_cible = float(isa.isa_density(zrho))
    lo, hi = 0.0, H_TOP
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        rho_mid = float(model.pressure_geopotential(mid)) / (R_AIR * float(model.temperature(mid)))
        if rho_mid > rho_cible:  # densité décroît avec l'altitude
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-4:
            break
    return model.state_from_geopotential(0.5 * (lo + hi))


def resoudre_etat(model: AtmosphereModel, valeurs: dict[str, float]) -> tuple[AtmosphereState, str]:
    """Résout l'état atmosphérique depuis la grandeur verticale prioritaire disponible."""
    for grandeur in _PRIORITE_VERT:
        if grandeur not in valeurs:
            continue
        v = valeurs[grandeur]
        if grandeur == "pression":
            return model.state_from_pressure_altitude(float(pressure_altitude(v))), grandeur
        if grandeur == "zp":
            return model.state_from_pressure_altitude(v), grandeur
        if grandeur == "H":
            return model.state_from_geopotential(v), grandeur
        if grandeur == "z":
            return model.state_from_geometric(v), grandeur
        return _etat_depuis_zrho(model, v), grandeur
    raise ValueError(
        "Aucune information verticale : fournissez une pression statique ou une "
        "altitude (z, H, zp ou zρ)."
    )


def resoudre_vitesses(
    p: float, t: float, valeurs: dict[str, float]
) -> tuple[object | None, str | None]:
    """Reconstruit toutes les vitesses depuis la vitesse prioritaire disponible."""
    for grandeur in _PRIORITE_VIT:
        if grandeur in valeurs:
            return airspeeds(p, t, **{grandeur: valeurs[grandeur]}), grandeur
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Le compléteur
# ─────────────────────────────────────────────────────────────────────────────
def _series_si(df: pd.DataFrame, colonnes: Colonnes) -> dict[str, np.ndarray]:
    """Extrait et convertit en SI les colonnes présentes -> {grandeur: tableau}."""
    fa = units.METRES_PER_FOOT if colonnes.unite_altitude == "ft" else 1.0
    fv = units.MPS_PER_KNOT if colonnes.unite_vitesse == "kt" else 1.0
    fp = 100.0 if colonnes.unite_pression == "hPa" else 1.0
    facteurs = {
        "pression": fp,
        "z": fa,
        "H": fa,
        "zp": fa,
        "zrho": fa,
        "mach": 1.0,
        "cas": fv,
        "eas": fv,
        "tas": fv,
    }
    out: dict[str, np.ndarray] = {}
    for grandeur, facteur in facteurs.items():
        col = colonnes.nom(grandeur)
        if col is not None:
            if col not in df.columns:
                raise KeyError(f"Colonne '{col}' (pour {grandeur}) absente du DataFrame.")
            out[grandeur] = df[col].to_numpy(dtype=float) * facteur
    return out


def _err_rel(donne: float, recon: float, plancher: float) -> float:
    return abs(donne - recon) / max(abs(recon), plancher)


def enrichir_atmosphere(
    df: pd.DataFrame,
    modele: str | Path | AtmosphereModel = MODELE,
    colonnes: Colonnes | None = None,
    *,
    tolerance_rel: float = 2e-3,
    verbose: bool = True,
) -> pd.DataFrame:
    """Complète ``df`` : ajoute les 4 altitudes, les conditions et les 4 vitesses.

    Parameters
    ----------
    df:
        DataFrame d'entrée (une ligne par point de vol).
    modele:
        ``"ISA"``, ``"ISA+15"``, ``"ISA-10"``, un chemin de profil ``.yaml``, ou un
        ``AtmosphereModel`` déjà construit.
    colonnes:
        Description des colonnes disponibles (voir :class:`Colonnes`). Par défaut,
        elle est bâtie depuis les constantes ``COL_*`` en tête de fichier.
    tolerance_rel:
        Écart relatif au-delà duquel une colonne redondante est jugée incohérente.
    verbose:
        Affiche le bilan (sources, contrôles, manques).

    Returns
    -------
    Une **copie** de ``df`` avec les colonnes ajoutées, plus ``coherent`` (bool) et
    ``ecart_rel_max`` (float) par ligne. Le :class:`Diagnostic` complet est aussi
    rangé dans ``resultat.attrs["diagnostic"]``.

    Raises
    ------
    ValueError:
        Si aucune information verticale n'est fournie (rien n'est reconstructible).
    """
    if colonnes is None:
        colonnes = _colonnes_depuis_constantes()
    model = construire_modele(modele)
    series = _series_si(df, colonnes)

    verticales = {g: series[g] for g in _PRIORITE_VERT if g in series}
    vitesses = {g: series[g] for g in _PRIORITE_VIT if g in series}
    if not verticales:
        raise ValueError(
            "Impossible de compléter : aucune colonne verticale (pression ou "
            "altitude z/H/zp/zρ) n'a été déclarée."
        )

    n = len(df)
    diag = Diagnostic(n_lignes=n)
    diag.sources = {g: str(colonnes.nom(g)) for g in (*verticales, *vitesses)}
    if not vitesses:
        diag.groupes_manquants.append("vitesses (Mach, CAS, EAS, TAS) — aucune vitesse fournie")

    noms_sortie = (
        "z_m",
        "H_m",
        "zp_m",
        "zrho_m",
        "T_K",
        "rho_kgm3",
        "a_ms",
        "mach",
        "cas_ms",
        "eas_ms",
        "tas_ms",
        "q_Pa",
    )
    cols: dict[str, list[float]] = {nom: [] for nom in noms_sortie}
    coherent_col: list[bool] = []
    ecart_max_col: list[float] = []
    err_par_grandeur: dict[str, list[float]] = defaultdict(list)

    for i in range(n):
        vals_v = {g: float(arr[i]) for g, arr in verticales.items()}
        st, pilote_v = resoudre_etat(model, vals_v)
        diag.pilote_vertical = pilote_v

        vals_s = {g: float(arr[i]) for g, arr in vitesses.items()}
        spd, pilote_s = resoudre_vitesses(st.p, st.t, vals_s)
        diag.pilote_vitesse = pilote_s

        recon_v = {"pression": st.p, "zp": st.zp, "H": st.h, "z": st.z, "zrho": st.zrho}
        errs: list[float] = []
        for g, donne in vals_v.items():
            if g == pilote_v:
                continue
            e = _err_rel(donne, recon_v[g], _PLANCHER[g])
            err_par_grandeur[g].append(e)
            errs.append(e)

        if spd is not None:
            recon_s = {"mach": spd.mach, "cas": spd.cas, "eas": spd.eas, "tas": spd.tas}
            for g, donne in vals_s.items():
                if g == pilote_s:
                    continue
                e = _err_rel(donne, recon_s[g], _PLANCHER[g])
                err_par_grandeur[g].append(e)
                errs.append(e)

        cols["z_m"].append(st.z)
        cols["H_m"].append(st.h)
        cols["zp_m"].append(st.zp)
        cols["zrho_m"].append(st.zrho)
        cols["T_K"].append(st.t)
        cols["rho_kgm3"].append(st.rho)
        cols["a_ms"].append(st.a)
        cols["mach"].append(spd.mach if spd is not None else np.nan)
        cols["cas_ms"].append(spd.cas if spd is not None else np.nan)
        cols["eas_ms"].append(spd.eas if spd is not None else np.nan)
        cols["tas_ms"].append(spd.tas if spd is not None else np.nan)
        cols["q_Pa"].append(spd.q if spd is not None else np.nan)

        ecart_max = max(errs) if errs else 0.0
        ecart_max_col.append(ecart_max)
        coherent_col.append(ecart_max <= tolerance_rel)

    out = df.copy()
    for nom, valeurs in cols.items():
        out[nom] = valeurs
    for base in ("z", "H", "zp", "zrho"):
        out[f"{base}_ft"] = out[f"{base}_m"] * units.FEET_PER_METRE
    for base in ("cas", "eas", "tas"):
        out[f"{base}_kt"] = out[f"{base}_ms"] * units.KNOTS_PER_MPS
    out["coherent"] = coherent_col
    out["ecart_rel_max"] = ecart_max_col

    for g, liste in err_par_grandeur.items():
        emax = max(liste)
        diag.verifications.append(Verif(g, str(colonnes.nom(g)), emax, emax <= tolerance_rel))
    diag.n_incoherentes = int(sum(not c for c in coherent_col))
    out.attrs["diagnostic"] = diag

    if verbose:
        _afficher_diagnostic(diag, model, tolerance_rel)
    return out


def _colonnes_depuis_constantes() -> Colonnes:
    """Construit un :class:`Colonnes` depuis les constantes ``COL_*`` du fichier."""
    return Colonnes(
        pression=COL_PRESSION,
        z=COL_Z,
        H=COL_H,
        zp=COL_ZP,
        zrho=COL_ZRHO,
        mach=COL_MACH,
        tas=COL_TAS,
        cas=COL_CAS,
        eas=COL_EAS,
        unite_altitude=UNITE_ALTITUDE,
        unite_vitesse=UNITE_VITESSE,
        unite_pression=UNITE_PRESSION,
    )


def _afficher_diagnostic(diag: Diagnostic, model: AtmosphereModel, tol: float) -> None:
    print(f"── Bilan de l'enrichissement ({diag.n_lignes} lignes) ──")
    print(f"  Modèle          : {model.label}")
    print(
        f"  Pilote vertical : {diag.pilote_vertical}  (colonne '{diag.sources.get(diag.pilote_vertical)}')"
    )
    if diag.pilote_vitesse:
        print(
            f"  Pilote vitesse  : {diag.pilote_vitesse}  (colonne '{diag.sources.get(diag.pilote_vitesse)}')"
        )
    for groupe in diag.groupes_manquants:
        print(f"  ⚠ Manque        : {groupe} → colonnes laissées à NaN")
    if diag.verifications:
        print(f"  Contrôles de cohérence (tolérance {tol:.1%}) :")
        for v in diag.verifications:
            marque = "✓" if v.ok else "✗"
            print(
                f"    {marque} {v.grandeur:9s} (col '{v.colonne}') : écart max {v.ecart_rel_max:.2%}"
            )
    else:
        print("  Contrôles       : aucune colonne redondante à recouper.")
    if diag.n_incoherentes:
        print(f"  ✗ {diag.n_incoherentes} ligne(s) incohérente(s) (voir colonne 'coherent').")
    else:
        print("  ✓ Cohérence globale : OK.")


# ─────────────────────────────────────────────────────────────────────────────
# Démonstration
# ─────────────────────────────────────────────────────────────────────────────
def _demo_dataframe() -> pd.DataFrame:
    """Petit DataFrame « comme sorti d'une simulation » : pression statique + Mach."""
    zp_ft = [0.0, 10000.0, 25000.0, 35000.0, 41000.0]
    mach = [0.20, 0.45, 0.70, 0.80, 0.84]
    p_statique = [float(isa.isa_pressure(z * units.METRES_PER_FOOT)) for z in zp_ft]
    return pd.DataFrame(
        {"point": [f"P{i}" for i in range(1, 6)], "p_statique": p_statique, "mach": mach}
    )


def main() -> None:
    df = _demo_dataframe()
    print("DataFrame d'entrée (pression statique + Mach) :")
    print(df.to_string(index=False, float_format=lambda x: f"{x:.4g}"))

    cols = Colonnes(pression="p_statique", mach="mach")

    for modele in ("ISA", "ISA+20", "custom"):
        spec = PROFIL_DEFAUT if modele == "custom" else modele
        print(f"\n========== Modèle {modele} ==========")
        enrichi = enrichir_atmosphere(df, spec, cols)
        apercu = enrichi[["point", "zp_ft", "H_ft", "T_K", "cas_kt", "tas_kt"]]
        print(apercu.to_string(index=False, float_format=lambda x: f"{x:.1f}"))

    # --- Démo du contrôle de cohérence : on ajoute une TAS, dont une fausse. ---
    print("\n========== Contrôle de cohérence (Mach + TAS) ==========")
    ref = enrichir_atmosphere(df, PROFIL_DEFAUT, cols, verbose=False)
    df_tas = df.copy()
    df_tas["tas_ms"] = ref["tas_ms"].to_numpy()
    df_tas.loc[2, "tas_ms"] *= 1.15  # 15 % d'erreur sur P3 (incohérence volontaire)
    cols_tas = Colonnes(pression="p_statique", mach="mach", tas="tas_ms")
    verifie = enrichir_atmosphere(df_tas, PROFIL_DEFAUT, cols_tas)
    print(
        verifie[["point", "mach", "tas_ms", "tas_kt", "coherent", "ecart_rel_max"]].to_string(
            index=False, float_format=lambda x: f"{x:.3g}"
        )
    )

    sortie = ICI / "SORTIE" / "df_enrichi.csv"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    enrichir_atmosphere(df, PROFIL_DEFAUT, cols, verbose=False).to_csv(sortie, index=False)
    print(f"\nDataFrame complet écrit dans {sortie}")


if __name__ == "__main__":
    main()
