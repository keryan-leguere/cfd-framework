# Encapsulation Python (f2py)

Le code Fortran devient un module Python avec f2py, puis une classe dont on
appelle la phase de calcul sur un point ou sur un DataFrame.

```
PYTHON/
├── construire.sh     sources Fortran → module aerolib*.so (un appel à f2py)
├── modele_f2py.py    ModeleF2py : la mécanique, sans rien du modèle aéro
├── modele_aero.py    ModeleAero : la surcouche propre à ce code (conversions, sorties en plus)
├── exemple_appel.py  paramètres standard, arguments Fortran, une constante qui varie
├── calcul_yaml.py    points de vol d'un fichier YAML → CSV
├── exemple_pdv.yaml  un fichier de points de vol commenté (paramètres standard)
└── exemple_pdv_elementaire.yaml  le même en arguments Fortran, init par défaut, avec sondes
```

## 1. Construire le module

```bash
pip install meson ninja             # seulement si f2py passe par meson (voir plus bas)
bash construire.sh                                      # aerolib.cpython-*.so dans ce dossier
FFLAGS="-O3 -ffast-math" bash construire.sh aerolib_o3  # une autre compilation, sous un autre nom
FC=ifx bash construire.sh aerolib /ailleurs             # autre compilateur, autre dossier
```

Les sources sont **un dossier** : `DOSSIER_SOURCES` (ici `../SOURCES`), dont
tout fichier `*.f *.F *.for *.f90 *.F90` est compilé (`MOTIFS`), et `INCLUDES`
la liste des dossiers des `INCLUDE`. Ajouter un fichier au dossier suffit ; n'y
laisser que le code livré.

C'est un script bash de quelques lignes : un appel à `python -m numpy.f2py -c`,
dans un dossier temporaire, avec `FC` et `FFLAGS`. Aucun backend n'est imposé
(`--backend meson` échouait là où meson manque) : f2py prend **distutils** tant
que `numpy.distutils` existe (Python < 3.12), **meson** sinon, et
il faut alors `pip install meson ninja`. Avec distutils, `FFLAGS` passe par
`--opt` (en variable d'environnement, numpy.distutils remplacerait aussi
`-fPIC`) ; avec meson, par la variable `FFLAGS`. L'interpréteur est
`CFD_VALIDATION_PYTHON` (`python3` par défaut) ; son dossier passe en tête du
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

### Journal de compilation

Chaque compilation écrit `<NOM>.compilation.log` à côté du module, **aussi en
cas d'échec** (le chemin est rappelé à l'écran) :

```
# Compilation f2py de aerolib — réussie
## Machine          système, distribution, processeur, cœurs, mémoire, jeux SIMD,
                    ce que -march=native désigne (znver2…), travail SLURM s'il y en a un
## Compilateurs     FC (chemin, version, cible), FFLAGS, compilateur C de l'enveloppe
## Python et f2py   interpréteur, numpy, backend, meson/ninja, commande f2py
## Sources          SHA-256 de chaque source et de chaque INCLUDE
## Commandes réelles du compilateur Fortran
                    une ligne par source : les options effectivement passées
## Module           SHA-256 et taille du .so produit
## Sortie complète de f2py
```

