# Contrôle qualitatif par jalon

Chaque jalon se termine par des images à regarder, produites par :

```bash
python 02_CONTROLE/generer_controle.py --jalon J1
```

Les sorties vont dans `02_CONTROLE/<jalon>/` (git-ignorées, sauf `MANIFESTE.txt`,
qui dit quoi regarder et avec quelle pile elles ont été produites). Un jalon n'est
clos qu'après relecture.

| Jalon | Ce qu'on regarde |
|---|---|
| J0 | l'Aim9 rendu hors écran, GPU et logiciel (`J0/`, prototypes compris) |
| J1 | trièdres corps / ENU et vitesse sur l'Aim9 à 4 instants du vol de référence : nez ≡ vitesse, roulis visible, même lecture en ENU+quaternion et NED+Euler |
| J2 | planche 4 instants + tout le vol en 10 s de vidéo 1080p, caméra de poursuite, fond uni |
| J3 | `CONFIG_MULTIVUES.yaml` : planche de 6 instants (chaque étape de séquence et ses fondus) + tout le vol en temps réel, 1080p |
| J3b | retours J3 : titre en haut ; `CONFIG_ENSEMBLE.yaml`, vue d'ensemble NED en principale + zooms ; planche 5 instants + vol complet 1080p |
| J4 | `CONFIG_MULTIVUES` sobre ∣ conférence côte à côte ; `CONFIG_VIRAGE` : planche 4 instants + vol complet 1080p avec ralentis |
| J4b | jets par phases et scénarios `01_EXEMPLE/SCENARIOS/` : une planche de 6 instants et une vidéo 1080p par scénario |
| J5 | `ROCKETPY/CONFIG_ROCKETPY.yaml` : planche 6 instants + vidéo 1080p rendue en parallèle (événements et télémétrie venus de RocketPy) ; temps de simulation et de relecture du cache ; débit série / parallèle ; scénarios avion re-rendus avec l’Aim9 |
| V | figures de vent (`cfd-trajcast vent`) : roses Nord/Est + profil vertical à 3, 8 et 5 instants (16 et 8,5 cm), vidéo sans rendu de tout le vol et 3 images extraites |
| J6 | `FUSEE_NUIT_4K` : planche 6 instants + vidéo 4K complète (préréglage nuit) ; `FUSEE_NUIT_BLENDER` : extrait rendu par Blender ; comparaison PyVista ∣ Blender aux mêmes instants. Se lance avec un Python qui a bpy (3.13) |
