# Validation du modèle aéro

Les tests de `cfd-validation` appliqués au modèle à travers son encapsulation
Python (`../PYTHON`), un répertoire par test.

```
VALIDATION/
├── RUN_VALIDATION.sh      lance tous les tests, puis le récapitulatif
├── recapituler.py         SORTIE/RECAP.txt : un test par ligne, conforme ou non, en %
└── 01_LECTURE_TABLES/     chaque nœud de chaque table, relu par le code
```

Le module se construit d'abord, une fois :

```bash
cd ../PYTHON && bash construire.sh
```

Puis on lance tout (`CFD_VALIDATION_PYTHON` désigne l'interpréteur où
`cfd-validation` est installé, `python3` par défaut) :

```bash
bash RUN_VALIDATION.sh
```

```
== 01_LECTURE_TABLES      conforme (4 s) — SORTIE/01_LECTURE_TABLES.txt

==============================================================================
RÉCAPITULATIF DE LA VALIDATION — 2026-11-21T19:22:41+00:00 (UTC)
==============================================================================
Test                   Verdict       Détail                   Conformes
------------------------------------------------------------------------------
01_LECTURE_TABLES      CONFORME      8/8 tables, 26888 appels     100 %
------------------------------------------------------------------------------
1/1 tests conformes — TOUT EST À 100 %
==============================================================================
```

Ce qui est écrit dans `SORTIE/` :
- `<TEST>/` : les pièces du test ;
- `<TEST>.txt` : sa sortie terminal ;
- `RECAP.txt` : le récapitulatif.

Le code de retour vaut 0 si tout est conforme, 1 sinon. Les options passées
à `RUN_VALIDATION.sh` (`--sans-figures`…) sont transmises à chaque test.

**Ajouter un test** : un répertoire `NN_NOM/` avec son script, et une ligne
dans `TESTS=(…)` de `RUN_VALIDATION.sh`. Le script doit :
- accepter `--sortie DIR` ;
- y écrire un `resume.json` (ce que fait toute façade de `cfd-validation`) ;
- rendre 0 s'il est conforme, 2 s'il ne l'est pas.
