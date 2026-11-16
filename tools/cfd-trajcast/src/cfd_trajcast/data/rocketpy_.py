"""Adaptateur RocketPy : un ``rocketpy.Flight`` → :class:`Trajectoire` (événements compris).

Conventions de RocketPy, vérifiées sur une simulation réelle (``tests/test_rocketpy.py``) :

* ``Flight.solution`` : lignes ``[t, x, y, z, vx, vy, vz, e0, e1, e2, e3, w1, w2, w3]`` ;
* repère inertiel **ENU** centré sur la rampe, mais ``z`` est l'**altitude au-dessus du
  niveau de la mer** : on retranche ``env.elevation`` (origine = rampe, comme partout) ;
* quaternion ``(e0, e1, e2, e3)``, scalaire en tête, rotation **corps → inertiel** ;
* repère corps RocketPy : ``z`` le long de l'axe, **vers le nez** (``tail_to_nose``), ``x``
  et ``y`` transverses. Il est ramené en FRD par la permutation circulaire
  ``x_FRD = z_rp, y_FRD = x_rp, z_FRD = y_rp`` (directe, donc sans changer la chiralité).
  Le roulis de la maquette se règle ensuite comme d'habitude, par ``maquette.axe_haut``.

L'adaptateur ne fait qu'**accéder aux attributs** du vol : il n'importe pas RocketPy,
qui ne sert qu'au script de l'utilisateur (RocketPy exige Python ≥ 3.10 ; le reste du
paquet tourne en 3.9). La simulation est exécutée par :func:`executer_script`, puis
mise en cache (:mod:`cfd_trajcast.data.cache`) : un rendu relancé ne la refait pas.
"""

from __future__ import annotations

import os
import runpy
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from cfd_trajcast.core import rotations as rot
from cfd_trajcast.data import cache
from cfd_trajcast.data.constats import INFO, Constat
from cfd_trajcast.data.trajectoire import (
    DeclarationAttitude,
    DeclarationTrajectoire,
    ErreurTrajectoire,
    Evenement,
    Trajectoire,
)

__all__ = [
    "DECLARATION_ROCKETPY",
    "GRANDEURS_ROCKETPY",
    "SUFFIXES_ENTREES",
    "ErreurRocketPy",
    "TableauVol",
    "executer_script",
    "tableau_depuis_flight",
    "trajectoire_depuis_flight",
    "trajectoire_depuis_script",
]

Tableau = NDArray[np.float64]

#: Grandeurs de ``Flight`` échantillonnées par défaut (noms RocketPy, unités RocketPy :
#: Pa, degrés, N, m/s). Celles qu'une version de RocketPy n'a pas sont ignorées.
GRANDEURS_ROCKETPY = (
    "mach_number", "dynamic_pressure", "angle_of_attack", "speed", "stability_margin",
    "net_thrust", "path_angle", "attitude_angle", "free_stream_speed",
)

#: Le quaternion lu est corps FRD → ENU, déjà en convention interne.
DECLARATION_ROCKETPY = DeclarationTrajectoire(
    repere="ENU",
    attitude=DeclarationAttitude(type="quaternion", colonnes=("qw", "qx", "qy", "qz")),
)

#: Fichiers du dossier du script pris dans la clé de cache (moteurs, courbes, tables).
SUFFIXES_ENTREES = (".py", ".eng", ".rse", ".csv", ".txt", ".json", ".yaml", ".yml")

#: Corps RocketPy → FRD : colonnes = axes FRD exprimés dans le repère corps RocketPy.
_FRD_DANS_RP = np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]])
_Q_FRD_VERS_RP = rot.depuis_matrice(_FRD_DANS_RP)


class ErreurRocketPy(ErreurTrajectoire):
    """Le script ou le vol RocketPy ne peut pas être lu."""


@dataclass(frozen=True, eq=False)
class TableauVol:
    """Ce qu'on garde d'un vol : une table (convention interne) et ses événements."""

    table: pd.DataFrame
    evenements: tuple[Evenement, ...]
    constats: tuple[Constat, ...] = ()


def _echantillonner(flight: Any, nom: str, t: Tableau) -> Tableau | None:
    """Une ``rocketpy.Function`` du vol aux instants ``t`` ; ``None`` si absente ou illisible."""
    try:
        fonction = getattr(flight, nom)
        valeurs = np.asarray(fonction.get_value(t), dtype=float).reshape(-1)
    except Exception:
        return None
    if valeurs.shape != t.shape or not np.all(np.isfinite(valeurs)):
        return None
    return valeurs


