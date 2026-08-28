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

## Formats d'export

| Format | Écrit | Bon pour |
|--------|-------|----------|
| **CSV — format long** | une ligne par point, colonne `serie` en tête | pandas, R, tableur ; supporte des séries de longueurs différentes |
| **CSV — colonnes par série** | deux colonnes `x`, `y` par série, côte à côte | lecture humaine, tableur ; les séries courtes sont complétées par des vides |
| **Texte — deux colonnes** | `x`⇥`y`, un bloc par série | collage direct dans un tableur |
| **JSON** | structure imbriquée avec noms et couleurs | reprise par un script |
| **Python / NumPy** | `import numpy as np` puis un couple de tableaux par série | collage dans un carnet ou un script |
| **MATLAB** | un couple de vecteurs par série | collage dans un script `.m` |

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

## Fichier de projet

**Enregistrer le projet** écrit un `.digit.json` autonome, qui contient :

- l'image, en data URL — le fichier se suffit à lui-même ;
- la calibration : les quatre repères, leurs valeurs, les indicateurs
  logarithmiques ;
- la zone d'analyse ;
- les séries, en coordonnées pixel, avec les réglages de détection utilisés ;
- les notes libres.

On peut donc poser ce fichier sur une clé, le rouvrir sur une autre machine
hors réseau, et retrouver exactement l'état de travail. Les réglages de
détection étant conservés série par série, un tiers peut voir *comment* chaque
courbe a été obtenue — ce qui compte pour une donnée qui finira dans un rapport.

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
