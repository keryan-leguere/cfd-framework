#!/usr/bin/env python3
"""Après ``pip install`` : lanceurs en ``#!/usr/bin/env python3`` et complétion bash.

À lancer avec le ``python3`` qui a servi à installer les paquets, après chaque
installation ou mise à jour (pip réécrit ses lanceurs à chaque fois)::

    python3 tools/installation/installer_lanceurs.py            # tout
    python3 tools/installation/installer_lanceurs.py --a-blanc  # dire sans écrire

Pourquoi un script et pas une option de pip : pip grave dans chaque script
console le chemin absolu de l'interpréteur (``sys.executable``) et n'a ni option
pour en choisir un autre, ni crochet post-installation. Écrire soi-même un script
``#!/usr/bin/env python3`` dans le paquet n'aide pas : setuptools réécrit toute
ligne ``#!…python…`` à la construction de la roue, et pip la remplace à
l'installation.

Deux actions, pour chaque paquet de ``tools/`` installé dans cet interpréteur :

1. **Shebang** : le script console est réécrit avec ``#!/usr/bin/env python3``
   (même contenu que celui de pip, seul l'interpréteur change). Il n'est réécrit
   que si le ``python3`` du ``PATH`` importe *maintenant* le paquet : sinon la
   commande cesserait de marcher (venv non activé, autre Python en tête du PATH),
   et le script le dit au lieu de casser. ``--forcer`` passe outre.
2. **Complétion bash** : l'analyseur argparse de chaque commande est capturé
   (sans l'exécuter) et traduit en une fonction bash *statique* — sous-commandes,
   options, valeurs permises (``choices``), fichiers ailleurs. Statique parce
   qu'une complétion qui relancerait Python à chaque tabulation importerait
   NumPy à chaque fois. Toutes les fonctions vont dans un fichier, sourcé par une
   ligne ajoutée une fois à ``~/.bashrc`` (``--sans-bashrc`` pour ne pas y toucher).

Bibliothèque standard seulement, Python ≥ 3.9 : il doit tourner sur une machine
air-gap où rien d'autre n'est garanti.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import importlib.metadata
import io
import os
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

SHEBANG = "#!/usr/bin/env python3"
DEBUT_BASHRC = "# >>> cfd-framework : complétion bash >>>"
FIN_BASHRC = "# <<< cfd-framework : complétion bash <<<"
TOOLS = Path(__file__).resolve().parents[1]

_TYPES_NUMERIQUES = (int, float)


# --- paquets et commandes -----------------------------------------------------

def _normaliser(nom: str) -> str:
    return re.sub(r"[-_.]+", "-", nom).lower()


def noms_des_paquets(racine: Path = TOOLS) -> set[str]:
    """Noms ``[project] name`` des ``pyproject.toml`` de ``tools/*`` (sans tomllib : 3.9)."""
    noms = set()
    for pyproject in sorted(racine.glob("*/pyproject.toml")):
        texte = pyproject.read_text(encoding="utf-8")
        bloc = texte.split("[project]", 1)[-1]
        m = re.search(r'^name\s*=\s*"([^"]+)"', bloc, re.MULTILINE)
        if m:
            noms.add(_normaliser(m.group(1)))
    return noms


@dataclass(frozen=True)
class Commande:
    """Un script console : ``nom`` → ``module:attribut``, fourni par ``paquet``."""

    nom: str
    paquet: str
    valeur: str
    script: Path | None

    @property
    def module(self) -> str:
        return self.valeur.split(":", 1)[0].strip()

    @property
    def attribut(self) -> str:
        return self.valeur.split(":", 1)[1].strip() if ":" in self.valeur else ""


def _script_de(dist: importlib.metadata.Distribution, nom: str) -> Path | None:
    for f in dist.files or ():
        if f.name == nom and f.parent.name in ("bin", "Scripts"):
            chemin = Path(str(dist.locate_file(f))).resolve()
            if chemin.is_file():
                return chemin
    trouve = shutil.which(nom)
    return Path(trouve).resolve() if trouve else None


def commandes_installees(paquets: set[str]) -> list[Commande]:
    """Les scripts console des ``paquets`` installés dans cet interpréteur."""
    vues: dict[str, Commande] = {}
    for dist in importlib.metadata.distributions():
        paquet = _normaliser(dist.metadata["Name"] or "")
        if paquet not in paquets:
            continue
        for ep in dist.entry_points:
            if ep.group == "console_scripts" and ep.name not in vues:
                vues[ep.name] = Commande(ep.name, paquet, ep.value, _script_de(dist, ep.name))
    return [vues[n] for n in sorted(vues)]


