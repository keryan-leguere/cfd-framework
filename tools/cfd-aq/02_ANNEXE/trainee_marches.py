#!/usr/bin/env python3
"""
Traînée d'une marche ou d'une arête sur une surface aérodynamique.
==================================================================

Script autonome : tout est dans ce fichier. Aucune dépendance au paquet
cfd-aq. Seuls numpy est requis ; cfd-atm et cfd-plot, s'ils sont installés,
sont utilisés automatiquement pour l'atmosphère et pour le style des figures.

    python3 trainee_marches.py              # exemple de bout en bout
    python3 trainee_marches.py --figures .  # + les planches de corrélation

Méthode
-------
AGARD-AG-264, « Aircraft Excrescence Drag », A. D. Young & J. H. Paterson,
AGARD/NATO, juillet 1981, § 4.3. Les corrélations viennent des essais RAE
(Gaudet & Winter) et ARA (Pallister).

Le principe tient en deux grandeurs. Une aspérité assez petite ne « voit »
pas la couche limite entière : elle ne voit que la région interne, celle où
le profil de vitesse ne dépend que du frottement pariétal et de la viscosité.
Sa traînée se corrèle donc sur un nombre de Reynolds de rugosité

    h+ = u_tau * h / nu_w        avec  u_tau = sqrt(tau_w / rho_w)

et le rapport de traînée CDe/Cfe se range alors sur des droites en log(h+),
une par nombre de Mach :

    CDe/Cfe = A * log10(h+) + B

La pression dynamique se simplifie entre CDe = dD/(q_e*f_e) et Cfe = tau_w/q_e,
d'où la relation de travail :

    dD = (CDe/Cfe) * f_forme * tau_w * f_e        f_e = h * b

Domaine de validité
-------------------
h+ de 25 a 2000 (>= 55 pour la marche montante subsonique), h/delta <= 0.03,
M de 0.2 a 1.4 (montante) ou 2.8 (descendante, arete), couche limite
turbulente bidimensionnelle a gradient de pression nul.

Provenance des nombres
----------------------
« PUBLIE »  : coefficients imprimes dans le rapport (tables sous eq. 4(37),
              p. 91 ; eq. 4(34), p. 87). Exacts.
« NUMERISE »: lus sur les figures scannees du rapport, par traitement
              d'image. L'incertitude indiquee est celle de la numerisation
              seule ; la dispersion experimentale s'y ajoute.

Licence : MIT. AGARD-AG-264 est en diffusion publique.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

__all__ = [
    "Asperite",
    "CoucheLimite",
    "EtatLocal",
    "Resultat",
    "calculer_trainee",
    "facteur_amplification_nash_bradshaw",
    "ratio_arete",
    "ratio_marche_descendante",
    "ratio_marche_montante",
]

# ===========================================================================
#  1. LES DONNEES D'AGARD-AG-264
# ===========================================================================

#: Plage de h+ couverte par les essais.
#:
#: Les axes des figures commencent a 10, mais les ajustements droits ne
#: survivent pas jusque-la : la droite de l'arete carree a M = 0.2 (A = 150,
#: B = -190, valeurs PUBLIEES) s'annule a h+ = 18.5, et celle de la marche
#: montante a M = 0.2 a h+ = 20.7. 25 est la borne au-dessus de laquelle
#: toutes les droites restent positives.
H_PLUS_MIN = 25.0
H_PLUS_MAX = 2000.0

#: Les tiretes subsoniques de la Figure 4.23 ne sont pas traces sous h+ ~ 55.
#: Plus bas, leur forte pente les fait passer sous la marche descendante :
#: artefact d'extrapolation, pas une mesure.
H_PLUS_MIN_MONTANTE_SUBSONIQUE = 55.0

#: Immersion maximale testee, h/delta (§ 4.3.1.1.1).
H_SUR_DELTA_MAX = 0.03

# --- Marche montante -------------------------------------------------------

#: Figure 4.23 : CDe/Cfe = A*log10(h+) + B. NUMERISE, +/- 3.
#: Une seule droite supersonique vaut pour tout M >= 1.4 (§ 4.3.1.1.1).
MARCHE_MONTANTE: dict[float, tuple[float, float]] = {
    0.2: (60.0, -79.0),
    0.8: (61.5, -74.0),
    1.4: (76.8, -59.5),
}

#: Figure 4.25 : facteur d'interpolation transsonique PC1, eq. 4(27).
#: NUMERISE depuis les symboles de mesure, +/- 0.01.
PC1_MACH = (0.800, 0.850, 0.900, 0.950, 1.000, 1.050, 1.100, 1.150, 1.200, 1.300, 1.400)
PC1_VALEUR = (0.000, 0.022, 0.052, 0.094, 0.193, 0.399, 0.567, 0.615, 0.720, 0.871, 1.000)

#: Figure 4.26(a) : E(r/h), reduction due a l'arrondi de l'arete amont,
#: eq. 4(28). NUMERISE, +/- 0.03.
ARRONDI_MONTANTE_X = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8)
ARRONDI_MONTANTE: dict[float, tuple[float, ...]] = {
    0.2: (0.0, 0.130, 0.240, 0.343, 0.461, 0.595, 0.656, 0.724, 0.760),
    0.8: (0.0, 0.185, 0.345, 0.490, 0.611, 0.703, 0.759, 0.794, 0.805),
    1.4: (0.0, 0.107, 0.187, 0.248, 0.282, 0.303, 0.306, 0.313, 0.315),
    2.0: (0.0, 0.005, 0.012, 0.032, 0.055, 0.081, 0.106, 0.127, 0.138),
}

#: Figure 4.26(b) : E(theta), reduction due au chanfrein amont, eq. 4(29).
#: NUMERISE, +/- 0.04. theta = 90 deg : marche vive (E = 0).
CHANFREIN_MONTANTE_X = (0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0)
CHANFREIN_MONTANTE: dict[float, tuple[float, ...]] = {
    0.2: (1.0, 0.905, 0.825, 0.745, 0.660, 0.570, 0.480, 0.390, 0.255, 0.0),
    0.8: (1.0, 0.890, 0.796, 0.712, 0.581, 0.456, 0.327, 0.229, 0.135, 0.0),
    1.4: (1.0, 0.600, 0.425, 0.305, 0.215, 0.152, 0.105, 0.068, 0.035, 0.0),
    2.0: (1.0, 0.450, 0.265, 0.178, 0.128, 0.090, 0.064, 0.044, 0.026, 0.0),
}

# --- Marche descendante ----------------------------------------------------

#: Figure 4.28 : CDe/Cfe = A*log10(h+) + B. NUMERISE, +/- 4.
#: La trainee culmine vers M = 1.4 puis redescend (§ 4.3.1.2.1).
MARCHE_DESCENDANTE: dict[float, tuple[float, float]] = {
    0.2: (16.0, -7.5),
    0.8: (20.0, -13.0),
    1.4: (49.0, -21.2),
    1.7: (52.0, -35.2),
    2.0: (44.0, -19.2),
    2.2: (33.0, 4.8),
    2.8: (36.0, -15.8),
}

#: Figure 4.30 : PC2, eq. 4(32). NUMERISE depuis les symboles, +/- 0.02.
#: PC2 depasse 1 : la trainee culmine vers M = 1.15, au-dessus de sa valeur
#: a M = 1.4 (Figure 4.29). Ce n'est pas une extrapolation, c'est la mesure.
PC2_MACH = (0.800, 0.900, 0.950, 1.000, 1.050, 1.100, 1.150, 1.200, 1.300, 1.400)
PC2_VALEUR = (0.000, 0.065, 0.110, 0.400, 1.030, 1.210, 1.275, 1.260, 1.140, 1.000)

#: Eq. 4(34), PUBLIE : arrondir l'arete AVAL AUGMENTE la trainee,
#: CDe/Cfe = [1 + 1.43*(r/h)] * (CDe/Cfe)_{r=0}. Relation unique, sans Mach.
COEFFICIENT_ARRONDI_DESCENDANTE = 1.43

#: Figure 4.33 : G(theta), eq. 4(33). NUMERISE, +/- 0.05 — la table la moins
#: sure du lot : sept courbes serrees dans un cadre de quatre centimetres.
#: Le texte du § 4.3.1.2.2 y est plus net que le trace et la table le suit :
#: pas d'effet notable jusqu'a 45 deg, legere AUGMENTATION de trainee entre
#: 12 et 45 deg au transsonique et au supersonique, chute franche sous 12 deg.
CHANFREIN_DESCENDANTE_X = (0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 90.0)
CHANFREIN_DESCENDANTE: dict[float, tuple[float, ...]] = {
    0.2: (1.0, 0.780, 0.600, 0.460, 0.355, 0.257, 0.164, 0.082, 0.010, 0.0, 0.0),
    0.8: (1.0, 0.920, 0.860, 0.790, 0.690, 0.555, 0.415, 0.275, 0.135, 0.0, 0.0),
    1.2: (1.0, 0.450, 0.000, -0.190, -0.220, -0.210, -0.180, -0.130, -0.070, 0.0, 0.0),
    1.4: (1.0, 0.520, 0.100, -0.130, -0.170, -0.165, -0.140, -0.100, -0.050, 0.0, 0.0),
    1.7: (1.0, 0.580, 0.220, -0.030, -0.077, -0.075, -0.060, -0.040, -0.020, 0.0, 0.0),
    2.0: (1.0, 0.600, 0.250, 0.090, 0.051, 0.046, 0.046, 0.046, 0.046, 0.020, 0.0),
}

# --- Arete -----------------------------------------------------------------

#: Eq. 4(37), PUBLIE : arete carree (t = h), table imprimee page 91.
ARETE_CARREE: dict[float, tuple[float, float]] = {
    0.2: (150.0, -190.0),
    0.8: (150.0, -160.0),
    1.4: (160.0, -125.0),
    2.2: (110.0, -42.0),
    2.8: (100.0, -44.0),
}

#: Eq. 4(37), PUBLIE : arete rectangulaire t = 2h, meme page.
#: Cette table croise ARETE_CARREE vers h+ ~ 1000 — plus trainante en
#: dessous, moins au-dessus — ce que decrit le § 4.3.2.1. Le produit
#: generique T(2) * (arete carree) de l'eq. 4(39), lui, reste 21 % sous
#: l'arete carree a tout h+ : les deux routes different de 80 % a h+ = 100.
#: Contradiction du rapport, pas de la transcription (voir ratio_arete).
ARETE_RECTANGULAIRE_2H: dict[float, tuple[float, float]] = {
    0.2: (105.0, -55.0),
    0.8: (115.0, -60.0),
    1.4: (100.0, 8.0),
    1.7: (100.0, 20.0),
}

#: Figure 4.38 : PC3, eq. 4(38). NUMERISE en continu, +/- 0.02.
#: PC3 culmine a 1.58 vers M = 1.03 : pic transsonique 50 % au-dessus du
#: niveau subsonique.
PC3_MACH = (
    0.800,
    0.825,
    0.850,
    0.875,
    0.900,
    0.925,
    0.950,
    0.975,
    1.000,
    1.025,
    1.050,
    1.075,
    1.100,
    1.150,
    1.200,
    1.250,
    1.300,
    1.350,
    1.400,
)
PC3_VALEUR = (
    0.000,
    0.102,
    0.197,
    0.308,
    0.456,
    0.642,
    0.927,
    1.303,
    1.520,
    1.580,
    1.572,
    1.500,
    1.428,
    1.330,
    1.236,
    1.152,
    1.095,
    1.050,
    1.000,
)

#: Figure 4.40 : T(t/h), eq. 4(39). NUMERISE en continu, +/- 0.02.
#: T(1) = 1 par definition ; maximum ~ 1.07 vers t/h = 0.25 (une arete mince
#: traine un peu plus) ; plateau a 0.58 au-dela de t/h ~ 4, ou l'ecoulement
#: recolle entre les deux faces.
EPAISSEUR_ARETE_X = (
    0.000,
    0.125,
    0.250,
    0.375,
    0.500,
    0.625,
    0.750,
    0.875,
    1.000,
    1.125,
    1.250,
    1.375,
    1.500,
    1.625,
    1.750,
    1.875,
    2.000,
    2.125,
    2.250,
    2.375,
    2.500,
    2.625,
    2.750,
    2.875,
    3.000,
    3.250,
    3.500,
    3.750,
    4.000,
    4.500,
    5.000,
)
EPAISSEUR_ARETE = (
    1.065,
    1.064,
    1.066,
    1.063,
    1.058,
    1.048,
    1.036,
    1.022,
    1.000,
    0.982,
    0.961,
    0.937,
    0.914,
    0.886,
    0.855,
    0.820,
    0.789,
    0.758,
    0.734,
    0.709,
    0.688,
    0.673,
    0.654,
    0.639,
    0.627,
    0.613,
    0.587,
    0.585,
    0.577,
    0.575,
    0.577,
)


# ===========================================================================
#  2. ATMOSPHERE  (cfd-atm si disponible, ISA de repli sinon)
# ===========================================================================

R_AIR = 287.05287  # J/(kg.K)
G0 = 9.80665  # m/s2
RAYON_TERRE = 6356766.0  # m, rayon conventionnel de l'ISA

_COUCHES_ISA = (
    # (altitude geopotentielle de base [m], T [K], p [Pa], gradient [K/m])
    (0.0, 288.15, 101325.0, -0.0065),
    (11000.0, 216.65, 22632.06, 0.0),
    (20000.0, 216.65, 5474.889, 0.001),
)

try:  # pragma: no cover
    import cfd_atm as _cfd_atm
except ImportError:  # pragma: no cover
    _cfd_atm = None

A_CFD_ATM = _cfd_atm is not None


def conditions_isa(
    altitude: float, delta_isa: float = 0.0, type_altitude: str = "geometrique"
) -> tuple[float, float]:
    """Temperature [K] et pression [Pa] statiques a `altitude` [m].

    Passe par cfd-atm s'il est installe, ce qui donne acces a l'ISA decalee
    d'un ecart `delta_isa` et aux altitudes geopotentielle et pression.
    Sans cfd-atm, seul le cas « ISA, altitude geometrique, 0 a 32 km » est
    traite ; le reste leve une exception plutot que de rendre un nombre faux.
    """
    if _cfd_atm is not None:
        modele = (
            _cfd_atm.AtmosphereModel.isa()
            if delta_isa == 0.0
            else _cfd_atm.AtmosphereModel.isa_offset(delta_isa)
        )
        if type_altitude == "geometrique":
            etat = modele.state_from_geometric(altitude)
        elif type_altitude == "geopotentielle":
            etat = modele.state_from_geopotential(altitude)
        elif type_altitude == "pression":
            etat = modele.state_from_pressure_altitude(altitude)
        else:
            raise ValueError(f"type d'altitude inconnu : {type_altitude!r}")
        return float(etat.t), float(etat.p)

    if delta_isa != 0.0 or type_altitude != "geometrique":
        raise RuntimeError(
            "ISA decalee et altitudes geopotentielle/pression demandent le "
            "paquet cfd-atm :  pip install -e tools/cfd-atm"
        )
    if not 0.0 <= altitude <= 32000.0:
        raise ValueError(
            f"altitude hors du modele de repli (0 a 32000 m) : {altitude} m. "
            "Installer cfd-atm pour aller plus haut."
        )
    h = RAYON_TERRE * altitude / (RAYON_TERRE + altitude)  # geopotentielle
    base_h, base_t, base_p, gradient = _COUCHES_ISA[0]
    for couche in _COUCHES_ISA:
        if h >= couche[0]:
            base_h, base_t, base_p, gradient = couche
        else:
            break
    dh = h - base_h
    if gradient == 0.0:
        return base_t, base_p * math.exp(-G0 * dh / (R_AIR * base_t))
    t = base_t + gradient * dh
    return t, base_p * (t / base_t) ** (-G0 / (gradient * R_AIR))


def mach_depuis_vitesse(
    temperature: float,
    pression: float,
    vc: float | None = None,
    tas: float | None = None,
    eas: float | None = None,
) -> float:
    """Mach a partir d'une vitesse Vc / TAS / EAS [m/s]. Demande cfd-atm."""
    if _cfd_atm is None:
        raise RuntimeError(
            "la conversion d'une vitesse en Mach demande cfd-atm :  pip install -e tools/cfd-atm"
        )
    fournies = [v for v in (vc, tas, eas) if v is not None]
    if len(fournies) != 1:
        raise ValueError("donner exactement une vitesse parmi vc, tas, eas")
    return float(_cfd_atm.airspeeds(pression, temperature, cas=vc, tas=tas, eas=eas).mach)


