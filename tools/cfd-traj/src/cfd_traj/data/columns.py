"""Column roles: how a trajectory column earns its place in the plan.

This is where the genericity of the tool lives. The CSV files carry eight
mandatory columns plus **any number of extra parameter columns under any
names**; nothing in this module -- or anywhere downstream -- may key off a
particular name such as ``PARA1``. What a column *is* has to be decided from
its values, or declared by the user in the study file.

Five roles:

``principal``
    A grid dimension in its own right, sampled at ``levels`` levels per band.
``conditionnel``
    Strongly tied to Mach, so it is not a free dimension of the hyperspace but
    a parameter conditioned on the band: few levels, bounds recomputed band by
    band.
``discret``
    A two-level factor rather than a continuous axis (a boundary-layer state, a
    configuration switch), applied to a subset of the nodes.
``mecanique``
    Covers a *declared mechanical range*, never the trajectory range. This is
    what the control deflections do: restricting them to the values the current
    guidance law commands would make the database circular and forbid any
    evolution of the guidance law.
``ignore``
    Present in the files, excluded from the analysis and from the plan.

Auto-detection exists so the tool is usable on an unknown lot straight away,
but it is a heuristic and it will sometimes be wrong. Every auto-detected role
is therefore reported in yellow together with the rule and the measured
statistic that produced it, and an explicit declaration in the study file
always wins.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import ArrayLike, NDArray

from cfd_traj.core.stats import spearman, suggest_log_scale


class Role(enum.StrEnum):
    """What a column does in the design of experiments."""

    PRINCIPAL = "principal"
    CONDITIONNEL = "conditionnel"
    DISCRET = "discret"
    MECANIQUE = "mecanique"
    IGNORE = "ignore"


class Scale(enum.StrEnum):
    """Scale on which bounds, levels and standardisation are computed."""

    LINEAIRE = "lineaire"
    LOG = "log"


#: Columns every trajectory file must carry, in canonical order.
REQUIRED_COLUMNS: tuple[str, ...] = (
    "time",
    "Mach",
    "Altitude",
    "alpha",
    "beta",
    "dl",
    "dm",
    "dn",
)

#: Control-surface deflections: roll, pitch, yaw.
DEFLECTION_COLUMNS: tuple[str, ...] = ("dl", "dm", "dn")

#: Columns added by :mod:`cfd_traj.data.derive`.
DERIVED_COLUMNS: tuple[str, ...] = (
    "alpha_tot",
    "phi",
    "phi_fold",
    "phi_defined",
    "p_inf",
    "T_inf",
    "rho_inf",
    "a_inf",
    "mu_inf",
    "V_inf",
    "q_inf",
    "Re_m",
    "Re_ref",
)

#: Name of the column identifying which shot a row came from.
SHOT_COLUMN: str = "tir"

#: Names a user column may not take, because they mean something else here.
RESERVED_COLUMNS: frozenset[str] = frozenset({SHOT_COLUMN, *DERIVED_COLUMNS})

#: Default number of levels per role.
DEFAULT_LEVELS: Mapping[Role, int] = {
    Role.PRINCIPAL: 5,
    Role.CONDITIONNEL: 3,
    Role.DISCRET: 2,
    Role.MECANIQUE: 3,
    Role.IGNORE: 1,
}

#: Above this |Spearman| against Mach, a column is conditioned on Mach rather
#: than treated as a free dimension. The most arbitrary constant of the design:
#: the measured value is always displayed so the user can override knowingly.
CONDITIONAL_RHO: float = 0.7

#: At or below this many distinct finite values, a column is a discrete factor.
MAX_DISCRETE_LEVELS: int = 2

#: Fallback mechanical range for a deflection column when none is declared.
MECHANICAL_RANGE_FACTOR: float = 1.5

#: Levels given to an *auto-detected* generic column. Deliberately fewer than
#: the default for a declared dimension: the tool has no idea yet whether the
#: column deserves to be a grid axis at all, and an over-generous guess is what
#: makes a tensor plan explode before the user has read a single report.
AUTO_LEVELS: int = 3


@dataclass(frozen=True)
class ColumnSpec:
    """Everything the engine needs to know about one column."""

    name: str
    role: Role
    levels: int | None = None
    scale: Scale = Scale.LINEAIRE
    unit: str = ""
    label: str = ""
    mechanical_range: tuple[float, float] | None = None
    physical_min: float | None = None
    q_low: float | None = None
    q_high: float | None = None
    margin: float | None = None
    auto: bool = False
    detection: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a column spec needs a name")
        if not isinstance(self.role, Role):
            raise ValueError(
                f"« {self.name} » : rôle {self.role!r} inconnu ; "
                f"valeurs valides : {[r.value for r in Role]}"
            )
        if not isinstance(self.scale, Scale):
            raise ValueError(
                f"« {self.name} » : échelle {self.scale!r} inconnue ; "
                f"valeurs valides : {[s.value for s in Scale]}"
            )
        if self.levels is not None and self.levels <= 0:
            raise ValueError(f"« {self.name} » : niveaux doit être positif, reçu {self.levels}")
        if self.role is Role.MECANIQUE and self.mechanical_range is None:
            raise ValueError(
                f"« {self.name} » : le rôle « mecanique » exige une plage déclarée (clé « plage »)"
            )
        if self.mechanical_range is not None:
            low, high = self.mechanical_range
            if not (np.isfinite(low) and np.isfinite(high)):
                raise ValueError(f"« {self.name} » : plage non finie {self.mechanical_range}")
            if high <= low:
                raise ValueError(
                    f"« {self.name} » : plage inversée ou vide {self.mechanical_range}"
                )
        if self.q_low is not None or self.q_high is not None:
            lo = 0.0 if self.q_low is None else self.q_low
            hi = 1.0 if self.q_high is None else self.q_high
            if not 0.0 <= lo < hi <= 1.0:
                raise ValueError(
                    f"« {self.name} » : quantiles invalides ({lo}, {hi}) ; "
                    f"il faut 0 <= bas < haut <= 1"
                )
        if self.margin is not None and self.margin < 0.0:
            raise ValueError(f"« {self.name} » : marge négative {self.margin}")

    @property
    def n_levels(self) -> int:
        """Number of levels, falling back to the role's default."""
        return self.levels if self.levels is not None else DEFAULT_LEVELS[self.role]

    @property
    def is_grid_axis(self) -> bool:
        """True for the roles that define the conditional box of a band."""
        return self.role in (Role.PRINCIPAL, Role.CONDITIONNEL)

    @property
    def is_active(self) -> bool:
        """True for every role that takes part in the analysis."""
        return self.role is not Role.IGNORE

    @property
    def log_scaled(self) -> bool:
        """True when bounds and levels are computed in log space."""
        return self.scale is Scale.LOG

    @property
    def display(self) -> str:
        """Human label: name, unit, and free-text label when present."""
        bits = [self.name]
        if self.unit:
            bits.append(f"[{self.unit}]")
        if self.label:
            bits.append(self.label)
        return " ".join(bits)


