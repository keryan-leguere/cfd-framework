# 02 — Bornes des tables

Appelé au-delà des bornes de ses tables, le code sature-t-il ou extrapole-t-il
comme on le lui demande ? Pour chaque table, chaque axe et chaque côté (une
**face**), le code est appelé à 10 % de l'étendue de l'axe au-delà de la borne,
les autres axes parcourant tous leurs nœuds.

```bash
python 02_bornes_tables.py                 # 11 déclarations, 43 faces, 4 615 appels
python 02_bornes_tables.py --ecart 0.25    # plus loin
python 02_bornes_tables.py --defaut        # alpha de CX déclaré « sature » : NON CONFORME (code 2)
```

Consignes du modèle, déclarées dans `../tables_modele.py` (`bornes=`) :

| Axe | Consigne |
|-----|----------|
| Mach, DM, DN, Mach de la propulsion | sature |
| α, β | extrapole |
| alphaT | inatteignable sous 0 (acos ≥ 0), extrapole au-delà de 20° |
| phiA | inatteignable (atan2 reste dans [−180°, 180°]) |

Pour chaque face, le rapport donne la consigne **attendue** et le comportement
**observé** (sature, extrapole, indiscernable, ni l'un ni l'autre). Une
consigne non respectée se lit donc directement : « attendu sature, observé
extrapole ».

Les pièces sont écrites dans `SORTIE/<scénario>/` (ou dans le dossier passé par `--sortie`) :
- `bornes_tables.log` : le rapport complet ;
- `resume.json` ;
- `RESULTATS/` : par table, un appel par ligne, avec `valeur_ATTENDUE`,
  `valeur_SATURATION`, `valeur_EXTRAPOLATION`, `valeur_CODE`, `ecart` et
  `conforme` ;
- `FIGURES/synthese_bornes_*.svg` : la synthèse.

Le mécanisme est décrit dans `00_DOC/04_BORNES_TABLES.md`, à la racine de
`cfd-validation`.
