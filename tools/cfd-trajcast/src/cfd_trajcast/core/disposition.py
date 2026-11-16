"""Dispositions multi-vues : comment les vues se partagent l'image, en pixels.

Une disposition se réduit à une liste ordonnée de :class:`Case` (nom de la vue ou
``"telemetrie"``, rectangle en pixels) ; l'ordre est l'ordre de dessin, donc les
incrustations viennent après la vue qu'elles recouvrent. Tous les rectangles ont
des dimensions **paires** (chaque vue est rendue à la taille exacte de sa case).

Types :

* ``unique`` : une vue, plus éventuellement une bande de télémétrie ;
* ``incrustation`` : une vue principale, des vues en médaillon dans ses coins ;
* ``grille`` : des rangées de cases égales (``"telemetrie"`` peut en être une) ;
* ``libre`` : des rectangles donnés en fractions de l'image.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "COINS",
    "TELEMETRIE",
    "TYPES",
    "Case",
    "Disposition",
    "Incrustation",
    "agencer",
    "vues_citees",
]

TYPES = ("unique", "incrustation", "grille", "libre")
COINS = ("haut_gauche", "haut_droite", "bas_gauche", "bas_droite")
#: Nom réservé de la case du panneau de télémétrie.
TELEMETRIE = "telemetrie"
#: Côtés possibles de la bande de télémétrie (``unique`` / ``incrustation``).
COTES_TELEMETRIE = ("droite", "gauche", "bas", "aucune")
#: Part de l'image prise par la bande de télémétrie.
PART_TELEMETRIE = {"droite": 0.28, "gauche": 0.28, "bas": 0.24}
#: Marge des médaillons, en fraction de la largeur de l'image.
MARGE = 0.015


@dataclass(frozen=True)
class Case:
    """Un rectangle de l'image : ``x``, ``y`` depuis le coin haut-gauche, en pixels."""

    nom: str
    x: int
    y: int
    largeur: int
    hauteur: int
    medaillon: bool = False

    @property
    def taille(self) -> tuple[int, int]:
        """``(largeur, hauteur)``."""
        return self.largeur, self.hauteur


@dataclass(frozen=True)
class Incrustation:
    """Une vue en médaillon. ``largeur`` en fraction de la largeur de l'image."""

    vue: str
    coin: str = "bas_gauche"
    largeur: float = 0.25

    def __post_init__(self) -> None:
        if self.coin not in COINS:
            raise ValueError(f"coin {self.coin!r} : {', '.join(COINS)}")
        if not 0.05 <= self.largeur <= 0.6:
            raise ValueError("largeur d'un médaillon : entre 0.05 et 0.6 de l'image")


@dataclass(frozen=True)
class Disposition:
    """Description d'une disposition ; :func:`agencer` la traduit en pixels."""

    type: str = "unique"
    principale: str | None = None
    telemetrie: str = "aucune"
    incrustations: tuple[Incrustation, ...] = ()
    cases: tuple[tuple[str, ...], ...] = ()
    libres: tuple[tuple[str, tuple[float, float, float, float]], ...] = ()

    def __post_init__(self) -> None:
        if self.type not in TYPES:
            raise ValueError(f"type {self.type!r} : {', '.join(TYPES)}")
        if self.telemetrie not in COTES_TELEMETRIE:
            raise ValueError(f"telemetrie {self.telemetrie!r} : {', '.join(COTES_TELEMETRIE)}")
        if self.type in ("unique", "incrustation") and not self.principale:
            raise ValueError(f"une disposition {self.type} demande une vue principale")
        if self.type == "incrustation" and not self.incrustations:
            raise ValueError("une disposition incrustation demande au moins un médaillon")
        if self.type == "grille" and (not self.cases or any(not r for r in self.cases)):
            raise ValueError("une grille demande des rangées non vides de cases")
        if self.type == "libre":
            if not self.libres:
                raise ValueError("une disposition libre demande des cases")
            for vue, (x, y, l_, h) in self.libres:
                if not (x >= 0 and y >= 0 and l_ > 0 and h > 0 and x + l_ <= 1 + 1e-9 and y + h <= 1 + 1e-9):
                    raise ValueError(f"case {vue} : rectangle [x, y, l, h] hors de l'image (fractions 0 → 1)")
        coins = [i.coin for i in self.incrustations]
        if len(set(coins)) != len(coins):
            raise ValueError("deux médaillons dans le même coin")


