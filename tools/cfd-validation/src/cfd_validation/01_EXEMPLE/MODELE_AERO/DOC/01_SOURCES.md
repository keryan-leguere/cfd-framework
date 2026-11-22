# Modèle aéro : les sources

Un modèle aérodynamique **factice** en Fortran 77, écrit comme les codes qu'on
reçoit vraiment : tables en dur, `COMMON`, `BLOCK DATA`, un sous-programme à
deux points d'entrée `ENTRY`. Il sert de banc d'essai à `cfd-validation` ; ses
valeurs n'ont aucune prétention physique au-delà des signes et des symétries.

## 1. Ce que fait le modèle

À partir d'un point de vol, il rend les six coefficients aérodynamiques au
centre de gravité.

Les constantes du calcul sont données une fois, à l'initialisation :

| Entrée de `AERINI`   | Sens                                            | Unité |
|----------------------|-------------------------------------------------|-------|
| `XREF, YREF, ZREF`   | point de référence des moments des tables, FRD  | m     |
| `LREF`               | longueur de référence des moments               | m     |

Puis, à chaque point :

| Entrée de `AERCAL` | Sens                                     | Unité |
|--------------|------------------------------------------|-------|
| `MACH`       | nombre de Mach                           | –     |
| `ALPHA`      | incidence                                | deg   |
| `BETA`       | dérapage                                 | deg   |
| `XG, YG, ZG` | centre de gravité, axes corps FRD        | m     |
| `IPROPU`     | propulsion : 0 éteinte, 1 allumée        | –     |
| `DM, DN`     | braquages des gouvernes, tangage et lacet | deg   |

| Sortie de `AERCAL` | Sens                                              |
|--------------------|---------------------------------------------------|
| `CX`               | force axiale (négative : traînée)                 |
| `CY`               | force latérale                                    |
| `CZ`               | force normale (négative : portance vers le haut)  |
| `CL`               | moment de roulis au CDG                           |
| `CM`               | moment de tangage au CDG                          |
| `CN`               | moment de lacet au CDG                            |
| `IERR`             | code de retour (§ 6)                              |

Toutes les sorties sont **scalaires** : chacune devient une colonne nommée
côté Python (`PYTHON/README.md`).

Repère corps FRD : x vers l'avant, y vers la droite, z vers le bas. Les
moments sont adimensionnés par la longueur de référence `LREF` (0,2 m, le
diamètre, pour les tables livrées).

## 2. Les fichiers

```
SOURCES/
├── aero_dim.inc     dimensions (PARAMETER), COMMON /AERTAB/ et /AERTB5/ des tables
├── aero_probe.inc   COMMON /PROBE/ : les sondes de validation VALID_TAB_*
├── aero_tables.f    BLOCK DATA AERTBD : toutes les valeurs, en dur (généré)
├── aero_interp.f    CHERCH, INTE1D, INTE2D, INTE5D : recherche de maille, interpolation
└── aero_modele.f    SUBROUTINE AERO, ENTRY AERINI, ENTRY AERCAL ; fonction CROISS
```

Graphe d'appel :

```
AERINI ──► CROISS                       (contrôle des grilles)
AERCAL ──► INTE2D ──► CHERCH            (6 coefficients, 2 tables chacun en x/y)
       ├─► INTE1D ──► CHERCH            (propulsion, si IPROPU = 1)
       └─► INTE5D ──► CHERCH ×5         (gouvernes, en angles polaires)
              tables lues dans COMMON /AERTAB/ et /AERTB5/, remplies par BLOCK DATA AERTBD
              chaque valeur lue recopiée dans COMMON /PROBE/ (VALID_TAB_<TABLE>)
```

`aero_dim.inc` est la seule déclaration des tables : modèle et `BLOCK DATA`
l'incluent tous deux, si bien que le `COMMON` ne peut pas diverger d'une unité
à l'autre.

## 3. Deux phases, un seul sous-programme

