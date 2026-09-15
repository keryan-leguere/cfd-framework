# 1. Pourquoi relire une table valide un code

## Le fait sur lequel tout repose

Une table interpolée vaut **exactement** la valeur tabulée à chacun de ses
nœuds.

C'est vrai de toute interpolation — linéaire, spline, Akima, peu importe — et
cela ne dépend d'aucun réglage. Une interpolation qui ne passerait pas par ses
points ne serait pas une interpolation.

Il en découle un contrôle sans échappatoire :

> Évaluez le modèle sur les nœuds de sa propre table. Tout écart est une erreur
> de lecture.

Pas une imprécision, pas un choix de schéma, pas un effet de maillage : une
erreur de lecture. C'est la seule situation, dans toute une chaîne de calcul, où
l'on dispose d'une référence exacte et gratuite — la table *est* sa propre
référence.

## Pourquoi ça vaut la peine

Les erreurs de lecture de table ne se voient pas.

Un code qui indexe le mauvais axe, qui décale son indice de un, qui lit des
degrés là où la table porte des radians, produit des courbes **lisses**. Elles
ont la bonne allure, le bon ordre de grandeur, la bonne monotonie. Elles
passent la revue. Elles sortent en note de calcul. Elles sont fausses.

Trois propriétés rendent ce contrôle rentable :

**Il ne demande aucune référence extérieure.** Pas d'essai en soufflerie, pas de
calcul de référence, pas de code concurrent. La table suffit.

**Il est exhaustif.** On passe par tous les nœuds, pas par un point de vol
choisi. Une panne qui ne touche qu'un coin du domaine est vue comme le reste.

**Son verdict est binaire.** Il n'y a pas de « c'est acceptable » : à un nœud,
soit le modèle rend la valeur tabulée, soit il ne la rend pas.

## Ce qu'il attrape, et ce qu'il n'attrape pas

Il attrape :

- un axe indexé à la place d'un autre ;
- un indice décalé, saturé, ou basé à 0 au lieu de 1 ;
- une unité convertie deux fois, ou pas du tout ;
- un axe qui n'entre pas dans l'indexation ;
- une queue de tableau jamais renseignée, prise pour des données ;
- une table dimensionnée autrement que déclarée.

Il n'attrape pas :

- une table dont les **valeurs** sont fausses. Si la base aérodynamique est
  mauvaise, le code la relira fidèlement, et ce contrôle dira que tout va bien.
  C'est une autre question, qui demande une autre référence ;
- une erreur **d'interpolation entre** les nœuds. Les nœuds sont justes par
  construction ; un schéma qui déraille au milieu d'une maille passerait. Un
  contrôle à mi-maille contre une interpolation de référence est une suite
  naturelle, et ce n'est pas celui-ci ;
- ce qui se passe **hors du domaine tabulé**. L'extrapolation est un choix de
  modélisation, pas une lecture.

## Le déroulé

```
COMMON block ──lire_table──►  table (cadre de données)
                                   │
                            on retire les QOI
                                   │
                                   ▼
                          entrées du modèle  ──► votre modèle ──► QOI rendues
                                   │                                   │
                                   └──────────► comparer ◄─────────────┘
                                                    │
                                          ┌─────────┴─────────┐
                                          ▼                   ▼
                                     diagnostic           planches
```

Le point le plus important de ce schéma est **on retire les QOI**. Un modèle à
qui l'on tend la réponse ne prouve rien. C'est ce retrait qui fait du contrôle
un contrôle, et c'est pour cela que le paquet compose lui-même le cadre
d'entrée plutôt que de laisser l'utilisateur passer sa table telle quelle.

## La tolérance

Par défaut `rtol = 1e-9`, `atol = 1e-12` : une table relue juste l'est au bit
près, ou à un aller-retour en simple précision près si la chaîne d'appel en
impose un.

Desserrer la tolérance est légitime quand le chemin entre la table et la sortie
comporte une conversion d'unité ou un changement de repère. Ce n'est plus
légitime quand cela sert à faire taire un écart qu'on ne s'explique pas : c'est
exactement l'écart que ce contrôle existe pour montrer.

## Ensuite

- [`02_DECLARER_SES_TABLES.md`](02_DECLARER_SES_TABLES.md) — le dictionnaire `TABLES`, clé par clé
- [`03_BRANCHER_SON_MODELE.md`](03_BRANCHER_SON_MODELE.md) — le contrat de votre fonction
- [`04_DIAGNOSTICS.md`](04_DIAGNOSTICS.md) — les huit motifs de panne
- [`05_ENVELOPPER_DU_FORTRAN.md`](05_ENVELOPPER_DU_FORTRAN.md) — f2py, COMMON blocks, calculateur isolé
