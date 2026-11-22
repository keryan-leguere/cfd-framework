"""Rapport du test des bornes de table : terminal (Rich) et journal complet.

Sections : identification, spécification (défauts, distance hors bornes,
consigne de chaque axe et de chaque côté, tolérances justifiées), résultats par
face (attendu, **observé**, points, échecs), points en échec, verdict. Comme pour
la lecture de table, les coordonnées d'un point tiennent dans une colonne : le
rapport garde la même largeur en 2D qu'en 5D, et tient en 80 colonnes.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from rich.console import Console, Group, RenderableType
from rich.padding import Padding
from rich.panel import Panel
from rich.text import Text

from cfd_validation.core.bornes import INATTEIGNABLE
from cfd_validation.core.format import formater, pourcentage
from cfd_validation.core.tolerance import ORIGINE_DEFAUT, Tolerance
from cfd_validation.engine.bornes_tables import BilanBornes, ResultatBornesTables, tolerance_face
from cfd_validation.report import theme
from cfd_validation.report.console import _grille, _table, _titre, _valeur
from cfd_validation.report.lecture_tables import (
    LIGNES_MAX_TERMINAL,
    _point,
    _v,
    ecrire_journal_rich,
)

__all__ = ["ecrire_journal_bornes", "rendre_bornes_tables"]


def _en_tete(res: ResultatBornesTables) -> Panel:
    style = theme.OK if res.conforme else theme.ERREUR
    corps = Group(Text(res.description), Text(""), Text.assemble(("Verdict : ", theme.DISCRET), (res.verdict, style)))
    return Panel(corps, title=Text(f"Test des bornes de table {res.identifiant}", style=theme.TITRE),
                 title_align="left", border_style=style, padding=(0, 1))


def _identification(res: ResultatBornesTables) -> list[RenderableType]:
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


def _consigne(texte: str, origine: str) -> Text:
    t = Text(texte, style=theme.DISCRET if texte == INATTEIGNABLE else "")
    if origine == ORIGINE_DEFAUT:
        t.append("*", style=theme.ATTENTION)
    return t


def _specification(res: ResultatBornesTables, complet: bool) -> list[RenderableType]:
    g = _grille()
    g.add_row("Défauts", "  ".join(f"{k}={_v(v)}" for k, v in res.defauts.items()))
    distance = f"{res.ecart * 100:g} % de l'étendue de l'axe, au-delà de chaque borne"
    if res.ecarts:
        distance += " ; " + ", ".join(f"{k} : {v * 100:g} %" for k, v in res.ecarts.items())
    g.add_row("Distance", distance)
    g.add_row("Points", "une face par axe et par côté : cet axe hors bornes, les autres sur tous leurs nœuds")
    g.add_row("Consignes", "sature (valeur au bord), extrapole (dernière maille prolongée), "
                           "inatteignable (aucune entrée n'y mène : non testé)")
    g.add_row("Défaut", Text.assemble(f"{res.consigne_defaut} ", ("(*)", theme.ATTENTION),
                                      " pour un axe dont la table ne déclare pas la consigne"))
    g.add_row("Critère", "|code − attendu| ≤ atol + rtol·|attendu| ; l'attendu est calculé sur la table")

    t = _table("Table", "Axe", "Grille", "Hors bornes", "Consigne min / max", insecables=(0, 1))
    for b in res.tables:
        faces = {(f.face.axe, f.face.cote): f.face for f in b.faces} | {(f.axe, f.cote): f for f in b.non_testees}
        for axe, grille in b.table.axes.items():
            fmin, fmax = faces[(axe, "min")], faces[(axe, "max")]
            consigne = Text.assemble(_consigne(fmin.consigne, fmin.origine), " / ", _consigne(fmax.consigne, fmax.origine))
            t.add_row(b.nom, axe, f"[{_v(float(grille[0]))}, {_v(float(grille[-1]))}]",
                      f"{_v(fmin.valeur)} / {_v(fmax.valeur)}", consigne)

    renvois: dict[tuple[float, float, str, str], int] = {}
    tol_table = _table("Table", "Faces", "Critère", insecables=(0,))
    for b in res.tables:
        par_tol: dict[tuple[float, float, str, str], list[str]] = {}
        for f in b.faces:
            tol: Tolerance = tolerance_face(b.table, f.face.consigne)
            cle = (tol.rtol, tol.atol, tol.justification or "", tol.origine)
            par_tol.setdefault(cle, []).append(f.face.nom)
        for cle, noms in par_tol.items():
            numero = renvois.setdefault(cle, len(renvois) + 1)
            tol = Tolerance(cle[0], cle[1], cle[2] or None, cle[3])
            tol_table.add_row(b.nom, " ".join(noms), f"({numero}) {tol.decrire()}")
    notes = _grille()
    for (_, _, justif, origine), numero in renvois.items():
        texte = Text(justif or "non justifiée", style="" if justif else theme.ATTENTION)
        if origine == ORIGINE_DEFAUT:
            texte.append("  (tolérance par défaut)", style=theme.DISCRET)
        notes.add_row(f"({numero})", texte)
    blocs: list[RenderableType] = [g, Text(""), t, Text(""), tol_table, Text(""), notes]
    if complet:
        for b in res.tables:
            if b.table.description:
                blocs.append(Text.assemble((f"{b.nom} : ", theme.DISCRET), b.table.description))
    return [_titre("2. Spécification"), Padding(Group(*blocs), (0, 0, 1, 2))]


def _resultats(res: ResultatBornesTables) -> list[RenderableType]:
    t = _table("Table", "Face", "Attendu", "Observé", "Points", "Échecs", "max |Δ|", "Statut",
               droite=(4, 5, 6), insecables=(0, 1, 7))
    non_testees: list[str] = []
    for b in res.tables:
        for f in b.faces:
            style = theme.OK if f.conforme else theme.ERREUR
            observe = Text(f.observe, style="" if f.observe == f.face.consigne or f.conforme else theme.ERREUR)
            t.add_row(b.nom, f.face.nom, f.face.consigne, observe, str(f.n_points),
                      Text(str(f.n_echecs), style=theme.ERREUR if f.n_echecs else ""),
                      formater(f.max_abs), Text("ok" if f.conforme else "ÉCHEC", style=style))
        if b.non_testees:
            non_testees.append(f"{b.nom} {' '.join(f.nom for f in b.non_testees)}")
    blocs: list[RenderableType] = [t]
    if non_testees:
        blocs += [Text(""), Text("Non testées (inatteignables) : " + " ; ".join(non_testees), style=theme.DISCRET)]
    return [_titre("3. Résultats par face"), Padding(Group(*blocs), (0, 0, 1, 2))]


def _echecs_table(b: BilanBornes, lignes_max: int | None) -> list[RenderableType]:
    e = b.echecs()
    montres = e if lignes_max is None else e.head(lignes_max)
    t = _table("Face", "Point (colonnes de la table)", "attendu", "code", "écart", "ULP", "Statut",
               droite=(2, 3, 4, 5), insecables=(0, 6))
    for _, ligne in montres.iterrows():
        t.add_row(str(ligne["face"]), _point(ligne, b.table.noms_axes), _valeur(ligne["valeur_ATTENDUE"], 8),
                  _valeur(ligne["valeur_CODE"], 8), formater(ligne["ecart"]), formater(ligne["ulp"]),
                  Text(str(ligne["statut"]).lower().replace("_", " "), style=theme.ERREUR))
    blocs: list[RenderableType] = []
    for f in b.faces:
        if not f.conforme:
            blocs.append(Text.assemble((f"{f.face.nom} : ", theme.ERREUR), f"attendu {f.face.consigne}, observé ",
                                       (f.observe, theme.ERREUR), f" — {f.n_echecs}/{f.n_points} hors tolérance"))
    blocs.append(t)
    if len(montres) < len(e):
        blocs.append(Text(f"… et {len(e) - len(montres)} autre(s) : voir le journal et RESULTATS/{b.nom}.csv",
                          style=theme.DISCRET))
    return [Text(f"{b.nom} — {b.n_echecs} échec(s) sur {b.n_valeurs}", style=theme.ERREUR),
            Padding(Group(*blocs), (0, 0, 1, 2))]


def _echecs(res: ResultatBornesTables, lignes_max: int | None) -> list[RenderableType]:
    sections: list[RenderableType] = [_titre("4. Points en échec")]
    en_echec = [b for b in res.tables if not b.conforme]
    if not en_echec:
        texte = "Aucun : chaque face se comporte comme sa consigne le demande."
        return [*sections, Padding(Text(texte, style=theme.OK), (0, 0, 1, 2))]
    for b in en_echec:
        sections += _echecs_table(b, lignes_max)
    return sections


def _verdict(res: ResultatBornesTables) -> Panel:
    n = res.n_appels
    n_id = sum(b.n_identiques for b in res.tables)
    n_tol = sum(b.n_toleres for b in res.tables)
    n_ech = sum(b.n_echecs for b in res.tables)
    n_faces = sum(len(b.faces) for b in res.tables)
    n_nt = sum(len(b.non_testees) for b in res.tables)
    lignes: list[RenderableType] = [Text(
        f"{len(res.tables)} tables, {n_faces} faces testées ({n_nt} inatteignables), {n} appels : "
        f"{n_id} identiques ({pourcentage(n_id, n)}), {n_tol} dans la tolérance, {n_ech} en échec."
    )]
    for b in res.tables:
        style = theme.OK if b.conforme else theme.ERREUR
        lignes.append(Text.assemble(("• ", style), (f"{b.nom:<8s}", ""), (b.verdict, style)))
    for m in res.motifs_non_conformite:
        lignes.append(Text.assemble(("  ✗ ", theme.ERREUR), m))
    style = theme.OK if res.conforme else theme.ERREUR
    return Panel(Group(*lignes), title=Text(f"Verdict {res.identifiant} : {res.verdict}", style=style),
                 title_align="left", border_style=style, padding=(0, 1))


def rendre_bornes_tables(
    console: Console, res: ResultatBornesTables, *, lignes_max: int | None = LIGNES_MAX_TERMINAL, complet: bool = False
) -> None:
    """Le rapport sur ``console`` ; ``complet`` (journal) : tous les points en échec, les descriptions."""
    for s in (
        _en_tete(res), Text(""), *_identification(res), *_specification(res, complet),
        *_resultats(res), *_echecs(res, None if complet else lignes_max), _verdict(res),
    ):
        console.print(s)


def ecrire_journal_bornes(
    res: ResultatBornesTables, chemin: Path, *, pieces: Sequence[Path] = (), racine: Path | None = None
) -> Path:
    """Le journal complet du test des bornes."""
    entete = [
        f"Journal du test des bornes de table {res.identifiant} — "
        f"cfd-validation {res.environnement.versions.get('cfd-validation', '?')}",
        f"Écrit le {res.environnement.date} (UTC). Ce fichier est généré : ne pas l'éditer.",
    ]
    return ecrire_journal_rich(chemin, entete, lambda c: rendre_bornes_tables(c, res, complet=True),
                               pieces=pieces, racine=racine)
