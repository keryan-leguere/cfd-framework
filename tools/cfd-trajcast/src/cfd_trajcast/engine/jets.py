"""Géométrie des jets, en NumPy pur : flammes (repère de la tuyère) et fumées (repère terrestre).

**Flamme** — surface de révolution autour de l'axe −x (la tuyère est à l'origine,
le jet part vers l'arrière). Profil de rayon, pour ``u = s / L`` :

    r(u) = (r₀ + s·tan θ) · (1 − u³)^½

il s'évase d'un demi-angle θ puis se referme en douceur au bout. Couleur
interpolée le long de ``couleurs``, opacité décroissante vers le bout. Un cœur
blanc plus court et plus étroit, et des disques de Mach (ellipsoïdes brillants)
en option. Le moteur la dessine sans éclairage : elle émet sa lumière.

**Fumée** — une ligne de points émis par la tuyère aux instants passés τ, figés
dans l'air : rayon ``r₀·rayon + d·tan(évasement) + expansion·âge`` (``d`` : distance
le long de la fumée depuis la tuyère, d'où un panache qui s'ouvre en cône), dérive
turbulente (bruit lisse en τ, amplitude proportionnelle à l'âge), couleur et
opacité qui évoluent avec l'âge. Elle apparaît progressivement derrière la
flamme au lieu de la recouvrir. Chaque point garde le jet de la **phase active à son émission** : une
fumée d'étage 1 continue de vieillir pendant que l'étage 2 émet la sienne.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.core import rotations as rot
from cfd_trajcast.data.configuration import Flamme, Jet
from cfd_trajcast.engine.textures import teinte

__all__ = ["Coque", "Phase", "coques_flamme", "fumee", "lumiere_jets", "phase_active", "scintillement", "tube"]

Tableau = NDArray[np.float64]


@dataclass(frozen=True)
class Phase:
    """Phase de propulsion aux instants résolus (s de vol)."""

    de: float
    a: float
    jet: Jet


@dataclass(frozen=True, eq=False)
class Coque:
    """Un maillage triangulé avec une couleur RGBA par sommet."""

    points: Tableau
    faces: NDArray[np.int64]
    rgba: NDArray[np.uint8]


def _degrade(couleurs: Sequence[str], u: Tableau) -> Tableau:
    """Couleur (r, g, b) ∈ [0 ; 1] interpolée le long de ``couleurs`` pour u ∈ [0 ; 1]."""
    c = np.array([teinte(x) for x in couleurs])
    pos = np.linspace(0, 1, len(c))
    return np.stack([np.interp(u, pos, c[:, i]) for i in range(3)], axis=-1)


def _revolution(rayons: Tableau, abscisses: Tableau, n_tour: int) -> tuple[Tableau, NDArray[np.int64]]:
    """Surface de révolution autour de −x ; une rangée de sommets par abscisse."""
    theta = np.linspace(0, 2 * np.pi, n_tour, endpoint=False)
    x = -np.repeat(abscisses, n_tour)
    r = np.repeat(rayons, n_tour)
    t = np.tile(theta, len(abscisses))
    points = np.stack([x, r * np.cos(t), r * np.sin(t)], axis=1)
    faces = []
    for i in range(len(abscisses) - 1):
        for j in range(n_tour):
            a, b = i * n_tour + j, i * n_tour + (j + 1) % n_tour
            c, d = a + n_tour, b + n_tour
            faces += [[a, b, d], [a, d, c]]
    return points, np.asarray(faces, dtype=np.int64)


def _rgba(rgb: Tableau, alpha: Tableau, n_tour: int) -> NDArray[np.uint8]:
    out = np.concatenate([np.repeat(rgb, n_tour, axis=0), np.repeat(alpha, n_tour)[:, None]], axis=1)
    return np.asarray(np.clip(out, 0, 1) * 255, dtype=np.uint8)


def _ellipsoide(centre_x: float, ax: float, ar: float, rgb: Tableau, alpha: float,
                n: int = 12) -> Coque:
    u = np.linspace(0, np.pi, n)
    v = np.linspace(0, 2 * np.pi, 2 * n, endpoint=False)
    uu, vv = np.meshgrid(u, v, indexing="ij")
    points = np.stack([centre_x + ax * np.cos(uu).ravel(), ar * (np.sin(uu) * np.cos(vv)).ravel(),
                       ar * (np.sin(uu) * np.sin(vv)).ravel()], axis=1)
    faces = []
    m = 2 * n
    for i in range(n - 1):
        for j in range(m):
            a, b = i * m + j, i * m + (j + 1) % m
            faces += [[a, b, b + m], [a, b + m, a + m]]
    rgba = np.tile(np.append(rgb, alpha), (len(points), 1))
    return Coque(points, np.asarray(faces, dtype=np.int64), np.asarray(np.clip(rgba, 0, 1) * 255, dtype=np.uint8))


def coques_flamme(f: Flamme, r0: float, n_long: int = 40, n_tour: int = 32) -> list[Coque]:
    """Coques de la flamme (enveloppe, cœur, disques de Mach), tuyère à l'origine, jet vers −x."""
    longueur = f.longueur * r0
    u = np.linspace(0, 1, n_long)
    s = u * longueur
    tan_t = np.tan(np.radians(f.evasement))
    rayon = (r0 + s * tan_t) * np.sqrt(np.clip(1 - u**3, 0, 1))
    points, faces = _revolution(rayon, s, n_tour)
    alpha = f.opacite * (1 - u) ** 1.3
    coques = [Coque(points, faces, _rgba(_degrade(f.couleurs, u), alpha, n_tour))]
    if f.coeur > 0:
        lc = f.coeur * longueur
        sc = u * lc
        rc = 0.55 * (r0 + sc * tan_t * 0.5) * np.sqrt(np.clip(1 - u**2, 0, 1))
        pc, fc = _revolution(rc, sc, n_tour)
        couleurs_coeur = ("#ffffff", *f.couleurs[:1])
        coques.append(Coque(pc, fc, _rgba(_degrade(couleurs_coeur, u), np.minimum(1.0, 0.95 * (1 - u) ** 0.7 + 0.05),
                                          n_tour)))
    for k in range(f.diamants):
        sk = r0 * (1.0 + 1.5 * k)
        if sk > 0.75 * longueur:
            break
        rk = float(np.interp(sk, s, rayon))
        eclat = 0.9 * (1 - k / max(f.diamants, 1)) + 0.1
        coques.append(_ellipsoide(-sk, 0.35 * r0, 0.6 * rk, teinte("#fff6d0"), eclat))
    return coques