#: Roles forced on the mandatory and derived columns, whatever their values.
#: ``Altitude``, ``alpha`` and ``beta`` are absorbed by the derived quantities
#: (Re_ref, alpha_tot, phi_fold) and would otherwise be counted twice.
FORCED_ROLES: Mapping[str, tuple[Role, Scale]] = {
    "time": (Role.IGNORE, Scale.LINEAIRE),
    "Mach": (Role.PRINCIPAL, Scale.LINEAIRE),
    "Altitude": (Role.IGNORE, Scale.LINEAIRE),
    "alpha": (Role.IGNORE, Scale.LINEAIRE),
    "beta": (Role.IGNORE, Scale.LINEAIRE),
    "alpha_tot": (Role.PRINCIPAL, Scale.LINEAIRE),
    "phi_fold": (Role.PRINCIPAL, Scale.LINEAIRE),
    "phi": (Role.IGNORE, Scale.LINEAIRE),
    "phi_defined": (Role.IGNORE, Scale.LINEAIRE),
    "Re_ref": (Role.DISCRET, Scale.LOG),
    "p_inf": (Role.IGNORE, Scale.LINEAIRE),
    "T_inf": (Role.IGNORE, Scale.LINEAIRE),
    "rho_inf": (Role.IGNORE, Scale.LINEAIRE),
    "a_inf": (Role.IGNORE, Scale.LINEAIRE),
    "mu_inf": (Role.IGNORE, Scale.LINEAIRE),
    "V_inf": (Role.IGNORE, Scale.LINEAIRE),
    "q_inf": (Role.IGNORE, Scale.LINEAIRE),
    "Re_m": (Role.IGNORE, Scale.LINEAIRE),
}

#: Physical floors applied to the derived columns when building their bounds.
PHYSICAL_MINIMA: Mapping[str, float] = {
    "Mach": 0.0,
    "alpha_tot": 0.0,
    "phi_fold": 0.0,
    "Re_ref": 0.0,
    "Re_m": 0.0,
    "q_inf": 0.0,
}


@dataclass(frozen=True)
class RoleDetection:
    """Why a role was chosen, so the report can justify it."""

    role: Role
    scale: Scale
    reason: str
    rho_mach: float = 0.0
    n_unique: int = 0


