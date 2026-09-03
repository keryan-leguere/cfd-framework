"""cfd-dispersion — lois de dispersion, tirage, validation, polaires dispersées.

Bâti sur `OpenTURNS <https://openturns.github.io/>`_ : les six familles de lois
sont des distributions OpenTURNS, les plans d'échantillonnage et le test
d'adéquation viennent de là aussi.

Prise en main::

    from cfd_dispersion import charger_lois, tirer, valider_lot

    lois = charger_lois(DICT_DISP_LAWS)     # {coeff: {Biais_*, FE_*}}
    tirage = tirer(lois, graine=42)         # {coeff: {"Biais": …, "FE": …}}
    coeffs = tirage.appliquer({"Cm_alpha": -2.5})

Attention à la convention ``ET`` : c'est une **demi-étendue**, pas un
écart-type. Pour les familles gaussiennes, ``σ = ET/2``. Voir
:mod:`cfd_dispersion.core.loi`.
"""

from __future__ import annotations

__version__ = "1.0.0"

# --- Les lois ----------------------------------------------------------------
from .core.loi import (
    LIBELLES_TYPE,
    TYPES_VALIDES,
    LoiDispersion,
    libelle_type,
)
from .core.lois import (
    CLES_ATTENDUES,
    COMPOSANTES,
    JeuDeLois,
    LoiCoefficient,
    charger_lois,
    charger_lois_yaml,
)

# --- La reconstruction -------------------------------------------------------
from .core.convention import (
    CONVENTION_PAR_DEFAUT,
    CONVENTIONS,
    Convention,
    convention,
)

# --- Le tirage ---------------------------------------------------------------
from .core.alea import graine_temporaire
from .core.tirage import (
    Tirage,
    tirer,
    tirer_lot,
)

# --- La propagation le long d'un balayage ------------------------------------
from .core.bande import (
    INTERVALLES,
    BandeDispersion,
    bande_depuis_loi,
    bande_depuis_points,
)

# --- La validation -----------------------------------------------------------
from .core.validation import (
    Verdict,
    alpha_corrige,
    valider,
    valider_lot,
)

# --- Les figures -------------------------------------------------------------
# `enregistrer` écrit une figure par cfd_plot.save_figure : c'est ce qui donne
# au fichier le DPI, les marges et le fond du profil de style.
from .figures._base import enregistrer, nouvelle_figure, style, tracer_ligne
from .figures.monte_carlo import (
    figure_comparaison,
    figures_par_pdv,
)
from .figures.polaire import (
    courbes_par_tirage,
    superposer_dispersion,
)
from .figures.synthese import (
    figure_synthese,
    pdv_rejetes,
    synthese,
    table_rich,
    tableau_par_pdv,
)
from .figures.tirage import (
    figure_tirage,
    figure_tirage_matrice,
    tracer_loi,
)

__all__ = [
    "__version__",
    # Les lois
    "LoiDispersion",
    "LoiCoefficient",
    "JeuDeLois",
    "LIBELLES_TYPE",
    "TYPES_VALIDES",
    "CLES_ATTENDUES",
    "COMPOSANTES",
    "libelle_type",
    "charger_lois",
    "charger_lois_yaml",
    # La reconstruction
    "Convention",
    "CONVENTIONS",
    "CONVENTION_PAR_DEFAUT",
    "convention",
    # Le tirage
    "Tirage",
    "tirer",
    "tirer_lot",
    "graine_temporaire",
    # La propagation
    "BandeDispersion",
    "INTERVALLES",
    "bande_depuis_loi",
    "bande_depuis_points",
    # La validation
    "Verdict",
    "valider",
    "valider_lot",
    "alpha_corrige",
    # Les figures
    "enregistrer",
    "nouvelle_figure",
    "style",
    "tracer_ligne",
    "tracer_loi",
    "figure_tirage",
    "figure_tirage_matrice",
    "figure_comparaison",
    "figures_par_pdv",
    "synthese",
    "tableau_par_pdv",
    "pdv_rejetes",
    "figure_synthese",
    "table_rich",
    "superposer_dispersion",
    "courbes_par_tirage",
]
