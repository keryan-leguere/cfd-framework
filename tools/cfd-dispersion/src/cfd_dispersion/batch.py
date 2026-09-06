"""Greffer la dispersion sur les figures de ``cfd_plot.batch_plot``.

``batch_plot`` produit une figure par (polaire × point de vol × grandeur). Son
seul point de greffe est ``on_before_save(fig, ax, context)``, appelé une fois
les courbes, les libellés, la légende et le titre posés, et juste avant
l'enregistrement. Tout ce qu'on y dessine se retrouve dans le SVG **et** dans
la page du rapport PDF.

    from cfd_dispersion.batch import hook_dispersion_tableau

    batch_plot(
        configuration_dict={"CFD": {"df": df_reference, ...}},   # le nominal
        ...,
        on_before_save=hook_dispersion_tableau(df_disperse),     # les tirages
    )

La courbe nominale n'est pas à redonner : elle est déjà sur les axes. Le hook
va chercher la série nommée, en lit l'abscisse et l'ordonnée, et disperse
celles-là. Une erreur de recopie entre les données tracées et les données
dispersées devient ainsi impossible.

Deux hooks, deux entrées
------------------------
Le tableau et la loi ne disent pas la même chose, et on peut vouloir l'un,
l'autre, ou les deux sur la même figure.

============================== ===============================================
:func:`hook_dispersion_tableau` part du **tableau dispersé** du modèle — une
                               ligne par (tirage × point du balayage), pour
                               tous les points de vol. Il le découpe lui-même,
                               point de vol par point de vol, du même filtre
                               que ``batch_plot`` a employé pour la référence.
                               C'est ce qu'on a sous la main après une étude.
:func:`hook_dispersion`        part des **lois** et de tirages déjà mis en
                               forme ``{clé: (n_tirages, npts)}``. C'est la
                               bande théorique — ce qui était prescrit.
============================== ===============================================

Le second sait aussi tracer les deux : ``lois=`` sur le hook de tableau ajoute
la bande théorique par-dessus le nuage obtenu, et l'intérêt est précisément de
les voir se recouvrir — ou non.

Le découpage par point de vol
-----------------------------
``batch_plot`` produit une figure par point de vol, et filtre sa source à
l'égalité stricte sur les clés de point de vol et les balayages figés
(``df[cle] == valeur``). Le hook de tableau applique **le même filtre, aux
mêmes valeurs**, lues sur le ``context`` : le sous-tableau dispersé correspond
donc exactement à la courbe tracée, sans arrondi ni tolérance à régler.

Un point de vol absent du tableau dispersé lève une erreur dès la première
figure plutôt que de laisser un lot de deux cents figures sortir muet ;
``absent="ignorer"`` est là pour l'étude volontairement partielle.

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
import pandas as pd

from .core.convention import ConventionArg
from .core.lois import JeuDeLois
from .figures.polaire import superposer_depuis_tableau, superposer_dispersion

__all__ = [
    "HookDispersion",
    "HookDispersionTableau",
    "cle_par_defaut",
    "hook_dispersion",
    "hook_dispersion_tableau",
]

#: Ce que fait le hook d'un point de vol absent du tableau dispersé.
ABSENT = ("erreur", "ignorer")


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

        if _panneau_ignore(self.panneaux, context):
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


def _panneau_ignore(panneaux: tuple[str, ...] | None, context: Any) -> bool:
    """Vrai si ce panneau de comparaison n'est pas à décorer.

    En mode comparaison, ``batch_plot`` appelle le hook une fois par panneau ;
    ``panneaux=`` permet de n'en décorer que certains.
    """
    if panneaux is None:
        return False
    nom = getattr(context, "compare_name", None)
    return nom is not None and nom not in panneaux


def _colonne(spec: Any, cle: str) -> str:
    """La colonne du tableau derrière une clé de ``batch_plot``.

    Une entrée de ``y_axis_dict`` / ``sweep_dict`` porte son nom de colonne
    dans ``col_name`` ; la clé du dictionnaire n'est qu'un identifiant. Les
    deux coïncident le plus souvent, et pas toujours.
    """
    if isinstance(spec, Mapping):
        nom = spec.get("col_name")
        if nom:
            return str(nom)
    return cle


def _serie_unique(ax: Any) -> str:
    """Le libellé de la seule courbe des axes, quand il n'y en a qu'une.

    C'est le cas ordinaire d'un ``batch_plot`` à une source, et il évite
    d'avoir à répéter dans le hook un nom déjà écrit dans le
    ``configuration_dict``.
    """
    libelles = [
        str(ligne.get_label())
        for ligne in ax.get_lines()
        if not str(ligne.get_label()).startswith("_")
    ]
    if len(libelles) == 1:
        return libelles[0]
    if not libelles:
        raise ValueError(
            "aucune courbe nommée sur ces axes : il n'y a rien à disperser. "
            "Vérifier que le configuration_dict porte bien la référence."
        )
    raise ValueError(
        f"plusieurs courbes sur ces axes ({libelles}) : préciser laquelle porte le "
        "nominal avec serie=<libellé>."
    )


class HookDispersionTableau:
    """Rappel ``on_before_save`` qui lit la dispersion dans le tableau du modèle.

    C'est la greffe la plus directe entre une étude et ses polaires : le
    ``configuration_dict`` de ``batch_plot`` porte le tableau **de référence**
    (le modèle tourné une fois avec un tirage neutre), qui donne les courbes ;
    le hook porte le tableau **dispersé** (le modèle tourné n fois), qui donne
    tout le reste.

        batch_plot(
            configuration_dict={"CFD": {"df": df_reference, "color": "C0"}},
            ...,
            on_before_save=hook_dispersion_tableau(df_disperse),
        )

    Aucune mise en forme préalable : le hook filtre lui-même le tableau sur le
    point de vol de la figure, regroupe en une courbe par tirage, et superpose.

    Parameters
    ----------
    df:
        Le tableau dispersé, à plat : une ligne par (tirage × point du
        balayage), pour **tous** les points de vol. C'est la sortie du modèle
        telle quelle.
    serie:
        Le libellé de la courbe qui porte le nominal. Sa couleur est reprise,
        et ses données servent de référence à la bande. **Omis**, la seule
        courbe des axes est prise — le cas d'un ``batch_plot`` à une source.
    coefficients:
        Correspondance ``{y_key: colonne}`` quand la grandeur tracée ne porte
        pas dans le tableau dispersé le nom que ``batch_plot`` lui donne. Par
        défaut, ``y_spec["col_name"]``, donc la même colonne que la référence.
    par:
        Les colonnes identifiant un tirage. ``("tirage",)`` par défaut — le
        numéro que pose :func:`cfd_dispersion.lire_sortie_modele`.
    colonnes_point_de_vol:
        Les colonnes sur lesquelles découper le tableau dispersé. **None par
        défaut** : celles du ``context``, c'est-à-dire exactement le filtre que
        ``batch_plot`` a appliqué à la référence. ``()`` supprime tout filtrage
        — correct pour une étude à un seul point de vol, faux dès qu'il y en a
        deux, puisque toutes les figures recevraient alors tous les tirages.
    lois:
        Les lois, si on veut **aussi** la bande théorique par-dessus le nuage
        obtenu. L'intérêt est de les voir se recouvrir : un modèle qui disperse
        plus que prescrit se lit là et nulle part ailleurs.
    absent:
        Ce qu'on fait d'un point de vol que le tableau dispersé ne porte pas.
        ``"erreur"`` (défaut) lève dès la première figure ; ``"ignorer"``
        laisse la figure nue, pour une étude volontairement partielle.
    panneaux:
        En mode comparaison, les panneaux à décorer. Tous par défaut.
    max_tirages:
        Plafond de courbes dessinées. **None** — le tableau a déjà été découpé
        sur le point de vol, et en écarter d'autres en douce ferait mentir la
        légende, qui compte ce qu'elle affiche.
    options:
        Tout le reste va à
        :func:`cfd_dispersion.figures.polaire.superposer_dispersion` —
        ``remplissage``, ``remplir``, ``bordures``, ``sigmas``,
        ``boite_parametres``, ``montrer_tirages``…

    Notes
    -----
    Les **planches repliées** (``fold=`` de ``batch_plot``) ne sont pas
    décorées : elles rassemblent plusieurs conditions sur les mêmes axes en
    renommant leurs courbes, et autant de faisceaux superposés ne se liraient
    pas. Les figures ordinaires et les panneaux de comparaison le sont.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        *,
        serie: str | None = None,
        coefficients: Mapping[str, str] | None = None,
        par: Sequence[str] = ("tirage",),
        colonnes_point_de_vol: Sequence[str] | None = None,
        lois: JeuDeLois | Mapping[str, Any] | None = None,
        convention_: ConventionArg = None,
        absent: str = "erreur",
        panneaux: Sequence[str] | None = None,
        max_tirages: int | None = None,
        **options: Any,
    ) -> None:
        if absent not in ABSENT:
            raise ValueError(f"absent= doit valoir l'un de {list(ABSENT)}, reçu {absent!r}")
        self.df = df
        self.serie = serie
        self.coefficients = dict(coefficients) if coefficients else {}
        self.par = tuple(par)
        self.colonnes_point_de_vol = (
            None if colonnes_point_de_vol is None else tuple(colonnes_point_de_vol)
        )
        self.lois = lois
        self.convention_ = convention_
        self.absent = absent
        self.panneaux = tuple(panneaux) if panneaux is not None else None
        self.max_tirages = max_tirages
        self.options = options

    # ------------------------------------------------------------------

    def colonne_pour(self, context: Any) -> str:
        """La colonne du tableau dispersé qui correspond à la grandeur tracée."""
        return self.coefficients.get(
            context.y_key, _colonne(getattr(context, "y_spec", None), context.y_key)
        )

    def sous_tableau(self, context: Any) -> pd.DataFrame:
        """Le tableau dispersé restreint au point de vol de cette figure.

        Le filtre est celui de ``batch_plot`` — égalité stricte sur les clés du
        point de vol et sur les balayages figés — donc le même découpage que
        celui qui a produit la courbe tracée.
        """
        contexte = {**context.flight_point, **getattr(context, "fixed_sweeps", {})}
        if self.colonnes_point_de_vol is not None:
            contexte = {c: contexte[c] for c in self.colonnes_point_de_vol if c in contexte}

        manquantes = [c for c in contexte if c not in self.df.columns]
        if manquantes:
            raise ValueError(
                f"le tableau dispersé ne porte pas la ou les colonnes de point de vol "
                f"{manquantes} ; il porte {sorted(self.df.columns)}. Sans elles, toutes "
                "les figures recevraient tous les tirages. Ajouter la colonne, ou "
                "nommer les colonnes à filtrer avec colonnes_point_de_vol= — dont "
                "colonnes_point_de_vol=() qui supprime le filtrage, ce qui n'est juste "
                "que pour une étude à un seul point de vol."
            )

        masque = pd.Series(True, index=self.df.index)
        for colonne, valeur in contexte.items():
            masque &= self.df[colonne] == valeur
        return self.df.loc[masque]

    def __call__(self, fig: Any, ax: Any, context: Any) -> None:
        """Superpose la dispersion sur *ax*, si cette figure en relève."""
        if _panneau_ignore(self.panneaux, context):
            return
        # Une planche repliée porte plusieurs conditions sur les mêmes axes,
        # sous des libellés recomposés : la série ne s'y retrouve pas, et
        # plusieurs faisceaux empilés ne se liraient pas.
        if getattr(context, "fold_kind", None) is not None:
            return

        colonne = self.colonne_pour(context)
        if colonne not in self.df.columns:
            # Une grandeur que l'étude de dispersion ne couvre pas : la figure
            # sort telle quelle, ce qui est le comportement voulu.
            return

        abscisse = _colonne(getattr(context, "x_spec", None), context.sweep_key)
        if abscisse not in self.df.columns:
            raise ValueError(
                f"le tableau dispersé ne porte pas la colonne de balayage {abscisse!r} ; "
                f"il porte {sorted(self.df.columns)}."
            )

        sous = self.sous_tableau(context)
        if sous.empty:
            if self.absent == "erreur":
                raise ValueError(
                    f"aucun tirage dans le tableau dispersé pour le point de vol "
                    f"{context.flight_point} (grandeur {colonne!r}). Les deux tableaux "
                    "ne couvrent pas les mêmes points de vol : les rejouer sur la même "
                    "liste, ou passer absent='ignorer' si c'est voulu."
                )
            return

        serie = self.serie if self.serie is not None else _serie_unique(ax)
        courbe = _courbe_nommee(ax, serie)
        if courbe is None:
            # `include_curve` peut légitimement retirer la série de certaines
            # figures ; il n'y a alors rien à décorer sur celles-là.
            return
        x_trace, nominal = courbe

        # La référence est la courbe DÉJÀ TRACÉE, remise en tableau pour que
        # `nominal_depuis_tableau` vérifie qu'elle est bien sur l'abscisse des
        # tirages. Une bande posée à côté de sa courbe se voit mal et se lit
        # comme un biais.
        reference = pd.DataFrame({abscisse: x_trace, colonne: nominal})

        superposer_depuis_tableau(
            ax,
            sous,
            x=abscisse,
            y=colonne,
            par=self.par,
            reference=reference,
            max_tirages=self.max_tirages,
            loi=None if self.lois is None else self.lois.get(colonne),
            serie=serie,
            convention_=self.convention_,
            label=colonne,
            **self.options,
        )

    def __repr__(self) -> str:
        return (
            f"HookDispersionTableau(serie={self.serie!r}, lignes={len(self.df)}, "
            f"par={list(self.par)})"
        )


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


def hook_dispersion_tableau(df: pd.DataFrame, **options: Any) -> HookDispersionTableau:
    """Construit un :class:`HookDispersionTableau` prêt pour ``on_before_save``.

    Vérifie au passage que ``cfd_plot`` est installé, pour que l'échec survienne
    à la construction du hook plutôt qu'au milieu d'un lot de deux cents
    figures.

    Examples
    --------
    >>> hook = hook_dispersion_tableau(df_disperse, sigmas=(3,))   # doctest: +SKIP
    >>> batch_plot(..., on_before_save=hook)                        # doctest: +SKIP
    """
    _exiger_cfd_plot()
    return HookDispersionTableau(df, **options)
