"""Local flow state and the turbulent boundary layer the excrescence sits in.

The AGARD-AG-264 step and ridge correlations take **two** numbers from the
undisturbed boundary layer and nothing else:

``h⁺ = u_τ·h/ν_w``
    the roughness Reynolds number, which is what the drag ratio is correlated
    against. It is built on *wall* values — friction velocity and kinematic
    viscosity at the wall — because a small excrescence only ever sees the
    inner region of the layer (§4.3.1.1.1).

``τ_w``
    the undisturbed wall shear stress, which converts the drag ratio into a
    force: the report's ``CDe/Cfe`` is ``ΔD/(q_e·f_e)`` divided by
    ``τ_w/q_e``, so the local dynamic pressure cancels and

        ΔD = (CDe/Cfe) · τ_w · f_e

    with ``f_e`` the frontal area of the excrescence. Nothing downstream needs
    ``q_e`` at all; it is reported only because an engineer reads it.

A caller who already has ``τ_w`` from a CFD solution or a wind-tunnel balance
should hand it over with :meth:`CoucheLimite.depuis_cisaillement` and ignore
the flat-plate correlation entirely — that is the accurate path. The
correlation in :func:`cf_plaque_plane` exists for preliminary work, where the
only data available are "so many metres from the leading edge".
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from cfd_aq.core.atmosphere import PointAtmospherique, conditions, mach_depuis_vitesse

__all__ = [
    "CoucheLimite",
    "EtatLocal",
    "cf_plaque_plane",
    "epaisseur_plaque_plane",
    "temperature_paroi_adiabatique",
    "temperature_reference_eckert",
    "viscosite_sutherland",
]

#: Sutherland, air : μ_ref [Pa·s], T_ref [K], S [K].
_MU_REF = 1.716e-5
_T_REF = 273.15
_S_SUTHERLAND = 110.4


def viscosite_sutherland(temperature: float) -> float:
    """Dynamic viscosity of air [Pa·s] from Sutherland's law."""
    if temperature <= 0.0:
        raise ValueError(f"température absolue attendue, reçu {temperature} K")
    return (
        _MU_REF
        * float((temperature / _T_REF) ** 1.5)
        * (_T_REF + _S_SUTHERLAND)
        / (temperature + _S_SUTHERLAND)
    )