def _evenements(flight: Any, t0: float, t1: float, z_sol: Tableau) -> list[Evenement]:
    candidats: list[tuple[Any, str]] = [
        (getattr(flight, "out_of_rail_time", None), "Sortie de rampe"),
        (getattr(getattr(getattr(flight, "rocket", None), "motor", None), "burn_out_time", None),
         "Fin de propulsion"),
        (getattr(flight, "apogee_time", None), "Apogée"),
    ]
    for t, parachute in getattr(flight, "parachute_events", None) or []:
        candidats.append((t, f"Parachute « {getattr(parachute, 'name', 'parachute')} »"))
    if float(z_sol[-1]) < 1.0 and not getattr(flight, "terminate_on_apogee", False):
        candidats.append((t1, "Impact"))
    out = []
    for t, nom in candidats:
        try:
            tf = float(t)
        except (TypeError, ValueError):
            continue
        if np.isfinite(tf) and t0 <= tf <= t1:
            out.append(Evenement(t=tf, nom=nom))
    return sorted(out, key=lambda e: e.t)


def tableau_depuis_flight(flight: Any, grandeurs: Sequence[str] = GRANDEURS_ROCKETPY) -> TableauVol:
    """Table ``t, x, y, z, qw, qx, qy, qz`` (ENU depuis la rampe, FRD → ENU) + grandeurs + événements."""
    try:
        sol = np.asarray(flight.solution, dtype=float)
    except AttributeError:
        raise ErreurRocketPy(
            f"l'objet rendu ({type(flight).__name__}) n'a pas d'attribut `solution` : "
            "la fonction doit renvoyer un rocketpy.Flight"
        ) from None
    if sol.ndim != 2 or sol.shape[1] < 14 or len(sol) < 2:
        raise ErreurRocketPy(f"Flight.solution de forme {sol.shape} : (N ≥ 2, 14) attendu")
    constats = []
    # Les instants d'événements peuvent être répétés : on garde la dernière ligne de chaque instant.
    t_brut = sol[:, 0]
    garde = np.append(np.diff(t_brut) > 0, True)
    if not garde.all():
        constats.append(Constat(INFO, "rocketpy_doublons",
                                f"{int((~garde).sum())} instant(s) répété(s) de Flight.solution retiré(s)"))
    sol = sol[garde]
    if np.any(np.diff(sol[:, 0]) <= 0):
        raise ErreurRocketPy("Flight.solution : temps non croissant")
    t = sol[:, 0]
    altitude_rampe = float(getattr(getattr(flight, "env", None), "elevation", 0.0) or 0.0)
    positions = sol[:, 1:4] - np.array([0.0, 0.0, altitude_rampe])
    q_rp = rot.normaliser(sol[:, 7:11])
    q = rot.continuite_hemisphere(rot.produit(q_rp, _Q_FRD_VERS_RP))[0]
    table = pd.DataFrame({"t": t, "x": positions[:, 0], "y": positions[:, 1], "z": positions[:, 2],
                          "qw": q[:, 0], "qx": q[:, 1], "qy": q[:, 2], "qz": q[:, 3],
                          "vx": sol[:, 4], "vy": sol[:, 5], "vz": sol[:, 6],
                          "w1": sol[:, 11], "w2": sol[:, 12], "w3": sol[:, 13]})
    absentes = []
    for nom in grandeurs:
        if nom in table.columns:
            continue
        valeurs = _echantillonner(flight, nom, t)
        if valeurs is None:
            absentes.append(nom)
        else:
            table[nom] = valeurs
    if absentes:
        constats.append(Constat(INFO, "rocketpy_grandeurs",
                                f"grandeur(s) RocketPy indisponible(s), ignorée(s) : {', '.join(absentes)}"))
    evenements = _evenements(flight, float(t[0]), float(t[-1]), positions[:, 2])
    return TableauVol(table=table, evenements=tuple(evenements), constats=tuple(constats))


def _trajectoire(vol: TableauVol, evenements: Sequence[Evenement], source: str) -> Trajectoire:
    tous = {(e.t, e.nom): e for e in (*vol.evenements, *evenements)}
    traj = Trajectoire.depuis_dataframe(vol.table, declaration=DECLARATION_ROCKETPY,
                                        evenements=tuple(tous.values()), source=source)
    return replace(traj, constats=(*vol.constats, *traj.constats))


