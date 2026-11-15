"""Le journal du test : le rapport complet, en texte, archivable.

C'est le rendu du terminal en ``complet=True`` (toutes les lignes, chaque
niveau de chaque entrée), écrit sans couleur dans une console Rich large : un
fichier texte UTF-8 qui se lit dans n'importe quel éditeur et se compare d'une
exécution à l'autre avec ``diff``.

Il se termine par la liste des pièces produites, lui compris, et l'empreinte
SHA-256 de chacune — de sorte qu'on puisse vérifier plus tard qu'une figure
jointe à un rapport est bien celle de cette exécution.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Sequence
from pathlib import Path

from rich import box
from rich.console import Console
from rich.padding import Padding
from rich.table import Table

from cfd_validation.engine.integration import ResultatIntegration
from cfd_validation.report import theme
from cfd_validation.report.console import largeur_journal, rendre_integration

__all__ = ["LARGEUR_JOURNAL", "ecrire_journal", "sha256_fichier"]

#: Largeur minimale du journal en caractères ; elle croît avec le nombre d'entrées et de
#: sorties (:func:`largeur_journal`), pour que la table ligne à ligne n'y soit jamais rognée.
LARGEUR_JOURNAL = 160


def sha256_fichier(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def ecrire_journal(
    res: ResultatIntegration,
    chemin: str | Path,
    *,
    pieces: Sequence[Path] = (),
    racine: Path | None = None,
) -> Path:
    """Écrit le journal complet de ``res`` dans ``chemin`` ; ``pieces`` sont listées avec leur SHA-256."""
    p = Path(chemin)
    p.parent.mkdir(parents=True, exist_ok=True)
    tampon = io.StringIO()
    # Rendu en mémoire : on ôte ensuite le remplissage de fin de ligne de Rich.
    console = Console(
        file=tampon,
        width=largeur_journal(res, minimum=LARGEUR_JOURNAL),
        no_color=True,
        color_system=None,
        force_terminal=False,
        highlight=False,
        emoji=False,
        soft_wrap=False,
    )
    console.print(f"Journal du test d'intégration {res.identifiant} — cfd-validation {res.environnement.versions.get('cfd-validation', '?')}")
    console.print(f"Écrit le {res.environnement.date} (UTC). Ce fichier est généré : ne pas l'éditer.")
    console.print()
    rendre_integration(console, res, lignes_max=None, complet=True)
    if pieces:
        t = Table(title="Pièces produites (SHA-256)", title_justify="left", header_style=theme.ENTETE,
                  box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False)
        t.add_column("Pièce")
        t.add_column("SHA-256")
        for piece in pieces:
            nom = str(piece.relative_to(racine)) if racine is not None and piece.is_relative_to(racine) else str(piece)
            t.add_row(nom, sha256_fichier(piece) if piece.exists() else "—")
        console.print(Padding(t, (1, 0, 0, 2)))
    texte = "\n".join(ligne.rstrip() for ligne in tampon.getvalue().splitlines()) + "\n"
    p.write_text(texte, encoding="utf-8")
    return p
