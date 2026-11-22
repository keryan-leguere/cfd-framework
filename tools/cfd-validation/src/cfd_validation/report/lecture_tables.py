"""Rapport du test de lecture de table : terminal (Rich) et journal complet.

Sections : identification, spécification (défauts, combinaisons, chaque table
avec ses axes, son passage aux entrées et sa tolérance justifiée), résultats
par table, points en échec, verdict. Les coordonnées d'un point tiennent dans
**une** colonne (``mach=0.8 alphat=5 phia=90 dm=-10 dn=0``) : la largeur du
rapport ne dépend pas du nombre d'axes, une table 5D se lit comme une 2D.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
from rich import box
from rich.console import Console, Group, RenderableType
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cfd_validation.core.format import formater, pourcentage
from cfd_validation.core.tolerance import ORIGINE_DEFAUT
from cfd_validation.engine.lecture_tables import BilanTable, ResultatLectureTables
from cfd_validation.report import theme
from cfd_validation.report.console import _grille, _table, _titre, _valeur
from cfd_validation.report.journal import sha256_fichier

__all__ = ["LIGNES_MAX_TERMINAL", "ecrire_journal_rich", "ecrire_journal_tables", "rendre_lecture_tables"]

#: Points en échec listés par table au terminal (le journal les liste tous).
LIGNES_MAX_TERMINAL = 15
LARGEUR_JOURNAL = 160


def _v(x: Any) -> str:
    return formater(x, 3) if isinstance(x, (int, float)) else str(x)


def _point(ligne: pd.Series, noms: Sequence[str]) -> str:
    return "  ".join(f"{n}={_valeur(ligne[n])}" for n in noms)


def _en_tete(res: ResultatLectureTables) -> Panel:
    style = theme.OK if res.conforme else theme.ERREUR
    corps = Group(
        Text(res.description),
        Text(""),
        Text.assemble(("Verdict : ", theme.DISCRET), (res.verdict, style)),
    )
    return Panel(corps, title=Text(f"Test de lecture de table {res.identifiant}", style=theme.TITRE),
                 title_align="left", border_style=style, padding=(0, 1))


def _identification(res: ResultatLectureTables) -> list[RenderableType]:
    env = res.environnement
    g = _grille()
    g.add_row("Date (UTC)", env.date)
    g.add_row("Hôte", f"{env.hote} — {env.utilisateur}")
    g.add_row("Système", env.systeme)
    g.add_row("Python", env.python)
    g.add_row("Outils", ", ".join(f"{k} {v}" for k, v in env.versions.items()))
    for k, v in res.metadonnees.items():
        g.add_row(k, v)
    t = _table("Table", "Forme", "Nœuds", "SHA-256 du contenu", droite=(2,), insecables=(0, 1))
    for b in res.tables:
        t.add_row(b.nom, b.table.decrire_forme, str(b.table.n_noeuds), b.empreinte.courte + "…")
    return [_titre("1. Identification"), Padding(Group(g, Text(""), t), (0, 0, 1, 2))]


def _specification(res: ResultatLectureTables, complet: bool) -> list[RenderableType]:
    g = _grille()
    g.add_row("Défauts", "  ".join(f"{k}={_v(v)}" for k, v in res.defauts.items()))
    if res.combinaisons:
        g.add_row("Combinaisons", "  ".join(f"{k} ∈ {{{', '.join(_v(x) for x in v)}}}" for k, v in res.combinaisons.items()))
    else:
        g.add_row("Combinaisons", Text("aucune : chaque nœud est appelé une fois, entrées libres aux défauts", style=theme.DISCRET))
    g.add_row("Critère", "|code − table| ≤ atol + rtol·|table| ; la table est l'oracle ; une sonde NaN est un échec")
    g.add_row("Ordre de lecture", "ordre mémoire Fortran (premier indice le plus rapide), celui des DATA")

    # Une justification n'est écrite qu'une fois : sept tables au critère par défaut
    # ne répètent pas sept fois le même paragraphe.
    renvois: dict[tuple[str, str], int] = {}
    t = _table("Table", "Axes → entrées", "Sonde", "Fixées", "Critère", insecables=(0, 2))
    for b in res.tables:
        tab = b.table
        passage = ", ".join(tab.noms_axes)
        if tab.vers_entrees is not None:
            passage += f"\n→ {', '.join(b.entrees_pilotees)} (inversion)"
        fixes = "  ".join(f"{k}={_v(v)}" for k, v in tab.fixes.items()) or "—"
        tol = b.tolerance
        cle = (tol.justification or "", tol.origine)
        numero = renvois.setdefault(cle, len(renvois) + 1)
        t.add_row(tab.nom, passage, tab.sonde, fixes, f"({numero}) {tol.decrire()}")
    notes = Table.grid(padding=(0, 1))
    notes.add_column(style=theme.DISCRET, no_wrap=True)
    notes.add_column(overflow="fold")
    for (justif, origine), numero in renvois.items():
        texte = Text(justif or "non justifiée", style="" if justif else theme.ATTENTION)
        if origine == ORIGINE_DEFAUT:
            texte.append("  (critère par défaut)", style=theme.DISCRET)
        notes.add_row(f"({numero})", texte)
    blocs: list[RenderableType] = [g, Text(""), t, Text(""), notes]
    ignorees = [(b.nom, b.combinaisons_ignorees) for b in res.tables if b.combinaisons_ignorees]
    if ignorees and res.combinaisons:
        blocs.append(Text(""))
        for nom, noms in ignorees:
            blocs.append(Text(f"{nom} : {', '.join(noms)} non combiné(s) (piloté par la table ou fixé)", style=theme.DISCRET))
    if complet:
        for b in res.tables:
            if b.table.description:
                blocs.append(Text.assemble((f"{b.nom} : ", theme.DISCRET), b.table.description))
    return [_titre("2. Spécification"), Padding(Group(*blocs), (0, 0, 1, 2))]


def _resultats(res: ResultatLectureTables) -> list[RenderableType]:
    # Neuf colonnes étroites : tient en 80 caractères (forme et nœuds sont en section 1).
    t = _table("Table", "Comb.", "Appels", "Ident.", "Tolér.", "Échecs", "max |Δ|", "max ULP", "Statut",
               droite=(1, 2, 3, 4, 5, 6, 7), insecables=(0, 8))
    for b in res.tables:
        style = theme.OK if b.conforme else theme.ERREUR
        t.add_row(
            b.nom, str(len(b.combinaisons)), str(b.n_valeurs), str(b.n_identiques), str(b.n_toleres),
            Text(str(b.n_echecs), style=theme.ERREUR if b.n_echecs else ""),
            formater(b.max_abs), formater(b.max_ulp), Text("conforme" if b.conforme else "NON CONFORME", style=style),
        )
    return [_titre("3. Résultats par table"), Padding(t, (0, 0, 1, 2))]


def _echecs_table(b: BilanTable, lignes_max: int | None) -> list[RenderableType]:
    e = b.echecs()
    blocs: list[RenderableType] = []
    if len(b.combinaisons) > 1:
        blocs += _dependances(b, complet=lignes_max is None)
    montres = e if lignes_max is None else e.head(lignes_max)
    t = _table("Nœud", "Comb.", "Point (colonnes de la table)", "valeur_TAB", "valeur_CODE", "écart", "ULP", "Statut",
               droite=(0, 1, 3, 4, 5, 6), insecables=(0, 1, 7))
    for _, ligne in montres.iterrows():
        t.add_row(
            str(int(ligne["noeud"])), str(int(ligne["combinaison"])), _point(ligne, b.table.noms_axes),
            _valeur(ligne["valeur_TAB"], 10), _valeur(ligne["valeur_CODE"], 10), formater(ligne["ecart"]),
            formater(ligne["ulp"]), Text(str(ligne["statut"]).lower().replace("_", " "), style=theme.ERREUR),
        )
    blocs.append(t)
    if len(montres) < len(e):
        blocs.append(Text(f"… et {len(e) - len(montres)} autre(s) : voir le journal et RESULTATS/{b.nom}.csv", style=theme.DISCRET))
    return [Text(f"{b.nom} — {b.n_echecs} échec(s) sur {b.n_valeurs}", style=theme.ERREUR), Padding(Group(*blocs), (0, 0, 1, 2))]


#: Combinaisons citées une à une au journal (les autres comptées).
COMBINAISONS_CITEES = 12


def _dependances(b: BilanTable, *, complet: bool) -> list[RenderableType]:
    """La lecture dépend-elle d'une entrée combinée ? Laquelle, et pour quelles valeurs."""
    blocs: list[RenderableType] = []
    liees = b.dependances()
    par_comb = b.echecs_par_combinaison()
    if not liees:
        texte = "échecs dès les défauts, au même taux pour chaque valeur de " + ", ".join(b.entrees_combinees)
        blocs.append(Text.assemble(("Combinaisons : ", theme.DISCRET), (texte, theme.ATTENTION),
                                   (" — lecture fausse, pas dépendance à une autre entrée", theme.DISCRET)))
    for k, par_valeur in liees.items():
        detail = "  ".join(f"{k}={_v(v)} : {e}/{n}" for v, (e, n) in par_valeur.items())
        blocs.append(Text.assemble(("La lecture dépend de ", theme.ERREUR), (k, theme.ERREUR),
                                   (" (échecs par valeur)  ", theme.DISCRET), detail))
    if complet and len(par_comb):
        cites = list(zip(par_comb.index.tolist(), par_comb.tolist()))
        texte = "  ".join(f"[{b.decrire_combinaison(int(c))}] {n}" for c, n in cites[:COMBINAISONS_CITEES])
        if len(cites) > COMBINAISONS_CITEES:
            texte += f"  … et {len(cites) - COMBINAISONS_CITEES} autre(s)"
        blocs.append(Text.assemble(("Échecs par combinaison : ", theme.DISCRET), texte))
    return blocs