# ===========================================================================
#  3. ETAT LOCAL ET COUCHE LIMITE
# ===========================================================================

# Sutherland, air sec.
_MU_REF, _T_REF, _S_SUTHERLAND = 1.716e-5, 273.15, 110.4


def viscosite_sutherland(temperature: float) -> float:
    """Viscosite dynamique de l'air [Pa.s]."""
    return (
        _MU_REF
        * (temperature / _T_REF) ** 1.5
        * (_T_REF + _S_SUTHERLAND)
        / (temperature + _S_SUTHERLAND)
    )


@dataclass(frozen=True)
class EtatLocal:
    """Ecoulement au bord de la couche limite, a l'abscisse de l'asperite.

    ATTENTION : « local » veut dire local. Sur une voilure, le Mach au bord
    de couche limite a l'abscisse de la marche, pas le Mach infini amont.
    Prendre M_infini sur un extrados sous-estime la trainee d'un bon tiers.
    """

    mach: float
    temperature: float  # K
    pression: float  # Pa
    gamma: float = 1.4
    r_gaz: float = R_AIR
    prandtl: float = 0.72

    @classmethod
    def atmosphere(
        cls,
        altitude: float,
        mach: float | None = None,
        vc: float | None = None,
        tas: float | None = None,
        eas: float | None = None,
        delta_isa: float = 0.0,
        type_altitude: str = "geometrique",
    ) -> EtatLocal:
        """Construit l'etat depuis une altitude et une vitesse."""
        temperature, pression = conditions_isa(altitude, delta_isa, type_altitude)
        if mach is None:
            mach = mach_depuis_vitesse(temperature, pression, vc=vc, tas=tas, eas=eas)
        return cls(mach=mach, temperature=temperature, pression=pression)

    @property
    def celerite(self) -> float:
        return math.sqrt(self.gamma * self.r_gaz * self.temperature)

    @property
    def vitesse(self) -> float:
        return self.mach * self.celerite

    @property
    def masse_volumique(self) -> float:
        return self.pression / (self.r_gaz * self.temperature)

    @property
    def viscosite(self) -> float:
        return viscosite_sutherland(self.temperature)

    @property
    def pression_dynamique(self) -> float:
        """q_e = 1/2 * rho_e * u_e^2 [Pa]."""
        return 0.5 * self.masse_volumique * self.vitesse**2

    @property
    def facteur_recuperation(self) -> float:
        """r = Pr^(1/3), couche limite turbulente."""
        return self.prandtl ** (1.0 / 3.0)


