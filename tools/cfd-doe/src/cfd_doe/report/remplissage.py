"""Rapport terminal du remplissage (``cfd-doe remplir``).

Lu de haut en bas :

1. **En-tête** : l'étude réduite, les conditions (Mach, paramètres).
2. **Grille de référence** : les niveaux de chaque variable du repère de travail.
3. **Plan retenu** : ses tables (rôle, ce qu'elles balaient, nombre de calculs),
   son hypothèse, et la **démarche** numérotée — quoi lancer, dans quel ordre,
   quoi comparer.
4. **Comparaison** de tous les plans demandés : calculs, contrôles, tests.

Avec ``verbeux=True``, chaque plan reçoit le détail du plan retenu, plus sa
répartition par Mach et par sous-domaine.
"""

from __future__ import annotations

from collections.abc import Sequence

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cfd_doe.data.format import formater_intervalle, formater_nombre
from cfd_doe.engine.remplissage import (
    ROLE_CALCUL,
    ROLE_CONTROLE,
    ROLE_TEST,
    Contexte,
    PlanDOE,
    Resultat,
)
from cfd_doe.report import theme
from cfd_doe.report.console import libelle

__all__ = ["detail_plan", "rapport_remplissage", "tableau_comparaison"]

_STYLE_ROLE = {ROLE_CALCUL: theme.VALEUR, ROLE_CONTROLE: theme.ATTENTION, ROLE_TEST: theme.OK}
_NOM_ROLE = {ROLE_CALCUL: "calcul", ROLE_CONTROLE: "contrôle", ROLE_TEST: "test"}
_TABLE_COURT = {"oui": "directe", "oui, par somme": "somme", "non": "modèle"}


def _n(x: int) -> str:
    """Entier à la française : 12 345."""
    return f"{x:,}".replace(",", chr(0x202F))


def _valeurs(valeurs: Sequence[float], largeur: int = 9) -> str:
    textes = [formater_nombre(v) for v in valeurs]
    if len(textes) > largeur:
        textes = [*textes[:4], "…", *textes[-2:]]
    return " · ".join(textes)


def _table(titre: str) -> Table:
    return Table(
        title=Text(titre, style=theme.TITRE),
        title_justify="left",
        box=box.SIMPLE_HEAD,
        header_style=theme.ENTETE,
        pad_edge=False,
        padding=(0, 1, 0, 0),
    )


def _puces(lignes: Sequence[tuple[str, str, str]]) -> Table:
    grille = Table.grid(padding=(0, 1))
    grille.add_column(no_wrap=True, justify="right", min_width=3)
    grille.add_column()
    for puce, texte, style in lignes:
        grille.add_row(Text(puce, style=style), Text(texte, style=style))
    return grille


# ---------------------------------------------------------------------------
# En-tête et grille
# ---------------------------------------------------------------------------


def _en_tete(c: Contexte) -> Panel:
    r = c.reduction
    grille = Table.grid(padding=(0, 2))
    grille.add_column(no_wrap=True, style=theme.DISCRET)
    grille.add_column()
    repere = "polaire (αt, φa), repère mixte" if r.repere == "polaire" else "cartésien (α, β)"
    ordre = "∞" if r.ordre_groupe is None else str(r.ordre_groupe)
    grille.add_row(
        "Étude",
        Text.assemble(
            (r.etude.nom, theme.VALEUR),
            (f"  {r.etude.trajectoire.nom}, {r.etude.geometrie.nom}", theme.DISCRET),
        ),
    )
    grille.add_row(
        "Domaine",
        Text.assemble(
            (f"{len(r.sous_domaines)} sous-domaines", theme.VALEUR),
            (f"  {repere}, {r.groupe} d'ordre {ordre}", theme.DISCRET),
        ),
    )
    if c.machs:
        grille.add_row(
            "Mach",
            Text.assemble(
                (f"{len(c.machs)}", theme.VALEUR), (f"  {_valeurs(c.machs)}", theme.DISCRET)
            ),
        )
    for p in c.parametres:
        nature = "discret" if not p.continu else "continu pour les plans à métamodèle"
        grille.add_row(
            f"Paramètre {p.nom}",
            Text.assemble(
                (_valeurs(p.niveaux), theme.VALEUR),
                (f"  nominal {formater_nombre(p.nominal)}, {nature}", theme.DISCRET),
            ),
        )
    exclusions = c.remplissage.exclure
    if exclusions:
        grille.add_row("Exclusions", Text(" ; ".join(exclusions), style=theme.ATTENTION))
    if c.remplissage.source is not None:
        grille.add_row("Fichier", Text(str(c.remplissage.source), style=theme.DISCRET))
    return Panel(
        grille,
        title=Text(f"cfd-doe remplir · {c.remplissage.nom}", style=theme.TITRE),
        title_align="left",
        box=box.ROUNDED,
        border_style=theme.DISCRET,
        padding=(0, 1),
    )


