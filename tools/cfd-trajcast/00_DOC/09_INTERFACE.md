# Interface interactive — `cfd-trajcast gui`

```bash
cfd-trajcast gui 01_EXEMPLE/CONFIG_GUI.yaml        # ou Fichier › Ouvrir / Nouveau vol depuis un CSV
cfd-trajcast gui CONFIG.yaml --moteur vtk          # vue 3D VTK d'emblée (OpenGL)
```

Le vol en grand, et on s'y promène :

| Zone | Ce qu'elle fait |
|---|---|
| **Centre** | vue d'ensemble 3D : NED (classique ou `ned_local`), proportions vraies, maquette agrandie placée **autour du CDG**, partie parcourue en noir, événements atteints, repères locaux, flèches de vent |
| **Bas** | frise : curseur (triangles = événements), instant au clavier, lecture/pause, vitesse ×0,1 à ×10, pas à pas, liste des événements |
| **Télémétrie** (droite) | **toutes** les séries, à cocher et filtrables : grandeurs calculées, angles aérodynamiques, CDG et chaque colonne du CSV ; valeur à l'instant courant ; une courbe par coche, curseur commun ; un clic dans une courbe place le temps |
| **Vent** (onglet) | hodographe (vers l'Est, vers le Nord) coloré par l'altitude, vent vertical en fonction de l'altitude, point courant |
| **Affichage** (gauche) | repères au CDG (corps FRD, NED local, aérodynamique, trajectoire), flèches de vent, maquette, trace au sol, événements, agrandissement ; **zoom** (−, +, Vol entier, Engin, Suivre l'engin) |

Clavier : **Espace** lecture/pause, **←/→** ±0,05 s (**Maj** : ±1 s), **Début/Fin** ;
zoom **Ctrl++** (ou Ctrl+=), **Ctrl+−**, **Ctrl+0** vol entier, **Ctrl+1** cadrer l'engin.
Souris : glisser fait tourner la vue, le bouton du milieu la déplace, la **molette** zoome ;
un **clic** (sans glisser) sur le vol s'y place (en VTK : **double-clic**, le simple clic
appartient à la caméra).

La lecture suit le **temps réel** × la vitesse : si le dessin est lent, des images sont
sautées, le vol ne ralentit pas.

## Zoom

Le dock Affichage (et le menu Affichage › Zoom) propose quatre commandes et une case :

| Commande | Effet |
|---|---|
| **+ / −**, molette | zoom ×1,25 par cran. En Matplotlib, la molette zoome **vers le point du vol sous la souris**, qui reste où il est ; loin du vol, elle zoome vers le centre de la vue |
| **Vol entier** | retour à la vue de départ ; la vue cesse de suivre l'engin |
| **Engin** | cadre la maquette affichée (demi-largeur = 1,5 × sa taille, agrandissement compris) **et la suit** |
| **Suivre l'engin** | à chaque instant, le centre de la vue est le CDG ; le zoom ne change pas. Pendant la lecture, la vue accompagne l'engin |

Le zoom va du vol entier (×1) jusqu'à une demi-largeur d'une demi-maquette **réelle**. Pour
voir l'engin à sa vraie taille : décocher « auto », mettre l'agrandissement à 1, puis « Engin ».

En Matplotlib, zoomer, c'est resserrer les **limites** des trois axes ; la boîte reste
graduée et les graduations se refont pour la partie visible. Le plus long côté rétrécit
d'abord, puis les trois ensemble. Un vol presque vertical, vu de près, donne donc une
boîte **cubique** autour de l'engin, et pas une fente de 170 m de haut sur 60 m de large.
L'échelle reste la même sur les trois axes : les proportions restent vraies, et l'axe Bas
reste inversé (`tests/test_zoom.py`). Le zoom intégré à Matplotlib (glisser au bouton droit)
est désactivé, car il peut étirer un axe plus que les autres.

Ce qui sort de la boîte est coupé avec Matplotlib ≥ 3.10 (`axlim_clip`). Avec une version
plus ancienne, comme Matplotlib 3.9, la dernière pour Python 3.9, le tracé déborde de la
boîte quand on zoome. Les données restent justes, l'image est seulement moins propre. Le
sol, lui, est découpé à la main dans tous les cas.

En VTK, la molette est celle de VTK : la caméra avance vers le point visé. Les boutons font
la même chose qu'en Matplotlib, en déplaçant la caméra. Les flèches de vent gardent
l'échelle du vol entier : de près, elles paraissent grandes.

« Exporter › Vue courante » écrit la vue **telle qu'elle est zoomée**. Les vidéos, elles,
montrent toujours le vol entier.

## Données : vent et CDG

Les sections `vent` et `cdg` du YAML sont décrites dans `02_CONFIGURATION.md` (§ 12 et
13) ; l'exemple complet est `01_EXEMPLE/CONFIG_GUI.yaml` sur `vol_vent_cdg.csv` (le vol
de référence, avec un vent qui tourne avec l'altitude, un ascendant vers 2 500 m, et un
CDG qui avance pendant la combustion).

