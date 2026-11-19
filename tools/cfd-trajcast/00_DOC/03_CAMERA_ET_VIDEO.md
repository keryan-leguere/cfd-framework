# Caméras, dispositions, télémétrie, montage

État : jalon J4 — vues `poursuite`, `sol`, `embarquee`, `ensemble`, `orbite`,
`images_cles` ; dispositions et séquence ; ralentis ; panneau de télémétrie libre ;
titre, bandeaux, logo, générique ; style (ciel, terrain, traînée, soleil).

Exemples complets : `01_EXEMPLE/CONFIG_MULTIVUES.yaml` (séquence, médaillons),
`01_EXEMPLE/CONFIG_ENSEMBLE.yaml` (vue d'ensemble NED en principale, zooms autour, QOI
en télémétrie) et `01_EXEMPLE/CONFIG_VIRAGE.yaml` (vol à virage, style conférence,
images clés, orbite, ralentis).

## 1. Rendre

```bash
cfd-trajcast rendre CONFIG.yaml                 # CONFIG.mp4 à côté du YAML
cfd-trajcast rendre CONFIG.yaml --apercu        # 540p, 15 ips, encodage rapide
cfd-trajcast rendre CONFIG.yaml --de 0 --a 10   # seulement 0 → 10 s de vol
cfd-trajcast rendre CONFIG.yaml -j 4            # 4 processus (défaut : automatique ; -j 1 : en série)
cfd-trajcast image CONFIG.yaml --t 12.5         # une image, pour régler la caméra
cfd-trajcast diagnostic                         # ce que la machine sait faire
```

```python
from cfd_trajcast import Film
film = Film.depuis_yaml("CONFIG_MULTIVUES.yaml")
film.rendre("vol.mp4")
film.image(12.5, "t12.png")
```

`image` rend exactement ce que montrerait la vidéo à cet instant : la caméra
étant lissée, son plan est calculé depuis le début du vol.

## 2. Section `video`

```yaml
video:
  resolution: 1080p        # 540p | 720p | 1080p | 1440p | 4K | [largeur, hauteur] (paires)
  ips: 30
  vitesse: 1.0             # secondes de vol par seconde de vidéo (1 = temps réel)
  # duree: 12              # ou : durée de la vidéo (s) ; exclut vitesse
  # de: "Fin de propulsion"   # partie du vol montrée : s de vol ou nom d'événement
  # a: 45.0                   # (défaut : tout le vol ; --de/--a de la ligne de commande priment)
  codec: { crf: 18, preset: medium }   # x264 : crf 0 (sans perte) → 51 ; 18 ≈ visuellement sans perte
```

Sortie : MP4 H.264, `yuv420p` (lisible partout, PowerPoint compris), index en tête
de fichier (`+faststart`). Le binaire ffmpeg vient de la roue `imageio-ffmpeg`.

### Ralentis

```yaml
video:
  vitesse: 1.0                         # hors ralentis
  ralentis:                            # intervalles de **vol**, croissants et disjoints
    - { de: 3.4,  a: 4.6,  vitesse: 0.25 }   # ×4
    - { de: 39.5, a: 41.5, vitesse: 0.5 }    # ×2
  transition_ralenti: 0.5              # s de vol : rampe linéaire de part et d'autre
```

La vidéo s'allonge d'autant (55,5 s de vol → 62,4 s de vidéo dans `CONFIG_VIRAGE`).
Télémétrie, bandeaux et séquence restent calés sur le temps de vol. `ralentis`
exclut `duree`.

## 3. Section `vues` — mode `poursuite`

```yaml
vues:
  poursuite:
    mode: poursuite
    distance: auto     # ou en mètres
    cadrage: 0.35      # avec distance auto : la fusée occupe 35 % de la hauteur d'image
    azimut: 60         # ° : 0 = derrière, 90 = à droite de la route, 180 = devant
    elevation: 10      # ° au-dessus de l'horizontale, dans [-80 ; 80]
    lissage: 0.8       # s (temps vidéo) : constante de temps de la caméra ; 0 = aucun
    champ: 30          # ° : angle de vue vertical
```

La caméra se place par rapport à la **route** — direction horizontale de la
vitesse — et non par rapport à l'attitude : sinon le roulis ferait tourner
l'image. La route est lissée (filtre exponentiel sur la direction) ; quand la
vitesse horizontale est nulle (départ vertical), la route est reprise de l'instant
le plus proche où elle est définie, et à défaut la caméra regarde vers le Nord.

