"""Digitised data of AGARD-AG-264, *Aircraft Excrescence Drag* (1981).

Everything the correlations need that the AGARDograph publishes **as a figure
rather than as a number** lives here, in one module, each table carrying the
figure it came from. Two kinds of entries must not be confused:

``PUBLIÉ``
    Coefficients printed in the text of the report. :data:`ARETE_CARREE` and
    :data:`ARETE_RECTANGULAIRE_2H` are transcriptions of the tables under
    equation 4(37); they are exact.

``NUMÉRISÉ``
    Everything else was read off a scanned figure. The scans are 1981
    microfiche reproductions: the curves are 2–3 px wide on a dotted grid, and
    the AGARDograph itself describes the underlying measurements as scattered
    (§4.3.1.2.1 on rearward steps: "the amount of scatter and/or uncertainty is
    significantly greater than for forward-facing steps"). The uncertainty
    attached to each table below is the digitisation alone — the experimental
    scatter sits on top of it.

The straight-line fits are all in the form the report uses for ridges,

    CDe/Cfe = A·log₁₀(h⁺) + B                                      — eq. 4(37)

which is also the shape of the step lines of Figures 4.23 and 4.28, so steps
and ridges are stored the same way. ``A`` is the slope per decade of h⁺ and
``B`` the value at h⁺ = 1 (well outside the measured range: it is an intercept,
not a physical value).

Sanity checks that fall out of these numbers and are asserted by the test
suite, because they are statements the report makes in prose:

* superposing a forward and a rearward step gives about 50 % less drag than a
  square ridge of the same height at low Mach (§4.3.2.1);
* that deficit shrinks with Mach number and has vanished by M = 2.8.
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = [
    "ARETE_CARREE",
    "ARETE_RECTANGULAIRE_2H",
    "ARRONDI_MONTANTE",
    "CHANFREIN_DESCENDANTE",
    "CHANFREIN_MONTANTE",
    "EPAISSEUR_ARETE",
    "H_PLUS_MAX",
    "H_PLUS_MIN",
    "H_PLUS_MIN_MONTANTE_SUBSONIQUE",
    "MACH_SUPERSONIQUE_MONTANTE",
    "MARCHE_DESCENDANTE",
    "MARCHE_MONTANTE",
    "PC1_MARCHE_MONTANTE",
    "PC2_MARCHE_DESCENDANTE",
    "PC3_ARETE",
    "RAPPORT_ARRONDI_DESCENDANTE",
]

#: A table of straight lines ``CDe/Cfe = A·log₁₀(h⁺) + B``, keyed by Mach number.
DroitesLogH = dict[float, tuple[float, float]]

#: A tabulated curve, as two parallel ascending sequences (abscissa, ordinate).
Courbe = tuple[Sequence[float], Sequence[float]]


# --------------------------------------------------------------------------
# Domaine de validité commun
# --------------------------------------------------------------------------

#: Borne basse exploitable de h⁺.
#:
#: Les axes des Figures 4.23, 4.28 et 4.34 commencent à h⁺ = 10, mais les
#: ajustements droits ne survivent pas jusque-là : la droite de l'arête carrée
#: à M = 0,2 (A = 150, B = −190, valeurs **publiées**) s'annule à h⁺ = 18,5, et
#: celle de la marche montante à M = 0,2 à h⁺ = 20,7. En dessous, la forme
#: A·log₁₀(h⁺) + B prédit une traînée nulle ou négative : elle est hors de son
#: domaine, et les courbes des figures ne sont d'ailleurs guère tracées plus
#: bas. 25 est la borne au-dessus de laquelle toutes les droites du module
#: restent positives.
H_PLUS_MIN = 25.0

#: Borne haute de h⁺ couverte par les essais RAE/ARA.
H_PLUS_MAX = 2000.0

#: Borne basse propre aux droites **subsoniques** de la marche montante.
#:
#: Sur la Figure 4.23, les deux droites en tiretés (M = 0,2 et 0,8) ne sont
#: tracées qu'à partir de h⁺ ≈ 55 — il n'y a pas de point de mesure en dessous
#: — alors que la droite supersonique part de h⁺ = 10. Comme les droites de la
#: marche montante sont nettement plus pentues que celles de la marche
#: descendante, les prolonger vers le bas les fait passer *sous* la marche
#: descendante aux environs de h⁺ = 42 à M = 0,2, ce qui n'est pas une
#: observation mais un artefact de l'extrapolation.
H_PLUS_MIN_MONTANTE_SUBSONIQUE = 55.0

#: Immersion maximale testée, h/δ. Au-delà, l'aspérité cesse de ne « voir » que
#: la région interne de la couche limite et la corrélation en h⁺ perd son sens
#: (§4.3.1.1.1 : les essais RAE portaient sur h < 0,03 δ).
H_SUR_DELTA_MAX = 0.03


# --------------------------------------------------------------------------
# 4.3.1.1 — Marche montante (forward-facing step)
# --------------------------------------------------------------------------

#: Figure 4.23, droites RAE. NUMÉRISÉ, ±3 sur CDe/Cfe.
#:
#: La figure ne porte que deux droites subsoniques (M = 0,2 et 0,8) et une
#: unique droite supersonique valable pour tout M ≥ 1,4 — §4.3.1.1.1 : « In the
#: case of the supersonic results (M ≥ 1.4) […] all the data seem to be along a
#: single line ». La traînée de la marche montante croît donc avec le Mach
#: jusqu'à 1,4 puis reste essentiellement constante.
MARCHE_MONTANTE: DroitesLogH = {
    0.2: (60.0, -79.0),
    0.8: (61.5, -74.0),
    1.4: (76.8, -59.5),
}

#: Mach au-delà duquel :data:`MARCHE_MONTANTE` n'évolue plus (droite unique).
MACH_SUPERSONIQUE_MONTANTE = 1.4

#: Figure 4.25 — facteur d'interpolation transsonique PC₁, eq. 4(27).
#: NUMÉRISÉ depuis les symboles de mesure (donc ±0,01) ; PC₁(0,8) = 0 et
#: PC₁(1,4) = 1 par construction.
PC1_MARCHE_MONTANTE: Courbe = (
    (0.800, 0.850, 0.900, 0.950, 1.000, 1.050, 1.100, 1.150, 1.200, 1.300, 1.400),
    (0.000, 0.022, 0.052, 0.094, 0.193, 0.399, 0.567, 0.615, 0.720, 0.871, 1.000),
)

#: Figure 4.26(a) — réduction relative E(r/h) due à l'arrondi de l'arête
#: amont, eq. 4(28) : CDe/Cfe = (CDe/Cfe)_{r=0}·(1 − E). NUMÉRISÉ, ±0,03.
#: Clé : Mach ; valeur : (r/h, E).
ARRONDI_MONTANTE: dict[float, Courbe] = {
    0.2: (
        (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8),
        (0.0, 0.130, 0.240, 0.343, 0.461, 0.595, 0.656, 0.724, 0.760),
    ),
    0.8: (
        (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8),
        (0.0, 0.185, 0.345, 0.490, 0.611, 0.703, 0.759, 0.794, 0.805),
    ),
    1.4: (
        (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8),
        (0.0, 0.107, 0.187, 0.248, 0.282, 0.303, 0.306, 0.313, 0.315),
    ),
    2.0: (
        (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8),
        (0.0, 0.005, 0.012, 0.032, 0.055, 0.081, 0.106, 0.127, 0.138),
    ),
}

#: Figure 4.26(b) — réduction relative E(θ) due au chanfrein de l'arête amont,
#: eq. 4(29) : CDe/Cfe = (CDe/Cfe)_{θ=90°}·(1 − E). NUMÉRISÉ, ±0,04.
#: θ = 90° est la marche vive (E = 0), θ = 0 le carénage complet (E = 1).
CHANFREIN_MONTANTE: dict[float, Courbe] = {
    0.2: (
        (0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0),
        (1.0, 0.905, 0.825, 0.745, 0.660, 0.570, 0.480, 0.390, 0.255, 0.0),
    ),
    0.8: (
        (0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0),
        (1.0, 0.890, 0.796, 0.712, 0.581, 0.456, 0.327, 0.229, 0.135, 0.0),
    ),
    1.4: (
        (0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0),
        (1.0, 0.600, 0.425, 0.305, 0.215, 0.152, 0.105, 0.068, 0.035, 0.0),
    ),
    2.0: (
        (0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0),
        (1.0, 0.450, 0.265, 0.178, 0.128, 0.090, 0.064, 0.044, 0.026, 0.0),
    ),
}


# --------------------------------------------------------------------------
# 4.3.1.2 — Marche descendante (rearward-facing step)
# --------------------------------------------------------------------------

#: Figure 4.28, droites RAE. NUMÉRISÉ, ±4 sur CDe/Cfe.
#:
#: Contrairement à la marche montante, la traînée passe par un maximum : elle
#: croît jusqu'à M ≈ 1,4 puis redescend (§4.3.1.2.1). Les droites M ≥ 1,7 sont
#: les plus incertaines de tout le jeu — elles sont serrées et se croisent au
#: voisinage de M = 2.
MARCHE_DESCENDANTE: DroitesLogH = {
    0.2: (16.0, -7.5),
    0.8: (20.0, -13.0),
    1.4: (49.0, -21.2),
    1.7: (52.0, -35.2),
    2.0: (44.0, -19.2),
    2.2: (33.0, 4.8),
    2.8: (36.0, -15.8),
}

#: Figure 4.30 — facteur d'interpolation transsonique PC₂, eq. 4(32).
#: NUMÉRISÉ depuis les symboles, ±0,02.
#:
#: PC₂ dépasse 1 : la traînée de la marche descendante culmine vers M ≈ 1,15
#: (Figure 4.29) au-dessus de sa valeur à M = 1,4. Ce n'est pas une
#: extrapolation, c'est la mesure.
PC2_MARCHE_DESCENDANTE: Courbe = (
    (0.800, 0.900, 0.950, 1.000, 1.050, 1.100, 1.150, 1.200, 1.300, 1.400),
    (0.000, 0.065, 0.110, 0.400, 1.030, 1.210, 1.275, 1.260, 1.140, 1.000),
)

#: Eq. 4(34) — effet de l'arrondi de l'arête aval : CDe/Cfe = (1 + 1,43·r/h)·
#: (CDe/Cfe)_{r=0}. PUBLIÉ. Noter le signe : arrondir une marche descendante
#: **augmente** sa traînée (Figure 4.32), au contraire d'une marche montante.
#: La relation est unique, indépendante du Mach (§4.3.1.2.2).
RAPPORT_ARRONDI_DESCENDANTE = 1.43

#: Figure 4.33 — réduction relative G(θ) due au chanfrein de l'arête aval,
#: eq. 4(33) : CDe/Cfe = (CDe/Cfe)_{θ=90°}·(1 − G).
#:
#: NUMÉRISÉ, ±0,05 — **c'est la table la moins sûre du module**. La figure
#: superpose sept courbes serrées, leurs repères et leurs lignes de rappel dans
#: un cadre de 4 cm. Le texte (§4.3.1.2.2) est ici plus net que le tracé et les
#: tables ci-dessous le respectent : pas d'effet notable jusqu'à θ = 45°, une
#: légère augmentation de traînée (G < 0) entre 12° et 45° au transsonique et
#: au supersonique, une chute franche en dessous de 12° à tous les Mach.
CHANFREIN_DESCENDANTE: dict[float, Courbe] = {
    0.2: (
        (0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 90.0),
        (1.0, 0.780, 0.600, 0.460, 0.355, 0.257, 0.164, 0.082, 0.010, 0.0, 0.0),
    ),
    0.8: (
        (0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 90.0),
        (1.0, 0.920, 0.860, 0.790, 0.690, 0.555, 0.415, 0.275, 0.135, 0.0, 0.0),
    ),
    1.2: (
        (0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 90.0),
        (1.0, 0.450, 0.000, -0.190, -0.220, -0.210, -0.180, -0.130, -0.070, 0.0, 0.0),
    ),
    1.4: (
        (0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 90.0),
        (1.0, 0.520, 0.100, -0.130, -0.170, -0.165, -0.140, -0.100, -0.050, 0.0, 0.0),
    ),
    1.7: (
        (0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 90.0),
        (1.0, 0.580, 0.220, -0.030, -0.077, -0.075, -0.060, -0.040, -0.020, 0.0, 0.0),
    ),
    2.0: (
        (0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 90.0),
        (1.0, 0.600, 0.250, 0.090, 0.051, 0.046, 0.046, 0.046, 0.046, 0.020, 0.0),
    ),
}


# --------------------------------------------------------------------------
# 4.3.2 — Arête (ridge : marche montante + descendante combinées)
# --------------------------------------------------------------------------

#: Eq. 4(37) — arête carrée (t = h), coefficients A et B. **PUBLIÉ** : table
#: imprimée page 91 du rapport, pas une lecture de la Figure 4.34.
ARETE_CARREE: DroitesLogH = {
    0.2: (150.0, -190.0),
    0.8: (150.0, -160.0),
    1.4: (160.0, -125.0),
    2.2: (110.0, -42.0),
    2.8: (100.0, -44.0),
}

#: Eq. 4(37) — arête rectangulaire d'épaisseur t = 2h. **PUBLIÉ**, même page.
#:
#: Cette table croise :data:`ARETE_CARREE` vers h⁺ ≈ 1000 — plus traînante en
#: dessous, moins au-dessus — ce qui est exactement ce que décrit §4.3.2.1.
#: Le produit :data:`ARETE_CARREE` × T(2) de l'eq. 4(39), lui, reste 21 % sous
#: l'arête carrée à tout h⁺ et ne croise jamais rien : les deux routes
#: diffèrent de 80 % à h⁺ = 100 et de 27 % à h⁺ = 1000.
#:
#: Ce n'est pas une faute de transcription mais une contradiction du rapport
#: lui-même : le facteur T vient des essais Wieghardt, tous à h/δ > 3 %
#: (Figure 4.39), alors que le croisement carrée/rectangulaire décrit en
#: §4.3.2.1 se produit entre h/δ = 0,02 et 0,03. Voir
#: :func:`cfd_aq.core.marches.ratio_arete`.
ARETE_RECTANGULAIRE_2H: DroitesLogH = {
    0.2: (105.0, -55.0),
    0.8: (115.0, -60.0),
    1.4: (100.0, 8.0),
    1.7: (100.0, 20.0),
}

#: Figure 4.38 — facteur d'interpolation transsonique PC₃, eq. 4(38).
#: NUMÉRISÉ en continu le long du tracé, ±0,02.
#:
#: PC₃ culmine à ≈ 1,59 vers M = 1,03 : la traînée d'une arête passe par un pic
#: transsonique 50 % au-dessus du niveau subsonique avant de redescendre
#: (§4.3.2.1). C'est le comportement le plus marqué des trois facteurs PC.
PC3_ARETE: Courbe = (
    (
        0.800,
        0.825,
        0.850,
        0.875,
        0.900,
        0.925,
        0.950,
        0.975,
        1.000,
        1.025,
        1.050,
        1.075,
        1.100,
        1.150,
        1.200,
        1.250,
        1.300,
        1.350,
        1.400,
    ),
    (
        0.000,
        0.102,
        0.197,
        0.308,
        0.456,
        0.642,
        0.927,
        1.303,
        1.520,
        1.580,
        1.572,
        1.500,
        1.428,
        1.330,
        1.236,
        1.152,
        1.095,
        1.050,
        1.000,
    ),
)

#: Figure 4.40 — facteur d'épaisseur T(t/h), eq. 4(39) :
#: (CDe/Cfe)_{t/h} = T·(CDe/Cfe)_{t/h=1}. NUMÉRISÉ en continu, ±0,02.
#:
#: T(1) = 1 par définition ; le maximum (≈ 1,07) se trouve vers t/h ≈ 0,25,
#: c'est-à-dire qu'une arête mince traîne un peu plus qu'une arête carrée de
#: même hauteur, et T s'effondre ensuite vers un plateau de 0,58 au-delà de
#: t/h ≈ 4 — l'écoulement recolle entre les deux arêtes et l'aspérité se
#: comporte comme deux marches indépendantes.
EPAISSEUR_ARETE: Courbe = (
    (
        0.000,
        0.125,
        0.250,
        0.375,
        0.500,
        0.625,
        0.750,
        0.875,
        1.000,
        1.125,
        1.250,
        1.375,
        1.500,
        1.625,
        1.750,
        1.875,
        2.000,
        2.125,
        2.250,
        2.375,
        2.500,
        2.625,
        2.750,
        2.875,
        3.000,
        3.250,
        3.500,
        3.750,
        4.000,
        4.500,
        5.000,
    ),
    (
        1.065,
        1.064,
        1.066,
        1.063,
        1.058,
        1.048,
        1.036,
        1.022,
        1.000,
        0.982,
        0.961,
        0.937,
        0.914,
        0.886,
        0.855,
        0.820,
        0.789,
        0.758,
        0.734,
        0.709,
        0.688,
        0.673,
        0.654,
        0.639,
        0.627,
        0.613,
        0.587,
        0.585,
        0.577,
        0.575,
        0.577,
    ),
)
