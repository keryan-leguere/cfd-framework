"""Lire une table de résultats depuis un fichier, sans perdre un bit.

Pour un test d'intégration, la lecture fait partie de la chaîne mesurée : un
CSV relu avec l'analyseur par défaut de pandas peut s'écarter d'un ULP de ce
qui a été écrit, et cet écart serait mis au compte du code. Les CSV sont donc
relus exactement (``float_precision="round_trip"`` avant pandas 3, le défaut
depuis) : un flottant écrit par Python, ou avec 17 chiffres significatifs,
revient identique. Le test ``test_csv_relu_au_bit_pres`` le vérifie.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

__all__ = ["EXTENSIONS", "ErreurLecture", "lire_dossier", "lire_table", "lire_yaml"]

#: Extensions reconnues.
EXTENSIONS = (".csv", ".tsv", ".txt", ".dat", ".parquet", ".feather", ".pkl", ".pickle")


# pandas < 3 : l'analyseur par défaut peut s'écarter d'un ULP, il faut le demander
# explicitement ; pandas ≥ 3 lit exactement par défaut et déprécie l'option.
_PANDAS_AVANT_3 = int(pd.__version__.split(".")[0]) < 3


class ErreurLecture(ValueError):
    """Fichier introuvable, format inconnu ou illisible."""


def lire_table(chemin: str | Path, *, sep: str | None = None) -> pd.DataFrame:
    """Une table depuis CSV/TSV, Parquet, Feather ou pickle pandas.

    ``sep`` force le séparateur d'un fichier texte ; à défaut : tabulation pour
    ``.tsv``, virgule pour ``.csv``, et détection automatique pour ``.txt``/``.dat``.

    Un pickle exécute du code à la lecture : ne relisez que les vôtres.
    """
    p = Path(chemin)
    if not p.is_file():
        raise ErreurLecture(f"fichier introuvable : {p}")
    ext = p.suffix.lower()
    try:
        if ext in (".csv", ".tsv", ".txt", ".dat"):
            if sep is None:
                sep = {".csv": ",", ".tsv": "\t"}.get(ext)
            if sep is None:
                return pd.read_csv(p, sep=None, engine="python")
            if _PANDAS_AVANT_3:
                return pd.read_csv(p, sep=sep, float_precision="round_trip")
            return pd.read_csv(p, sep=sep)
        if ext == ".parquet":
            return pd.read_parquet(p)
        if ext == ".feather":
            return pd.read_feather(p)
        if ext in (".pkl", ".pickle"):
            objet = pd.read_pickle(p)
            if not isinstance(objet, pd.DataFrame):
                raise ErreurLecture(f"{p} ne contient pas un DataFrame ({type(objet).__name__})")
            return objet
    except ImportError as erreur:
        raise ErreurLecture(f"lecture de {p} impossible : {erreur} (pip install pyarrow)") from None
    except (OSError, ValueError, pd.errors.ParserError) as erreur:
        if isinstance(erreur, ErreurLecture):
            raise
        raise ErreurLecture(f"lecture de {p} impossible : {erreur}") from None
    raise ErreurLecture(f"format inconnu : {p.name} (reconnus : {', '.join(EXTENSIONS)})")


def lire_dossier(
    dossier: str | Path,
    motif: str = "*.csv",
    *,
    sep: str | None = None,
    renommer: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
    colonne_fichier: str | None = "fichier",
) -> pd.DataFrame:
    """Toutes les tables d'un dossier (``motif``, ordre alphabétique), mises bout à bout.

    Chaque fichier est lu par :func:`lire_table` (exactement), passé à
    ``renommer`` s'il est donné — c'est là qu'on ramène des en-têtes d'un autre
    outil aux noms attendus —, puis tous doivent avoir **les mêmes colonnes** :
    une colonne qui manquerait à un fichier deviendrait des NaN sans prévenir.
    ``colonne_fichier`` (``None`` pour s'en passer) ajoute en tête le nom du
    fichier de chaque ligne. ``attrs["fichiers"]`` donne ``{nom: sha256}``.
    """
    d = Path(dossier)
    if not d.is_dir():
        raise ErreurLecture(f"dossier introuvable : {d}")
    chemins = sorted(p for p in d.glob(motif) if p.is_file())
    if not chemins:
        raise ErreurLecture(f"aucun fichier {motif} dans {d}")
    morceaux: list[pd.DataFrame] = []
    colonnes: list[Any] = []
    for chemin in chemins:
        df = lire_table(chemin, sep=sep)
        if renommer is not None:
            df = renommer(df)
        if not morceaux:
            colonnes = list(df.columns)
        elif set(df.columns) != set(colonnes):
            manque = sorted(set(colonnes) - set(df.columns), key=str)
            en_plus = sorted(set(df.columns) - set(colonnes), key=str)
            raise ErreurLecture(
                f"{chemin.name} : colonnes différentes de {chemins[0].name}"
                + (f" — manquantes : {', '.join(map(str, manque))}" if manque else "")
                + (f" — en plus : {', '.join(map(str, en_plus))}" if en_plus else "")
            )
        df = df[colonnes]  # l'ordre du premier fichier
        if colonne_fichier is not None:
            if colonne_fichier in df.columns:
                raise ErreurLecture(f"{chemin.name} a déjà une colonne « {colonne_fichier} » (colonne_fichier=)")
            df.insert(0, colonne_fichier, chemin.name)
        morceaux.append(df)
    tout = pd.concat(morceaux, ignore_index=True)
    tout.attrs["fichiers"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in chemins}
    return tout


def lire_yaml(chemin: str | Path) -> Any:
    """Le contenu d'un fichier YAML."""
    p = Path(chemin)
    if not p.is_file():
        raise ErreurLecture(f"fichier introuvable : {p}")
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as erreur:
        raise ErreurLecture(f"{p} n'est pas un YAML valide : {erreur}") from None
