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

## En cinq lignes

```python
from cfd_trajcast import Film, Maquette, Trajectoire

traj = Trajectoire.depuis_csv("vol.csv", repere="NED", attitude={"type": "euler", "sequence": "ZYX"})
fusee = Maquette.depuis_fichier("fusee.step", axe_nez="-X", axe_haut="+Z", longueur_attendue=2.87)
Film(traj, fusee).rendre("vol.mp4")
```

## En ligne de commande

```bash
cfd-trajcast diagnostic         # rendu hors écran possible ? ffmpeg ? extras ?
cfd-trajcast exemple ex/        # AIM-9 + vol de référence analytique
cd ex && cfd-trajcast check CONFIG.yaml
cfd-trajcast rendre CONFIG.yaml --apercu
cfd-trajcast rendre CONFIG_MULTIVUES.yaml --apercu   # 3 vues + télémétrie + habillage
cfd-trajcast rendre CONFIG_ENSEMBLE.yaml --apercu    # vue d'ensemble NED + 3 zooms
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
| `00_DOC/04_RENDU_HORS_ECRAN.md` | bilan du jalon J0 : rendu sans écran, mesures |
| `02_CONTROLE/README.md` | contrôle qualitatif de chaque jalon |

## Tests

```bash
pytest          # ~720 tests ; STEP sauté sans cascadio, RocketPy sans rocketpy, Blender sans bpy, rendu sans OpenGL
ruff check . && mypy src
```
