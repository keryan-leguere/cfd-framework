# Rendu hors écran — bilan du jalon J0

Date : 2026-11-15. Prototypes : `02_CONTROLE/J0/prototypes/` (`spike_rendu.py`,
`spike_chaine.py`), images : `02_CONTROLE/J0/`.

## Verdict : GO

La pile pip seule (pyvista 0.49.2, vtk 9.7.2, trimesh, cascadio 0.1.1, matplotlib,
imageio-ffmpeg 0.8.1) rend l'Aim9 hors écran **sans serveur X**, y compris en rendu
**logiciel** (llvmpipe), à un débit qui ne fait pas du rendu 3D le goulot.

## Mesures

Machine : Ubuntu 24.04, AMD Renoir (radeonsi), Mesa 25.2, 8 cœurs, Python 3.12. Scène :
Aim9 (2 054 triangles), PBR, ciel dégradé, sol. Temps par image, capture comprise.

| Fenêtre VTK (sans `DISPLAY`) | Moteur OpenGL | 1080p | 4K | 540×304 (incrustation) |
|---|---|---|---|---|
| défaut (X absent → repli EGL) | GPU | 6,2 ms | 21,5 ms | 1,5 ms |
| `vtkEGLRenderWindow` | GPU radeonsi | 5,7 ms | 20,4 ms | 1,2 ms |
| `vtkEGLRenderWindow`, `VTK_DEFAULT_EGL_DEVICE_INDEX=1` | **llvmpipe (logiciel)** | 5,7 ms | 20,9 ms | 0,9 ms |
| `vtkOSOpenGLRenderWindow` | — | **échec** : `libOSMesa not found`, puis core dump | | |

Reste de la chaîne (1080p) :

| Étape | Temps |
|---|---|
| Encodage H.264 CRF 18 `medium`, imageio-ffmpeg en flux | 16,3 ms/image |
| Panneau matplotlib 600×1080, 4 courbes en blitting | 0,9 ms/image |
| cascadio, `screw.step` / `linkrods.step` (OpenCASCADE) | 0,07 s / 0,34 s |

Écart llvmpipe / GPU sur la même image : 0,30 niveau de gris en moyenne, 0,022 % des
pixels au-delà de 10 niveaux (bords anticrénelés) → les tests de non-régression d'image
avec tolérance sont viables entre machines.

## Ce que J0 change au plan

