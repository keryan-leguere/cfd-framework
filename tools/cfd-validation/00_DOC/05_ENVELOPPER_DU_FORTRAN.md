# 5. Envelopper du Fortran

Ce que f2py fait d'un COMMON block, ce dont il a besoin pour compiler, et ce
qui change sur un calculateur isolé.

## Ce que f2py expose

Pour un source portant

```fortran
      DOUBLE PRECISION TAB_CN(320, 4)
      INTEGER NPT_CN
      COMMON /TAB_CN/ TAB_CN, NPT_CN
```

le module compilé offre :

```python
>>> import aero
>>> aero.tab_cn                 # le COMMON block
<fortran object>
>>> aero.tab_cn.tab_cn.shape    # le tableau, en vue NumPy Fortran-contiguë
(320, 4)
>>> aero.tab_cn.npt_cn          # l'entier, en tableau à zéro dimension
array(294, dtype=int32)
```

Quatre choses que rien ne laisse deviner, et que le paquet traite :

* **les noms sont en minuscules**, quelle que soit la casse du source ;
* **un COMMON block est un objet appelable**, du même type que les routines.
  Ce qui les sépare est ce qu'ils portent : un bloc porte des tableaux, une
  routine ne porte qu'elle-même. `blocs_exposes()` trie là-dessus ;
* **les tableaux sont Fortran-contigus** : la forme est celle du source, l'ordre
  mémoire est celui de Fortran. `np.asarray(…, dtype=float)` rend une vue
  utilisable sans copie ni transposition ;
* **un entier du bloc arrive en tableau à zéro dimension**, pas en `int`. La
  clé `lignes` en tient compte.

Un COMMON block se lit **et s'écrit** : `aero.tab_cn.npt_cn = 10` modifie la
mémoire du module. Le contrôle ne fait que lire, mais c'est la voie par laquelle
un test peut injecter une table de son choix.

## Compiler

```bash
cfd-validation toolchain                    # de quoi f2py dispose ici
cfd-validation construire aero.f            # écrit aero.cpython-*.so à côté
cfd-validation construire a.f b.f -m modele -o build/
```

Ou depuis Python :

```python
from cfd_validation import construire, charger_module

produit = construire("aero.f", nom_module="aero", destination="build")
aero = charger_module(produit)
```

`charger_module` importe **par chemin**, hors `sys.path` : deux compilations
d'un même modèle vivent alors côte à côte dans une session, ce qui est
exactement le cas d'une comparaison avant/après correctif.

### Le source doit être en ASCII

f2py lit le Fortran en ASCII et échoue sur le premier octet accentué — avec un
message qui parle de codec, jamais du fichier. Les commentaires en français
s'écrivent sans accents, ou le fichier se passe par `iconv`.

### Les directives `!f2py`

Elles disent à f2py ce qu'un source F77 ne dit pas :

```fortran
      SUBROUTINE EVAL_CN(MACH_IN, ALPHA_IN, DELTA_IN, NPTS, CN_OUT)
      INTEGER NPTS
      DOUBLE PRECISION MACH_IN(NPTS), ALPHA_IN(NPTS), DELTA_IN(NPTS)
      DOUBLE PRECISION CN_OUT(NPTS)
!f2py intent(in) :: MACH_IN, ALPHA_IN, DELTA_IN
!f2py intent(out) :: CN_OUT
!f2py integer intent(hide), depend(MACH_IN) :: NPTS = len(MACH_IN)
```

Le Python obtenu est `cn_out = aero.eval_cn(mach_in, alpha_in, delta_in)` :
`NPTS` a disparu de la signature, `CN_OUT` est devenu la valeur de retour.
`01_EXEMPLE/MODELE_FORTRAN/aero.f` en est un exemple complet.

## Ce dont f2py a besoin

`f2py -c` a changé de moteur, et c'est la source de la plupart des échecs :

| NumPy | moteur | ce qu'il faut |
|:--|:--|:--|
| ≤ 1.26 | `numpy.distutils` | `setuptools` — et un Python ≤ 3.11, `distutils` ayant quitté la bibliothèque standard |
| ≥ 2.0 | **meson** | `meson` et `ninja`, **sur le PATH** |

Aucun des deux n'est une dépendance de NumPy : `pip install numpy` donne un
f2py qui sait générer des sources et pas les compiler.

`cfd-validation toolchain` le dit avant la première tentative, et
`cfd-validation construire` refuse de tenter quand il manque quelque chose —
parce que ce que produit `f2py -c` sans meson est une trace de plusieurs
dizaines de lignes qui ne nomme jamais le remède.

### Le piège du PATH

f2py lance `meson` et `ninja` **par leur nom**, dans un sous-processus. Installés
dans un environnement virtuel non activé, ils sont là et introuvables à la fois,
et l'échec brut est :

```
FileNotFoundError: [Errno 2] No such file or directory: 'meson'
```

Le paquet reconnaît ce cas et le nomme :

```
meson, ninja sont installés dans /…/.venv/bin mais absent(s) du PATH —
activez l'environnement virtuel, ou export PATH="/…/.venv/bin:$PATH"
```

## Calculateur isolé

Le contrôle lui-même — lecture des tables, comparaison, diagnostic, rapport —
ne dépend que de `numpy`, `pandas`, `rich` et `pyyaml`. Il tourne partout où
le paquet s'installe, et tout se teste sans compilateur grâce au faux module
livré (`cfd_validation.wrap.factice`).

Trois choses à prévoir dans le cache de roues hors-ligne, si vous comptez
**compiler** sur site :

* `meson` et `ninja` (roues PyPI, pures Python et binaire ninja) ;
* `gfortran`, qui est un paquet **système** (`gcc-gfortran` sur RHEL/Rocky), pas
  une roue ;
* une version de NumPy cohérente avec le moteur : NumPy 2 + meson est la voie
  d'avenir, NumPy 1.26 + distutils ne marche plus au-delà de Python 3.11.

Si le site ne permet pas de compiler, compilez ailleurs sur une machine de
même ABI (même Python, même glibc, même architecture) et déposez le `.so` :
`charger_module` l'importe par chemin, sans installation.

## Ce que le paquet n'enveloppe pas

Le paquet lit des COMMON blocks et vous laisse appeler vos routines. Il ne
construit pas d'interface générique vers du Fortran, et ne remplace pas f2py :
`00_DOC/03_BRANCHER_SON_MODELE.md` dit ce qu'il attend de votre côté, et c'est
volontairement peu.

Un code C se traite de la même façon — f2py sait le compiler, et une variable
globale C se lit comme un COMMON block — mais l'exemple livré est en Fortran,
parce que c'est là que sont les tables.
