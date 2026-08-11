"""Load and validate a nozzle case file (YAML).

A case file pins down one nozzle and one operating point so that a study is
reproducible and can live in the CFD case repository next to the mesh. Every
error raised here is a :class:`CaseError` carrying a message meant to be shown
to the user as-is, naming the offending key.

Schema — ``cfd-nozzle example`` writes a commented, valid one::

    tuyere:
      nom: "MOTEUR_DEMO"
      gaz: lox_rp1            # nom de la bibliothèque, ou gamma/r explicites
      # gamma: 1.22
      # r: 345.0
      diametre_col: 0.20      # m   (ou aire_col: en m²)
      rapport_section: 16.0   # ε = Ae/At
      eta_cstar: 0.96         # rendement de combustion (défaut 1.0)
      lambda_divergence: null # null → déduit du contour

    fonctionnement:
      p0: 100.0e5             # Pa
      t0: 3500.0              # K
      pa: 1.013e5             # Pa

    geometrie:
      type: bell              # bell | conique
      pourcentage_longueur: 80.0
      demi_angle: 15.0        # conique uniquement
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from cfd_nozzle.core.gas import GAS_LIBRARY, GasModel
from cfd_nozzle.core.geometry import NozzleContour, bell_contour, conical_contour
from cfd_nozzle.core.nozzle import Nozzle

__all__ = ["CaseError", "ContourKind", "NozzleCase", "load_case"]

ContourKind = Literal["bell", "conique"]


class CaseError(Exception):
    """A case file that cannot be read, parsed or validated."""


@dataclass(frozen=True)
class NozzleCase:
    """A validated nozzle case: the nozzle, its operating point, its contour."""

    name: str
    gas: GasModel
    throat_area: float
    area_ratio: float
    eta_cstar: float
    lambda_div: float | None
    p0: float
    t0: float
    pa: float
    contour_kind: ContourKind
    pct_length: float
    half_angle_deg: float
    source: Path | None = None

    def build_contour(self) -> NozzleContour:
        """Generate the contour described by the case."""
        throat_radius = math.sqrt(self.throat_area / math.pi)
        try:
            if self.contour_kind == "bell":
                return bell_contour(throat_radius, self.area_ratio, self.pct_length)
            return conical_contour(throat_radius, self.area_ratio, self.half_angle_deg)
        except ValueError as exc:
            raise CaseError(f"géométrie irréalisable : {exc}") from exc

    def build_nozzle(self, contour: NozzleContour | None = None) -> Nozzle:
        """Build the :class:`Nozzle`, taking λ from the contour when unset."""
        lambda_div = self.lambda_div
        if lambda_div is None:
            lambda_div = (contour or self.build_contour()).divergence_lambda
        try:
            return Nozzle(
                self.throat_area,
                self.area_ratio,
                self.gas,
                eta_cstar=self.eta_cstar,
                lambda_div=lambda_div,
            )
        except ValueError as exc:
            raise CaseError(f"tuyère irréalisable : {exc}") from exc


def _section(data: dict[str, Any], key: str, *, required: bool = True) -> dict[str, Any]:
    value = data.get(key)
    if value is None:
        if required:
            raise CaseError(f"section « {key} » absente du fichier de cas")
        return {}
    if not isinstance(value, dict):
        raise CaseError(f"la section « {key} » doit être un bloc de clés, pas {type(value).__name__}")
    return value


def _number(
    section: dict[str, Any],
    key: str,
    where: str,
    *,
    default: float | None = None,
    positive: bool = True,
) -> float:
    if key not in section or section[key] is None:
        if default is not None:
            return default
        raise CaseError(f"clé « {where}.{key} » manquante")
    value = section[key]
    if isinstance(value, bool):
        raise CaseError(f"« {where}.{key} » doit être un nombre (reçu {value!r})")
    if isinstance(value, str):
        # PyYAML follows YAML 1.1, whose float pattern demands a *signed*
        # exponent: "1.0e5" is read as a string while "1.0e+5" is a float.
        # Writing a pressure as 100.0e5 is far too natural to punish, so
        # numeric strings are accepted here.
        try:
            value = float(value.strip())
        except ValueError:
            raise CaseError(f"« {where}.{key} » doit être un nombre (reçu {value!r})") from None
    elif not isinstance(value, (int, float)):
        raise CaseError(f"« {where}.{key} » doit être un nombre (reçu {value!r})")
    number = float(value)
    if not math.isfinite(number):
        raise CaseError(f"« {where}.{key} » doit être un nombre fini (reçu {value!r})")
    if positive and number <= 0.0:
        raise CaseError(f"« {where}.{key} » doit être > 0 (reçu {number:g})")
    return number


def _gas(section: dict[str, Any]) -> GasModel:
    name = section.get("gaz")
    gamma = section.get("gamma")
    r = section.get("r")
    if name is not None:
        if not isinstance(name, str):
            raise CaseError(f"« tuyere.gaz » doit être un nom de gaz (reçu {name!r})")
        if name not in GAS_LIBRARY:
            known = ", ".join(sorted(GAS_LIBRARY))
            raise CaseError(f"gaz inconnu « {name} » — gaz disponibles : {known}")
        base = GAS_LIBRARY[name]
        return GasModel(
            float(gamma) if gamma is not None else base.gamma,
            float(r) if r is not None else base.r,
            base.name,
        )
    if gamma is None or r is None:
        raise CaseError(
            "définir « tuyere.gaz » (nom de la bibliothèque) ou le couple "
            "« tuyere.gamma » / « tuyere.r »"
        )
    try:
        return GasModel(float(gamma), float(r), "personnalisé")
    except (TypeError, ValueError) as exc:
        raise CaseError(f"gaz invalide : {exc}") from exc


def _throat_area(section: dict[str, Any]) -> float:
    has_area = section.get("aire_col") is not None
    has_diameter = section.get("diametre_col") is not None
    if has_area and has_diameter:
        raise CaseError("donner « tuyere.aire_col » OU « tuyere.diametre_col », pas les deux")
    if has_area:
        return _number(section, "aire_col", "tuyere")
    if has_diameter:
        return 0.25 * math.pi * _number(section, "diametre_col", "tuyere") ** 2
    raise CaseError("donner « tuyere.aire_col » [m²] ou « tuyere.diametre_col » [m]")


def load_case(path: str | Path) -> NozzleCase:
    """Read, parse and validate a nozzle case file.

    Raises:
        CaseError: on any unreadable, malformed or inconsistent file.
    """
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise CaseError(f"fichier de cas illisible : {exc}") from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise CaseError(f"YAML invalide : {exc}") from exc
    if not isinstance(raw, dict):
        raise CaseError("le fichier de cas doit contenir un dictionnaire de sections")

    nozzle_section = _section(raw, "tuyere")
    operating = _section(raw, "fonctionnement")
    geometry = _section(raw, "geometrie", required=False)

    name = nozzle_section.get("nom", source.stem)
    if not isinstance(name, str):
        raise CaseError(f"« tuyere.nom » doit être une chaîne (reçu {name!r})")

    kind_raw = geometry.get("type", "bell")
    if kind_raw not in ("bell", "conique"):
        raise CaseError(f"« geometrie.type » doit valoir « bell » ou « conique » (reçu {kind_raw!r})")
    kind: ContourKind = kind_raw

    lambda_raw = nozzle_section.get("lambda_divergence")
    lambda_div = None if lambda_raw is None else _number(nozzle_section, "lambda_divergence", "tuyere")

    case = NozzleCase(
        name=name,
        gas=_gas(nozzle_section),
        throat_area=_throat_area(nozzle_section),
        area_ratio=_number(nozzle_section, "rapport_section", "tuyere"),
        eta_cstar=_number(nozzle_section, "eta_cstar", "tuyere", default=1.0),
        lambda_div=lambda_div,
        p0=_number(operating, "p0", "fonctionnement"),
        t0=_number(operating, "t0", "fonctionnement"),
        pa=_number(operating, "pa", "fonctionnement"),
        contour_kind=kind,
        pct_length=_number(geometry, "pourcentage_longueur", "geometrie", default=80.0),
        half_angle_deg=_number(geometry, "demi_angle", "geometrie", default=15.0),
        source=source,
    )
    if case.area_ratio < 1.0:
        raise CaseError(f"« tuyere.rapport_section » doit être ≥ 1 (reçu {case.area_ratio:g})")
    if not 0.0 < case.eta_cstar <= 1.0:
        raise CaseError(f"« tuyere.eta_cstar » doit être dans ]0, 1] (reçu {case.eta_cstar:g})")
    if case.lambda_div is not None and not 0.0 < case.lambda_div <= 1.0:
        raise CaseError(
            f"« tuyere.lambda_divergence » doit être dans ]0, 1] (reçu {case.lambda_div:g})"
        )
    return case
