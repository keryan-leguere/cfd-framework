"""Greffer la dispersion sur les figures de ``cfd_plot.batch_plot``.

``batch_plot`` produit une figure par (polaire × point de vol × grandeur). Son
seul point de greffe est ``on_before_save(fig, ax, context)``, appelé une fois
les courbes, les libellés, la légende et le titre posés, et juste avant
l'enregistrement. Tout ce qu'on y dessine se retrouve dans le SVG **et** dans
la page du rapport PDF.

    from cfd_dispersion.batch import hook_dispersion

    batch_plot(
        ...,
        on_before_save=hook_dispersion(lois, serie="KW"),
    )

La courbe nominale n'est pas à redonner : elle est déjà sur les axes. Le hook
va chercher la série nommée, en lit l'abscisse et l'ordonnée, et disperse
celles-là. Une erreur de recopie entre les données tracées et les données
dispersées devient ainsi impossible.

Pourquoi une classe et non une fermeture
----------------------------------------
``batch_plot`` sérialise le hook pour l'envoyer à ses processus de travail, et
**retombe silencieusement sur ``n_jobs=1``** — avec un simple ``UserWarning`` —
quand il n'y parvient pas. Une fermeture capturant un ``DataFrame`` coûterait
donc tous les cœurs de la machine sans rien dire de plus qu'un avertissement
noyé dans la sortie.

:class:`HookDispersion` est une classe de niveau module dont tous les attributs
sont des données simples, donc sérialisable. Une réserve demeure : une
convention **maison** construite sur une ``lambda`` ne l'est pas. Passer son
nom (une chaîne) plutôt que l'objet, ou définir sa relation comme une fonction
de niveau module.

Et cfd-plot dans tout ça
------------------------
Il est exigé deux fois : par ``batch_plot`` lui-même, et par le tracé de la
superposition — toutes les figures de cfd-dispersion passent par cfd-plot, qui
définit le format du framework.

:func:`hook_dispersion` le vérifie donc à la construction du hook, et lève un
``ImportError`` nommant la commande d'installation, plutôt que de laisser
l'échec survenir au milieu d'un lot de deux cents figures.

Seul le **calcul** — lois, tirage, validation, synthèse chiffrée — tourne sans
cfd-plot.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from .core.convention import ConventionArg
from .core.lois import JeuDeLois
from .figures.polaire import superposer_dispersion

__all__ = ["HookDispersion", "cle_par_defaut", "hook_dispersion"]


def _exiger_cfd_plot() -> Any:
    """Importe cfd_plot, ou explique comment l'installer."""
    try:
        import cfd_plot
    except ImportError as erreur:  # pragma: no cover - dépend de l'environnement
        raise ImportError(
            "cfd_dispersion.batch a besoin de cfd-plot, qui n'est pas installé. "
            "cfd-plot est un paquet frère de ce dépôt, pas une publication PyPI :\n"
            "    pip install -e tools/cfd-plot\n"
            "Le calcul de cfd_dispersion (lois, tirage, validation) tourne sans lui ; "
            "les figures, non."
        ) from erreur
    return cfd_plot


def cle_par_defaut(context: Any) -> tuple[Any, ...]:
    """La clé identifiant une figure : ``(grandeur, variable de balayage)``.

    C'est le découpage naturel d'une étude : une loi de dispersion porte sur un
    coefficient, indépendamment du point de vol. Pour une dispersion qui varie
    d'un point de vol à l'autre, fournir des *tirages* indexés plus finement et
    passer sa propre fonction de clé — de niveau module, pour rester
    sérialisable.
    """
    return (context.y_key, context.sweep_key)


