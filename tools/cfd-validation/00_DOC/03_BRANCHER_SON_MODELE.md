# 3. Brancher son modèle

C'est la seule pièce que cfd-validation ne peut pas fournir : elle dépend de la
signature de vos routines.

## Le contrat

```python
def appeler(entrees: pd.DataFrame) -> pd.DataFrame: ...
```

**Elle reçoit** un cadre portant les colonnes **indépendantes** de la table, plus
les `constantes` déclarées. Une ligne par nœud de la table, dans l'ordre du
tableau Fortran.

**Elle rend** un cadre de **même longueur**, **dans le même ordre**, portant les
QOI de la table.

**Elle ne trie rien et ne regroupe rien.**

C'est tout. Le reste est votre affaire : le nombre d'appels, la vectorisation,
l'initialisation de la bibliothèque, le cache.

## Le squelette

```python
import pandas as pd
import aero  # votre module f2py

aero.init_tables()  # une fois, pas à chaque appel


def appeler(entrees: pd.DataFrame) -> pd.DataFrame:
    rendu = entrees.copy()
    rendu["CN"] = aero.eval_cn(
        entrees["mach"].to_numpy(),
        entrees["alpha"].to_numpy(),
        entrees["delta"].to_numpy(),
    )
    return rendu
```

Si vos routines ne sont pas vectorisées, la boucle est là :

```python
def appeler(entrees: pd.DataFrame) -> pd.DataFrame:
    valeurs = [aero.eval_cn(ligne.mach, ligne.alpha, ligne.delta) for ligne in entrees.itertuples()]
    return entrees.assign(CN=valeurs)
```

Une table fait typiquement quelques centaines à quelques milliers de nœuds : une
boucle Python y est sans conséquence.

## Ce que vous ne recevez pas

**Les QOI.** Jamais. Un modèle à qui l'on tend la réponse ne prouve rien, et
c'est ce retrait qui fait du contrôle un contrôle.

Si votre fonction a besoin de la valeur tabulée pour travailler, c'est qu'elle ne
relit pas la table : elle la recopie.

## Ce que vous rendez, et ce qui en est fait

Seules les **QOI** de votre cadre sont lues. Les colonnes d'entrée que vous
rendez sont ignorées pour le calcul — mais elles servent à vérifier que vous
n'avez pas réordonné vos lignes, et c'est une vérification qui vaut son prix :

```
table « CN » : le modèle a rendu « mach » = 0.95 à la ligne 0, là où on lui
avait passé 0.3. Le modèle doit rendre ses lignes dans l'ordre reçu — un tri
ou un regroupement dans la chaîne d'appel comparerait chaque point à son voisin.
```

Sans ce refus, un `groupby` ou un `sort_values` glissé dans la chaîne d'appel
ferait sortir le contrôle en rouge sur un modèle juste. C'est le genre de faux
positif qui fait abandonner un outil.

La comparaison et les figures sont bâties sur les colonnes **de la table**, avec
votre QOI greffée dessus. Un aller-retour en simple précision côté Fortran est
donc sans conséquence sur les abscisses — ce qui compte, parce que `batch_plot`
filtre ses points de vol par égalité stricte.

## Les refus, et ce qu'ils veulent dire

| message | cause |
|:--|:--|
| « doit rendre un DataFrame pandas » | vous rendez un tableau, un dict, ou `None` |
| « a reçu N points et en a rendu M » | une ligne perdue ou ajoutée en route |
| « QOI […] absente(s) du cadre rendu » | le nom de la colonne rendue ne correspond pas à `qoi` |
| « dans l'ordre reçu » | un tri ou un regroupement dans la chaîne d'appel |
| « n'est pas numérique » | une colonne de texte, souvent une valeur d'erreur du solveur |

Ce sont des **ruptures de contrat**, pas des écarts : le contrôle ne peut pas
conclure, alors qu'un écart *est* une conclusion. Ils lèvent une `ErreurModele`,
qui hérite de `ValueError`.

## Depuis la ligne de commande

```bash
cfd-validation valider --tables TABLES.yaml --module aero --modele mon_appel:appeler
```

`--modele` désigne l'objet `module:attribut`. `--module` désigne le code
enveloppé : un nom importable, ou le chemin d'un `.so` fraîchement compilé.

## Un modèle qui n'est pas une fonction

Tout appelable convient — une instance, une `functools.partial`, un objet à
`__call__`. C'est utile pour porter l'état d'initialisation :

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Appel:
    module: object
    version_base: str

    def __call__(self, entrees: pd.DataFrame) -> pd.DataFrame:
        return entrees.assign(CN=self.module.eval_cn(...))
```

Un `@dataclass(frozen=True)` de niveau module reste **picklable**, ce qui compte
si vous le passez ailleurs à un pool de processus.
