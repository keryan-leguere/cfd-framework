"""Generic parameter columns: any number, any names, a handful of shapes.

The tool's central requirement is that it never assumes anything about the
extra columns of the CSV files. The generator has to hold up its end of that
bargain: it emits whatever column names it is given, with whatever shape is
asked for, and nothing downstream may recognise them by name.

The archetypes exist to cover the *kinds* of behaviour the role auto-detection
has to tell apart -- one that tracks Mach (and must come out ``conditionnel``),
one that tracks altitude, ones that are independent of the flight (and must
come out ``principal``), and one that only ever takes two values (``discret``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

#: Archetype name -> one-line description, used by the CLI help and the report.
ARCHETYPES: dict[str, str] = {
    "rampe": "décroissance monotone, forte au début puis lente",
    "plateau_bruite": "valeur nominale constante, bruit blanc autour",
    "sinus_amorti": "oscillation dont l'amplitude décroît",
    "correle_altitude": "suit l'altitude, donc corrélée au temps de vol",
    "correle_mach": "suit le Mach : c'est l'archétype conditionnel au Mach",
    "discret": "deux valeurs seulement, commutation en cours de vol",
}


class ArchetypeError(ValueError):
    """An unknown parameter archetype."""


@dataclass(frozen=True)
class ParameterModel:
    """One generic parameter column to generate."""

    name: str
    archetype: str = "plateau_bruite"
    nominal: float = 100.0
    amplitude: float = 0.15

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a parameter column needs a name")
        if self.archetype not in ARCHETYPES:
            raise ArchetypeError(
                f"archétype « {self.archetype} » inconnu pour la colonne « {self.name} » ; "
                f"valeurs valides : {sorted(ARCHETYPES)}"
            )


def generate(
    model: ParameterModel,
    *,
    time_s: NDArray[np.float64],
    mach: NDArray[np.float64],
    altitude_m: NDArray[np.float64],
    rng: np.random.Generator,
    scale: float = 1.0,
) -> NDArray[np.float64]:
    """Produce one column of values for one shot.

    ``scale`` is the shot-to-shot dispersion multiplier: it is what makes the
    lot a dispersed lot rather than the same curve repeated.
    """
    n = time_s.size
    span = max(float(time_s[-1] - time_s[0]), 1e-9)
    phase = (time_s - time_s[0]) / span
    nominal = model.nominal * scale
    noise = model.amplitude * nominal

    match model.archetype:
        case "rampe":
            values = nominal * (1.0 - 0.85 * phase**0.6) + rng.normal(0.0, 0.02 * noise, n)
        case "plateau_bruite":
            values = nominal + rng.normal(0.0, noise, n)
        case "sinus_amorti":
            values = nominal * np.exp(-2.5 * phase) * np.sin(9.0 * np.pi * phase) + rng.normal(
                0.0, 0.02 * noise, n
            )
        case "correle_altitude":
            reach = max(float(np.max(altitude_m)), 1.0)
            values = nominal * (0.2 + 1.6 * altitude_m / reach) + rng.normal(0.0, 0.01 * noise, n)
        case "correle_mach":
            values = nominal * (0.25 + 0.9 * mach) + rng.normal(0.0, 0.01 * noise, n)
        case "discret":
            values = np.where(phase < 0.45, nominal, 2.0 * nominal).astype(np.float64)
        case _:  # pragma: no cover - guarded by ParameterModel.__post_init__
            raise ArchetypeError(f"archétype « {model.archetype} » inconnu")

    return np.asarray(values, dtype=np.float64)


def parse_models(text: str) -> tuple[ParameterModel, ...]:
    """Parse a ``"NOM:archetype,AUTRE:archetype"`` command-line specification.

    The archetype may be omitted, in which case the default applies. Column
    names are taken verbatim, spaces and accents included.
    """
    models: list[ParameterModel] = []
    for chunk in text.split(","):
        item = chunk.strip()
        if not item:
            continue
        if ":" in item:
            name, _, archetype = item.partition(":")
            name, archetype = name.strip(), archetype.strip()
        else:
            name, archetype = item, "plateau_bruite"
        if not name:
            raise ValueError(f"spécification de paramètre invalide : « {chunk} »")
        models.append(ParameterModel(name=name, archetype=archetype))
    if not models:
        raise ValueError("aucun paramètre valide dans la spécification")
    return tuple(models)


def default_models(n: int, *, prefix: str = "PARA") -> tuple[ParameterModel, ...]:
    """``n`` columns named ``PARA1..PARAn``, cycling deterministically over archetypes."""
    if n < 0:
        raise ValueError(f"n must be non-negative, got {n}")
    order = (
        "correle_mach",
        "plateau_bruite",
        "correle_altitude",
        "rampe",
        "sinus_amorti",
        "discret",
    )
    return tuple(
        ParameterModel(name=f"{prefix}{i + 1}", archetype=order[i % len(order)]) for i in range(n)
    )