def temperature_paroi_adiabatique(etat: EtatLocal) -> float:
    """T_aw = T_e * (1 + r*(gamma-1)/2*M^2) [K]."""
    return etat.temperature * (
        1.0 + etat.facteur_recuperation * 0.5 * (etat.gamma - 1.0) * etat.mach**2
    )


def temperature_reference_eckert(etat: EtatLocal, t_paroi: float) -> float:
    """T* / T_e = 0.5*(1 + T_w/T_e) + 0.22*r*(gamma-1)/2*M^2 [K].

    Evaluer une loi de frottement incompressible a T* est la facon standard
    de la porter en compressible ; quelques pour-cent jusqu'a M = 5 environ.
    """
    return etat.temperature * (
        0.5 * (1.0 + t_paroi / etat.temperature)
        + 0.22 * etat.facteur_recuperation * 0.5 * (etat.gamma - 1.0) * etat.mach**2
    )


@dataclass(frozen=True)
class CoucheLimite:
    """La couche limite NON PERTURBEE, reduite a ce dont la methode a besoin.

    tau_w et h+ suffisent. Si tau_w vient d'un calcul RANS ou d'une mesure,
    utiliser `depuis_cisaillement` : c'est la voie exacte. `plaque_plane`
    n'est la que pour l'avant-projet, quand seule la distance au bord
    d'attaque est connue.
    """

    cisaillement_paroi: float  # tau_w [Pa]
    cf: float  # C_fe = tau_w / q_e [-]
    vitesse_frottement: float  # u_tau [m/s]
    viscosite_cinematique_paroi: float  # nu_w [m2/s]
    temperature_paroi: float  # T_w [K]
    epaisseur: float | None = None  # delta [m]

    def h_plus(self, hauteur: float) -> float:
        """Nombre de Reynolds de rugosite h+ = u_tau * h / nu_w."""
        return self.vitesse_frottement * hauteur / self.viscosite_cinematique_paroi

    def immersion(self, hauteur: float) -> float | None:
        """h / delta, ou None si delta est inconnu."""
        return None if self.epaisseur is None else hauteur / self.epaisseur

    @classmethod
    def depuis_cisaillement(
        cls,
        etat: EtatLocal,
        tau_w: float,
        t_paroi: float | None = None,
        epaisseur: float | None = None,
    ) -> CoucheLimite:
        """Depuis un cisaillement parietal mesure ou calcule [Pa]."""
        if tau_w <= 0.0:
            raise ValueError(f"tau_w doit etre > 0 (recu {tau_w})")
        t_paroi = temperature_paroi_adiabatique(etat) if t_paroi is None else t_paroi
        # La pression est constante a travers la couche limite : rho_w suit T_w.
        rho_paroi = etat.pression / (etat.r_gaz * t_paroi)
        mu_paroi = viscosite_sutherland(t_paroi)
        return cls(
            cisaillement_paroi=tau_w,
            cf=tau_w / etat.pression_dynamique,
            vitesse_frottement=math.sqrt(tau_w / rho_paroi),
            viscosite_cinematique_paroi=mu_paroi / rho_paroi,
            temperature_paroi=t_paroi,
            epaisseur=epaisseur,
        )

    @classmethod
    def depuis_cf(
        cls,
        etat: EtatLocal,
        cf: float,
        t_paroi: float | None = None,
        epaisseur: float | None = None,
    ) -> CoucheLimite:
        """Depuis un coefficient de frottement local C_fe = tau_w / q_e."""
        return cls.depuis_cisaillement(etat, cf * etat.pression_dynamique, t_paroi, epaisseur)

    @classmethod
    def plaque_plane(cls, etat: EtatLocal, x: float, t_paroi: float | None = None) -> CoucheLimite:
        """Correlation de plaque plane a la distance `x` du bord d'attaque [m].

        Loi en 1/7, cf = 0.0592 * Re_x^(-0.2), evaluee a la temperature de
        reference d'Eckert puis ramenee aux conditions de bord par le rapport
        des masses volumiques. Suppose une couche limite turbulente depuis le
        bord d'attaque, sans gradient de pression.
        """
        if x <= 0.0:
            raise ValueError(f"la distance au bord d'attaque doit etre > 0 (recu {x})")
        t_paroi = temperature_paroi_adiabatique(etat) if t_paroi is None else t_paroi
        t_etoile = temperature_reference_eckert(etat, t_paroi)
        rho_etoile = etat.pression / (etat.r_gaz * t_etoile)
        mu_etoile = viscosite_sutherland(t_etoile)
        re_etoile = rho_etoile * etat.vitesse * x / mu_etoile
        cf = 0.0592 * re_etoile**-0.2 * rho_etoile / etat.masse_volumique
        delta = 0.37 * x * re_etoile**-0.2
        return cls.depuis_cf(etat, cf, t_paroi, delta)