class HookDispersion:
    """Rappel compatible ``on_before_save`` qui superpose la dispersion.

    Parameters
    ----------
    lois:
        Les lois, indexées par coefficient. Le nom du coefficient est confronté
        à ``context.y_key``.
    serie:
        Le libellé de la courbe à disperser. Sa couleur est reprise, et ses
        données servent de nominal.
    coefficients:
        Correspondance ``{y_key: coefficient}`` quand la grandeur tracée ne
        porte pas le même nom que la loi. Par défaut, les noms coïncident.
    tirages:
        ``{clé: tableau (n_tirages, npts)}`` — les courbes réellement obtenues,
        à superposer à la bande théorique. La clé est celle que rend *cle*.
    cle:
        Fonction ``context -> clé`` pour retrouver les tirages. Doit être de
        niveau module pour rester sérialisable.
    options:
        Tout le reste est transmis à
        :func:`cfd_dispersion.figures.polaire.superposer_dispersion`.

    Examples
    --------
    >>> hook = hook_dispersion(lois, serie="KW", n=5000, graine=1)   # doctest: +SKIP
    >>> batch_plot(..., on_before_save=hook)                          # doctest: +SKIP
    """

    def __init__(
        self,
        lois: JeuDeLois | Mapping[str, Any],
        *,
        serie: str,
        coefficients: Mapping[str, str] | None = None,
        tirages: Mapping[Any, Any] | None = None,
        cle: Any = cle_par_defaut,
        convention_: ConventionArg = None,
        panneaux: Sequence[str] | None = None,
        **options: Any,
    ) -> None:
        self.lois = lois
        self.serie = serie
        self.coefficients = dict(coefficients) if coefficients else {}
        self.tirages = {k: np.asarray(v, dtype=float) for k, v in (tirages or {}).items()}
        self.cle = cle
        self.convention_ = convention_
        self.panneaux = tuple(panneaux) if panneaux is not None else None
        self.options = options

    # ------------------------------------------------------------------

    def coefficient_pour(self, y_key: str) -> str | None:
        """Le coefficient correspondant à une grandeur tracée, ou None."""
        nom = self.coefficients.get(y_key, y_key)
        return nom if nom in self.lois else None

    def __call__(self, fig: Any, ax: Any, context: Any) -> None:
        """Superpose la dispersion sur *ax*, si cette figure en relève."""
        nom = self.coefficient_pour(context.y_key)
        if nom is None:
            return

        # En mode comparaison, `batch_plot` appelle le hook une fois par
        # panneau ; `panneaux=` permet de n'en décorer que certains.
        if (
            self.panneaux is not None
            and getattr(context, "compare_name", None) is not None
            and context.compare_name not in self.panneaux
        ):
            return

        courbe = _courbe_nommee(ax, self.serie)
        if courbe is None:
            return
        x, nominal = courbe

        superposer_dispersion(
            ax,
            x,
            nominal,
            loi=self.lois[nom],
            tirages=self.tirages.get(self.cle(context)),
            serie=self.serie,
            convention_=self.convention_,
            label=nom,
            **self.options,
        )

    def __repr__(self) -> str:
        return (
            f"HookDispersion(serie={self.serie!r}, "
            f"coefficients={sorted(self.lois)}, tirages={len(self.tirages)})"
        )


def _courbe_nommee(ax: Any, label: str) -> tuple[np.ndarray, np.ndarray] | None:
    """Les données de la courbe portant *label*, ou None si elle est absente.

    Absente n'est pas une erreur : un ``include_curve`` peut légitimement
    retirer une série de certaines figures, et la dispersion n'a alors rien à
    décorer sur celles-là.
    """
    for ligne in ax.get_lines():
        if ligne.get_label() == label:
            return (
                np.asarray(ligne.get_xdata(), dtype=float),
                np.asarray(ligne.get_ydata(), dtype=float),
            )
    return None


def hook_dispersion(
    lois: JeuDeLois | Mapping[str, Any],
    *,
    serie: str,
    **options: Any,
) -> HookDispersion:
    """Construit un :class:`HookDispersion` prêt pour ``on_before_save``.

    Vérifie au passage que ``cfd_plot`` est installé, pour que l'échec survienne
    à la construction du hook plutôt qu'au milieu d'un lot de deux cents
    figures.
    """
    _exiger_cfd_plot()
    return HookDispersion(lois, serie=serie, **options)
