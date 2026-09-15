"""Comparer point à point une référence et ce qu'un modèle a rendu.

NumPy pur, sans pandas : un écart est une affaire de tableaux, et le confiner
ici est ce qui garde ``core`` testable au cas limite près — référence nulle,
``atol`` seul, infini des deux côtés, ``NaN``.

Le critère de conformité est celui de ``numpy.isclose``, à deux différences
près, toutes deux voulues :

* **l'égalité stricte l'emporte d'abord**, pour que ``+inf`` soit conforme à
  ``+inf`` — la formule usuelle y produit ``|inf − inf| = NaN`` et rejetterait
  deux valeurs pourtant identiques ;
* **``NaN`` n'est jamais conforme**, même face à ``NaN``. Une table qui porte
  un ``NaN`` est cassée, et le contrôle existe pour le dire.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

__all__ = ["Ecart", "comparer"]

#: Tolérance relative par défaut. Assez lâche pour absorber un aller-retour en
#: simple précision côté Fortran, assez serrée pour qu'aucune erreur de lecture
#: de table ne passe : une table relue juste l'est au bit près.
RTOL_DEFAUT = 1e-9

#: Tolérance absolue par défaut, qui gouverne au voisinage de zéro.
ATOL_DEFAUT = 1e-12

Tableau = npt.NDArray[np.float64]


@dataclass(frozen=True)
class Ecart:
    """Le résultat d'une comparaison point à point.

    Tous les tableaux ont la même longueur et le même ordre que les entrées :
    l'indice *i* désigne le même point partout, y compris dans le cadre de
    données d'origine. C'est ce qui permet aux détecteurs de motifs de
    remonter d'un point fautif à ses coordonnées.
    """

    #: La valeur tabulée, qui fait foi.
    reference: Tableau
    #: Ce que le modèle a rendu.
    obtenu: Tableau
    #: ``obtenu − reference``, signé.
    difference: Tableau
    #: ``|difference|``.
    absolu: Tableau
    #: ``|difference| / |reference|`` ; ``0`` si les deux sont nuls, ``inf`` si
    #: la référence seule est nulle. Jamais une division silencieuse par zéro.
    relatif: Tableau
    #: Point par point, la conformité.
    ok: npt.NDArray[np.bool_]
    rtol: float
    atol: float

    # -- Ce que le rapport lit ------------------------------------------------

    @property
    def n(self) -> int:
        """Nombre de points comparés."""
        return int(self.reference.size)

    @property
    def indices_fautifs(self) -> npt.NDArray[np.intp]:
        """Indices des points hors tolérance, dans l'ordre d'origine."""
        return np.flatnonzero(~self.ok)

    @property
    def n_fautifs(self) -> int:
        """Nombre de points hors tolérance."""
        return int((~self.ok).sum())

    @property
    def conforme(self) -> bool:
        """Vrai si aucun point n'est hors tolérance."""
        return self.n_fautifs == 0

    @property
    def absolu_max(self) -> float:
        """Le plus grand écart absolu, ``NaN`` inclus s'il y en a."""
        return _max_avec_nan(self.absolu)

    @property
    def relatif_max(self) -> float:
        """Le plus grand écart relatif."""
        return _max_avec_nan(self.relatif)

    @property
    def indice_pire(self) -> int | None:
        """Indice du point le plus fautif, ``None`` si tout est conforme.

        Le classement se fait sur l'écart **relatif** quand il est fini, parce
        que c'est lui qui a un sens d'une grandeur à l'autre ; un ``NaN`` ou un
        ``inf`` obtenu passe devant tout le reste, puisque c'est la panne la
        plus grave.
        """
        if self.conforme:
            return None
        rang = np.where(np.isfinite(self.relatif), self.relatif, np.inf)
        rang = np.where(self.ok, -np.inf, rang)
        return int(np.argmax(rang))

    def quantiles(self, niveaux: tuple[float, ...] = (0.5, 0.9, 0.99, 1.0)) -> dict[float, float]:
        """Quantiles de l'écart relatif fini, pour dire *à quel point* ça dérive."""
        fini = self.relatif[np.isfinite(self.relatif)]
        if fini.size == 0:
            return dict.fromkeys(niveaux, float("nan"))
        valeurs = np.quantile(fini, niveaux)
        return {niveau: float(valeur) for niveau, valeur in zip(niveaux, valeurs)}


def comparer(
    reference: npt.ArrayLike,
    obtenu: npt.ArrayLike,
    *,
    rtol: float = RTOL_DEFAUT,
    atol: float = ATOL_DEFAUT,
) -> Ecart:
    """Compare *obtenu* à *reference*, point par point.

    Parameters
    ----------
    reference:
        La valeur tabulée. C'est elle qui fait foi, et c'est sur elle que
        porte la tolérance relative.
    obtenu:
        Ce que le modèle a rendu, même longueur et même ordre.
    rtol, atol:
        Un point est conforme si ``|Δ| <= atol + rtol·|reference|``.

    Raises
    ------
    ValueError
        Si les longueurs diffèrent, ou si une tolérance est négative.
    """
    ref = np.asarray(reference, dtype=np.float64).ravel()
    obt = np.asarray(obtenu, dtype=np.float64).ravel()
    if ref.shape != obt.shape:
        raise ValueError(
            f"référence et obtenu n'ont pas la même longueur : {ref.size} contre {obt.size}"
        )
    if rtol < 0.0 or atol < 0.0:
        raise ValueError(
            f"les tolérances doivent être positives, reçu rtol={rtol!r}, atol={atol!r}"
        )

    # `inf - inf` vaut NaN et avertit : c'est attendu ici, l'égalité stricte
    # ci-dessous sauve ce cas-là. Le reste du calcul est fait sous le même
    # couvert, pour qu'aucun avertissement NumPy ne remonte à l'appelant.
    with np.errstate(invalid="ignore", divide="ignore"):
        difference = obt - ref
        absolu = np.abs(difference)
        relatif = np.where(
            ref == 0.0,
            np.where(absolu == 0.0, 0.0, np.inf),
            absolu / np.abs(ref),
        )
        # L'égalité d'abord : elle seule sauve `inf` face à `inf`.
        proche = absolu <= atol + rtol * np.abs(ref)
    ok = (ref == obt) | proche
    # Un NaN n'est conforme à rien, pas même à lui-même.
    ok &= ~(np.isnan(ref) | np.isnan(obt))

    return Ecart(
        reference=ref,
        obtenu=obt,
        difference=difference,
        absolu=absolu,
        relatif=relatif,
        ok=ok,
        rtol=float(rtol),
        atol=float(atol),
    )


def _max_avec_nan(valeurs: Tableau) -> float:
    """Le maximum, en laissant un ``NaN`` remonter au lieu de le taire."""
    if valeurs.size == 0:
        return float("nan")
    return float(np.max(valeurs))