# ===========================================================================
#  4. LES CORRELATIONS
# ===========================================================================


def _interpoler(x: float, abscisses: Sequence[float], ordonnees: Sequence[float]) -> float:
    """Interpolation lineaire par morceaux, valeurs d'extremite au-dela."""
    return float(np.interp(x, abscisses, ordonnees))


def _droite(table: dict[float, tuple[float, float]], mach: float, h_plus: float) -> float:
    """A*log10(h+) + B, interpole EN MACH entre les droites tabulees.

    On interpole le rapport de trainee, pas les coefficients A et B : B est
    une ordonnee a l'origine en h+ = 1, une decade sous tout ce qui a ete
    mesure, et une interpolation de B seul n'a pas de sens physique. Melanger
    les deux droites a la valeur de h+ voulue garde le resultat dans
    l'enveloppe des deux courbes mesurees.
    """
    machs = sorted(table)
    valeurs = [table[m][0] * math.log10(h_plus) + table[m][1] for m in machs]
    return _interpoler(mach, machs, valeurs)


def _transsonique(table: dict[float, tuple[float, float]], pc: float, h_plus: float) -> float:
    """Eq. 4(27), 4(32), 4(38) : melange des droites M = 0.8 et M = 1.4."""
    bas = table[0.8][0] * math.log10(h_plus) + table[0.8][1]
    haut = table[1.4][0] * math.log10(h_plus) + table[1.4][1]
    return bas + pc * (haut - bas)


def pc1(mach: float) -> float:
    """Facteur transsonique de la marche montante — Figure 4.25."""
    return _interpoler(mach, PC1_MACH, PC1_VALEUR)


def pc2(mach: float) -> float:
    """Facteur transsonique de la marche descendante — Figure 4.30."""
    return _interpoler(mach, PC2_MACH, PC2_VALEUR)


def pc3(mach: float) -> float:
    """Facteur transsonique de l'arete — Figure 4.38."""
    return _interpoler(mach, PC3_MACH, PC3_VALEUR)


def ratio_marche_montante(h_plus: float, mach: float) -> float:
    """CDe/Cfe d'une marche montante vive, 2-D, normale a l'ecoulement.

    Figures 4.23 et 4.25, eq. 4(26) et 4(27). Au-dela de M = 1.4 le rapport
    ne donne qu'une droite : le resultat cesse de varier avec le Mach.
    """
    if h_plus <= 0.0:
        raise ValueError(f"h+ doit etre > 0 (recu {h_plus})")
    if 0.8 < mach < 1.4:
        valeur = _transsonique(MARCHE_MONTANTE, pc1(mach), h_plus)
    else:
        valeur = _droite(MARCHE_MONTANTE, mach, h_plus)
    return max(valeur, 0.0)


def ratio_marche_descendante(h_plus: float, mach: float) -> float:
    """CDe/Cfe d'une marche descendante vive, 2-D, normale a l'ecoulement.

    Figures 4.28 et 4.30, eq. 4(31) et 4(32). La trainee passe par un maximum
    vers M = 1.15 puis decroit, contrairement a la marche montante.
    """
    if h_plus <= 0.0:
        raise ValueError(f"h+ doit etre > 0 (recu {h_plus})")
    if 0.8 < mach < 1.4:
        valeur = _transsonique(MARCHE_DESCENDANTE, pc2(mach), h_plus)
    else:
        valeur = _droite(MARCHE_DESCENDANTE, mach, h_plus)
    return max(valeur, 0.0)


def facteur_epaisseur_arete(t_sur_h: float) -> float:
    """T(t/h) — eq. 4(39), Figure 4.40."""
    if t_sur_h < 0.0:
        raise ValueError(f"t/h doit etre >= 0 (recu {t_sur_h})")
    return _interpoler(t_sur_h, EPAISSEUR_ARETE_X, EPAISSEUR_ARETE)


def ratio_arete(h_plus: float, mach: float, t_sur_h: float = 1.0) -> float:
    """CDe/Cfe d'une arete 2-D a faces verticales, epaisseur t = t_sur_h * h.

    Arete carree depuis les coefficients PUBLIES de l'eq. 4(37), transsonique
    par l'eq. 4(38) avec PC3, epaisseur par l'eq. 4(39) avec T(t/h).
    t_sur_h = 0 est une plaque mince normale a l'ecoulement.
    """
    if h_plus <= 0.0:
        raise ValueError(f"h+ doit etre > 0 (recu {h_plus})")
    if 0.8 < mach < 1.4:
        valeur = _transsonique(ARETE_CARREE, pc3(mach), h_plus)
    else:
        valeur = _droite(ARETE_CARREE, mach, h_plus)
    return max(valeur * facteur_epaisseur_arete(t_sur_h), 0.0)


