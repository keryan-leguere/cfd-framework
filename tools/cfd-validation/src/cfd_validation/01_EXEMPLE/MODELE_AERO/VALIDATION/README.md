# Validation du modèle aéro

Les tests de `cfd-validation` appliqués au modèle à travers son encapsulation
Python (`../PYTHON`), un répertoire par test.

```
VALIDATION/
├── RUN_VALIDATION.sh      lance tous les tests, puis le récapitulatif
├── recapituler.py         SORTIE/RECAP.txt : un test par ligne, conforme ou non, en %
├── tables_modele.py       les 8 tables du modèle, leurs polaires et libellés, déclarés une fois
├── 01_LECTURE_TABLES/     chaque nœud de chaque table, relu par le code
├── 02_BORNES_TABLES/      au-delà des bornes : sature ou extrapole comme demandé ?
└── 03_INTERPOLATION_TABLES/  entre les nœuds : interpolation multilinéaire ? + les polaires
```

Le module se construit d'abord, une fois :

```bash
cd ../PYTHON && bash construire.sh
```

Ou, depuis `MODELE_AERO/`, `cmake -B build && cmake --build build -t validation`
fait les deux (voir `../README.md`, « Avec CMake »).

Puis on lance tout (`CFD_VALIDATION_PYTHON` désigne l'interpréteur où
`cfd-validation` est installé, `python3` par défaut) :

```bash
bash RUN_VALIDATION.sh
```

```
== 01_LECTURE_TABLES        conforme (5 s) — SORTIE/01_LECTURE_TABLES.txt
== 02_BORNES_TABLES         conforme (3 s) — SORTIE/02_BORNES_TABLES.txt
== 03_INTERPOLATION_TABLES  conforme (20 s) — SORTIE/03_INTERPOLATION_TABLES.txt

==============================================================================
RÉCAPITULATIF DE LA VALIDATION — 2026-11-21T23:42:01+00:00 (UTC)
==============================================================================
Test                     Verdict       Détail                   Conformes
------------------------------------------------------------------------------
01_LECTURE_TABLES        CONFORME      8/8 tables, 26888 appels     100 %
02_BORNES_TABLES         CONFORME      8/8 tables, 4545 appels      100 %
03_INTERPOLATION_TABLES  CONFORME      8/8 tables, 40270 appels     100 %
------------------------------------------------------------------------------
3/3 tests conformes — TOUT EST À 100 %
==============================================================================
```

Ce qui est écrit dans `SORTIE/` :
- `<TEST>/` : les pièces du test ;
- `<TEST>.txt` : sa sortie terminal ;
- `RECAP.txt` : le récapitulatif.

Le code de retour vaut 0 si tout est conforme, 1 sinon. Les options passées
à `RUN_VALIDATION.sh` (`--sans-figures`…) sont transmises à chaque test.

**Les tables** (valeurs et grilles lues dans le COMMON, sondes, passage aux
entrées, consignes hors bornes, polaires à tracer, libellés des axes) sont déclarées une seule fois, dans
`tables_modele.py`, et importées par chaque test : pour un autre code, c'est
ce fichier qu'on réécrit.

**Ajouter un test** : un répertoire `NN_NOM/` avec son script, et une ligne
dans `TESTS=(…)` de `RUN_VALIDATION.sh`. Le script doit :
- accepter `--sortie DIR` ;
- y écrire un `resume.json` (ce que fait toute façade de `cfd-validation`) ;
- rendre 0 s'il est conforme, 2 s'il ne l'est pas.
