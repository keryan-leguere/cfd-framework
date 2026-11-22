# Test d'interpolation de table, et les polaires

## 1. La question

Le code lit juste ses tables sur les nœuds (test de lecture) et fait ce qu'on
lui demande au-delà des bornes (test des bornes). Reste l'essentiel de son
domaine, l'**intérieur des mailles** : entre deux nœuds, rend-il
l'interpolation de la table ? Une recherche de maille décalée, un poids mal
écrit, un plus proche nœud à la place d'une interpolation, un terme croisé
oublié laissent les nœuds intacts, et donc passent la lecture (vérifié : § 7).

Le schéma attendu est l'interpolation **multilinéaire** : linéaire par axe,
produit des poids sur les 2ᵈ coins de la maille. C'est celui du modèle
d'exemple et des codes tabulés usuels.

## 2. Les points : deux groupes

Pour chaque table, les points se rangent en **groupes**, chacun une ligne du
rapport :

| Groupe | Points | Ce qu'il voit |
|--------|--------|---------------|
| un par axe (`mach`, `alpha`…) | l'axe dans chacune de ses mailles à `t` = ¼, ½, ¾ ; les autres axes sur **tous** leurs nœuds | l'interpolation le long de l'axe, maille par maille |
| `centres` (dès 2 axes) | le centre de chaque maille, tous les axes à `t` = ½ | le **couplage** entre axes : les 2ᵈ coins pèsent autant |

Un point est placé par sa fraction `t` dans la maille, `x = (1 − t)·g[i] +
t·g[i+1]` (`core/mailles.py`) : la forme même de l'interpolation, si bien que
`t` = 0 et 1 retombent exactement sur les nœuds.

| Table | Groupes par axe | Centres | Appels |
|-------|-----------------|---------|--------|
| 2D 7×7 | 2 × 6 mailles × 3 fractions × 7 nœuds = 252 | 36 | 288 |
| 1D 7 | 6 × 3 = 18 | — | 18 |
| 5D 5⁵ | 5 × 4 × 3 × 625 = 37 500 | 1 024 | 38 524 |

Pourquoi les centres ? Une somme d'interpolations 1D autour du coin bas,
`V(i,j) + t·ΔV_x + u·ΔV_y`, est **exacte** dès que l'un des axes est sur son
nœud bas (`u = 0`) : la plupart des points des groupes par axe ne la voient
pas. Au centre, il lui manque `t·u·(V₁₁ − V₁₀ − V₀₁ + V₀₀)`, partout.

`fractions=` change les positions dans la maille ; `centres=False` retire le
groupe des centres.

