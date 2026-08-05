# Le générateur de trajectoires

> `cfd-traj generer` produit un lot de trajectoires dispersées crédibles. Cela
> sert à trois choses : disposer d'un exemple exécutable, donner aux tests un
> nuage qui a la structure que la méthode exploite, et permettre d'essayer
> l'outil avant d'avoir ses propres données.

Le modèle ne représente **aucun engin réel** et n'a aucune prétention à la
fidélité. Ce qu'on lui demande est plus modeste : que le nuage produit ait les
bonnes corrélations — Mach, altitude et Reynolds évoluant de concert le long
d'un tir, une traversée transsonique, une incidence pilotée par le guidage et
des braquages qui trimment.

## 1. Le modèle de vol

Point matériel à 3 degrés de liberté, intégré en RK4. État :

```
(vitesse, pente, altitude, distance parcourue, masse)
```

```
 phase propulsée              phase balistique
 ├──────────────┤             ├───────────────────────────────┤
 poussée constante            poussée nulle
 masse décroissante           masse constante
 t < temps_combustion         jusqu'à l'apogée
```

**Poussée** constante pendant la combustion, nulle ensuite. **Masse** décroissant
linéairement, jamais sous la masse à vide.

**Traînée** — coefficient à pic transsonique, caricature de la courbe réelle
mais avec le pic au bon endroit, ce qui est tout ce qui compte pour les bandes
de Mach que l'outil construira ensuite :

```
CD = CD0 · [1 + 1,4·exp(−((M − 1,1)/0,22)²)] / (1 + 0,25·max(M − 1,4, 0))  +  k·α²
```

**Incidence** — un pilote automatique proportionnel suit un programme de pente
qui part de 84° et descend vers 28°, saturé à ±12°. S'y ajoute la contribution
des rafales.

**Rafales** — somme de trois sinusoïdes de périodes et phases distinctes,
d'amplitude décroissant exponentiellement avec l'altitude. Elles alimentent
l'incidence *et* le dérapage ; le dérapage n'a d'ailleurs pas d'autre source,
ce qui le fait s'éteindre proprement quand l'engin monte.

Le vol s'arrête à l'**apogée**. La descente balistique n'apporte rien à un plan
de calcul et c'est là que le modèle est le plus grossier. Comme l'instant
d'apogée dépend de la dispersion, c'est aussi ce qui donne au lot des tirs de
**longueurs différentes** — que le reste du paquet doit savoir encaisser.

### Une note sur l'incidence en fin de vol

L'incidence ne décroît pas monotonement. Après l'extinction, la gravité fait
basculer l'engin plus vite que le programme ne le demande, l'écart croît, et le
pilote automatique sature. On obtient donc de fortes incidences à faible
pression dynamique près de l'apogée. C'est physiquement cohérent pour un engin
non propulsé, et cela donne au nuage une queue que le conditionnement au Mach
sait traiter.

## 2. La dispersion

Elle est appliquée aux **causes**, pas aux résultats. C'est ce qui fait que le
nuage a la forme d'un faisceau de trajectoires et non d'un brouillard : à
l'intérieur d'un tir, Mach, altitude et Reynolds restent liés ; c'est seulement
l'ensemble des tirs qui s'étale.

| Grandeur dispersée | Écart-type | Effet dominant |
|:---|---:|:---|
| niveau de poussée | 4,5 % | apogée, Mach maximal |
| masse | 2,0 % | accélération |
| traînée | 7,0 % | apogée, décélération |
| élévation de tir | 1,8° | forme de la trajectoire |
| amplitude des rafales | log-normale, σ = 0,35 | incidence, dérapage |
| paramètres génériques | log-normale, σ = 0,08 | niveau de chaque colonne |

Sur un lot typique, la dispersion d'apogée obtenue est de l'ordre de 12 %.

## 3. Les colonnes génériques

C'est le point où le générateur tient sa part du contrat de généricité : il
émet **les noms de colonnes qu'on lui donne**, en quantité quelconque, et rien
en aval ne doit les reconnaître autrement que par leurs valeurs.

Six archétypes, choisis pour couvrir les comportements que l'auto-détection des
rôles doit savoir distinguer :

| Archétype | Forme | Rôle attendu à la détection |
|:---|:---|:---|
| `correle_mach` | suit le Mach | `conditionnel` |
| `correle_altitude` | suit l'altitude | `conditionnel` (via le Mach) |
| `rampe` | décroissance monotone | `principal` |
| `plateau_bruite` | constante + bruit blanc | `principal` |
| `sinus_amorti` | oscillation décroissante | `principal` |
| `discret` | deux valeurs, commutation en vol | `discret` |

```bash
# deux colonnes PARA1, PARA2, archétypes cyclés
cfd-traj generer --sortie TRAJ --n-parametres 2

# aucune colonne générique
cfd-traj generer --sortie TRAJ --n-parametres 0

# noms et archétypes choisis
cfd-traj generer --sortie TRAJ --parametres "PRESSION:rampe,TEMP_PAROI:plateau_bruite"
```

Le préfixe `PARA` n'est que la valeur par défaut de `--n-parametres`. Un test
dédié (`tests/test_genericite.py`) vérifie mécaniquement qu'il n'apparaît nulle
part dans les couches qui décident.

## 4. Reproductibilité

Tout passe par un unique `numpy.random.default_rng(graine)`. **Deux appels avec
la même graine produisent des fichiers identiques octet pour octet** — c'est ce
qui rend possible le test de déterminisme de bout en bout.

```bash
cfd-traj generer --sortie A --graine 42
cfd-traj generer --sortie B --graine 42
diff -r A B        # rien
```

## 5. L'étude compagnon

`generer` écrit aussi un `ETUDE.yaml` à côté des CSV, avec tous les réglages par
défaut et les rôles laissés à l'auto-détection. Son `source` est un **motif**
(`tir_*.csv`) et non un répertoire : le fichier d'étude vit à côté des CSV, et
un répertoire avalerait plus tard comme un tir le plan que l'outil y écrit
lui-même.

`--sans-etude` supprime ce comportement.

## 6. Performance

Un tir coûte environ 0,1 s, un lot de 40 tirs environ 5 s. La boucle RK4 est
écrite sur des flottants Python plutôt que sur des tableaux NumPy, et
l'atmosphère est tabulée tous les 50 m : à cette taille de problème, la
machinerie des tableaux coûte un ordre de grandeur de plus que l'arithmétique
qu'elle enveloppe.

## 7. Ce qu'il ne faut pas en attendre

- Ce n'est pas un simulateur de mécanique du vol. Trois degrés de liberté, pas
  de modèle d'attitude, pas de couplage aéroélastique, aucune donnée réelle.
- Les valeurs absolues n'ont pas de sens en soi. Les tests du générateur
  n'assertent d'ailleurs que des propriétés qualitatives — monotonies, unicité
  de l'apogée, ordres de grandeur, reproductibilité.
- Un lot généré ne remplace pas un vrai lot Monte-Carlo pour dimensionner une
  base. Il sert à faire tourner la chaîne, pas à décider.