# --- shebang ------------------------------------------------------------------

def contenu_lanceur(commande: Commande) -> str:
    """Le script console de pip, à l'interpréteur près."""
    attribut = commande.attribut or "main"
    tete, _, reste = attribut.partition(".")
    appel = f"{tete}.{reste}()" if reste else f"{tete}()"
    return (
        f"{SHEBANG}\n"
        "# -*- coding: utf-8 -*-\n"
        "# Réécrit par tools/installation/installer_lanceurs.py : python3 résolu sur le PATH.\n"
        "import re\n"
        "import sys\n"
        f"from {commande.module} import {tete}\n"
        "if __name__ == '__main__':\n"
        "    sys.argv[0] = re.sub(r'(-script\\.pyw|\\.exe)?$', '', sys.argv[0])\n"
        f"    sys.exit({appel})\n"
    )


def est_lanceur_pip(texte: str, module: str) -> bool:
    """Un script console écrit par pip (ou par nous) : on ne touche à rien d'autre."""
    lignes = texte.splitlines()
    if not lignes or not lignes[0].startswith("#!"):
        return False
    python = "python" in lignes[0] or (lignes[0].startswith("#!/bin/sh") and "'''exec'" in texte)
    return python and f"from {module} import" in texte


def python3_du_path_importe(module: str) -> tuple[bool, str]:
    """``/usr/bin/env python3`` trouverait-il ``module`` ? (et lequel serait-ce)"""
    python3 = shutil.which("python3")
    if python3 is None:
        return False, "aucun python3 sur le PATH"
    r = subprocess.run([python3, "-c", f"import {module.split('.')[0]}"],
                       capture_output=True, text=True, check=False)
    return r.returncode == 0, python3


def reecrire_shebang(commande: Commande, a_blanc: bool, forcer: bool) -> str:
    """Réécrit un lanceur ; renvoie la ligne de compte rendu."""
    if commande.script is None:
        return "script introuvable (installé sans scripts ?)"
    texte = commande.script.read_text(encoding="utf-8", errors="replace")
    if not est_lanceur_pip(texte, commande.module):
        return f"{commande.script} : pas un lanceur pip, laissé tel quel"
    nouveau = contenu_lanceur(commande)
    if texte == nouveau:
        return f"{commande.script} : déjà en {SHEBANG}"
    importe, python3 = python3_du_path_importe(commande.module)
    if not importe and not forcer:
        return (f"{commande.script} : NON réécrit — {python3} n'importe pas {commande.module} "
                f"(activer le bon environnement, ou --forcer)")
    if a_blanc:
        return f"{commande.script} : serait réécrit ({python3})"
    mode = commande.script.stat().st_mode
    commande.script.write_text(nouveau, encoding="utf-8")
    os.chmod(commande.script, mode)
    return f"{commande.script} : réécrit ({python3})"


# --- capture de l'analyseur ---------------------------------------------------

class _Capture(BaseException):
    """Levée à la place de ``parse_args`` ; BaseException pour traverser ``except Exception``."""

    def __init__(self, parseur: argparse.ArgumentParser) -> None:
        super().__init__()
        self.parseur = parseur


def capturer_parseur(commande: Commande) -> argparse.ArgumentParser:
    """Appelle le point d'entrée jusqu'à son ``parse_args``, et garde l'analyseur."""
    objet = importlib.import_module(commande.module)
    for morceau in (commande.attribut or "main").split("."):
        objet = getattr(objet, morceau)

    def intercepter(self: argparse.ArgumentParser, *_: object, **__: object) -> None:
        raise _Capture(self)

    originaux = (argparse.ArgumentParser.parse_args, argparse.ArgumentParser.parse_known_args)
    argv = sys.argv
    argparse.ArgumentParser.parse_args = intercepter  # type: ignore[assignment,method-assign]
    argparse.ArgumentParser.parse_known_args = intercepter  # type: ignore[assignment,method-assign]
    # « --help » et non rien : certains points d'entrée affichent l'aide sans analyser
    # quand la ligne est vide (cfd-stats) ; parse_args, intercepté, ne la verra jamais.
    sys.argv = [commande.nom, "--help"]
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            objet()  # type: ignore[operator]
    except _Capture as capture:
        return capture.parseur
    finally:
        argparse.ArgumentParser.parse_args, argparse.ArgumentParser.parse_known_args = originaux  # type: ignore[method-assign]
        sys.argv = argv
    raise RuntimeError("le point d'entrée n'appelle pas parse_args")


