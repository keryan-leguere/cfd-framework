"""Turn a geometry plus a boundary layer into a drag force.

The assembly is short, because the physics is all in
:mod:`cfd_aq.core.marches`:

    ΔD = (CDe/Cfe) · f_forme · τ_w · f_e

with ``f_e = h·b`` the frontal area, ``τ_w`` the undisturbed wall shear stress
and ``f_forme`` the product of the shape corrections (rounding, chamfer, sweep)
the report gives as independent multiplying factors — equations 4(28) to 4(35)
and 4(41). The report applies them one at a time and never says they combine;
multiplying them, as :class:`Asperite` does, is the usual engineering
assumption and is flagged as such whenever more than one is active.

Two cautions that cost more than the correlation's own scatter:

*Local conditions, not free-stream.* ``CDe/Cfe`` is correlated against the
boundary layer the step actually sits in. A step on a wing's suction peak sees
a higher ``q_e`` and a higher ``τ_w`` than the free stream.

*Pressure gradient.* The whole §4.3 data set is zero-pressure-gradient. On an
aerofoil, the downstream history of the boundary layer changes the drag
increment — Nash & Bradshaw showed it can be much larger than simple
proportionality to the local dynamic head suggests (§5.1). The correction is
:func:`facteur_amplification_nash_bradshaw`; it is not applied automatically
because it needs trailing-edge data cfd-aq has no way to guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cfd_aq.core import marches
from cfd_aq.core.couche_limite import CoucheLimite, EtatLocal
from cfd_aq.core.marches import Avertissement, TypeAsperite

__all__ = [
    "Asperite",
    "ResultatTrainee",
    "calculer_trainee",
    "facteur_amplification_nash_bradshaw",
]


@dataclass(frozen=True)
class Asperite:
    """A spanwise step or ridge on a surface.

    Attributes:
        type_asperite: forward step, rearward step or ridge.
        hauteur: step height h [m].
        envergure: spanwise length b [m] over which the step runs.
        t_sur_h: ridge thickness over height [-]; ignored for a plain step.
        rayon_sur_h: edge radius over height r/h [-]; ignored for a ridge,
            which the report treats through its own rounded-ridge data.
        angle_chanfrein: chamfer angle θ [°], 90° meaning a square face.
        angle_derapage: angle α [°] between the flow and the excrescence axis,
            90° meaning the excrescence lies across the flow.
    """

    type_asperite: TypeAsperite
    hauteur: float
    envergure: float
    t_sur_h: float = 1.0
    rayon_sur_h: float = 0.0
    angle_chanfrein: float = 90.0
    angle_derapage: float = 90.0

    def __post_init__(self) -> None:
        if self.hauteur <= 0.0:
            raise ValueError(f"la hauteur doit être > 0 m (reçue {self.hauteur})")
        if self.envergure <= 0.0:
            raise ValueError(f"l'envergure doit être > 0 m (reçue {self.envergure})")
        if self.rayon_sur_h > 0.0 and self.angle_chanfrein < 90.0:
            raise ValueError(
                "une arête est soit arrondie soit chanfreinée, pas les deux : "
                f"r/h = {self.rayon_sur_h} et θ = {self.angle_chanfrein}°"
            )

    @property
    def aire_frontale(self) -> float:
        """Frontal area f_e = h·b [m²]."""
        return self.hauteur * self.envergure

    def facteur_forme(self, mach: float) -> float:
        """Product of the shape corrections at ``mach`` [-]."""
        facteur = marches.facteur_derapage(self.angle_derapage)

        if self.type_asperite is TypeAsperite.MONTANTE:
            if self.rayon_sur_h > 0.0:
                facteur *= marches.facteur_arrondi_montante(self.rayon_sur_h, mach)
            if self.angle_chanfrein < 90.0:
                facteur *= marches.facteur_chanfrein_montante(self.angle_chanfrein, mach)
        elif self.type_asperite is TypeAsperite.DESCENDANTE:
            if self.rayon_sur_h > 0.0:
                facteur *= marches.facteur_arrondi_descendante(self.rayon_sur_h)
            if self.angle_chanfrein < 90.0:
                facteur *= marches.facteur_chanfrein_descendante(self.angle_chanfrein, mach)
        # L'épaisseur d'une arête est déjà portée par ratio_arete() ; les
        # arêtes arrondies ou chanfreinées relèvent des Figures 4.41 à 4.44,
        # non numérisées : Asperite les refuse plus haut plutôt que de les
        # traiter comme une marche.
        return facteur


@dataclass(frozen=True)
class ResultatTrainee:
    """Everything a report needs about one excrescence.

    Attributes:
        h_plus: roughness Reynolds number [-].
        immersion: h/δ, or None when δ is unknown.
        cde_sur_cfe: plain drag ratio from the AGARD correlation [-].
        facteur_forme: product of the shape corrections applied [-].
        cde: excrescence drag coefficient on frontal area, D/(q_e·f_e) [-].
        cisaillement_paroi: τ_w [Pa].
        trainee: drag increment ΔD [N].
        delta_cx: ΔD/(q_e·S_ref) [-], None when no reference area was given.
        surface_reference: S_ref [m²], when given.
        avertissements: extrapolations the call is making.
    """

    h_plus: float
    immersion: float | None
    cde_sur_cfe: float
    facteur_forme: float
    cde: float
    cisaillement_paroi: float
    trainee: float
    delta_cx: float | None = None
    surface_reference: float | None = None
    avertissements: list[Avertissement] = field(default_factory=list)


def calculer_trainee(
    asperite: Asperite,
    etat: EtatLocal,
    couche_limite: CoucheLimite,
    surface_reference: float | None = None,
    amplification: float = 1.0,
) -> ResultatTrainee:
    """Drag increment of one excrescence.

    Args:
        asperite: the step or ridge.
        etat: local flow state at the boundary-layer edge.
        couche_limite: the undisturbed boundary layer at the same station.
        surface_reference: S_ref [m²] for the ΔCx output; omitted if None.
        amplification: pressure-gradient magnification factor m_d, 1 on a flat
            plate — see :func:`facteur_amplification_nash_bradshaw`.

    Returns:
        A :class:`ResultatTrainee`.
    """
    if amplification <= 0.0:
        raise ValueError(f"le facteur d'amplification doit être > 0 (reçu {amplification})")

    h_plus = couche_limite.h_plus(asperite.hauteur)
    immersion = couche_limite.immersion(asperite.hauteur)

    ratio = marches.ratio_asperite(asperite.type_asperite, h_plus, etat.mach, asperite.t_sur_h)
    forme = asperite.facteur_forme(etat.mach)

    cde = ratio * couche_limite.cf * forme * amplification
    trainee = cde * etat.pression_dynamique * asperite.aire_frontale

    delta_cx = None
    if surface_reference is not None:
        if surface_reference <= 0.0:
            raise ValueError(
                f"la surface de référence doit être > 0 m² (reçue {surface_reference})"
            )
        delta_cx = trainee / (etat.pression_dynamique * surface_reference)

    avertissements = marches.verifier_domaine(asperite.type_asperite, h_plus, etat.mach, immersion)

    return ResultatTrainee(
        h_plus=h_plus,
        immersion=immersion,
        cde_sur_cfe=ratio,
        facteur_forme=forme,
        cde=cde,
        cisaillement_paroi=couche_limite.cisaillement_paroi,
        trainee=trainee,
        delta_cx=delta_cx,
        surface_reference=surface_reference,
        avertissements=avertissements,
    )


def facteur_amplification_nash_bradshaw(
    ue_locale_sur_v0: float,
    ue_bord_fuite_sur_v0: float,
    theta_locale_sur_theta_bord_fuite: float,
) -> float:
    """Nash–Bradshaw drag magnification factor m_d — equation 5(5).

    ``m_d = (u_eo/V₀)^4.2 · (V₀/u_eT) · (θ_o/θ_T)^(1/5)``

    An excrescence in a pressure gradient does not simply scale with the local
    dynamic head: what it adds to the momentum thickness is carried to the
    trailing edge and amplified on the way (§5.1). ``m_d`` is the ratio of the
    real drag increment to the flat-plate one, so the flat-plate case
    (u_eo = u_eT = V₀, θ_o = θ_T) gives exactly 1.

    The derivation assumes incompressible flow, a 1/7th-power turbulent
    profile and a small perturbation (Δθ ≪ θ). Cook's compressible version
    (Ref. 5.4) underestimated measured increments by about 10 % in subcritical
    flow.

    Args:
        ue_locale_sur_v0: u_eo/V₀, edge velocity at the excrescence over the
            undisturbed free-stream velocity.
        ue_bord_fuite_sur_v0: u_eT/V₀, the same at the trailing edge.
        theta_locale_sur_theta_bord_fuite: θ_o/θ_T, momentum thicknesses.

    Returns:
        m_d [-].
    """
    for nom, valeur in (
        ("u_eo/V₀", ue_locale_sur_v0),
        ("u_eT/V₀", ue_bord_fuite_sur_v0),
        ("θ_o/θ_T", theta_locale_sur_theta_bord_fuite),
    ):
        if valeur <= 0.0:
            raise ValueError(f"{nom} doit être > 0 (reçu {valeur})")
    return (
        float(ue_locale_sur_v0**4.2)
        / ue_bord_fuite_sur_v0
        * float(theta_locale_sur_theta_bord_fuite**0.2)
    )
