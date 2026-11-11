"""De l'étude aux sous-domaines à calculer.

Trois étapes, dans l'ordre du document (00_DOC/01_BASE_AERO.md) :

1. **Trajectoire** : les variables que le simulateur ne consomme pas sont
   fixées à 0.
2. **Repère** : cartésien (α, β) en repère engin, ou polaire (αt, φa) avec des
   braquages en repère mixte (§5.4).
3. **Symétries** : le domaine est réduit à un domaine fondamental, découpé en
   sous-domaines disjoints (§4, §7).

Le résultat, :class:`Reduction`, ne contient aucun texte formaté : c'est ce que
la couche ``report`` affiche et ce qu'une phase de remplissage lira (voir
:func:`vers_dict`). Il porte aussi sa **démarche** (:mod:`cfd_doe.engine.demarche`),
rédigée au fil des étapes : ce que ``cfd-doe domaine --verbose`` affiche.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cfd_doe.core.angles import arc_phia_rectangle, normaliser_angle, plage_alphat_rectangle
from cfd_doe.core.domaine_fondamental import (
    Condition,
    Contrainte,
    Disque,
    Evenement,
    Recollement,
    Secteur,
    Strate,
    fusionner,
    replier_arc,
    strates_diedrales_plan,
    stratifier_signes,
)
from cfd_doe.core.intervalle import TOLERANCE, Intervalle
from cfd_doe.core.symetrie import ElementSigne, engendrer, restreindre
from cfd_doe.data.etude import ErreurEtude, Etude
from cfd_doe.data.format import formater_intervalle as _fi
from cfd_doe.data.format import formater_nombre as _fn
from cfd_doe.data.geometries import (
    COEFFICIENTS_HORS_PAV,
    MIROIR_PLAN_POLAIRE,
    Geometrie,
    coefficients_retournes,
)
from cfd_doe.data.trajectoires import EFFORTS, PILOTES
from cfd_doe.data.variables import (
    BRAQUAGES,
    VARIABLES,
    VARIABLES_CARTESIENNES,
    VARIABLES_POLAIRES,
)
from cfd_doe.engine.demarche import (
    Brouillon,
    Etape,
    Redaction,
    arbre_signes,
    borne,
    decrire_element,
    numeroteur,
    symbole,
)

__all__ = ["Reduction", "SousDomaine", "reduire", "symetries_exportees", "vers_dict"]


@dataclass(frozen=True)
class SousDomaine:
    """Un sous-domaine à couvrir : produit d'intervalles, plus d'éventuelles contraintes."""

    numero: int
    nom: str
    bornes: dict[str, Intervalle]
    contraintes: tuple[Contrainte, ...]
    chemin: tuple[Condition, ...]

    @property
    def dimension(self) -> int:
        """Nombre de variables libres."""
        return Strate(self.bornes, self.contraintes).dimension

    def contient(self, point: Mapping[str, float], tol: float = TOLERANCE) -> bool:
        """Appartenance d'un point exprimé dans les variables du repère de travail."""
        return Strate(self.bornes, self.contraintes).contient(point, tol)


@dataclass(frozen=True)
class Reduction:
    """Le résultat de la réduction."""

    etude: Etude
    repere: str
    raison_repere: str
    variables: tuple[str, ...]
    domaine_entree: dict[str, Intervalle]
    actives: tuple[str, ...]
    sous_domaines: tuple[SousDomaine, ...]
    groupe: str
    ordre_groupe: int | None
    symetries_exploitees: tuple[str, ...]
    symetries_non_exploitees: tuple[str, ...]
    avertissements: tuple[str, ...]
    notes: tuple[str, ...]
    #: Comment les sous-domaines ont été obtenus, étape par étape.
    demarche: tuple[Etape, ...] = ()


# ---------------------------------------------------------------------------
# Étape 1 : domaine actif
# ---------------------------------------------------------------------------


