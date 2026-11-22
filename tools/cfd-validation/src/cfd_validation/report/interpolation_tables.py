"""Rapport du test d'interpolation de table : terminal (Rich) et journal complet.

Sections : identification, spécification (défauts, points, tolérances
justifiées), résultats par groupe (axe ou centres : points, mailles, **observé**,
échecs), points en échec avec leur maille, polaires tracées, verdict. Comme pour
les deux autres tests de table, les coordonnées d'un point tiennent dans une
colonne : le rapport tient en 80 colonnes en 2D comme en 5D.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from rich.console import Console, Group, RenderableType
from rich.padding import Padding
from rich.panel import Panel
from rich.text import Text

from cfd_validation.core.format import formater, pourcentage
from cfd_validation.core.tolerance import ORIGINE_DEFAUT, Tolerance
from cfd_validation.engine.interpolation_tables import (
    LINEAIRE,
    OBSERVE_INDISCERNABLE,
    BilanInterpolation,
    ResultatInterpolationTables,
    tolerance_interpolation,
)
from cfd_validation.engine.polaires import Polaire
from cfd_validation.report import theme
from cfd_validation.report.console import _grille, _table, _titre, _valeur
from cfd_validation.report.lecture_tables import (
    LIGNES_MAX_TERMINAL,
    _point,
    _v,
    ecrire_journal_rich,
)

__all__ = ["ecrire_journal_interpolation", "rendre_interpolation_tables"]

#: Mailles en échec citées par groupe avant « … ».
MAILLES_CITEES = 6


def _en_tete(res: ResultatInterpolationTables) -> Panel:
    style = theme.OK if res.conforme else theme.ERREUR
    corps = Group(Text(res.description), Text(""), Text.assemble(("Verdict : ", theme.DISCRET), (res.verdict, style)))
    return Panel(corps, title=Text(f"Test d'interpolation de table {res.identifiant}", style=theme.TITRE),
                 title_align="left", border_style=style, padding=(0, 1))


def _identification(res: ResultatInterpolationTables) -> list[RenderableType]:
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


def _specification(res: ResultatInterpolationTables, complet: bool) -> list[RenderableType]:
    g = _grille()
    g.add_row("Défauts", "  ".join(f"{k}={_v(v)}" for k, v in res.defauts.items()))
    g.add_row("Par axe", "l'axe dans chacune de ses mailles, à t = "
              + ", ".join(f"{f:g}" for f in res.fractions) + " ; les autres axes sur tous leurs nœuds")
    g.add_row("Centres", "le centre de chaque maille, tous les axes à t = 0.5 (couplage entre axes)"
              if res.centres else Text("non demandés", style=theme.DISCRET))
    g.add_row("Attendu", "l'interpolation multilinéaire de la table, Σ Π (1 − t | t)·V sur les coins de la maille")
    g.add_row("Observé", "linéaire ; palier (le code rend un coin de la maille) ; indiscernable (maille plate) ; "
                         "ni l'un ni l'autre")
    g.add_row("Critère", "|code − attendu| ≤ atol + rtol·|attendu|")

    renvois: dict[tuple[float, float, str, str], int] = {}
    tol_table = _table("Table", "Groupes", "Critère", insecables=(0,))
    for b in res.tables:
        tol: Tolerance = tolerance_interpolation(b.table)
        cle = (tol.rtol, tol.atol, tol.justification or "", tol.origine)
        numero = renvois.setdefault(cle, len(renvois) + 1)
        tol_table.add_row(b.nom, " ".join(gr.groupe.nom for gr in b.groupes), f"({numero}) {tol.decrire()}")
    notes = _grille()
    for (_, _, justif, origine), numero in renvois.items():
        texte = Text(justif or "non justifiée", style="" if justif else theme.ATTENTION)
        if origine == ORIGINE_DEFAUT:
            texte.append("  (tolérance par défaut)", style=theme.DISCRET)
        notes.add_row(f"({numero})", texte)
    blocs: list[RenderableType] = [g, Text(""), tol_table, Text(""), notes]
    if complet:
        for b in res.tables:
            if b.table.description:
                blocs.append(Text.assemble((f"{b.nom} : ", theme.DISCRET), b.table.description))
    return [_titre("2. Spécification"), Padding(Group(*blocs), (0, 0, 1, 2))]


def _resultats(res: ResultatInterpolationTables) -> list[RenderableType]:
    t = _table("Table", "Groupe", "Points", "Mailles", "Observé", "Échecs", "max |Δ|", "Statut",
               droite=(2, 3, 5, 6), insecables=(0, 1, 7))
    for b in res.tables:
        for g in b.groupes:
            style = theme.OK if g.conforme else theme.ERREUR
            normal = g.observe in (LINEAIRE, OBSERVE_INDISCERNABLE) or g.conforme
            t.add_row(b.nom, g.groupe.nom, str(g.n_points), str(g.n_mailles),
                      Text(g.observe, style="" if normal else theme.ERREUR),
                      Text(str(g.n_echecs), style=theme.ERREUR if g.n_echecs else ""),
                      formater(g.max_abs), Text("ok" if g.conforme else "ÉCHEC", style=style))
    return [_titre("3. Résultats par groupe"), Padding(t, (0, 0, 1, 2))]


def _mailles(noms: Sequence[str]) -> str:
    cites = ", ".join(noms[:MAILLES_CITEES])
    return cites + (f", … (+{len(noms) - MAILLES_CITEES})" if len(noms) > MAILLES_CITEES else "")


def _echecs_table(b: BilanInterpolation, lignes_max: int | None) -> list[RenderableType]:
    e = b.echecs()
    montres = e if lignes_max is None else e.head(lignes_max)
    t = _table("Groupe", "Maille", "Point", "attendu", "code", "écart", "Statut",
               droite=(3, 4, 5), insecables=(0, 6))
    for _, ligne in montres.iterrows():
        t.add_row(str(ligne["groupe"]), str(ligne["maille"]), _point(ligne, b.table.noms_axes),
                  _valeur(ligne["valeur_ATTENDUE"], 8), _valeur(ligne["valeur_CODE"], 8), formater(ligne["ecart"]),
                  Text(str(ligne["statut"]).lower().replace("_", " "), style=theme.ERREUR))
    blocs: list[RenderableType] = []
    for g in b.groupes:
        if not g.conforme:
            blocs.append(Text.assemble(
                (f"{g.groupe.nom} : ", theme.ERREUR), f"attendu {LINEAIRE}, observé ", (g.observe, theme.ERREUR),
                f" — {g.n_echecs}/{g.n_points} points, {len(g.mailles_en_echec)}/{g.n_mailles} mailles "
                f"({_mailles(g.mailles_en_echec)})"))
    blocs.append(t)
    if len(montres) < len(e):
        blocs.append(Text(f"… et {len(e) - len(montres)} autre(s) : voir le journal et RESULTATS/{b.nom}.csv",
                          style=theme.DISCRET))
    return [Text(f"{b.nom} — {b.n_echecs} échec(s) sur {b.n_valeurs}", style=theme.ERREUR),
            Padding(Group(*blocs), (0, 0, 1, 2))]


def _echecs(res: ResultatInterpolationTables, lignes_max: int | None) -> list[RenderableType]:
    sections: list[RenderableType] = [_titre("4. Points en échec")]
    en_echec = [b for b in res.tables if not b.conforme]
    if not en_echec:
        texte = "Aucun : entre les nœuds, le code rend l'interpolation multilinéaire de chaque table."
        return [*sections, Padding(Text(texte, style=theme.OK), (0, 0, 1, 2))]
    for b in en_echec:
        sections += _echecs_table(b, lignes_max)
    return sections


def _polaires(polaires: Sequence[Polaire]) -> list[RenderableType]:
    if not polaires:
        return []
    t = _table("Table", "Abscisse", "Conditions", "Courbes", "Superposé", "Appels", droite=(3, 5), insecables=(0, 1))
    for p in polaires:
        t.add_row(p.nom, p.axe, " ".join(p.conditions) or "—", str(p.n_courbes), p.superpose or "—", str(p.n_appels))
    note = Text("Qualitatives, sans verdict : la courbe du code passe par les nœuds (lecture), droite entre eux "
                "(interpolation), plate ou prolongée au-delà des bornes selon la consigne (bornes).",
                style=theme.DISCRET)
    return [_titre("5. Polaires"), Padding(Group(t, Text(""), note), (0, 0, 1, 2))]


def _verdict(res: ResultatInterpolationTables) -> Panel:
    n = res.n_appels
    n_id = sum(b.n_identiques for b in res.tables)
    n_tol = sum(b.n_toleres for b in res.tables)
    n_ech = sum(b.n_echecs for b in res.tables)
    n_gr = sum(len(b.groupes) for b in res.tables)
    lignes: list[RenderableType] = [Text(
        f"{len(res.tables)} tables, {n_gr} groupes, {n} appels : {n_id} identiques ({pourcentage(n_id, n)}), "
        f"{n_tol} dans la tolérance, {n_ech} en échec."
    )]
    for b in res.tables:
        style = theme.OK if b.conforme else theme.ERREUR
        lignes.append(Text.assemble(("• ", style), (f"{b.nom:<8s}", ""), (b.verdict, style)))
    for m in res.motifs_non_conformite:
        lignes.append(Text.assemble(("  ✗ ", theme.ERREUR), m))
    style = theme.OK if res.conforme else theme.ERREUR
    return Panel(Group(*lignes), title=Text(f"Verdict {res.identifiant} : {res.verdict}", style=style),
                 title_align="left", border_style=style, padding=(0, 1))


def rendre_interpolation_tables(
    console: Console, res: ResultatInterpolationTables, *, polaires: Sequence[Polaire] = (),
    lignes_max: int | None = LIGNES_MAX_TERMINAL, complet: bool = False,
) -> None:
    """Le rapport sur ``console`` ; ``complet`` (journal) : tous les points en échec, les descriptions."""
    for s in (
        _en_tete(res), Text(""), *_identification(res), *_specification(res, complet),
        *_resultats(res), *_echecs(res, None if complet else lignes_max), *_polaires(polaires), _verdict(res),
    ):
        console.print(s)


def ecrire_journal_interpolation(
    res: ResultatInterpolationTables, chemin: Path, *, polaires: Sequence[Polaire] = (),
    pieces: Sequence[Path] = (), racine: Path | None = None,
) -> Path:
    """Le journal complet du test d'interpolation."""
    entete = [
        f"Journal du test d'interpolation de table {res.identifiant} — "
        f"cfd-validation {res.environnement.versions.get('cfd-validation', '?')}",
        f"Écrit le {res.environnement.date} (UTC). Ce fichier est généré : ne pas l'éditer.",
    ]
    return ecrire_journal_rich(chemin, entete,
                               lambda c: rendre_interpolation_tables(c, res, polaires=polaires, complet=True),
                               pieces=pieces, racine=racine)
