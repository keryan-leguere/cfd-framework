# Référence du fichier de configuration

Un fichier YAML par vidéo. Seules `trajectoire` et `maquette` sont obligatoires ; une
clé inconnue est **refusée** avec la liste des clés permises (une faute de frappe ne
passe jamais en silence). Les chemins sont relatifs au fichier YAML.

`tests/test_doc_configuration.py` vérifie que chaque clé acceptée par le lecteur
figure dans cette page : elle ne peut pas prendre de retard sur le code.

Les guides détaillés sont ailleurs ; cette page est l'index :

| Section | Guide |
|---|---|
| `trajectoire`, `maquette` | `01_REPERES.md`, `06_ROCKETPY_ET_PERFORMANCE.md` |
| `video`, `vues`, `disposition`, `sequence`, `telemetrie`, `montage` | `03_CAMERA_ET_VIDEO.md` |
| `style`, `propulsion` | `03_CAMERA_ET_VIDEO.md` §8, `05_PROPULSION_ET_SCENARIOS.md`, §7 ci-dessous |
| `moteur` | §11 ci-dessous |

Sections de premier niveau : `etude`, `trajectoire`, `maquette`, `video`, `vues`,
`disposition`, `sequence`, `telemetrie`, `montage`, `style`, `propulsion`, `moteur`.

## 1. `etude`

| Clé | Défaut | Rôle |
|---|---|---|
| `titre` | — | titre affiché au début et au générique |
| `sous_titre` | — | ligne sous le titre |

## 2. `trajectoire`

### Source CSV (`source: csv`, défaut)

| Clé | Défaut | Rôle |
|---|---|---|
| `source` | `csv` | `csv` ou `rocketpy` |
| `fichier` | **obligatoire** | CSV (séparateur détecté, lignes `#` ignorées) |
| `repere` | **obligatoire** | `ENU` ou `NED` (origine : la rampe) |
| `unites` | `{temps: s, longueur: m, angle: deg}` | `temps` (s, ms, min), `longueur` (m, km, mm, ft), `angle` (deg, rad) |
| `colonnes` | `{t: t, x: x, y: y, z: z}` | noms des colonnes `t`, `x`, `y`, `z` |
| `attitude` | **obligatoire** | voir ci-dessous ; jamais déduite de la vitesse |
| `evenements` | aucun | liste de `{t, nom}`, ou un CSV `t,nom` |

`attitude` :

| Clé | Défaut | Rôle |
|---|---|---|
| `type` | **obligatoire** | `quaternion` ou `euler` |
| `colonnes` | jeux connus (`q0…q3`, `qw…qz`, `e0…e3` ; `lacet tangage roulis`…) | 4 ou 3 noms |
| `ordre` | `wxyz` | quaternion : `wxyz` ou `xyzw` |
| `sens` | `corps_vers_reference` | ou `reference_vers_corps` |
| `sequence` | `ZYX` | Euler : 12 séquences ; majuscules = intrinsèque, minuscules = extrinsèque |
| `corps` | `FRD` | repère corps : `FRD` ou `FLU` |

### Source RocketPy (`source: rocketpy`)

| Clé | Défaut | Rôle |
|---|---|---|
| `script` | **obligatoire** | script Python exécuté depuis son dossier |
| `fonction` | `simuler` | appelée sans argument, rend un `rocketpy.Flight` |
| `grandeurs` | sélection | grandeurs du `Flight` échantillonnées en colonnes |
| `cache` | `true` | garder le vol sur disque |
| `evenements` | aucun | ajoutés à ceux du vol |

`repere`, `attitude`, `unites` et `colonnes` sont refusés : RocketPy fixe ses conventions.

## 3. `maquette`

| Clé | Défaut | Rôle |
|---|---|---|
| `fichier` | **obligatoire** | STEP (extra `[step]`), STL, OBJ, PLY, GLB/glTF |
| `axe_nez` | **obligatoire** | axe CAO vers le nez : `+X`, `-X`, `+Y`… |
| `axe_haut` | **obligatoire** | axe CAO « vers le haut » (fixe le roulis de la maquette) |
| `unite` | — | m, cm, mm, in, ft ; obligatoire pour un maillage, contrôle pour un STEP |
| `origine` | `base` | point suivi par la trajectoire : `base`, `centre_volume` ou `[x, y, z]` (unité du fichier) |
| `longueur_attendue` | — | contrôle d'unités (m, ±5 %) |
| `longueur_imposee` | — | mise à l'échelle (m) ; exclut `longueur_attendue` |

## 4. `video`

