# Exemple cfd-aq

Tout part d'un constat d'atelier : un panneau ne se repose jamais parfaitement
à fleur. Reste à savoir ce que la marche coûte.

| Fichier | Ce qu'il montre |
| --- | --- |
| `CAS_VOILURE.yaml` | un cas complet : point de vol, couche limite, cinq aspérités |
| `01_budget_trainee.py` | le coût en *counts* de traînée en fonction de la hauteur, et ce que rapporte un chanfrein |
| `02_arete_contre_deux_marches.py` | pourquoi une arête n'est pas la somme de ses deux marches |
| `RUN_EXEMPLE.sh` | enchaîne le tout, figures comprises |

```bash
./RUN_EXEMPLE.sh
```

Le piège principal n'est pas dans l'outil : **les conditions demandées sont
locales**, au bord de la couche limite à l'abscisse de l'aspérité, pas à
l'infini amont. Sur un extrados, s'y tromper sous-estime la traînée d'un bon
tiers. Et les corrélations sont à gradient de pression nul : sur un profil,
voir `facteur_amplification_nash_bradshaw`.