`distance: auto` vaut `L / (cadrage · 2 tan(champ/2))` : exact vu de flanc, plus
serré quand la fusée est vue dans l'axe.

## 4. Modes `sol` et `embarquee`

```yaml
vues:
  sol:
    mode: sol
    position: [1440, 90, 2]     # ENU (m), origine à la rampe — même si la trajectoire est en NED
    champ: auto                 # ou un angle fixe (°)
    cadrage: 0.25               # avec champ auto : part de la hauteur occupée par la fusée
    champ_min: 0.1              # bornes du zoom (°)
    champ_max: 60
  embarquee:
    mode: embarquee
    position_corps: [-0.9, 0.0, -0.16]   # FRD (m) depuis le point de référence de la maquette
    visee: [1.0, 0.0, 0.06]              # direction de visée, FRD
    champ: 70
```

* `sol` suit la fusée du regard depuis un point fixe. Le zoom automatique garde
  la fusée à `cadrage` *vue de flanc* : vue dans l'axe (fusée qui s'éloigne), elle
  paraît plus courte — c'est la perspective, pas une erreur.
* `embarquee` est solidaire du corps : **elle roule avec la fusée**, c'est voulu.
  Le « haut » de l'image est −z corps (le dos de la fusée).

### Modes `orbite` et `images_cles`

```yaml
vues:
  orbite:
    mode: orbite
    distance: auto            # ou en m ; auto = cadrage comme poursuite
    azimut: 0                 # ° depuis le Nord au début
    elevation: 15
    vitesse_angulaire: 20     # °/s de vidéo (un tour en 18 s)
  cinema:
    mode: images_cles         # repérée sur la route, comme poursuite
    cadrage: 0.35             # pour les clés sans distance
    lissage: 0.8              # lissage de la route (s)
    cles:                     # t en s de vol ; azimut : 0 = derrière, 90 = à droite, 180 = devant
      - { t: 0.0,  azimut: 160, elevation: 3,  champ: 35 }
      - { t: 14.0, azimut: 100, elevation: 25, distance: 30 }
      - { t: 40.5, azimut: 90,  elevation: 0 }
```

Entre deux clés, chaque réglage suit une courbe en S (Hermite à tangentes
nulles) : la caméra s'arrête en douceur sur chaque clé, et l'azimut passe par le
plus petit arc (350° → 10° en passant par 0°). Avant la première clé et après la
dernière, les réglages restent ceux de la clé.

### Mode `ensemble` : le vol entier, en NED

```yaml
vues:
  ensemble:
    mode: ensemble
    azimut: auto          # ° depuis le Nord vers l'Est, d'où l'on regarde ; auto = route + 110°
    elevation: 20         # ° au-dessus de l'horizontale
    cadrage: 0.85         # part du cadre occupée par la boîte graduée
    echelle_fusee: auto   # auto : fusée ≈ part_fusee (0.1) de l'étendue du vol ; ou un facteur
    champ: 30
```

Une vue « macro » à caméra **fixe** : boîte graduée en mètres sur les axes
**Nord, Est, Bas** (le Bas est négatif au-dessus du sol), sol et trace au sol,
trajectoire complète en gris, partie déjà parcourue en orange, événements nommés,
et la fusée qui avance et s'oriente. À cette échelle une fusée de 3 m serait
invisible : elle est **agrandie**, et le facteur est écrit dans la vue (« fusée
agrandie × 253 ») pour que personne ne le prenne pour la réalité. Les graduations
tombent sur des valeurs rondes (même pas sur les trois axes, donc pas de
déformation), et le cadrage ajuste exactement les 8 coins de la boîte dans
l'image. Les proportions sont vraies : un vol presque vertical donne une boîte
haute et étroite — on lui donne alors une case haute (voir `CONFIG_ENSEMBLE.yaml`)
plutôt que de déformer les axes.

### La vue d'ensemble seule : schéma SVG et vidéo

`VueEnsemble` (`engine/ensemble.py`) sort la vue d'ensemble de la mise en page
multi-vues, sous deux formes :

```python
from cfd_trajcast import VueEnsemble

vue = VueEnsemble.depuis_yaml("CONFIG_ENSEMBLE.yaml")    # ou VueEnsemble(traj, maquette, parametres=…)
vue.svg("vol.svg")                                       # schéma vectoriel, aucun rendu 3D
vue.svg("vol_sombre.svg", theme="sombre", poses=[10.0, "Apogée"], titre="", taille=900)
vue.rendre("vol.mp4", apercu=True)                       # vidéo de tout le vol, une seule vue
vue.rendre("portrait.mp4", resolution=(1080, 1920), duree=20, telemetrie=False)
vue.image(40.5, "apogee.png")                            # une image de cette vidéo
```