# --- complétion bash ----------------------------------------------------------

@dataclass
class Noeud:
    """Un niveau de sous-commande : ``chemin`` = ``""``, ``/rendre``, ``/a/b``…"""

    chemin: str
    options: list[str] = field(default_factory=list)
    #: option → ("choix", valeurs) | ("fichier", []) | ("rien", [])
    valeurs: dict[str, tuple[str, list[str]]] = field(default_factory=dict)
    sous: list[str] = field(default_factory=list)
    mots: list[str] = field(default_factory=list)
    fichiers: bool = False


def _sorte(action: argparse.Action) -> tuple[str, list[str]]:
    if action.choices is not None:
        return "choix", [str(c) for c in action.choices]
    if action.type in _TYPES_NUMERIQUES:
        return "rien", []
    return "fichier", []


def arbre(parseur: argparse.ArgumentParser, chemin: str = "") -> Iterator[Noeud]:
    """Les niveaux du parseur, du sommet vers les feuilles."""
    noeud = Noeud(chemin)
    enfants: list[tuple[str, argparse.ArgumentParser]] = []
    for action in parseur._actions:
        if isinstance(action, argparse._SubParsersAction):
            for nom, sous in action.choices.items():
                noeud.sous.append(nom)
                enfants.append((nom, sous))
        elif action.option_strings:
            if action.help == argparse.SUPPRESS:
                continue
            noeud.options += action.option_strings
            if action.nargs != 0:
                for option in action.option_strings:
                    noeud.valeurs[option] = _sorte(action)
        else:
            sorte, valeurs = _sorte(action)
            noeud.mots += valeurs
            noeud.fichiers |= sorte == "fichier"
    yield noeud
    for nom, sous in enfants:
        yield from arbre(sous, f"{chemin}/{nom}")


def _mots(mots: Sequence[str]) -> str:
    # IFS = saut de ligne dans la fonction : une valeur peut contenir une espace.
    return shlex.quote("\n".join(dict.fromkeys(mots)))


def completion_bash(nom: str, parseur: argparse.ArgumentParser) -> str:
    """Fonction bash statique qui complète ``nom`` comme ``parseur`` l'analyserait."""
    fonction = "_" + re.sub(r"\W", "_", nom) + "_completion"
    noeuds = list(arbre(parseur))
    L = [f"# Complétion bash de {nom} — générée par tools/installation/installer_lanceurs.py.",
         "# Ne pas modifier : relancer le script après une mise à jour du paquet.",
         f"{fonction}() {{",
         "    local IFS=$'\\n' cur=${COMP_WORDS[COMP_CWORD]} prev= chemin= i mots= fichiers=0",
         "    (( COMP_CWORD > 0 )) && prev=${COMP_WORDS[COMP_CWORD-1]}"]
    passages = [f"{n.chemin}|{s}" for n in noeuds for s in n.sous]
    if passages:
        L += ["    for ((i = 1; i < COMP_CWORD; i++)); do",
              '        case "$chemin|${COMP_WORDS[i]}" in',
              f"            {'|'.join(shlex.quote(p) for p in passages)}) chemin=\"$chemin/${{COMP_WORDS[i]}}\" ;;",
              "        esac",
              "    done"]
    valeurs = [(f"{n.chemin}|{o}", s) for n in noeuds for o, s in n.valeurs.items()]
    if valeurs:
        L.append('    case "$chemin|$prev" in')
        for cle, (sorte, choix) in valeurs:
            if sorte == "choix":
                action = f'COMPREPLY=($(compgen -W {_mots(choix)} -- "$cur"))'
            elif sorte == "fichier":
                action = 'COMPREPLY=($(compgen -f -- "$cur")); compopt -o filenames 2>/dev/null'
            else:
                action = "COMPREPLY=()"
            L.append(f"        {shlex.quote(cle)}) {action}; return 0 ;;")
        L.append("    esac")
    L += ['    if [[ $cur == -* ]]; then', '        case "$chemin" in']
    L += [f"            {shlex.quote(n.chemin)}) mots={_mots(n.options)} ;;" for n in noeuds]
    L += ["        esac",
          '        COMPREPLY=($(compgen -W "$mots" -- "$cur")); return 0',
          "    fi",
          '    case "$chemin" in']
    L += [f"        {shlex.quote(n.chemin)}) mots={_mots(n.sous + n.mots)}; fichiers={int(n.fichiers)} ;;"
          for n in noeuds]
    L += ["    esac",
          '    COMPREPLY=($(compgen -W "$mots" -- "$cur"))',
          "    if (( fichiers )); then",
          '        COMPREPLY+=($(compgen -f -- "$cur")); compopt -o filenames 2>/dev/null',
          "    fi",
          "    return 0",
          "}",
          f"complete -F {fonction} {nom}",
          ""]
    return "\n".join(L)


