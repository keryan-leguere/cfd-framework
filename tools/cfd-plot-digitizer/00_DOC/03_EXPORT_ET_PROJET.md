# Export des données et fichiers de projet

## Séries

Une **série** est une courbe extraite : un nom, une couleur d'affichage et une
liste de points. Un graphique à trois courbes donne trois séries.

Les points d'une série sont mémorisés **en coordonnées pixel**, jamais en
unités physiques. Ce choix a une conséquence directe et précieuse : corriger une
valeur de repère mal saisie recalcule toutes les séries, sans repointer quoi que
ce soit. La conversion en unités physiques n'a lieu qu'au moment de l'export.

Détection automatique et pointage manuel se mélangent librement dans une même
série : on détecte le gros de la courbe, puis on complète à la main les
portions en pointillés ou masquées par un symbole.

### Le marqueur : couleur, forme, taille

Chaque série choisit sa **forme** de marqueur (disque, anneau, carré, losange,
triangle, croix, plus) et sa **taille**, en plus de sa couleur. Ce n'est pas
cosmétique : un disque de deux pixels posé sur un trait noir de deux pixels est
invisible, et c'est exactement là qu'on pointe. Les formes creuses — anneau,
croix, plus — laissent voir la courbe *sous* le marqueur, ce qui est la seule
façon de juger si l'on a visé son centre.

Les nouvelles séries reçoivent une forme tournante en même temps qu'une
couleur : deux séries voisines se distinguent alors même en niveaux de gris, ou
pour un daltonien. L'aperçu du panneau dessine les marqueurs **sur un trait**,
pas sur fond blanc, puisque c'est dans cette situation qu'ils doivent rester
lisibles.

### Gommer en zone

L'outil **Gommer** retire le point le plus proche d'un clic ; en *glissant*, il
retire d'un coup tous les points de la série active contenus dans le rectangle.
C'est le même geste que les rectangles de zone, et c'est le relâchement qui
décide s'il s'agissait d'un clic ou d'une sélection.

Effacer point par point une centaine de pixels captés à tort — une grille prise
pour une courbe, une légende oubliée dans la zone — demandait sinon autant de
clics que de points. L'ordre des points survivants est conservé : réordonner la
série en gommant produirait un tracé en zigzag à la relecture.

## Formats d'export

| Format | Écrit | Bon pour |
|--------|-------|----------|
| **CSV — format long** | une ligne par point, colonne `serie` en tête | pandas, R, tableur ; supporte des séries de longueurs différentes |
| **CSV — colonnes par série** | deux colonnes `x`, `y` par série, côte à côte | lecture humaine, tableur ; les séries courtes sont complétées par des vides |
| **CSV — grille X commune** | une colonne `x`, puis une colonne par série, toutes interpolées | superposer, soustraire, comparer des courbes qui n'ont pas les mêmes abscisses |
| **Texte — deux colonnes** | `x`⇥`y`, un bloc par série | collage direct dans un tableur |
| **JSON** | structure imbriquée avec noms et couleurs | reprise par un script |
| **Python / NumPy** | `import numpy as np` puis un couple de tableaux par série | collage dans un carnet ou un script |
| **MATLAB** | un couple de vecteurs par série | collage dans un script `.m` |

Le panneau présente ces formats en **fiches**, pas en liste déroulante :
chacune porte son résumé, ce à quoi elle sert, et trois lignes du rendu réel.
Le choix engage la suite du travail — tableur, script, fichier d'entrée de
solveur — et se faisait jusqu'ici sur trois mots. Ces fiches vivent dans
`40_export.js` plutôt que dans le HTML : c'est le module qui sait ce qu'il
produit, et l'exemple reste ainsi à côté du code qui l'écrit. Un test vérifie
qu'aucun format n'est sans fiche, et qu'aucune fiche ne décrit un format
disparu.

Les réglages sans effet sont masqués : le **séparateur** ne veut rien dire pour
du JSON, du Python ou du MATLAB. Le drapeau qui pilote cet affichage n'est pas
déclaratif — un test rend chaque format deux fois, avec deux séparateurs, et
exige que le drapeau dise la vérité sur ce qui change.

Sous l'aperçu, une ligne de **bilan** dit ce qui sera écrit avant de l'écrire :
nombre de séries et de points, étendue en x et en y, nom du fichier, nombre de
lignes et taille. De quoi vérifier d'un coup d'œil qu'on exporte bien ce qu'on
croit, plutôt que de le découvrir dans le fichier écrit.

Le **format long** est celui à préférer par défaut. C'est le seul qui reste
correct quand les séries n'ont pas le même nombre de points, ce qui est la règle
plutôt que l'exception après une détection automatique.

### Détails qui évitent des surprises

- **Échappement CSV** conforme au RFC 4180 : un nom de série contenant le
  séparateur, un guillemet ou un retour à la ligne est mis entre guillemets, les
  guillemets internes étant doublés. Un nom comme `Cp, extrados` ne décale donc
  pas les colonnes.
- **Séparateur** au choix — virgule, point-virgule, tabulation. Le
  point-virgule est le bon réflexe pour un tableur configuré en français, où la
  virgule est le séparateur décimal.
