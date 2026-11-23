# Validation du modèle aéro — copie de production

Les mêmes tests que `../VALIDATION/`, **sans aucune option pour les fausser**.
C'est cette copie qu'on livre ou qu'on fait tourner pour produire une preuve.

| Démonstration (`../VALIDATION/`)                     | Production (ici)  |
|------------------------------------------------------|-------------------|
| `01 --defaut` : une valeur de CM faussée côté référence | absent         |
| `02 --defaut` : consigne d'alpha de CX déclarée « sature » | absent      |
| `03 --defaut` : CM relu en palier, simulé en Python    | absent          |
| `04 --defaut` : Cm décalé de 1e-9 à \|DM\| = 20°       | absent          |
| `04_INTEGRATION/generer_reference.py`                  | absent : les CSV de `REFERENCE/` sont des données |
| `declarer_tables(modele, cm_faussee=, consigne_cx_alpha=)` | `declarer_tables(modele)` |
| option inconnue → code 2 (lu « NON CONFORME »)        | option inconnue → code 1 (ERREUR) |

Le reste est identique : tables, défauts, combinaisons, tolérances et leurs
justifications, polaires, identifiants `VAL-TAB-01…03` et `VAL-INT-04`,
CSV de référence du test 4 (copie octet pour octet). Les verdicts et les
pièces d'un passage nominal sont donc les mêmes dans les deux dossiers.

```
VALIDATION_PRODUCTION/
├── RUN_VALIDATION.sh      lance tous les tests, puis le récapitulatif
├── recapituler.py         SORTIE/RECAP.txt (copie conforme de ../VALIDATION/)
├── tables_modele.py       les 10 tables (11 déclarations), sans paramètre de falsification
├── 01_LECTURE_TABLES/
├── 02_BORNES_TABLES/
├── 03_INTERPOLATION_TABLES/
└── 04_INTEGRATION/        04_integration.py + REFERENCE/*.csv
```

```bash
cd ../PYTHON && bash construire.sh      # une fois
cd ../VALIDATION_PRODUCTION
bash RUN_VALIDATION.sh                  # ou, depuis MODELE_AERO/ : cmake --build build -t validation_production
```

Les sorties vont dans `VALIDATION_PRODUCTION/SORTIE/`, comme pour la démonstration.

**À garder synchronisé** : une table, un défaut ou une tolérance modifiés dans
`../VALIDATION/tables_modele.py` doivent l'être ici aussi, comme un CSV
ajouté à `REFERENCE/` ou un alias ajouté au helper du test 4. Les tests du paquet
vérifient que les deux déclarations donnent les mêmes tables, et qu'aucun
script d'ici n'accepte `--defaut`.

Pour ajouter un test, voir « Ajouter un test » dans `../VALIDATION/README.md`
(étape 4 : la copie de production).