def _domaine_actif(etude: Etude, avert: list[str]) -> dict[str, Intervalle]:
    actives = etude.trajectoire.actives
    domaine: dict[str, Intervalle] = {}
    manquantes = [v for v in actives if v not in etude.plages]
    if manquantes:
        raise ErreurEtude(
            f"{etude.trajectoire.nom} rend actives {', '.join(actives)} : "
            f"plage manquante pour {', '.join(manquantes)}"
        )
    for v in VARIABLES:
        if v in actives:
            domaine[v] = etude.plages[v]
        else:
            donnee = etude.plages.get(v)
            if donnee is not None and not donnee.est_nul:
                avert.append(f"{v} est donnée mais inactive en {etude.trajectoire.nom} : fixée à 0")
            domaine[v] = Intervalle.point(0.0)
    return domaine


def _rediger_trajectoire(redac: Redaction, etude: Etude, domaine: dict[str, Intervalle]) -> None:
    traj = etude.trajectoire
    etape = redac.etape("Trajectoire → variables actives")
    etape.ajouter(
        f"{traj.nom} consomme les efforts {' '.join(traj.efforts)} : "
        f"la base doit fournir {', '.join(traj.coefficients)}"
    )
    for v in VARIABLES:
        effort = PILOTES[v]
        if v in traj.actives:
            etape.ajouter(
                f"{symbole(v)} active : pilote {effort} ({EFFORTS[effort]}), "
                f"{borne(v, domaine[v])}°"
            )
        else:
            etape.ajouter(f"{symbole(v)} inactive : {effort} n'est pas consommé → {symbole(v)} = 0")


# ---------------------------------------------------------------------------
# Étape 2 : choix du repère
# ---------------------------------------------------------------------------


def _choisir_repere(etude: Etude, domaine: Mapping[str, Intervalle]) -> tuple[str, str]:
    geo = etude.geometrie
    angles_libres = not domaine["alpha"].est_point and not domaine["beta"].est_point
    braquages_lateraux = [not domaine[v].est_point for v in ("DM", "DN")]
    polaire_possible = angles_libres and braquages_lateraux[0] == braquages_lateraux[1]

    if etude.repere == "polaire":
        if not angles_libres:
            raise ErreurEtude(
                "repère polaire impossible : il faut α et β actifs, avec des plages non réduites "
                f"à un point (trajectoire {etude.trajectoire.nom})"
            )
        if not polaire_possible:
            raise ErreurEtude(
                "repère polaire impossible : δm et δn doivent être actifs ensemble, "
                "la rotation de φa les mélange (§7.1)"
            )
        return "polaire", "imposé par l'étude"
    if etude.repere == "cartesien":
        return "cartesien", "imposé par l'étude"

    if not angles_libres:
        return "cartesien", "vol plan : β ou α fixé, le polaire n'apporte rien"
    if geo.revolution:
        if polaire_possible:
            return "polaire", "corps de révolution : seul αt compte"
    elif geo.n_rotation >= 3 and polaire_possible:
        return (
            "polaire",
            f"rotation de {360 / geo.n_rotation:g}° : exploitable seulement en (αt, φa) (§4.4)",
        )
    return "cartesien", "les symétries de la géométrie s'expriment toutes en (α, β) (§5.4)"


def _rediger_repere(
    redac: Redaction, etude: Etude, domaine: dict[str, Intervalle], repere: str, raison: str
) -> Brouillon:
    etape = redac.etape("Choix du repère")
    if repere == "cartesien":
        etape.ajouter(f"cartésien (α, β) en repère engin : {raison}")
        return etape
    etape.ajouter(f"polaire (αt, φa) : {raison}")
    alpha, beta = domaine["alpha"], domaine["beta"]
    alphat = plage_alphat_rectangle(alpha, beta)
    etape.ajouter(
        f"α × β = {_fi(alpha)} × {_fi(beta)} : αt ∈ {_fi(alphat)}°, du point du rectangle "
        "le plus proche de l'origine à son coin le plus éloigné (§5.1)"
    )
    if etude.geometrie.revolution:
        return etape
    arc = arc_phia_rectangle(alpha, beta)
    if arc.est_complet:
        etape.ajouter("φa fait le tour complet : l'origine est intérieure au rectangle")
    else:
        fin = normaliser_angle(arc.debut + arc.longueur)
        etape.ajouter(
            f"φa parcourt l'arc de {_fn(arc.debut)}° à {_fn(fin)}° ({_fn(arc.longueur)}°), "
            "délimité par les directions des coins"
        )
    if not domaine["DM"].est_point:
        etape.ajouter(
            "(δm, δn) → (δmB, δnB), tournés de φa (repère mixte, §7.1) : "
            "ils tournent avec l'écoulement, une rotation de l'engin ne les change plus"
        )
    return etape