- **Identifiants** Python et MATLAB : accents translittérés, caractères
  interdits remplacés, doublons désambiguïsés, jamais de nom commençant par un
  chiffre. `Débit à 20 °C` devient `Debit_a_20_C`.
- **Chiffres significatifs** réglables. Six est un choix honnête : une
  digitalisation vaut trois à quatre chiffres au mieux, en exporter quinze
  n'ajoute que du bruit. La notation exponentielle n'apparaît que hors de la
  plage lisible.

## Grille X commune

Deux courbes digitalisées séparément n'ont **jamais** les mêmes abscisses :
chacune tombe là où ses pixels tombaient. Impossible, en l'état, de les
retrancher l'une de l'autre ni de les mettre côte à côte dans un tableur.

Le format **CSV — grille X commune** ramène toutes les séries sur une seule
abscisse par interpolation linéaire :

```
x,Re = 3e6,Re = 6e6
0.02,0.512,0.498
0.0205,0.531,0.517
```

Trois réglages :

- **Points** — taille de la grille. Digitaliser ne crée pas d'information :
  au-delà du nombre de points réellement extraits, on ne fait qu'interpoler
  plus finement le même tracé.
- **Espacement** — linéaire ou logarithmique. Le second s'impose quand l'axe X
  est lui-même logarithmique, sinon les décades basses sont sous-échantillonnées.
- **Domaine** — *recouvrement commun* (l'intervalle où toutes les séries sont
  définies) ou *étendue totale* (l'union, avec des cellules vides là où une
  série n'existe pas).

Hors du domaine propre d'une série, la cellule reste **vide**. L'outil
n'extrapole jamais : prolonger une courbe au-delà de ce que l'image montre
serait fabriquer des données.

### Ce qui est refusé, et dit

Une série n'est ré-échantillonnable en x que si elle **est une fonction de x**.
Une polaire `Cz(Cx)` ne l'est pas : c'est un arc couché, où un même `Cx` porte
deux `Cz`. L'interpoler en x fondrait ses deux branches en une moyenne sans
signification — et le tableau produit n'aurait l'air de rien de suspect.

L'outil détecte le cas et écarte la série en le disant. Le critère n'est pas le
simple comptage des changements de sens en x : une courbe repliée proprement
n'en compte qu'un, qu'une tolérance au bruit avalerait. Ce sont les **longueurs
des passages monotones** qui tranchent — le bruit de détection produit une nuée
d'allers-retours minuscules, un vrai repli produit deux parcours étendus.

Sont également signalées et écartées les séries de moins de deux points, et le
cas où les domaines ne se recouvrent pas du tout.

## Fichier de projet

**Enregistrer le projet** écrit un `.digit.json` autonome, qui contient :

- l'image, en data URL — le fichier se suffit à lui-même ;
- la calibration : les quatre repères, leurs valeurs, les indicateurs
  logarithmiques ;
- la zone d'analyse ;
- les séries, en coordonnées pixel, avec leur marqueur (forme et taille) et les
  réglages de détection utilisés ;
- les notes libres.

On peut donc poser ce fichier sur une clé, le rouvrir sur une autre machine
hors réseau, et retrouver exactement l'état de travail. Les réglages de
détection étant conservés série par série, un tiers peut voir *comment* chaque
courbe a été obtenue — ce qui compte pour une donnée qui finira dans un rapport.

Un projet enregistré avant l'apparition du marqueur se relit sans lui :
l'interface attribue alors une forme par défaut. C'est vérifié par un test —
un fichier déjà posé sur une clé ne doit pas devenir illisible.

Les positions sont arrondies au centième de pixel : bien au-delà de la précision
du pointage humain, et cela divise par deux la taille du fichier.

### Relecture

`Projet.deserialiser` refuse explicitement plutôt que de produire un état à
moitié valide : fichier qui n'est pas du JSON, fichier d'une autre application,
version de format postérieure à celle que l'outil connaît. Un message clair vaut
mieux qu'une courbe fausse.

À l'intérieur, la lecture est tolérante : points écrits `[x, y]` ou
`{px, py}`, séries sans nom (numérotées automatiquement), champs absents. Un
projet écrit à la main ou par un script reste donc lisible.

## Reprise dans le reste du dépôt

Le CSV en format long se lit directement avec pandas :

```python
import pandas as pd

donnees = pd.read_csv("polaire.csv")
for nom, groupe in donnees.groupby("serie"):
    print(nom, len(groupe))
```

et se trace avec `cfd-plot` comme n'importe quelle autre source :

```python
import cfd_plot

cfd_plot.use_style("paper")
figure, axes = cfd_plot.subplots()
for nom, groupe in donnees.groupby("serie"):
    cfd_plot.plot_line(axes, groupe["x"], groupe["y"], label=nom)
cfd_plot.save_figure(figure, "polaire.png")
```

Une courbe digitalisée sert typiquement de référence expérimentale ou
bibliographique à comparer à un calcul : c'est exactement le cas d'usage du
module `batch.py` de `cfd-plot`, qui superpose des sources CFD, analytiques et
expérimentales sur un même point de vol.
