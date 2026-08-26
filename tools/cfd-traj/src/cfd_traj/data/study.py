"""Study definition: one YAML file describing a lot and the plan to draw from it.

A single self-documenting file is what makes this shareable across a
department -- it can be committed next to the CSV files, diffed, and reviewed
line by line. Unknown sections and unknown keys are errors, not warnings: a
typo in a study file must never silently produce a plan with a missing
dimension.

Schema (French keys; only ``etude`` and ``reference`` are required)::

    etude:
      nom: "LOT_MC_2026_REV_B"
      source: "TRAJECTOIRES"        # directory, glob or list, relative to this file
      sortie: "SORTIE"

    reference:
      longueur_m: 2.5               # reference length of the Reynolds number
      surface_m2: 0.049             # optional, documentation only

    atmosphere:
      delta_t_K: 0.0

    symetrie:
      groupe: "C4v"                 # C4v | C4 | Cs | C1 | Cinfv
      plan_reference_deg: 0.0
      n_azimuts: 3

    bandes:
      bornes: [0.5, 0.8, 0.95, 1.2, 1.8, 2.5, 3.2]
      # or, instead of « bornes »:
      # n_bandes: 8
      # transsonique: [0.8, 1.2]
      # raffinement_transsonique: 2
      points_min: 30

    enveloppe:
      quantile_bas: 0.001
      quantile_haut: 0.999
      marge: 0.05

    parametres:                     # indexed by CSV column name; any name, any count
      PARA1: { role: conditionnel, niveaux: 3, echelle: log }
      dl:    { role: mecanique, plage: [-20.0, 20.0] }

    doe:
      methode: "tensoriel"          # tensoriel | lhs
      coins: true
      n_lhs_par_bande: 24
      graine: 12345
      noeuds_max: 2000
      fraction_discret: 0.25
      braquages:
        - { nom: "neutre", dl: 0.0, dm: 0.0, dn: 0.0 }
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from cfd_traj._compat import StrEnum, pairwise
from cfd_traj.core.adim import Reference
from cfd_traj.core.symmetry import (
    DeflectionSymmetry,
    SymmetryGroup,
    SymmetrySpec,
    classify_deflection,
)
from cfd_traj.data.columns import ColumnSpec, Role, Scale

TOP_LEVEL_SECTIONS: frozenset[str] = frozenset(
    {"etude", "reference", "atmosphere", "symetrie", "bandes", "enveloppe", "parametres", "doe"}
)


class StudyError(ValueError):
    """A study file that cannot be understood.

    Carries the offending file path so the CLI can point at it directly.
    """

    def __init__(self, message: str, *, path: Path | None = None) -> None:
        self.path = path
        super().__init__(f"{path} : {message}" if path is not None else message)


class DoeMethod(StrEnum):
    """How the nodes of a band are placed inside its conditional box."""

    TENSORIEL = "tensoriel"
    LHS = "lhs"


@dataclass(frozen=True)
class BandSpec:
    """How the Mach axis is cut into bands."""

    edges: tuple[float, ...] | None = None
    n_bands: int = 8
    transonic: tuple[float, float] = (0.8, 1.2)
    transonic_refinement: int = 2
    min_points: int = 30

    def __post_init__(self) -> None:
        if self.edges is not None:
            if len(self.edges) < 2:
                raise ValueError(f"« bandes.bornes » : au moins deux bornes, reçu {self.edges}")
            if any(b <= a for a, b in pairwise(self.edges)):
                raise ValueError(
                    f"« bandes.bornes » : bornes non strictement croissantes {self.edges}"
                )
        if self.n_bands <= 0:
            raise ValueError(f"« bandes.n_bandes » doit être positif, reçu {self.n_bands}")
        if self.transonic[1] <= self.transonic[0]:
            raise ValueError(f"« bandes.transsonique » : intervalle vide {self.transonic}")
        if self.transonic_refinement < 1:
            raise ValueError(
                f"« bandes.raffinement_transsonique » doit valoir au moins 1, "
                f"reçu {self.transonic_refinement}"
            )
        if self.min_points < 1:
            raise ValueError(f"« bandes.points_min » doit être positif, reçu {self.min_points}")


@dataclass(frozen=True)
class EnvelopeSpec:
    """Quantiles and margin used to build the conditional bounds."""

    q_low: float = 0.001
    q_high: float = 0.999
    margin: float = 0.05

    def __post_init__(self) -> None:
        if not 0.0 <= self.q_low < self.q_high <= 1.0:
            raise ValueError(
                f"« enveloppe » : quantiles invalides ({self.q_low}, {self.q_high}) ; "
                f"il faut 0 <= quantile_bas < quantile_haut <= 1"
            )
        if self.margin < 0.0:
            raise ValueError(f"« enveloppe.marge » doit être positive, reçu {self.margin}")


@dataclass(frozen=True)
class DeflectionSet:
    """One named set of control-surface deflections, used as a block of the plan."""

    name: str
    dl: float = 0.0
    dm: float = 0.0
    dn: float = 0.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("« doe.braquages » : chaque jeu de braquages doit porter un « nom »")

    @property
    def symmetry(self) -> DeflectionSymmetry:
        """What this set does to the wind-plane mirror."""
        return classify_deflection(self.dl, self.dm, self.dn)

    @property
    def values(self) -> tuple[float, float, float]:
        """The three deflections, in ``dl, dm, dn`` order."""
        return (self.dl, self.dm, self.dn)


NEUTRAL_DEFLECTION: DeflectionSet = DeflectionSet(name="neutre")


@dataclass(frozen=True)
class DoeSpec:
    """How the plan is built from the envelope."""

    method: DoeMethod = DoeMethod.TENSORIEL
    include_corners: bool = True
    n_lhs_per_band: int = 24
    seed: int = 12345
    max_nodes: int = 2000
    discrete_fraction: float = 0.25
    deflections: tuple[DeflectionSet, ...] = (NEUTRAL_DEFLECTION,)

    def __post_init__(self) -> None:
        if self.n_lhs_per_band <= 0:
            raise ValueError(
                f"« doe.n_lhs_par_bande » doit être positif, reçu {self.n_lhs_per_band}"
            )
        if self.max_nodes <= 0:
            raise ValueError(f"« doe.noeuds_max » doit être positif, reçu {self.max_nodes}")
        if not 0.0 <= self.discrete_fraction <= 1.0:
            raise ValueError(
                f"« doe.fraction_discret » doit être dans [0, 1], reçu {self.discrete_fraction}"
            )
        if not self.deflections:
            raise ValueError("« doe.braquages » : au moins un jeu de braquages est nécessaire")
        names = [d.name for d in self.deflections]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ValueError(f"« doe.braquages » : noms en double {duplicates}")


@dataclass(frozen=True)
class Study:
    """A fully parsed and validated study."""

    name: str
    source: str
    output_dir: str
    reference: Reference
    symmetry: SymmetrySpec
    bands: BandSpec
    envelope: EnvelopeSpec
    doe: DoeSpec
    declared_columns: Mapping[str, ColumnSpec] = field(default_factory=dict)
    delta_t_k: float = 0.0
    path: Path | None = None

    @property
    def base_dir(self) -> Path:
        """Directory relative paths in this study resolve against."""
        return self.path.parent if self.path is not None else Path()

    def resolved_source(self) -> Path:
        """The trajectory source, relative to the study file rather than the cwd."""
        source = Path(self.source)
        return source if source.is_absolute() else self.base_dir / source

    def resolved_output(self) -> Path:
        """The output directory, relative to the study file rather than the cwd."""
        out = Path(self.output_dir)
        return out if out.is_absolute() else self.base_dir / out


# --- parsing helpers -------------------------------------------------------


def _section(data: Mapping[str, Any], key: str, path: Path | None) -> dict[str, Any]:
    """One top-level section, as a mapping."""
    value = data.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise StudyError(f"« {key} » doit être une section, pas {type(value).__name__}", path=path)
    return dict(value)


def _reject_unknown(
    section: Mapping[str, Any], allowed: Collection[str], where: str, path: Path | None
) -> None:
    """Refuse a key that is not in the schema, listing what is."""
    unknown = sorted(set(section) - set(allowed))
    if unknown:
        raise StudyError(
            f"« {where} » : clé(s) inconnue(s) {unknown} ; clés valides : {sorted(allowed)}",
            path=path,
        )


def _as_float(value: Any, where: str, path: Path | None) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise StudyError(f"« {where} » : nombre attendu, reçu {value!r}", path=path) from exc


def _as_int(value: Any, where: str, path: Path | None) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise StudyError(f"« {where} » : entier attendu, reçu {value!r}", path=path) from exc


def _as_pair(value: Any, where: str, path: Path | None) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise StudyError(f"« {where} » : deux valeurs attendues, reçu {value!r}", path=path)
    return (_as_float(value[0], where, path), _as_float(value[1], where, path))


def _enum(kind: type[StrEnum], value: Any, where: str, path: Path | None) -> Any:
    try:
        return kind(str(value))
    except ValueError as exc:
        raise StudyError(
            f"« {where} » : valeur « {value} » inconnue ; "
            f"valeurs valides : {[m.value for m in kind]}",
            path=path,
        ) from exc


_COLUMN_KEYS = (
    "role",
    "niveaux",
    "echelle",
    "unite",
    "libelle",
    "plage",
    "min_physique",
    "quantile_bas",
    "quantile_haut",
    "marge",
)


def _parse_column(name: str, raw: Any, path: Path | None) -> ColumnSpec:
    """One entry of the ``parametres`` table."""
    if not isinstance(raw, dict):
        raise StudyError(
            f"« parametres.{name} » : section attendue, reçu {type(raw).__name__}", path=path
        )
    _reject_unknown(raw, _COLUMN_KEYS, f"parametres.{name}", path)

    if "role" not in raw:
        raise StudyError(f"« parametres.{name} » : clé « role » manquante", path=path)

    try:
        return ColumnSpec(
            name=name,
            role=_enum(Role, raw["role"], f"parametres.{name}.role", path),
            levels=_as_int(raw["niveaux"], f"parametres.{name}.niveaux", path)
            if "niveaux" in raw
            else None,
            scale=_enum(
                Scale, raw.get("echelle", Scale.LINEAIRE), f"parametres.{name}.echelle", path
            ),
            unit=str(raw.get("unite", "")),
            label=str(raw.get("libelle", "")),
            mechanical_range=_as_pair(raw["plage"], f"parametres.{name}.plage", path)
            if "plage" in raw
            else None,
            physical_min=_as_float(raw["min_physique"], f"parametres.{name}.min_physique", path)
            if "min_physique" in raw
            else None,
            q_low=_as_float(raw["quantile_bas"], f"parametres.{name}.quantile_bas", path)
            if "quantile_bas" in raw
            else None,
            q_high=_as_float(raw["quantile_haut"], f"parametres.{name}.quantile_haut", path)
            if "quantile_haut" in raw
            else None,
            margin=_as_float(raw["marge"], f"parametres.{name}.marge", path)
            if "marge" in raw
            else None,
        )
    except StudyError:
        raise
    except ValueError as exc:
        raise StudyError(str(exc), path=path) from exc


def _parse_deflections(raw: Any, path: Path | None) -> tuple[DeflectionSet, ...]:
    """The ``doe.braquages`` list."""
    if not isinstance(raw, list):
        raise StudyError(
            f"« doe.braquages » : liste attendue, reçu {type(raw).__name__}", path=path
        )
    sets: list[DeflectionSet] = []
    for i, item in enumerate(raw):
        where = f"doe.braquages[{i}]"
        if not isinstance(item, dict):
            raise StudyError(f"« {where} » : section attendue, reçu {item!r}", path=path)
        _reject_unknown(item, ("nom", "dl", "dm", "dn"), where, path)
        if "nom" not in item:
            raise StudyError(f"« {where} » : clé « nom » manquante", path=path)
        try:
            sets.append(
                DeflectionSet(
                    name=str(item["nom"]),
                    dl=_as_float(item.get("dl", 0.0), f"{where}.dl", path),
                    dm=_as_float(item.get("dm", 0.0), f"{where}.dm", path),
                    dn=_as_float(item.get("dn", 0.0), f"{where}.dn", path),
                )
            )
        except StudyError:
            raise
        except ValueError as exc:
            raise StudyError(str(exc), path=path) from exc
    return tuple(sets)


def parse_study(data: Mapping[str, Any], *, path: Path | None = None) -> Study:
    """Validate an in-memory study mapping. Testable without touching the disk."""
    if not isinstance(data, dict):
        raise StudyError(f"contenu YAML invalide : {type(data).__name__}", path=path)
    _reject_unknown(data, TOP_LEVEL_SECTIONS, "fichier d'étude", path)

    etude = _section(data, "etude", path)
    _reject_unknown(etude, ("nom", "source", "sortie"), "etude", path)
    for key in ("nom", "source"):
        if key not in etude:
            raise StudyError(f"« etude » : clé requise « {key} » manquante", path=path)

    ref_raw = _section(data, "reference", path)
    _reject_unknown(ref_raw, ("longueur_m", "surface_m2"), "reference", path)
    if "longueur_m" not in ref_raw:
        raise StudyError("« reference » : clé requise « longueur_m » manquante", path=path)

    atmosphere = _section(data, "atmosphere", path)
    _reject_unknown(atmosphere, ("delta_t_K",), "atmosphere", path)

    sym_raw = _section(data, "symetrie", path)
    _reject_unknown(sym_raw, ("groupe", "plan_reference_deg", "n_azimuts"), "symetrie", path)

    bands_raw = _section(data, "bandes", path)
    _reject_unknown(
        bands_raw,
        ("bornes", "n_bandes", "transsonique", "raffinement_transsonique", "points_min"),
        "bandes",
        path,
    )

    env_raw = _section(data, "enveloppe", path)
    _reject_unknown(env_raw, ("quantile_bas", "quantile_haut", "marge"), "enveloppe", path)

    doe_raw = _section(data, "doe", path)
    _reject_unknown(
        doe_raw,
        (
            "methode",
            "coins",
            "n_lhs_par_bande",
            "graine",
            "noeuds_max",
            "fraction_discret",
            "braquages",
        ),
        "doe",
        path,
    )

    params_raw = _section(data, "parametres", path)
    declared = {name: _parse_column(name, raw, path) for name, raw in params_raw.items()}

    try:
        reference = Reference(
            length_m=_as_float(ref_raw["longueur_m"], "reference.longueur_m", path),
            area_m2=_as_float(ref_raw["surface_m2"], "reference.surface_m2", path)
            if "surface_m2" in ref_raw
            else None,
        )
        symmetry = SymmetrySpec(
            group=_enum(
                SymmetryGroup, sym_raw.get("groupe", SymmetryGroup.C4V), "symetrie.groupe", path
            ),
            reference_plane_deg=_as_float(
                sym_raw.get("plan_reference_deg", 0.0), "symetrie.plan_reference_deg", path
            ),
            n_azimuths=_as_int(sym_raw["n_azimuts"], "symetrie.n_azimuts", path)
            if "n_azimuts" in sym_raw
            else None,
        )
        bands = BandSpec(
            edges=tuple(_as_float(x, "bandes.bornes", path) for x in bands_raw["bornes"])
            if bands_raw.get("bornes")
            else None,
            n_bands=_as_int(bands_raw.get("n_bandes", 8), "bandes.n_bandes", path),
            transonic=_as_pair(
                bands_raw.get("transsonique", [0.8, 1.2]), "bandes.transsonique", path
            ),
            transonic_refinement=_as_int(
                bands_raw.get("raffinement_transsonique", 2),
                "bandes.raffinement_transsonique",
                path,
            ),
            min_points=_as_int(bands_raw.get("points_min", 30), "bandes.points_min", path),
        )
        envelope = EnvelopeSpec(
            q_low=_as_float(env_raw.get("quantile_bas", 0.001), "enveloppe.quantile_bas", path),
            q_high=_as_float(env_raw.get("quantile_haut", 0.999), "enveloppe.quantile_haut", path),
            margin=_as_float(env_raw.get("marge", 0.05), "enveloppe.marge", path),
        )
        doe = DoeSpec(
            method=_enum(
                DoeMethod, doe_raw.get("methode", DoeMethod.TENSORIEL), "doe.methode", path
            ),
            include_corners=bool(doe_raw.get("coins", True)),
            n_lhs_per_band=_as_int(doe_raw.get("n_lhs_par_bande", 24), "doe.n_lhs_par_bande", path),
            seed=_as_int(doe_raw.get("graine", 12345), "doe.graine", path),
            max_nodes=_as_int(doe_raw.get("noeuds_max", 2000), "doe.noeuds_max", path),
            discrete_fraction=_as_float(
                doe_raw.get("fraction_discret", 0.25), "doe.fraction_discret", path
            ),
            deflections=_parse_deflections(doe_raw["braquages"], path)
            if "braquages" in doe_raw
            else (NEUTRAL_DEFLECTION,),
        )
    except StudyError:
        raise
    except (ValueError, TypeError) as exc:
        raise StudyError(str(exc), path=path) from exc

    return Study(
        name=str(etude["nom"]),
        source=str(etude["source"]),
        output_dir=str(etude.get("sortie", "SORTIE")),
        reference=reference,
        symmetry=symmetry,
        bands=bands,
        envelope=envelope,
        doe=doe,
        declared_columns=declared,
        delta_t_k=_as_float(atmosphere.get("delta_t_K", 0.0), "atmosphere.delta_t_K", path),
        path=path,
    )


def load_study(path: str | Path) -> Study:
    """Read and validate a study file."""
    target = Path(path)
    if not target.exists():
        raise StudyError("fichier d'étude introuvable", path=target)
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise StudyError(f"YAML mal formé : {exc}", path=target) from exc
    except UnicodeDecodeError as exc:
        raise StudyError("fichier illisible (encodage non UTF-8)", path=target) from exc
    if raw is None:
        raise StudyError("fichier vide", path=target)
    return parse_study(raw, path=target.resolve())


def default_study(source: str | Path, *, name: str = "sans nom") -> Study:
    """A valid study with every default applied, for use without a YAML file."""
    return Study(
        name=name,
        source=str(source),
        output_dir="SORTIE",
        reference=Reference(length_m=1.0),
        symmetry=SymmetrySpec(group=SymmetryGroup.C4V),
        bands=BandSpec(),
        envelope=EnvelopeSpec(),
        doe=DoeSpec(),
    )


def study_to_dict(study: Study, *, columns: Sequence[ColumnSpec] = ()) -> dict[str, Any]:
    """Serialise a study back to the YAML shape.

    ``columns`` promotes auto-detected specs to declared ones, which is how
    ``cfd-traj inspecter`` offers a ready-to-paste ``parametres`` block.
    """
    declared: dict[str, Any] = {}
    for spec in (*study.declared_columns.values(), *columns):
        entry: dict[str, Any] = {"role": str(spec.role)}
        if spec.levels is not None:
            entry["niveaux"] = spec.levels
        if spec.scale is not Scale.LINEAIRE:
            entry["echelle"] = str(spec.scale)
        if spec.unit:
            entry["unite"] = spec.unit
        if spec.label:
            entry["libelle"] = spec.label
        if spec.mechanical_range is not None:
            entry["plage"] = list(spec.mechanical_range)
        if spec.physical_min is not None:
            entry["min_physique"] = spec.physical_min
        if spec.q_low is not None:
            entry["quantile_bas"] = spec.q_low
        if spec.q_high is not None:
            entry["quantile_haut"] = spec.q_high
        if spec.margin is not None:
            entry["marge"] = spec.margin
        declared[spec.name] = entry

    out: dict[str, Any] = {
        "etude": {"nom": study.name, "source": study.source, "sortie": study.output_dir},
        "reference": {"longueur_m": study.reference.length_m},
        "symetrie": {
            "groupe": str(study.symmetry.group),
            "plan_reference_deg": study.symmetry.reference_plane_deg,
        },
        "enveloppe": {
            "quantile_bas": study.envelope.q_low,
            "quantile_haut": study.envelope.q_high,
            "marge": study.envelope.margin,
        },
        "doe": {
            "methode": str(study.doe.method),
            "coins": study.doe.include_corners,
            "n_lhs_par_bande": study.doe.n_lhs_per_band,
            "graine": study.doe.seed,
            "noeuds_max": study.doe.max_nodes,
            "fraction_discret": study.doe.discrete_fraction,
            "braquages": [
                {"nom": d.name, "dl": d.dl, "dm": d.dm, "dn": d.dn} for d in study.doe.deflections
            ],
        },
    }
    if study.reference.area_m2 is not None:
        out["reference"]["surface_m2"] = study.reference.area_m2
    if study.symmetry.n_azimuths is not None:
        out["symetrie"]["n_azimuts"] = study.symmetry.n_azimuths
    if study.delta_t_k:
        out["atmosphere"] = {"delta_t_K": study.delta_t_k}

    bands: dict[str, Any] = {"points_min": study.bands.min_points}
    if study.bands.edges is not None:
        bands["bornes"] = list(study.bands.edges)
    else:
        bands["n_bandes"] = study.bands.n_bands
        bands["transsonique"] = list(study.bands.transonic)
        bands["raffinement_transsonique"] = study.bands.transonic_refinement
    out["bandes"] = bands

    if declared:
        out["parametres"] = declared
    return out


def write_study(
    study: Study, path: str | Path, *, columns: Sequence[ColumnSpec] = (), header: str = ""
) -> Path:
    """Write a study file. Round-trips through :func:`load_study`."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(
        study_to_dict(study, columns=columns),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    target.write_text((header + body) if header else body, encoding="utf-8")
    return target