* **Positions = CDG.** La maquette est placée par ``position + R · e · (s − cdg)`` : le
  CDG reste sur la trajectoire quel que soit l'agrandissement ``e``, la maquette glisse
  autour de lui (`tests/test_vent_cdg.py`).
* **Rien n'est supposé** sur le vent : le sens de VZ (`haut`/`bas`) est obligatoire.
* Le vent donne à toutes les commandes les séries `incidence` α, `derapage` β,
  `vitesse_air`, `vent_horizontal` ; le CDG donne `xcg`.

Repères (colonnes en ENU, orthonormés directs, `core/reperes_locaux.py`) :

| Repère | Axes | Défini par |
|---|---|---|
| Corps FRD | x_b avant, y_b droite, z_b bas | l'attitude |
| NED local | N, E, D | — (translaté au CDG) |
| Aérodynamique | x_a le long de la vitesse air | α = atan2(w, u), β = asin(v/V) avec (u, v, w) = Rᵀ (v_sol − vent) ; non dessiné sous 0,5 m/s |
| Trajectoire | x_k le long de la vitesse sol, y_k horizontal à droite | la vitesse sol ; y_k vers l'Est en vol vertical |

## Exports

Menu **Exporter** :
- la vue courante (PDF, SVG, PNG 300 dpi ; PNG seulement en VTK), telle qu'affichée ;
- les courbes ;
- le panneau vent ;
- la figure paper du vol entier (`VueEnsemble.figure`) ;
- une **vidéo**. Une boîte de dialogue demande :
  - le mode : figure animée sans rendu 3D, ou vue rendue en 3D ;
  - l'intervalle ;
  - la résolution (540p, 1080p, 4K) ;
  - la durée.

La vidéo tourne dans un **sous-processus** (`gui/tache_video.py`, lancé par `QProcess`).
Le rendu VTK hors écran à côté d'une vue OpenGL interactive, ou le style Matplotlib changé
pendant que l'interface dessine, sont des sources de plantage. Le sous-processus isole
tout, la barre de progression suit ses lignes `PROGRES`, et « Annuler » le tue et efface
le fichier partiel.

Les vidéos exportées ne montrent pas (encore) les repères ni les flèches de vent. Pour
exporter le vent hors de l'interface (roses Nord/Est + profil vertical, figure et vidéo),
voir `cfd-trajcast vent` (`10_FIGURES_VENT.md`).

## Nouveau vol depuis un CSV

L'assistant (Fichier › Nouveau vol depuis un CSV) propose :
- un aperçu du fichier ;
- le repère, les unités et les colonnes t, x, y, z ;
- l'attitude (quaternion ou Euler, ordre, sens, séquence, axes du corps) ;
- la maquette ;
- le vent et le CDG, facultatifs.

Les listes sont **préremplies** avec les noms que la lecture reconnaît (`qw..qz`, `q0..q3`,
`lacet/tangage/roulis`, `VN/VE/VZ`, `Xcg`…), mais chaque convention reste affichée et
modifiable. Avant d'écrire le YAML, la dernière page le vérifie comme à l'ouverture
(parseur de configuration + `EtatVol`). En cas d'erreur, le message est le même qu'à
l'ouverture, et rien n'est écrit.

## Architecture

```
core/reperes_locaux.py     trièdres et α/β — NumPy
data/vent.py, data/cdg.py  déclarations, conversion vers ENU / FRD
engine/etat_vol.py         EtatVol : séries précalculées, état à l'instant t, placement de la maquette
engine/vue3d_mpl.py        VueMpl : scène 3D Matplotlib animable, dans une Figure quelconque
engine/courbes.py          Courbes (télémétrie), PanneauVent
engine/rendu/pyvista_interactif.py   VueVtk : la même scène dans un QtInteractor
gui/                       Qt seulement : fenêtre, frise, docks, exports, assistant, sondes
```

