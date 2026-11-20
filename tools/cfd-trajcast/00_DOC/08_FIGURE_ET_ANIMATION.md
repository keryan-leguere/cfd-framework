# Vue d'ensemble : figure paper, animation sans rendu, NED local

La vue d'ensemble existe sous quatre formes, de la plus légère à la plus lourde :

| Sortie | Commande | Dépendances | Pour |
|---|---|---|---|
| **Figure paper** (PDF, SVG, PNG 300 dpi) | `cfd-trajcast ensemble CONFIG` | Matplotlib + cfd-plot | un article, un rapport |
| Schéma SVG maison | `… ensemble CONFIG --schema` | aucune | quand cfd-plot manque (repli automatique) |
| **Vidéo sans rendu 3D** (figure animée) | `… ensemble CONFIG --video --sans-rendu` | Matplotlib + cfd-plot + ffmpeg | une machine sans GPU ni OpenGL |
| Vidéo rendue (PyVista) | `… ensemble CONFIG --video` | VTK + EGL ou X | une présentation |

Depuis Python : `VueEnsemble.figure(base)`, `.svg(chemin)`, `.animer(chemin)`, `.rendre(chemin)`.
`01_EXEMPLE/vue_ensemble.py` (`--sans-rendu`) les montre toutes.

## 1. Repère : NED classique ou NED local

`vues.<nom>.repere` (vue `mode: ensemble`) :

- `ned` (défaut) : NED classique, origine de la trajectoire. Un vol qui part de 1 500 m
  d'altitude commence à Bas = −1 500 m.
- `ned_local` : le **même** NED, origine **verticale** au point de départ : Bas = 0 au
  départ. Nord et Est ne sont pas décalés. L'axe s'intitule « Bas local (m) ».

Dans les deux cas, les figures restent en NED classique : axes Nord, Est, Bas, Bas
positif vers le sol, donc des valeurs négatives au-dessus du sol. Le repère vaut pour les
quatre sorties : `core/camera.origine_ensemble` donne le décalage et
`boite_ensemble(…, origine=)` en tient compte, sol compris (`sol = −altitude_sol − Bas₀`).

## 2. Figure paper

```bash
cfd-trajcast ensemble CONFIG_ENSEMBLE.yaml                       # 12 cm, pdf + svg + png
cfd-trajcast ensemble CONFIG_ENSEMBLE.yaml --largeur-cm 8.5 --formats pdf --projection persp
```

Ce qui la rend publiable :

- **Le style `paper` de cfd-plot** : TeX Gyre Termes, cadre et graduations noirs,
  graduations rentrantes. Elle se lit comme les autres figures du rapport.
- **Proportions vraies.** La boîte est proportionnelle aux étendues
  (`cfd_plot.true_proportions`) et aucun axe n'est étiré. Un vol de 7 km de haut pour 2 km
  de portée donne une figure haute.
- **Projection orthographique** par défaut : une distance se lit pareil au premier plan
  et au fond. `--projection persp` reprend la perspective de la vidéo (angle `champ`).
- **Image non miroir.** Tracé en x = Est, y = Nord, z = Bas avec l'axe z inversé : le
  trièdre affiché (Est, Nord, Haut) est direct. Avec Nord en x, l'image serait le miroir
  du vol, et un virage à droite s'y lirait à gauche
  (`tests/test_figure_ensemble.py::test_image_non_miroir`).
- **Largeur tenue.** `--largeur-cm` est la largeur finale du fichier, légende comprise.
  Matplotlib dessine la 3D dans un carré : `cfd_plot.fit_box3d` zoome la boîte pour
  qu'elle remplisse ce carré, `cfd_plot.bbox3d` rogne sur ce qui est vraiment dessiné, et
  trois passes corrigent la boîte de ce que prennent graduations, titres et légende (en
  points, donc fixes).
- **Graduations proportionnelles aux côtés.** Le côté court a moins de graduations,
  sans graduations mineures, et les fonds sont blancs (`cfd_plot.tidy_axes3d`). Les nombres
  sont en français : espace fine pour les milliers, vrai signe moins, virgule décimale.
  Les étiquettes de l'axe Bas sont écartées d'une demi-étiquette, sans quoi « −7 000 »
  chevaucherait l'axe.
- **Événements.** Couleur Okabe-Ito et forme de marqueur propres à chacun : la figure
  se lit aussi en noir et blanc. Ils sont nommés dans la légende avec leur instant
  (« Apogée (40,6 s) »), au lieu d'étiquettes flottantes qui se chevauchent. Un fil à
  plomb pointillé les relie au sol.
- **Maquette.** Agrandie (facteur dans la légende), ombrée en gris (Lambert à deux faces :
  l'orientation des faces d'un STL n'est pas garantie). Par défaut, elle est posée aux
  événements, sauf deux poses à moins d'une maquette l'une de l'autre (Mach 1 et fin de
  propulsion).
- **Pas de titre.** Il appartient à la légende de l'article. Le rapport terminal propose
  le texte de cette légende (repère, poses, agrandissement, projection).

Aucun glyphe ne manque : les tests font des avertissements Matplotlib des erreurs.

## 3. Vidéo sans rendu 3D

```bash
cfd-trajcast ensemble CONFIG_ENSEMBLE.yaml --video --sans-rendu --apercu   # 540p, 15 ips
cfd-trajcast ensemble CONFIG_ENSEMBLE.yaml --video --sans-rendu --duree 20
```

C'est la figure elle-même, animée par `cfd_plot.anim` :

- la trajectoire se trace au fil du vol, le reste en gris clair ;
- la maquette la parcourt avec son attitude ;
- les marqueurs des événements apparaissent quand ils sont atteints ;
- un panneau à droite donne l'instant, l'altitude, la vitesse et la liste des événements,
  grisés tant qu'ils ne sont pas passés.

Cadence, résolution, durée ou vitesse et **ralentis** viennent de la section `video`,
comme pour la vidéo rendue (`core/temps.instants_de_vol`).

Ni OpenGL ni GPU : c'est la sortie à utiliser quand `cfd-trajcast diagnostic` ne trouve
aucune fenêtre de rendu. Les images vont directement de Matplotlib à ffmpeg, sans PNG
intermédiaire (`cfd_plot.anim.Mp4Stream`). ffmpeg est cherché dans
`$CFD_PLOT_FFMPEG`, puis sur le `PATH`, puis dans la roue `imageio-ffmpeg`, qui est déjà
une dépendance de cfd-trajcast. Comptez environ 70 ms par image en 540p sur un portable :
une minute de vol à 15 ips en un peu plus d'une minute.

## 4. Dépendance à cfd-plot

`engine/figure_ensemble.py` est le seul module qui importe cfd-plot et `mpl_toolkits`
(règle vérifiée dans `tests/test_architecture.py`). Sans cfd-plot, la figure et
l'animation lèvent `ErreurFigure` avec la commande d'installation, et
`cfd-trajcast ensemble` se replie sur le schéma SVG maison en le signalant.