```fortran
      CALL AERINI(XREF, YREF, ZREF, LREF, IERR)            ! une fois
      CALL AERCAL(MACH, ALPHA, BETA, XG, YG, ZG, IPROPU, DM, DN,   ! à chaque point
     &            CX, CY, CZ, CL, CM, CN, IERR)
```

`AERINI` et `AERCAL` sont deux `ENTRY` de `SUBROUTINE AERO`. Ils partagent les
variables locales de `AERO`, et ce qui est en `SAVE` survit d'un appel à
l'autre : c'est ce qui lie les phases.

- **Initialisation (`AERINI`)** : reçoit les constantes du calcul (point de
  référence des moments, `LREF`), vérifie que les quatre grilles sont
  strictement croissantes (`CROISS`) et que `LREF > 0`, garde les constantes en
  `SAVE` (`SXREF`, `SYREF`, `SZREF`, `ULREF = 1/LREF`), puis lève le drapeau
  `INIT`. Un second appel remplace les constantes : c'est ce qui permet de les
  changer sans toucher aux sources ni recompiler.
- **Calcul (`AERCAL`)** : refuse de calculer si `INIT` est faux (`IERR = 1`),
  ou si `IPROPU` n'est ni 0 ni 1 (`IERR = 3`) — les six sorties valent alors 0.
  Sinon, dans l'ordre :
  1. interpolation des six coefficients au point de référence ;
  2. ajout de l'incrément propulsif à `CX` si `IPROPU = 1` ;
  3. angles polaires (alphaT, phiA) depuis (α, β), lecture de la table des
     gouvernes et ajout de son incrément à `CM` ;
  4. transport des moments au CDG (§ 5).

  Chaque valeur lue dans une table est recopiée dans sa sonde (§ 8) **avant**
  les étapes qui la transforment.

  `AERCAL` n'a pas de mémoire : deux appels identiques rendent la même chose,
  quoi qu'on ait calculé entre les deux.

L'appel direct `CALL AERO` n'a pas d'objet et l'écrit.

`EXTERNAL AERTBD` dans `AERO` n'est pas décoratif : quand le modèle est pris
dans une bibliothèque statique (`libaero.a`), l'éditeur de liens n'extrait un
`BLOCK DATA` que si quelque chose le référence. Sans cette ligne, les tables
restent à zéro, sans erreur ni avertissement.

## 4. Les tables

Toutes **carrées**, 7 × 7, coefficients au point de référence des moments.
Les tables livrées ont été établies en `(1,2 ; 0 ; 0) m` avec `LREF = 0,2 m` :
ce sont les valeurs par défaut de `ModeleAero` côté Python, pas des
constantes du Fortran.

| Table | Dépend de      | Grille 2           |
|-------|----------------|--------------------|
| `TCX` | Mach, α        | `TALPHA`           |
| `TCZ` | Mach, α        | `TALPHA`           |
| `TCM` | Mach, α        | `TALPHA`           |
| `TCY` | Mach, β        | `TBETA`            |
| `TCL` | Mach, β        | `TBETA`            |
| `TCN` | Mach, β        | `TBETA`            |
| `TDCXP` | Mach seul    | grille `TMACHP` propre |
| `TDCMG` | Mach, alphaT, phiA, DM, DN | 5D, 5 × 5 × 5 × 5 × 5 |

| Grille   | Valeurs                                       |
|----------|-----------------------------------------------|
| `TMACH`  | 0,3 0,6 0,8 0,95 1,1 1,5 2,0                  |
| `TALPHA` | −20 −10 −5 0 5 10 20 (deg)                    |
| `TBETA`  | −10 −5 −2 0 2 5 10 (deg)                      |
| `TMACHP` | 0,4 0,6 0,8 1,0 1,2 1,5 1,8                   |
| `TMACHG` | 0,3 0,6 1,0 1,5 2,0                           |
| `TALFT`  | 0 5 10 15 20 (deg), incidence totale          |
| `TPHIA`  | −180 −90 0 90 180 (deg), azimut aérodynamique |
| `TDMG`, `TDNG` | −20 −10 0 10 20 (deg)                   |

