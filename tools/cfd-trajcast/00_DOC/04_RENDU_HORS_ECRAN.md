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
