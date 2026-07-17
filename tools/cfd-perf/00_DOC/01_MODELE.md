Le modèle de scalabilité

> Ce document explique **ce que calcule cfd-perf et pourquoi**. Pour l'utiliser,
> voir [02_GUIDE_UTILISATEUR.md](02_GUIDE_UTILISATEUR.md).

## 1. Le problème

Sur un maillage **fixe**, ajouter des cœurs a deux effets opposés :

- chaque rang a **moins de mailles** à traiter → on gagne du temps ;
- chaque sous-domaine devient **plus petit**, donc son rapport surface/volume
  augmente → chaque rang passe proportionnellement **plus de temps à échanger
  ses halos** en MPI.

Au début le premier effet gagne. Passé un certain point, le second l'emporte et
**le calcul redevient plus lent**. Toute la question « sur combien de cœurs
lancer ? » consiste à situer ce point.

## 2. Le modèle

```
T(Nc) = t_ser  +  t_par / Nc  +  t_comm · Nc^γ
        \_____/    \_________/    \____________/
        plancher    se divise      MPI : croît
        d'Amdahl    (on gagne)     (on perd)
```

| Terme | Signification physique | Effet quand Nc augmente |
|:---|:---|:---|
| `t_ser` | travail jamais parallélisé (E/S, initialisation, réductions) | constant |
| `t_par / Nc` | travail qui se divise parfaitement | ↓ décroît |
| `t_comm · Nc^γ` | coût MPI / échange de halos | ↑ croît |

![Les trois contributions](FIGURES/01_termes_modele.png)

Le minimum de la courbe bleue est exactement le croisement où le gain de
parallélisme est mangé par le coût de communication. **C'est la borne physique
au-delà de laquelle aucune réponse n'a de sens.**

### Grandeurs dérivées

| Grandeur | Formule | Lecture |
|:---|:---|:---|
| Accélération | `S(Nc) = T(Nc_ref) / T(Nc)` | « je vais combien de fois plus vite ? » |
| Efficacité | `E(Nc) = S(Nc) / (Nc / Nc_ref)` | « quelle fraction des cœurs sert vraiment ? » |
| Perte d'efficacité | `1 − E(Nc)` | « quelle fraction je gaspille ? » |
| Durée totale | `T(Nc) × n_iterations / 3600` | heures d'horloge |
| Coût | `durée × Nc` | heures·cœur facturées |

`Nc_ref` est le **point pilote le plus bas**. L'accélération vaut exactement 1
en `Nc_ref` par construction.

> **Pourquoi le terme de communication est indispensable.** Un modèle réduit à
> `t_ser + t_par/Nc` (dit `amdahl` ci-dessous) est monotone décroissant : il ne
> *peut pas* représenter la remontée mesurée à fort nombre de cœurs. Sur les
> données réelles (20 M mailles, calculateur isolé), le modèle complet
> `amdahl+comm` reste à **2,5 % d'erreur max** là où un modèle sans terme MPI
> dérive de plus de 20 % dès que la communication domine.

## 3. L'ajustement

À **γ fixé**, le modèle est *linéaire* en `(t_ser, t_par, t_comm)`. On balaie
donc γ sur une grille (`0,05` à `2,0`) et on résout un moindres carrés linéaire
pour chaque valeur, en gardant la meilleure. Deux détails comptent sur des
données réelles :

1. **Pondération relative.** Les résidus sont pondérés par `1/T_mesuré`, ce qui
   minimise l'erreur *relative*. Sans cela, les points lents à bas nombre de
   cœurs (T grand) écrasent numériquement les points rapides à haut nombre de
   cœurs — précisément ceux qui décident de la réponse.
2. **Coefficients positifs.** Ce sont des temps physiques. La contrainte est
   imposée exactement en énumérant les 7 sous-ensembles actifs possibles : pas
   de solveur itératif, pas de dépendance SciPy.

> **Choix d'implémentation : NumPy uniquement.** Le paquet doit s'installer sur
> un calculateur isolé avec un simple cache de *wheels*.

### Choix automatique du modèle

| Points pilotes | Modèle retenu | Pourquoi |
|:---|:---|:---|
| ≥ 3 | `amdahl+comm` | assez de points pour identifier le terme de communication |
| 2 | `amdahl` (repli) | 3 inconnues, 2 équations : le terme MPI n'est pas identifiable |
| 1 | **erreur** | rien à ajuster |

Forcer un modèle : `--model amdahl` / `--model amdahl+comm`.

## 4. Qualité d'ajustement

La qualité de l'ajustement est un résultat de premier plan, toujours affiché :

| Verdict | Erreur max | Interprétation |
|:---|---:|:---|
| excellent | ≤ 2 % | — |
| bon | ≤ 5 % | comparable à la gigue d'un calculateur réel |
| limite | ≤ 10 % | ajouter des points pilotes |
| mauvais | > 10 % | **ne pas décider sur cette base** |

Le tableau *« Model vs pilot measurements »* du rapport donne l'écart **point par
point** : si la courbe ne suit pas les mesures, cela se voit en chiffres avant
même d'ouvrir la figure.

## 5. Limites connues

- **Scalabilité forte uniquement** (maillage fixe). Pas de scalabilité faible.
- **RANS stationnaire** : on suppose un coût par itération constant. Un LES/URANS
  avec un pas de temps variable sort du cadre.
- **Le nombre d'itérations est une donnée d'entrée**, pas une prédiction : il
  vient de votre expérience du cas. Durée et coût lui sont proportionnels.
- **Mémoire** : on suppose l'empreinte totale fixe, répartie également. La
  duplication des halos rend l'estimation légèrement optimiste à très grand
  nombre de cœurs.
- **Extrapolation** : au-delà de la plage pilote le modèle est signalé comme
  extrapolant (zone ambre sur la figure, avertissement dans le rapport).
- **γ ajusté** absorbe la topologie du réseau, le partitionnement et le solveur.
  Il n'est pas transposable d'une machine à l'autre : **refaire un pilote par
  machine**.
