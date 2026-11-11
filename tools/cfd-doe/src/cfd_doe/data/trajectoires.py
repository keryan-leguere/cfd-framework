"""Types de trajectoire et variables qu'ils rendent actives.

Classification de Freeman. Un type de trajectoire dit quels efforts le
simulateur consomme ; une variable du DOE est **active** si elle pilote l'un
de ces efforts :

- la force normale N demande α ; la force latérale Y demande β ;
- le moment de tangage m demande δm, le lacet n demande δn, le roulis l
  demande δl.

Les variables inactives sont fixées à 0 : le simulateur ne les verra jamais.
La table est surchargeable depuis le fichier d'étude (clé ``trajectoires``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from cfd_doe.data.variables import VARIABLES

__all__ = [
    "EFFORTS",
    "PILOTES",
    "TRAJECTOIRES",
    "Trajectoire",
    "fabriquer_trajectoire",
    "resoudre_trajectoire",
]

#: Efforts reconnus, et le coefficient qu'ils désignent.
EFFORTS: dict[str, str] = {
    "A": "CA",
    "N": "CN",
    "Y": "CY",
    "m": "Cm",
    "n": "Cn",
    "l": "Cl",
}

#: Variable du DOE → effort qu'elle pilote (une variable est active si le type
#: de trajectoire consomme cet effort).
PILOTES: dict[str, str] = {"alpha": "N", "beta": "Y", "DM": "m", "DN": "n", "DL": "l"}


@dataclass(frozen=True)
class Trajectoire:
    """Un type de trajectoire."""

    nom: str
    description: str
    efforts: tuple[str, ...]
    actives: tuple[str, ...]

    @property
    def coefficients(self) -> tuple[str, ...]:
        """Les coefficients aéro que la base doit fournir."""
        return tuple(EFFORTS[e] for e in self.efforts)


def _t(nom: str, description: str, efforts: str, actives: Sequence[str]) -> Trajectoire:
    return Trajectoire(nom, description, tuple(efforts.split()), tuple(actives))


TRAJECTOIRES: dict[str, Trajectoire] = {
    t.nom: t
    for t in (
        _t("1DOF", "force axiale seule", "A", ()),
        _t("2DOF", "forces normale et axiale", "A N", ("alpha",)),
        _t(
            "3DOF_MASSE_PONCTUELLE",
            "masse ponctuelle : forces normale, axiale, latérale",
            "A N Y",
            ("alpha", "beta"),
        ),
        _t(
            "3DOF_TANGAGE",
            "plan de tangage : forces normale et axiale, moment de tangage",
            "A N m",
            ("alpha", "DM"),
        ),
        _t(
            "4DOF",
            "forces normale et axiale, moments de tangage et de roulis",
            "A N m l",
            ("alpha", "DM", "DL"),
        ),
        _t(
            "5DOF",
            "forces normale, axiale, latérale, moments de tangage et de lacet",
            "A N Y m n",
            ("alpha", "beta", "DM", "DN"),
        ),
        _t(
            "6DOF",
            "trois forces, trois moments",
            "A N Y m n l",
            ("alpha", "beta", "DM", "DN", "DL"),
        ),
    )
}


def fabriquer_trajectoire(nom: str, definition: Mapping[str, object]) -> Trajectoire:
    """Une trajectoire définie par l'utilisateur : ``{efforts: [...], description: ...}``.

    Les variables actives se déduisent des efforts, pour que la table ne puisse
    pas se contredire.
    """
    cles = set(definition) - {"efforts", "description"}
    if cles:
        raise ValueError(
            f"trajectoire {nom} : clé(s) inconnue(s) {sorted(cles)} ; "
            "clés admises : efforts, description"
        )
    efforts_bruts = definition.get("efforts")
    if not isinstance(efforts_bruts, (list, tuple)) or not efforts_bruts:
        raise ValueError(f"trajectoire {nom} : « efforts » doit être une liste non vide")
    efforts = tuple(str(e) for e in efforts_bruts)
    inconnus = [e for e in efforts if e not in EFFORTS]
    if inconnus:
        raise ValueError(
            f"trajectoire {nom} : effort(s) inconnu(s) {inconnus} ; admis : {', '.join(EFFORTS)}"
        )
    actives = tuple(v for v in VARIABLES if PILOTES[v] in efforts)
    return Trajectoire(
        nom, str(definition.get("description", "définie par l'étude")), efforts, actives
    )


def resoudre_trajectoire(nom: str, table: Mapping[str, Trajectoire] = TRAJECTOIRES) -> Trajectoire:
    """Retrouve un type par son nom, sans tenir compte de la casse."""
    index = {k.upper(): t for k, t in table.items()}
    try:
        return index[nom.strip().upper()]
    except KeyError:
        raise ValueError(
            f"type de trajectoire inconnu : {nom!r} ; types admis : {', '.join(table)}"
        ) from None