@dataclass(frozen=True)
class EtatLocal:
    """Flow state at the edge of the boundary layer, where the step sits.

    "Local" means local: on a wing, the Mach number and the static conditions
    just outside the boundary layer at the step's chordwise station, not the
    free-stream ones. Using free-stream values on a suction peak understates
    the drag — see also the Nash–Bradshaw magnification factor in
    :mod:`cfd_aq.core.trainee`.

    Attributes:
        mach: local Mach number at the boundary-layer edge [-].
        temperature: local static temperature [K].
        pression: local static pressure [Pa].
        gamma: ratio of specific heats [-].
        r_gaz: specific gas constant [J/(kg·K)].
        prandtl: Prandtl number, used for the recovery factor [-].
    """

    mach: float
    temperature: float
    pression: float
    gamma: float = 1.4
    r_gaz: float = 287.05287
    prandtl: float = 0.72

    def __post_init__(self) -> None:
        if self.mach <= 0.0:
            raise ValueError(f"le Mach local doit être > 0 (reçu {self.mach})")
        if self.temperature <= 0.0:
            raise ValueError(f"la température doit être > 0 K (reçue {self.temperature})")
        if self.pression <= 0.0:
            raise ValueError(f"la pression doit être > 0 Pa (reçue {self.pression})")
        if self.gamma <= 1.0:
            raise ValueError(f"γ doit être > 1 (reçu {self.gamma})")

    @classmethod
    def isa(cls, altitude: float, mach: float, **kwargs: Any) -> EtatLocal:
        """Build a state from the plain ISA at ``altitude`` [m] and a Mach number.

        Short form of :meth:`atmosphere`; goes through ``cfd-atm`` when that
        package is installed.
        """
        return cls.atmosphere(altitude, mach=mach, **kwargs)

    @classmethod
    def atmosphere(
        cls,
        altitude: float,
        mach: float | None = None,
        vitesse_conventionnelle: float | None = None,
        vitesse_vraie: float | None = None,
        vitesse_equivalente: float | None = None,
        delta_isa: float = 0.0,
        type_altitude: str = "geometrique",
        **kwargs: Any,
    ) -> EtatLocal:
        """Build a state from an altitude and a speed, through ``cfd-atm``.

        The speed may be given as a Mach number or as any of the three
        airspeeds a cockpit or a flight-test record carries — exactly one of
        the four. Everything but ``mach`` on a plain geometric ISA needs the
        sibling package ``cfd-atm`` (see :mod:`cfd_aq.core.atmosphere`).

        Args:
            altitude: altitude [m], read according to ``type_altitude``.
            mach: Mach number [-].
            vitesse_conventionnelle: Vc / CAS [m/s].
            vitesse_vraie: TAS [m/s].
            vitesse_equivalente: EAS [m/s].
            delta_isa: temperature offset ΔT [K] on top of the ISA.
            type_altitude: ``"geometrique"``, ``"geopotentielle"`` or
                ``"pression"``.
            **kwargs: forwarded to the constructor (``gamma``, ``r_gaz``,
                ``prandtl``).

        Remember that these are the conditions **at the excrescence**, not in
        the free stream: on a wing's suction peak the local Mach number is the
        higher one, and it is the one the correlations want.
        """
        vitesses = {
            "mach": mach,
            "vitesse_conventionnelle": vitesse_conventionnelle,
            "vitesse_vraie": vitesse_vraie,
            "vitesse_equivalente": vitesse_equivalente,
        }
        nommees = [nom for nom, valeur in vitesses.items() if valeur is not None]
        if len(nommees) != 1:
            raise ValueError(
                "donner exactement une vitesse parmi mach, vitesse_conventionnelle, "
                f"vitesse_vraie et vitesse_equivalente (reçu : {', '.join(nommees) or 'aucune'})."
            )
        point = conditions(altitude, delta_isa=delta_isa, type_altitude=type_altitude)
        if mach is None:
            mach = mach_depuis_vitesse(
                point,
                vitesse_conventionnelle=vitesse_conventionnelle,
                vitesse_vraie=vitesse_vraie,
                vitesse_equivalente=vitesse_equivalente,
            )
        return cls(
            mach=mach,
            temperature=point.temperature,
            pression=point.pression,
            **kwargs,
        )

    @classmethod
    def depuis_point(cls, point: PointAtmospherique, mach: float, **kwargs: Any) -> EtatLocal:
        """Build a state from an already-resolved atmospheric point."""
        return cls(mach=mach, temperature=point.temperature, pression=point.pression, **kwargs)

    @property
    def celerite(self) -> float:
        """Speed of sound [m/s]."""
        return math.sqrt(self.gamma * self.r_gaz * self.temperature)

    @property
    def vitesse(self) -> float:
        """Flow speed at the boundary-layer edge, u_e [m/s]."""
        return self.mach * self.celerite

    @property
    def masse_volumique(self) -> float:
        """Density at the boundary-layer edge, ρ_e [kg/m³]."""
        return self.pression / (self.r_gaz * self.temperature)

    @property
    def viscosite(self) -> float:
        """Dynamic viscosity at the boundary-layer edge, μ_e [Pa·s]."""
        return viscosite_sutherland(self.temperature)

    @property
    def pression_dynamique(self) -> float:
        """Local dynamic pressure q_e = ½ρ_e·u_e² [Pa]."""
        return 0.5 * self.masse_volumique * self.vitesse**2

    @property
    def facteur_recuperation(self) -> float:
        """Turbulent recovery factor, r = Pr^(1/3) [-]."""
        return float(self.prandtl ** (1.0 / 3.0))

    def reynolds(self, longueur: float) -> float:
        """Reynolds number on ``longueur`` [m], built on edge conditions."""
        if longueur <= 0.0:
            raise ValueError(f"la longueur doit être > 0 m (reçue {longueur})")
        return self.masse_volumique * self.vitesse * longueur / self.viscosite