# ---------------------------------------------------------------------------
# Étape 3a : cartésien
# ---------------------------------------------------------------------------


def _symetriser(
    domaine: dict[str, Intervalle],
    elements: tuple[ElementSigne, ...],
    avert: list[str],
) -> dict[str, Intervalle]:
    agitees = {v for e in elements for v in e.inverse}
    resultat = dict(domaine)
    for v in agitees:
        plage = domaine[v]
        if plage.est_point or plage.est_symetrique:
            continue
        sym = plage.symetrise()
        avert.append(
            f"{v} : plage {_fi(plage)} asymétrique, étendue à {_fi(sym)} "
            f"(×{_fn(sym.largeur / plage.largeur)}) pour exploiter "
            "la symétrie ; une partie du sous-domaine n'a pas d'antécédent dans le domaine d'entrée"
        )
        resultat[v] = sym
    return resultat


def _cartesien(
    etude: Etude, domaine: dict[str, Intervalle], avert: list[str], redac: Redaction
) -> tuple[list[Strate], tuple[ElementSigne, ...]]:
    geo = etude.geometrie
    libres = [v for v in VARIABLES_CARTESIENNES if not domaine[v].est_point]
    complet = engendrer(geo.generateurs_cartesiens())
    groupe = restreindre(complet, libres)
    bornes = _symetriser({v: domaine[v] for v in VARIABLES_CARTESIENNES}, groupe, avert)

    etape = redac.etape("Groupe de symétries")
    if len(complet) == 1:
        etape.ajouter(f"{geo.nom} ({geo.description}) : aucune symétrie exprimable en (α, β)")
    else:
        noeud = etape.ajouter(
            f"{geo.nom} ({geo.description}) : {len(complet) - 1} "
            + (
                "symétries en (α, β), chacune change le signe de :"
                if len(complet) > 2
                else "symétrie en (α, β), qui change le signe de :"
            )
        )
        for e in complet[1:]:
            noeud.ajouter(decrire_element(e))
        vues = ", ".join(symbole(v) for v in libres) or "aucune"
        if len(groupe) == 1:
            etape.ajouter(f"variables libres ({vues}) : aucune n'est retournée, rien à réduire")
        elif [e.inverse for e in groupe] == [e.inverse for e in complet]:
            etape.ajouter(
                f"variables libres ({vues}) : toutes ces symétries agissent, ordre {len(groupe)}"
            )
        else:
            confondues = (
                " — des symétries qui ne diffèrent que par des variables fixées à 0 se confondent"
                if len(groupe) < len(complet)
                else ""
            )
            noeud = etape.ajouter(
                f"vu sur les variables libres ({vues}) : ordre {len(groupe)}{confondues}"
            )
            for e in groupe[1:]:
                noeud.ajouter(decrire_element(e))
        agitees = [v for v in libres if any(v in e.inverse for e in groupe)]
        for v in agitees:
            if bornes[v] == domaine[v]:
                etape.ajouter(f"{borne(v, domaine[v])} : symétrique, préservé par le groupe")
            else:
                etape.ajouter(
                    f"{borne(v, domaine[v])} : asymétrique, étendu à {_fi(bornes[v])} "
                    "pour que le groupe préserve le domaine"
                )
    angles_libres = not domaine["alpha"].est_point and not domaine["beta"].est_point
    perdues = geo.symetries_non_cartesiennes() if angles_libres else ()
    if perdues:
        etape.ajouter("non exprimables en (α, β), donc non exploitées : " + " ; ".join(perdues))

    etape = redac.etape("Découpage en domaine fondamental")
    if len(groupe) > 1:
        etape.ajouter(_REGLE_SIGNES)
    journal: list[Evenement] = []
    strates = stratifier_signes(
        bornes, groupe, VARIABLES_CARTESIENNES, nom="domaine", journal=journal
    )
    arbre_signes(etape.ajouter("domaine entier"), journal)
    return strates, groupe


