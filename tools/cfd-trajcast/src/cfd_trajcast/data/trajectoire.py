"""La trajectoire, lue depuis un CSV ou un DataFrame et ramenée aux conventions internes.

En sortie, et nulle part ailleurs : temps en secondes, positions **ENU** en mètres,
attitude en quaternion ``(w, x, y, z)`` **corps FRD → ENU**. Les conventions
d'entrée sont *déclarées* (:class:`DeclarationTrajectoire`) ; quand une valeur par
défaut s'applique, le rapport le dit.

L'attitude est **obligatoire** : quaternion ou angles d'Euler. Aucune attitude
n'est déduite de la vitesse — sans elle, :class:`ErreurAttitude`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from functools import cached_property
from pathlib import Path
from typing import Any, Union

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from cfd_trajcast.core import atmosphere, reperes
from cfd_trajcast.core import rotations as rot
from cfd_trajcast.core.interpolation import Pchip, deriver, slerp_serie
from cfd_trajcast.data.constats import ALERTE, INFO, Constat

__all__ = [
    "COLONNES_EULER_CONNUES",
    "COLONNES_QUATERNION_CONNUES",
    "ORDRES",
    "SENS",
    "TYPES_ATTITUDE",
    "UNITES_ANGLE",
    "UNITES_LONGUEUR",
    "UNITES_TEMPS",
    "Brut",
    "DeclarationAttitude",
    "DeclarationTrajectoire",
    "ErreurAttitude",
    "ErreurTrajectoire",
    "Evenement",
    "Trajectoire",
    "convertir",
]

Tableau = NDArray[np.float64]

UNITES_TEMPS = {"s": 1.0, "ms": 1e-3, "min": 60.0}
UNITES_LONGUEUR = {"m": 1.0, "km": 1e3, "mm": 1e-3, "ft": 0.3048}
UNITES_ANGLE = {"deg": float(np.pi / 180), "rad": 1.0}

TYPES_ATTITUDE = ("quaternion", "euler")
ORDRES = ("wxyz", "xyzw")
SENS = ("corps_vers_reference", "reference_vers_corps")

#: Noms de colonnes reconnus quand la déclaration n'en donne pas (dans cet ordre).
COLONNES_QUATERNION_CONNUES: tuple[tuple[str, ...], ...] = (
    ("q0", "q1", "q2", "q3"),
    ("qw", "qx", "qy", "qz"),
    ("e0", "e1", "e2", "e3"),
)
COLONNES_EULER_CONNUES: tuple[tuple[str, ...], ...] = (
    ("lacet", "tangage", "roulis"),
    ("yaw", "pitch", "roll"),
    ("psi", "theta", "phi"),
)

#: Écart à la norme 1 toléré sans rien dire, puis corrigé avec alerte, puis refusé.
NORME_SILENCE = 1e-6
NORME_REFUS = 1e-2
#: Distance au blocage de cardan (rad) à partir de laquelle on alerte.
MARGE_CARDAN = np.radians(1.0)


class ErreurTrajectoire(ValueError):
    """La trajectoire ne peut pas être lue telle que déclarée."""


class ErreurAttitude(ErreurTrajectoire):
    """Ni quaternion ni angles d'Euler : la fusée n'a pas d'orientation."""


def _choix(nom: str, valeur: str, permis: Sequence[str]) -> None:
    if valeur not in permis:
        raise ErreurTrajectoire(f"{nom} {valeur!r} inconnu ; valeurs permises : {', '.join(permis)}")


