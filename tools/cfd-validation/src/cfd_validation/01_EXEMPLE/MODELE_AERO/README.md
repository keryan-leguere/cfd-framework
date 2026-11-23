# MODELE_AERO — un code Fortran 77 encapsulé en Python

Un projet organisé comme on aimerait recevoir un code à vérifier : les
sources, la documentation, l'encapsulation Python et la validation qui passe
par elle. Le modèle est **factice** mais a la forme des vrais : Mach, α, β,
CDG, propulsion et braquages en entrée, six coefficients en sortie, tables
carrées en dur dans un `BLOCK DATA` (six 2D, une 1D, une 5D en angles
polaires), initialisation (constantes du calcul), configuration (biais sur CX) puis
calcul par trois `ENTRY`, une sonde de validation après chaque lecture de table, et une consigne
hors grille par axe (saturation en Mach, extrapolation linéaire en α et β).

```
MODELE_AERO/
├── SOURCES/               le code livré (Fortran 77, format fixe, ASCII)
│   ├── aero_dim.inc         dimensions et COMMON des tables
│   ├── aero_probe.inc       COMMON /PROBE/ : sondes de validation
│   ├── aero_tables.f        BLOCK DATA : les tables en dur (généré)
│   ├── aero_interp.f        interpolation 1D / 2D / 5D avec saturation
│   └── aero_modele.f        AERO : ENTRY AERINI (init), AERCFG (biais sur CX), AERCAL (calcul)
├── DOC/
│   └── 01_SOURCES.md        ce que font les sources, conventions, codes d'erreur
├── PYTHON/                encapsulation f2py (voir PYTHON/README.md)
│   ├── construire.sh        sources → module aerolib*.so (un appel à f2py)
│   ├── modele_f2py.py       classe générique ModeleF2py
│   ├── modele_aero.py       ModeleAero : ce qui est propre à ce code
│   ├── exemple_appel.py
│   ├── calcul_yaml.py       points de vol d'un fichier YAML → CSV
│   └── exemple_pdv.yaml
├── VALIDATION/            tests cfd-validation, par l'encapsulation (un répertoire par test)
│   ├── RUN_VALIDATION.sh    lance tous les tests, puis le récapitulatif SORTIE/RECAP.txt
│   ├── recapituler.py
│   ├── tables_modele.py     les tables du modèle, leurs polaires, déclarées une fois pour tous les tests
│   ├── 01_LECTURE_TABLES/   chaque nœud de chaque table, relu par le code
│   ├── 02_BORNES_TABLES/    au-delà des bornes : sature ou extrapole comme demandé ?
│   ├── 03_INTERPOLATION_TABLES/  entre les nœuds : interpolation multilinéaire ? + polaires
│   └── 04_INTEGRATION/      CSV d'un autre environnement (REFERENCE/), rejoués et comparés
├── VALIDATION_PRODUCTION/ les mêmes tests sans option pour les fausser (--defaut) : à livrer
├── OUTILS/
│   ├── generer_tables.py    régénère SOURCES/aero_tables.f
│   └── nettoyer.cmake       efface les sorties (cibles nettoyer, nettoyer_tout)
├── CMakeLists.txt         les commandes de base en un point d'entrée (facultatif)
├── cmake.sh               une cible CMake en une commande (configure build/ au besoin)
├── CMakePresets.json
└── gitignore.exemple      un .gitignore complet pour ce genre de projet (à renommer)
```

## En quelques commandes

```bash
cd PYTHON
bash construire.sh            # gfortran + f2py → aerolib*.so + aerolib.compilation.log
python exemple_appel.py       # un point, un DataFrame de 180 cas
python calcul_yaml.py exemple_pdv.yaml   # points de vol en YAML → SORTIE/exemple_pdv.csv
cd ../VALIDATION
bash RUN_VALIDATION.sh        # tous les tests, puis « TOUT EST À 100 % » ou non
cd ../VALIDATION_PRODUCTION
bash RUN_VALIDATION.sh        # idem, la copie de production (pas de --defaut)
```

