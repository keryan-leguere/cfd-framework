# RocketPy, cache et rendu parallèle (J5)

## 1. Une simulation RocketPy comme trajectoire

```yaml
trajectoire:
  source: rocketpy
  script: vol_rocketpy.py     # chemin relatif au YAML
  fonction: simuler           # défaut ; appelée sans argument, doit rendre un rocketpy.Flight
  cache: true                 # défaut
  grandeurs: [mach_number, dynamic_pressure, angle_of_attack]   # facultatif
  evenements: [{ t: 3.1, nom: "Mach 1" }]                       # ajoutés à ceux du vol
```

Le script est exécuté **depuis son dossier**, qui est aussi ajouté au chemin
d'import. Les fichiers moteur relatifs (`.eng`) et les modules voisins fonctionnent
donc. `repere`, `attitude`, `unites` et `colonnes` sont refusés, parce que RocketPy
fixe ses conventions et que l'adaptateur les applique. En Python :

```python
from cfd_trajcast.data.rocketpy_ import trajectoire_depuis_flight, trajectoire_depuis_script
traj = trajectoire_depuis_flight(flight)                 # un Flight déjà calculé
traj = trajectoire_depuis_script("vol.py", "simuler")    # exécuté, ou relu du cache
```

RocketPy exige **Python ≥ 3.10** : `pip install 'cfd-trajcast[rocketpy]'`. L'adaptateur
lit seulement les attributs du `Flight` et n'importe pas RocketPy. Le reste du paquet
tourne donc toujours en 3.9.

### Conventions de RocketPy (vérifiées sur une vraie simulation)

| RocketPy | cfd-trajcast |
|---|---|
| `Flight.solution` : `t, x, y, z, vx, vy, vz, e0…e3, w1…w3` | lu tel quel ; instants répétés retirés (dernière ligne gardée) |
| `x` Est, `y` Nord, `z` **altitude au-dessus du niveau de la mer** | ENU ; `z − env.elevation`, l'origine étant la rampe |
| quaternion `e0…e3`, scalaire en tête, corps → inertiel | idem (Hamilton, wxyz) |
| corps : `z` vers le nez (`tail_to_nose`), `x`, `y` transverses | FRD par permutation circulaire `x_FRD = z`, `y_FRD = x`, `z_FRD = y` |

Le roulis de la maquette se règle comme pour toute trajectoire, par `maquette.axe_haut`.
Le test `test_vraie_simulation` vérifie l'ensemble sur l'exemple : pendant la propulsion,
le nez est à moins de 2° de la vitesse, et l'inclinaison et le cap de la rampe se
retrouvent sur l'axe du nez au départ.

### Événements et grandeurs

Événements extraits du `Flight` : **Sortie de rampe** (`out_of_rail_time`), **Fin
de propulsion** (`rocket.motor.burn_out_time`), **Apogée**, **Parachute « nom »**
(`parachute_events`) et **Impact** (fin du vol au sol). Ils servent comme les autres
partout où un événement est accepté : `sequence[].de`, phases de `propulsion`,
`video.de` / `video.a`, bandeaux.

Les grandeurs sont échantillonnées aux instants de la solution, sous leur nom
RocketPy et dans leurs unités (Pa, degrés, N). Par défaut : `mach_number`,
`dynamic_pressure`, `angle_of_attack`, `speed`, `stability_margin`, `net_thrust`,
`path_angle`, `attitude_angle` et `free_stream_speed`, ainsi que `vx vy vz` et
`w1 w2 w3` tirés de la solution. Une grandeur que la version de RocketPy n'a pas est
ignorée, et `check` le signale. En télémétrie :
`{ colonne: dynamic_pressure, unite: kPa, facteur: 0.001 }`.

### Figer une simulation : `exporter`

```bash
cfd-trajcast exporter CONFIG_ROCKETPY.yaml --sortie vol.csv
```

Cette commande écrit la trajectoire lue **aux conventions internes** : `t x y z` en
ENU et `qw qx qy qz` du corps FRD vers ENU, suivies des autres colonnes. Les
événements vont dans `vol_evenements.csv`. Elle affiche aussi la section `trajectoire`
qui permet de relire ces fichiers sans RocketPy, par exemple sur une machine en 3.9.
Elle sert pour tout type de source : un vol NED en angles d'Euler en ressort en ENU et
en quaternions.

## 2. Cache

| Quoi | Clé (SHA-256) |
|---|---|
| maillage d'un STEP (OpenCASCADE) | contenu du fichier, versions de cascadio et trimesh |
| vol RocketPy (table + événements) | script, fichiers `.py .eng .rse .csv .txt .json .yaml .yml` de son dossier, `fonction`, `grandeurs`, version de RocketPy |

