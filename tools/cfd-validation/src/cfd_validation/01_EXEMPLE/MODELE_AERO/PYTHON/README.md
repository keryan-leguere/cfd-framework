# Encapsulation Python (f2py)

Le code Fortran devient un module Python avec f2py, puis une classe dont on
appelle la phase de calcul sur un point ou sur un DataFrame.

```
PYTHON/
├── construire.sh     sources Fortran → module aerolib*.so (un appel à f2py)
├── modele_f2py.py    ModeleF2py : la mécanique, sans rien du modèle aéro
├── modele_aero.py    ModeleAero : les 4 lignes propres à ce code
└── exemple_appel.py  un point, un DataFrame, une constante qui varie
```

## 1. Construire le module

```bash
pip install meson ninja             # ou : pip install -e "tools/cfd-validation[f2py]"
bash construire.sh                                      # aerolib.cpython-*.so dans ce dossier
FFLAGS="-O3 -ffast-math" bash construire.sh aerolib_o3  # une autre compilation, sous un autre nom
FC=ifx bash construire.sh aerolib /ailleurs             # autre compilateur, autre dossier
```

C'est un script bash de quelques lignes : un appel à `python -m numpy.f2py -c
--backend meson`, dans un dossier temporaire, avec `FC` et `FFLAGS`. L'interpréteur
est `CFD_VALIDATION_PYTHON` (`python3` par défaut) ; son dossier passe en tête du
`PATH`, là où pip a installé meson et ninja. Le script refuse un source non ASCII (f2py ne le lit pas : un accent
dans un commentaire suffit) et affiche, une fois le module construit, ce que
f2py a exposé :

```
  cx,cy,cz,cl,cm,cn,ierr = aercal(mach,alpha,beta,xg,yg,zg,ipropu,dm,dn)
  ierr = aerini(xref,yref,zref,lref)
  COMMON /aertab/
  …
```

Ces signatures viennent des directives placées après chaque `ENTRY` :

```fortran
      ENTRY AERCAL(MACH, ALPHA, BETA, XG, YG, ZG, IPROPU,
     &             CX, CY, CZ, CL, CM, CN, IERR)
Cf2py intent(in) MACH, ALPHA, BETA, XG, YG, ZG, IPROPU
Cf2py intent(out) CX, CY, CZ, CL, CM, CN, IERR
```

Pour un compilateur Fortran, ce sont des commentaires (ligne qui commence par
`C`) : le code reste compilable tel quel. Une sortie `intent(out)` disparaît
des arguments Python et passe dans le tuple rendu. Les sorties gagnent à être
scalaires : chaque scalaire est une colonne nommée.

Le nom du module est figé dans le binaire : deux compilations à comparer se
construisent sous deux noms (`aerolib_o0`, `aerolib_o3`) et se chargent côte
à côte dans le même processus, chacune avec son propre état Fortran.

## 2. Appeler le modèle

```python
from modele_aero import ModeleAero

modele = ModeleAero()                 # aerini(xref=1.2, yref=0, zref=0, lref=0.2)
modele = ModeleAero(lref=0.25)        # une constante changée, sans toucher au Fortran
modele.calculer(mach=0.8, alpha=5.0, beta=0.0, xg=1.1, yg=0.0, zg=0.0, ipropu=1, dm=0.0, dn=0.0)
# {'cx': -0.28…, 'cy': 0.0, …, 'ierr': 0}