@dataclass(frozen=True)
class DeclarationAttitude:
    """Comment lire l'attitude.

    ``colonnes`` : 4 noms (quaternion, dans l'ordre ``ordre``) ou 3 (Euler, dans
    l'ordre de ``sequence``) ; ``None`` = chercher un jeu de noms connu.
    """

    type: str
    colonnes: tuple[str, ...] | None = None
    ordre: str = "wxyz"
    sens: str = "corps_vers_reference"
    sequence: str = "ZYX"
    corps: str = "FRD"

    def __post_init__(self) -> None:
        _choix("type d'attitude", self.type, TYPES_ATTITUDE)
        _choix("ordre du quaternion", self.ordre, ORDRES)
        _choix("sens du quaternion", self.sens, SENS)
        _choix("repère corps", self.corps, reperes.CORPS)
        try:
            rot.valider_sequence(self.sequence)
        except ValueError as exc:
            raise ErreurTrajectoire(str(exc)) from None
        if self.colonnes is not None:
            attendu = 4 if self.type == "quaternion" else 3
            if len(self.colonnes) != attendu:
                raise ErreurTrajectoire(
                    f"attitude {self.type} : {attendu} colonnes attendues, "
                    f"{len(self.colonnes)} déclarées ({', '.join(self.colonnes)})"
                )
            object.__setattr__(self, "colonnes", tuple(self.colonnes))

    @classmethod
    def depuis(cls, valeur: AttitudeDeclarable) -> DeclarationAttitude:
        """Accepte une déclaration, un type (``"euler"``) ou un dict de champs."""
        if valeur is None:
            raise ErreurAttitude(_message_sans_attitude(()))
        if isinstance(valeur, DeclarationAttitude):
            return valeur
        if isinstance(valeur, str):
            return cls(type=valeur)
        inconnues = set(valeur) - {f.name for f in fields(cls)}
        if inconnues:
            raise ErreurTrajectoire(f"attitude : clés inconnues {sorted(inconnues)}")
        donnees = dict(valeur)
        if donnees.get("colonnes") is not None:
            donnees["colonnes"] = tuple(donnees["colonnes"])
        return cls(**donnees)


AttitudeDeclarable = Union[DeclarationAttitude, str, Mapping[str, Any], None]


@dataclass(frozen=True)
class DeclarationTrajectoire:
    """Conventions et colonnes d'un fichier de trajectoire.

    Pour ``repere="NED"``, les colonnes ``x, y, z`` contiennent Nord, Est, Bas.
    """

    repere: str
    attitude: DeclarationAttitude
    t: str = "t"
    x: str = "x"
    y: str = "y"
    z: str = "z"
    unite_temps: str = "s"
    unite_longueur: str = "m"
    unite_angle: str = "deg"

    def __post_init__(self) -> None:
        _choix("repère", self.repere, reperes.REPERES)
        _choix("unité de temps", self.unite_temps, tuple(UNITES_TEMPS))
        _choix("unité de longueur", self.unite_longueur, tuple(UNITES_LONGUEUR))
        _choix("unité d'angle", self.unite_angle, tuple(UNITES_ANGLE))

    def decrire(self) -> list[tuple[str, str]]:
        """Les conventions retenues, en clair, pour le rapport."""
        a = self.attitude
        converti = "" if self.repere == "ENU" else " (converti en ENU)"
        lignes = [
            ("repère", f"{self.repere} local{converti}"),
            ("unités", f"temps {self.unite_temps}, longueur {self.unite_longueur}"),
        ]
        if a.type == "quaternion":
            sens = "corps → référence" if a.sens == "corps_vers_reference" else "référence → corps"
            lignes.append(("attitude", f"quaternion {a.ordre}, {sens}"))
        else:
            nature = "intrinsèque" if a.sequence.isupper() else "extrinsèque"
            lignes.append(("attitude", f"Euler {a.sequence} {nature}, en {self.unite_angle}"))
        lignes.append(("repère corps", a.corps + ("" if a.corps == "FRD" else " (converti en FRD)")))
        return lignes


@dataclass(frozen=True)
class Evenement:
    """Un instant nommé du vol (fin de propulsion, apogée, parachute…)."""

    t: float
    nom: str


@dataclass(frozen=True, eq=False)
class Brut:
    """Les données telles que lues (unités SI, repère et convention d'entrée)."""

    t: Tableau
    positions: Tableau
    attitude: Tableau


def _message_sans_attitude(candidates: Sequence[str]) -> str:
    message = (
        "aucune attitude déclarée : la trajectoire doit fournir un quaternion "
        "(4 colonnes, ex. q0 q1 q2 q3) ou des angles d'Euler (3 colonnes, ex. lacet "
        "tangage roulis, séquence déclarée). L'attitude n'est jamais déduite de la vitesse."
    )
    if candidates:
        message += f" Colonnes du fichier qui y ressemblent : {', '.join(candidates)}."
    return message


