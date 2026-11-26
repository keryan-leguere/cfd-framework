# Figures de vent : roses Nord/Est et profil vertical

Le vent déclaré dans la section `vent` du YAML (`02_CONFIGURATION.md` § 12) s'exporte hors de
l'interface, en deux formes synchronisées par l'instant :

| Sortie | Commande | Dépendances | Pour |
|---|---|---|---|
| **Figure paper** (PDF, SVG, PNG 300 dpi) | `cfd-trajcast vent CONFIG` | Matplotlib + cfd-plot | un article, un rapport |
| **Vidéo sans rendu 3D** | `cfd-trajcast vent CONFIG --video` | Matplotlib + cfd-plot + ffmpeg | une présentation, sur une machine sans GPU |

Depuis Python : `VueVent.depuis_yaml(…).figure(base)` et `.animer(chemin)`.
`01_EXEMPLE/figures_vent.py` montre les deux.

## 1. Ce qui est dessiné

- **La rose** est une polaire orientée comme une carte : le Nord en haut, l'Est à droite.
  La flèche part du centre, et sa longueur est le **vent horizontal** en m/s. La courbe
  grise derrière elle est l'hodographe, c'est-à-dire le vent horizontal sur tout le vol.
  Sous chaque rose figurent la vitesse et la direction (« 15,5 m/s vers 016° »), le vent
  vertical (« 0,9 m/s montant ») et l'altitude.
- **Le profil vertical** trace l'altitude en fonction du temps. Les événements y sont
  marqués en pointillé, leurs noms en haut du cadre. Deux événements à moins de 4 % de la
  durée du vol partagent une étiquette (« Mach 1 / Fin de propulsion »).
- **La synchronisation** passe par les marqueurs. En figure fixe, chaque instant porte sur
  le profil un numéro, une couleur et une forme de marqueur (Okabe-Ito, comme les
  événements de la vue d'ensemble), repris sur sa rose et son titre. En vidéo, le profil se
  trace au fil du vol avec un point et un curseur à l'instant courant, pendant que la
  flèche tourne et que la trace des vents déjà rencontrés s'allonge derrière elle.

## 2. Conventions

- **Azimut** : compté depuis le Nord, dans le sens horaire (0° = Nord, 90° = Est), comme
  un cap.
- **`--sens vers`** (défaut) : la flèche montre **où va l'air**. C'est la convention
  interne du paquet et celle de l'hodographe du GUI.
- **`--sens depuis`** : la flèche montre **d'où vient le vent** (convention météo).
  L'azimut est retourné de 180°, le module ne change pas.
  Ce choix d'affichage est indépendant du `sens` de la section `vent` du YAML : celui-ci
  dit comment **lire** les colonnes, et le vent est toujours converti en vitesse de l'air
  ENU à la lecture.
- **Un seul rayon** pour toutes les roses d'une figure ou d'une vidéo : le plus fort vent
  horizontal du vol, arrondi au pas lisible suivant (1, 2, 2,5, 5 × 10ⁿ), avec 5 % de
  marge. Deux flèches de même longueur sont donc deux vents de même force. Le dernier
  anneau porte l'unité.
- **Interpolation par composante** entre deux échantillons, jamais sur l'angle : un vent
  qui passe de 359° à 1° ne fait pas le tour du cadran. La trace grise est tracée sur un
  azimut déroulé pour la même raison.
- **Le vent est affiché, pas intégré** : il ne modifie pas la trajectoire.

Le code est dans `core/vent_polaire.py` (NumPy seul, testé sans figure) :
`azimut_module`, `vent_a`, `rayon_polaire`.

## 3. Figure paper

```bash
cfd-trajcast vent CONFIG_GUI.yaml                         # une rose par événement, 16 cm, pdf + svg + png
cfd-trajcast vent CONFIG_GUI.yaml --instants 8 --sens depuis
cfd-trajcast vent CONFIG_GUI.yaml --instants 2,10,Apogée --formats pdf --largeur-cm 12
```

- **`--instants`** : un nombre (instants répartis sur le vol), ou une liste d'instants en
  secondes et de noms d'événements. Par défaut, les événements, ou cinq instants répartis
  s'il n'y en a pas. Au plus 24.
- **Disposition** : autant de roses par rangée que la largeur en loge (0,75 pouce de
  diamètre au moins, six au plus). À 16 cm, cela fait quatre par rangée. Une rangée
  incomplète est centrée.
- **Style `paper` de cfd-plot**, nombres en français (espace fine des milliers, virgule
  décimale). Pas de titre par défaut, il va dans la légende de l'article : la commande en
  propose une, qui dit les instants, le sens de la flèche et le rayon.
- Les fichiers sont `<config>_vent.{pdf,svg,png}`, ou la base donnée par `--sortie`.

## 4. Vidéo sans rendu 3D

```bash
cfd-trajcast vent CONFIG_GUI.yaml --video --apercu        # 540p, 15 ips
cfd-trajcast vent CONFIG_GUI.yaml --video --duree 20 --de 0 --a 45
```

La vidéo écrit aussi la figure. Disposition : une grande rose à gauche, le profil à
droite, et sous lui l'état courant (t, altitude, vent, vertical) et les événements, qui
s'allument quand ils sont atteints. Cadence, résolution, vitesse ou durée et ralentis
viennent de la section `video`, comme `cfd-trajcast ensemble --video --sans-rendu`, avec
le même calcul des instants (`core/temps.instants_de_vol`). Le titre est celui de l'étude.
Le fichier est `<config>_vent_anime[_apercu].mp4`, ou celui donné par `--mp4`.

## 5. Erreurs

- Fichier sans section `vent` : code 1, « pas de section `vent` dans ce fichier ».
- cfd-plot absent : code 1. Il n'y a pas de repli, contrairement à la vue d'ensemble qui a
  son schéma SVG maison.
- Instant hors du vol, événement inconnu, `--instants 0`, format inconnu : code 1, avec un
  message qui nomme la valeur fautive.

## 6. Architecture

```
core/vent_polaire.py     azimut, module, interpolation par composante, rayon commun — NumPy
engine/figure_vent.py    DonneesVent, figure_vent, animation_vent — seul module Matplotlib du vent exporté
engine/vue_vent.py       VueVent : depuis un YAML, .figure(), .animer()
report/rendu.py          rapport_figure_vent, rapport_animation_vent
cli/main.py              cfd-trajcast vent
```

Tests : `tests/test_figure_vent.py` (conventions, flèche dessinée au vent de l'instant,
rayon commun, Nord en haut et Est à droite, rangées, formats, glyphes manquants, vidéo,
CLI). Contrôle visuel : `python 02_CONTROLE/generer_controle.py --jalon V`.
