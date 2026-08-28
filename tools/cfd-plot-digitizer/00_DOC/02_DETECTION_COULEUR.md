# Détection automatique d'une courbe par sa couleur

C'est la fonction centrale de l'outil : on désigne une couleur, l'outil rend la
courbe. Ce document explique comment, et surtout **quand cela échoue**.

## 1. Le critère de couleur : deux tolérances, pas une

Un traceur ne dessine pas un trait uniforme. L'anticrénelage fond les bords du
trait dans le fond : un trait rouge de 2 px sur fond blanc produit un cœur
rouge vif entouré de rose de toutes les nuances.

Une distance unique en RVB force alors un compromis intenable : trop serrée,
elle ne retient que le cœur — la courbe s'amincit et se troue ; trop large, elle
avale le fond.

L'observation qui débloque : l'anticrénelage change surtout la **clarté**, très
peu la **teinte**. On convertit donc chaque pixel en CIE L\*a\*b\* et on
applique deux critères indépendants :

| Réglage | Grandeur | Ce qu'il fait |
|---------|----------|---------------|
| Tolérance de teinte | distance dans le plan (a\*, b\*) | distingue les courbes entre elles |
| Tolérance de clarté | écart sur L\* | absorbe l'anticrénelage |

Un pixel est retenu si **les deux** passent.

L\*a\*b\* n'est pas un raffinement gratuit : c'est un espace approximativement
uniforme, où une même distance correspond à peu près au même écart perçu, ce
qui n'est pas du tout le cas en RVB. Un réglage trouvé sur une courbe bleue
vaut donc à peu près pour une courbe orange.

### Le cas des courbes noires et grises

Pour un trait noir sur fond blanc, a\* et b\* valent zéro des deux côtés : la
teinte ne discrimine rien du tout. **Seule la clarté travaille.** Il faut donc
la resserrer (20 à 30), et non l'élargir. C'est le seul réglage vraiment
contre-intuitif de l'outil, et la raison pour laquelle les deux tolérances sont
exposées séparément plutôt que fondues dans un unique « seuil ».

## 2. Du masque aux points : le balayage

Les pixels retenus forment un masque binaire. Reste à en tirer une courbe.

L'outil balaye le masque **ligne par ligne** — soit colonne par colonne, soit
rangée par rangée — et repère dans chaque ligne les **suites contiguës** de
pixels retenus. Un trait d'épaisseur `e` traversant une colonne y laisse un
segment de longueur voisine de `e` ; le point cherché est son **centre**.

Prendre le centre plutôt que le premier pixel rencontré divise l'erreur par
deux et supprime un biais systématique vers le haut du trait. Sur les figures
d'essai, l'écart médian à la courbe vraie est de l'ordre de **0,1 à 0,5 pixel**.

### Trois politiques quand une ligne porte plusieurs segments

| Mode | Comportement | Pour quoi |
|------|--------------|-----------|
| `moyenne` | un point par ligne, barycentre des segments pondéré par l'épaisseur | le cas courant : une courbe isolée |
| `tous` | un point par segment | nuages de points, courbes repliées, plusieurs branches |
| `suivi` | une seule branche, choisie par continuité | deux courbes de **même couleur** qui se croisent |

Le mode `suivi` ne se contente pas de prendre le segment le plus proche du
précédent : à un croisement, les deux branches sont à égale distance et le choix
serait un tirage au sort. Il compare donc à une **prédiction** — dernière
position prolongée par la pente locale lissée. La courbe garde sa direction et
traverse le croisement sans changer de branche.

## 3. L'orientation du balayage : le piège le plus coûteux

Le balayage en colonnes suppose que la courbe est une fonction `y = f(x)` :
un seul `y` par `x`. Beaucoup de tracés d'aérodynamique ne le sont pas.

Une **polaire** `Cz(Cx)` est un arc couché : à un même `Cx` correspondent deux
`Cz`. Balayée en colonnes, chaque colonne contient deux segments, et le mode
`moyenne` rend leur milieu — c'est-à-dire une courbe entièrement fausse, qui
suit l'axe de l'arc au lieu de l'arc.

Il n'y a rien à régler dans les tolérances : **il faut changer d'orientation.**
Balayée en lignes, la polaire redevient une fonction à une seule valeur et se
lit exactement.

> **Règle** : balayer perpendiculairement à la courbe. En colonnes pour une
> courbe qui monte ou descend franchement, en lignes pour une courbe couchée.

### Ce qui reste, même bien orienté