def trajectoire_depuis_flight(flight: Any, *, grandeurs: Sequence[str] = GRANDEURS_ROCKETPY,
                              evenements: Sequence[Evenement] = ()) -> Trajectoire:
    """Un ``rocketpy.Flight`` déjà calculé → :class:`Trajectoire`. ``evenements`` s'ajoutent aux siens."""
    return _trajectoire(tableau_depuis_flight(flight, grandeurs), evenements,
                        f"RocketPy ({getattr(flight, 'name', 'Flight')})")


@contextmanager
def _dans(dossier: Path) -> Iterator[None]:
    """Le script tourne depuis son dossier (chemins relatifs des moteurs) et peut y importer."""
    avant = Path.cwd()
    sys.path.insert(0, str(dossier))
    os.chdir(dossier)
    try:
        yield
    finally:
        os.chdir(avant)
        with suppress(ValueError):
            sys.path.remove(str(dossier))


def executer_script(script: Path, fonction: str = "simuler") -> Any:
    """Exécute ``script`` et appelle ``fonction()`` (sans argument) : le ``Flight`` qu'elle renvoie."""
    script = Path(script).resolve()
    if not script.is_file():
        raise ErreurRocketPy(f"script RocketPy introuvable : {script}")
    with _dans(script.parent):
        try:
            espace = runpy.run_path(str(script), run_name="cfd_trajcast_rocketpy")
        except ImportError as exc:
            raise ErreurRocketPy(
                f"{script.name} : {exc}. RocketPy s'installe par pip install 'cfd-trajcast[rocketpy]' "
                "(Python ≥ 3.10)"
            ) from None
        appel = espace.get(fonction)
        if not callable(appel):
            raise ErreurRocketPy(f"{script.name} : pas de fonction `{fonction}()`")
        return appel()


def _version_rocketpy() -> str:
    from importlib import metadata

    try:
        return metadata.version("rocketpy")
    except metadata.PackageNotFoundError:
        return "absent"


def cle_script(script: Path, fonction: str, grandeurs: Sequence[str]) -> str:
    """Empreinte d'une simulation : le script, les entrées de son dossier, la fonction, RocketPy."""
    script = Path(script).resolve()
    parties: list[bytes | str] = ["rocketpy-v1", fonction, ",".join(grandeurs), _version_rocketpy()]
    for p in sorted(script.parent.iterdir()):
        if p.is_file() and p.suffix.lower() in SUFFIXES_ENTREES:
            parties += [p.name, p.read_bytes()]
    return cache.empreinte(*parties)


def trajectoire_depuis_script(script: str | Path, fonction: str = "simuler", *,
                              grandeurs: Sequence[str] = GRANDEURS_ROCKETPY,
                              evenements: Sequence[Evenement] = (),
                              utiliser_cache: bool = True) -> Trajectoire:
    """Exécute la simulation (ou relit son cache) et la convertit.

    Clé de cache : le script, les fichiers d'entrée de son dossier (``SUFFIXES_ENTREES``),
    ``fonction``, ``grandeurs`` et la version de RocketPy. Un fichier lu ailleurs que dans
    ce dossier n'y est pas : ``utiliser_cache=False`` (``--sans-cache``) force le calcul.
    """
    script = Path(script).resolve()
    cle = cle_script(script, fonction, grandeurs) if script.is_file() else ""
    vol: TableauVol | None = None
    if utiliser_cache and cle:
        vol = _relire(cle)
    if vol is None:
        vol = tableau_depuis_flight(executer_script(script, fonction), grandeurs)
        if utiliser_cache:
            _ecrire(cle, vol)
    else:
        vol = TableauVol(vol.table, vol.evenements,
                         (*vol.constats, Constat(INFO, "cache", f"vol RocketPy relu du cache ({cle[:12]}…)")))
    return _trajectoire(vol, evenements, f"RocketPy ({script.name}:{fonction})")


def _ecrire(cle: str, vol: TableauVol) -> None:
    tableaux = {f"c_{c}": vol.table[c].to_numpy(dtype=float) for c in vol.table.columns}
    tableaux["evenements_t"] = np.array([e.t for e in vol.evenements], dtype=float)
    tableaux["evenements_nom"] = np.array([e.nom for e in vol.evenements], dtype=str)
    cache.ecrire("rocketpy", cle, tableaux)


def _relire(cle: str) -> TableauVol | None:
    tableaux = cache.lire("rocketpy", cle)
    if tableaux is None:
        return None
    table = pd.DataFrame({k[2:]: v for k, v in tableaux.items() if k.startswith("c_")})
    evts = tuple(Evenement(t=float(t), nom=str(n))
                 for t, n in zip(tableaux["evenements_t"], tableaux["evenements_nom"]))
    return TableauVol(table=table, evenements=evts)
