# 1. Les lois de dispersion

Une loi de dispersion se décrit par **trois nombres** — ceux que porte votre
table :

| clé | sens |
|:--|:--|
| `Type` | la famille, entier de 1 à 6 |
| `M` | la moyenne, ou le centre |
| `ET` | la **demi-étendue** |

Chaque coefficient en porte deux : une pour son **biais** (additif) et une pour
son **facteur d'échelle** (multiplicatif).

```python
DICT_DISP_LAWS = {
    "Cm_alpha": {
        "Biais_Type": 5,
        "Biais_M": 0.0,
        "Biais_ET": 0.015,
        "FE_Type": 4,
        "FE_M": 1.0,
        "FE_ET": 0.10,
    },
}
```

---

## 1.1 `ET` n'est pas un écart-type

C'est l'erreur numéro un de ce modèle, et elle est invisible.

Pour les familles gaussiennes, **`σ = ET/2`**. `ET` est donc une demi-largeur à
2σ, et non un écart-type. Une table écrite en écarts-types et lue ici donne des
dispersions **deux fois trop larges** — ce qui reste parfaitement crédible à
l'œil sur n'importe quelle courbe.

![la convention ET](FIGURES/02_convention_ET.png)

À gauche, les deux densités : rien ne dit laquelle est la bonne. À droite, le
tirage fautif confronté à la loi demandée — 289 points sur 1000 tombent hors du
support prescrit, et
[la validation](03_VALIDATION_MONTE_CARLO.md) le dit sans ambiguïté.

C'est aussi pourquoi `LoiDispersion` distingue deux grandeurs :

* `sigma_nominal` — le **paramètre** `ET/2` passé à OpenTURNS ;
* `ET_theorique` — l'**écart-type réel** de la loi, calculé par OpenTURNS.

Pour les lois tronquées, les deux diffèrent : la troncature resserre la loi.

---

## 1.2 Les six familles

![les six familles](FIGURES/01_types_de_lois.png)

| type | libellé | distribution OpenTURNS | support | écart-type réel |
|:--:|:--|:--|:--|:--|
| 1 | Nulle | `Dirac(0)` | {0} | 0 |
| 2 | Constante | `Dirac(M)` | {M} | 0 |
| 3 | Uniforme | `Uniform(M−ET, M+ET)` | M ± ET | ET/√3 ≈ 0.577·ET |
| 4 | Gaussienne | `Normal(M, ET/2)` | non borné | ET/2 |
| 5 | Gaussienne ±3σ | `TruncatedNormal(M, ET/2, M±1.5·ET)` | M ± 1.5·ET | ≈ 0.4933·ET |
| 6 | Gaussienne ±2σ | `TruncatedNormal(M, ET/2, M±1.0·ET)` | M ± 1.0·ET | ≈ 0.4398·ET |

Les bornes des types 5 et 6 sont bien `M ± 3σ` et `M ± 2σ` — avec `σ = ET/2`,
cela fait `M ± 1.5·ET` et `M ± 1.0·ET`.

Noter la dernière colonne : au type 6, l'écart-type réel vaut **88 %** de
`ET/2`. Comparer un échantillon à `ET/2` plutôt qu'à cette valeur rejetterait
des tirages parfaitement corrects — c'est pourquoi la validation emploie les
moments exacts d'OpenTURNS.

### `ET = 0`

Les types 3 à 6 se réduisent alors à une masse en `M`. C'est traité
explicitement, et non laissé au hasard des refus d'OpenTURNS : celui-ci accepte
`Normal(M, 0)` mais refuse `Uniform(M, M)` et `TruncatedNormal(σ=0)`. Une seule
règle, le même comportement pour les quatre.

---

## 1.3 Deux pièges d'OpenTURNS

**`getRange()` n'est pas le support.** Sur une gaussienne non tronquée,
OpenTURNS rend un intervalle *fini* — environ `M ± 7.65 σ`. C'est une plage
numérique de travail, pas le support mathématique. `LoiDispersion.support()`
rend donc `(-inf, +inf)` pour le type 4 ; sans quoi une queue lointaine mais
légitime serait comptée « hors support ». Pour tracer, utiliser
`plage_utile()`, qui rend des bornes finies.

**`getSample(n)` rend du `(n, 1)`.** Un point par ligne, même en dimension 1.
Sans aplatissement, ce `(n, 1)` se diffuse contre un balayage `(npts,)` et
produit un `(n, npts)` d'apparence plausible et faux. Toutes les conversions du
paquet passent par un seul point — `core.alea.vers_numpy` —, qui aplatit **et**
recopie (une vue sur le tampon d'OpenTURNS arrive en lecture seule).

---

## 1.4 La reproductibilité est globale

OpenTURNS n'a pas de générateur par appel : il n'y a qu'un état global, piloté
par `ot.RandomGenerator.SetSeed / GetState / SetState`. Il n'y a donc pas de
paramètre `rng=` dans ce paquet, mais un `graine=`.

Toutes les fonctions de tirage passent par `core.alea.graine_temporaire`, qui
pose la graine puis **restitue l'état antérieur**. Un `graine=` reproductible ne
coûte ainsi jamais la reproductibilité de l'appelant.

```python
>>> import openturns as ot
>>> ot.RandomGenerator.SetSeed(123)
>>> avant = ot.Normal().getSample(3)
>>> ot.RandomGenerator.SetSeed(123)
>>> _ = LoiDispersion(4, 0.0, 1.0).tirer(1000, graine=999)
>>> apres = ot.Normal().getSample(3)     # identique à `avant`
```

---

## 1.5 Corrélation entre coefficients

Sans argument, les composantes sont **indépendantes**. C'est presque toujours ce
qu'on veut, et presque jamais ce qu'on a vérifié : deux coefficients issus du
même recalage partagent une erreur. L'hypothèse étant invisible sur une figure,
elle est rendue explicite — `JeuDeLois.independantes` est reportée dans chaque
boîte de paramètres.

```python
lois = charger_lois(DICT, correlation={("CN", "Cm_alpha"): 0.6})
```

Nommer deux **coefficients** corrèle leurs composantes de même nature : biais
avec biais, FE avec FE. Ce n'est pas une commodité — appliquer un même ρ aux
quatre croisements en laissant les couples internes à zéro produit, dès deux
coefficients, une matrice non définie positive qu'aucune loi jointe ne réalise.
C'est aussi la lecture physique : le recalage lie les biais entre eux, pas le
biais de l'un à l'échelle de l'autre.

Pour cibler une paire croisée, nommer explicitement les deux composantes :
`{("CN_Biais", "Cm_alpha_FE"): 0.4}`.
