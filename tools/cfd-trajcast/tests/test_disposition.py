"""Dispositions : cases paires, couvrantes, dans l'image."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_trajcast.core.disposition import (
    TELEMETRIE,
    Disposition,
    Incrustation,
    agencer,
    vues_citees,
)

L, H = 1920, 1080


def _couverture(cases) -> np.ndarray:  # type: ignore[no-untyped-def]
    n = np.zeros((H, L), dtype=int)
    for c in cases:
        n[c.y:c.y + c.hauteur, c.x:c.x + c.largeur] += 1
    return n


def _paires_et_dedans(cases) -> None:  # type: ignore[no-untyped-def]
    for c in cases:
        assert c.largeur % 2 == 0 and c.hauteur % 2 == 0, c
        assert 0 <= c.x and 0 <= c.y and c.x + c.largeur <= L and c.y + c.hauteur <= H, c


@pytest.mark.parametrize("cote", ["droite", "gauche", "bas", "aucune"])
def test_unique_avec_bande(cote: str) -> None:
    cases = agencer(Disposition(type="unique", principale="a", telemetrie=cote), L, H)
    _paires_et_dedans(cases)
    assert np.all(_couverture(cases) == 1)  # partition exacte de l'image
    assert (TELEMETRIE in [c.nom for c in cases]) == (cote != "aucune")


@pytest.mark.parametrize("cases_", [
    (("a", "b"), ("c", TELEMETRIE)),
    (("a",), ("b", "c", "d")),
    (("a", "b", "c"),),
])
def test_grille_partition(cases_: tuple) -> None:  # type: ignore[type-arg]
    cases = agencer(Disposition(type="grille", cases=cases_), L, 1078)
    for c in cases:
        assert c.largeur % 2 == 0 and c.hauteur % 2 == 0
    n = np.zeros((1078, L), dtype=int)
    for c in cases:
        n[c.y:c.y + c.hauteur, c.x:c.x + c.largeur] += 1
    assert np.all(n == 1)


def test_incrustations_dans_la_vue_principale() -> None:
    d = Disposition(type="incrustation", principale="a", telemetrie="droite",
                    incrustations=(Incrustation("b", "haut_droite", 0.24), Incrustation("c", "bas_gauche", 0.3)))
    cases = agencer(d, L, H)
    _paires_et_dedans(cases)
    principale, b, c, _ = cases
    assert [x.nom for x in cases] == ["a", "b", "c", TELEMETRIE] and b.medaillon and c.medaillon
    for m in (b, c):  # dans la vue principale, pas sur la télémétrie
        assert m.x >= principale.x and m.x + m.largeur <= principale.x + principale.largeur
        assert abs(m.largeur / m.hauteur - L / H) < 0.02
    assert b.x + b.largeur > principale.largeur * 0.9 and b.y < 100
    assert c.x < 100 and c.y + c.hauteur > H * 0.9


def test_libre() -> None:
    d = Disposition(type="libre", libres=(("a", (0, 0, 0.5, 1)), ("b", (0.5, 0, 0.5, 0.5))))
    a, b = agencer(d, L, H)
    assert (a.x, a.y, a.largeur, a.hauteur) == (0, 0, 960, 1080)
    assert (b.x, b.largeur, b.hauteur) == (960, 960, 540)


@pytest.mark.parametrize(("champs", "motif"), [
    ({"type": "unique"}, "principale"),
    ({"type": "incrustation", "principale": "a"}, "médaillon"),
    ({"type": "grille", "cases": ((),)}, "rangées"),
    ({"type": "libre", "libres": (("a", (0.6, 0, 0.5, 1)),)}, "hors de l'image"),
    ({"type": "unique", "principale": "a", "telemetrie": "haut"}, "telemetrie"),
    ({"type": "incrustation", "principale": "a",
      "incrustations": (Incrustation("b", "bas_gauche"), Incrustation("c", "bas_gauche"))}, "même coin"),
])
def test_refus(champs: dict, motif: str) -> None:  # type: ignore[type-arg]
    with pytest.raises(ValueError, match=motif):
        Disposition(**champs)


def test_vues_citees() -> None:
    d = Disposition(type="incrustation", principale="a", telemetrie="bas", incrustations=(Incrustation("b"),))
    assert vues_citees(d) == ["a", "b", TELEMETRIE]