def ratio_arete_rectangulaire_2h(h_plus: float, mach: float) -> float:
    """CDe/Cfe d'une arete d'epaisseur exactement 2h, table dediee eq. 4(37).

    A utiliser quand t = 2h et que l'immersion est faible : cette table
    croise l'arete carree vers h+ ~ 1000, ce que decrit le § 4.3.2.1, alors
    que la route generique T(2) * (arete carree) reste 21 % en dessous a
    tout h+. Les deux sont dans le rapport (voir ARETE_RECTANGULAIRE_2H).
    """
    if h_plus <= 0.0:
        raise ValueError(f"h+ doit etre > 0 (recu {h_plus})")
    if 0.8 < mach < 1.4:
        valeur = _transsonique(ARETE_RECTANGULAIRE_2H, pc3(mach), h_plus)
    else:
        valeur = _droite(ARETE_RECTANGULAIRE_2H, mach, h_plus)
    return max(valeur, 0.0)


def interference_arete(h_plus: float, mach: float) -> tuple[float, float, float]:
    """Compare une arete carree a la somme de ses deux marches — § 4.3.2.1.

    Retourne (arete, somme, somme/arete). Le rapport est d'environ 0.5 a bas
    Mach — « about 50 % below the drag of square ridges » — et remonte a 1
    vers M = 2.8, ou l'interference a disparu. Le bulbe de recirculation de
    la face amont n'a pas recolle quand il rencontre la face aval.
    """
    arete = ratio_arete(h_plus, mach)
    somme = ratio_marche_montante(h_plus, mach) + ratio_marche_descendante(h_plus, mach)
    return arete, somme, (somme / arete if arete > 0.0 else math.nan)


# --- Corrections de forme --------------------------------------------------


def _famille(
    table: dict[float, tuple[float, ...]], abscisses: Sequence[float], mach: float, x: float
) -> float:
    """Interpole une famille de courbes indexee par Mach, en x puis en Mach."""
    machs = sorted(table)
    valeurs = [_interpoler(x, abscisses, table[m]) for m in machs]
    return _interpoler(mach, machs, valeurs)


def facteur_arrondi_montante(r_sur_h: float, mach: float) -> float:
    """(1 - E) pour une marche montante a arete arrondie — eq. 4(28)."""
    if r_sur_h < 0.0:
        raise ValueError(f"r/h doit etre >= 0 (recu {r_sur_h})")
    return max(1.0 - _famille(ARRONDI_MONTANTE, ARRONDI_MONTANTE_X, mach, r_sur_h), 0.0)


def facteur_chanfrein_montante(angle: float, mach: float) -> float:
    """(1 - E) pour une marche montante chanfreinee — eq. 4(29).

    `angle` en DEGRES : 90 deg est la marche vive (facteur 1), 0 deg le
    carenage complet (facteur 0).
    """
    if not 0.0 <= angle <= 90.0:
        raise ValueError(f"l'angle de chanfrein doit etre dans [0, 90] (recu {angle})")
    return max(1.0 - _famille(CHANFREIN_MONTANTE, CHANFREIN_MONTANTE_X, mach, angle), 0.0)


def facteur_arrondi_descendante(r_sur_h: float) -> float:
    """(1 + 1.43*r/h) pour une marche descendante a arete arrondie — eq. 4(34).

    Noter le signe : arrondir l'arete AVAL augmente la trainee (Figure 4.32).
    """
    if r_sur_h < 0.0:
        raise ValueError(f"r/h doit etre >= 0 (recu {r_sur_h})")
    return 1.0 + COEFFICIENT_ARRONDI_DESCENDANTE * r_sur_h


def facteur_chanfrein_descendante(angle: float, mach: float) -> float:
    """(1 - G) pour une marche descendante chanfreinee — eq. 4(33).

    Sans effet jusqu'a 45 deg ; entre 12 et 45 deg le facteur passe LEGEREMENT
    au-dessus de 1 au transsonique et au supersonique (la trainee augmente) ;
    chute franche sous 12 deg. C'est la correlation la moins sure du lot.
    """
    if not 0.0 <= angle <= 90.0:
        raise ValueError(f"l'angle de chanfrein doit etre dans [0, 90] (recu {angle})")
    return max(1.0 - _famille(CHANFREIN_DESCENDANTE, CHANFREIN_DESCENDANTE_X, mach, angle), 0.0)


def facteur_derapage(angle: float) -> float:
    """sin^2(alpha) pour une asperite en biais — eq. 4(30), 4(35), 4(41).

    `angle` en DEGRES entre l'ecoulement et l'axe de l'asperite : 90 deg,
    l'asperite est en travers du flux (facteur 1) ; 0 deg, elle lui est
    parallele (facteur 0). Etabli sur les aretes (Figure 4.45) ; l'appliquer
    aux marches est une hypothese du rapport, pas une mesure (§ 4.3.2.3).
    """
    if not 0.0 <= angle <= 90.0:
        raise ValueError(f"l'angle de derapage doit etre dans [0, 90] (recu {angle})")
    return math.sin(math.radians(angle)) ** 2


def facteur_amplification_nash_bradshaw(
    ue_locale_sur_v0: float, ue_bord_fuite_sur_v0: float, theta_locale_sur_theta_bf: float
) -> float:
    """Facteur d'amplification m_d de Nash & Bradshaw — eq. 5(5), § 5.1.

        m_d = (u_eo/V0)^4.2 * (V0/u_eT) * (theta_o/theta_T)^(1/5)

    Toutes les correlations du § 4.3 sont a gradient de pression nul. Sur un
    profil, ce que l'asperite ajoute a l'epaisseur de quantite de mouvement
    est transporte jusqu'au bord de fuite et amplifie en chemin. m_d vaut
    exactement 1 sur plaque plane et peut largement depasser le (u_eo/V0)^2
    que donnerait la simple proportionnalite a la pression dynamique locale.

    Hypotheses : ecoulement incompressible, profil turbulent en 1/7, petite
    perturbation. La version compressible de Cook (Ref. 5.4) sous-estimait
    les increments mesures d'environ 10 % en subcritique.
    """
    for nom, valeur in (
        ("u_eo/V0", ue_locale_sur_v0),
        ("u_eT/V0", ue_bord_fuite_sur_v0),
        ("theta_o/theta_T", theta_locale_sur_theta_bf),
    ):
        if valeur <= 0.0:
            raise ValueError(f"{nom} doit etre > 0 (recu {valeur})")
    return ue_locale_sur_v0**4.2 / ue_bord_fuite_sur_v0 * theta_locale_sur_theta_bf**0.2


# ===========================================================================
#  5. ASSEMBLAGE : DE LA GEOMETRIE A LA FORCE
# ===========================================================================

MONTANTE, DESCENDANTE, ARETE = "montante", "descendante", "arete"