#: La récurrence de :func:`stratifier_signes`, en une phrase.
_REGLE_SIGNES = (
    "règle : la première variable v qu'une symétrie retourne est gardée ≥ 0 ; sur v > 0 ne "
    "restent que les symétries qui ne la retournent pas, sur v = 0 toutes agissent encore, "
    "sur les autres variables"
)


# ---------------------------------------------------------------------------
# Étape 3b : polaire
# ---------------------------------------------------------------------------


def _braquages_mixtes(
    etude: Etude,
    domaine: dict[str, Intervalle],
    avert: list[str],
) -> tuple[dict[str, Intervalle], tuple[Contrainte, ...], float]:
    """Pavé (δmB, δnB) et contrainte de disque ; renvoie aussi le rayon."""
    dm, dn = domaine["DM"], domaine["DN"]
    if dm.est_point and dn.est_point:
        zero = Intervalle.point(0.0)
        return {"DMB": zero, "DNB": zero}, (), 0.0
    for v, plage in (("DM", dm), ("DN", dn)):
        if not plage.est_symetrique:
            avert.append(
                f"{v} : plage {_fi(plage)} asymétrique ; en repère mixte "
                "seule compte son amplitude (la rotation de φa mélange δm et δn)"
            )
    mm, mn = dm.amplitude, dn.amplitude
    if etude.limite_braquage == "disque":
        rayon = max(mm, mn)
        if abs(mm - mn) > TOLERANCE:
            avert.append(
                f"limite en disque : √(δm² + δn²) ≤ {_fn(rayon)}°, rayon pris sur la plus "
                f"grande amplitude (δm ±{_fn(mm)}°, δn ±{_fn(mn)}°)"
            )
    else:
        rayon = math.hypot(mm, mn)
        avert.append(
            f"limite en carré (δm ±{_fn(mm)}°, δn ±{_fn(mn)}°) : tourné de φa en repère mixte, "
            f"il impose de couvrir le disque de rayon {_fn(rayon, 1)}° ; une partie des points sera "
            "hors débattement (§7.6)"
        )
    plage = Intervalle(-rayon, rayon)
    return {"DMB": plage, "DNB": plage}, (Disque("DMB", "DNB", rayon),), rayon


def _apex(
    geo: Geometrie,
    etude: Etude,
    domaine: dict[str, Intervalle],
    base: dict[str, Intervalle],
    contraintes: tuple[Contrainte, ...],
    noeud: Brouillon,
) -> list[Strate]:
    """Strates de l'axe αt = 0 : D_N n'agit plus que sur les braquages, en repère engin."""
    nom = "axe"
    bornes = {**base, "alphat": Intervalle.point(0.0), "phia": Intervalle.point(0.0)}
    n = geo.n_rotation
    plan_actif = not bornes["DMB"].est_point

    if plan_actif and etude.limite_braquage == "carre":
        mm, mn = domaine["DM"].amplitude, domaine["DN"].amplitude
        if n <= 2 or (n == 4 and abs(mm - mn) <= TOLERANCE):
            # Le carré est invariant par le groupe : inutile de couvrir le disque.
            bornes = {**bornes, "DMB": Intervalle(-mm, mm), "DNB": Intervalle(-mn, mn)}
            contraintes = ()
            noeud.ajouter(
                "le carré des braquages est invariant par le groupe : gardé tel quel, "
                "sans passer au disque"
            )

    if plan_actif and n >= 3:
        angle = 180.0 / n
        roulis = "" if bornes["DL"].est_point else ", qui retourne δl → δl ≥ 0"
        noeud.ajouter(
            f"rotations de k·{360 / n:g}° : tournent (δm, δn) ; miroirs : les réfléchissent "
            f"et retournent δl → (δm, δn) ramené dans le secteur [0° ; {angle:g}°]"
        )
        interieur, axe, bord = strates_diedrales_plan(
            {v: bornes[v] for v in VARIABLES_POLAIRES},
            "DMB",
            "DNB",
            "DL",
            n,
            nom=nom,
            contraintes=contraintes,
        )
        noeud.ajouter(
            f"(δmB, δnB) dans le secteur ]0° ; {angle:g}°[ : aucune symétrie ne fixe "
            "ces braquages, δl entier",
            interieur,
        )
        noeud.ajouter(f"δnB = 0, δmB ≥ 0 : demi-droite fixée par le miroir φs = 0°{roulis}", axe)
        noeud.ajouter(
            f"demi-droite à {angle:g}°, hors origine : fixée par le miroir φs = {angle:g}°{roulis}",
            bord,
        )
        return [interieur, axe, bord]
    elements: list[ElementSigne] = []
    if geo.miroirs:
        elements.append(ElementSigne("miroir φs = 0°", frozenset({"DL", "DNB"})))
        if n == 2:
            elements.append(ElementSigne("miroir φs = 90°", frozenset({"DL", "DMB"})))
        elif n >= 3:
            # Plan (δm, δn) inactif : seul compte le changement de signe de δl.
            elements = [ElementSigne("miroirs", frozenset({"DL"}))]
    if n == 2:
        elements.append(ElementSigne("rotation 180°", frozenset({"DMB", "DNB"})))
    groupe = engendrer(elements)
    journal: list[Evenement] = []
    strates = stratifier_signes(
        {v: bornes[v] for v in VARIABLES_POLAIRES},
        groupe,
        VARIABLES_POLAIRES,
        nom=nom,
        contraintes=contraintes,
        journal=journal,
    )
    arbre_signes(noeud, journal)
    return strates


