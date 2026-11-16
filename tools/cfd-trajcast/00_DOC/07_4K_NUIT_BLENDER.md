# 4K, préréglage nuit, moteur Blender (J6)

## 1. 4K

```yaml
video:
  resolution: 4K          # 3840×2160 ; ou [largeur, hauteur]
```

Tout ce qui s'affiche est dimensionné **en fraction de la hauteur d'image** : titres,
bandeaux, étiquettes de vues, logo, polices et graduations de la télémétrie, épaisseur
des traits de la vue d'ensemble, taille des étoiles. Une configuration écrite pour le
1080p donne donc la même mise en page en 4K, avec quatre fois plus de pixels. Le seul
réglage qui compte est le débit (§4).

## 2. Préréglage `nuit`

```yaml
style:
  preset: nuit
  # surcharges possibles :
  ciel: { haut: "#01030a", bas: "#18233d", etoiles: 1.0 }
  eclairage: { soleil: [210, 30], intensite: 0.45, couleur: "#a9bcff", ambiance: 0.1, jets: 2.5 }
  lueur: 0.9
  ensemble: sombre
```

Les trois effets ajoutés au J6 peuvent aussi servir avec les autres préréglages.

**Étoiles** (`ciel.etoiles`). La scène 3D est rendue sur un fond **transparent** ; le
ciel (dégradé) et les étoiles sont ensuite peints derrière elle
(`engine/effets.composer_ciel`). Les étoiles sont des directions fixes du repère ENU,
projetées avec la caméra de chaque image. Elles tournent donc avec le regard comme un
vrai ciel, et la fumée, le sol et la maquette les cachent.
- **Lecture de la profondeur, écartée** : lire le tampon de profondeur pour savoir où
  est le ciel coûtait 126 ms par image en 4K (mesuré), et ce tampon ne marque pas le
  fond une fois la caméra recadrée.
- **Ce que fait le procédé retenu** : la couche alpha donne la réponse gratuitement,
  translucidité de la fumée comprise. Couleurs prémultipliées, vérifié : 255 pour un
  objet opaque, 163 pour deux faces à 40 % d'opacité.
- **Dessin** : environ 6 000 étoiles avec une loi d'éclat en puissance, déposées sur
  4 pixels voisins pour qu'elles ne scintillent pas quand la caméra tourne lentement.
  Elles scintillent seulement par un lent effet voulu.

**Lumière des jets** (`eclairage.jets`). C'est une lumière ponctuelle placée une
demi-flamme derrière le barycentre des tuyères.
- **Couleur** : celle du premier tiers de la flamme.
- **Intensité** : le poids des phases actives, fondus et scintillement compris.
- **Atténuation** : quadratique, divisée par deux à une taille de maquette. Elle éclaire
  le culot et la fumée proche, et le sol au décollage, pas au-delà.
- **Ombres** : aucune, car collée au culot, une ombre n'y ferait que du grain.

**Lueur** (`lueur`). Ce qui dépasse 62 % de luminance est flouté au quart de la
résolution (deux rayons : cœur et halo large) puis ajouté. La nuit, seules les flammes
passent ce seuil. Le jour, le ciel clair le passerait aussi, d'où le 0 par défaut en
dehors de `nuit`.

**Vue d'ensemble sombre** (`ensemble: sombre`) : fond bleu nuit, traits et textes clairs.

Fumée : son terme ambiant suit `eclairage.ambiance`. La nuit, elle reste sombre sauf là
où la flamme l'éclaire.

## 3. Moteur Blender

```yaml
moteur:
  type: blender        # pyvista (défaut) | blender
  rendu: eevee         # eevee (GPU) | cycles (lancer de rayons, CPU)
  echantillons: 16     # par pixel : anticrénelage d'EEVEE, bruit de Cycles
```

`pip install 'cfd-trajcast[blender]'`, c'est-à-dire bpy. Il y a **une roue par version
de Python** : bpy 5.x exige Python 3.13 exactement, bpy 4.x et 5.0 exigent 3.11. Le
reste du paquet n'en dépend pas. Exemple : `01_EXEMPLE/SCENARIOS/FUSEE_NUIT_BLENDER.yaml`.

Ce que Blender apporte : des ombres portées (soleil, lune), une peinture physique
(Principled BSDF), des flammes réellement émissives et une fumée éclairée par la scène.

Ce qui reste commun aux deux moteurs : plan, caméras, origine flottante, géométrie des
flammes et des fumées (`engine/jets.py`, `tube()` remplaçant le filtre VTK), ciel,
étoiles, lueur, télémétrie et habillage. Les vues `ensemble` (schéma NED gradué) restent
dessinées par PyVista, même avec `type: blender`.

Pièges réglés dans `engine/rendu/blender.py` :

| Piège | Réglage |
|---|---|
| `import bpy` échoue : `undefined symbol tbb::detail::r1::get_thread_reference_vertex` (TBB du système plus ancienne que celle de la roue) | préchargement de la `libtbb.so.12` de la roue (`RTLD_GLOBAL`) avant l'import |
| couleurs délavées par la vue « AgX » | `view_transform = Standard` ; couleurs du style converties de sRGB en linéaire |
| flamme blanche, écrêtée | émission 1,6 au lieu de 4 ; le halo vient de `lueur` |
| anneaux sombres dans la fumée (faces arrière vues à travers l'avant) | `use_backface_culling` sur la fumée |
| grain sur les ailettes près de la tuyère | lampe du jet sans ombre |
| PNG de Blender en alpha droit | prémultiplié à la lecture, puis composé comme avec PyVista |

Le rendu parallèle (`-j`) fonctionne aussi, chaque processus important bpy. Mais un GPU
intégré se partage mal, d'où les 3 processus du contrôle J6.

## 4. Débit mesuré (`02_CONTROLE/J6/MANIFESTE.txt`)

Machine : portable Ryzen 7 4700U (8 cœurs), GPU intégré, 15 Go de mémoire dont environ
6 de libres pendant le contrôle.

| Rendu | Images | Temps | ms/image | Processus |
|---|---|---|---|---|
| `FUSEE_NUIT_4K` : PyVista, 4K, nuit, 3 vues + télémétrie | 2 547 (84,9 s de vidéo) | 1 223 s | 480 | 3 |
| `FUSEE_NUIT_BLENDER` : Blender EEVEE, 1080p, 16 échantillons | 537 (vol de 0 à 8 s) | 879 s | 1 636 | 2 |

* **4K PyVista** : environ 14 fois la durée de la vidéo sur cette machine. Ce coût vient
  surtout de l'encodage x264 `medium` en 4K et de l'anticrénelage SSAA (rendu interne
  deux fois plus grand dans chaque dimension). Leviers : `codec.preset: veryfast`,
  `antialiasing: aucun` pour les essais, ou une station avec plus de cœurs.
* **Blender** : environ 50 fois la durée de la vidéo. C'est l'outil des plans courts et
  soignés, pas des vols entiers. Cycles est plus lent encore.
* **Mémoire** : le premier contrôle J6 a été **tué par le noyau** à 6 processus 4K.
  Un processus 4K dépasse 1,5 Go, et sur un GPU intégré ses tampons sont aussi en
  mémoire centrale. Le nombre automatique de processus est depuis borné par la mémoire
  disponible : `MemAvailable`, 500 Mo + 160 octets par pixel et par processus. Cela
  donne 2 ou 3 processus en 4K ici, 5 en 1080p. Pour Blender, compter plus et fixer
  `-j` à la main (le contrôle en utilise 2).