@dataclass(frozen=True)
class Asperite:
    """Une marche ou une arete sur une surface.

    hauteur et envergure en metres ; angles en degres. `angle_chanfrein`
    vaut 90 pour une arete vive, `angle_derapage` 90 pour une asperite en
    travers de l'ecoulement.
    """

    type_asperite: str  # MONTANTE | DESCENDANTE | ARETE
    hauteur: float  # h [m]
    envergure: float  # b [m]
    t_sur_h: float = 1.0  # epaisseur d'arete
    rayon_sur_h: float = 0.0  # arrondi d'arete
    angle_chanfrein: float = 90.0  # theta [deg]
    angle_derapage: float = 90.0  # alpha [deg]

    def __post_init__(self) -> None:
        if self.type_asperite not in (MONTANTE, DESCENDANTE, ARETE):
            raise ValueError(f"type inconnu : {self.type_asperite!r}")
        if self.hauteur <= 0.0 or self.envergure <= 0.0:
            raise ValueError("hauteur et envergure doivent etre > 0")
        if self.rayon_sur_h > 0.0 and self.angle_chanfrein < 90.0:
            raise ValueError("une arete est soit arrondie soit chanfreinee, pas les deux")

    @property
    def aire_frontale(self) -> float:
        """f_e = h * b [m2]."""
        return self.hauteur * self.envergure

    def facteur_forme(self, mach: float) -> float:
        """Produit des corrections de forme.

        Le rapport applique ces corrections une a une et ne dit jamais
        qu'elles se composent ; les multiplier est l'hypothese d'ingenieur
        usuelle.
        """
        facteur = facteur_derapage(self.angle_derapage)
        if self.type_asperite == MONTANTE:
            if self.rayon_sur_h > 0.0:
                facteur *= facteur_arrondi_montante(self.rayon_sur_h, mach)
            if self.angle_chanfrein < 90.0:
                facteur *= facteur_chanfrein_montante(self.angle_chanfrein, mach)
        elif self.type_asperite == DESCENDANTE:
            if self.rayon_sur_h > 0.0:
                facteur *= facteur_arrondi_descendante(self.rayon_sur_h)
            if self.angle_chanfrein < 90.0:
                facteur *= facteur_chanfrein_descendante(self.angle_chanfrein, mach)
        # L'epaisseur de l'arete est deja portee par ratio_arete ; les aretes
        # arrondies ou chanfreinees relevent des Figures 4.41 a 4.44, non
        # numerisees ici.
        return facteur


@dataclass(frozen=True)
class Resultat:
    """Tout ce qu'un rapport a besoin de citer pour une asperite."""

    h_plus: float
    immersion: float | None
    cde_sur_cfe: float
    facteur_forme: float
    cde: float  # dD / (q_e * f_e)
    cisaillement_paroi: float  # tau_w [Pa]
    trainee: float  # dD [N]
    delta_cx: float | None  # dD / (q_e * S_ref)
    avertissements: list[str] = field(default_factory=list)


def verifier_domaine(
    type_asperite: str, h_plus: float, mach: float, immersion: float | None = None
) -> list[str]:
    """Liste les extrapolations que l'appel est en train de faire."""
    messages: list[str] = []

    if not H_PLUS_MIN <= h_plus <= H_PLUS_MAX:
        cote = "sous" if h_plus < H_PLUS_MIN else "au-dessus de"
        messages.append(
            f"h+ = {h_plus:.3g} est {cote} la plage mesuree "
            f"[{H_PLUS_MIN:.0f}, {H_PLUS_MAX:.0f}] : la droite est extrapolee."
        )
    if (
        type_asperite == MONTANTE
        and mach < 1.4
        and H_PLUS_MIN <= h_plus < H_PLUS_MIN_MONTANTE_SUBSONIQUE
    ):
        messages.append(
            f"h+ = {h_plus:.3g} : les droites subsoniques de la marche montante "
            f"(Figure 4.23) ne sont tracees qu'a partir de h+ ~ "
            f"{H_PLUS_MIN_MONTANTE_SUBSONIQUE:.0f} ; plus bas elles passent sous "
            "la marche descendante, ce qui est un artefact d'extrapolation."
        )

    table = {MONTANTE: MARCHE_MONTANTE, DESCENDANTE: MARCHE_DESCENDANTE, ARETE: ARETE_CARREE}[
        type_asperite
    ]
    mach_min, mach_max = min(table), max(table)
    if not mach_min <= mach <= mach_max:
        cote = "sous" if mach < mach_min else "au-dessus de"
        messages.append(
            f"M = {mach:.3g} est {cote} la plage tabulee [{mach_min:g}, {mach_max:g}] "
            f"pour une asperite « {type_asperite} » : la courbe la plus proche "
            "est maintenue constante."
        )
    if immersion is not None and immersion > H_SUR_DELTA_MAX:
        messages.append(
            f"h/delta = {immersion:.3g} depasse {H_SUR_DELTA_MAX:g} : l'asperite "
            "n'est plus noyee dans la region interne de la couche limite et la "
            "correlation en h+ perd son fondement."
        )
    return messages


def calculer_trainee(
    asperite: Asperite,
    etat: EtatLocal,
    couche: CoucheLimite,
    surface_reference: float | None = None,
    amplification: float = 1.0,
) -> Resultat:
    """Increment de trainee d'une asperite.

        dD = (CDe/Cfe) * f_forme * m_d * tau_w * f_e

    `amplification` est le facteur m_d de Nash-Bradshaw (1 sur plaque plane) ;
    il n'est jamais applique d'office car il demande des grandeurs au bord de
    fuite. `surface_reference` ne sert qu'a exprimer le resultat en dCx.
    """
    if amplification <= 0.0:
        raise ValueError(f"le facteur d'amplification doit etre > 0 (recu {amplification})")

    h_plus = couche.h_plus(asperite.hauteur)
    immersion = couche.immersion(asperite.hauteur)

    if asperite.type_asperite == MONTANTE:
        ratio = ratio_marche_montante(h_plus, etat.mach)
    elif asperite.type_asperite == DESCENDANTE:
        ratio = ratio_marche_descendante(h_plus, etat.mach)
    else:
        ratio = ratio_arete(h_plus, etat.mach, asperite.t_sur_h)

    forme = asperite.facteur_forme(etat.mach)
    cde = ratio * couche.cf * forme * amplification
    trainee = cde * etat.pression_dynamique * asperite.aire_frontale

    delta_cx = None
    if surface_reference is not None:
        if surface_reference <= 0.0:
            raise ValueError("la surface de reference doit etre > 0")
        delta_cx = trainee / (etat.pression_dynamique * surface_reference)

    return Resultat(
        h_plus=h_plus,
        immersion=immersion,
        cde_sur_cfe=ratio,
        facteur_forme=forme,
        cde=cde,
        cisaillement_paroi=couche.cisaillement_paroi,
        trainee=trainee,
        delta_cx=delta_cx,
        avertissements=verifier_domaine(asperite.type_asperite, h_plus, etat.mach, immersion),
    )