La grille propulsive est **plus étroite** que la grille aéro, exprès : entre
Mach 0,3 et 0,4, le point est dans les tables aéro mais hors de la table
propulsive, et le diagnostic `IERR = 2` dépend alors de `IPROPU`.

Rangement mémoire : `TCX(I,J)`, `I` sur Mach, `J` sur α — l'ordre Fortran, un
`DATA` par colonne d'α dans `aero_tables.f`. Pour la table 5D, un `DATA` par
tranche (phiA, DM, DN), soit 25 valeurs, Mach le plus rapide.

**Table des gouvernes, en angles polaires.** Elle n'est pas tabulée sur les
entrées du modèle mais sur l'incidence totale et l'azimut, que `AERCAL`
calcule :

```
cos(alphaT) = cos(α)·cos(β)            phiA = atan2(sin β, sin α·cos β)
```

À alphaT = 0, phiA n'est pas défini (atan2(0, 0) rend 0) : la table y est donc
**indépendante de phiA**, par construction (tout terme en phiA est multiplié
par sin alphaT). Une table qui ne le serait pas donnerait, à incidence nulle, un
incrément qui dépend d'un angle que le code ne voit pas.

Les valeurs viennent de formules simples (bosse transsonique centrée sur
Mach 1, termes en sin α et sin α·|sin α|, coefficients latéraux impairs en β),
arrondies à 4 décimales. `aero_tables.f` est **généré** par
`OUTILS/generer_tables.py` et versionné : c'est lui qui fait foi pour le
code. `python OUTILS/generer_tables.py --verifier` échoue si le fichier ne
correspond plus au script.

## 5. Interpolation et transport

**Interpolation** (`aero_interp.f`). `CHERCH` trouve la maille `[XT(I),
XT(I+1)]` qui contient `X` et le poids `T ∈ [0, 1]` (hors grille : voir plus bas). `INTE2D` est bilinéaire :

```
V = (1−T)(1−U)·V(I,J) + T(1−U)·V(I+1,J) + (1−T)U·V(I,J+1) + TU·V(I+1,J+1)
```

Écrite ainsi (et non `V(I) + T·(V(I+1) − V(I))`), elle rend **au bit près** la
valeur de la table sur un nœud, aux deux bords compris : les poids valent
exactement 0 ou 1. On peut donc exiger l'égalité exacte entre une sortie
calculée sur un nœud et la table (lisible depuis Python : `aerolib.aertab.tcx`).

**Hors des grilles**, chaque axe suit sa **consigne**, passée à `CHERCH` par
`INTE1D` / `INTE2D` / `INTE5D` (constantes `ISATU`, `IEXTR` de `aero_dim.inc`) :

- `ISATU` : saturation — `T` borné à 0 ou 1, la valeur au bord de la grille ;
- `IEXTR` : extrapolation linéaire — `T` laissé hors de [0, 1], la dernière
  maille prolongée par la même formule `(1−T)·V(I) + T·V(I+1)`.

| Axe                         | Consigne                                         |
|-----------------------------|--------------------------------------------------|
| Mach (toutes les tables)    | saturation                                       |
| α (CX, CZ, CM), β (CY, CL, CN) | extrapolation linéaire                        |
| alphaT (gouvernes)          | extrapolation au-delà de 20° ; jamais sous 0 (acos) |
| phiA (gouvernes)            | saturation, jamais atteinte (atan2 ∈ [−180, 180]) |
| DM, DN (gouvernes)          | saturation                                       |
| Mach de la propulsion       | saturation                                       |

Dans les deux cas `IERR = 2` : les coefficients sont calculés, c'est à
l'appelant de décider s'il les garde. Ces consignes sont celles que vérifie le
test des bornes (`VALIDATION/02_BORNES_TABLES/`), déclarées dans
`VALIDATION/tables_modele.py`.