```bash
cfd-trajcast ensemble CONFIG_ENSEMBLE.yaml                       # → CONFIG_ENSEMBLE_ensemble.svg
cfd-trajcast ensemble CONFIG_ENSEMBLE.yaml --poses 5 --theme sombre
cfd-trajcast ensemble CONFIG_ENSEMBLE.yaml --video --apercu      # + CONFIG_ENSEMBLE_ensemble_apercu.mp4
cfd-trajcast ensemble CONFIG.yaml --video --duree 20 --sans-telemetrie
```

Les réglages viennent de la première vue `mode: ensemble` du fichier (`--vue NOM`
/ `vue=` pour en choisir une), sinon des valeurs par défaut : n'importe quelle
configuration convient. L'exemple complet est `01_EXEMPLE/vue_ensemble.py`.

**Le schéma SVG** (`engine/schema_ensemble.py`) n'utilise ni VTK ni OpenGL : il
projette lui-même, en NumPy, avec **la même caméra** (`cadre_ensemble`), **la même
boîte graduée** (`boite_ensemble`, partagée avec le moteur PyVista), le même
agrandissement de la maquette et les mêmes couleurs (`style.ensemble`). Un test
compare sa projection (`core/camera.projeter`) à celle de VTK : moins de 0,01 px
d'écart. Il montre le sol et la trace au sol, la boîte NED graduée (grilles sur les
faces du fond), le vol entier, chaque événement (point, nom, instant, fil à plomb
jusqu'au sol pour lire la profondeur) et la maquette posée à quelques instants :

* `poses` : un nombre (instants régulièrement répartis), une liste d'instants (s)
  et de noms d'événements, ou rien — une pose par événement, en sautant celles qui
  tomberaient à moins d'une maquette à l'écran d'une pose déjà retenue (Mach 1 et
  fin de propulsion, à 0,26 s d'écart, donneraient deux maquettes superposées) ;
* la maquette est dessinée par l'algorithme du peintre (triangles du plus loin au
  plus proche, Lambert à deux faces), parce que le sens des faces d'un STL n'est pas
  garanti ; au-delà de 4 000 faces elle est simplifiée par regroupement de sommets ;
* l'image est **recadrée sur son contenu** : `taille` fixe le plus grand côté, l'autre
  suit le vol — un vol presque vertical donne une image haute, jamais d'axes étirés.

Le fichier pèse quelques centaines de ko (la maquette en fait l'essentiel ;
`poses=0` le ramène à ~40 ko).

**La vidéo** est un `Film` à une vue : format (`video`), titres, bandeaux et logo
(`montage`, `etude`) sont repris du fichier, mais **tout le vol** est montré
(`video.de`/`video.a` ignorés ; `de=`/`a=` explicites pour une partie). La
télémétrie, si le fichier en a une, va dans une bande à droite (`telemetrie=False`
l'enlève, `True` l'impose avec le panneau par défaut) ; un logo prévu en haut à
droite — au-dessus du panneau d'une disposition libre — passe alors à gauche pour
ne pas en couvrir les valeurs. L'étiquette de vue est retirée (une seule vue).

## 5. Section `style`

```yaml
style:
  preset: conference          # sobre (défaut, rendu des jalons J2–J3) | conference | nuit (J6, 07_4K_NUIT_BLENDER.md)
  ciel: { haut: "#1d4f91", bas: "#b4d2ec" }      # dégradé vertical de l'écran
  sol: { type: terrain, couleur: "#5d7a3e", maille: 400 }   # grille | terrain | damier | uni | aucun
  trace: false                # le tracé gris du vol
  sol: { altitude: 0 }        # cote du sol dans le repère de la trajectoire (m)
  eclairage: { soleil: [135, 35], intensite: 0.8, ambiance: 0.25 }   # [azimut, élévation] ; ou camera
  fusee: { couleur: "#c9ced5", metal: 0.0, rugosite: 0.45 }        # metal > 0 → matériau PBR
  antialiasing: ssaa          # aucun | ssaa (« fxaa » : synonyme ; EGL n'a que le SSAA)
```

* **Terrain** : tuile procédurale de `maille` m, raccordable (bruit filtré dans le
  domaine de Fourier, donc périodique), répétée sur un plan d'au moins 40 km ;
  mipmaps pour éviter le moiré à l'horizon. `damier` : 2 × 2 cases de `maille`.