| Clé | Défaut | Rôle |
|---|---|---|
| `resolution` | `1080p` | `540p`, `720p`, `1080p`, `1440p`, `4K` ou `[largeur, hauteur]` (paires) |
| `ips` | 30 | images par seconde |
| `vitesse` | 1 | secondes de vol par seconde de vidéo |
| `duree` | `auto` | durée de la vidéo (s) ; exclut `vitesse` et `ralentis` |
| `de` | début du vol | début montré : s de vol ou nom d'événement |
| `a` | fin du vol | fin montrée : s de vol ou nom d'événement |
| `ralentis` | aucun | liste de `{de, a, vitesse}` (s de vol) |
| `transition_ralenti` | 0,5 | rampe de vitesse (s de vol) |
| `codec` | `{crf: 18, preset: medium}` | x264 : `crf` 0–51, `preset` de `ultrafast` à `veryslow` |

## 5. `vues`

Un dictionnaire `nom: {mode, …}` ; une ou plusieurs vues. `auto` est accepté pour
les longueurs et les champs qui le prévoient.

| Mode | Clés |
|---|---|
| `poursuite` | `distance`, `cadrage`, `azimut`, `elevation`, `lissage`, `champ` |
| `sol` | `position` (obligatoire, ENU), `champ`, `cadrage`, `champ_min`, `champ_max` |
| `embarquee` | `position_corps` (FRD), `visee`, `champ` |
| `ensemble` | `azimut`, `elevation`, `cadrage`, `echelle_fusee`, `part_fusee`, `champ`, `repere` |
| `orbite` | `distance`, `cadrage`, `azimut`, `elevation`, `vitesse_angulaire`, `champ` |
| `images_cles` | `cles` (liste de `{t, azimut, elevation, distance, champ}`), `cadrage`, `lissage` |

`repere` (vue `ensemble`) : `ned` (défaut, NED classique) ou `ned_local` : le même NED,
origine verticale au point de départ (Bas = 0 au départ, Nord et Est inchangés). Les
axes restent Nord, Est, Bas (Bas positif vers le sol) ; l'axe s'intitule « Bas local ».
Vaut pour la vidéo, le schéma SVG et la figure de `cfd-trajcast ensemble`.

## 6. `disposition` et `sequence`

| `type` | Clés |
|---|---|
| `unique` | `principale`, `telemetrie` |
| `incrustation` | `principale`, `incrustations` (liste de `{vue, coin, largeur}`), `telemetrie` |
| `grille` | `cases` (lignes de noms de vues) |
| `libre` | `cases` (liste de `{vue, rect: [x, y, largeur, hauteur]}`, fractions) |

`telemetrie` : `droite`, `gauche`, `bas` ou `aucune`. Coins : `haut_gauche`,
`haut_droite`, `bas_gauche`, `bas_droite`. La vue nommée `telemetrie` est le panneau.

`sequence` : liste d'étapes `{de, disposition, transition}` ; `de` en s de vol ou nom
d'événement ; `transition` : `coupe` ou `fondu`.

## 7. `style`

| Clé | Rôle |
|---|---|
| `preset` | `sobre` (défaut), `conference`, `nuit` |
| `ciel` | `haut`, `bas` (couleurs `#rrggbb`), `etoiles` (0 : aucune ; 1 : ciel de campagne) |
| `sol` | `type` (`grille`, `terrain`, `damier`, `uni`, `aucun`), `couleur`, `maille` (m), `altitude` (m) |
| `trace` | tracé du vol en fond : `true` / `false` |
| `trainee` | ancienne fumée seule : `active`, `duree`, `couleur`, `rayon`, `croissance`, `jusqu_a` |
| `eclairage` | `soleil` (`[azimut, elevation]` ou `camera`), `intensite`, `ambiance`, `couleur`, `jets` (lumière des flammes) |
| `fusee` | `couleur`, `metal`, `rugosite` |
| `antialiasing` | `aucun`, `ssaa` (`fxaa` : synonyme, VTK passe en SSAA sous EGL) |
| `lueur` | halo autour des zones très lumineuses (0 : aucun) |
| `ensemble` | thème de la vue d'ensemble : `clair` ou `sombre` |

Le préréglage `nuit` : ciel presque noir étoilé, lune bleutée (`eclairage.couleur`),
terrain sombre, flammes qui éclairent la maquette, la fumée et le sol
(`eclairage.jets`) et rayonnent (`lueur`), vue d'ensemble sombre. Les étoiles sont fixes
dans le ciel (elles tournent avec la caméra) et passent derrière la fumée et le sol :
la scène est rendue sur fond transparent puis composée sur le ciel.

## 8. `propulsion`