def _echecs(res: ResultatLectureTables, lignes_max: int | None) -> list[RenderableType]:
    sections: list[RenderableType] = [_titre("4. Points en échec")]
    en_echec = [b for b in res.tables if not b.conforme]
    if not en_echec:
        return [*sections, Padding(Text("Aucun : chaque nœud relu dans la tolérance de sa table.", style=theme.OK), (0, 0, 1, 2))]
    for b in en_echec:
        sections += _echecs_table(b, lignes_max)
    return sections


def _verdict(res: ResultatLectureTables) -> Panel:
    n = sum(b.n_valeurs for b in res.tables)
    n_id = sum(b.n_identiques for b in res.tables)
    n_tol = sum(b.n_toleres for b in res.tables)
    n_ech = sum(b.n_echecs for b in res.tables)
    lignes: list[RenderableType] = [Text(
        f"{len(res.tables)} tables, {n} appels : {n_id} identiques ({pourcentage(n_id, n)}), "
        f"{n_tol} dans la tolérance, {n_ech} en échec."
    )]
    for b in res.tables:
        style = theme.OK if b.conforme else theme.ERREUR
        lignes.append(Text.assemble(("• ", style), (f"{b.nom:<8s}", ""), (b.verdict, style)))
    style = theme.OK if res.conforme else theme.ERREUR
    return Panel(Group(*lignes), title=Text(f"Verdict {res.identifiant} : {res.verdict}", style=style),
                 title_align="left", border_style=style, padding=(0, 1))