* **Flammes et fumées** : section `propulsion`, voir `05_PROPULSION_ET_SCENARIOS.md`
  (phases, préréglages, plusieurs tuyères). L'ancienne `style.trainee` (fumée seule)
  reste acceptée sans section `propulsion`, mais n'est plus activée par défaut.
* **Matériau** : Phong (ambiant + diffus + spéculaire) par défaut — une maquette à
  contre-jour reste lisible ; `metal > 0` passe en PBR, qui sans carte d'environnement
  peut devenir noir à contre-jour.
* **Soleil** : lumière directionnelle fixe dans le repère terrestre (l'ombre
  propre de la fusée tourne quand elle roule), plus une lumière de caméra
  d'intensité `ambiance` pour déboucher les ombres.
* Avec des jets, le rendu trie les couches translucides (*depth peeling*) : sans cela,
  un matériau vu à travers la fumée laisse des fantômes de ses ailettes.
* La vue `ensemble` garde son propre style (fond clair, axes gradués).

## 6. Section `disposition`

Comment les vues se partagent l'image. Chaque vue est rendue **à la taille exacte
de sa case** (une incrustation au quart de la largeur coûte ~1/16 d'une image).

```yaml
disposition:
  type: incrustation            # unique | incrustation | grille | libre
  principale: poursuite
  incrustations:                # coins : haut_gauche, haut_droite, bas_gauche, bas_droite
    - { vue: embarquee, coin: haut_droite, largeur: 0.24 }   # largeur : fraction de l'image
    - { vue: sol,       coin: bas_droite,  largeur: 0.24 }
  telemetrie: droite            # droite | gauche | bas | aucune (unique et incrustation)
```

```yaml
disposition: { type: grille, cases: [[poursuite, sol], [embarquee, telemetrie]] }
disposition:
  type: libre                   # rectangles [x, y, largeur, hauteur] en fractions
  cases: [{ vue: poursuite, rect: [0, 0, 0.7, 1] }, { vue: telemetrie, rect: [0.7, 0, 0.3, 1] }]
```

`telemetrie` est le nom réservé de la case du panneau. Les cases juxtaposées
(grille, libre) sont séparées par un filet sombre ; une zone qu'aucune case ne
couvre prend le fond du panneau de télémétrie (on peut y loger le logo). Sans section
`disposition` : une seule vue (la première), avec la télémétrie à droite si la
section `telemetrie` existe. Une vue définie mais jamais affichée est signalée
par `check`.

## 7. Section `sequence`

Changer de disposition au fil du vol ; `de` est en **secondes de vol**, ou le nom
d'un événement (`de: "Spirale"`).

```yaml
sequence:
  - { de: 0.0,  disposition: { type: unique, principale: sol, telemetrie: droite } }
  - { de: 2.5,  disposition: defaut, transition: fondu }       # defaut = la section disposition
  - { de: 36.0, disposition: { type: grille, cases: [[poursuite, sol], [embarquee, telemetrie]] },
      transition: fondu }                                      # coupe (défaut) | fondu
```

Le fondu dure `montage.fondu` secondes de vidéo ; pendant ce temps les deux
dispositions sont rendues et mélangées.

## 8. Section `telemetrie`

Le panneau affiche **n'importe quelles grandeurs** (1 à 8 lignes, dans l'ordre) :
celles que calcule `cfd-trajcast`, et surtout les **colonnes de ta trajectoire**
— Mach, q0, αₜ, φ, DL/DM/DN, poussée, masse… Toutes les colonnes numériques du
fichier sont disponibles, celles de l'attitude comprises.

```yaml
telemetrie:
  grandeurs:
    - mach                                   # grandeur calculée
    - DL                                     # colonne, affichée telle quelle, sans unité
    - { colonne: q0, libelle: "Pression dynamique q₀", unite: kPa, facteur: 0.001, decimales: 1 }
    - { colonne: alphat, libelle: "αₜ", unite: "°", plage: [0, 20] }
    - { colonne: phi, libelle: "φ", unite: "°", decimales: 0, couleur: "#ba68c8" }
    - { grandeur: altitude, unite: km, libelle: "Altitude" }
```

