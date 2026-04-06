"""
dispersion.core — Dispersion models for Monte Carlo sensitivity analyses.

Provides two dataclasses:

    DispersionSpec       — one dispersion component (bias or scale factor)
    QuantityDispersion   — a full dispersed quantity with bias + scale spec

Usage example::

    from dispersion import QuantityDispersion, DispersionSpec

    Cm_alpha = QuantityDispersion(
        name="Cm_alpha",
        nominal=-2.5,
        bias=DispersionSpec(disp_type=5, moy=0.0, var=0.015),
        scale=DispersionSpec(disp_type=6, moy=0.0, var=0.10),
    )

    samples = Cm_alpha.sample(n=10000)

Reproducibility
---------------
Pass an ``rng=np.random.default_rng(seed)`` to all draw/sample calls for the
new-style Generator API.  Alternatively, call ``np.random.seed(...)`` before
draw/sample calls with the default ``rng=None`` to use the legacy global RNG.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import truncnorm

# ---------------------------------------------------------------------------
# Type labels
# ---------------------------------------------------------------------------

DISP_TYPE_LABELS: dict[int, str] = {
    1: "Null",
    2: "Constant",
    3: "Uniform",
    4: "Gaussian",
    5: "Gaussian \u00b13\u03c3",
    6: "Gaussian \u00b12\u03c3",
}

VALID_TYPES: frozenset[int] = frozenset(DISP_TYPE_LABELS)


def dispersion_type_label(disp_type: int) -> str:
    """Return the human-readable label for a dispersion type integer."""
    if disp_type not in VALID_TYPES:
        raise ValueError(f"Unknown disp_type={disp_type!r}; must be one of {sorted(VALID_TYPES)}")
    return DISP_TYPE_LABELS[disp_type]


def sigma(var: float) -> float:
    """Standard deviation for Gaussian dispersion types: sigma = 0.5 * var."""
    return 0.5 * var


# ---------------------------------------------------------------------------
# DispersionSpec
# ---------------------------------------------------------------------------

@dataclass
class DispersionSpec:
    """One dispersion component: bias or scale factor.

    Parameters
    ----------
    disp_type:
        Integer 1–6 selecting the distribution family.
    moy:
        Mean / centre of the distribution.
    var:
        Half-range.  For Gaussian types, ``sigma = 0.5 * var``.
    """

    disp_type: int
    moy: float
    var: float

    def __post_init__(self) -> None:
        if self.disp_type not in VALID_TYPES:
            raise ValueError(
                f"Unknown disp_type={self.disp_type!r}; must be one of {sorted(VALID_TYPES)}"
            )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def draw(self, n: int, rng: np.random.Generator | None = None) -> np.ndarray:
        """Return *n* independent samples from this dispersion component.

        Parameters
        ----------
        n:
            Number of samples.
        rng:
            Optional :class:`numpy.random.Generator` for the new-style API.
            When *None*, the legacy ``np.random`` module functions are used so
            that ``np.random.seed(...)`` controls reproducibility.

        Returns
        -------
        np.ndarray, shape (n,)
        """
        dt = self.disp_type
        moy = float(self.moy)
        var = float(self.var)

        if dt == 1:
            return np.zeros(n, dtype=float)

        if dt == 2:
            return np.full(n, moy, dtype=float)

        if dt == 3:
            if var == 0.0:
                return np.full(n, moy, dtype=float)
            if rng is not None:
                return rng.uniform(moy - var, moy + var, size=n)
            return np.random.uniform(moy - var, moy + var, size=n)

        if dt == 4:
            s = sigma(var)
            if s == 0.0:
                return np.full(n, moy, dtype=float)
            if rng is not None:
                return rng.normal(moy, s, size=n)
            return np.random.normal(moy, s, size=n)

        if dt == 5:
            return self._draw_truncnorm(n, a=-3.0, b=3.0, rng=rng)

        # dt == 6
        return self._draw_truncnorm(n, a=-2.0, b=2.0, rng=rng)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _draw_truncnorm(
        self, n: int, a: float, b: float, rng: np.random.Generator | None
    ) -> np.ndarray:
        moy = float(self.moy)
        s = sigma(self.var)
        if s == 0.0:
            return np.full(n, moy, dtype=float)
        return truncnorm.rvs(a, b, loc=moy, scale=s, size=n, random_state=rng)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def label(self) -> str:
        """Human-readable type label."""
        return DISP_TYPE_LABELS[self.disp_type]

    @property
    def sigma(self) -> float:
        """Standard deviation for Gaussian types (0.5 * var)."""
        return sigma(self.var)


# ---------------------------------------------------------------------------
# QuantityDispersion
# ---------------------------------------------------------------------------

@dataclass
class QuantityDispersion:
    """A nominal quantity with independent bias and scale-factor dispersions.

    The dispersed value is:

        C_drawn[i] = (1 + scale_draw[i]) * nominal + bias_draw[i]

    Parameters
    ----------
    name:
        Human-readable label shown in plot titles.
    nominal:
        Nominal (reference) value of the quantity.
    bias:
        Additive dispersion component.
    scale:
        Multiplicative dispersion component (applied as ``1 + s``).
    """

    name: str
    nominal: float
    bias: DispersionSpec
    scale: DispersionSpec

    def sample(self, n: int, rng: np.random.Generator | None = None) -> np.ndarray:
        """Return *n* dispersed realisations of this quantity.

        Parameters
        ----------
        n:
            Number of samples.
        rng:
            Optional :class:`numpy.random.Generator`.  When *None*, uses the
            legacy ``np.random`` global state (respects ``np.random.seed``).

        Returns
        -------
        np.ndarray, shape (n,)
        """
        b = self.bias.draw(n, rng=rng)
        s = self.scale.draw(n, rng=rng)
        return (1.0 + s) * float(self.nominal) + b