`VALIDATION/` est la démonstration : chaque test y a un `--defaut` qui le
fausse exprès, pour montrer à quoi ressemble un échec. `VALIDATION_PRODUCTION/`
est la copie à livrer et à faire tourner pour produire une preuve : mêmes
tables, mêmes tolérances, mêmes verdicts, et aucune option capable de rendre un
test faux (une option inconnue y sort en erreur, code 1, jamais en « non
conforme »).

```python
from modele_aero import ModeleAero

modele = ModeleAero()                      # charge aerolib
sortie = modele.calcul_aero(df, csv="res.csv")  # paramètres standard (csv= : aussi en fichier) → + cx … cn, ierr, sondes, etat, modele…
brut = modele.calcul_aero_elementaire(df_f)  # xref … lref, biaicx, mach … dn (le Fortran tel quel) → + sorties, sondes
```

## Avec CMake

Les mêmes commandes, avec les dépendances en plus : le module est reconstruit
quand une source change, et la validation le construit d'abord. CMake ne
compile rien lui-même, il appelle les scripts ci-dessus, qui restent
utilisables sans lui.

```bash
cmake -B build                       # une fois : choisit Python, vérifie gfortran, numpy (meson, ninja si besoin)
cmake --build build                  # construit PYTHON/aerolib*.so
cmake --build build -t validation    # les quatre tests, puis SORTIE/RECAP.txt
cmake --build build -t validation_production   # idem avec VALIDATION_PRODUCTION/
cmake --build build -t nettoyer      # efface SORTIE/ et __pycache__/ (nettoyer_tout : et les *.so)
cmake --build build -t aide          # toutes les cibles et les réglages
ctest --test-dir build               # construit, puis un test ctest par test de validation
```

`cmake --build build …` sans le `cmake -B build` d'abord, ou lancé depuis un
autre dossier que celui-ci, donne « build is not a directory ». `cmake.sh` fait
les deux étapes et marche depuis n'importe où :

```bash
bash cmake.sh                        # configure build/ s'il manque, construit le module
bash cmake.sh validation             # n'importe quelle cible, ou plusieurs
```

Les réglages restent ceux de `build/` : `cmake -B build -DFFLAGS="-O3 -march=native"`
une fois, puis `bash cmake.sh` comme d'habitude.

Autres cibles : `exemple`, `pdv` (points de vol d'un YAML → CSV, `-DPDV_YAML=…`), `lecture`, `bornes`, `interpolation` (un test
seul), `verifier_tables`, `tables`. Réglages : `-DPYTHON=…` (défaut
`$CFD_VALIDATION_PYTHON`, sinon le venv actif, sinon `python3`), `-DFC=…`,
`-DFFLAGS=…`, `-DMODELE_NOM=…`, `-DVALIDATION_JOBS=4`,
`-DVALIDATION_OPTIONS="--sans-figures"`. Avec CMake ≥ 3.21, les presets
raccourcissent : `cmake --preset defaut`, `cmake --build --preset validation` ;
le preset `o3` construit `aerolib_o3` (`-O3 -ffast-math`) dans `build-o3/`.

`gitignore.exemple` ne s'applique pas tel quel : le copier en `.gitignore` à la
racine d'un projet du même genre.

Prérequis : `gfortran`, numpy ≥ 1.26 ; `meson` et `ninja` (`pip install meson
ninja`) seulement quand f2py passe par meson (Python ≥ 3.12).
Options pour un module plus rapide (mesurées, et ce qu'elles coûtent) :
`PYTHON/README.md`, « Options de compilation ». Le détail de l'encapsulation et la marche à suivre pour un autre
code sont dans `PYTHON/README.md` ; les sources sont expliquées dans
`DOC/01_SOURCES.md`.