1. **OSMesa n'est pas dans la roue VTK** : il exige `libOSMesa` système. L'ordre de repli
   devient **EGL (matériel) → EGL llvmpipe (logiciel) → xvfb** ; OSMesa sort de la liste
   (il fait planter le processus au lieu d'échouer proprement). `cfd-trajcast diagnostic`
   doit sonder chaque fenêtre **dans un sous-processus**, justement à cause de ce core dump.
   EGL demande `libEGL` + un pilote Mesa côté système : présent sur toute distribution de
   bureau, à vérifier sur les nœuds de calcul (sinon xvfb).
2. **Le goulot est l'encodage**, pas le rendu (16 ms contre 6 ms en 1080p). Le parallélisme
   par tronçons reste utile, mais l'option qui pèse est le `preset` x264 ; `--apercu`
   utilisera `veryfast`.
3. **imageio-ffmpeg redimensionne 1080 → 1088** par défaut (`macro_block_size=16`), ce qui
   déforme l'image. Toujours passer `macro_block_size=1` (H.264 gère 1080 nativement) ; un
   test ffprobe doit vérifier la hauteur exacte.
4. **cascadio convertit en mètres** (`screw.step` sort avec une boîte de 0,02 × 0,02 × 0,04) :
   pour un STEP, l'unité vient du fichier et `maquette.unite` n'est qu'un contrôle ; pour un
   STL (sans unité), elle reste obligatoire.
5. **Ombrage lisse du STL** : `smooth_shading=True` moyenne les normales à travers les arêtes
   vives (ailettes ondulées sur l'image de contrôle). Utiliser `split_sharp_edges=True`
   (angle ~30°).
6. **Python 3.9** : les dernières roues compatibles sont vtk 9.6.2, pyvista 0.46.5,
   trimesh 4.12.2, imageio-ffmpeg 0.6.0, cascadio 0.1.1. Planchers du `pyproject` :
   `vtk>=9.3`, `pyvista>=0.44`, `trimesh>=4.0`, `imageio-ffmpeg>=0.5`. Roues présentes pour
   Linux x86_64/aarch64, Windows amd64, macOS arm64 (vtk et cascadio).

## Non vérifié à J0

- Windows et macOS (seulement la présence des roues) ; Python 3.9 réellement exécuté.
- Rendu sur un nœud sans pilote Mesa (seul xvfb y sauverait la mise).
- Lecture du STEP de l'Aim9 : seul `aim9.FCStd` existe ; un export STEP depuis FreeCAD
  permettrait de tester l'extra `[step]` sur la vraie maquette.
- Débit sur une CAO lourde (10⁵–10⁶ faces) : l'Aim9 est très léger.

## Suite donnée (J2)

Sans `DISPLAY`, le moteur fixe `VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow` avant
d'importer VTK (un choix explicite de l'utilisateur prime) : VTK n'essaie plus X
d'abord. `cfd-trajcast diagnostic` essaie EGL, EGL périphérique 1 (llvmpipe ici) et
X11, chacun dans un sous-processus. Pour forcer le rendu logiciel :
`VTK_DEFAULT_EGL_DEVICE_INDEX=1` (l'indice dépend de la machine — le diagnostic le dit).

## Lire un diagnostic en échec (machine air-gap)

Retour utilisateur : sur une machine air-gap avec un bon GPU, les trois essais
échouaient et le diagnostic ne disait pas pourquoi (120 caractères d'erreur). Il donne
maintenant, dans l'ordre où il faut regarder :

1. **Versions** de numpy, vtk, pyvista, trimesh, matplotlib, pillow, imageio-ffmpeg,
   lues dans les métadonnées (sans import : un pyvista cassé ne casse pas le
   diagnostic) et comparées aux minimums de `pyproject.toml` (`VERSIONS_MINIMALES`, un
   test vérifie qu'ils concordent). Une version trop ancienne est **refusée** : code de
   sortie 2 même si le rendu passe. pyvista < 0.44 est antérieur à NumPy 2, et le
   diagnostic le signale quand NumPy 2 est installé.
2. **Système** (Linux) : `libEGL` / `libOpenGL` / `libGLX` / `libGL` trouvées ou non,
   fournisseurs EGL glvnd (`*.json` de `/usr/share/glvnd/egl_vendor.d`,
   `/etc/glvnd/egl_vendor.d` ou `__EGL_VENDOR_LIBRARY_*`), droits sur `/dev/dri/renderD*`
   et `/dev/nvidia*`, version du pilote NVIDIA.
3. **Étape** à laquelle chaque essai s'arrête : la sonde annonce `import`, `fenetre`
   puis `rendu` *avant* de les tenter, sortie vidée, parce qu'un plantage par signal ne
   laisse rien d'autre. Un échec à l'`import` sur les trois essais vient de la pile
   Python, pas du GPU. Le signal est nommé (`SIGSEGV`…).
4. **Erreur complète** (40 dernières lignes du stderr) de chaque essai raté, sous le
   tableau, pour pouvoir la recopier.
5. **Fenêtre du rendu** : celle que le moteur prendra vraiment (`fenetre_choisie`).
   Avec `DISPLAY` défini, c'est le choix de VTK (X11 en premier). Si cet essai échoue
   alors qu'EGL passe, le diagnostic donne l'`export` à faire et sort en code 2.

En dernière ligne, une **cause probable** (`cause_probable`) : pile Python, puis
bibliothèques glvnd, puis fournisseurs EGL, puis droits sur les périphériques.