def fichier_completion() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "cfd-framework" / "completion.bash"


def bloc_bashrc(chemin: Path) -> str:
    c = shlex.quote(str(chemin))
    return f"{DEBUT_BASHRC}\n[ -f {c} ] && . {c}\n{FIN_BASHRC}\n"


def ajouter_au_bashrc(bashrc: Path, chemin: Path) -> bool:
    """Ajoute (une fois) la ligne qui source les complétions ; ``True`` si ajoutée."""
    texte = bashrc.read_text(encoding="utf-8") if bashrc.exists() else ""
    if DEBUT_BASHRC in texte:
        return False
    with bashrc.open("a", encoding="utf-8") as f:
        f.write(("\n" if texte and not texte.endswith("\n") else "") + bloc_bashrc(chemin))
    return True


# --- programme ----------------------------------------------------------------

def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="installer_lanceurs.py",
        description="Lanceurs en #!/usr/bin/env python3 et complétion bash des paquets de tools/.")
    p.add_argument("--a-blanc", action="store_true", help="dire ce qui serait fait, ne rien écrire")
    p.add_argument("--forcer", action="store_true",
                   help="réécrire le shebang même si le python3 du PATH n'importe pas le paquet")
    p.add_argument("--sans-shebang", action="store_true", help="ne pas toucher aux lanceurs")
    p.add_argument("--sans-completion", action="store_true", help="ne pas générer la complétion")
    p.add_argument("--sans-bashrc", action="store_true", help="ne pas ajouter la ligne à ~/.bashrc")
    args = p.parse_args(argv)

    commandes = commandes_installees(noms_des_paquets())
    if not commandes:
        print(f"Aucun paquet de {TOOLS} installé dans {sys.executable}.")
        return 1
    print(f"Interpréteur : {sys.executable}")
    print(f"Commandes    : {', '.join(c.nom for c in commandes)}\n")
    erreurs = 0

    if not args.sans_shebang:
        print(f"Shebang {SHEBANG}")
        for c in commandes:
            ligne = reecrire_shebang(c, args.a_blanc, args.forcer)
            erreurs += "NON réécrit" in ligne
            print(f"  {c.nom:<16} {ligne}")
        print()

    if not args.sans_completion:
        print("Complétion bash")
        morceaux = []
        for c in commandes:
            try:
                morceaux.append(completion_bash(c.nom, capturer_parseur(c)))
                print(f"  {c.nom:<16} ok")
            except Exception as exc:  # noqa: BLE001 — un paquet cassé n'empêche pas les autres
                erreurs += 1
                print(f"  {c.nom:<16} NON générée — {type(exc).__name__} : {exc}")
        cible = fichier_completion()
        if morceaux and not args.a_blanc:
            cible.parent.mkdir(parents=True, exist_ok=True)
            cible.write_text("\n".join(morceaux), encoding="utf-8")
        print(f"  {'fichier':<16} {cible}" + (" (non écrit : à blanc)" if args.a_blanc else ""))
        bashrc = Path.home() / ".bashrc"
        if args.sans_bashrc:
            print(f"  {'~/.bashrc':<16} non modifié ; à ajouter :\n{bloc_bashrc(cible)}")
        elif args.a_blanc:
            print(f"  {'~/.bashrc':<16} recevrait (une fois) la ligne qui source ce fichier")
        else:
            ajoute = ajouter_au_bashrc(bashrc, cible)
            print(f"  {'~/.bashrc':<16} " + ("ligne ajoutée" if ajoute else "ligne déjà présente"))
        if not args.a_blanc:
            print(f"\nNouveau terminal, ou : source {shlex.quote(str(cible))}")
    return 1 if erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