# ===========================================================================
#  6. FIGURES : CE QUI A ETE EXTRAIT DES PLANCHES DU RAPPORT
# ===========================================================================
#
# Une planche par figure source. Elles redessinent EXACTEMENT les tables du
# § 1, et servent donc de controle visuel : superposees aux figures scannees
# du rapport, les traits doivent se recouvrir.
#
# cfd-plot est utilise s'il est installe (style maison, plot_line,
# save_figure) ; sinon on retombe sur Matplotlib nu.

_COULEURS = ("#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b")


def _bibliotheque_trace() -> Any:
    try:  # pragma: no cover
        import cfd_plot

        return cfd_plot
    except ImportError:  # pragma: no cover
        return None


def tracer_extractions(repertoire: str, dpi: int = 140) -> list[str]:
    """Ecrit les planches d'extraction dans `repertoire`. Retourne les chemins."""
    import os

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    trace = _bibliotheque_trace()
    if trace is not None:
        trace.use_style("paper")

    os.makedirs(repertoire, exist_ok=True)
    ecrits: list[str] = []

    def ligne(axe, x, y, **kw):
        kw.setdefault("marker", "")
        if trace is not None:
            return trace.plot_line(axe, x, y, **kw)
        return axe.plot(x, y, **kw)[0]

    def enregistrer(figure, nom):
        chemin = os.path.join(repertoire, nom)
        figure.savefig(chemin, dpi=dpi, bbox_inches="tight")
        plt.close(figure)
        ecrits.append(chemin)

    h_plus = np.logspace(math.log10(H_PLUS_MIN), math.log10(H_PLUS_MAX), 200)

    def planche_droites(table, fonction, titre, nom, extra=None):
        figure, axe = plt.subplots(figsize=(7.2, 4.6))
        for couleur, mach in zip(_COULEURS, sorted(table)):
            ligne(
                axe,
                h_plus,
                [fonction(float(x), mach) for x in h_plus],
                color=couleur,
                label=f"M = {mach:g}",
            )
        if extra is not None:
            extra(axe)
        axe.set_xscale("log")
        axe.set_xlabel("h$^+$ = u$_\\tau$·h/ν$_w$")
        axe.set_ylabel("CDe / Cfe")
        axe.set_title(titre)
        axe.grid(True, which="both", alpha=0.3)
        axe.legend(fontsize="small", loc="upper left")
        enregistrer(figure, nom)

    # -- Figure 4.23 : marche montante
    planche_droites(
        MARCHE_MONTANTE,
        ratio_marche_montante,
        "Extraction de la Figure 4.23 — marche montante",
        "ext_4_23.png",
    )

    # -- Figure 4.25 : PC1
    def planche_pc(machs, valeurs, titre, nom, symbole):
        figure, axe = plt.subplots(figsize=(7.2, 4.4))
        fin = np.linspace(min(machs), max(machs), 300)
        ligne(
            axe,
            fin,
            [_interpoler(float(m), machs, valeurs) for m in fin],
            color=_COULEURS[0],
            label="interpolation du paquet",
        )
        axe.plot(
            machs,
            valeurs,
            "o",
            color=_COULEURS[1],
            markerfacecolor="white",
            markeredgewidth=1.4,
            label="points extraits de la figure",
        )
        axe.axhline(1.0, color="0.5", linewidth=0.8, linestyle="--", zorder=0)
        axe.set_xlabel("Nombre de Mach")
        axe.set_ylabel(symbole)
        axe.set_title(titre)
        axe.grid(True, alpha=0.3)
        axe.legend(fontsize="small", loc="upper left")
        enregistrer(figure, nom)

    planche_pc(
        PC1_MACH,
        PC1_VALEUR,
        "Extraction de la Figure 4.25 — facteur transsonique PC$_1$",
        "ext_4_25.png",
        "PC$_1$",
    )

    # -- Figure 4.26 : arrondi et chanfrein de la marche montante
    figure, axes = plt.subplots(1, 2, figsize=(11.0, 4.2))
    for couleur, mach in zip(_COULEURS, sorted(ARRONDI_MONTANTE)):
        ligne(
            axes[0],
            ARRONDI_MONTANTE_X,
            ARRONDI_MONTANTE[mach],
            color=couleur,
            label=f"M = {mach:g}",
        )
    axes[0].set_xlabel("r/h")
    axes[0].set_ylabel("E$_{r/h}$")
    axes[0].set_title("(a) arrondi")
    for couleur, mach in zip(_COULEURS, sorted(CHANFREIN_MONTANTE)):
        ligne(
            axes[1],
            CHANFREIN_MONTANTE_X,
            CHANFREIN_MONTANTE[mach],
            color=couleur,
            label=f"M = {mach:g}",
        )
    axes[1].set_xlabel("θ [°]")
    axes[1].set_ylabel("E$_θ$")
    axes[1].set_title("(b) chanfrein")
    for axe in axes:
        axe.grid(True, alpha=0.3)
        axe.legend(fontsize="small")
    figure.suptitle("Extraction de la Figure 4.26 — marche montante, arête adoucie")
    enregistrer(figure, "ext_4_26.png")

    # -- Figure 4.28 : marche descendante
    planche_droites(
        MARCHE_DESCENDANTE,
        ratio_marche_descendante,
        "Extraction de la Figure 4.28 — marche descendante",
        "ext_4_28.png",
    )

    # -- Figure 4.30 : PC2
    planche_pc(
        PC2_MACH,
        PC2_VALEUR,
        "Extraction de la Figure 4.30 — facteur transsonique PC$_2$",
        "ext_4_30.png",
        "PC$_2$",
    )

    # -- Figure 4.33 : chanfrein de la marche descendante
    figure, axe = plt.subplots(figsize=(7.2, 4.4))
    for couleur, mach in zip(_COULEURS, sorted(CHANFREIN_DESCENDANTE)):
        ligne(
            axe,
            CHANFREIN_DESCENDANTE_X,
            CHANFREIN_DESCENDANTE[mach],
            color=couleur,
            label=f"M = {mach:g}",
        )
    axe.axhline(0.0, color="0.5", linewidth=0.8, linestyle="--", zorder=0)
    axe.set_xlabel("θ [°]")
    axe.set_ylabel("G$_θ$")
    axe.set_title("Extraction de la Figure 4.33 — marche descendante, chanfrein")
    axe.grid(True, alpha=0.3)
    axe.legend(fontsize="small")
    enregistrer(figure, "ext_4_33.png")

    # -- Figure 4.34 : arete
    def rectangulaire(axe):
        ligne(
            axe,
            h_plus,
            [ratio_arete_rectangulaire_2h(float(x), 0.2) for x in h_plus],
            color="0.35",
            linestyle="--",
            label="t = 2h, M = 0,2 (table dédiée)",
        )

    planche_droites(
        ARETE_CARREE,
        ratio_arete,
        "Extraction de la Figure 4.34 — arête carrée (t = h)",
        "ext_4_34.png",
        extra=rectangulaire,
    )

    # -- Figure 4.38 : PC3
    planche_pc(
        PC3_MACH,
        PC3_VALEUR,
        "Extraction de la Figure 4.38 — facteur transsonique PC$_3$",
        "ext_4_38.png",
        "PC$_3$",
    )

    # -- Figure 4.40 : epaisseur d'arete
    figure, axe = plt.subplots(figsize=(7.2, 4.2))
    fin = np.linspace(0.0, 5.0, 300)
    ligne(
        axe,
        fin,
        [facteur_epaisseur_arete(float(x)) for x in fin],
        color=_COULEURS[0],
        label="T(t/h)",
    )
    axe.plot(
        EPAISSEUR_ARETE_X,
        EPAISSEUR_ARETE,
        "o",
        markersize=3.5,
        color=_COULEURS[1],
        markerfacecolor="white",
        label="points extraits de la figure",
    )
    axe.axhline(1.0, color="0.5", linewidth=0.8, linestyle="--", zorder=0)
    axe.set_xlabel("t/h")
    axe.set_ylabel("T")
    axe.set_title("Extraction de la Figure 4.40 — effet de l'épaisseur d'arête")
    axe.grid(True, alpha=0.3)
    axe.legend(fontsize="small")
    enregistrer(figure, "ext_4_40.png")

    # -- Figure 4.45 : derapage
    figure, axe = plt.subplots(figsize=(7.2, 4.2))
    angles = np.linspace(0.0, 90.0, 181)
    ligne(
        axe, angles, [facteur_derapage(float(a)) for a in angles], color=_COULEURS[0], label="sin²α"
    )
    axe.set_xlabel("α [°]")
    axe.set_ylabel("(CDe)$_α$ / (CDe)$_{α=90°}$")
    axe.set_title("Extraction de la Figure 4.45 — effet du dérapage")
    axe.grid(True, alpha=0.3)
    axe.legend(fontsize="small")
    enregistrer(figure, "ext_4_45.png")

    return ecrits