def vues_citees(d: Disposition) -> list[str]:
    """Noms des vues (et ``telemetrie``) qu'une disposition affiche."""
    noms: list[str] = []
    if d.principale:
        noms.append(d.principale)
    noms += [i.vue for i in d.incrustations]
    noms += [n for rangee in d.cases for n in rangee]
    noms += [vue for vue, _ in d.libres]
    if d.type in ("unique", "incrustation") and d.telemetrie != "aucune":
        noms.append(TELEMETRIE)
    return noms


def _pair(v: float) -> int:
    return max(2, round(v / 2) * 2)


def _bande(d: Disposition, largeur: int, hauteur: int) -> tuple[Case | None, tuple[int, int, int, int]]:
    """Case de télémétrie et zone restante ``(x, y, l, h)``."""
    if d.telemetrie == "aucune":
        return None, (0, 0, largeur, hauteur)
    if d.telemetrie == "bas":
        h = _pair(hauteur * PART_TELEMETRIE["bas"])
        return Case(TELEMETRIE, 0, hauteur - h, largeur, h), (0, 0, largeur, hauteur - h)
    l_ = _pair(largeur * PART_TELEMETRIE[d.telemetrie])
    if d.telemetrie == "droite":
        return Case(TELEMETRIE, largeur - l_, 0, l_, hauteur), (0, 0, largeur - l_, hauteur)
    return Case(TELEMETRIE, 0, 0, l_, hauteur), (l_, 0, largeur - l_, hauteur)


def agencer(d: Disposition, largeur: int, hauteur: int) -> tuple[Case, ...]:
    """Les cases de ``d`` pour une image ``largeur × hauteur``, dans l'ordre de dessin."""
    if d.type == "grille":
        cases: list[Case] = []
        n = len(d.cases)
        bords_y = [_pair(hauteur * i / n) if 0 < i < n else (0 if i == 0 else hauteur) for i in range(n + 1)]
        for r, rangee in enumerate(d.cases):
            m = len(rangee)
            bords_x = [_pair(largeur * j / m) if 0 < j < m else (0 if j == 0 else largeur) for j in range(m + 1)]
            for j, nom in enumerate(rangee):
                cases.append(Case(nom, bords_x[j], bords_y[r], bords_x[j + 1] - bords_x[j],
                                  bords_y[r + 1] - bords_y[r]))
        return tuple(cases)
    if d.type == "libre":
        out = []
        for vue, (x, y, l_, h) in d.libres:
            px, py = _pair(x * largeur) if x > 0 else 0, _pair(y * hauteur) if y > 0 else 0
            pl = min(_pair(l_ * largeur), largeur - px)
            ph = min(_pair(h * hauteur), hauteur - py)
            out.append(Case(vue, px, py, pl - pl % 2, ph - ph % 2))
        return tuple(out)
    bande, (zx, zy, zl, zh) = _bande(d, largeur, hauteur)
    assert d.principale is not None
    cases = [Case(d.principale, zx, zy, zl, zh)]
    marge = _pair(MARGE * largeur)
    for inc in d.incrustations:
        l_ = _pair(inc.largeur * largeur)
        h = _pair(l_ * hauteur / largeur)
        l_, h = min(l_, zl - 2 * marge), min(h, zh - 2 * marge)
        x = zx + marge if inc.coin.endswith("gauche") else zx + zl - marge - l_
        y = zy + marge if inc.coin.startswith("haut") else zy + zh - marge - h
        cases.append(Case(inc.vue, x, y, l_, h, medaillon=True))
    if bande is not None:
        cases.append(bande)
    return tuple(cases)
