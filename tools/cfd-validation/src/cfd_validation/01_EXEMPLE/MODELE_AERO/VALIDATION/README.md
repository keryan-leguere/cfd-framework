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
├── 03_INTERPOLATION_TABLES/  entre les nœuds : interpolation multilinéaire ? + les polaires
└── 04_INTEGRATION/        REFERENCE/*.csv d'un autre environnement, rejoués par ce code
```

Ce dossier est la **démonstration** : chaque test y a une option `--defaut`
qui le fausse exprès. La copie à livrer, identique sans ces options, est
`../VALIDATION_PRODUCTION/` ; une table ou une tolérance changée ici doit l'être
là aussi (les tests du paquet le vérifient).

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
== 04_INTEGRATION           conforme (6 s) — SORTIE/04_INTEGRATION.txt

==============================================================================
RÉCAPITULATIF DE LA VALIDATION — 2026-11-21T23:42:01+00:00 (UTC)
==============================================================================
Test                     Verdict       Détail                   Conformes
------------------------------------------------------------------------------
01_LECTURE_TABLES        CONFORME      8/8 tables, 26888 appels     100 %
02_BORNES_TABLES         CONFORME      8/8 tables, 4545 appels      100 %
03_INTERPOLATION_TABLES  CONFORME      8/8 tables, 40270 appels     100 %
04_INTEGRATION           CONFORME      7/7 sorties, 1016 lignes         100 %
------------------------------------------------------------------------------
4/4 tests conformes — TOUT EST À 100 %
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

**Les valeurs par défaut** des arguments — celles que prend un argument quand
la table testée ne le pilote pas — ne s'y écrivent pas : elles viennent du
modèle (`PYTHON/modele_aero.py`), `ModeleAero.DEFAUTS` pour les phases d'init
et `ModeleAero.DEFAUTS_CALCUL` pour AERCAL. Ces dernières ne servent qu'à ça :
le modèle ne s'en sert jamais pour calculer. `tables_modele.DEFAUTS =
ModeleAero.defauts_complets()`, et `charger_modele` sort en erreur (code 1)
si un argument n'a pas de valeur. Une valeur propre à la validation se
surcharge là : `{**ModeleAero.defauts_complets(), "biaicx": 0.005}`.

## Ajouter un test

Quatre étapes, et rien d'autre à toucher : `RUN_VALIDATION.sh` lance ce que
liste `TESTS`, `recapituler.py` lit le `resume.json` de chacun.

**1. Un répertoire et un script.** `05_MON_TEST/05_mon_test.py`, en partant
de ce squelette (ou du test existant le plus proche) :

```python
#!/usr/bin/env python3
"""Test 05 du modèle aéro : <la question à laquelle il répond>.

Code de retour : 0 conforme, 2 non conforme, 1 erreur.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))  # VALIDATION/ : tables_modele

from tables_modele import DEFAUTS, PYTHON, charger_modele, declarer_tables, metadonnees  # noqa: E402

from cfd_validation import valider_lecture_tables  # noqa: E402  (ou la façade qui convient)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--module", default="aerolib", help="module f2py à tester")
    p.add_argument("--dossier", type=Path, default=PYTHON, help="où chercher le module")
    p.add_argument("--sortie", type=Path, default=None, help="dossier des pièces")
    p.add_argument("--sans-figures", action="store_true", help="ne pas tracer les figures")
    args = p.parse_args()

    modele = charger_modele(args.module, args.dossier)
    if modele is None:
        return 1
    res = valider_lecture_tables(
        declarer_tables(modele),
        evaluer=modele.calcul_aero_elementaire,   # toujours le Fortran tel quel
        defauts=DEFAUTS,
        identifiant="VAL-XXX-05",                 # l'exigence vérifiée, reprise partout
        metadonnees=metadonnees(modele, "nominal"),
        sortie=args.sortie or ICI / "SORTIE" / "nominal",
        figures=not args.sans_figures,
        nettoyer=True,                            # (valider_integration : ajouter formats=("svg",))
    )
    return 0 if res.conforme else 2


if __name__ == "__main__":
    sys.exit(main())
```

Le contrat, le seul que `RUN_VALIDATION.sh` suppose :
- accepter `--sortie DIR`, `--module` et `--dossier`, plus les options globales
  (`--sans-figures`) ;
- écrire `resume.json` dans `DIR` (toute façade de `cfd-validation` le fait) ;
- rendre **0** s'il est conforme, **2** s'il ne l'est pas, autre chose en cas
  d'erreur (affiché « ERREUR » dans le récapitulatif).

Le récapitulatif détaille un test de table (`tables` dans `resume.json`) ou
d'intégration (`sorties`) ; pour un autre contrôle, il affiche le verdict seul.

**2. Une ligne dans `TESTS=(…)` de `RUN_VALIDATION.sh`** : répertoire, script,
options propres au test.

```bash
    "05_MON_TEST|05_mon_test.py|--combinaisons"
```

**3. (Facultatif) CMake** : une ligne dans `../CMakeLists.txt` donne une cible
`cmake --build build -t mon_test` et un test `ctest` :

```cmake
test_validation(mon_test 05_MON_TEST 05_mon_test.py --combinaisons)
```

**4. La copie de production** : le même script dans
`../VALIDATION_PRODUCTION/05_MON_TEST/`, sans option de démonstration
(`--defaut`) et avec `analyseur()` de son `tables_modele.py` au lieu
d'`argparse.ArgumentParser` (une option inconnue sort alors en 1, jamais en 2),
plus la même ligne dans son `RUN_VALIDATION.sh`. Ajouter le script à `SCRIPTS`
dans `tests/test_modele_aero.py` : le test du paquet vérifie qu'il n'accepte pas
`--defaut`.

Une option `--defaut` (démonstration seulement) est la bienvenue : elle fausse
le test exprès, pour montrer qu'il sait échouer et à quoi ressemble l'échec.