def temperature_paroi_adiabatique(etat: EtatLocal) -> float:
    """Adiabatic (recovery) wall temperature [K].

    ``T_aw = T_e·(1 + r·(γ−1)/2·M²)`` with ``r = Pr^(1/3)``. This is the right
    default for an airframe skin in cruise; a heated or cooled wall must be
    passed explicitly wherever a wall temperature is accepted.
    """
    return etat.temperature * (
        1.0 + etat.facteur_recuperation * 0.5 * (etat.gamma - 1.0) * etat.mach**2
    )


def temperature_reference_eckert(etat: EtatLocal, temperature_paroi: float) -> float:
    """Eckert reference temperature T* [K].

    ``T*/T_e = 0.5·(1 + T_w/T_e) + 0.22·r·(γ−1)/2·M²``. Evaluating an
    incompressible skin-friction law at T* is the standard way to carry a
    turbulent flat-plate correlation into compressible flow; it is accurate to
    a few per cent up to about M = 5 for an adiabatic wall.
    """
    if temperature_paroi <= 0.0:
        raise ValueError(f"la température de paroi doit être > 0 K (reçue {temperature_paroi})")
    return etat.temperature * (
        0.5 * (1.0 + temperature_paroi / etat.temperature)
        + 0.22 * etat.facteur_recuperation * 0.5 * (etat.gamma - 1.0) * etat.mach**2
    )


def cf_plaque_plane(
    etat: EtatLocal,
    distance_bord_attaque: float,
    temperature_paroi: float | None = None,
) -> float:
    """Local turbulent skin-friction coefficient C_fe = τ_w/q_e [-].

    Incompressible 1/7-power law ``cf = 0.0592·Re_x^(-0.2)`` evaluated at the
    Eckert reference temperature, then referred back to edge conditions by the
    density ratio ρ*/ρ_e.

    This assumes a turbulent layer that started at the leading edge, on a flat
    plate, with zero pressure gradient. On a real wing none of the three holds
    exactly; the pressure-gradient part is what the Nash–Bradshaw
    magnification factor is for (:mod:`cfd_aq.core.trainee`).

    Args:
        etat: local flow state.
        distance_bord_attaque: run length x of the turbulent layer [m].
        temperature_paroi: wall temperature [K]; adiabatic if omitted.
    """
    if distance_bord_attaque <= 0.0:
        raise ValueError(
            f"la distance au bord d'attaque doit être > 0 m (reçue {distance_bord_attaque})"
        )
    t_paroi = (
        temperature_paroi if temperature_paroi is not None else temperature_paroi_adiabatique(etat)
    )
    t_etoile = temperature_reference_eckert(etat, t_paroi)
    # p est constante à travers la couche limite : ρ* suit T* à pression figée.
    rho_etoile = etat.pression / (etat.r_gaz * t_etoile)
    mu_etoile = viscosite_sutherland(t_etoile)
    re_etoile = rho_etoile * etat.vitesse * distance_bord_attaque / mu_etoile
    # float(...) : typeshed type « float ** float » comme Any (le résultat peut
    # être complexe pour une base négative), ce qui n'est pas le cas ici.
    cf_etoile = 0.0592 * float(re_etoile**-0.2)
    return cf_etoile * rho_etoile / etat.masse_volumique


def epaisseur_plaque_plane(
    etat: EtatLocal,
    distance_bord_attaque: float,
    temperature_paroi: float | None = None,
) -> float:
    """Boundary-layer thickness δ [m], same 1/7-power basis as :func:`cf_plaque_plane`.

    ``δ = 0.37·x·Re*_x^(-0.2)``. Only used to check the immersion ratio h/δ
    against the validity domain of the correlations; it never enters the drag.
    """
    t_paroi = (
        temperature_paroi if temperature_paroi is not None else temperature_paroi_adiabatique(etat)
    )
    t_etoile = temperature_reference_eckert(etat, t_paroi)
    rho_etoile = etat.pression / (etat.r_gaz * t_etoile)
    mu_etoile = viscosite_sutherland(t_etoile)
    re_etoile = rho_etoile * etat.vitesse * distance_bord_attaque / mu_etoile
    return 0.37 * distance_bord_attaque * float(re_etoile**-0.2)