def scintillement(t: float, amplitude: float, graine: int = 0) -> float:
    """Facteur de longueur ≈ 1 ± amplitude, bruit lisse et déterministe (somme de sinus)."""
    if amplitude <= 0:
        return 1.0
    phases = 1.7 * graine + np.array([0.0, 1.3, 2.9])
    bruit = (np.sin(31.0 * t + phases[0]) + 0.6 * np.sin(53.0 * t + phases[1]) + 0.4 * np.sin(97.0 * t + phases[2])) / 2.0
    return float(1.0 + amplitude * bruit)


def phase_active(t: float, phases: Sequence[Phase], fondu: float) -> list[tuple[int, float]]:
    """(indice, poids) des phases visibles à ``t`` ; poids < 1 pendant les fondus d'entrée et de sortie."""
    out = []
    for i, p in enumerate(phases):
        if p.de - fondu / 2 <= t <= p.a + fondu / 2:
            if fondu > 0:
                poids = min(1.0, (t - (p.de - fondu / 2)) / fondu, ((p.a + fondu / 2) - t) / fondu)
            else:
                poids = 1.0
            if poids > 0:
                out.append((i, float(min(poids, 1.0))))
    return out


def _poids_phase(tau: Tableau, p: Phase, fondu: float) -> Tableau:
    """Poids de la phase ``p`` aux instants ``tau`` (fondus compris), vectorisé."""
    if fondu <= 0:
        return ((tau >= p.de) & (tau <= p.a)).astype(float)
    return np.asarray(np.clip(np.minimum((tau - (p.de - fondu / 2)) / fondu, ((p.a + fondu / 2) - tau) / fondu), 0, 1))


def _bruit_lisse(tau: Tableau, graine: int) -> Tableau:
    """Vecteur 3D lisse en τ, d'amplitude ≈ 1 — la turbulence de la fumée."""
    rng = np.random.default_rng(graine)
    freq = rng.uniform(0.3, 1.6, size=(3, 3))
    phase = rng.uniform(0, 2 * np.pi, size=(3, 3))
    return np.stack([np.sum(np.sin(np.outer(tau, freq[i]) + phase[i]), axis=1) / 1.7 for i in range(3)], axis=1)