Chaque ligne du CSV porte la **maille** de son point, en indices de base 1
comme le Fortran : `3-4` (entre les nœuds 3 et 4 de l'axe), et pour les centres
une maille par axe, `2-3 4-5`. Le rapport donne les mailles en échec : une
faute confinée à une maille (un nœud mal trié, une borne de boucle) se localise.

## 3. L'oracle et l'observé

**Attendu.** L'interpolation multilinéaire de la table au point
(`core/bornes.interpoler`, le même oracle que le test des bornes ; dans la
grille, la consigne de bord ne joue pas). Vérifiée indépendamment : sur une
table tirée d'une fonction multilinéaire, elle rend la fonction exacte.

**Observé.** Chaque groupe est comparé à l'attendu **et aux coins de la
maille** de chaque point :

| Observé | Sens |
|---------|------|
| `linéaire` | le code interpole, sur tous les points du groupe |
| `palier` | le code rend la valeur d'un coin de la maille : plus proche nœud, nœud bas… |
| `indiscernable` | mailles plates : les coins et l'interpolation coïncident |
| `ni l'un ni l'autre` | autre chose : terme croisé oublié, mauvaise maille, mauvais poids… |
| `sonde non atteinte` | la sonde est restée NaN |

« CM alpha : attendu linéaire, observé palier (126/126 hors tolérance, 6/6
maille(s)) » se lit sans ouvrir un CSV.

## 4. Critère

`|code − attendu| ≤ atol + rtol·|attendu|`. Si la table déclare une tolérance,
c'est la sienne. Sinon `rtol = 1e-12`, `atol = 1e-15`, marquée « défaut » au
rapport : l'oracle refait le calcul du code, `Σ Π (1 − t | t)·V`, mais pas
forcément dans le même ordre d'opérations. Sur le modèle d'exemple, l'écart
maximal est de 5.55e-17 sur les tables 2D (aux centres), de 2.5e-16 sur la 5D.

## 5. Les polaires

Le test trace aussi les **polaires** des tables, par `cfd_plot.batch_plot`
(`report/figures_polaires.py`). Elles ne rendent pas de verdict : elles montrent
d'un coup d'œil ce que les trois tests de table vérifient point par point.

Une polaire est la courbe du code le long d'un axe (l'**abscisse**), les autres
axes fixés sur un de leurs nœuds (une **condition**). Le code y est appelé
finement (`core/mailles.abscisses_polaire`) : les nœuds, 7 points par maille,
et 8 points de chaque côté jusqu'à `ecart × étendue` au-delà des bornes (10 %,
comme le test des bornes ; rien d'un côté `inatteignable`).

| Sur la figure | Ce qu'on vérifie | Test |
|---------------|------------------|------|
| la courbe vermillon passe par les points bleus (nœuds de la table) | la lecture | 1 |
| elle est droite entre deux points | l'interpolation | 3 |
| dans les zones grisées, elle est plate (`sature`) ou prolonge la dernière maille (`extrapole`) | la consigne hors bornes | 2 |

La consigne déclarée est écrite dans chaque zone grisée, les bornes sont en
pointillés.

**Avec `batch_plot`.** Chaque (table, abscisse) est un appel de `batch_plot` :
deux sources dans `configuration_dict` — `code` (trait vermillon, la courbe
dense) et `table` (points bleus, les nœuds) —, l'abscisse dans `sweep_dict`, les
autres axes dans `flight_point_dict`, qui en fait une arborescence ::

    POLAIRES/CM/POLAIRE_ALPHA/MACH_0.8/CM_vs_alpha.svg

Un crochet `on_before_save` (`HabillagePolaire`, une dataclass gelée, donc
sérialisable : `n_jobs` garde ses processus) ajoute les zones hors bornes,
leur consigne, la légende et les titres en français.

**Superposition.** Avec `superposer=True` (défaut), le `fold` « overlay » de
`batch_plot` ajoute, par abscisse, une figure où toutes les valeurs d'un axe de
condition sont superposées — `SUPERPOSITION/CM_vs_alpha_by_MACH.svg` : une
couleur par valeur, le trait pour le code, les points pour la table. C'est la
figure qu'on lit en premier ; les figures par condition servent à regarder de
près.

**Quelles polaires.** Par défaut, toutes : chaque axe en abscisse, chaque
combinaison de nœuds des autres axes. C'est raisonnable en 2D (7 × 7 : 14
courbes, 16 figures) et déraisonnable en 5D (5⁵ : 3 125 courbes). Au-delà de
`courbes_max` (200) la table est refusée, avec la façon de la restreindre :

```python
Polaires(
    abscisses=("alphat", "phia", "dm"),               # axes tracés en abscisse
    noeuds={"mach": [1.0], "alphat": [0.0, 10.0, 20.0],
            "phia": [0.0, 90.0], "dn": [0.0]},       # nœuds retenus quand l'axe est une condition
    superposer="dm",                                  # l'axe superposé (défaut : le premier qui varie)
)
```

`noeuds` ne restreint un axe que quand il est une condition : en abscisse, un
axe est toujours parcouru de part en part.