def _rediger_groupe_polaire(redac: Redaction, geo: Geometrie) -> None:
    etape = redac.etape("Groupe de symétries")
    if geo.revolution:
        etape.ajouter(
            "O(2) : toute rotation autour de x et tout miroir contenant x ; φa n'a plus "
            "d'effet, seul αt compte (§4.3)"
        )
        return
    n = geo.n_rotation
    largeur = geo.secteur_phia
    assert largeur is not None
    etape.ajouter(f"{geo.nom_groupe}, ordre {geo.ordre_groupe} : {geo.description}")
    if n > 1:
        etape.ajouter(
            f"{n} rotations de k·{360 / n:g}° : φa → φa + k·{360 / n:g}° ; δmB, δnB et δl "
            "inchangés, les braquages mixtes tournant avec φa (§7.1)"
        )
    else:
        etape.ajouter("aucune rotation autre que l'identité")
    if geo.miroirs:
        plans = ", ".join(f"{p:g}°" for p in geo.plans_phia)
        etape.ajouter(
            f"{n} miroir{'s' if n > 1 else ''} φs = {plans} : φa → 2φs − φa ; δnB et δl "
            "changent de signe, "
            "δmB est conservé (§7.2)"
        )
    secteur = Intervalle(0.0, largeur, haut_inclus=geo.miroirs)
    etape.ajouter(
        f"secteur fondamental φa ∈ {_fi(secteur)}° : ses {geo.ordre_groupe} images par le "
        "groupe pavent le tour, chaque orbite de φa y a un représentant"
    )


