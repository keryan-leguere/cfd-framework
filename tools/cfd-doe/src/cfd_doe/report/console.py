"""Rapport terminal de la réduction du domaine.

Lu de haut en bas :

1. **En-tête** : trajectoire et coefficients requis, géométrie et symétries,
   domaine d'entrée, repère retenu et pourquoi.
2. **Sous-domaines à calculer** : une ligne par sous-domaine, une colonne par
   variable libre quelque part. Une variable fixée à 0 partout n'a pas de
   colonne ; elle est citée une fois dans le titre. Les contraintes non
   cartésiennes (disque, secteur) sont des renvois ``a``, ``b`` détaillés sous
   le tableau, pour que le tableau tienne en 80 colonnes.
3. Notes, avertissements, et la ligne de synthèse.

Avec ``verbeux=True`` (``cfd-doe domaine --verbose``), la **démarche** s'insère
entre l'en-tête et le tableau : une étape par arbre, et chaque branche du
découpage se termine par le numéro du sous-domaine où elle aboutit (« → #3 »).
"""

from __future__ import annotations

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from cfd_doe.core.domaine_fondamental import Contrainte, Disque, Secteur
from cfd_doe.data.format import formater_intervalle, formater_nombre
from cfd_doe.data.variables import SYMBOLES, VARIABLES
from cfd_doe.engine.demarche import Noeud
from cfd_doe.engine.reduction import Reduction, SousDomaine
from cfd_doe.report import theme

__all__ = [
    "colonnes_utiles",
    "demarche",
    "libelle",
    "panneau_erreur",
    "panneau_etude",
    "rapport_reduction",
    "tableau_sous_domaines",
    "texte_contrainte",
]


def _symbole(variable: str) -> str:
    return SYMBOLES.get(variable, variable)


def texte_contrainte(c: Contrainte) -> str:
    """Une contrainte en clair."""
    x, y = _symbole(c.x), _symbole(c.y)
    if isinstance(c, Disque):
        return f"√({x}² + {y}²) ≤ {formater_nombre(c.rayon, 1)}°"
    assert isinstance(c, Secteur)
    if abs(c.angle_max - c.angle_min) < 1e-9:
        return f"({x}, {y}) sur la demi-droite à {formater_nombre(c.angle_min)}°, hors origine"
    g = "[" if c.min_inclus else "]"
    d = "]" if c.max_inclus else "["
    return (
        f"({x}, {y}) dans le secteur {g}{formater_nombre(c.angle_min)}° ; "
        f"{formater_nombre(c.angle_max)}°{d}, angle atan2({y}, {x})"
    )


def libelle(sd: SousDomaine) -> str:
    """Nom court d'un sous-domaine.

    En polaire, le nom de la strate (secteur, plan, axe). En cartésien, les
    variables que le sous-domaine fixe à 0 par symétrie : c'est ce qui le
    distingue des autres.
    """
    if sd.nom and sd.nom != "domaine":
        return sd.nom
    nulles = [_symbole(c.variable) for c in sd.chemin if c.texte == "= 0"]
    return "plan " + ", ".join(nulles) + " = 0" if nulles else "général"


# ---------------------------------------------------------------------------
# En-tête
# ---------------------------------------------------------------------------


def _domaine_entree(reduction: Reduction) -> Table:
    """Les cinq variables en colonnes : symbole au-dessus, plage dessous."""
    grille = Table.grid(padding=(0, 3))
    for _ in VARIABLES:
        grille.add_column(justify="center", no_wrap=True)
    grille.add_row(*(Text(SYMBOLES[v], style=theme.DISCRET) for v in VARIABLES))
    grille.add_row(
        *(
            Text(formater_intervalle(reduction.domaine_entree[v], espace=False), style=theme.VALEUR)
            if v in reduction.actives
            else Text("0", style=theme.DISCRET)
            for v in VARIABLES
        )
    )
    return grille


