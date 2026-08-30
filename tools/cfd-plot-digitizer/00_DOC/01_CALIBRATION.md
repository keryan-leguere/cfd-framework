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

## Détection automatique du cadre

Le bouton **« Détecter le cadre automatiquement »** place les quatre repères
sans un clic sur l'image. Il ne lit aucune valeur — il n'y a pas d'OCR ici —
mais c'est le pointage, pas la frappe, qui coûte du temps et de la précision :
un repère posé trois pixels à côté de l'axe fausse *toutes* les valeurs
exportées, et rien ne le signale.

La méthode (`app/js/15_cadre.js`) tient en quatre étapes :

1. **Couleur de fond** = la couleur la plus fréquente de l'image, le papier.
2. **Masque d'encre** = tout pixel qui s'en écarte de plus de 40 sur un canal.
3. **Profils** : nombre de pixels d'encre par colonne, puis par ligne. Un axe
   est un trait plein d'un bord à l'autre du tracé : il domine son profil de
   très loin. Une courbe ne contribue qu'un ou deux pixels par colonne, une
   étiquette de graduation guère plus.
4. Les colonnes (resp. lignes) au-dessus du seuil sont **regroupées en traits** :
   deux voisines appartiennent au même axe, sans quoi un axe tracé à 1,5 px de
   large donnerait deux bords là où il n'y en a qu'un.

Le seuil est double — dominer le profil **et** couvrir au moins 35 % de
l'étendue encrée. La première condition suffirait sur une figure encadrée ; la
seconde empêche une image sans le moindre axe, un nuage de points nu, de
promouvoir sa colonne la plus dense au rang de bord.

### Les planches sans cadre fermé

Beaucoup de figures ne tracent que deux axes, l'ordonnée à gauche et l'abscisse
en bas. Le profil ne livre alors qu'un seul pic par direction, et deux pièges
s'ouvrent :

- **Duquel des deux bords s'agit-il ?** Le prendre pour le premier serait faux
  une fois sur deux : l'abscisse serait décrétée bord *supérieur*, ce qui
  replie le cadre sur une ligne et rend la calibration dégénérée. C'est la
  position du trait dans l'encre qui tranche, sans préjugé.
- **Où est le bord d'en face ?** Sur l'**étendue** du trait trouvé : la ligne
  d'axe du bas court exactement sur la largeur du tracé, donc son premier et
  son dernier pixel donnent les bords gauche et droit. Ce repli est ce qui
  évite de retomber sur la boîte englobante de l'encre — laquelle inclut le
  titre et les étiquettes, et déborde donc largement du cadre.

Le résultat reste une **proposition**. Le panneau affiche une *confiance* : la
part des quatre côtés vus comme de vrais traits (100 % pour une figure
encadrée). En dessous de 60 %, il invite explicitement à vérifier.

Mesuré sur les trois figures matplotlib de `exemples/`, les quatre bords
tombent à **moins de 2 px** des axes réellement tracés, et la calibration qui
en découle reste à moins de 0,6 % de l'étendue de la calibration parfaite —
soit le niveau d'un pointage manuel soigné.

## X1 et Y1 au même point

La case **« X1 et Y1 au même point (coin d'origine) »**, cochée par défaut,
lie les deux repères : placer l'un place l'autre, et le balayage automatique
saute `Y1`. Trois repères à poser au lieu de quatre.

C'est la géométrie de la quasi-totalité des figures, et la lier vaut mieux que
la laisser au hasard : deux repères censés être confondus mais posés à un pixel
l'un de l'autre introduisent un cisaillement parasite dans la calibration, que
rien n'affiche.

Décocher la case libère `Y1` — pour un axe décalé, une échelle brisée, ou une
planche où l'origine n'est tout simplement pas au coin.

## Corriger une position au clavier

La colonne **Position px** est un champ de saisie, pas un affichage : écrire
`84, 315` place le repère au pixel exact, ce qu'un clic ne garantit jamais.
C'est aussi la façon de reporter une position lue ailleurs, ou de décaler un
repère d'un pixel sans repartir à la souris.

## Conseils de pointage

- Viser des **graduations franches** (les grands traits étiquetés), pas des
  points de la courbe.
- Écarter au maximum `X1` de `X2` et `Y1` de `Y2` : l'erreur relative de
  calibration est inversement proportionnelle à cet écart.
- Utiliser la **loupe** : elle est là précisément pour viser le centre d'un
  trait de graduation à mieux qu'un pixel.
- `X1` et `Y1` peuvent être le même point (l'origine) : c'est le cas courant,
  et la case dédiée le fait pour vous.

## Corriger après coup

Les points des séries sont mémorisés **en coordonnées pixel**, jamais en unités
physiques. Si une valeur de repère a été mal saisie, il suffit de la corriger :
toutes les séries se recalculent, sans repointer quoi que ce soit. C'est
l'objet du test « recalibrer suffit à corriger toutes les séries ».