def _polaire(
    etude: Etude,
    domaine: dict[str, Intervalle],
    avert: list[str],
    notes: list[str],
    redac: Redaction,
) -> list[Strate]:
    geo = etude.geometrie
    alphat = plage_alphat_rectangle(domaine["alpha"], domaine["beta"])
    zero = Intervalle.point(0.0)
    _rediger_groupe_polaire(redac, geo)
    etape = redac.etape("Découpage en domaine fondamental")

    if geo.revolution:
        notes.append("corps de révolution : les coefficients ne dépendent que de αt (§4.3)")
        bornes = {
            "alphat": alphat,
            "phia": zero,
            "DMB": zero,
            "DNB": zero,
            "DL": zero,
        }
        strate = Strate(bornes, nom="axisymétrique")
        etape.ajouter(f"αt ∈ {_fi(alphat)}°, φa = 0 et pas de braquage : une seule strate", strate)
        return [strate]

    notes.append(
        f"le rectangle (α, β) est couvert par αt ∈ {_fi(alphat)}° sur tout le secteur utile : "
        "les points hors rectangle sont calculés aussi (§5.4)"
    )

    lateraux, contraintes, _ = _braquages_mixtes(etude, domaine, avert)
    roulis = domaine["DL"]
    if geo.miroirs and not roulis.est_point and not roulis.est_symetrique:
        avert.append(
            f"DL : plage {_fi(roulis)} asymétrique, étendue à "
            f"±{_fn(roulis.amplitude)}° (les miroirs changent le signe de δl)"
        )
        etape.ajouter(
            f"{borne('DL', roulis)} : asymétrique, étendu à {_fi(roulis.symetrise())} "
            "car les miroirs retournent δl"
        )
        roulis = roulis.symetrise()
    base = {**lateraux, "DL": roulis}

    arc = arc_phia_rectangle(domaine["alpha"], domaine["beta"])
    largeur = geo.secteur_phia
    assert largeur is not None
    secteurs = replier_arc(arc, geo.n_rotation, geo.miroirs)

    strates: list[Strate] = []
    if alphat.haut > TOLERANCE:
        if alphat.bas <= TOLERANCE:
            couronnes = Intervalle(0.0, alphat.haut, bas_inclus=False)
        else:
            couronnes = alphat
        plans = (0.0, largeur) if geo.miroirs else ()
        noeud = etape.ajouter(
            f"αt ∈ {_fi(couronnes)}° : φa ramené dans le secteur fondamental "
            f"{_fi(Intervalle(0.0, largeur, haut_inclus=geo.miroirs))}°"
        )
        if arc.est_complet:
            noeud.ajouter("φa fait le tour complet : tout le secteur est atteint")
        else:
            atteint = ", ".join(_fi(s) for s in secteurs) or "rien"
            noeud.ajouter(
                f"l'arc de φa, replié par les {geo.ordre_groupe} symétries, atteint {atteint}° "
                "du secteur"
            )

        for secteur in secteurs:
            bas_ouvert = geo.miroirs and abs(secteur.bas) <= TOLERANCE
            haut_ouvert = (geo.miroirs and abs(secteur.haut - largeur) <= TOLERANCE) or (
                not secteur.haut_inclus
            )
            if secteur.haut - secteur.bas <= TOLERANCE:
                continue
            interieur = Intervalle(
                secteur.bas,
                secteur.haut,
                bas_inclus=secteur.bas_inclus and not bas_ouvert,
                haut_inclus=secteur.haut_inclus and not haut_ouvert,
            )
            strate = Strate(
                {"alphat": couronnes, "phia": interieur, **base},
                contraintes,
                nom="secteur",
            )
            strates.append(strate)
            pourquoi = (
                "aucune symétrie ne fixe un φa intérieur au secteur"
                if geo.miroirs
                else "aucune symétrie ne fixe φa (pas de miroir)"
            )
            noeud.ajouter(f"{borne('phia', interieur)} : {pourquoi} → braquages entiers", strate)
        for phis in plans:
            if not any(s.contient(phis) for s in secteurs):
                noeud.ajouter(f"φa = {phis:g}° : plan non atteint par l'arc, rien à calculer")
                continue
            plan = noeud.ajouter(f"φa = {phis:g}° : plan du miroir φs = {phis:g}°, qui fixe φa")
            journal: list[Evenement] = []
            strates += stratifier_signes(
                {"alphat": couronnes, "phia": Intervalle.point(phis), **base},
                (MIROIR_PLAN_POLAIRE,),
                VARIABLES_POLAIRES,
                nom="plan",
                contraintes=contraintes,
                journal=journal,
            )
            arbre_signes(plan, journal)

    if alphat.bas <= TOLERANCE:
        notes.append("axe αt = 0 : φa fixé à 0 par convention (§2.5), braquages en repère engin")
        noeud = etape.ajouter(
            "αt = 0 : φa indéfini, fixé à 0 (§2.5) ; le groupe n'agit plus que sur les "
            "braquages, en repère engin"
        )
        strates += _apex(geo, etude, domaine, base, contraintes, noeud)

    strates = [
        Strate({v: s.bornes[v] for v in VARIABLES_POLAIRES}, s.contraintes, s.nom, s.chemin)
        for s in strates
    ]
    return strates


def _symetries_polaires(geo: Geometrie) -> tuple[str, ...]:
    if geo.revolution:
        return ("toutes les rotations et tous les miroirs autour de x",)
    noms: list[str] = []
    if geo.n_rotation > 1:
        noms.append(f"rotation de {360 / geo.n_rotation:g}°")
    if geo.miroirs:
        noms.append("miroirs φs = " + ", ".join(f"{p:g}°" for p in geo.plans_phia))
    return tuple(noms)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------


