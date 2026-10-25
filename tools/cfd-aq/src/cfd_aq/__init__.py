"""cfd-aq — excrescence drag of surface steps and ridges.

Given a step height, the local flow and the boundary layer it sits in, the
package answers the question a CFD or structures engineer asks when a panel
joint, a door edge or a fairing lip does not come out flush: *how much drag
does this cost?*

The method is the one of AGARDograph **AGARD-AG-264**, *Aircraft Excrescence
Drag*, A. D. Young & J. H. Paterson, 1981, §4.3 — the RAE (Gaudet & Winter)
and ARA (Pallister) correlations, which collapse the drag of an excrescence
deeply immersed in a turbulent boundary layer onto a single roughness Reynolds
number:

    CDe/Cfe = f(h⁺, M),      h⁺ = u_τ·h/ν_w

Three shapes are covered: the forward-facing step (§4.3.1.1), the
rearward-facing step (§4.3.1.2) and the ridge that combines them (§4.3.2),
with the rounding, chamfer, thickness and sweep corrections the report gives.

Standing assumptions, all inherited from the source data:

* fully turbulent boundary layer, no transition effects;
* zero pressure gradient — see
  :func:`~cfd_aq.core.trainee.facteur_amplification_nash_bradshaw` for the
  Nash–Bradshaw correction when that fails;
* two-dimensional excrescence, long compared with its height;
* excrescence deeply immersed, h/δ ≤ 0.03;
* measured over h⁺ = 10 to 2000 and M = 0.2 to 2.8.

Everything the package reads off a figure rather than a printed table is
collected in :mod:`cfd_aq.core.donnees`, with its uncertainty.
"""

from __future__ import annotations

from cfd_aq.core.atmosphere import etat_isa
from cfd_aq.core.couche_limite import (
    CoucheLimite,
    EtatLocal,
    cf_plaque_plane,
    epaisseur_plaque_plane,
    temperature_paroi_adiabatique,
    temperature_reference_eckert,
    viscosite_sutherland,
)
from cfd_aq.core.marches import (
    Avertissement,
    TypeAsperite,
    facteur_arrondi_descendante,
    facteur_arrondi_montante,
    facteur_chanfrein_descendante,
    facteur_chanfrein_montante,
    facteur_derapage,
    facteur_epaisseur_arete,
    interference_arete,
    ratio_arete,
    ratio_arete_rectangulaire_2h,
    ratio_asperite,
    ratio_marche_descendante,
    ratio_marche_montante,
    verifier_domaine,
)
from cfd_aq.core.trainee import (
    Asperite,
    ResultatTrainee,
    calculer_trainee,
    facteur_amplification_nash_bradshaw,
)

__version__ = "1.0.0"

__all__ = [
    "Asperite",
    "Avertissement",
    "CoucheLimite",
    "EtatLocal",
    "ResultatTrainee",
    "TypeAsperite",
    "__version__",
    "calculer_trainee",
    "cf_plaque_plane",
    "epaisseur_plaque_plane",
    "etat_isa",
    "facteur_amplification_nash_bradshaw",
    "facteur_arrondi_descendante",
    "facteur_arrondi_montante",
    "facteur_chanfrein_descendante",
    "facteur_chanfrein_montante",
    "facteur_derapage",
    "facteur_epaisseur_arete",
    "interference_arete",
    "ratio_arete",
    "ratio_arete_rectangulaire_2h",
    "ratio_asperite",
    "ratio_marche_descendante",
    "ratio_marche_montante",
    "temperature_paroi_adiabatique",
    "temperature_reference_eckert",
    "verifier_domaine",
    "viscosite_sutherland",
]