La rubrique « commandes réelles » est la seule qui fasse foi : avec meson, le
`buildtype=release` ajoute `-O3` *avant* `FFLAGS` (`… -O3 -O2 …` : c'est le
dernier qui l'emporte, donc `-O2`). Le journal se joint à une preuve de
validation : il dit avec quoi le module validé a été construit, et les SHA-256
permettent de vérifier qu'on parle bien du même.

### Options de compilation pour aller plus vite

Mesuré sur ce modèle (un appel `aercal` depuis Python, Ryzen 7 4700U,
gfortran 13) :

| FFLAGS | µs / appel | validation |
|---|---|---|
| `-O0` | 2,0 | — |
| `-O2` (défaut) | 1,17 | 100 % |
| `-O3 -march=native` | 0,73 | 100 % (4/4, copie de production) |
| `-O3 -march=native -flto` | 0,74 | — |

Pistes, de la plus sûre à la plus risquée :

1. **`-O3 -march=native`** : le gain mesuré ci-dessus. Le binaire n'est valable
   que sur ce type de processeur (le journal dit lequel) ; pour un cluster
   hétérogène ou un module à livrer, viser un niveau x86-64 commun :
   `-O3 -march=x86-64-v3` (AVX2/FMA, tout x86 depuis ~2015) ou `-v2`.
2. **`-funroll-loops`**, **`-fno-semantic-interposition`** : petits gains
   possibles sur les boucles de recherche dans les tables (`CHERCH`) ; à
   mesurer, sans risque numérique.
3. **Optimisation guidée par profil** : compiler `-O3 -fprofile-generate`,
   lancer la validation (elle balaie tout le domaine), recompiler
   `-O3 -fprofile-use -fprofile-correction`. Les tests de validation servent
   alors de jeu d'entraînement.
4. **`-flto`** : n'apporte rien ici (le gain demanderait l'inlining de `CHERCH`
   et `INTE*D` dans `AERO`, d'un fichier à l'autre, et l'éditeur de liens de f2py
   ne reçoit pas l'option) ; à réessayer sur un code où les sous-programmes
   chauds sont dans des fichiers différents.
5. **`-ffast-math` / `-Ofast`** : réordonne les calculs, donc plus de
   bit-à-bit garanti (la référence de `04_INTEGRATION` en est l'exemple : jusqu'à
   64 ULP sur Cm). Avec gfortran < 13, il lie en plus `crtfastmath.o`, qui passe
   **tout le processus Python** en flush-to-zero : numpy et le reste en sont
   affectés. À réserver à une compilation sous un autre nom, comparée à la
   compilation de référence par la validation.

Au-delà des options : à 0,7 µs, l'appel Fortran ne pèse plus beaucoup devant
l'emballage Python de chaque ligne de DataFrame. Le gain suivant viendrait
d'une `ENTRY` qui prend des tableaux (`intent(in) MACH(N)`, boucle en Fortran)
plutôt que d'options supplémentaires.

Pour mettre au point plutôt que pour aller vite :
`FFLAGS="-O0 -g -fcheck=all -ffpe-trap=invalid,zero,overflow -finit-real=snan -Wall"`
(débordements de tableaux, NaN, variables non initialisées).

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
| `calcul_aero_elementaire` | les arguments de AERCAL, unités et conventions du Fortran (CDG en m, axes FRD, `ipropu` 0/1) ; ceux de AERINI et AERCFG (`xref … lref`, `biaicx`) facultatifs (`DEFAUTS`) | + `cx … cn`, `ierr`, sondes |
| `calcul_aero` | `ModeleAero.PARAMETRES` : CDG en mm en axes FLU (`xg_mm`, `yg_mm`, `zg_mm`), `propulsion` booléen ; `xref … lref`, `biaicx` facultatifs (`DEFAUTS`) | + les arguments élémentaires calculés, les sorties, et `etat`, `modele`, `version`, `bibliotheque` |

`calcul_aero` = `vers_elementaire` (conversions : unités, signes, valeurs par
défaut) → `calcul_aero_elementaire` → `completer_sorties` (tout ce qu'on veut
retrouver en plus dans le vecteur de sortie). Une colonne en convention Fortran
(`xg`, `ipropu`) mêlée aux paramètres standard est refusée : on passe par l'un
ou par l'autre. **La validation passe par `calcul_aero_elementaire`** : elle
teste le code, pas la surcouche.

**Init par défaut.** Les deux fonctions complètent les arguments des phases
d'init par `ModeleAero.DEFAUTS` (`completer_init`) : une colonne absente, ou
vide sur certaines lignes, prend le défaut ; une valeur donnée prime. Les
arguments de AERCAL restent obligatoires. `ModeleF2py.calcul_elementaire`, le
générique, n'a toujours aucune valeur par défaut : c'est la surcouche du code
qui les connaît. La validation donne les siennes explicitement.

**CSV.** Les trois fonctions prennent `csv=` : `modele.calcul_aero(df,
csv="resultats.csv")` rend le DataFrame **et** l'écrit (dossier créé au
besoin, `ecrire_csv`). Les réels sont écrits par `repr`, le plus court texte
qui redonne le même double (`0.8`) : relu exactement (`float_precision=
"round_trip"` avant pandas 3). Un index nommé (`set_index("cas")`) est gardé en
première colonne ; l'index 0, 1, 2… par défaut ne l'est pas.

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