**Libellés.** `libelles={"alpha": (r"$\alpha$", "°"), "CX": "$C_X$"}` donne le
nom affiché (mathtext) et l'unité de chaque axe et de chaque table ; sans
libellé, le nom de la colonne.

`tracer_polaires_tables(tables, evaluer, defauts, sortie, polaires=…)` trace les
polaires seules, sans test.

## 6. Pièces

| Pièce | Contenu |
|-------|---------|
| `interpolation_tables.log` | Le rapport complet : identification, spécification (points, attendu, observé, tolérances justifiées), résultats par groupe, tous les points en échec avec leur maille, les polaires tracées, verdict, SHA-256 de toutes les pièces (polaires comprises). |
| `resume.json` | Le même, en types JSON, plus `polaires[]`. Les clés `tables[].nom / appels / echecs / conforme` sont celles que lit le récapitulatif de `VALIDATION/`. |
| `RESULTATS/<NOM>.csv` | Un appel par ligne : `groupe`, `point`, `maille`, `fraction`, colonnes de la table, entrées injectées, `valeur_ATTENDUE`, `valeur_CODE`, `ecart`, `ulp`, `marge`, `statut`, `conforme`. |
| `POLAIRES/<NOM>/POLAIRE_<AXE>/…` | Les polaires, une par condition, et `SUPERPOSITION/`. SVG, profil « paper ». |

Au terminal, les polaires se résument en une ligne (« 121 figures ») ; le
journal les liste toutes.

## 7. Éprouvé sur le vrai code

Deux fautes injectées dans une copie du Fortran, chaque copie compilée sous
son propre nom, et les trois tests lancés dessus :

| Faute | Lecture (1) | Bornes (2) | Interpolation (3) |
|-------|-------------|------------|-------------------|
| `CHERCH` rend `T = 0` dans la grille (palier : nœud bas) | 2D et 1D conformes ; DCMG non conforme | 2D et 1D conformes ; DCMG non conforme | **les 8 tables** : « observé palier » sur chaque axe |
| `INTE2D` sans terme croisé (somme de deux interpolations 1D) | 5 tables 2D sur 6 (un nœud d'angle) ; **CL conforme** | 5 sur 6 ; **CL conforme** | **les 6 tables 2D**, CL comprise : « observé ni l'un ni l'autre », 32/36 centres pour CL |

Dans le premier cas, les tables 2D et la 1D ne sont prises que par
l'interpolation. DCMG est prise partout : l'aller-retour (alphaT, phiA) → (α,
β) → (alphaT, phiA) ne retombe pas exactement sur le nœud, un rien sous lui, et
le palier rend alors le nœud précédent. Dans le second, la somme 1D n'est
fausse sur un nœud qu'au coin haut de la table : CL y vaut ce que la somme
rend, et seuls ses centres la trahissent.

Le scénario `--defaut` du script d'exemple simule côté Python un palier sur CM
(alpha arrondi au nœud le plus proche) : « CM alpha : attendu linéaire, observé
palier », « CM centres : … ni l'un ni l'autre », et un escalier sur la polaire
superposée de CM.

## 8. API

```python
from cfd_validation import Polaires, valider_interpolation_tables

res = valider_interpolation_tables(
    tables, evaluer=modele.calculer_df, defauts=DEFAUTS,
    fractions=(0.25, 0.5, 0.75), centres=True,
    polaires={"DCMG": Polaires(...)}, libelles=LIBELLES, superposer=True, n_jobs=4,
    identifiant="VAL-TAB-03", metadonnees={...}, sortie="INTERPOLATION_TABLES",
)
res.conforme, res.motifs_non_conformite, res.tables[0].groupes
```

`verifier_interpolation` fait le même calcul sans rien afficher ni écrire.
Exemple complet :
`src/cfd_validation/01_EXEMPLE/MODELE_AERO/VALIDATION/03_INTERPOLATION_TABLES/03_interpolation_tables.py`.