def panneau_etude(reduction: Reduction) -> Panel:
    """Ce qui a été demandé, et ce qui a été décidé."""
    etude = reduction.etude
    traj, geo = etude.trajectoire, etude.geometrie
    grille = Table.grid(padding=(0, 2))
    grille.add_column(no_wrap=True, style=theme.DISCRET)
    grille.add_column()

    grille.add_row(
        "Trajectoire",
        Text.assemble((traj.nom, theme.VALEUR), (f"  {traj.description}", theme.DISCRET)),
    )
    grille.add_row("Coefficients", Text("  ".join(traj.coefficients), style=theme.VALEUR))
    grille.add_row(
        "Géométrie",
        Text.assemble((geo.nom, theme.VALEUR), (f"  {geo.description}", theme.DISCRET)),
    )
    ordre = "∞" if reduction.ordre_groupe is None else str(reduction.ordre_groupe)
    grille.add_row(
        "Symétries",
        Text.assemble(
            (f"{reduction.groupe}, ordre {ordre}", theme.VALEUR),
            (
                f"  {', '.join(reduction.symetries_exploitees) or 'aucune exploitable'}",
                theme.DISCRET,
            ),
        ),
    )
    grille.add_row("Domaine (°)", _domaine_entree(reduction))

    if reduction.repere == "polaire":
        mixte = any(
            not sd.bornes[v].est_point for sd in reduction.sous_domaines for v in ("DMB", "DNB")
        )
        repere = "polaire (αt, φa)" + (", braquages en repère mixte" if mixte else "")
        if mixte:
            repere += ", limite en " + {"carre": "carré"}.get(
                etude.limite_braquage, etude.limite_braquage
            )
    else:
        repere = "cartésien (α, β), repère engin"
    grille.add_row(
        "Repère",
        Text.assemble((repere, theme.VALEUR), (f"\n{reduction.raison_repere}", theme.DISCRET)),
    )
    if etude.source is not None:
        grille.add_row("Fichier", Text(str(etude.source), style=theme.DISCRET))

    return Panel(
        grille,
        title=Text(f"cfd-doe · {etude.nom}", style=theme.TITRE),
        title_align="left",
        box=box.ROUNDED,
        border_style=theme.DISCRET,
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# Tableau des sous-domaines
# ---------------------------------------------------------------------------


def colonnes_utiles(reduction: Reduction) -> tuple[list[str], list[str]]:
    """Variables à afficher, et variables nulles dans tous les sous-domaines."""
    utiles: list[str] = []
    nulles: list[str] = []
    for v in reduction.variables:
        if all(sd.bornes[v].est_nul for sd in reduction.sous_domaines):
            nulles.append(v)
        else:
            utiles.append(v)
    return utiles, nulles


def _renvois(reduction: Reduction) -> dict[Contrainte, str]:
    lettres: dict[Contrainte, str] = {}
    for sd in reduction.sous_domaines:
        for c in sd.contraintes:
            if c not in lettres:
                lettres[c] = "abcdefghijklmnopqrstuvwxyz"[len(lettres) % 26]
    return lettres


def tableau_sous_domaines(reduction: Reduction) -> Table:
    """Le résultat : un sous-domaine par ligne."""
    utiles, _ = colonnes_utiles(reduction)
    renvois = _renvois(reduction)
    titre = Text(f"Sous-domaines à calculer ({len(reduction.sous_domaines)})", style=theme.TITRE)
    table = Table(
        title=titre,
        title_justify="left",
        box=box.SIMPLE_HEAD,
        header_style=theme.ENTETE,
        pad_edge=False,
        # Marge à droite seulement : le séparateur de colonne fait déjà un blanc.
        padding=(0, 1, 0, 0),
    )
    table.add_column("#", justify="right", style=theme.DISCRET)
    table.add_column("sous-domaine", no_wrap=True)
    for v in utiles:
        table.add_column(SYMBOLES[v], justify="center", no_wrap=True)
    if renvois:
        table.add_column("c.", style=theme.DISCRET, no_wrap=True)
    table.add_column("dim", justify="right", style=theme.DISCRET)

    for sd in reduction.sous_domaines:
        cellules: list[RenderableType] = [str(sd.numero), Text(libelle(sd), style=theme.VALEUR)]
        for v in utiles:
            i = sd.bornes[v]
            cellules.append(
                Text(
                    formater_intervalle(i, espace=False),
                    style=theme.FIXE if i.est_point else theme.VALEUR,
                )
            )
        if renvois:
            cellules.append(" ".join(renvois[c] for c in sd.contraintes))
        cellules.append(str(sd.dimension))
        table.add_row(*cellules)
    return table


def _puces(lignes: list[tuple[str, str, str]]) -> Table:
    """Liste à puces dont les lignes repliées gardent leur retrait."""
    grille = Table.grid(padding=(0, 1))
    grille.add_column(no_wrap=True, justify="right", min_width=3)
    grille.add_column()
    for puce, texte, style in lignes:
        grille.add_row(Text(puce, style=style), Text(texte, style=style))
    return grille


#: Ce que désignent les noms courts de la colonne « sous-domaine ».
_NATURES = {
    "secteur": "secteur : intérieur du secteur fondamental en φa",
    "plan": "plan : plan de symétrie φa = φs, braquages réduits par le miroir",
    "axe": "axe : αt = 0, les symétries n'agissent plus que sur les braquages",
    "axisymétrique": "axisymétrique : corps de révolution, seul αt compte",
}


def _legende(reduction: Reduction) -> Table:
    lignes = [
        (lettre, texte_contrainte(c), theme.DISCRET) for c, lettre in _renvois(reduction).items()
    ]
    natures = {sd.nom for sd in reduction.sous_domaines}
    lignes += [("", texte, theme.DISCRET) for nom, texte in _NATURES.items() if nom in natures]
    _, nulles = colonnes_utiles(reduction)
    if nulles:
        lignes.append(
            (
                "",
                ", ".join(SYMBOLES[v] for v in nulles) + " = 0 dans tous les sous-domaines",
                theme.DISCRET,
            )
        )
    lignes.append(
        (
            "",
            "degrés · ]0;20] : 0 exclu · valeur seule : variable fixée · dim : variables libres",
            theme.DISCRET,
        )
    )
    return _puces(lignes)


def _messages(reduction: Reduction) -> Table:
    return _puces(
        [("·", n, theme.DISCRET) for n in reduction.notes]
        + [("!", a, theme.ATTENTION) for a in reduction.avertissements]
    )


def _synthese(reduction: Reduction) -> Text:
    n = len(reduction.sous_domaines)
    ordre = reduction.ordre_groupe
    texte = Text.assemble(
        (f"{n} sous-domaine{'s' if n > 1 else ''}", theme.ACCENT),
        (" à couvrir", theme.DISCRET),
    )
    if ordre is None:
        texte.append(" · révolution : φa éliminé, seul αt compte", style=theme.DISCRET)
    elif ordre > 1:
        texte.append(" · domaine divisé par ", style=theme.DISCRET)
        texte.append(str(ordre), style=theme.ACCENT)
        texte.append(f" ({reduction.groupe})", style=theme.DISCRET)
    else:
        texte.append(" · aucune symétrie exploitable", style=theme.DISCRET)
    return texte


# ---------------------------------------------------------------------------
# Démarche (--verbose)
# ---------------------------------------------------------------------------


def _ligne(noeud: Noeud) -> RenderableType:
    """Le texte du nœud ; une feuille garde son « → #k » d'un seul tenant, en bout de ligne."""
    if noeud.numero is None:
        return Text(noeud.texte)
    grille = Table.grid(padding=(0, 0, 0, 2))
    grille.add_column()
    grille.add_column(no_wrap=True, vertical="bottom")
    grille.add_row(Text(noeud.texte), Text(f"→ #{noeud.numero}", style=theme.ACCENT))
    return grille


def _greffer(arbre: Tree, noeud: Noeud) -> None:
    branche = arbre.add(_ligne(noeud))
    for enfant in noeud.enfants:
        _greffer(branche, enfant)


def demarche(reduction: Reduction) -> Group:
    """Comment les sous-domaines ont été obtenus : une étape numérotée par arbre."""
    morceaux: list[RenderableType] = [Text("Démarche", style=theme.TITRE)]
    for i, etape in enumerate(reduction.demarche, start=1):
        arbre = Tree(
            Text(f"{i}. {etape.titre}", style=theme.ENTETE),
            guide_style=theme.DISCRET,
        )
        for noeud in etape.noeuds:
            _greffer(arbre, noeud)
        morceaux.append(arbre)
    return Group(*morceaux)


def rapport_reduction(reduction: Reduction, *, verbeux: bool = False) -> Group:
    """Le rapport complet, prêt pour ``Console.print`` ; ``verbeux`` ajoute la démarche."""
    morceaux: list[RenderableType] = [panneau_etude(reduction), Text()]
    if verbeux:
        morceaux += [demarche(reduction), Text()]
    morceaux += [
        tableau_sous_domaines(reduction),
        _legende(reduction),
    ]
    if reduction.notes or reduction.avertissements:
        morceaux += [Text(), _messages(reduction)]
    morceaux += [Text(), _synthese(reduction)]
    return Group(*morceaux)


def panneau_erreur(message: str, *, indice: str = "") -> Panel:
    """Erreur d'entrée : un panneau rouge, jamais une trace d'appels."""
    contenu = Text(message, style=theme.ERREUR)
    if indice:
        contenu.append(f"\n{indice}", style=theme.DISCRET)
    return Panel(
        contenu,
        title=Text("cfd-doe · erreur", style=theme.ERREUR),
        title_align="left",
        border_style=theme.ERREUR,
        box=box.ROUNDED,
    )
