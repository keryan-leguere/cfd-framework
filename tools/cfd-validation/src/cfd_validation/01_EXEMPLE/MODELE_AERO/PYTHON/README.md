# Encapsulation Python (f2py)

Le code Fortran devient un module Python avec f2py, puis une classe dont on
appelle la phase de calcul sur un point ou sur un DataFrame.

```
PYTHON/
├── construire.sh     sources Fortran → module aerolib*.so (un appel à f2py)
├── modele_f2py.py    ModeleF2py : la mécanique, sans rien du modèle aéro
├── modele_aero.py    ModeleAero : la surcouche propre à ce code (conversions, sorties en plus)
└── exemple_appel.py  paramètres standard, arguments Fortran, une constante qui varie
```

## 1. Construire le module

```bash
pip install meson ninja             # ou : pip install -e "tools/cfd-validation[f2py]"
bash construire.sh                                      # aerolib.cpython-*.so dans ce dossier
FFLAGS="-O3 -ffast-math" bash construire.sh aerolib_o3  # une autre compilation, sous un autre nom
FC=ifx bash construire.sh aerolib /ailleurs             # autre compilateur, autre dossier
```

Les sources sont **un dossier** : `DOSSIER_SOURCES` (ici `../SOURCES`), dont
tout fichier `*.f *.F *.for *.f90 *.F90` est compilé (`MOTIFS`), et `INCLUDES`
la liste des dossiers des `INCLUDE`. Ajouter un fichier au dossier suffit ; n'y
laisser que le code livré.

C'est un script bash de quelques lignes : un appel à `python -m numpy.f2py -c
--backend meson`, dans un dossier temporaire, avec `FC` et `FFLAGS`. L'interpréteur
est `CFD_VALIDATION_PYTHON` (`python3` par défaut) ; son dossier passe en tête du
`PATH`, là où pip a installé meson et ninja. Le script refuse un source non ASCII (f2py ne le lit pas : un accent
dans un commentaire suffit) et affiche, une fois le module construit, ce que
f2py a exposé :

```
  cx,cy,cz,cl,cm,cn,ierr = aercal(mach,alpha,beta,xg,yg,zg,ipropu,dm,dn)
  aercfg(biaicx)
  aerini(xref,yref,zref,lref)
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

Deux couches, deux fichiers.

**`ModeleF2py`** (`modele_f2py.py`) est générique et ne connaît rien du modèle
aéro. Il charge le module, lit les signatures, appelle les phases et lit les
sondes. **Il ne garde aucune valeur d'argument** : pas de constante cachée dans
l'objet, tout vient du DataFrame.

1. les arguments de chaque phase sont **lus dans la docstring f2py**
   (`aerolib.aercal.__doc__`), en minuscules, dans l'ordre ;
2. `calcul_elementaire(df)` prend **une colonne par argument**, init puis calcul
   (`modele.colonnes_entree` : `xref, yref, zref, lref, biaicx, mach, … dn`), toutes
   obligatoires sauf les dimensions que f2py déduit ;
3. pour chaque ligne, les phases d'init (`PHASES_INIT`, ici `aerini` puis
   `aercfg`) sont toutes rappelées, dans l'ordre, **si l'un de leurs arguments a
   changé** depuis la dernière init faite sur la bibliothèque, puis la phase de
   calcul, par mots-clés ;
4. la sortie est le DataFrame d'entrée (index et autres colonnes compris),
   augmenté des sorties dans l'ordre de la docstring (`cx … cn, ierr`) puis des
   sondes. `calcul_point(**point)` fait la même chose pour un point.

Une valeur non entière dans une colonne entière (`ipropu = 0.5`) est refusée,
pas tronquée ; une sortie déjà présente en entrée aussi. Les phases d'init
n'ont **pas de code de retour** : une init refusée se lit dans les sorties du
calcul (ici `ierr = 1`).

**`ModeleAero`** (`modele_aero.py`) est la surcouche propre à ce code :

```python
from modele_aero import ModeleAero

modele = ModeleAero()                          # charge aerolib, rien d'autre
brut = modele.calcul_aero_elementaire(df_f)    # arguments Fortran tels quels → sorties + sondes
sortie = modele.calcul_aero(df)                # paramètres standard → sorties + colonnes en plus
```