def fumee(t: float, trace_t: Tableau, trace: Tableau, trace_attitudes: Tableau, tuyere: Tableau,
          r0: float, phases: Sequence[Phase], fondu: float, position: Tableau, attitude: Tableau,
          graine: int = 0) -> tuple[Tableau, Tableau, NDArray[np.uint8]] | None:
    """Ligne de fumée d'une tuyère à l'instant ``t`` : points (relatifs à ``position``), rayons, RGBA.

    ``None`` s'il n'y a rien à dessiner.
    """
    durees = [p.jet.fumee.duree for p in phases if p.jet.fumee is not None]
    if not durees:
        return None
    dedans = (trace_t >= t - max(durees)) & (trace_t < t)
    tau = np.append(trace_t[dedans], t)
    base = np.vstack([trace[dedans], position[None, :]])
    att = np.vstack([trace_attitudes[dedans], attitude[None, :]])
    points = base + rot.tourner(att, tuyere) - position
    age = t - tau
    # Distance le long de la fumée depuis la tuyère (le point le plus récent est le dernier).
    pas = np.linalg.norm(np.diff(points, axis=0), axis=1)
    distance = np.concatenate([np.cumsum(pas[::-1])[::-1], [0.0]])
    rayons = np.zeros(len(tau))
    rgb = np.zeros((len(tau), 3))
    alpha = np.zeros(len(tau))
    derive = np.zeros((len(tau), 3))
    bruit = _bruit_lisse(tau, graine)
    for p in phases:
        f = p.jet.fumee
        if f is None:
            continue
        w = _poids_phase(tau, p, fondu)
        m = w > 0
        if not m.any():
            continue
        rel = np.clip(age[m] / f.duree, 0, 1)
        # Apparition derrière la flamme : opacité nulle à la tuyère, pleine après 1,2 flamme.
        longueur_flamme = (p.jet.flamme.longueur if p.jet.flamme is not None else 3.0) * r0
        apparition = np.clip(distance[m] / (1.2 * longueur_flamme), 0, 1)
        a_i = f.opacite * w[m] * (1 - rel) ** 1.3 * apparition * apparition * (3 - 2 * apparition)
        prend = a_i > alpha[m]
        idx = np.flatnonzero(m)[prend]
        alpha[idx] = a_i[prend]
        rayons[idx] = (r0 * f.rayon + distance[idx] * np.tan(np.radians(f.evasement))
                       + f.expansion * age[idx])
        rgb[idx] = _degrade((f.couleur_debut, f.couleur_fin), rel[prend])
        derive[idx] = f.turbulence * age[idx, None] * bruit[idx]
    if not np.any(alpha > 0.01):
        return None
    rayons = np.where(rayons > 0, rayons, r0)
    rgba = np.asarray(np.clip(np.concatenate([rgb, alpha[:, None]], axis=1), 0, 1) * 255, dtype=np.uint8)
    return points + derive, rayons, rgba


def lumiere_jets(t: float, phases: Sequence[Phase], tuyeres: Tableau, rayon: float, fondu: float,
                 attitude: Tableau) -> tuple[Tableau, Tableau, float] | None:
    """Lumière émise par les flammes : (position relative à la maquette, couleur RGB, poids).

    Une seule source, au barycentre des tuyères, une demi-flamme en arrière ; couleur
    entre le cœur et le milieu de la flamme ; poids = somme des phases actives
    (fondus compris), modulée par le scintillement. ``None`` sans flamme visible.
    """
    poids_total, couleur, distance = 0.0, np.zeros(3), 0.0
    for i, w in phase_active(t, phases, fondu):
        f = phases[i].jet.flamme
        if f is None:
            continue
        w *= scintillement(t, f.scintillement, graine=31 * i)
        couleur += w * _degrade(f.couleurs, np.array([0.3]))[0]
        distance += w * 0.5 * f.longueur * rayon
        poids_total += w
    if poids_total <= 0.01:
        return None
    couleur, distance = couleur / poids_total, distance / poids_total
    r = rot.vers_matrice(attitude)
    position = r @ (np.mean(tuyeres, axis=0) + np.array([-distance, 0.0, 0.0]))
    return position, np.clip(couleur, 0, 1), float(min(poids_total, 1.5))


def tube(points: Tableau, rayons: Tableau, n_cotes: int = 16) -> tuple[Tableau, NDArray[np.int64]]:
    """Tube autour d'une ligne polygonale (cadres à transport parallèle, sans torsion) : sommets, faces.

    Une rangée de ``n_cotes`` sommets par point de la ligne, dans l'ordre ; pour les
    moteurs qui n'ont pas de filtre « tube » (Blender).
    """
    n = len(points)
    if n < 2:
        raise ValueError("un tube demande au moins deux points")
    tangentes = np.gradient(points, axis=0)
    tangentes /= np.maximum(np.linalg.norm(tangentes, axis=1, keepdims=True), 1e-12)
    # Premier normal : perpendiculaire à la première tangente, puis transporté point à point.
    a = np.array([0.0, 0.0, 1.0]) if abs(tangentes[0, 2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    normal = np.cross(tangentes[0], a)
    normal /= np.linalg.norm(normal)
    normaux = np.empty_like(points)
    for i in range(n):
        normal = normal - tangentes[i] * (normal @ tangentes[i])
        normal /= max(float(np.linalg.norm(normal)), 1e-12)
        normaux[i] = normal
    binormaux = np.cross(tangentes, normaux)
    theta = np.linspace(0, 2 * np.pi, n_cotes, endpoint=False)
    sommets = (points[:, None, :] + rayons[:, None, None]
               * (np.cos(theta)[None, :, None] * normaux[:, None, :]
                  + np.sin(theta)[None, :, None] * binormaux[:, None, :])).reshape(-1, 3)
    rangee = np.arange(n - 1)[:, None]
    cote = np.arange(n_cotes)[None, :]
    a0 = rangee * n_cotes + cote
    b0 = rangee * n_cotes + (cote + 1) % n_cotes
    faces = np.stack([np.stack([a0, b0, b0 + n_cotes], -1), np.stack([a0, b0 + n_cotes, a0 + n_cotes], -1)], axis=2)
    return sommets, faces.reshape(-1, 3).astype(np.int64)
