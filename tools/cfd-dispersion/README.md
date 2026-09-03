# cfd-dispersion

Lois de dispersion, tirage Monte-Carlo, validation et polaires dispersées —
bâti sur [OpenTURNS](https://openturns.github.io/).

Vous décrivez vos coefficients par une table de lois. Le paquet en tire des
réalisations, vérifie que votre modèle a bien tiré ce que vous lui demandiez, et
superpose la dispersion sur les polaires que le framework produit déjà.

![polaire dispersée](00_DOC/FIGURES/07_polaire_dispersee.png)

---

## Sommaire

- [Installation](#installation)
- [Prise en main](#prise-en-main)
- [Guide API](#guide-api)
  - [Conventions](#conventions)
  - [1. Les lois](#1-les-lois)
  - [2. La reconstruction](#2-la-reconstruction)
  - [3. Le tirage](#3-le-tirage)
  - [4. La propagation le long d'un balayage](#4-la-propagation-le-long-dun-balayage)
  - [5. La validation](#5-la-validation)
  - [6. Les figures](#6-les-figures)
  - [7. La polaire dispersée](#7-la-polaire-dispersée)
  - [8. Greffe sur batch_plot](#8-greffe-sur-batch_plot)
  - [9. La ligne de commande](#9-la-ligne-de-commande)
  - [10. Gestion des erreurs](#10-gestion-des-erreurs)
  - [Référence de l'API publique](#référence-de-lapi-publique)
- [Limites du modèle](#limites-du-modèle)
- [Documentation](#documentation)
- [Structure](#structure)
- [Vérification](#vérification)

---

## Installation

```bash
cd tools/cfd-dispersion
pip install -e ".[dev]"
```

Python ≥ 3.9. Dépendances : `openturns`, `numpy`, `matplotlib`, `pandas`,
`rich`, `pyyaml`. Pas de SciPy.

Les figures gagnent le style maison quand [`cfd-plot`](../cfd-plot) est
installé, et retombent sur Matplotlib nu sinon :

```bash
pip install -e ../cfd-plot     # facultatif, sauf pour cfd_dispersion.batch
```

> **Calculateur isolé.** La roue OpenTURNS est marquée `cp39-abi3` /
> `manylinux_2_28` : elle s'installe donc sur RHEL 8 / Rocky 8 (glibc 2.28),
> mais elle pèse 63 Mo. Sur une machine sans réseau, il faut qu'elle soit déjà
> dans le cache de roues.

---

## Prise en main

```python
from cfd_dispersion import charger_lois, tirer, tirer_lot, valider_lot

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

lois = charger_lois(DICT_DISP_LAWS)

# 1. un tirage — c'est le DICT_DISP_DRAWN que votre modèle attend
tirage = tirer(lois, graine=42)
tirage["Cm_alpha"]["Biais"]
tirage.appliquer({"Cm_alpha": -2.5})

# 2. mille tirages, pour appeler le modèle en boucle
lot = tirer_lot(lois, 1000, graine=42, methode="lhs")

# 3. le modèle a-t-il tiré ce qu'on lui demandait ?
verdicts = valider_lot(resultats, lois, par=("Mach", "Altitude_m"))
```

En ligne de commande :

```bash
cfd-dispersion exemple /tmp/ex && bash /tmp/ex/RUN_EXEMPLE.sh
```

---

## Guide API

### Conventions

**`ET` est une demi-étendue, pas un écart-type.** Pour les familles gaussiennes,
`σ = ET/2`. Une table écrite en écarts-types et lue ici donne des dispersions
deux fois trop larges — ce qui reste parfaitement crédible à l'œil.
Voir [00_DOC/01](00_DOC/01_LOIS_DE_DISPERSION.md#11-et-nest-pas-un-écart-type).

**La reproductibilité est globale.** OpenTURNS n'a pas de générateur par appel :
il n'y a donc pas de `rng=` ici, mais un `graine=`. L'état antérieur du
générateur est restauré après chaque tirage, si bien qu'un `graine=` ne coûte
jamais la reproductibilité de l'appelant.

**Toutes les erreurs sont des `ValueError` nommant le coupable** — le
coefficient *et* la clé fautive, la série absente et celles qui sont présentes,
la colonne manquante et celles du tableau.

---

### 1. Les lois

```python
LoiDispersion(type_loi: int, M: float = 0.0, ET: float = 0.0)
charger_lois(table, *, correlation=None) -> JeuDeLois
charger_lois_yaml(chemin, *, correlation=None) -> JeuDeLois
```

| type | libellé | OpenTURNS | support | écart-type réel |
|:--:|:--|:--|:--|:--|
| 1 | Nulle | `Dirac(0)` | {0} | 0 |
| 2 | Constante | `Dirac(M)` | {M} | 0 |
| 3 | Uniforme | `Uniform(M−ET, M+ET)` | M ± ET | 0.577·ET |
| 4 | Gaussienne | `Normal(M, ET/2)` | non borné | ET/2 |
| 5 | Gaussienne ±3σ | `TruncatedNormal(M, ET/2, M±1.5·ET)` | M ± 1.5·ET | 0.4933·ET |
| 6 | Gaussienne ±2σ | `TruncatedNormal(M, ET/2, M±1.0·ET)` | M ± 1.0·ET | 0.4398·ET |

![les six familles](00_DOC/FIGURES/01_types_de_lois.png)

Une `LoiDispersion` porte `distribution`, `pdf`, `cdf`, `quantile`, `tirer`,
`support`, `plage_utile`, `M_theorique`, `ET_theorique`, `sigma_nominal`,
`est_degeneree`, `est_bornee`, `label`.

Noter `ET_theorique` (l'écart-type réel, calculé par OpenTURNS) face à
`sigma_nominal` (le paramètre `ET/2`). Pour les lois tronquées, les deux
diffèrent : la troncature resserre la loi, de 12 % au type 6.

---

### 2. La reconstruction

```python
CONVENTIONS          # "lineaire" (défaut) · "pourcentage" · "relatif"
convention(choix) -> Convention
Convention(nom, formule, appliquer)
```

| nom | relation | FE neutre |
|:--|:--|:--:|
| `lineaire` | `biais + FE · c` | 1 |
| `pourcentage` | `biais + (1 + FE/100) · c` | 0 |
| `relatif` | `biais + (1 + FE) · c` | 0 |

Chaque convention **porte sa formule en clair**, qui se retrouve imprimée dans
les boîtes de paramètres : une figure ne peut pas cacher sous quelle relation
elle a été produite.

---

### 3. Le tirage

```python
tirer(lois, *, graine=None, convention_=None, methode="mc") -> Tirage
tirer_lot(lois, n, *, graine=None, methode="mc") -> pd.DataFrame
```

`Tirage` est un `Mapping` : il se passe tel quel au modèle qui attend
`{coeff: {"Biais": …, "FE": …}}`, tout en portant `.appliquer`, la convention,
la graine et le plan employé.

`methode` vaut `"mc"`, `"lhs"` ou `"sobol"`. Le tirage passe par la loi
**jointe** de toutes les composantes : c'est la seule façon d'honorer une
corrélation déclarée, et la seule où LHS et Sobol apportent quelque chose.

---

### 4. La propagation le long d'un balayage

```python
bande_depuis_loi(x, nominal, *, loi, n=20000, intervalle="percentile",
                 couverture=None, k=None, correle=True, graine=None) -> BandeDispersion
bande_depuis_points(x, nominal, lois, ...) -> BandeDispersion
```

`BandeDispersion` porte `x`, `nominal`, `moyenne`, `bas`, `haut`,
`echantillons` (le nuage complet), `ecart_type`, `demi_largeur`, `label`,
`reduire()` et `enveloppe_sigma(k)`.

`correle=True` partage un même tirage sur tout le balayage — le cas d'une erreur
de recalage, et le cas physique usuel. Voir
[00_DOC/04 §4.6](00_DOC/04_POLAIRE_DISPERSEE.md#46-corrélé-ou-indépendant) :
l'enveloppe sort semblable dans les deux cas, mais seule l'enveloppe corrélée se
lit « la vraie courbe est là-dedans ».

---

### 5. La validation

```python
valider(echantillon, loi, *, alpha=0.05, tol_M=0.10, tol_ET=0.10, n_min=20) -> Verdict
valider_lot(df, lois, *, par=(), correction="sidak", ...) -> pd.DataFrame
```

Trois contrôles, dans cet ordre, parce qu'ils échouent pour des raisons
différentes et que le `motif` doit dire laquelle :

1. **support** — un point hors bornes est rédhibitoire. Attrape la loi tronquée
   tirée comme une gaussienne pleine, que Kolmogorov–Smirnov valide (p = 0.13).
2. **moments** — contre les valeurs exactes d'OpenTURNS, pas contre `ET/2`.
3. **Kolmogorov–Smirnov** — attrape ce que les moments laissent passer : une loi
   bimodale de mêmes moments et même support est rejetée à p ≈ 10⁻²³⁵.

Motifs : `effectif`, `support`, `moyenne`, `écart-type`, `forme`.

**`valider_lot` corrige la multiplicité.** Sur 12 points de vol × 4 composantes,
un tableau entièrement conforme sort intact 19 fois sur 20 avec la correction,
contre 3 fois sur 20 sans. Voir
[00_DOC/03 §3.3](00_DOC/03_VALIDATION_MONTE_CARLO.md#33-le-piège-de-la-multiplicité).

---

### 6. Les figures

| | |
|:--|:--|
| `figure_tirage` | trois panneaux : biais, FE, reconstruction |
| `figure_tirage_matrice` | une ligne de trois par coefficient |
| `figure_comparaison` | loi prescrite contre loi réalisée, avec verdict |
| `figures_par_pdv` | le générateur, une figure par (point de vol × coefficient) |
| `synthese`, `tableau_par_pdv` | les tableaux |
| `figure_synthese`, `table_rich` | le damier, en figure et au terminal |
| `pdv_rejetes` | les points de vol fautifs, à repasser à `figures_par_pdv` |

![comparaison rejetée](00_DOC/FIGURES/05_comparaison_rejete.png)

![la synthèse](00_DOC/FIGURES/06_synthese.png)

Le raccord entre les deux est l'essentiel : sur cinquante points de vol et six
composantes, on ne regarde pas trois cents figures.

```python
for cles, coefficient, figure in figures_par_pdv(
    resultats, lois, par=PAR, seulement=pdv_rejetes(verdicts)
):
    figure.savefig(...)
```

---

### 7. La polaire dispersée

```python
superposer_dispersion(ax, x, nominal, *, loi=None, tirages=None,
                      serie=None, couleur=None, remplissage="minmax",
                      sigmas=(1, 2, 3), etiquettes_sigma=True,
                      boite_parametres=True, max_tirages=200, ...) -> dict
courbes_par_tirage(df, *, x, y, par) -> (x, courbes)
```

`serie="CFD"` reprend la couleur de cette courbe-là : le remplissage en
transparence, la moyenne dispersée en plus sombre. À défaut, `couleur=` trace un
faisceau autonome.

![les trois remplissages](00_DOC/FIGURES/08_remplissages.png)

Les lignes ±kσ sont **étiquetées sur la courbe**, avec l'inclinaison calculée en
coordonnées d'affichage — donc juste sur un axe logarithmique comme sur des
échelles sans rapport. Elles sont posées en dernier, après tout artiste
susceptible de déplacer les limites.

---

### 8. Greffe sur `batch_plot`

```python
from cfd_dispersion.batch import hook_dispersion

batch_plot(..., on_before_save=hook_dispersion(lois, serie="CFD", tirages=tirages))
```

La courbe nominale n'est pas à redonner : le hook la lit sur les axes.

`HookDispersion` est une classe de niveau module, donc **sérialisable** :
`batch_plot` retombe silencieusement sur `n_jobs=1` quand son hook ne l'est pas,
et une fermeture capturant un `DataFrame` coûterait tous les cœurs de la machine
pour un avertissement noyé dans la sortie.

Ce module s'importe et s'exécute sans `cfd-plot` — c'est `batch_plot`, donc
l'appelant, qui l'exige. `hook_dispersion` le vérifie néanmoins et lève un
`ImportError` explicite, pour que l'échec tombe à la construction du hook et non
au milieu d'un lot de deux cents figures.

---

### 9. La ligne de commande

```bash
cfd-dispersion check   --lois LOIS.yaml
cfd-dispersion tirage  --lois LOIS.yaml -n 1000 --methode lhs --sortie lot.csv
cfd-dispersion valider --lois LOIS.yaml --donnees resultats.csv \
                       --par Mach Altitude_m --figures FIG/ --strict
cfd-dispersion exemple /tmp/ex
```

`--strict` sort en code 1 dès qu'un point de vol est rejeté, pour une chaîne
d'intégration. `--correction aucune` retrouve le seuil test par test.

Le script console de pip fige le chemin de l'interpréteur ; `python -m
cfd_dispersion.cli.main` est l'équivalent qui marche partout.

---

### 10. Gestion des erreurs

Toutes les erreurs sont des `ValueError` nommant le coupable :

```
coefficient 'Cm_alpha' : clé(s) manquante(s) ['Biais_ET']
corrélation portant sur 'inexistant', qui n'est ni un coefficient ni une composante…
aucune courbe intitulée 'EXP' sur ces axes ; libellés présents : ['CFD', 'Essai']
les tirages ne partagent pas la même abscisse ; les empiler donnerait un tableau…
```

En ligne de commande, elles ressortent en panneau encadré et non en trace
d'exécution : le public est un ingénieur qui disperse des coefficients, pas un
développeur Python qui débogue cet outil.

---

### Référence de l'API publique

| symbole | rôle |
|:--|:--|
| `LoiDispersion`, `LoiCoefficient`, `JeuDeLois` | les lois |
| `charger_lois`, `charger_lois_yaml`, `libelle_type` | la table |
| `LIBELLES_TYPE`, `TYPES_VALIDES`, `CLES_ATTENDUES`, `COMPOSANTES` | les constantes |
| `Convention`, `CONVENTIONS`, `CONVENTION_PAR_DEFAUT`, `convention` | la reconstruction |
| `Tirage`, `tirer`, `tirer_lot`, `graine_temporaire` | le tirage |
| `BandeDispersion`, `bande_depuis_loi`, `bande_depuis_points`, `INTERVALLES` | la propagation |
| `Verdict`, `valider`, `valider_lot`, `alpha_corrige` | la validation |
| `tracer_loi`, `figure_tirage`, `figure_tirage_matrice` | figures du tirage |
| `figure_comparaison`, `figures_par_pdv` | figures Monte-Carlo |
| `synthese`, `tableau_par_pdv`, `pdv_rejetes`, `figure_synthese`, `table_rich` | la synthèse |
| `superposer_dispersion`, `courbes_par_tirage` | la polaire dispersée |

---

## Limites du modèle

* **Six familles, pas davantage.** Ni log-normale, ni Weibull, ni loi tabulée.
  Le format d'entrée est celui d'une table de lois d'établissement, pas d'un
  langage de description de distributions.
* **Deux composantes par coefficient**, un biais et un facteur d'échelle. Une
  dispersion à trois termes demande une `Convention` maison.
* **La corrélation est gaussienne** (`ot.NormalCopula`) et porte sur les
  composantes. La corrélation de rang réalisée est légèrement inférieure au ρ
  demandé, la copule agissant sur les marginales uniformes sous-jacentes.
* **Rien sur la sensibilité.** « Quel coefficient pilote la dispersion ? » est
  une autre question ; OpenTURNS sait y répondre (`SobolIndicesAlgorithm`), ce
  paquet ne l'expose pas.
* **La validation juge un tirage, pas un modèle.** Elle dit si les
  *entrées* tirées suivent leurs lois, non si le modèle en fait quelque chose de
  juste.
* **`valider_lot` suppose les tests indépendants** pour sa correction de Šidák.
  Avec des composantes corrélées, la correction est légèrement conservatrice.

---

## Documentation

| | |
|:--|:--|
| [00_DOC/01](00_DOC/01_LOIS_DE_DISPERSION.md) | les six familles, la convention `M`/`ET`, les pièges OpenTURNS |
| [00_DOC/02](00_DOC/02_CONVENTIONS_ET_TIRAGE.md) | les trois relations, les plans MC/LHS/Sobol |
| [00_DOC/03](00_DOC/03_VALIDATION_MONTE_CARLO.md) | les trois contrôles, la multiplicité, la synthèse |
| [00_DOC/04](00_DOC/04_POLAIRE_DISPERSEE.md) | la superposition, corrélé/indépendant, `batch_plot` |

Régénérer les figures : `python 00_DOC/generer_figures.py`.

---

## Structure

```
cfd-dispersion/
├── 00_DOC/                        docs FR + FIGURES/ + generer_figures.py
├── README.md
├── pyproject.toml
├── src/cfd_dispersion/
│   ├── __init__.py, _compat.py, paths.py
│   ├── core/
│   │   ├── alea.py          graine globale d'OpenTURNS, conversion (n,1) -> (n,)
│   │   ├── loi.py           les six familles
│   │   ├── lois.py          la table {coeff: {Biais_*, FE_*}}, la corrélation
│   │   ├── convention.py    les relations de reconstruction
│   │   ├── tirage.py        tirer / tirer_lot
│   │   ├── bande.py         propagation le long d'un balayage
│   │   └── validation.py    support / moments / Kolmogorov–Smirnov
│   ├── report/              theme.py, console.py, _plotting_lib.py
│   ├── figures/             _base, tirage, monte_carlo, synthese, polaire
│   ├── batch.py             la greffe sur cfd_plot.batch_plot
│   ├── cli/main.py
│   └── 01_EXEMPLE/          livré comme donnée de paquet
└── tests/                   miroir de src/
```

---

## Vérification

```bash
pytest                                  # 455 tests
ruff check . && ruff format --check .
mypy src tests                          # strict
python 00_DOC/generer_figures.py
cfd-dispersion exemple /tmp/ex && bash /tmp/ex/RUN_EXEMPLE.sh
```

Le paquet doit aussi tenir debout **sans** cfd-plot :

```bash
python -m venv /tmp/seul && /tmp/seul/bin/pip install .
/tmp/seul/bin/python -c \
  "from cfd_dispersion.report._plotting_lib import HAS_PLOTTING; print(HAS_PLOTTING)"
```

Quelques invariants que la suite tient :

| invariant | où |
|:--|:--|
| les six familles reproduisent l'implémentation SciPy d'origine (moments et supports, 400 000 tirages) | `test_loi.py::TestPortageDepuisScipy` |
| `getSample` est aplati en `(n,)`, et le tableau rendu est modifiable | `test_loi.py::TestPiegesOpenTurns` |
| un `graine=` ne décale pas le flux global de l'appelant | `test_loi.py`, `test_tirage.py` |
| une erreur de facteur 2 sur `ET` est rejetée à n = 50 … 20 000, bornée ou non | `test_validation.py::TestErreurDeFacteurDeux` |
| chacun des cinq motifs attrape ce que les autres laissent passer | `test_validation.py::TestLesQuatreMotifs` |
| le taux de faux rejet vaut α, et la correction nettoie le tableau | `test_validation.py::TestCalibration` |
| le hook survit à `pickle`, donc à `n_jobs > 1` | `test_batch.py::TestSerialisation` |
| l'exemple livré tourne, et son défaut volontaire est détecté | `test_exemple.py` |