def detect_role(
    name: str,
    values: ArrayLike,
    mach: ArrayLike,
    *,
    max_discrete_levels: int = MAX_DISCRETE_LEVELS,
    conditional_rho: float = CONDITIONAL_RHO,
) -> RoleDetection:
    """Infer the role of a column from its values alone.

    Never looks at ``name`` except to honour the forced roles of the mandatory
    and derived columns: two columns holding the same values must get the same
    role whatever they are called.
    """
    if name in FORCED_ROLES:
        role, scale = FORCED_ROLES[name]
        return RoleDetection(role=role, scale=scale, reason="colonne réservée : rôle imposé")

    if name in DEFLECTION_COLUMNS:
        return RoleDetection(
            role=Role.MECANIQUE,
            scale=Scale.LINEAIRE,
            reason="braquage : plage mécanique, pas la plage trajectoire",
        )

    raw = np.asarray(values, dtype=np.float64).ravel()
    finite = raw[np.isfinite(raw)]
    n_unique = int(np.unique(finite).size) if finite.size else 0

    if n_unique <= max_discrete_levels:
        return RoleDetection(
            role=Role.DISCRET,
            scale=Scale.LINEAIRE,
            reason=f"{n_unique} valeur(s) distincte(s) : facteur discret",
            n_unique=n_unique,
        )

    scale = Scale.LOG if suggest_log_scale(finite) else Scale.LINEAIRE
    rho = spearman(raw, mach)

    if abs(rho) >= conditional_rho:
        return RoleDetection(
            role=Role.CONDITIONNEL,
            scale=scale,
            reason=f"corrélation au Mach ρ = {rho:+.2f} : conditionnée au Mach",
            rho_mach=rho,
            n_unique=n_unique,
        )

    return RoleDetection(
        role=Role.PRINCIPAL,
        scale=scale,
        reason=f"corrélation au Mach ρ = {rho:+.2f} : dimension propre",
        rho_mach=rho,
        n_unique=n_unique,
    )


def default_mechanical_range(values: ArrayLike) -> tuple[float, float]:
    """Fallback mechanical range: the observed excursion, widened and rounded."""
    raw = np.asarray(values, dtype=np.float64).ravel()
    finite = raw[np.isfinite(raw)]
    peak = float(np.max(np.abs(finite))) if finite.size else 1.0
    widened = max(MECHANICAL_RANGE_FACTOR * peak, 1.0)
    rounded = float(np.ceil(widened))
    return (-rounded, rounded)


class ColumnError(ValueError):
    """A column declaration that does not match the data."""


def build_specs(
    available: Sequence[str],
    column_values: Mapping[str, NDArray[np.float64]],
    declared: Mapping[str, ColumnSpec],
    *,
    mach_key: str = "Mach",
) -> tuple[tuple[ColumnSpec, ...], tuple[str, ...]]:
    """Merge declared specs with auto-detected ones, in the order of ``available``.

    Returns the specs and the notes to display. A declaration naming a column
    that is not in the data is an error, and the message lists what is actually
    there -- a typo in a study file must not silently produce a plan with a
    missing dimension.
    """
    available = tuple(available)
    unknown = sorted(set(declared) - set(available))
    if unknown:
        raise ColumnError(
            f"colonne(s) déclarée(s) mais absente(s) des fichiers : {unknown} ; "
            f"colonnes présentes : {list(available)}"
        )

    mach = column_values.get(mach_key, np.zeros(0, dtype=np.float64))
    specs: list[ColumnSpec] = []
    notes: list[str] = []

    for name in available:
        if name == SHOT_COLUMN:
            continue
        values = column_values.get(name, np.zeros(0, dtype=np.float64))

        if name in declared:
            spec = declared[name]
            if spec.role is Role.MECANIQUE and spec.mechanical_range is None:
                spec = replace(spec, mechanical_range=default_mechanical_range(values))
            specs.append(replace(spec, name=name, auto=False))
            continue

        detection = detect_role(name, values, mach)
        # The mechanical range has to be resolved before construction: a
        # MECANIQUE spec without one is refused by ColumnSpec on purpose.
        fallback_range = (
            default_mechanical_range(values) if detection.role is Role.MECANIQUE else None
        )
        generic = name not in FORCED_ROLES and name not in DEFLECTION_COLUMNS
        spec = ColumnSpec(
            name=name,
            role=detection.role,
            levels=AUTO_LEVELS if generic and detection.role.value in ("principal",) else None,
            scale=detection.scale,
            mechanical_range=fallback_range,
            physical_min=PHYSICAL_MINIMA.get(name),
            auto=True,
            detection=detection.reason,
        )
        if fallback_range is not None:
            notes.append(
                f"« {name} » : aucune plage mécanique déclarée, "
                f"repli sur {fallback_range} — à confirmer dans l'étude"
            )
        if spec.role is not Role.IGNORE and name not in FORCED_ROLES:
            notes.append(f"« {name} » : rôle auto-détecté « {spec.role} » ({detection.reason})")
        specs.append(spec)

    return tuple(specs), tuple(notes)


def active_specs(specs: Sequence[ColumnSpec]) -> tuple[ColumnSpec, ...]:
    """The specs that take part in the analysis."""
    return tuple(s for s in specs if s.is_active)


def grid_axes(
    specs: Sequence[ColumnSpec], *, exclude: Sequence[str] = ()
) -> tuple[ColumnSpec, ...]:
    """The specs that define the conditional box of a band.

    ``phi_fold`` is excluded by default at the call site: its levels come from
    the symmetry group, not from conditional bounds.
    """
    skip = set(exclude)
    return tuple(s for s in specs if s.is_grid_axis and s.name not in skip)