@dataclass(frozen=True)
class CoucheLimite:
    """The undisturbed boundary layer, reduced to what the correlations need.

    Attributes:
        cisaillement_paroi: τ_w [Pa].
        cf: local skin-friction coefficient τ_w/q_e [-].
        vitesse_frottement: u_τ = √(τ_w/ρ_w) [m/s].
        viscosite_cinematique_paroi: ν_w = μ_w/ρ_w [m²/s].
        temperature_paroi: T_w [K].
        epaisseur: δ [m], or None when it was not supplied.
    """

    cisaillement_paroi: float
    cf: float
    vitesse_frottement: float
    viscosite_cinematique_paroi: float
    temperature_paroi: float
    epaisseur: float | None = None

    def h_plus(self, hauteur: float) -> float:
        """Roughness Reynolds number h⁺ = u_τ·h/ν_w of a step of height ``hauteur`` [m]."""
        if hauteur <= 0.0:
            raise ValueError(f"la hauteur de marche doit être > 0 m (reçue {hauteur})")
        return self.vitesse_frottement * hauteur / self.viscosite_cinematique_paroi

    def immersion(self, hauteur: float) -> float | None:
        """Immersion ratio h/δ, or None when δ is unknown."""
        if self.epaisseur is None:
            return None
        return hauteur / self.epaisseur

    # --- constructeurs ----------------------------------------------------
    @classmethod
    def depuis_cisaillement(
        cls,
        etat: EtatLocal,
        cisaillement_paroi: float,
        temperature_paroi: float | None = None,
        epaisseur: float | None = None,
    ) -> CoucheLimite:
        """Build from a measured or computed wall shear stress [Pa].

        The accurate path: nothing is correlated, τ_w is taken as given.
        """
        if cisaillement_paroi <= 0.0:
            raise ValueError(f"τ_w doit être > 0 Pa (reçu {cisaillement_paroi})")
        t_paroi = (
            temperature_paroi
            if temperature_paroi is not None
            else temperature_paroi_adiabatique(etat)
        )
        # La pression est constante à travers la couche limite ; ρ_w suit T_w.
        rho_paroi = etat.pression / (etat.r_gaz * t_paroi)
        mu_paroi = viscosite_sutherland(t_paroi)
        return cls(
            cisaillement_paroi=cisaillement_paroi,
            cf=cisaillement_paroi / etat.pression_dynamique,
            vitesse_frottement=math.sqrt(cisaillement_paroi / rho_paroi),
            viscosite_cinematique_paroi=mu_paroi / rho_paroi,
            temperature_paroi=t_paroi,
            epaisseur=epaisseur,
        )

    @classmethod
    def depuis_cf(
        cls,
        etat: EtatLocal,
        cf: float,
        temperature_paroi: float | None = None,
        epaisseur: float | None = None,
    ) -> CoucheLimite:
        """Build from a skin-friction coefficient C_fe = τ_w/q_e [-]."""
        if cf <= 0.0:
            raise ValueError(f"Cf doit être > 0 (reçu {cf})")
        return cls.depuis_cisaillement(
            etat,
            cisaillement_paroi=cf * etat.pression_dynamique,
            temperature_paroi=temperature_paroi,
            epaisseur=epaisseur,
        )

    @classmethod
    def plaque_plane(
        cls,
        etat: EtatLocal,
        distance_bord_attaque: float,
        temperature_paroi: float | None = None,
    ) -> CoucheLimite:
        """Build from the flat-plate correlation at a run length x [m]."""
        cf = cf_plaque_plane(etat, distance_bord_attaque, temperature_paroi)
        epaisseur = epaisseur_plaque_plane(etat, distance_bord_attaque, temperature_paroi)
        return cls.depuis_cf(etat, cf, temperature_paroi=temperature_paroi, epaisseur=epaisseur)
