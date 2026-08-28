# Calibration des axes — du pixel à la grandeur physique

## Ce qu'on cherche

Une image de graphique ne contient que des pixels. Digitaliser, c'est retrouver
l'application qui envoie un pixel `(px, py)` sur un couple de valeurs `(x, y)`.

`cfd-plot-digitizer` cherche cette application sous forme **affine** :

```
u = gx · p + cx        avec  u = x        ou  log10(x)  si l'axe X est logarithmique
v = gy · p + cy               v = y        ou  log10(y)  si l'axe Y est logarithmique
```

où `p = (px, py)`, et où `gx`, `gy` sont deux vecteurs du plan (les *gradients*
des deux coordonnées). Six inconnues en tout.

Pourquoi une affine et non deux simples règles de trois ? Parce qu'une affine
absorbe la **rotation** et le **cisaillement**. Une figure scannée de travers,
photographiée un peu de biais, ou tracée par un logiciel dont les axes ne sont
pas exactement perpendiculaires, reste lisible sans redressement préalable.

## Les quatre repères et l'équation manquante

L'utilisateur ne fournit que quatre points, et pour chacun une seule
coordonnée :

| Repère | Placé sur | Valeur saisie |
|--------|-----------|---------------|
| `X1`   | l'axe X   | sa valeur en x |
| `X2`   | l'axe X   | sa valeur en x |
| `Y1`   | l'axe Y   | sa valeur en y |
| `Y2`   | l'axe Y   | sa valeur en y |

Cela donne deux équations pour `gx` (qui en compte trois avec `cx`) et deux pour
`gy` : le système est sous-déterminé d'un degré de chaque côté.

On le referme avec l'hypothèse qui *définit* un repère cartésien :

> **x est constant le long de l'axe Y, et y est constant le long de l'axe X.**

En notant `ux = X2 − X1` et `uy = Y2 − Y1` (vecteurs en pixels), cela s'écrit :

```
gx · uy = 0            gx · ux = u2 − u1
gy · ux = 0            gy · uy = v2 − v1
```

Deux systèmes 2×2 indépendants, résolus par `Base.resoudre`. Les décalages
suivent : `cx = u1 − gx · X1`, `cy = v1 − gy · Y1`.

Noter ce qui n'est **pas** supposé : que les axes soient perpendiculaires *à
l'écran*. Seule leur indépendance linéaire compte. Un tracé cisaillé se calibre
donc exactement, ce que vérifie le test
« absorbe un cisaillement (axes non orthogonaux à l'écran) ».

## Axes logarithmiques

Un axe logarithmique est traité en amont et en aval, sans toucher au cœur : on
remplace la valeur saisie par son logarithme décimal avant de résoudre, et on
applique `10^u` à la sortie. La transformation intermédiaire reste affine, donc
tout ce qui précède vaut encore.

Conséquence pratique : **un pixel ne vaut pas la même chose partout**. Sur trois
décades étalées sur 500 px, un pixel vaut 1,4 % de la valeur lue, en bas comme
en haut de l'échelle — mais 0,014 unité en bas contre 14 unités en haut. La
barre d'état affiche `Calibration.resolutionLocale`, qui donne cette valeur au
point courant plutôt qu'une résolution globale trompeuse.

## Ce qui est refusé, et pourquoi

`Calibration.verifier` rend une liste de problèmes avant toute résolution :

- **repère non placé ou valeur absente** — le système n'a pas assez d'équations ;
- **deux repères de même valeur** sur un axe — la règle de trois serait une
  division par zéro ;
- **valeur négative ou nulle sur un axe logarithmique** — `log10` n'y est pas
  défini ;
- **deux repères confondus à l'écran** — `ux` ou `uy` est nul ;
- **axes presque parallèles** (moins de 5° entre eux) — le déterminant tend vers
  zéro et l'inversion amplifie démesurément l'erreur de pointage. Placer `X1` et
  `X2` aux deux extrémités de l'axe, pas côte à côte, est la meilleure façon de
  s'en prémunir.

Le seuil de 5° n'est pas décoratif : à 2°, une erreur de pointage d'un pixel se
traduit par plusieurs pour cent d'erreur sur la valeur lue.

## Conseils de pointage

- Viser des **graduations franches** (les grands traits étiquetés), pas des
  points de la courbe.
- Écarter au maximum `X1` de `X2` et `Y1` de `Y2` : l'erreur relative de
  calibration est inversement proportionnelle à cet écart.
- Utiliser la **loupe** : elle est là précisément pour viser le centre d'un
  trait de graduation à mieux qu'un pixel.
- `X1` et `Y1` peuvent être le même point (l'origine), c'est le cas courant et
  parfaitement admis.

## Corriger après coup

Les points des séries sont mémorisés **en coordonnées pixel**, jamais en unités
physiques. Si une valeur de repère a été mal saisie, il suffit de la corriger :
toutes les séries se recalculent, sans repointer quoi que ce soit. C'est
l'objet du test « recalibrer suffit à corriger toutes les séries ».