# ===========================================================================
#  7. EXEMPLE DE BOUT EN BOUT
# ===========================================================================


def exemple() -> None:
    """Un cas de croisiere complet, chiffre etape par etape."""
    print("=" * 74)
    print("  TRAINEE D'UNE MARCHE — AGARD-AG-264 § 4.3")
    print("=" * 74)
    print(f"  atmosphere : {'cfd-atm' if A_CFD_ATM else 'ISA de repli (cfd-atm absent)'}")
    print(f"  figures    : {'cfd-plot' if _bibliotheque_trace() else 'matplotlib'}")
    print()

    # --- 1. L'ecoulement LOCAL, au bord de couche limite -------------------
    etat = EtatLocal.atmosphere(altitude=11000.0, mach=0.82)
    print("1. Ecoulement local (extrados, FL360)")
    print(f"   M      = {etat.mach:.3f}")
    print(f"   T      = {etat.temperature:8.2f} K")
    print(f"   p      = {etat.pression:8.1f} Pa")
    print(f"   u_e    = {etat.vitesse:8.2f} m/s")
    print(f"   rho_e  = {etat.masse_volumique:8.5f} kg/m3")
    print(f"   q_e    = {etat.pression_dynamique:8.1f} Pa")

    # --- 2. La couche limite non perturbee ---------------------------------
    couche = CoucheLimite.plaque_plane(etat, x=10.0)
    assert couche.epaisseur is not None  # plaque_plane renseigne toujours delta
    print()
    print("2. Couche limite non perturbee (plaque plane, 10 m de parcours)")
    print(f"   T_w    = {couche.temperature_paroi:8.2f} K   (paroi adiabatique)")
    print(f"   C_fe   = {couche.cf:10.6f}       = tau_w / q_e")
    print(f"   tau_w  = {couche.cisaillement_paroi:8.3f} Pa")
    print(f"   u_tau  = {couche.vitesse_frottement:8.3f} m/s  = sqrt(tau_w/rho_w)")
    print(f"   nu_w   = {couche.viscosite_cinematique_paroi:10.3e} m2/s")
    print(f"   delta  = {couche.epaisseur * 1e3:8.1f} mm")

    # --- 3. Les trois geometries, meme hauteur -----------------------------
    hauteur, envergure, s_ref = 1.5e-3, 2.4, 122.6
    print()
    print(
        f"3. Trois aspérités de {hauteur * 1e3:.1f} mm sur {envergure:.1f} m "
        f"(S_ref = {s_ref:.1f} m2)"
    )
    print()
    print(f"   {'type':<14}{'h+':>8}{'h/delta':>10}{'CDe/Cfe':>10}{'dD [N]':>10}{'dCx':>12}")
    for type_asperite in (MONTANTE, DESCENDANTE, ARETE):
        asperite = Asperite(type_asperite, hauteur, envergure)
        r = calculer_trainee(asperite, etat, couche, surface_reference=s_ref)
        assert r.immersion is not None and r.delta_cx is not None
        print(
            f"   {type_asperite:<14}{r.h_plus:8.1f}{r.immersion:10.4f}"
            f"{r.cde_sur_cfe:10.1f}{r.trainee:10.3f}{r.delta_cx:12.3e}"
        )

    # --- 4. Ce que rapporte un chanfrein -----------------------------------
    print()
    print("4. Casser l'arête d'une marche montante")
    for angle in (90.0, 45.0, 30.0, 15.0):
        asperite = Asperite(MONTANTE, hauteur, envergure, angle_chanfrein=angle)
        r = calculer_trainee(asperite, etat, couche)
        print(
            f"   theta = {angle:4.0f} deg   facteur {r.facteur_forme:.3f}   dD = {r.trainee:6.3f} N"
        )

    # --- 5. L'interference d'arete -----------------------------------------
    print()
    print("5. Une arête n'est pas la somme de ses deux marches (h+ = 1000)")
    print(
        f"   {'M':>5}{'montante':>11}{'descendante':>13}{'somme':>9}{'arête':>9}{'somme/arête':>13}"
    )
    for mach in (0.2, 0.8, 1.4, 2.2, 2.8):
        arete, somme, rapport = interference_arete(1000.0, mach)
        print(
            f"   {mach:5.1f}{ratio_marche_montante(1000.0, mach):11.1f}"
            f"{ratio_marche_descendante(1000.0, mach):13.1f}{somme:9.1f}"
            f"{arete:9.1f}{rapport:13.3f}"
        )
    print()
    print("   Le rapport AGARD annonce « about 50 % below » a bas Mach et un")
    print("   ecart disparu a M = 2.8 : c'est bien ce qu'on retrouve.")

    # --- 6. Avertissements -------------------------------------------------
    hors_domaine = Asperite(MONTANTE, 2.0e-2, 1.0)
    r = calculer_trainee(hors_domaine, etat, couche)
    print()
    print("6. Hors domaine — une marche de 20 mm au meme endroit")
    for message in r.avertissements:
        print(f"   ! {message}")
    print()


def main(argv: Sequence[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(
        description="Trainee d'une marche ou d'une arete — AGARD-AG-264 § 4.3",
    )
    parseur.add_argument(
        "--figures", metavar="REP", help="ecrire les planches d'extraction dans REP"
    )
    arguments = parseur.parse_args(argv)

    exemple()
    if arguments.figures:
        print("Planches d'extraction :")
        for chemin in tracer_extractions(arguments.figures):
            print(f"   {chemin}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