Les sondes sont **facultatives** — un code pas encore sondé n'a pas de bloc —,
réglées par `sondes=` à la construction :

| `ModeleAero(…, sondes=)` | blocs de `SONDES` |
|---|---|
| `None` (défaut) | lus s'ils existent ; un absent est ignoré avec un avertissement (`modele.sondes_absentes`) |
| `True` | tous exigés : erreur s'il en manque un (c'est ce que fait la validation, `tables_modele.charger_modele`) |
| `False` | aucun lu, aucune colonne `valid_tab_*` |

Les sorties du code n'en dépendent pas. Pour un autre code sans sondes du tout,
`SONDES = ()` dans la sous-classe.

**`lire("bloc.variable")`** rend une copie d'une variable de COMMON (casse
indifférente), avec la forme et l'ordre d'indices du Fortran : `TCX(NM, NA)`
donne `(7, 7)`, `[i, j]` valant `TCX(I+1, J+1)`. C'est là que les tests de
table prennent leurs tables et leurs grilles : telles que le code les voit.

## 3. Points de vol depuis un fichier YAML

```bash
python calcul_yaml.py exemple_pdv.yaml                  # → SORTIE/exemple_pdv.csv (clé « sortie »)
python calcul_yaml.py mes_pdv.yaml --sortie res.csv     # ailleurs
```

```yaml
fonction: calcul_aero              # ou calcul_aero_elementaire (arguments Fortran tels quels)
sortie: SORTIE/exemple_pdv.csv     # relatif au YAML (défaut : <nom du YAML>.csv à côté)
sondes: false                      # true : sorties sondées valid_tab_* dans le CSV (défaut false)
commun: {beta: 0.0, xg_mm: 1050.0, yg_mm: 0.0, zg_mm: 0.0, propulsion: false, dm: 0.0, dn: 0.0}
pdv:
  - nom: balayage_alpha            # colonne « bloc » du CSV
    mach: [0.8, 1.2]               # liste
    alpha: {de: 0, a: 10, pas: 2}  # plage avec pas : 0, 2, …, 10 (bornes comprises)
  - nom: balayage_mach
    mach: {de: 0.4, a: 1.8, n: 8}  # plage en n points
    alpha: 5.0                     # scalaire
```

Chaque bloc est le **produit croisé** de ses clés, la dernière variant le plus
vite ; les blocs sont mis bout à bout ; `commun` complète chaque bloc, qui peut
le surcharger. Les noms de clés sont ceux de la fonction appelée. Les
arguments des phases d'init (`xref … lref`, `biaicx`) sont facultatifs **avec
les deux fonctions** : absents, ou absents d'un bloc seulement, ils prennent
`ModeleAero.DEFAUTS` sur ces lignes (`exemple_pdv_elementaire.yaml` : arguments
Fortran sans init, `lref` donné dans un seul bloc).

`sondes: true` ajoute les sorties sondées et **exige** le COMMON de sondes
(erreur, code 1, sur un code pas encore sondé) ; `sondes: false` (défaut) ne les
lit pas du tout, ce qui marche sur tout code. Toute autre valeur que
`true`/`false` est refusée. Une plage,
une fonction ou une clé de premier niveau mal écrites sont refusées avec leur
emplacement (`pdv[0].alpha : …`), code 1. Depuis `MODELE_AERO/` : `cmake --build
build -t pdv` (fichier : `-DPDV_YAML=…`).

## 4. Pour un autre code

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
