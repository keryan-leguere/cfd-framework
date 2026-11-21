# MODELE_AERO — un code Fortran 77 encapsulé en Python

Un projet organisé comme on aimerait recevoir un code à vérifier : les
sources, la documentation, l'encapsulation Python et la validation qui passe
par elle. Le modèle est **factice** mais a la forme des vrais : Mach, α, β,
CDG, propulsion et braquages en entrée, six coefficients en sortie, tables
carrées en dur dans un `BLOCK DATA` (six 2D, une 1D, une 5D en angles
polaires), initialisation (constantes du calcul) puis calcul par deux
`ENTRY`, et une sonde de validation après chaque lecture de table.

```
MODELE_AERO/
├── SOURCES/               le code livré (Fortran 77, format fixe, ASCII)
│   ├── aero_dim.inc         dimensions et COMMON des tables
│   ├── aero_probe.inc       COMMON /PROBE/ : sondes de validation
│   ├── aero_tables.f        BLOCK DATA : les tables en dur (généré)
│   ├── aero_interp.f        interpolation 1D / 2D / 5D avec saturation
│   └── aero_modele.f        AERO : ENTRY AERINI (init), ENTRY AERCAL (calcul)
├── DOC/
│   └── 01_SOURCES.md        ce que font les sources, conventions, codes d'erreur
├── PYTHON/                encapsulation f2py (voir PYTHON/README.md)
│   ├── construire.sh        sources → module aerolib*.so (un appel à f2py)
│   ├── modele_f2py.py       classe générique ModeleF2py
│   ├── modele_aero.py       ModeleAero : ce qui est propre à ce code
│   └── exemple_appel.py
├── VALIDATION/            tests cfd-validation, par l'encapsulation (un répertoire par test)
│   ├── RUN_VALIDATION.sh    lance tous les tests, puis le récapitulatif SORTIE/RECAP.txt
│   ├── recapituler.py
│   └── 01_LECTURE_TABLES/   chaque nœud de chaque table, relu par le code
└── OUTILS/
    └── generer_tables.py    régénère SOURCES/aero_tables.f
```

## En quelques commandes

```bash
cd PYTHON
bash construire.sh            # gfortran + f2py (meson, ninja) → aerolib*.so
python exemple_appel.py       # un point, un DataFrame de 180 cas
cd ../VALIDATION
bash RUN_VALIDATION.sh        # tous les tests, puis « TOUT EST À 100 % » ou non
```

```python
from modele_aero import ModeleAero

modele = ModeleAero(lref=0.2)              # appelle aerini(xref, yref, zref, lref)
sortie = modele.calculer_df(df)            # colonnes mach … dn → + cx … cn, ierr, sondes
```

Prérequis : `gfortran`, numpy ≥ 1.26, `meson` et `ninja` (`pip install meson
ninja`). Le détail de l'encapsulation et la marche à suivre pour un autre
code sont dans `PYTHON/README.md` ; les sources sont expliquées dans
`DOC/01_SOURCES.md`.