def _colonnes_attitude(df: pd.DataFrame, decl: DeclarationAttitude) -> tuple[str, ...]:
    if decl.colonnes is not None:
        return decl.colonnes
    connus = COLONNES_QUATERNION_CONNUES if decl.type == "quaternion" else COLONNES_EULER_CONNUES
    trouves = [jeu for jeu in connus if all(c in df.columns for c in jeu)]
    if len(trouves) == 1:
        return trouves[0]
    if not trouves:
        raise ErreurAttitude(
            f"attitude {decl.type} : aucune colonne déclarée et aucun des jeux connus "
            f"({' / '.join(' '.join(j) for j in connus)}) dans le fichier "
            f"(colonnes : {', '.join(map(str, df.columns))}). Déclarer attitude.colonnes."
        )
    raise ErreurAttitude(
        f"attitude {decl.type} : plusieurs jeux de colonnes possibles "
        f"({' / '.join(' '.join(j) for j in trouves)}). Déclarer attitude.colonnes."
    )


def _colonne(df: pd.DataFrame, nom: str) -> Tableau:
    if nom not in df.columns:
        raise ErreurTrajectoire(
            f"colonne {nom!r} absente ; colonnes du fichier : {', '.join(map(str, df.columns))}"
        )
    valeurs = pd.to_numeric(df[nom], errors="coerce").to_numpy(dtype=float)
    mauvais = np.flatnonzero(~np.isfinite(valeurs))
    if len(mauvais):
        raise ErreurTrajectoire(
            f"colonne {nom!r} : {len(mauvais)} valeur(s) manquante(s) ou non numérique(s), "
            f"première à la ligne de données {int(mauvais[0]) + 1}"
        )
    return valeurs


def convertir(brut: Brut, decl: DeclarationTrajectoire) -> tuple[Tableau, Tableau, list[Constat]]:
    """Données brutes → (positions ENU, quaternions FRD→ENU, constats).

    Séparé de la lecture pour que la validation puisse rejouer la conversion
    sous d'autres conventions et dire laquelle rendrait le vol cohérent.
    """
    constats: list[Constat] = []
    a = decl.attitude
    positions = reperes.positions_vers_enu(brut.positions, decl.repere)
    if a.type == "quaternion":
        q = brut.attitude[:, [3, 0, 1, 2]] if a.ordre == "xyzw" else brut.attitude.copy()
        norme = np.linalg.norm(q, axis=1)
        ecart = float(np.max(np.abs(norme - 1)))
        if ecart > NORME_REFUS:
            k = int(np.argmax(np.abs(norme - 1)))
            raise ErreurTrajectoire(
                f"quaternion de norme {norme[k]:.4g} à t = {brut.t[k]:g} s (écart maximal à 1 : "
                f"{ecart:.3g}) : ce ne sont pas des quaternions unitaires — colonnes ou ordre faux ?"
            )
        if ecart > NORME_SILENCE:
            constats.append(
                Constat(ALERTE, "norme_quaternion",
                        f"quaternions renormalisés (écart maximal à la norme 1 : {ecart:.2g})",
                        "précision d'écriture insuffisante dans le fichier ?")
            )
        q = rot.normaliser(q)
        if a.sens == "reference_vers_corps":
            q = rot.conjugue(q)
    else:
        q = rot.depuis_euler(brut.attitude, a.sequence)
        deuxieme = brut.attitude[:, 1]
        if a.sequence[0].lower() == a.sequence[2].lower():  # Euler propre : singulier en 0 et π
            proche = np.minimum(np.abs(deuxieme), np.abs(np.abs(deuxieme) - np.pi)) < MARGE_CARDAN
        else:  # Tait-Bryan : singulier en ±π/2
            proche = np.abs(np.abs(deuxieme) - np.pi / 2) < MARGE_CARDAN
        if np.any(proche):
            constats.append(
                Constat(ALERTE, "blocage_cardan",
                        f"{int(np.count_nonzero(proche))} échantillon(s) à moins de 1° du blocage "
                        f"de cardan de la séquence {a.sequence}",
                        "les angles y sont mal conditionnés ; l'interpolation se fait en "
                        "quaternions, mais un quaternion en entrée serait plus sûr")
            )
    q = reperes.quaternion_corps_vers_frd(q, a.corps)
    q = reperes.quaternion_vers_enu(q, decl.repere)
    q, retournements = rot.continuite_hemisphere(q)
    if retournements:
        constats.append(
            Constat(INFO, "hemisphere",
                    f"{retournements} changement(s) de signe du quaternion corrigé(s) "
                    "(q et −q sont la même attitude)")
        )
    return positions, q, constats


def _lire_csv(chemin: Path) -> pd.DataFrame:
    if not chemin.is_file():
        raise ErreurTrajectoire(f"fichier de trajectoire introuvable : {chemin}")
    try:
        df = pd.read_csv(chemin, sep=None, engine="python", comment="#")
    except (pd.errors.ParserError, UnicodeDecodeError, ValueError) as exc:
        raise ErreurTrajectoire(f"{chemin.name} illisible comme CSV : {exc}") from None
    df.columns = [str(c).strip() for c in df.columns]
    return df