| Clé | Défaut | Rôle |
|---|---|---|
| `tuyeres` | centre du culot | positions FRD (m) |
| `rayon_tuyere` | 4 % de la taille | m |
| `fondu` | 0,3 | s de vol entre phases |
| `phases` | — | liste de `{de, a, jet, nom}` (instants ou noms d'événements) |

`jet` : un préréglage (`fusee_poudre`, `fusee_liquide`, `postcombustion`, `reacteur`,
`panne`, `fumee`, `aucun`) ou `{base, flamme, fumee}`.
`flamme` : `longueur`, `evasement`, `couleurs`, `opacite`, `coeur`, `diamants`,
`scintillement`. `fumee` : `couleur_debut`, `couleur_fin`, `opacite`, `duree`, `rayon`,
`evasement`, `expansion`, `turbulence`.

## 9. `telemetrie`

| Clé | Rôle |
|---|---|
| `grandeurs` | 1 à 8 lignes : un nom calculé, un nom de colonne, ou un dict |
| `unites` | unités des grandeurs calculées données par leur nom |
| `colonnes` | lire une grandeur calculée dans une colonne plutôt que la calculer : `{mach: Mach}` |

Une ligne en dict : `grandeur` (calculée : altitude, vitesse, mach, acceleration,
incidence_totale, facteur_de_charge, cap, pente, roulis, tangage, lacet) ou
`colonne`, puis `libelle`, `unite`, `facteur`, `decimales`, `couleur`, `plage`.

## 10. `montage`

| Clé | Défaut | Rôle |
|---|---|---|
| `titre_debut` | 3 | s de vidéo |
| `position_titre` | `haut` | `haut`, `centre`, `bas` |
| `generique_fin` | 3 | s de vidéo |
| `fondu` | 0,5 | durée des fondus de séquence (s de vidéo) |
| `bandeaux_evenements` | `true` | un bandeau par événement |
| `coin_bandeaux` | `bas_gauche` | coin de la pile de bandeaux (elle s'écarte du titre tant qu'il est affiché) |
| `duree_bandeau` | 3 | s de vidéo |
| `etiquettes_vues` | `true` | nom de chaque vue dans son coin |
| `logo` | — | `{fichier, coin, hauteur}` (hauteur en fraction de l'image) |

## 11. `moteur`

| Clé | Défaut | Rôle |
|---|---|---|
| `type` | `pyvista` | `pyvista` (VTK, rapide) ou `blender` (bpy : ombres, matériaux physiques) |
| `rendu` | `eevee` | Blender : `eevee` (GPU) ou `cycles` (lancer de rayons, CPU) |
| `echantillons` | 16 | Blender : échantillons par pixel |

Blender demande `pip install bpy`, qui exige une version exacte de Python (bpy 5.x :
3.13). Les vues `ensemble` restent dessinées par PyVista ; le ciel, les étoiles et la
lueur sont les mêmes avec les deux moteurs. Débits mesurés : `07_4K_NUIT_BLENDER.md`.

## 12. `vent`

Facultatif. Le vent rencontré le long du vol, lu dans trois colonnes de la trajectoire
(une valeur par instant), converti en ENU à la lecture. Il donne à la télémétrie
`incidence`, `derapage`, `vitesse_air` et `vent_horizontal`, et à l'interface
(`cfd-trajcast gui`) les flèches de vent, le panneau Vent et le repère aérodynamique.
`cfd-trajcast vent` en tire des roses Nord/Est synchronisées avec le profil vertical,
en figure et en vidéo (`10_FIGURES_VENT.md`).

| Clé | Défaut | Rôle |
|---|---|---|
| `colonnes` | — (obligatoire) | `[VN, VE, VZ]` : composantes Nord, Est, verticale, dans cet ordre |
| `vz` | — (obligatoire) | `haut` (VZ > 0 : l'air monte) ou `bas` (NED strict : VZ > 0, l'air descend) |
| `sens` | `vers` | `vers` : vitesse de l'air (là où il va) ; `depuis` : convention météo (d'où il vient) |
| `unite` | `m/s` | `m/s`, `km/h` ou `kt` |

## 13. `cdg`

Facultatif. Le CDG de l'engin, variable au cours du vol. Les positions de la
trajectoire sont **celles du CDG** : la maquette est placée autour de lui et glisse
quand il avance. Les repères locaux de l'interface sont dessinés au CDG.

| Clé | Défaut | Rôle |
|---|---|---|
| `colonnes` | — (obligatoire) | une colonne (`Xcg`, le long de l'axe de l'engin) ou trois (`[Xcg, Ycg, Zcg]`, axes de la CAO) |
| `unite` | `m` | `m`, `km`, `mm` ou `ft` — longueurs de l'engin réel |
| `reference` | `nez` | `nez`, `culot` (point le plus avant / arrière de la maquette, sur son axe) ou `origine` (l'`origine` de la maquette) |
| `axe` | `vers_culot` | une colonne : sens dans lequel Xcg croît, `vers_culot` ou `vers_nez` |

En trois colonnes, les axes sont ceux de la CAO, convertis par `axe_nez` et `axe_haut`
de la maquette. Exemple complet : `01_EXEMPLE/CONFIG_GUI.yaml`.