def reduire(etude: Etude) -> Reduction:
    """Réduit le domaine d'une étude à ses sous-domaines de calcul."""
    avert: list[str] = []
    notes: list[str] = []
    redac = Redaction()
    domaine = _domaine_actif(etude, avert)
    _rediger_trajectoire(redac, etude, domaine)
    geo = etude.geometrie

    if geo.revolution and any(not domaine[v].est_point for v in BRAQUAGES):
        raise ErreurEtude(
            "corps de révolution : pas de gouverne, donc pas de braquage. "
            "Choisir une géométrie à ailettes ou une trajectoire sans moment piloté."
        )

    repere, raison = _choisir_repere(etude, domaine)
    etape_repere = _rediger_repere(redac, etude, domaine, repere, raison)
    if repere == "cartesien":
        strates, groupe = _cartesien(etude, domaine, avert, redac)
        variables = VARIABLES_CARTESIENNES
        exploitees = tuple(e.nom for e in groupe if e.inverse)
        n_elements = len(groupe)
        ordre: int | None = n_elements
        nom_groupe = {1: "trivial", 2: "Z2", 4: "D2"}.get(
            n_elements, f"Z2^{round(math.log2(n_elements))}"
        )
        angles_libres = not domaine["alpha"].est_point and not domaine["beta"].est_point
        perdues = geo.symetries_non_cartesiennes() if angles_libres else ()
        if perdues and etude.repere == "cartesien":
            avert.append(
                "repère cartésien demandé : symétries non exploitées — " + " ; ".join(perdues)
            )
        if geo.revolution and angles_libres:
            avert.append("corps de révolution en cartésien : seuls les miroirs V, H sont exploités")
    else:
        strates = _polaire(etude, domaine, avert, notes, redac)
        if not domaine["DM"].est_point:
            _rediger_limite(etape_repere, etude, domaine)
        variables = VARIABLES_POLAIRES
        exploitees = _symetries_polaires(geo)
        ordre = geo.ordre_groupe
        nom_groupe = geo.nom_groupe
        perdues = ()

    recollements: list[Recollement] = []
    strates = fusionner(strates, recollements)
    _rediger_recollement(redac, recollements, len(strates))
    sous_domaines = tuple(
        SousDomaine(i, s.nom, s.bornes, s.contraintes, s.chemin)
        for i, s in enumerate(strates, start=1)
    )
    return Reduction(
        etude=etude,
        repere=repere,
        raison_repere=raison,
        variables=variables,
        domaine_entree=domaine,
        actives=etude.trajectoire.actives,
        sous_domaines=sous_domaines,
        groupe=nom_groupe,
        ordre_groupe=ordre,
        symetries_exploitees=exploitees,
        symetries_non_exploitees=perdues,
        avertissements=tuple(avert),
        notes=tuple(notes),
        demarche=redac.figer(numeroteur(strates)),
    )


def _rediger_limite(etape: Brouillon, etude: Etude, domaine: dict[str, Intervalle]) -> None:
    mm, mn = domaine["DM"].amplitude, domaine["DN"].amplitude
    if etude.limite_braquage == "disque":
        etape.ajouter(
            f"limite en disque √(δm² + δn²) ≤ {_fn(max(mm, mn))}° : invariante par rotation, "
            "elle reste un disque en (δmB, δnB)"
        )
    else:
        etape.ajouter(
            f"limite en carré (δm ±{_fn(mm)}°, δn ±{_fn(mn)}°) : tournée de φa, elle n'est plus "
            f"un carré ; on couvre le disque circonscrit, rayon {_fn(math.hypot(mm, mn), 1)}° (§7.6)"
        )


def _nommer(nom: str) -> str:
    """Le nom d'une strate devant sa borne ; « domaine » (cartésien) ne dit rien, on le tait."""
    return "" if nom in ("", "domaine") else f"{nom} "