Là où la courbe devient **parallèle** à la direction de balayage, une ligne la
traverse en biais et rencontre un long segment, dont le milieu n'est plus tout
à fait le point de la courbe. Cela se voit sur les deux figures d'essai :

- le départ très raide d'une décroissance exponentielle en semi-log ;
- le haut d'une polaire, où `dCx/dCz` devient grand.

L'écart y monte à 1 ou 2 pixels, contre 0,1 à 0,5 ailleurs. Aux **bornes des
axes** s'ajoute le rognage du tracé par le cadre : le trait y est coupé, et le
milieu de ce qu'il en reste est décalé. Ces deux effets sont mesurés et
verrouillés par la suite d'intégration.

## 4. Restreindre : zone d'analyse et exclusions

### La zone

Restreindre la détection au cadre du tracé écarte d'emblée les axes, le titre,
les étiquettes. C'est le premier réflexe.

### L'exclusion — indispensable pour la légende

Une **légende** contient un segment de la couleur **exacte** de chaque courbe.
Aucun réglage de tolérance ne peut l'en distinguer : c'est la même couleur.
Et aucun rectangle d'analyse ne peut à la fois couvrir tout le tracé et éviter
une légende posée à l'intérieur.

D'où les **rectangles d'exclusion** : des zones simplement ignorées. Sur la
figure de convergence livrée en exemple, oublier d'exclure la légende fait
passer l'erreur de 0,03 % à **1,9 décade** — trois ordres de grandeur. C'est de
loin la cause d'erreur la plus fréquente, et la moins visible : les points
parasites se fondent dans le lot.

## 5. Nettoyer

| Réglage | Effet |
|---------|-------|
| Pas | ne balaye qu'une ligne sur *n* — pour alléger sans perdre la forme |
| Épaisseur min. | ignore les segments plus courts : élimine poussières et pointillés isolés |
| Épaisseur max. | ignore les segments plus longs : écarte aplats, bandeaux, zones remplies |
| Allègement | simplification de Douglas-Peucker, en pixels |

L'**allègement** mérite un mot. Une détection produit un point par ligne de
balayage, soit souvent plusieurs centaines pour une courbe qui en demanderait
vingt. Douglas-Peucker supprime les points dont le retrait ne déplace le
polyligne que de moins de la tolérance donnée. À 0,5 px la forme est
visuellement inchangée et le nombre de points divisé par cinq ou dix.

Attention : la garantie porte sur la distance **perpendiculaire** au polyligne.
Sur une portion raide, l'écart *vertical* vaut cette distance divisée par le
cosinus de la pente, et dépasse donc la tolérance sans que l'algorithme soit en
défaut.

## 6. Régler en pratique

1. Cadrer la **zone** sur le tracé, **exclure la légende**.
2. Prélever la couleur à la **pipette**, sur le cœur du trait. La pipette
   moyenne une fenêtre 3×3 : sur un trait fin, un pixel isolé est presque
   toujours un pixel de bord, donc un mélange trait/fond qui fausse la cible.
   *Maj+clic* prend au contraire la teinte la plus éloignée du fond dans la
   fenêtre — utile quand on a cliqué juste à côté du trait.
3. Activer l'**aperçu du masque** : les pixels retenus s'affichent en magenta.
   Régler les tolérances en le regardant, pas en regardant le résultat. La
   courbe doit apparaître continue, sans que le fond ne s'allume.
4. Choisir l'**orientation**, puis le **mode**.
5. Détecter, et lire les statistiques : `lignes retenues / lignes vues` dit
   immédiatement si la courbe a été suivie sur toute sa longueur.

Le bouton **« Proposer les couleurs du graphique »** court-circuite l'étape 2 :
il quantifie la zone, écarte le fond (le plus gros amas) et les nuances trop
voisines, et propose directement les teintes des courbes présentes.

## 7. Ce que l'automatique ne fera pas

- **Courbes en pointillés** : chaque tiret est un segment isolé ; le résultat
  est troué. Baisser l'épaisseur minimale aide, pointer à la main reste souvent
  plus rapide.
- **Deux courbes de même couleur qui se superposent** sur une portion : aucune
  information ne permet de les séparer là où elles sont confondues.
- **Fond texturé, tramé ou photographié** : le critère suppose des aplats.
- **Courbe de la couleur de la grille** : à traiter par la zone et l'épaisseur
  maximale, pas par la couleur.

Dans tous ces cas, l'outil de pointage manuel reste disponible, avec la loupe,
et les deux se mélangent librement dans une même série.