| Fonction | Entrée | Sortie |
|----------|--------|--------|
| `calcul_aero_elementaire` | les arguments de AERINI, AERCFG et AERCAL, unités et conventions du Fortran (CDG en m, axes FRD, `ipropu` 0/1) | + `cx … cn`, `ierr`, sondes |
| `calcul_aero` | `ModeleAero.PARAMETRES` : CDG en mm en axes FLU (`xg_mm`, `yg_mm`, `zg_mm`), `propulsion` booléen ; `xref … lref`, `biaicx` facultatifs (`DEFAUTS`) | + les arguments élémentaires calculés, les sorties, et `etat`, `modele`, `version`, `bibliotheque` |

`calcul_aero` = `vers_elementaire` (conversions : unités, signes, valeurs par
défaut) → `calcul_aero_elementaire` → `completer_sorties` (tout ce qu'on veut
retrouver en plus dans le vecteur de sortie). Une colonne en convention Fortran
(`xg`, `ipropu`) mêlée aux paramètres standard est refusée : on passe par l'un
ou par l'autre. **La validation passe par `calcul_aero_elementaire`** : elle
teste le code, pas la surcouche.

**L'état Fortran est global au processus.** Les variables `SAVE` d'AERINI sont
les mêmes pour tous les objets construits sur `aerolib`. La dernière init faite
sur chaque bibliothèque est suivie au niveau du module : deux objets, ou deux
lignes, aux `lref` différentes donnent chacun le bon résultat, au prix d'une
réinit à chaque alternance.

**Sondes** (`SONDES = ("probe",)`). Blocs COMMON que le code remplit en
cours de calcul pour la validation : chaque valeur lue dans une table y est
recopiée (`VALID_TAB_CX` …, voir `DOC/01_SOURCES.md` § 8). Avant chaque appel,
leurs variables réelles sont remises à **NaN** ; après l'appel, elles sont
rendues avec les sorties, sous leur nom f2py (`valid_tab_cx`), en colonnes
`float64`. Une sonde que l'appel n'a pas atteinte vaut donc NaN, jamais la
valeur de l'appel précédent. Les variables sont lues dans la docstring f2py du
bloc ; une sonde tableau ou homonyme d'une sortie est refusée.

**`lire("bloc.variable")`** rend une copie d'une variable de COMMON (casse
indifférente), avec la forme et l'ordre d'indices du Fortran : `TCX(NM, NA)`
donne `(7, 7)`, `[i, j]` valant `TCX(I+1, J+1)`. C'est là que les tests de
table prennent leurs tables et leurs grilles : telles que le code les voit.

## 3. Pour un autre code

1. après chaque `ENTRY` (ou en tête de chaque `SUBROUTINE` appelée de
   l'extérieur), une ligne `Cf2py intent(in)`, et une ligne `Cf2py intent(out)`
   pour la phase de calcul (les phases d'init n'ont pas de code de retour) ;
2. dans `construire.sh`, `DOSSIER_SOURCES` (et au besoin `MOTIFS`, `INCLUDES`) ;
3. une sous-classe, sur le modèle de `ModeleAero` :

```python
class MonCode(ModeleF2py):
    BIBLIOTHEQUE = "moncode"
    DOSSIER = Path(__file__).resolve().parent
    PHASES_INIT = ("monini",)          # 0, 1 ou plusieurs, dans l'ordre d'appel
    PHASE_CALCUL = "moncal"
    SONDES = ("probe",)                # COMMON de sondes, s'il y en a

    def calcul_elementaire_moncode(self, df):   # les arguments Fortran tels quels
        return self.calcul_elementaire(df)

    def calcul_moncode(self, df):               # paramètres standard → conversions → sorties en plus
        return self.completer(self.calcul_elementaire(self.convertir(df)))  # convertir, completer : à écrire
```

Limites :
une seule phase de calcul ; pas d'entrée tableau en colonne (refusée, nommée) ;
une sortie tableau devient `nom_1 … nom_n`.