def _grille_reference(c: Contexte) -> Table:
    noeuds = 1
    for v in c.libres:
        noeuds *= len(c.niveaux[v])
    table = _table(f"Grille de référence ({_n(noeuds)} nœuds avant symétries)")
    table.add_column("variable")
    table.add_column("domaine", justify="center", no_wrap=True)
    table.add_column("n", justify="right")
    table.add_column("niveaux (°)", style=theme.DISCRET)
    for v in c.variables:
        if v in c.libres:
            table.add_row(
                c.symbole(v),
                formater_intervalle(c.boite[v], espace=False),
                str(len(c.niveaux[v])),
                _valeurs(c.niveaux[v]),
            )
        else:
            table.add_row(
                Text(c.symbole(v), style=theme.DISCRET),
                Text(formater_nombre(c.reference[v]), style=theme.FIXE),
                Text("1", style=theme.DISCRET),
                "fixée par la réduction",
            )
    return table


# ---------------------------------------------------------------------------
# Un plan
# ---------------------------------------------------------------------------


def _par_mach(plan: PlanDOE, c: Contexte) -> str:
    comptes = list(plan.par_mach().values())
    if not comptes or not c.machs:
        return "—"
    absents = len(c.machs) - len(comptes)
    bas, haut = (0 if absents else min(comptes)), max(comptes)
    return _n(haut) if bas == haut else f"{_n(bas)} à {_n(haut)}"


def detail_plan(plan: PlanDOE, c: Contexte, *, complet: bool = False) -> Group:
    """Les tables d'un plan, son hypothèse, sa démarche ; ``complet`` ajoute les répartitions."""
    table = _table(f"{plan.nom} — {plan.titre} ({_n(plan.compter())} calculs)")
    table.add_column("table", no_wrap=True)
    table.add_column("rôle", no_wrap=True)
    table.add_column("ce qu'elle balaie")
    table.add_column("calculs", justify="right")
    for bloc, n in plan.par_bloc():
        style = _STYLE_ROLE[bloc.role]
        table.add_row(
            Text(bloc.nom, style=style),
            Text(_NOM_ROLE[bloc.role], style=style),
            Text(bloc.detail, style=theme.DISCRET),
            Text(_n(n), style=style),
        )
    morceaux: list[RenderableType] = [table]

    faits = [
        ("", f"hypothèse : {plan.hypothese}", theme.DISCRET),
        ("", f"table du simulateur : {plan.table_directe}", theme.DISCRET),
    ]
    if c.machs:
        faits.append(("", f"calculs par Mach : {_par_mach(plan, c)}", theme.DISCRET))
    if plan.facteurs:
        faits.append(
            (
                "",
                f"{len(plan.facteurs)} facteurs continus : "
                + ", ".join(c.symbole(f) for f in plan.facteurs),
                theme.DISCRET,
            )
        )
    if plan.spec.description:
        faits.append(("", plan.spec.description, theme.DISCRET))
    morceaux.append(_puces(faits))

    morceaux += [Text(), Text("  Démarche", style=theme.ENTETE)]
    morceaux.append(
        _puces([(f"{i}.", etape, theme.VALEUR) for i, etape in enumerate(plan.demarche, 1)])
    )
    if plan.avertissements:
        morceaux.append(_puces([("!", a, theme.ATTENTION) for a in plan.avertissements]))

    if complet:
        repartition = Table.grid(padding=(0, 2))
        repartition.add_column(style=theme.DISCRET, no_wrap=True)
        repartition.add_column()
        if c.machs:
            par_mach = plan.par_mach()
            repartition.add_row(
                "   par Mach",
                "  ".join(f"{formater_nombre(m)} : {_n(par_mach.get(m, 0))}" for m in c.machs),
            )
        noms = {sd.numero: libelle(sd) for sd in c.sous_domaines}
        repartition.add_row(
            "   par sous-domaine",
            "  ".join(f"#{k} {noms[k]} : {_n(n)}" for k, n in plan.par_sous_domaine().items()),
        )
        for fidelite in plan.fidelites:
            repartition.add_row(f"   fidélité {fidelite}", _n(plan.compter(fidelite=fidelite)))
        morceaux += [Text(), repartition]
    return Group(*morceaux)


