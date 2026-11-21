# cfd-trajcast

Transforme une simulation de vol (fusée, avion, tout engin : trajectoire + attitude)
et sa CAO en vidéo de présentation : rendu 3D, flammes et fumées par phases,
télémétrie animée, titres, MP4.
100 % pip, Linux, Python ≥ 3.9.

**État : jalon J6 (feuille de route terminée)** — conventions, lecture de la trajectoire et de la CAO,
validation (`cfd-trajcast check`), rendu MP4 (`cfd-trajcast rendre`) avec
plusieurs vues simultanées (vue d'ensemble NED, poursuite, sol, embarquée), enchaînements de
dispositions, panneau de télémétrie, titre, bandeaux d'événements et logo.
Style « conférence » (ciel, terrain, soleil, anticrénelage), jets par phases
(flammes évasées, fumées, plusieurs tuyères), caméras orbite et à images clés,
ralentis, générateur de trajectoires par manœuvres et scénarios avion / panne /
fusée bi-étage (`01_EXEMPLE/SCENARIOS/`). Lecture directe d'une simulation RocketPy
(événements compris), cache disque, rendu parallèle par tronçons, export CSV. 4K,
préréglage `nuit` (ciel étoilé, lueur, flammes qui éclairent la scène), moteur
Blender optionnel (bpy : EEVEE ou Cycles), CI.

## Installation

```bash
cd tools/cfd-trajcast
pip install -e ".[step]"        # [step] : lecture des STEP (cascadio / OpenCASCADE)
pip install -e ".[rocketpy]"    # [rocketpy] : simulations RocketPy (Python ≥ 3.10)
pip install -e ".[blender]"     # [blender] : moteur Blender (bpy 5.x : Python 3.13)
pip install -e ".[dev]"         # tests, ruff, mypy
```

### Machine sans réseau (air-gap)

Contrairement aux autres paquets de `tools/`, `pip install --no-deps` **ne suffit pas** :
cfd-trajcast importe des bibliothèques compilées rarement présentes (VTK, ffmpeg, OpenCASCADE).
Elles sont livrées en roues pour **Python 3.9, Linux x86_64, glibc ≥ 2.28** (RHEL/Rocky 8) :
15 fichiers, 167 Mo, `SHA256SUMS` joint, publiés dans la release GitHub
[`cfd-trajcast-roues-py39`](https://github.com/keryan-leguere/cfd-framework/releases/tag/cfd-trajcast-roues-py39)
(`gh release download cfd-trajcast-roues-py39 -D WHEELS_PY39` sur une machine connectée).

| Roue | Rôle |
|---|---|
| `vtk` 9.5.2 (108 Mo) | moteur 3D de la vidéo |
| `pyvista` 0.46.5, `scooby`, `pooch` + `requests`, `urllib3`, `idna`, `certifi`, `charset_normalizer`, `platformdirs`, `typing_extensions` | pilotage de VTK |
| `imageio_ffmpeg` 0.6.0 (29 Mo, contient le binaire ffmpeg), `imageio` | encodage MP4 — importé dès `import cfd_trajcast` |
| `trimesh` 4.12.2 | lecture STL/OBJ/GLB |
| `cascadio` 0.1.1 (28 Mo) | lecture STEP (facultatif si la CAO est en STL) |

Sont supposés **déjà installés** : `numpy`, `pandas`, `matplotlib`, `pillow`, `pyyaml`, `rich`.

1. Vérifier la cible (les roues compilées en dépendent exactement) :

   ```bash
   python3 -VV        # attendu : Python 3.9.x
   ldd --version      # 1re ligne : glibc ≥ 2.28 (RHEL/Rocky 8 : 2.28)
   python3 -c "import platform; print(platform.libc_ver(), platform.machine())"   # (glibc, 2.28+), x86_64
   python3 -c "import numpy, pandas, matplotlib, PIL, yaml, rich"   # les paquets « standard » sont là ?
   ```

2. Installer, sans réseau :

   ```bash
   cd WHEELS_PY39 && sha256sum -c SHA256SUMS && cd ..
   python3 -m pip install --no-index --find-links WHEELS_PY39 \
       vtk pyvista trimesh imageio imageio-ffmpeg cascadio
   python3 -m pip install --no-deps --no-build-isolation tools/cfd-trajcast
   python3 -m pip check
   ```

   Interface (`cfd-trajcast gui`) : `python3 -m pip install --no-index --find-links WHEELS_PY39
   PyQt5 pyvistaqt` et `python3 -m pip install tools/cfd-plot` (`00_DOC/09_INTERFACE.md`).

3. Lanceur en `#!/usr/bin/env python3` et complétion bash (pour tous les paquets de
   `tools/`) : `python3 tools/installation/installer_lanceurs.py`, à relancer après
   chaque `pip install`.
4. Vérifier le rendu : `cfd-trajcast diagnostic` (ou `python3 -m cfd_trajcast diagnostic`).
   La vidéo demande aussi, **hors pip**, `libEGL` + Mesa (paquets `mesa-libEGL mesa-dri-drivers`
   sur RHEL 8) ou un serveur X / `xvfb-run`. Le schéma SVG (`cfd-trajcast ensemble`) n'en a pas
   besoin.

Le lot se refait sur une machine connectée avec `outils/telecharger_roues_py39.sh` (il faut un
interpréteur 3.9 : avec un autre, `pip download --python-version 3.9` évalue les conditions
`python_version < "3.10"` avec la mauvaise version et oublie des dépendances).

## En cinq lignes

```python
from cfd_trajcast import Film, Maquette, Trajectoire

traj = Trajectoire.depuis_csv("vol.csv", repere="NED", attitude={"type": "euler", "sequence": "ZYX"})
fusee = Maquette.depuis_fichier("fusee.step", axe_nez="-X", axe_haut="+Z", longueur_attendue=2.87)
Film(traj, fusee).rendre("vol.mp4")
```

La vue d'ensemble seule — figure paper du vol entier, sa version animée (aucune des deux
n'a besoin de rendu 3D), schéma SVG sans dépendance, ou vidéo rendue :

```python
from cfd_trajcast import VueEnsemble

vue = VueEnsemble.depuis_yaml("CONFIG_ENSEMBLE.yaml")   # n'importe quelle configuration
vue.figure("vol")                                       # vol.pdf/.svg/.png, style paper de cfd-plot
vue.animer("vol_anime.mp4")                             # la figure animée, ni OpenGL ni GPU
vue.svg("vol.svg")                                      # schéma maison, ≈ 0,1 s
vue.rendre("vol_ensemble.mp4")                          # rendue en 3D (PyVista), tout le vol
```

`repere: ned_local` dans la vue d'ensemble met Bas = 0 au point de départ, sur les axes
du NED classique (`00_DOC/08_FIGURE_ET_ANIMATION.md`).

## En ligne de commande

```bash
cfd-trajcast diagnostic         # rendu hors écran possible ? ffmpeg ? extras ? interface ?
cfd-trajcast gui CONFIG_GUI.yaml   # interface : naviguer dans le vol, télémétrie, repères, vent
cfd-trajcast exemple ex/        # AIM-9 + vol de référence analytique
cd ex && cfd-trajcast check CONFIG.yaml
cfd-trajcast rendre CONFIG.yaml --apercu
cfd-trajcast rendre CONFIG_MULTIVUES.yaml --apercu   # 3 vues + télémétrie + habillage
cfd-trajcast rendre CONFIG_ENSEMBLE.yaml --apercu    # vue d'ensemble NED + 3 zooms
cfd-trajcast ensemble CONFIG_ENSEMBLE.yaml           # figure paper du vol entier (PDF, SVG, PNG)
cfd-trajcast ensemble CONFIG_ENSEMBLE.yaml --video --sans-rendu --apercu   # … animée, sans rendu 3D
cfd-trajcast ensemble CONFIG_ENSEMBLE.yaml --video --apercu   # … ou rendue en 3D (PyVista)
cfd-trajcast ensemble CONFIG_ENSEMBLE.yaml --schema  # schéma SVG maison (sans cfd-plot)
python vue_ensemble.py [--sans-rendu]                # la même chose depuis Python
cfd-trajcast rendre CONFIG_VIRAGE.yaml --apercu      # style conférence, images clés, ralentis
bash SCENARIOS/RUN_SCENARIOS.sh                      # avion, panne en spirale, fusée bi-étage
cfd-trajcast image CONFIG.yaml --t 12.5
cd ROCKETPY && cfd-trajcast rendre CONFIG_ROCKETPY.yaml --apercu   # vol RocketPy (≥ 3.10)
cfd-trajcast rendre CONFIG.yaml -j 4                 # 4 processus (défaut : automatique)
cfd-trajcast exporter CONFIG.yaml                    # trajectoire lue → CSV (ENU, quaternion)
cfd-trajcast rendre SCENARIOS/FUSEE_NUIT_4K.yaml     # 4K, de nuit
cfd-trajcast rendre SCENARIOS/FUSEE_NUIT_BLENDER.yaml   # moteur Blender (bpy)
```

Codes de retour : 0 succès, 1 entrée illisible, 2 contrôle en erreur (ou, pour
`diagnostic`, aucun rendu possible). `check --coherence` ajoute le contrôle
nez/vitesse, à demander seulement si la trajectoire contient une montée.
`python -m cfd_trajcast` est l'équivalent sans script console.

## Documentation

| Fichier | Sujet |
|---|---|
| `00_DOC/01_REPERES.md` | conventions, déclarations, contrôles — **à lire en premier** |
| `00_DOC/02_CONFIGURATION.md` | **référence** de toutes les clés du YAML (vérifiée par un test) |
| `00_DOC/03_CAMERA_ET_VIDEO.md` | `rendre`, `image` ; sections `video`, `vues`, `disposition`, `sequence`, `telemetrie`, `montage` |
| `00_DOC/05_PROPULSION_ET_SCENARIOS.md` | jets par phases, générateur de manœuvres, scénarios |
| `00_DOC/06_ROCKETPY_ET_PERFORMANCE.md` | RocketPy, cache, rendu parallèle et débit |
| `00_DOC/07_4K_NUIT_BLENDER.md` | 4K, préréglage nuit (étoiles, lueur, lumière des jets), moteur Blender |
| `00_DOC/08_FIGURE_ET_ANIMATION.md` | vue d'ensemble : figure paper, animation sans rendu 3D, repère NED local |
| `00_DOC/09_INTERFACE.md` | interface interactive (`cfd-trajcast gui`) : vent, CDG, repères, exports, installation |
| `00_DOC/04_RENDU_HORS_ECRAN.md` | bilan du jalon J0 : rendu sans écran, mesures |
| `02_CONTROLE/README.md` | contrôle qualitatif de chaque jalon |

## Tests

```bash
pytest          # ~720 tests ; STEP sauté sans cascadio, RocketPy sans rocketpy, Blender sans bpy, rendu sans OpenGL
ruff check . && mypy src
```
