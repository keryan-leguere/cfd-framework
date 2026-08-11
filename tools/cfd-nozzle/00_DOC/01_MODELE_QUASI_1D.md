# 1. Le modèle quasi-1D

## Ce qu'on suppose (et ce que ça coûte)

Toute la théorie de ce package repose sur cinq hypothèses. Les connaître, c'est
savoir quand le résultat cesse d'être crédible.

| Hypothèse | Conséquence si elle tombe |
|---|---|
| Écoulement **stationnaire**, **adiabatique**, **non visqueux** (sauf à travers les chocs) | Pas de couche limite, donc pas de décollement : c'est la limite principale (voir [`03_REGIMES_ET_PERFORMANCES.md`](03_REGIMES_ET_PERFORMANCES.md)) |
| **Gaz calorifiquement parfait** : γ et R constants | Pas de chimie, pas de figeage. Pour un moteur-fusée, γ et R doivent venir d'un calcul d'équilibre (CEA, RPA) aux conditions de chambre |
| Grandeurs **uniformes sur chaque section droite** | A = A(x) seulement ; le profil de vitesse réel est ignoré |
| Variation de section **lente** (dA/dx petit) | Pas de composante radiale de vitesse ; faux près d'un col très serré ou d'un divergent très ouvert |
| Chocs internes traités comme des **chocs droits localisés** | La structure réelle (choc en λ, décollement) est hors modèle |

La méthode des caractéristiques ([`04_GEOMETRIES.md`](04_GEOMETRIES.md)) est la seule
partie du package qui soit réellement bidimensionnelle.

## Le modèle de gaz

`GasModel(gamma, r, name)` — tout le reste en découle :

```
cp = γ·R/(γ−1)          cv = R/(γ−1)          a = √(γ·R·T)
Γ(γ) = √γ · (2/(γ+1))^((γ+1)/(2(γ−1)))        V_limite = √(2·cp·T0)
```

`Γ(γ)` est la **fonction de Vandenkerckhove** : c'est la constante du débit
sonique, ṁ = Γ·p0·At/√(R·T0). `V_limite` est l'asymptote M → ∞ : aucune tuyère,
si longue soit-elle, ne dépasse cette vitesse.

`GAS_LIBRARY` fournit une dizaine de gaz. **Les entrées « propergol » sont des
ordres de grandeur**, utiles pour explorer, pas pour dimensionner un moteur de
vol.

```python
from cfd_nozzle import GAS_LIBRARY, GasModel

gaz = GAS_LIBRARY["lox_rp1"]              # γ = 1.22, R = 345
sur_mesure = GasModel.from_molar_mass(1.21, 22.4, "mon mélange")
```

## Les relations isentropiques

Elles ne dépendent que de M et de γ :

```
T0/T   = 1 + (γ−1)/2 · M²
p0/p   = (T0/T)^(γ/(γ−1))
ρ0/ρ   = (T0/T)^(1/(γ−1))
M*     = V/a* = √( (γ+1)M² / (2 + (γ−1)M²) )
```

`M*` reste **fini** quand M → ∞ (il tend vers √((γ+1)/(γ−1))), ce qui en fait la
variable naturelle de part et d'autre d'un choc.

## La relation de section : pourquoi une tuyère de Laval fonctionne

En intégrant la relation de Hugoniot on obtient

```
A/A* = (1/M) · [ (2/(γ+1)) · (1 + (γ−1)/2 · M²) ] ^ ((γ+1)/(2(γ−1)))
```

Cette fonction a un **minimum à M = 1**, où A/A* = 1. Deux conséquences qui
gouvernent tout le reste :

1. Un écoulement ne peut devenir supersonique **qu'au col** — d'où le
   convergent-divergent.
2. Pour un ε ≥ 1 donné, la relation admet **deux racines** : une subsonique et
   une supersonique. Laquelle se réalise dépend de la pression aval, pas de la
   géométrie. C'est l'origine des cinq régimes du chapitre 3.

![Relations isentropiques](FIGURES/01_relations_isentropiques.png)

C'est pourquoi `mach_from_area_ratio` exige une branche :

```python
from cfd_nozzle import area_ratio, mach_from_area_ratio

area_ratio(2.0)                                  # 1.6875
mach_from_area_ratio(1.6875, 1.4, "sub")         # 0.3722
mach_from_area_ratio(1.6875, 1.4, "sup")         # 2.0000
```

## Inversions

| Relation | Fonction | Méthode |
|---|---|---|
| p0/p → M | `mach_from_p0_over_p` | explicite (monotone) |
| T0/T → M | `mach_from_t0_over_t` | explicite |
| A/A* → M | `mach_from_area_ratio` | dichotomie guardée, une branche à choisir |
| ν → M | `mach_from_prandtl_meyer` | dichotomie |
| p02/p01 → M₁ | `mach_from_shock_p0_ratio` | dichotomie |

Les inversions numériques passent par `core.numerics.find_root`, une dichotomie
combinée à un pas de sécante — le candidat sécante n'étant accepté que dans les
80 % centraux de l'encadrement. Sans ce garde-fou, l'itération stagne sur les
relations très raides de la dynamique des gaz (A/A* quand M → 0, typiquement).
Aucune dépendance à SciPy.

## En pratique

```bash
cfd-nozzle iso --mach 2.5
cfd-nozzle iso --rapport-section 4.0 --branche sup
cfd-nozzle iso --p0-p 10.0 --gaz lox_rp1
```

```python
from cfd_nozzle import isentropic_state

etat = isentropic_state(2.5, 1.4)
etat.area_ratio, etat.p_over_p0, etat.nu_deg
```

Toutes les valeurs du package sont vérifiées contre les tables publiées
(Anderson, *Modern Compressible Flow*, annexes A–C) — voir
`tests/conftest.py`.