def rendre_lecture_tables(
    console: Console, res: ResultatLectureTables, *, lignes_max: int | None = LIGNES_MAX_TERMINAL, complet: bool = False
) -> None:
    """Le rapport sur ``console`` ; ``complet`` (journal) : tous les points en échec, les descriptions."""
    for s in (
        _en_tete(res), Text(""), *_identification(res), *_specification(res, complet),
        *_resultats(res), *_echecs(res, None if complet else lignes_max), _verdict(res),
    ):
        console.print(s)


def ecrire_journal_rich(
    chemin: Path,
    entete: Sequence[str],
    rendre: Callable[[Console], None],
    *,
    pieces: Sequence[Path] = (),
    racine: Path | None = None,
    largeur: int = LARGEUR_JOURNAL,
) -> Path:
    """Un journal texte brut : ``entete``, le rapport complet (``rendre``), les pièces et leur SHA-256.

    Rendu en mémoire, sans couleur, espaces de fin de ligne ôtés. Commun aux
    contrôles sur les tables (lecture, bornes).
    """
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tampon = io.StringIO()
    console = Console(file=tampon, width=largeur, no_color=True, color_system=None, force_terminal=False,
                      highlight=False, emoji=False, soft_wrap=False)
    for ligne in entete:
        console.print(ligne)
    console.print()
    rendre(console)
    if pieces:
        t = Table(title="Pièces produites (SHA-256)", title_justify="left", header_style=theme.ENTETE,
                  box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False)
        t.add_column("Pièce")
        t.add_column("SHA-256")
        for p in pieces:
            nom = str(p.relative_to(racine)) if racine is not None and p.is_relative_to(racine) else str(p)
            t.add_row(nom, sha256_fichier(p) if p.exists() else "—")
        console.print(Padding(t, (1, 0, 0, 2)))
    chemin.write_text("\n".join(x.rstrip() for x in tampon.getvalue().splitlines()) + "\n", encoding="utf-8")
    return chemin


def ecrire_journal_tables(
    res: ResultatLectureTables, chemin: Path, *, pieces: Sequence[Path] = (), racine: Path | None = None
) -> Path:
    """Le journal complet du test de lecture de table."""
    entete = [
        f"Journal du test de lecture de table {res.identifiant} — "
        f"cfd-validation {res.environnement.versions.get('cfd-validation', '?')}",
        f"Écrit le {res.environnement.date} (UTC). Ce fichier est généré : ne pas l'éditer.",
    ]
    return ecrire_journal_rich(chemin, entete, lambda c: rendre_lecture_tables(c, res, complet=True),
                               pieces=pieces, racine=racine)