sortie = modele.calculer_df(df)       # df : colonnes mach … dn (+ ce qu'on veut)
modele.lire("aertab.tcx")             # une variable de COMMON (table, grille), copiée
```

Le déroulé, pour une phase quelconque :

1. les arguments de la phase sont **lus dans la docstring f2py**
   (`aerolib.aercal.__doc__`), en minuscules, dans l'ordre ;
2. chacun est pris dans un **attribut de l'objet** du même nom
   (`self.mach`, `self.lref`) ;
3. la phase est appelée par **mots-clés** : `aercal(**arguments)` ;
4. les sorties sont associées à leurs noms : `{"cx": …, "ierr": …}`.

`__init__` écrit les constantes en attributs (`CONSTANTES` de la classe, puis
les mots-clés passés) et appelle les phases d'init ; une sortie `ierr` non
nulle lève `ErreurModele`. `calculer(**point)` écrit le point en attributs
puis appelle la phase de calcul.

**DataFrame** (`calculer_df`). Les colonnes portent les noms des arguments,
init puis calcul, dans l'ordre des phases (`modele.colonnes_entree`) :

| colonne                     | rôle                                                                       |
|-----------------------------|----------------------------------------------------------------------------|
| `mach` … `ipropu`           | arguments de `aercal`, obligatoires                                        |
| `xref` … `lref`             | arguments de `aerini`, facultatifs : absents, l'attribut ; présents, réinit à chaque changement de valeur |
| toute autre (`cas`, …)      | recopiée telle quelle                                                      |

La sortie est le DataFrame d'entrée (index compris), augmenté des sorties
dans l'ordre de la docstring : `cx, cy, cz, cl, cm, cn, ierr`. Une valeur
non entière dans une colonne entière (`ipropu = 0.5`) est refusée, pas
tronquée.

**L'état Fortran est global au processus.** Les variables `SAVE` d'AERINI
sont les mêmes pour tous les objets construits sur `aerolib`. Chaque objet
note la dernière initialisation faite sur sa bibliothèque et la refait si ce
n'est plus la sienne : deux objets aux `lref` différentes donnent chacun le
bon résultat, au prix d'une réinit à chaque alternance.

**Sondes** (`SONDES = ("probe",)`). Blocs COMMON que le code remplit en
cours de calcul pour la validation : chaque valeur lue dans une table y est
recopiée (`VALID_TAB_CX` …, voir `DOC/01_SOURCES.md` § 8). Avant chaque appel,
leurs variables réelles sont remises à **NaN** ; après l'appel, elles sont
rendues avec les sorties, sous leur nom f2py (`valid_tab_cx`), en colonnes
`float64` dans `calculer_df`. Une sonde que l'appel n'a pas atteinte vaut donc
NaN, jamais la valeur de l'appel précédent. Les variables sont lues dans la
docstring f2py du bloc ; une sonde tableau ou homonyme d'une sortie est
refusée.

**`lire("bloc.variable")`** rend une copie d'une variable de COMMON (casse
indifférente), avec la forme et l'ordre d'indices du Fortran : `TCX(NM, NA)`
donne `(7, 7)`, `[i, j]` valant `TCX(I+1, J+1)`. C'est là que le test de
lecture de table prend ses tables et leurs grilles : telles que le code les
voit.

## 3. Pour un autre code

1. après chaque `ENTRY` (ou en tête de chaque `SUBROUTINE` appelée de
   l'extérieur), une ligne `Cf2py intent(in)` et une ligne
   `Cf2py intent(out)` ;
2. dans `construire.sh`, `SOURCES` et `INCLUDES` ;
3. une sous-classe :

```python
class MonCode(ModeleF2py):
    BIBLIOTHEQUE = "moncode"
    DOSSIER = Path(__file__).resolve().parent
    PHASES_INIT = ("monini",)          # 0, 1 ou plusieurs, dans l'ordre d'appel
    PHASE_CALCUL = "moncal"
    CONSTANTES = {"lref": 0.2}         # défauts des arguments d'init
    SONDES = ("probe",)                # COMMON de sondes, s'il y en a
```

`verifier_init` se surcharge si l'erreur d'init ne se lit pas dans une sortie
`ierr` (`SORTIE_ERREUR_INIT = None` désactive le contrôle). Limites : une
seule phase de calcul ; pas d'entrée tableau dans `calculer_df` (refusée,
nommée) ; une sortie tableau devient `nom_1 … nom_n`.
