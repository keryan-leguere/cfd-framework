"""Atmosphere access, delegated to the sibling package ``cfd-atm``.

``cfd-atm`` is the framework's atmosphere block: it maps an altitude
(geometric, geopotential or pressure) and a temperature model (ISA, ISA ± ΔT,
or a custom T(H) profile) to the air state, and converts between Mach, Vc/CAS,
EAS and TAS in subsonic *and* supersonic flow. cfd-aq uses it whenever it is
installed, which is what makes :func:`conditions` accept a hot day, a pressure
altitude or a calibrated airspeed rather than only a geometric altitude and a
Mach number.

``cfd-atm`` is a sibling package in this repository, not a PyPI release, so it
cannot be declared as a normal dependency. Install it alongside cfd-aq with::

    pip install -e tools/cfd-atm

**Without it**, cfd-aq falls back to a built-in ISA — 0 to 32 km, geometric
altitude, no ΔT, no airspeed conversion — so the package stays deployable on
its own. Anything the fallback cannot do raises with the install command in
the message rather than quietly returning a wrong number. The two are pinned
against each other by ``tests/core/test_atmosphere.py``: the fallback is a
degraded entry point, never a second model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from types import ModuleType
from typing import cast

__all__ = [
    "ALTITUDE_MAX",
    "HAS_CFD_ATM",
    "PointAtmospherique",
    "TypeAltitude",
    "conditions",
    "etat_isa",
    "get_cfd_atm",
    "mach_depuis_vitesse",
]

#: Constante spécifique de l'air sec [J/(kg·K)].
R_AIR = 287.05287

#: Accélération de la pesanteur de référence [m/s²].
G0 = 9.80665

#: Rayon terrestre conventionnel de l'ISA [m], pour l'altitude géopotentielle.
RAYON_TERRE = 6356766.0

#: Plafond du modèle de repli [m]. ``cfd-atm`` va bien plus haut.
ALTITUDE_MAX = 32000.0

#: Les trois façons de désigner une altitude, telles que ``cfd-atm`` les traite.
TypeAltitude = str

_TYPES_ALTITUDE = ("geometrique", "geopotentielle", "pression")

# (altitude géopotentielle de base [m], T base [K], p base [Pa], gradient [K/m])
_COUCHES = (
    (0.0, 288.15, 101325.0, -0.0065),
    (11000.0, 216.65, 22632.06, 0.0),
    (20000.0, 216.65, 5474.889, 0.001),
)


@lru_cache(maxsize=1)
def get_cfd_atm() -> ModuleType | None:
    """Return the :mod:`cfd_atm` module, or None when it is not installed."""
    try:
        import cfd_atm
    except ImportError:
        return None
    # cfd-atm ne livre pas de marqueur py.typed : mypy voit le module comme Any.
    return cast(ModuleType, cfd_atm)


HAS_CFD_ATM: bool = get_cfd_atm() is not None


@dataclass(frozen=True)
class PointAtmospherique:
    """Static air conditions at one altitude.

    Attributes:
        temperature: static temperature [K].
        pression: static pressure [Pa].
        modele: label of the temperature model used ("ISA", "ISA+15"…).
        source: which package produced it, ``"cfd-atm"`` or ``"repli"``.
    """

    temperature: float
    pression: float
    modele: str
    source: str


def _exiger_cfd_atm(fonctionnalite: str) -> ModuleType:
    module = get_cfd_atm()
    if module is None:
        raise RuntimeError(
            f"{fonctionnalite} demande le paquet cfd-atm, qui n'est pas installé. "
            "Installer le paquet frère :  pip install -e tools/cfd-atm"
        )
    return module


def _isa_repli(altitude: float) -> tuple[float, float]:
    """Static temperature [K] and pressure [Pa] of the built-in ISA fallback."""
    if not 0.0 <= altitude <= ALTITUDE_MAX:
        raise ValueError(
            f"altitude hors du modèle ISA de repli (0 à {ALTITUDE_MAX:.0f} m) : "
            f"{altitude} m. Installer cfd-atm pour aller plus haut : "
            "pip install -e tools/cfd-atm"
        )
    # Altitude géopotentielle : c'est elle que tabule l'ISA.
    h = RAYON_TERRE * altitude / (RAYON_TERRE + altitude)

    base_h, base_t, base_p, gradient = _COUCHES[0]
    for couche in _COUCHES:
        if h >= couche[0]:
            base_h, base_t, base_p, gradient = couche
        else:
            break

    dh = h - base_h
    if gradient == 0.0:
        temperature = base_t
        pression = base_p * math.exp(-G0 * dh / (R_AIR * base_t))
    else:
        temperature = base_t + gradient * dh
        pression = base_p * float((temperature / base_t) ** (-G0 / (gradient * R_AIR)))
    return temperature, pression


def conditions(
    altitude: float,
    delta_isa: float = 0.0,
    type_altitude: TypeAltitude = "geometrique",
) -> PointAtmospherique:
    """Static conditions at ``altitude`` [m].

    Args:
        altitude: altitude in metres, read according to ``type_altitude``.
        delta_isa: constant temperature offset ΔT [K] on top of the ISA.
            Needs ``cfd-atm``.
        type_altitude: ``"geometrique"``, ``"geopotentielle"`` or
            ``"pression"``. The last two need ``cfd-atm``.

    Raises:
        ValueError: unknown ``type_altitude``, or altitude out of the
            fallback's range.
        RuntimeError: a feature was asked for that only ``cfd-atm`` provides.
    """
    if type_altitude not in _TYPES_ALTITUDE:
        raise ValueError(
            f"type d'altitude « {type_altitude} » inconnu. "
            f"Types admis : {', '.join(_TYPES_ALTITUDE)}."
        )

    module = get_cfd_atm()
    if module is None:
        if delta_isa != 0.0:
            _exiger_cfd_atm("Un écart ΔT par rapport à l'ISA")
        if type_altitude != "geometrique":
            _exiger_cfd_atm(f"Une altitude « {type_altitude} »")
        temperature, pression = _isa_repli(altitude)
        return PointAtmospherique(temperature, pression, "ISA", "repli")

    modele = (
        module.AtmosphereModel.isa()
        if delta_isa == 0.0
        else module.AtmosphereModel.isa_offset(delta_isa)
    )
    if type_altitude == "geometrique":
        etat = modele.state_from_geometric(altitude)
    elif type_altitude == "geopotentielle":
        etat = modele.state_from_geopotential(altitude)
    else:
        etat = modele.state_from_pressure_altitude(altitude)
    return PointAtmospherique(float(etat.t), float(etat.p), str(modele.label), "cfd-atm")


def mach_depuis_vitesse(
    point: PointAtmospherique,
    vitesse_conventionnelle: float | None = None,
    vitesse_vraie: float | None = None,
    vitesse_equivalente: float | None = None,
) -> float:
    """Mach number from an airspeed, through ``cfd-atm``.

    Exactly one of the three must be given, in m/s. Vc (calibrated) is the
    one a cockpit reads; the conversion is the compressible one, with the
    Rayleigh pitot relation above M = 1.

    Raises:
        ValueError: none or several airspeeds given.
        RuntimeError: ``cfd-atm`` is not installed.
    """
    fournis = {
        "vitesse_conventionnelle": vitesse_conventionnelle,
        "vitesse_vraie": vitesse_vraie,
        "vitesse_equivalente": vitesse_equivalente,
    }
    nommes = [nom for nom, valeur in fournis.items() if valeur is not None]
    if len(nommes) != 1:
        raise ValueError(
            "donner exactement une vitesse parmi vitesse_conventionnelle, "
            f"vitesse_vraie et vitesse_equivalente (reçu : {', '.join(nommes) or 'aucune'})."
        )
    module = _exiger_cfd_atm("La conversion d'une vitesse en nombre de Mach")
    jeu = module.airspeeds(
        point.pression,
        point.temperature,
        cas=vitesse_conventionnelle,
        tas=vitesse_vraie,
        eas=vitesse_equivalente,
    )
    return float(jeu.mach)


def etat_isa(altitude: float) -> tuple[float, float]:
    """Static temperature [K] and pressure [Pa] of the plain ISA at ``altitude`` [m].

    Kept as the short form of ``conditions(altitude)``; it goes through
    ``cfd-atm`` when that package is installed.
    """
    point = conditions(altitude)
    return point.temperature, point.pression