Toute la logique est hors de Qt et testée sans écran. `gui/` ne fait que le câblage, et
c'est la seule couche qui importe PyQt5 (`tests/test_architecture.py`). Les tests Qt
tournent en `QT_QPA_PLATFORM=offscreen` (`tests/test_gui.py`), avec des réglages isolés :
un test vérifie que rien n'est écrit dans `~/.config` de l'utilisateur. Contrôle
qualitatif : `python 02_CONTROLE/generer_controle.py --jalon G`.

## Bilan du jalon G0 (mesures sur cette machine)

| Essai | Résultat |
|---|---|
| Matplotlib 3D (maquette ~1 200 faces) dans un `FigureCanvasQTAgg` 1 400 × 900 | **≈ 30 images/s**, en `offscreen` comme sur X : assez pour la lecture |
| VTK `QtInteractor`, Wayland natif | ~900 images/s |
| VTK `QtInteractor`, XWayland (xcb) | **2 images/s**, puis **250** avec `vblank_mode=0` |
| VTK `QtInteractor`, `offscreen` | image vide (pas d'OpenGL) : non testable sans écran |

Trois pièges, tous corrigés et documentés dans le code :

1. **Deux Qt dans le même processus.** L'environnement OpenFOAM met
   `/usr/lib/x86_64-linux-gnu` dans `LD_LIBRARY_PATH`. Le chargeur prend alors le Qt du
   système (5.15.13) avant celui de la roue (5.15.19), et Qt s'arrête : « Cannot mix
   incompatible Qt library ». Le `LD_LIBRARY_PATH` est lu au démarrage, le changer ensuite
   ne sert à rien. `gui/_qt.py` **précharge** donc les bibliothèques Qt de la roue par leur
   chemin complet (`RTLD_GLOBAL`), comme le TBB de bpy.
2. **Matplotlib prend Qt tout seul.** Dès que PyQt5 est installé et qu'un écran existe,
   `pyplot` choisit le backend `qtagg` et charge Qt, sans préparation, dans des commandes
   qui n'en ont aucun besoin (figure, vidéo, télémétrie). Avec le piège 1, elles tombaient.
   La correction est en deux temps :
   - `engine` ne passe plus du tout par `pyplot` (`Figure` + `FigureCanvasAgg`) ;
   - la CLI pose `MPLBACKEND=Agg` pour toute commande autre que `gui`.
   Un script Python qui appelle `vue.figure()` ne charge plus Qt (vérifié).
3. **Synchronisation verticale sous XWayland** : Mesa attend un vblank que la fenêtre ne
   reçoit pas. `vblank_mode=0` (Mesa) et `__GL_SYNC_TO_VBLANK=0` (NVIDIA) sont posés par
   défaut ; un choix explicite de l'utilisateur prime.

Autres points :
- Le choix de VTK passe d'abord par une **sonde en sous-processus**
  (`python -m cfd_trajcast.gui.sonde_vtk`), parce qu'un OpenGL cassé fait planter le
  processus au lieu de lever une exception. Si elle échoue, l'interface le dit et reste
  sur Matplotlib.
- `cfd-trajcast diagnostic` lance les deux sondes : fenêtre Qt et vue VTK interactive.
- La traduction française de Qt (`qtbase_fr`, livrée dans la roue) est chargée pour les
  boutons standard.

## Installation (machine air-gap)

```bash
bash outils/telecharger_roues_py39.sh          # ajoute PyQt5, PyQt5-Qt5, PyQt5-sip, pyvistaqt, qtpy (GUI=0 : sans)
pip install --no-index --find-links WHEELS_PY39 PyQt5 pyvistaqt
pip install tools/cfd-plot                     # le style paper des vues et des courbes
cfd-trajcast diagnostic                        # « fenêtre Qt » et « vue VTK interactive »
```

La roue PyQt5-Qt5 embarque Qt. Elle demande seulement au système les bibliothèques du
greffon `xcb` : `libxcb-xinerama0`, `libxcb-icccm4`, `libxcb-image0`, `libxcb-keysyms1`,
`libxcb-render-util0` et `libxkbcommon-x11-0`. Sur RHEL 8, ce sont `xcb-util-*` et
`libxkbcommon-x11`. Quand l'une manque, le diagnostic l'indique sur la ligne
« fenêtre Qt ». Sans OpenGL, l'interface marche avec la vue Matplotlib.