@dataclass(frozen=True, eq=False)
class Trajectoire:
    """Trajectoire aux conventions internes. Construire par ``depuis_csv``/``depuis_dataframe``."""

    t: Tableau
    positions: Tableau
    attitude: Tableau
    declaration: DeclarationTrajectoire
    brut: Brut
    donnees: dict[str, Tableau] = field(default_factory=dict)
    evenements: tuple[Evenement, ...] = ()
    constats: tuple[Constat, ...] = ()
    source: str = ""

    # -- construction --------------------------------------------------------------
    @classmethod
    def depuis_dataframe(
        cls,
        df: pd.DataFrame,
        *,
        repere: str | None = None,
        attitude: AttitudeDeclarable = None,
        colonnes: Mapping[str, str] | None = None,
        unites: Mapping[str, str] | None = None,
        declaration: DeclarationTrajectoire | None = None,
        evenements: Sequence[Evenement] = (),
        source: str = "DataFrame",
    ) -> Trajectoire:
        """Lit un DataFrame. Donner soit ``declaration``, soit ``repere`` + ``attitude``.

        ``colonnes`` : ``{"t": …, "x": …, "y": …, "z": …}`` ; ``unites`` :
        ``{"temps": "s", "longueur": "m", "angle": "deg"}``.
        """
        if declaration is None:
            if repere is None:
                raise ErreurTrajectoire("repère non déclaré : ENU ou NED")
            decl_att = DeclarationAttitude.depuis(attitude)
            cols = dict(colonnes or {})
            u = dict(unites or {})
            inconnues = (set(cols) - {"t", "x", "y", "z"}) | (set(u) - {"temps", "longueur", "angle"})
            if inconnues:
                raise ErreurTrajectoire(f"clés inconnues : {sorted(inconnues)}")
            declaration = DeclarationTrajectoire(
                repere=repere,
                attitude=decl_att,
                unite_temps=u.get("temps", "s"),
                unite_longueur=u.get("longueur", "m"),
                unite_angle=u.get("angle", "deg"),
                **cols,
            )
        decl = declaration
        df = df.rename(columns=lambda c: str(c).strip())
        noms_att = _colonnes_attitude(df, decl.attitude)
        decl = replace(decl, attitude=replace(decl.attitude, colonnes=noms_att))

        t = _colonne(df, decl.t) * UNITES_TEMPS[decl.unite_temps]
        pas = np.diff(t)
        if np.any(pas <= 0):
            k = int(np.flatnonzero(pas <= 0)[0])
            nature = "dupliqué" if pas[k] == 0 else "décroissant"
            raise ErreurTrajectoire(
                f"temps {nature} entre les lignes de données {k + 1} et {k + 2} "
                f"(t = {t[k]:g} puis {t[k + 1]:g} s) : il doit être strictement croissant"
            )
        if len(t) < 2:
            raise ErreurTrajectoire("au moins deux échantillons sont nécessaires")
        positions = np.stack([_colonne(df, c) for c in (decl.x, decl.y, decl.z)], axis=1)
        positions = positions * UNITES_LONGUEUR[decl.unite_longueur]
        att = np.stack([_colonne(df, c) for c in noms_att], axis=1)
        if decl.attitude.type == "euler":
            att = att * UNITES_ANGLE[decl.unite_angle]
        brut = Brut(t=t, positions=positions, attitude=att)
        pos_enu, q, constats = convertir(brut, decl)

        # Toutes les colonnes numériques, telles que lues (unités du fichier) : la télémétrie
        # peut afficher n'importe laquelle, y compris celles de l'attitude.
        donnees = {
            str(c): pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float)
            for c in df.columns
            if c != decl.t and pd.api.types.is_numeric_dtype(df[c])
        }
        evts = tuple(sorted(evenements, key=lambda e: e.t))
        hors = [e for e in evts if not t[0] <= e.t <= t[-1]]
        if hors:
            constats.append(
                Constat(ALERTE, "evenement_hors_vol",
                        f"événement(s) hors de [{t[0]:g} ; {t[-1]:g}] s : "
                        + ", ".join(f"{e.nom} ({e.t:g} s)" for e in hors))
            )
        return cls(t=t, positions=pos_enu, attitude=q, declaration=decl, brut=brut,
                   donnees=donnees, evenements=evts, constats=tuple(constats), source=source)

    @classmethod
    def depuis_csv(
        cls,
        chemin: str | Path,
        *,
        repere: str | None = None,
        attitude: AttitudeDeclarable = None,
        colonnes: Mapping[str, str] | None = None,
        unites: Mapping[str, str] | None = None,
        declaration: DeclarationTrajectoire | None = None,
        evenements: Sequence[Evenement] = (),
    ) -> Trajectoire:
        """Lit un CSV (séparateur détecté, lignes ``#`` ignorées). Voir :meth:`depuis_dataframe`."""
        p = Path(chemin)
        return cls.depuis_dataframe(
            _lire_csv(p), repere=repere, attitude=attitude, colonnes=colonnes, unites=unites,
            declaration=declaration, evenements=evenements, source=str(p),
        )

    # -- grandeurs dérivées -----------------------------------------------------------
    @property
    def duree(self) -> float:
        """Durée couverte (s)."""
        return float(self.t[-1] - self.t[0])

    @cached_property
    def vitesse(self) -> Tableau:
        """Vitesse ENU (m/s) aux échantillons, par différences finies d'ordre 2."""
        return deriver(self.t, self.positions)

    @cached_property
    def acceleration(self) -> Tableau:
        """Accélération ENU (m/s²) aux échantillons (dérivée de la vitesse)."""
        return deriver(self.t, self.vitesse)

    @cached_property
    def mach(self) -> Tableau:
        """Mach (ISA, vent nul ; l'altitude est la cote ENU au-dessus de la rampe)."""
        return atmosphere.mach(np.linalg.norm(self.vitesse, axis=1), self.positions[:, 2])

    @cached_property
    def axe_nez(self) -> Tableau:
        """Direction du nez (x corps) dans le repère ENU, ``(N, 3)``."""
        return rot.tourner(self.attitude, np.array([1.0, 0.0, 0.0]))

    @property
    def apogee(self) -> tuple[float, float]:
        """(instant, altitude) de l'échantillon le plus haut."""
        k = int(np.argmax(self.positions[:, 2]))
        return float(self.t[k]), float(self.positions[k, 2])

    @cached_property
    def _pchip(self) -> Pchip:
        return Pchip(self.t, self.positions)

    def etat(self, t: float | Sequence[float] | Tableau) -> tuple[Tableau, Tableau]:
        """Position ENU et quaternion aux instants ``t`` (PCHIP + SLERP), sans extrapolation."""
        return self._pchip(t), slerp_serie(self.t, self.attitude, t)

    def vers_csv(self, chemin: str | Path) -> tuple[Path, Path | None]:
        """Écrit la trajectoire **aux conventions internes**, et ses événements à côté.

        Colonnes ``t, x, y, z`` (ENU, m) et ``qw, qx, qy, qz`` (corps FRD → ENU), puis les
        autres colonnes numériques telles que lues. Événements : ``<nom>_evenements.csv``
        (``t,nom``), ou rien s'il n'y en a pas. Relecture : ``repere: ENU``, attitude
        ``quaternion`` (colonnes connues ``qw qx qy qz``), événements = ce fichier.
        """
        p = Path(chemin)
        p.parent.mkdir(parents=True, exist_ok=True)
        table = {"t": self.t, "x": self.positions[:, 0], "y": self.positions[:, 1],
                 "z": self.positions[:, 2], "qw": self.attitude[:, 0], "qx": self.attitude[:, 1],
                 "qy": self.attitude[:, 2], "qz": self.attitude[:, 3]}
        for nom, valeurs in self.donnees.items():
            table.setdefault(nom, valeurs)
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"# cfd-trajcast : ENU (m), quaternion qw qx qy qz corps FRD -> ENU ; source : {self.source}\n")
            pd.DataFrame(table).to_csv(f, index=False, float_format="%.10g")
        if not self.evenements:
            return p, None
        e = p.with_name(f"{p.stem}_evenements.csv")
        pd.DataFrame({"t": [x.t for x in self.evenements], "nom": [x.nom for x in self.evenements]}).to_csv(
            e, index=False, float_format="%.6f")
        return p, e

    def vitesse_a(self, t: float | Sequence[float] | Tableau) -> Tableau:
        """Vitesse ENU aux instants ``t`` : dérivée de l'interpolant des positions."""
        return self._pchip(t, derivee=1)