Dossier : `$CFD_TRAJCAST_CACHE`, sinon `$XDG_CACHE_HOME/cfd-trajcast`, sinon
`~/.cache/cfd-trajcast`. `CFD_TRAJCAST_CACHE=0` désactive le cache. Une entrée n'est
jamais périmée, puisque tout ce dont elle dépend est dans sa clé : elle cesse seulement
d'être demandée. Vider le dossier à la main ne fait rien perdre.

Il y a une limite : un fichier lu **hors** du dossier du script (une table moteur
partagée, une météo téléchargée) ne fait pas partie de la clé. Dans ce cas,
`--sans-cache` (sur `check`, `rendre`, `image` et `exporter`) refait la simulation.

Ce qui n'est pas mis en cache : le panneau de télémétrie. Son fond est déjà dessiné une
seule fois par taille (blitting), et chaque image ne redessine que les courbes
parcourues et les valeurs. Les courbes sont réduites à trois points par pixel de largeur
d'axe, en gardant l'enveloppe min/max pour qu'un pic bref reste visible.

## 3. Rendu parallèle par tronçons

```bash
cfd-trajcast rendre CONFIG.yaml            # automatique
cfd-trajcast rendre CONFIG.yaml -j 1       # en série
```

```python
film.rendre("vol.mp4", processus=4)        # None : automatique
```

Le **plan** est calculé une seule fois. Il contient les caméras lissées, la séquence et
les ralentis. Une fois le plan fixé, chaque image ne dépend plus que de son indice. La
vidéo est donc coupée en tronçons d'images consécutives, d'au moins 30 images et
d'environ quatre par processus pour équilibrer la charge. Des processus indépendants
(`spawn` : un contexte EGL ne survit pas à un `fork`), chacun avec son moteur 3D et ses
panneaux, rendent et encodent ces tronçons. ffmpeg les **recolle ensuite sans
réencoder** (`concat`, copie des paquets). Chaque processus x264 reçoit
`cœurs / processus` fils.

Le résultat est le même qu'en série, aux arrondis de compression près. Le test
`test_parallele_egal_serie` compare les deux vidéos image par image : même nombre
d'images et écart moyen inférieur à 3/255. Le fichier est un peu plus gros, parce que
chaque tronçon commence par une image clé.

Nombre automatique : les cœurs moins deux, au plus 6, et au moins 30 images par
processus. Un rendu court reste donc en série, car la préparation d'un processus coûte
2 à 3 s (import de VTK, scène, terrain).

### Débit mesuré (`02_CONTROLE/J5/MANIFESTE.txt`)

Machine : portable AMD Ryzen 7 4700U, 8 cœurs à 2 GHz, GPU intégré Renoir (EGL).
Extrait : `AVION_MANOEUVRES`, 1080p, vol de 40 à 80 s, soit 801 images (4 vues,
télémétrie, préréglage conférence).

| Processus | x264 | images/s | ms/image | fichier |
|---|---|---|---|---|
| 1 | medium | 14,8 | 67 | 5,1 Mo |
| 4 | medium | 21,6 | 46 | 5,9 Mo |
| 6 | medium | 22,1 | 45 | 6,5 Mo |
| 6 | veryfast | 26,4 | 38 | 5,4 Mo |

Vidéos complètes rendues avec le réglage automatique (6 processus) :

* `AVION_MANOEUVRES` : 4 260 images en 171 s (40 ms/image, contre 67 ms/image en série au J4b) ;
* `AVION_PANNE` : 3 355 images en 128 s ;
* `ROCKETPY` : 1 468 images en 49 s.

Le gain est de **×1,5 à ×1,7, pas ×6**, parce que la machine est limitée par le CPU.
L'encodeur x264 en `medium` coûte à lui seul environ 140 ms·cœur par image 1080p
(mesuré : 112 s de CPU pour 801 images). La composition et la télémétrie en ajoutent
environ 40, le rendu GPU environ 20. Avec 8 cœurs à 2 GHz, le plafond théorique est
d'environ 40 images/s, et la chauffe du portable en retire une partie. Au-delà de
6 processus, rien ne s'améliore (8 donnent moins que 6), d'où le plafond `PROCESSUS_MAX`.

Leviers, par ordre d'effet :

1. `codec.preset: veryfast` : environ 2,3 fois moins de calcul d'encodage, +20 % de
   débit ici. À CRF 18, la différence n'est pas visible à l'œil sur ces scènes, mais
   vérifiez-le sur les vôtres avant une projection.
2. Plus de cœurs. Le découpage passe à l'échelle tant que le GPU suit : sur une station
   de 16 cœurs ou plus, relever `-j` au-delà de 6.
3. `--apercu` pour régler les caméras : 540p, 15 ips, `veryfast`.

La cible fixée pour J5 était de rendre une vidéo 1080p multi-vues en temps réel ou
mieux. Sur cette machine elle est atteinte à 30 ips **seulement en `veryfast`**
(26 images/s ≈ 0,9 × temps réel à 30 ips). En `medium`, le rendu prend environ 1,4 fois
la durée de la vidéo.
