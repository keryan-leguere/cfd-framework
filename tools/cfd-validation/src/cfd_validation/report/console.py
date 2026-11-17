"""Rapport du test d'intégration, en Rich : le même rendu pour le terminal et pour le journal.

Le terminal montre l'essentiel — les lignes en échec seulement, plafonnées ;
le journal (``complet=True``) montre **tout** : chaque ligne, chaque niveau de
chaque entrée, la liaison entrée × sortie. Les deux sortent de ces mêmes
fonctions, si bien qu'ils ne peuvent pas se contredire.

Ordre des sections, celui d'un compte rendu d'essai (IEEE 29119-3) :
identification, spécification, structure, résultats par sortie, attribution,
lignes, avertissements, verdict.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from rich import box
from rich.console import Console, Group, RenderableType
from rich.padding import Padding
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from cfd_validation.core import statuts as st
from cfd_validation.core.format import formater, pourcentage
from cfd_validation.core.tolerance import ORIGINE_DEFAUT
from cfd_validation.data.specification import ALIGNEMENT_ENTREES
from cfd_validation.engine.integration import AttributionEntree, ResultatIntegration
from cfd_validation.report import theme

__all__ = [
    "ENTREES_CITEES_TERMINAL",
    "LIGNES_MAX_TERMINAL",
    "largeur_journal",
    "panneau_erreur",
    "rendre_fichiers",
    "rendre_integration",
    "seuils_lecture_v",
]

#: Lignes en échec listées au terminal (le journal les liste toutes).
LIGNES_MAX_TERMINAL = 25

#: Lecture du V de Cramér (Cohen, tableau 2 × k) : seuils et libellés.
_LECTURE_V = ((0.5, "forte", theme.ERREUR), (0.3, "marquée", theme.ATTENTION), (0.1, "faible", theme.DISCRET))

_STYLE_STATUT = {
    st.IDENTIQUE: theme.OK,
    st.TOLERE: theme.OK,
    st.ECART: theme.ERREUR,
    st.NON_FINI: theme.ERREUR,
    st.ENTREES_DIVERGENTES: theme.ERREUR,
    st.ABSENTE: theme.ERREUR,
    st.EN_TROP: theme.ATTENTION,
}


def seuils_lecture_v() -> tuple[tuple[float, str], ...]:
    """Les seuils de lecture du V de Cramér, pour la documentation et les figures."""
    return tuple((s, nom) for s, nom, _ in _LECTURE_V)


# ---------------------------------------------------------------------------
# Briques
# ---------------------------------------------------------------------------


def _titre(texte: str) -> Rule:
    return Rule(Text(texte, style=theme.TITRE), align="left", style=theme.DISCRET)


def _table(
    *colonnes: str,
    droite: Iterable[int] = (),
    titre: str | None = None,
    insecables: Iterable[int] = (),
) -> Table:
    t = Table(
        box=box.SIMPLE_HEAD,
        header_style=theme.ENTETE,
        title=titre,
        title_style=theme.DISCRET,
        title_justify="left",
        pad_edge=False,
        show_edge=False,
        collapse_padding=True,  # deux espaces entre colonnes : la table ligne à ligne tient en 80
    )
    droite, insecables = set(droite), set(insecables)
    for i, c in enumerate(colonnes):
        t.add_column(
            c,
            justify="right" if i in droite else "left",
            overflow="fold",
            no_wrap=i in insecables,
            min_width=len(c) if i in insecables else None,
        )
    return t


def _grille() -> Table:
    g = Table.grid(padding=(0, 2))
    g.add_column(style=theme.DISCRET, no_wrap=True)
    g.add_column(overflow="fold")
    return g


def _statut(code: int, *, court: bool = False) -> Text:
    libelles = st.LIBELLES_COURTS if court else st.LIBELLES
    return Text(libelles[code], style=_STYLE_STATUT[code])


def _valeur(x: Any, chiffres: int = 6) -> str:
    if isinstance(x, (np.generic,)):
        x = x.item()
    if x is None or x is pd.NA:
        return "—"
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return formater(x, chiffres)
    return str(x)


def _marge(m: float) -> Text:
    if m is None or (isinstance(m, float) and math.isnan(m)):
        return Text("—", style=theme.DISCRET)
    style = theme.ERREUR if abs(m) > 1 else theme.OK
    return Text(formater(m), style=style)


def _compte(n: int, total: int, style_si_non_nul: str | None = None) -> Text:
    texte = f"{n}" if n == 0 or n == total else f"{n} ({pourcentage(n, total)})"
    if n == total and total:
        texte = f"{n} (100 %)"
    return Text(texte, style=style_si_non_nul if (n and style_si_non_nul) else "")


#: Entrées d'un point citées au terminal ; le journal les cite toutes.
ENTREES_CITEES_TERMINAL = 3


def _entrees_texte(entrees: dict[str, Any], ordre: Sequence[str], nombre: int | None) -> str:
    """Les ``nombre`` entrées les plus pertinentes (toutes si None), les plus liées aux échecs d'abord.

    Au terminal, une par ligne : ``braquage_profondeur=20`` ne se coupe pas au
    milieu ; au journal (toutes), sur une ligne, que sa largeur loge.
    """
    noms = [n for n in ordre if n in entrees]
    montres = noms if nombre is None else noms[:nombre]
    separateur = "  " if nombre is None else "\n"
    texte = separateur.join(f"{k}={_valeur(entrees[k])}" for k in montres)
    return texte + (separateur + "…" if len(montres) < len(noms) else "")


def _lecture_v(v: float) -> Text:
    if math.isnan(v):
        return Text("sans objet", style=theme.DISCRET)
    for seuil, nom, style in _LECTURE_V:
        if v >= seuil:
            return Text(f"liaison {nom}", style=style)
    return Text("pas de liaison", style=theme.DISCRET)


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def _en_tete(res: ResultatIntegration) -> Panel:
    style = theme.OK if res.conforme else theme.ERREUR
    corps = Group(
        Text(res.description),
        Text(""),
        Text.assemble(("Verdict : ", theme.DISCRET), (res.verdict, style)),
    )
    return Panel(
        corps,
        title=Text(f"Test d'intégration {res.identifiant}", style=theme.TITRE),
        title_align="left",
        border_style=style,
        padding=(0, 1),
    )


def _identification(res: ResultatIntegration) -> list[RenderableType]:
    env = res.environnement
    g = _grille()
    g.add_row("Date (UTC)", env.date)
    g.add_row("Hôte", f"{env.hote} — {env.utilisateur}")
    g.add_row("Système", env.systeme)
    g.add_row("Python", env.python)
    g.add_row("Outils", ", ".join(f"{k} {v}" for k, v in env.versions.items()))
    for nom, e in (("Référence", res.empreinte_ref), ("Test", res.empreinte_test)):
        g.add_row(nom, f"{e.n_lignes} lignes × {e.n_colonnes} colonnes · sha256 {e.courte}…")
    for k, v in res.metadonnees.items():
        g.add_row(k, v)
    return [_titre("1. Identification"), Padding(g, (0, 0, 1, 2))]


def _specification(res: ResultatIntegration, complet: bool) -> list[RenderableType]:
    spec = res.specification
    g = _grille()
    g.add_row("Entrées", ", ".join(spec.entrees) if spec.entrees else Text("aucune", style=theme.ATTENTION))
    g.add_row("Sorties", ", ".join(spec.sorties))
    if spec.alignement == ALIGNEMENT_ENTREES:
        appariement = "sur la valeur des entrées"
        if spec.chiffres_cle:
            appariement += f", arrondies à {spec.chiffres_cle} chiffres significatifs"
    elif spec.entrees:
        appariement = "par position, entrées vérifiées ligne à ligne"
    else:
        appariement = "par position (la i-ème ligne contre la i-ème), rien à vérifier"
    g.add_row("Appariement", appariement)
    if spec.renommage_test:
        g.add_row("Renommage du test", ", ".join(f"{a} → {b}" for a, b in spec.renommage_test.items()))
    g.add_row("Critère", "|test − réf| ≤ atol + rtol·|réf| ; deux NaN sont identiques")

    numerique = {b.nom: b.numerique for b in res.sorties}
    t = _table("Sortie", "Critère", "Origine", "Justification", insecables=(0, 1))
    for nom in spec.sorties:
        tol = spec.tolerance(nom)
        if not numerique.get(nom, True):
            t.add_row(nom, "égalité stricte", Text("non numérique", style=theme.DISCRET), Text("—", style=theme.DISCRET))
            continue
        if tol.origine == ORIGINE_DEFAUT:
            origine = Text("défaut", style=theme.ATTENTION)
        else:
            origine = Text("déclarée")
        justif = Text(tol.justification) if tol.justification else Text("non justifiée", style=theme.ATTENTION)
        t.add_row(nom, tol.decrire(), origine, justif)
    return [_titre("2. Spécification"), Padding(Group(g, Text(""), t), (0, 0, 1, 2))]


def _structure(res: ResultatIntegration) -> list[RenderableType]:
    s = res.structure
    g = _grille()
    g.add_row("Lignes", f"{s.n_ref} en référence, {s.n_test} en test")
    g.add_row("Appariées", f"{s.n_appariees} ({pourcentage(s.n_appariees, s.n_ref)} de la référence)")
    g.add_row("Comparées", str(s.n_comparees))

    def ligne(libelle: str, n: int, grave: bool = True) -> None:
        style = (theme.ERREUR if grave else theme.ATTENTION) if n else theme.OK
        g.add_row(libelle, Text(str(n), style=style))

    ligne("Absentes du test", s.n_absentes)
    ligne("En trop dans le test", s.n_en_trop)
    if res.specification.alignement != ALIGNEMENT_ENTREES and res.specification.entrees:
        ligne("Entrées divergentes", s.n_divergentes)
    if res.specification.alignement == ALIGNEMENT_ENTREES:
        g.add_row("Ordre des lignes", "identique" if s.meme_ordre else "différent (sans conséquence : appariement sur les entrées)")
    if s.sorties_absentes:
        g.add_row("Sorties absentes du test", Text(", ".join(s.sorties_absentes), style=theme.ERREUR))
    if s.ignorees_ref:
        g.add_row("Non déclarées (réf.)", Text(", ".join(s.ignorees_ref), style=theme.DISCRET))
    if s.ignorees_test:
        g.add_row("Non déclarées (test)", Text(", ".join(s.ignorees_test), style=theme.DISCRET))
    return [_titre("3. Structure"), Padding(g, (0, 0, 1, 2))]


def _bilan_sorties(res: ResultatIntegration, complet: bool) -> list[RenderableType]:
    comptes = _table(
        "Sortie", "Identiques", "Tolérées", "Hors tol.", "Non finis", "Statut",
        droite=range(1, 5), insecables=range(0, 6),
        titre=f"Comptes, sur {res.structure.n_comparees} lignes comparées",
    )
    ampl = _table("Sortie", "max |Δ|", "max |Δ|/|réf|", "max ULP", "biais", "RMS", "marge max", droite=range(1, 7), titre="Amplitudes (marge = |Δ| / tolérance ; conforme si ≤ 1)")
    avec_entrees = bool(res.specification.entrees)
    pires = _table(
        "Sortie", "Ligne", "Référence", "Test", "Marge", *(("Entrées",) if avec_entrees else ()),
        droite=(1, 2, 3, 4), insecables=(0, 1, 2, 3, 4),
        titre=(
            "Point le plus éloigné de la référence, par sortie"
            if complet
            else "Point le plus éloigné de la référence, sorties en échec (toutes au journal)"
        ),
    )
    n_cites = None if complet else ENTREES_CITEES_TERMINAL
    for b in res.sorties:
        if not b.presente:
            comptes.add_row(b.nom, "—", "—", "—", "—", _statut(st.ABSENTE, court=True))
            continue
        comptes.add_row(
            b.nom,
            _compte(b.n_identiques, b.n),
            _compte(b.n_toleres, b.n),
            _compte(b.n_ecarts, b.n, theme.ERREUR),
            _compte(b.n_non_finis, b.n, theme.ERREUR),
            _statut(b.statut, court=True),
        )
        if b.numerique:
            ampl.add_row(
                b.nom,
                formater(b.max_abs),
                formater(b.max_rel),
                formater(b.max_ulp),
                formater(b.biais),
                formater(b.rms),
                _marge(b.marge_max),
            )
        else:
            ampl.add_row(b.nom, Text("—", style=theme.DISCRET), "", "", "", "", Text("exacte", style=theme.DISCRET))
        a_montrer = b.n_echecs > 0 if not complet else b.statut != st.IDENTIQUE
        if b.pire is not None and a_montrer:
            pires.add_row(
                b.nom,
                str(b.pire.ligne_ref),
                _valeur(b.pire.reference, 10),
                _valeur(b.pire.test, 10),
                _marge(b.pire.marge) if b.numerique else _statut(b.pire.statut, court=True),
                *(
                    (_entrees_texte(dict(b.pire.entrees), res.entrees_par_pertinence(b.nom), n_cites),)
                    if avec_entrees
                    else ()
                ),
            )
    blocs: list[RenderableType] = [comptes, Text(""), ampl]
    if pires.row_count:
        blocs += [Text(""), pires]
    return [_titre("4. Résultats par sortie"), Padding(Group(*blocs), (0, 0, 1, 2))]


def _attribution(res: ResultatIntegration, complet: bool) -> list[RenderableType]:
    titre = _titre("5. Attribution des échecs aux entrées")
    taux = res.taux_echec
    n_echec = res.n_lignes_echec
    if n_echec == 0:
        return [titre, Padding(Text("Aucune ligne en échec : rien à attribuer.", style=theme.DISCRET), (0, 0, 1, 2))]
    if not res.attributions:
        return [
            titre,
            Padding(
                Text(
                    f"{n_echec} ligne(s) de référence en échec sur {res.structure.n_ref} "
                    f"({pourcentage(n_echec, res.structure.n_ref)}), absentes du test comprises. "
                    "Aucune entrée déclarée : rien à quoi attribuer les échecs — leurs rangs sont en section 6.",
                ),
                (0, 0, 1, 2),
            ),
        ]

    ordre = sorted(res.attributions, key=lambda a: (math.isnan(a.v), -(a.v if not math.isnan(a.v) else 0)))
    t = _table(
        "Entrée", "Niveaux", "V", "Lecture", "Niveaux en cause (taux d'échec)",
        droite=(1, 2), insecables=(0, 1, 2, 3),
    )
    for a in ordre:
        # Sous le seuil d'une liaison faible, les « pires niveaux » ne sont que du bruit
        # d'échantillonnage : les citer ferait chercher une cause là où il n'y en a pas.
        lie = not math.isnan(a.v) and a.v >= _LECTURE_V[-1][0]
        en_cause = a.niveaux_en_cause(taux) if lie else []
        t.add_row(
            a.entree,
            f"{len(a.niveaux)}{' cl.' if a.en_classes else ''}",
            formater(a.v, 2),
            _lecture_v(a.v),
            ", ".join(f"{n.libelle} ({pourcentage(n.n_echecs, n.n)})" for n in en_cause) or "—",
        )
    blocs: list[RenderableType] = [
        Text(
            f"{n_echec} ligne(s) de référence en échec sur {res.structure.n_ref} "
            f"({pourcentage(n_echec, res.structure.n_ref)}), absentes du test comprises.",
        ),
        Text(""),
        t,
        Text("V : V de Cramér, liaison entre le niveau de l'entrée et l'échec de la ligne (0 : aucune, 1 : totale) ; "
             "cl. : classes de quantiles d'une entrée continue.", style=theme.DISCRET),
        Text(""),
        _diagnostic(ordre, taux),
    ]
    if complet:
        for a in ordre:
            blocs += [Text(""), _table_niveaux(a)]
        blocs += [Text(""), _table_v_par_sortie(res, ordre)]
    return [titre, Padding(Group(*blocs), (0, 0, 1, 2))]


def _diagnostic(ordre: Sequence[AttributionEntree], taux: float) -> Text:
    tete = ordre[0] if ordre else None
    if tete is None or math.isnan(tete.v) or tete.v < 0.3:
        return Text(
            "Lecture : les échecs ne se concentrent sur aucune entrée — écart diffus "
            "(environnement, précision, convention) plutôt qu'une branche du code.",
            style=theme.DISCRET,
        )
    en_cause = tete.niveaux_en_cause(taux, nombre=len(tete.niveaux))
    en_cause.sort(key=tete.niveaux.index)  # dans l'ordre des niveaux (Mach croissant), pas des taux
    n_dans = sum(n.n for n in en_cause)
    e_dans = sum(n.n_echecs for n in en_cause)
    autres = [n for n in tete.niveaux if n not in en_cause]
    n_hors = sum(n.n for n in autres)
    e_hors = sum(n.n_echecs for n in autres)
    libelles = ", ".join(n.libelle for n in en_cause)
    return Text.assemble(
        ("Lecture : ", theme.DISCRET),
        "les échecs se concentrent sur ",
        (f"{tete.entree} ∈ {{{libelles}}}", theme.ACCENT),
        f" — {pourcentage(e_dans, n_dans)} des lignes y échouent, "
        f"contre {pourcentage(e_hors, n_hors)} ailleurs.",
    )


def _table_niveaux(a: AttributionEntree) -> Table:
    t = _table(
        "Niveau", "Lignes", "Échecs", "dont absentes", "Taux", "Marge max",
        droite=range(1, 6),
        titre=f"{a.entree} — V = {formater(a.v, 2)}{' (classes de quantiles)' if a.en_classes else ''}",
    )
    for n in a.niveaux:
        style = theme.ERREUR if n.n_echecs else ""
        t.add_row(n.libelle, str(n.n), Text(str(n.n_echecs), style=style), str(n.n_absentes), pourcentage(n.n_echecs, n.n), _marge(n.marge_max))
    return t


def _table_v_par_sortie(res: ResultatIntegration, ordre: Sequence[AttributionEntree]) -> Table:
    presentes = [b.nom for b in res.sorties if b.presente]
    t = _table("Entrée", *presentes, droite=range(1, len(presentes) + 1), titre="V de Cramér entrée × sortie")
    for a in ordre:
        t.add_row(a.entree, *(formater(a.v_par_sortie.get(s, math.nan), 2) for s in presentes))
    return t


#: Indentation des sections et écart entre colonnes (``collapse_padding``).
_RETRAIT, _ECART = 2, 2


def _largeur_texte(entete: str, valeurs: Iterable[str]) -> int:
    return max([len(entete), *(len(v) for v in valeurs)])


def _colonnes_fixes(res: ResultatIntegration, df: pd.DataFrame, complet: bool) -> list[int]:
    """Largeur des colonnes de la table ligne à ligne qui ne sont pas des entrées."""
    sorties = [b.nom for b in res.sorties]
    rang_max = str(max(res.structure.n_ref, res.structure.n_test))  # pas len(df) : df est l'extrait affiché
    largeurs = [
        _largeur_texte("Réf.", [rang_max]),
        _largeur_texte("Test", [rang_max]),
        max(len(x) for x in (st.LIBELLES_COURTS.values())),
        _largeur_texte("Sortie", sorties),
        len("-2.00e+05"),
    ]
    if complet:
        largeurs += [len("|Δ|/|réf|"), len("1.00e+13")]
    return largeurs


def _largeur_entree(df: pd.DataFrame, nom: str) -> int:
    return _largeur_texte(nom, (_valeur(v) for v in pd.unique(df[nom])))


def _choisir_entrees(res: ResultatIntegration, df: pd.DataFrame, largeur: int, complet: bool) -> list[str]:
    """Les entrées qui tiennent dans ``largeur`` colonnes, les plus liées aux échecs d'abord.

    Rendues dans l'ordre de déclaration ; le journal (``complet``) les prend toutes.
    """
    declarees = list(res.specification.entrees)
    if complet:
        return declarees
    fixes = _colonnes_fixes(res, df, complet)
    occupe = _RETRAIT + sum(fixes) + _ECART * (len(fixes) - 1)
    gardees: set[str] = set()
    for nom in res.entrees_par_pertinence():
        besoin = _largeur_entree(df, nom) + _ECART
        if occupe + besoin <= largeur:
            gardees.add(nom)
            occupe += besoin
    return [n for n in declarees if n in gardees]


def largeur_journal(res: ResultatIntegration, *, minimum: int = 160, maximum: int = 1000) -> int:
    """Largeur qui loge **toutes** les colonnes du journal sans rien rogner ni replier.

    La table ligne à ligne y montre chaque entrée, et la liaison entrée × sortie
    chaque sortie : avec 10 entrées et 15 sorties, 160 colonnes ne suffisent plus.
    """
    df = res.lignes
    fixes = _colonnes_fixes(res, df, complet=True)
    entrees = [_largeur_entree(df, n) for n in res.specification.entrees]
    lignes = _RETRAIT + sum(fixes) + sum(entrees) + _ECART * (len(fixes) + len(entrees) - 1)
    liaison = _RETRAIT + max((len(n) for n in res.specification.entrees), default=0) + sum(
        max(len(b.nom), 4) + _ECART for b in res.sorties if b.presente
    )
    return max(minimum, min(maximum, max(lignes, liaison) + 2))


def _lignes(res: ResultatIntegration, lignes_max: int | None, complet: bool, largeur: int) -> list[RenderableType]:
    titre = _titre("6. Lignes")
    df = res.lignes

    repartition = _table("Statut", "Lignes", "Part", droite=(1, 2), insecables=(0,), titre="Statut des lignes")
    total = len(df)
    comptes = df["code"].value_counts().sort_index()
    for code, n in zip(comptes.index.to_numpy(dtype=np.int64), comptes.to_numpy(dtype=np.int64)):
        repartition.add_row(_statut(int(code)), str(n), pourcentage(int(n), total))

    if complet:
        choisies = df
        legende = "Toutes les lignes, dans l'ordre de la référence (lignes en trop du test à la fin)"
    else:
        echec = df[df["code"] >= st.ECART]
        cle = echec["marge_max"].fillna(np.inf)
        choisies = echec.assign(_cle=cle).sort_values(["code", "_cle"], ascending=False, kind="stable")
        if lignes_max is not None:
            choisies = choisies.head(lignes_max)
        legende = "Lignes en échec, les plus graves d'abord"
    entrees = _choisir_entrees(res, choisies, largeur, complet)
    masquees = [n for n in res.specification.entrees if n not in entrees]

    # Au terminal, la marge suffit à trier ; écart relatif et ULP sont au journal et dans lignes.csv.
    k = len(entrees)
    colonnes = ["Réf.", "Test", *entrees, "Statut", "Sortie", "Marge"]
    if complet:
        colonnes += ["|Δ|/|réf|", "ULP"]
    t = _table(
        *colonnes,
        droite=(0, 1, *range(2, 2 + k), *range(k + 4, len(colonnes))),
        insecables=range(len(colonnes)),
        titre=legende,
    )
    for d in choisies.to_dict("records"):
        cellules: list[Any] = [
            _valeur(d["ligne_ref"]),
            _valeur(d["ligne_test"]),
            *(_valeur(d[c]) for c in entrees),
            _statut(int(d["code"]), court=True),
            str(d["sortie_pire"] or "—"),
            _marge(d["marge_max"]),
        ]
        if complet:
            cellules += [formater(d["ecart_rel_max"]), formater(d["ulp_max"])]
        t.add_row(*cellules)
    blocs: list[RenderableType] = [repartition, Text("")]
    if choisies.empty:
        blocs.append(Text("Aucune ligne en échec.", style=theme.OK))
    else:
        blocs += [
            t,
            Text(
                "Réf., Test : rang de la ligne dans chaque table (0, 1…) ; Sortie : la plus en écart ; "
                "Marge : sa plus grande |Δ| / tolérance (inf : non fini).",
                style=theme.DISCRET,
            ),
        ]
        if masquees:
            blocs.append(
                Text(
                    f"Entrées non affichées faute de place (les moins liées aux échecs) : {', '.join(masquees)}"
                    " — toutes au journal et dans lignes.csv.",
                    style=theme.ATTENTION,
                )
            )
        if not complet:
            reste = int((df["code"] >= st.ECART).sum()) - len(choisies)
            if reste > 0:
                blocs.append(Text(f"… et {reste} autre(s) ligne(s) en échec : voir le journal et lignes.csv.", style=theme.DISCRET))
    return [titre, Padding(Group(*blocs), (0, 0, 1, 2))]


def _avertissements(res: ResultatIntegration) -> list[RenderableType]:
    if not res.avertissements:
        return []
    corps = Group(*(Text.assemble(("• ", theme.ATTENTION), a) for a in res.avertissements))
    return [_titre("7. Avertissements"), Padding(corps, (0, 0, 1, 2))]


def _verdict(res: ResultatIntegration) -> Panel:
    n_valeurs = sum(b.n for b in res.sorties if b.presente)
    n_ident = sum(b.n_identiques for b in res.sorties if b.presente)
    n_tol = sum(b.n_toleres for b in res.sorties if b.presente)
    n_ech = sum(b.n_echecs for b in res.sorties if b.presente)
    lignes: list[RenderableType] = [
        Text(
            f"{res.structure.n_comparees} lignes × {sum(b.presente for b in res.sorties)} sorties = {n_valeurs} valeurs : "
            f"{n_ident} identiques ({pourcentage(n_ident, n_valeurs)}), {n_tol} dans la tolérance, {n_ech} en échec."
        )
    ]
    for m in res.motifs_non_conformite:
        lignes.append(Text.assemble(("• ", theme.ERREUR), m))
    style = theme.OK if res.conforme else theme.ERREUR
    return Panel(
        Group(*lignes),
        title=Text(f"Verdict {res.identifiant} : {res.verdict}", style=style),
        title_align="left",
        border_style=style,
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# Points d'entrée
# ---------------------------------------------------------------------------


def rendre_integration(
    console: Console,
    res: ResultatIntegration,
    *,
    lignes_max: int | None = LIGNES_MAX_TERMINAL,
    complet: bool = False,
) -> None:
    """Écrit le rapport sur ``console``.

    ``complet=False`` (terminal) : lignes en échec seulement, ``lignes_max`` au
    plus. ``complet=True`` (journal) : toutes les lignes, le détail de chaque
    entrée et la liaison entrée × sortie.
    """
    sections: list[RenderableType] = [
        _en_tete(res),
        Text(""),
        *_identification(res),
        *_specification(res, complet),
        *_structure(res),
        *_bilan_sorties(res, complet),
        *_attribution(res, complet),
        *_lignes(res, lignes_max, complet, console.width),
        *_avertissements(res),
        _verdict(res),
    ]
    for s in sections:
        console.print(s)


def rendre_fichiers(console: Console, fichiers: Sequence[Path], *, racine: Path | None = None) -> None:
    """La liste des pièces écrites, avec leur taille."""
    t = _table("Pièce", "Taille", droite=(1,), titre="Pièces produites")
    for f in fichiers:
        nom = str(f.relative_to(racine)) if racine is not None and f.is_relative_to(racine) else str(f)
        taille = f.stat().st_size if f.exists() else 0
        t.add_row(nom, _taille(taille))
    console.print(Padding(t, (1, 0, 0, 2)))


def _taille(octets: int) -> str:
    for unite in ("o", "ko", "Mo", "Go"):
        if octets < 1024 or unite == "Go":
            return f"{octets:.0f} {unite}" if unite == "o" else f"{octets:.1f} {unite}"
        octets /= 1024  # type: ignore[assignment]
    return f"{octets} o"


def panneau_erreur(message: str, *, indice: str = "") -> Panel:
    """Une erreur d'entrée, et la piste pour la corriger."""
    corps = Text(message)
    if indice:
        corps.append("\n\n" + indice, style=theme.DISCRET)
    return Panel(corps, title=Text("Erreur", style=theme.ERREUR), title_align="left", border_style=theme.ERREUR)