| Clé | Rôle |
|---|---|
| `colonne` | nom de la colonne lue ; valeur affichée = colonne × `facteur` |
| `grandeur` | grandeur calculée (tableau ci-dessous) ; `unite` choisie parmi les siennes |
| `libelle` | texte affiché, tel quel (accents, lettres grecques, indices) ; rétréci s'il est trop long |
| `unite` | colonne : texte libre affiché après la valeur ; grandeur calculée : unité de conversion |
| `facteur` | colonne seulement : multiplicateur (ex. 0.001 pour Pa → kPa) |
| `decimales` | 0 à 6 ; défaut selon l'ordre de grandeur (0 au-delà de 100, 1 au-delà de 10, sinon 2) |
| `couleur` | `"#rrggbb"` ; défaut : palette dans l'ordre des lignes |
| `plage` | `[min, max]` de l'axe ; défaut : ajusté aux données |

| Grandeur calculée | Unités | Calcul |
|---|---|---|
| `altitude` | m, km, ft | cote ENU au-dessus de la rampe |
| `vitesse` | m/s, km/h, kt | norme de la dérivée des positions |
| `mach` | — | vitesse / célérité du son ISA à cette cote, vent nul |
| `acceleration` | g, m/s2 | norme de la dérivée seconde des positions — **cinématique** : 1 g en chute libre, ce n'est pas le facteur de charge |
| `incidence_totale` | deg, rad | angle entre l'axe du nez et la vitesse, vent nul (axe d'au moins 5° : une incidence nulle ne fait pas zoomer sur le bruit) |
| `facteur_de_charge` | g, m/s2 | force spécifique ressentie ‖a − g‖ : 1 g en palier, 0 en chute libre |
| `cap`, `pente` | deg, rad | direction de la vitesse (route depuis le Nord) et son inclinaison |
| `lacet`, `tangage`, `roulis` | deg, rad | angles d'Euler ZYX de l'attitude par rapport au NED (le roulis d'un avion en virage est son inclinaison) |

Une colonne absente est refusée dès la construction du film, avec la liste des
colonnes disponibles. Écritures plus courtes, encore acceptées :
`unites: { altitude: km }` et `colonnes: { mach: Mach_mesure }` (lire une grandeur
calculée dans une colonne, en SI).

Le panneau : libellé, valeur à la française (virgule décimale, espace fine
entre milliers, signe moins typographique), et la courbe du vol entier que la
partie parcourue repasse en couleur. Fond dessiné une fois, éléments animés
redessinés à chaque image (*blitting*).

## 9. Section `montage`

```yaml
montage:
  logo: { fichier: logo.png, coin: bas_gauche, hauteur: 0.05 }   # PNG transparent
  titre_debut: 3.0            # s de vidéo ; 0 = pas de titre (etude.titre / sous_titre)
  position_titre: haut        # haut (défaut) | centre | bas — au centre, il cache la fusée ;
                              # centré sur la vue principale, pas sur l'image entière
  generique_fin: 3.0          # s : l'image s'assombrit et le titre revient
  bandeaux_evenements: true   # un bandeau « nom · T+ x s » à chaque trajectoire.evenements
  coin_bandeaux: bas_gauche   # coin où s'empilent les bandeaux
  duree_bandeau: 3.0
  fondu: 0.6                  # durée des fondus de séquence
  etiquettes_vues: true       # nom de la vue en haut à gauche de sa case
```

Textes en DejaVu Sans (livrée avec matplotlib : accents garantis sans dépendre
des polices du système). Les bandeaux s'empilent depuis `coin_bandeaux` en
s'écartant du bord (et du logo s'il est dans ce coin). Par défaut (`Film` construit en Python sans `montage`), aucun
habillage.

## 10. Origine flottante

À chaque image, la scène est translatée pour que la fusée soit à l'origine. Une
fusée de 3 m à 8 km d'altitude reste ainsi nette (pas de scintillement du tampon
de profondeur) ; les plans de découpe sont recalculés par image.

## 11. Débit mesuré (AMD Renoir, un processus)

Mesures d'un seul processus ; le rendu parallèle (J5) et ses mesures sont dans
`06_ROCKETPY_ET_PERFORMANCE.md`.


| Rendu | ms/image |
|---|---|
| aperçu 960×540, `veryfast` | 8 |
| 1080p, `medium`, une vue | 22–25 |
| 1080p, `medium`, 3 vues + télémétrie + habillage (`CONFIG_MULTIVUES`) | 54 |
| 1080p, `medium`, ensemble + 3 zooms + télémétrie (`CONFIG_ENSEMBLE`) | 53 |
| 1080p, `medium`, conférence : images clés + ensemble + orbite + traînée (`CONFIG_VIRAGE`) | 66 |

Le vol de référence (55,5 s, 30 ips, 1 666 images) se rend en 1080p en 37,5 s
(mesuré) ; en multi-vues, en 90,6 s.