# ---------------------------------------------------------------------------
# Comparaison
# ---------------------------------------------------------------------------


def tableau_comparaison(resultat: Resultat) -> Table:
    """Tous les plans côte à côte ; le plan retenu est marqué."""
    c = resultat.contexte
    retenu = c.remplissage.retenu
    table = _table(f"Comparaison des plans ({len(resultat.plans)})")
    # Seule la méthode se raccourcit : un nombre tronqué ne se lit plus.
    largeur_nom = min(24, max(len(p.nom) for p in resultat.plans) + 2)
    table.add_column("plan", no_wrap=True, min_width=largeur_nom, overflow="ellipsis")
    table.add_column("méthode", no_wrap=True, overflow="ellipsis", max_width=19)
    for colonne, role in (
        ("calcul", ROLE_CALCUL),
        ("contrôle", ROLE_CONTROLE),
        ("test", ROLE_TEST),
        ("total", None),
    ):
        largeur = max(len(colonne), *(len(_n(p.compter(role))) for p in resultat.plans))
        table.add_column(colonne, justify="right", no_wrap=True, min_width=largeur)
    table.add_column("table", style=theme.DISCRET, no_wrap=True, min_width=7)
    for plan in resultat.plans:
        est_retenu = plan.nom == retenu

        def cellule(role: str, plan: PlanDOE = plan) -> Text:
            n = plan.compter(role)
            return Text(_n(n) if n else "·", style=_STYLE_ROLE[role] if n else theme.DISCRET)

        ligne: list[RenderableType] = [
            Text(
                ("▸ " if est_retenu else "  ") + plan.nom,
                style=theme.ACCENT if est_retenu else theme.VALEUR,
            ),
            plan.titre,
            cellule(ROLE_CALCUL),
            cellule(ROLE_CONTROLE),
            cellule(ROLE_TEST),
            Text(_n(plan.compter()), style=theme.ACCENT if est_retenu else theme.VALEUR),
        ]
        ligne.append(_TABLE_COURT[plan.table_directe])
        table.add_row(*ligne)
    return table


def _hypotheses(resultat: Resultat) -> Table:
    return _puces([("", f"{p.nom} : {p.hypothese}", theme.DISCRET) for p in resultat.plans])


def _synthese(resultat: Resultat) -> Text:
    plan = resultat.retenu
    texte = Text.assemble(
        ("Plan retenu : ", theme.DISCRET),
        (plan.nom, theme.ACCENT),
        (" · ", theme.DISCRET),
        (_n(plan.compter()), theme.ACCENT),
        (" calculs", theme.DISCRET),
    )
    details = [
        f"{_n(plan.compter(role))} {_NOM_ROLE[role]}"
        for role in (ROLE_CALCUL, ROLE_CONTROLE, ROLE_TEST)
        if plan.compter(role)
    ]
    if len(details) > 1:
        texte.append(f" ({', '.join(details)})", style=theme.DISCRET)
    return texte


def rapport_remplissage(resultat: Resultat, *, verbeux: bool = False) -> Group:
    """Le rapport complet, prêt pour ``Console.print``."""
    c = resultat.contexte
    morceaux: list[RenderableType] = [_en_tete(c), Text(), _grille_reference(c)]
    if c.notes:
        morceaux.append(_puces([("·", n, theme.DISCRET) for n in c.notes]))
    morceaux.append(Text())

    if verbeux:
        for plan in resultat.plans:
            morceaux += [detail_plan(plan, c, complet=True), Text()]
    else:
        morceaux += [detail_plan(resultat.retenu, c), Text()]

    if len(resultat.plans) > 1:
        morceaux.append(tableau_comparaison(resultat))
        legende = [
            (
                "",
                "▸ plan retenu, écrit dans le fichier DOE · calculs dans les sous-domaines, "
                "symétries exploitées",
                theme.DISCRET,
            ),
            (
                "",
                "table du simulateur — directe : les calculs, complétés par symétrie ; somme : "
                "incréments à additionner ; modèle : un métamodèle à ajuster et valider",
                theme.DISCRET,
            ),
        ]
        morceaux.append(_puces(legende))
        if verbeux:
            morceaux += [Text(), Text("  Hypothèses", style=theme.ENTETE), _hypotheses(resultat)]
        morceaux.append(Text())
    morceaux.append(_synthese(resultat))
    return Group(*morceaux)
