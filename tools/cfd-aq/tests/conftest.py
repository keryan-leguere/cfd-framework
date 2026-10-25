"""Shared fixtures: one realistic cruise condition, reused everywhere."""

from __future__ import annotations

import pytest

from cfd_aq import CoucheLimite, EtatLocal


@pytest.fixture()
def etat_croisiere() -> EtatLocal:
    """FL360, M = 0.82 — a transport aircraft's local flow on a clean panel."""
    return EtatLocal.isa(altitude=11000.0, mach=0.82)


@pytest.fixture()
def couche_croisiere(etat_croisiere: EtatLocal) -> CoucheLimite:
    """The flat-plate boundary layer 10 m behind the leading edge."""
    return CoucheLimite.plaque_plane(etat_croisiere, distance_bord_attaque=10.0)