**Transport des moments** du point de référence R au CDG G :

```
M(G) = M(R) + (R − G) × F          r = (R − G) / LREF

Cl(G) = Cl(R) + ry·CZ − rz·CY
Cm(G) = Cm(R) + rz·CX − rx·CZ
Cn(G) = Cn(R) + rx·CY − ry·CX
```

Les forces ne dépendent pas du CDG. L'incrément propulsif est ajouté à `CX`
**avant** le transport : il entre dans `Cm` et `Cn` dès que `ZG` ou `YG` ne
sont pas nuls.

## 6. Codes de retour

| `IERR` | Phase    | Sens                                      | Sorties       |
|--------|----------|-------------------------------------------|---------------|
| 0      | les deux | nominal                                   | calculés      |
| 1      | `AERCAL` | appelé avant `AERINI`                     | 0             |
| 2      | `AERCAL` | point hors d'une table : saturé ou extrapolé selon l'axe | calculés |
| 3      | `AERCAL` | `IPROPU` ni 0 ni 1                        | 0             |
| 11     | `AERINI` | grille non strictement croissante         | –             |
| 12     | `AERINI` | `LREF ≤ 0`                                | –             |

## 7. Directives f2py

Après chaque `ENTRY`, deux lignes disent à f2py quels arguments sont des
entrées et lesquels des sorties :

```fortran
      ENTRY AERINI(XREF, YREF, ZREF, LREF, IERR)
Cf2py intent(in) XREF, YREF, ZREF, LREF
Cf2py intent(out) IERR
```

Elles commencent par `C` : pour un compilateur Fortran ce sont des
commentaires, le code reste compilable tel quel. f2py en tire une fonction
Python par point d'entrée, `ierr = aerini(xref, yref, zref, lref)` et
`cx, cy, cz, cl, cm, cn, ierr = aercal(mach, …, dm, dn)`, et expose chaque
`COMMON` comme un attribut : `aerolib.aertab`, `aerolib.aertb5`, `aerolib.probe`. La suite est dans
`PYTHON/README.md`.

Deux contraintes de f2py sur les sources : **ASCII pur** (un accent dans un
commentaire fait échouer la lecture — `construire.sh` le signale avant), et
des noms qui ne diffèrent pas que par la casse (f2py met tout en minuscules).

## 8. Sondes de validation

`aero_probe.inc` déclare un `COMMON /PROBE/` avec une variable par table :
`VALID_TAB_CX`, `VALID_TAB_CZ`, `VALID_TAB_CM`, `VALID_TAB_CY`, `VALID_TAB_CL`,
`VALID_TAB_CN`, `VALID_TAB_DCXP`, `VALID_TAB_DCMG`. `AERCAL` y recopie la
valeur interpolée **juste après** chaque lecture de table, avant que le code ne
la transforme :

```fortran
      CX = INTE2D(TMACH, NM, ISATU, TALPHA, NA, IEXTR, TCX, NM,
     &            MACH, ALPHA, IS)
      VALID_TAB_CX = CX
```

C'est ce que lit le test de lecture de table (`VALIDATION/01_LECTURE_TABLES/`,
`00_DOC/03_LECTURE_TABLES.md` de cfd-validation) : sur un nœud, la sonde doit
valoir la table. La sortie `CX`, elle, reçoit ensuite l'incrément propulsif,
et `CM` les gouvernes et le report des moments.

Une sonde n'est écrite que si sa table est lue : `VALID_TAB_DCXP` seulement
quand `IPROPU = 1`, et aucune quand `AERCAL` sort en erreur (`IERR` 1 ou 3).
Le Fortran ne la remet pas à zéro ; c'est l'appelant qui le fait avant chaque
appel (`ModeleF2py` la met à NaN), pour qu'une sonde non atteinte ne garde
pas la valeur de l'appel précédent.
