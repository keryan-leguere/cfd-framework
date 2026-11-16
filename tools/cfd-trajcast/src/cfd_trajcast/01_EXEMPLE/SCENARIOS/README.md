# Scénarios

Trois vols synthétiques, prêts à rendre, pour voir l'outil hors du cas « fusée qui
monte » : un avion qui décolle et manœuvre, un avion en panne qui part en spirale,
une fusée à deux étages. Trajectoires et événements sont **fabriqués par le
paquet** (`cfd_trajcast.core.manoeuvres`) : `generer_scenarios.py`
les régénère. La maquette est partout la CAO de l'exemple, `../MAQUETTE/Aim9.stl`,
y compris pour les deux trajectoires d'avion.

```bash
bash RUN_SCENARIOS.sh            # check + aperçu (540p) des trois scénarios
bash RUN_SCENARIOS.sh --complet  # check + rendu 1080p
cfd-trajcast rendre AVION_PANNE.yaml --apercu          # un seul
cfd-trajcast image AVION_MANOEUVRES.yaml --t 120       # une image (sommet de la boucle)
```

| Fichier | Vol | Ce qu'il montre |
|---|---|---|
| `AVION_MANOEUVRES.yaml` | roulage, décollage, montée, virage à 60°, boucle, tonneau, descente en virage (190 s) | postcombustion au décollage et dans la boucle, réacteur sec ailleurs ; poursuite + ensemble NED + caméra au bout de piste + cockpit ; télémétrie avion (kt, ft, g, inclinaison, pente, cap) ; ralentis sur la rotation et le tonneau |
| `AVION_PANNE.yaml` | croisière à 4 000 m, panne, plané, grand virage, perte de contrôle, spirale jusqu'à 150 m (107 s) | jet « panne » (feu vacillant, fumée noire turbulente) ; vue d'ensemble en principale ; l'orbite remplace le cockpit au début de la spirale (séquence déclenchée par un **nom d'événement**) |
| `FUSEE_BI_ETAGE.yaml` | virage gravitaire, étage 1, séparation, étage 2, apogée à 15 km (75 s) | deux jets différents : poudre (flamme orange évasée, panache blanc) puis ergols liquides (flamme bleutée, disques de Mach, fumée légère) ; caméra à images clés ; ralenti ×4 sur la séparation |

Deux variantes du vol bi-étage (J6) :

| Fichier | Ce qu'il montre |
|---|---|
| `FUSEE_NUIT_4K.yaml` | le même vol **de nuit et en 4K** : ciel étoilé, clair de lune, flammes qui éclairent la maquette, la fumée et le sol, halo |
| `FUSEE_NUIT_BLENDER.yaml` | le même vol de nuit rendu par **Blender** (bpy, EEVEE), 8 premières secondes ; `pip install bpy` (Python 3.13) |

Fichiers produits par `generer_scenarios.py` :

* `<scénario>.csv` — t, x, y, z (ENU, m), quaternion `qw qx qy qz` corps FRD → ENU, et les
  grandeurs du simulateur : `V`, `mach`, `n`, `inclinaison`, `pente`, `cap`, `incidence` ;
* `<scénario>_evenements.csv` — `t,nom`, lu directement par `trajectoire.evenements`.

Ce que ce dossier ne prétend pas faire : le simulateur est un point matériel piloté
(portance, poussée, traînée en V², pesanteur), pas un modèle aérodynamique ; le
train d'atterrissage n'est pas modélisé (d'où `style.sol.altitude: -0.4` pour que
la maquette roule au-dessus de la piste) ; il n'y a pas de piste dessinée.
