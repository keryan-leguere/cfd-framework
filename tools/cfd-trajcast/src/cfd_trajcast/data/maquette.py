"""La maquette 3D : CAO lue, ramenée au repère corps FRD, en mètres, à son point de référence.

Formats : STEP (``.step``/``.stp``, extra ``[step]`` → cascadio, OpenCASCADE en
roues pip), STL, OBJ, PLY, GLB/glTF (trimesh).

Unités : un STEP déclare la sienne, cascadio la convertit en mètres — ``unite``
n'y est qu'un contrôle. Un maillage n'a pas d'unité : ``unite`` y est obligatoire.

Origine : la trajectoire donne la position d'**un point** de la fusée ; ``origine``
dit lequel (``base`` = centre du culot, ``centre_volume`` = centre de masse à
densité uniforme, ou un point ``[x, y, z]`` en unités CAO — typiquement le CG
réel ; en unité du fichier, y compris pour un STEP). La fusée tourne autour de
ce point.

Cache : le maillage d'un STEP (l'étape lente, OpenCASCADE) est gardé sur disque, clé =
contenu du fichier + versions de cascadio et trimesh (:mod:`cfd_trajcast.data.cache`).
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.core import reperes
from cfd_trajcast.data import cache
from cfd_trajcast.data.constats import ALERTE, INFO, Constat

__all__ = [
    "FORMATS_MAILLAGE",
    "FORMATS_STEP",
    "ORIGINES",
    "UNITES_CAO",
    "DeclarationMaquette",
    "ErreurMaquette",
    "Maquette",
    "unite_step",
]

Tableau = NDArray[np.float64]

UNITES_CAO = {"m": 1.0, "cm": 1e-2, "mm": 1e-3, "in": 0.0254, "ft": 0.3048}
FORMATS_STEP = (".step", ".stp")
FORMATS_MAILLAGE = (".stl", ".obj", ".ply", ".glb", ".gltf")
ORIGINES = ("base", "centre_volume")
#: Écart relatif toléré entre la longueur lue et ``longueur_attendue``.
TOLERANCE_LONGUEUR = 0.05
#: Facteurs de confusion d'unités qu'on sait nommer.
_CONFUSIONS = {
    1000.0: "mm pris pour des m",
    0.001: "m pris pour des mm",
    100.0: "cm pris pour des m",
    0.01: "m pris pour des cm",
    10.0: "mm pris pour des cm",
    0.1: "cm pris pour des mm",
    25.4: "mm pris pour des pouces",
    1 / 25.4: "pouces pris pour des mm",
    1 / 0.0254: "pouces pris pour des m",
    0.0254: "m pris pour des pouces",
}

Origine = Union[str, tuple[float, float, float]]


class ErreurMaquette(ValueError):
    """La CAO ne peut pas être lue ou ne correspond pas à sa déclaration."""


@dataclass(frozen=True)
class DeclarationMaquette:
    """Comment placer la CAO dans le repère corps."""

    fichier: Path
    axe_nez: str
    axe_haut: str
    unite: str | None = None
    origine: Origine = "base"
    longueur_attendue: float | None = None
    longueur_imposee: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "fichier", Path(self.fichier))
        try:
            reperes.matrice_cao_vers_corps(self.axe_nez, self.axe_haut)
        except ValueError as exc:
            raise ErreurMaquette(str(exc)) from None
        if self.unite is not None and self.unite not in UNITES_CAO:
            raise ErreurMaquette(
                f"unité {self.unite!r} inconnue ; valeurs permises : {', '.join(UNITES_CAO)}"
            )
        if isinstance(self.origine, str):
            if self.origine not in ORIGINES:
                raise ErreurMaquette(
                    f"origine {self.origine!r} inconnue : {', '.join(ORIGINES)} ou [x, y, z]"
                )
        else:
            point = tuple(float(v) for v in self.origine)
            if len(point) != 3:
                raise ErreurMaquette("origine [x, y, z] : trois coordonnées attendues")
            object.__setattr__(self, "origine", point)
        for nom in ("longueur_attendue", "longueur_imposee"):
            valeur = getattr(self, nom)
            if valeur is not None and not valeur > 0:
                raise ErreurMaquette(f"{nom} doit être une longueur positive (m)")
        if self.longueur_attendue is not None and self.longueur_imposee is not None:
            raise ErreurMaquette(
                "longueur_attendue (contrôle) et longueur_imposee (mise à l'échelle) "
                "s'excluent : la seconde rendrait la première toujours vraie"
            )


def unite_step(texte: str) -> str | None:
    """Unité de longueur déclarée dans un STEP (``"mm"``, ``"m"``…), ``None`` si illisible."""
    m = re.search(r"LENGTH_UNIT\s*\(\s*\)\s*NAMED_UNIT\s*\(\s*\*\s*\)\s*SI_UNIT\s*\(\s*([^,]+),\s*\.METRE\.", texte)
    if m is None:
        m = re.search(r"SI_UNIT\s*\(\s*([^,]+),\s*\.METRE\.\s*\)", texte)
    if m is not None:
        prefixe = m.group(1).strip()
        return {"$": "m", ".MILLI.": "mm", ".CENTI.": "cm"}.get(prefixe)
    m = re.search(r"CONVERSION_BASED_UNIT\s*\(\s*'([A-Z]+)'", texte.upper())
    if m is not None:
        return {"INCH": "in", "FOOT": "ft"}.get(m.group(1))
    return None


def _version(paquet: str) -> str:
    from importlib import metadata

    try:
        return metadata.version(paquet)
    except metadata.PackageNotFoundError:
        return "?"


def _maillage_trimesh(objet: Any) -> Any:
    """Une scène trimesh → un seul maillage (l'API a changé au fil des versions 4.x)."""
    import trimesh

    if isinstance(objet, trimesh.Trimesh):
        return objet
    for methode in ("to_mesh", "to_geometry"):
        if hasattr(objet, methode):
            return getattr(objet, methode)()
    return trimesh.util.concatenate(objet.dump())


def _lire(
    fichier: Path, unite: str | None
) -> tuple[Tableau, NDArray[np.int64], float, float | None, list[Constat]]:
    """Sommets, faces, facteur sommets → m, facteur unité CAO du fichier → m, constats.

    Pour un STEP les sommets sortent déjà en mètres, mais un point d'origine donné
    par l'utilisateur est en unité du fichier : d'où deux facteurs.
    """
    import trimesh

    constats: list[Constat] = []
    suffixe = fichier.suffix.lower()
    if suffixe in FORMATS_STEP:
        try:
            import cascadio
        except ImportError:
            raise ErreurMaquette(
                f"{fichier.name} : lire un STEP demande l'extra [step] "
                "(pip install 'cfd-trajcast[step]'), ou fournir un STL"
            ) from None
        octets = fichier.read_bytes()
        declaree = unite_step(octets.decode("latin-1", errors="replace"))
        if unite is not None and declaree is not None and unite != declaree:
            raise ErreurMaquette(
                f"{fichier.name} déclare des {declaree}, la configuration des {unite} : "
                "l'unité d'un STEP vient du fichier, retirer `unite` ou la corriger"
            )
        cle = cache.empreinte("step", octets, _version("cascadio"), _version("trimesh"))
        entree = cache.lire("step", cle)
        if entree is not None:
            sommets_lus, faces_lues = entree["sommets"].astype(float), entree["faces"].astype(np.int64)
            constats.append(Constat(INFO, "cache", f"maillage du STEP relu du cache ({cle[:12]}…)"))
        else:
            glb = cascadio.load(octets, file_type="step")
            if not glb:
                raise ErreurMaquette(f"{fichier.name} : OpenCASCADE n'a pas pu le mailler")
            maillage = _maillage_trimesh(trimesh.load(io.BytesIO(glb), file_type="glb"))
            sommets_lus = np.asarray(maillage.vertices, dtype=float)
            faces_lues = np.asarray(maillage.faces, dtype=np.int64)
            cache.ecrire("step", cle, {"sommets": sommets_lus, "faces": faces_lues})
        constats.append(
            Constat(INFO, "unite_step",
                    f"STEP en {declaree or 'unité non lue'}, converti en mètres par OpenCASCADE")
        )
        facteur = 1.0
        facteur_point = None if declaree is None else UNITES_CAO[declaree]
    elif suffixe in FORMATS_MAILLAGE:
        if unite is None:
            raise ErreurMaquette(
                f"{fichier.name} : un maillage {suffixe} n'a pas d'unité, déclarer "
                f"maquette.unite ({', '.join(UNITES_CAO)})"
            )
        maillage = _maillage_trimesh(trimesh.load(fichier, force="mesh"))
        sommets_lus = np.asarray(maillage.vertices, dtype=float)
        faces_lues = np.asarray(maillage.faces, dtype=np.int64)
        facteur = UNITES_CAO[unite]
        facteur_point = facteur
    else:
        raise ErreurMaquette(
            f"{fichier.name} : format {suffixe or '(sans extension)'} non pris en charge ; "
            f"formats : {', '.join(FORMATS_STEP + FORMATS_MAILLAGE)}"
        )
    sommets, faces = sommets_lus, faces_lues
    if len(faces) == 0:
        raise ErreurMaquette(f"{fichier.name} : aucune face")
    return sommets, faces, facteur, facteur_point, constats


def _centre_volume(sommets: Tableau, faces: NDArray[np.int64]) -> tuple[Tableau, bool]:
    """Centre de masse à densité uniforme ; centre des surfaces si le maillage n'est pas fermé."""
    import trimesh

    m = trimesh.Trimesh(vertices=sommets, faces=faces, process=True)
    if m.is_volume:
        return np.asarray(m.center_mass, dtype=float), True
    return np.asarray(m.triangles_center.T @ m.area_faces / m.area, dtype=float), False


def _confusion(rapport: float) -> str:
    for facteur, nom in _CONFUSIONS.items():
        if abs(rapport / facteur - 1) < TOLERANCE_LONGUEUR:
            return f" Rapport ≈ {facteur:g} : {nom} ?"
    return " Aucune confusion d'unités connue n'explique ce rapport ; `longueur_imposee` met à l'échelle."


@dataclass(frozen=True, eq=False)
class Maquette:
    """Maillage en repère corps FRD (x vers le nez), en mètres, origine au point de référence."""

    sommets: Tableau
    faces: NDArray[np.int64]
    declaration: DeclarationMaquette
    echelle: float
    sha256: str
    constats: tuple[Constat, ...] = ()

    @property
    def longueur(self) -> float:
        """Étendue selon l'axe de la fusée (m)."""
        return float(np.ptp(self.sommets[:, 0]))

    @property
    def taille(self) -> float:
        """Plus grande dimension (longueur ou envergure) : ce que les caméras cadrent."""
        return max(self.longueur, self.envergure)

    @property
    def envergure(self) -> float:
        """Plus grande étendue transversale (m)."""
        return float(max(np.ptp(self.sommets[:, 1]), np.ptp(self.sommets[:, 2])))

    @classmethod
    def depuis_declaration(cls, decl: DeclarationMaquette) -> Maquette:
        """Lit et place la CAO selon sa déclaration."""
        fichier = decl.fichier
        if not fichier.is_file():
            raise ErreurMaquette(f"fichier CAO introuvable : {fichier}")
        sommets_cao, faces, facteur, facteur_point, constats = _lire(fichier, decl.unite)
        r = reperes.matrice_cao_vers_corps(decl.axe_nez, decl.axe_haut)
        sommets = sommets_cao @ r.T * facteur

        if decl.origine == "base":
            mini, maxi = sommets.min(axis=0), sommets.max(axis=0)
            origine = np.array([mini[0], (mini[1] + maxi[1]) / 2, (mini[2] + maxi[2]) / 2])
        elif decl.origine == "centre_volume":
            origine, ferme = _centre_volume(sommets, faces)
            if not ferme:
                constats.append(
                    Constat(ALERTE, "maillage_ouvert",
                            "maillage non fermé : centre_volume pris au centre des surfaces",
                            "donner le CG réel en origine: [x, y, z] (unités CAO)")
                )
        else:
            if facteur_point is None:
                raise ErreurMaquette(
                    f"{fichier.name} : unité du STEP illisible, une origine [x, y, z] ne peut pas "
                    "être convertie ; utiliser base ou centre_volume"
                )
            origine = r @ np.asarray(decl.origine, dtype=float) * facteur_point
        sommets = sommets - origine

        longueur = float(np.ptp(sommets[:, 0]))
        transverse = float(max(np.ptp(sommets[:, 1]), np.ptp(sommets[:, 2])))
        if transverse > longueur:
            constats.append(
                Constat(ALERTE, "axe_nez_court",
                        f"l'axe déclaré du nez ({decl.axe_nez}) n'est pas la plus grande "
                        f"dimension ({longueur:.4g} contre {transverse:.4g})",
                        "axe_nez désigne-t-il bien l'axe long de la fusée ?")
            )
        # Facteur de l'unité du fichier vers le mètre (mise à l'échelle comprise).
        echelle = facteur_point if facteur_point is not None else facteur
        if decl.longueur_imposee is not None:
            k = decl.longueur_imposee / longueur
            sommets = sommets * k
            echelle *= k
            constats.append(
                Constat(INFO, "mise_a_echelle",
                        f"maquette mise à l'échelle × {k:.6g} : {longueur:.4g} m → "
                        f"{decl.longueur_imposee:g} m")
            )
        if decl.longueur_attendue is not None:
            rapport = longueur / decl.longueur_attendue
            if abs(rapport - 1) > TOLERANCE_LONGUEUR:
                raise ErreurMaquette(
                    f"{fichier.name} mesure {longueur:.4g} m selon {decl.axe_nez}, "
                    f"{decl.longueur_attendue:g} m attendus (rapport {rapport:.4g})."
                    + _confusion(rapport)
                )
        return cls(
            sommets=sommets,
            faces=faces,
            declaration=decl,
            echelle=echelle,
            sha256=hashlib.sha256(fichier.read_bytes()).hexdigest(),
            constats=tuple(constats),
        )

    @classmethod
    def depuis_fichier(
        cls,
        fichier: str | Path,
        *,
        axe_nez: str,
        axe_haut: str,
        unite: str | None = None,
        origine: Origine = "base",
        longueur_attendue: float | None = None,
        longueur_imposee: float | None = None,
    ) -> Maquette:
        """Raccourci de :meth:`depuis_declaration`."""
        return cls.depuis_declaration(
            DeclarationMaquette(
                fichier=Path(fichier), axe_nez=axe_nez, axe_haut=axe_haut, unite=unite,
                origine=origine, longueur_attendue=longueur_attendue,
                longueur_imposee=longueur_imposee,
            )
        )
