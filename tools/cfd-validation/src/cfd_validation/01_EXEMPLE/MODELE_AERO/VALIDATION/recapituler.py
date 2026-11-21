#!/usr/bin/env python3
"""Récapitulatif de la validation : un test par ligne, conforme ou non, et à combien de pour cent.

    python recapituler.py SORTIE 01_LECTURE_TABLES:0 02_AUTRE:2 …

Appelé par RUN_VALIDATION.sh, qui lui passe chaque test et son code de retour
(0 conforme, 2 non conforme, autre : le script a échoué). Lit le
``resume.json`` que chaque test a écrit dans ``SORTIE/<TEST>/`` et écrit
``SORTIE/RECAP.txt``. Bibliothèque standard seulement.

Code de retour : 0 si tous les tests sont conformes, 1 sinon.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LARGEUR = 78


def _pourcent(bons: int, total: int) -> str:
    if total == 0:
        return "—"
    if bons == total:
        return "100 %"
    p = 100.0 * bons / total
    return f"{min(p, 99.9):.1f} %"  # jamais « 100 % » tant qu'une valeur manque


def _ligne_test(nom: str, code: int, sortie: Path) -> tuple[bool, list[str]]:
    """(conforme, lignes du récapitulatif) pour un test."""
    resume_json = sortie / nom / "resume.json"
    if code not in (0, 2) or not resume_json.exists():
        return False, [f"{nom:<22s} ERREUR        le script a échoué (code {code}) : voir SORTIE/{nom}.txt"]
    r: dict[str, Any] = json.loads(resume_json.read_text(encoding="utf-8"))
    conforme = bool(r.get("conforme")) and code == 0
    lignes = []
    tables = r.get("tables")
    if isinstance(tables, list):  # test de lecture de table
        appels = sum(int(t["appels"]) for t in tables)
        bons = appels - sum(int(t["echecs"]) for t in tables)
        ok = sum(bool(t["conforme"]) for t in tables)
        lignes.append(f"{nom:<22s} {'CONFORME' if conforme else 'NON CONFORME':<13s} "
                      f"{ok}/{len(tables)} tables, {appels} appels".ljust(62) + f"{_pourcent(bons, appels):>9s}")
        for t in tables:
            if not t["conforme"]:
                lignes.append(f"{'':<22s}   ✗ {t['nom']} : {t['echecs']}/{t['appels']} en échec")
    else:  # autre contrôle : le verdict seul
        lignes.append(f"{nom:<22s} {'CONFORME' if conforme else 'NON CONFORME':<13s} {r.get('verdict', '')}")
    return conforme, lignes


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 1
    sortie = Path(argv[0])
    tests = [(a.rsplit(":", 1)[0], int(a.rsplit(":", 1)[1])) for a in argv[1:]]

    corps: list[str] = []
    n_ok = 0
    for nom, code in tests:
        ok, lignes = _ligne_test(nom, code, sortie)
        n_ok += ok
        corps += lignes
    tout = n_ok == len(tests)
    date = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    texte = "\n".join([
        "=" * LARGEUR,
        f"RÉCAPITULATIF DE LA VALIDATION — {date} (UTC)",
        "=" * LARGEUR,
        f"{'Test':<22s} {'Verdict':<13s} {'Détail'.ljust(25)}{'Conformes':>9s}",
        "-" * LARGEUR,
        *corps,
        "-" * LARGEUR,
        f"{n_ok}/{len(tests)} tests conformes — " + ("TOUT EST À 100 %" if tout else "À REPRENDRE"),
        "=" * LARGEUR,
    ]) + "\n"
    (sortie / "RECAP.txt").write_text(texte, encoding="utf-8")
    print(texte, end="")
    return 0 if tout else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