def _rediger_recollement(
    redac: Redaction, recollements: list[Recollement], n_sous_domaines: int
) -> None:
    etape = redac.etape("Recollement et numérotation")
    if not recollements:
        etape.ajouter("aucune strate à recoller : chacune est un sous-domaine")
    for r in recollements:
        (a, b), (nom_a, nom_b) = r.avant, r.noms
        etape.ajouter(
            f"{_nommer(nom_a)}{borne(r.variable, a)} et {_nommer(nom_b)}{borne(r.variable, b)} : "
            f"mêmes bornes ailleurs, contigus → recollés en {borne(r.variable, r.union)}"
        )
    etape.ajouter(
        (
            f"{n_sous_domaines} sous-domaines, numérotés dans l'ordre du découpage"
            if n_sous_domaines > 1
            else "1 sous-domaine"
        )
        + " : « → #k » renvoie à la ligne k du tableau"
    )


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def _intervalle(i: Intervalle) -> dict[str, Any]:
    return {
        "bas": round(i.bas, 10),
        "haut": round(i.haut, 10),
        "bas_inclus": i.bas_inclus,
        "haut_inclus": i.haut_inclus,
    }


def _contrainte(c: Contrainte) -> dict[str, Any]:
    if isinstance(c, Secteur):
        return {
            "type": "secteur",
            "x": c.x,
            "y": c.y,
            "angle_min": c.angle_min,
            "angle_max": c.angle_max,
            "min_inclus": c.min_inclus,
            "max_inclus": c.max_inclus,
        }
    return {"type": "disque", "x": c.x, "y": c.y, "rayon": round(c.rayon, 10)}


def symetries_exportees(reduction: Reduction) -> list[dict[str, Any]]:
    """Les symétries du groupe complet (identité exclue), telles qu'un lecteur les applique.

    Chacune donne les variables du repère de travail et les coefficients
    qu'elle change de signe ; en polaire, aussi son action sur φa (rotation
    ``φa + θ`` ou miroir ``2φs − φa``). C'est ce qui permet de reconstituer,
    hors de ce paquet, les points que la réduction a écartés, sans réécrire
    les conventions de signe (``data/geometries.py``).

    Le groupe est le groupe **complet**, non restreint aux variables libres :
    deux symétries qui y agissent pareil peuvent différer sur les coefficients.
    """
    geo = reduction.etude.geometrie
    if reduction.repere == "cartesien":
        return [
            {
                "nom": e.nom,
                "variables": [v for v in VARIABLES_CARTESIENNES if v in e.inverse],
                "coefficients": list(coefficients_retournes(e)),
            }
            for e in engendrer(geo.generateurs_cartesiens())[1:]
        ]
    if geo.revolution:
        return []
    n = geo.n_rotation
    elements: list[dict[str, Any]] = [
        {
            "nom": f"rotation {360 * k / n:g}°",
            "phia": {"rotation": 360 * k / n},
            "variables": [],
            "coefficients": [],
        }
        for k in range(1, n)
    ]
    retournees = [v for v in VARIABLES_POLAIRES if v in MIROIR_PLAN_POLAIRE.inverse]
    elements += [
        {
            "nom": f"miroir φs = {phis:g}°",
            "phia": {"miroir": phis},
            "variables": list(retournees),
            "coefficients": list(COEFFICIENTS_HORS_PAV),
        }
        for phis in geo.plans_phia
    ]
    return elements


def vers_dict(reduction: Reduction) -> dict[str, Any]:
    """Forme sérialisable (YAML/JSON), lue par la phase de remplissage."""
    etude = reduction.etude
    return {
        "etude": etude.nom,
        "trajectoire": etude.trajectoire.nom,
        "coefficients": list(etude.trajectoire.coefficients),
        "geometrie": etude.geometrie.nom,
        "n_rotation": etude.geometrie.n_rotation,
        "repere": reduction.repere,
        "limite_braquage": etude.limite_braquage,
        "unite": "deg",
        "variables": list(reduction.variables),
        "domaine_entree": {v: _intervalle(i) for v, i in reduction.domaine_entree.items()},
        "groupe": reduction.groupe,
        "ordre_groupe": reduction.ordre_groupe,
        "symetries": symetries_exportees(reduction),
        "sous_domaines": [
            {
                "numero": sd.numero,
                "nom": sd.nom,
                "dimension": sd.dimension,
                "bornes": {v: _intervalle(i) for v, i in sd.bornes.items()},
                "contraintes": [_contrainte(c) for c in sd.contraintes],
                "chemin": [f"{c.variable} {c.texte}" for c in sd.chemin],
            }
            for sd in reduction.sous_domaines
        ],
        "avertissements": list(reduction.avertissements),
    }
