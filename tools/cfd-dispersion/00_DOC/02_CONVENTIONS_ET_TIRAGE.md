# 2. Conventions de reconstruction et tirage

## 2.1 Recombiner biais et facteur d'échelle

Le tirage rend deux nombres par coefficient. Il ne dit pas comment les
recombiner avec la valeur nominale — or la relation employée varie d'une équipe
et d'un dossier à l'autre, et deux d'entre elles diffèrent d'un facteur 100.

| nom | relation | FE neutre |
|:--|:--|:--:|
| `lineaire` *(défaut)* | `c_disp = biais + FE · c` | 1 |
| `pourcentage` | `c_disp = biais + (1 + FE/100) · c` | 0 |
| `relatif` | `c_disp = biais + (1 + FE) · c` | 0 |

![les trois conventions](FIGURES/03_conventions.png)

Rien dans une figure ne trahit qu'on s'est trompé de convention : la courbe
reste lisse et l'ordre de grandeur reste crédible. La relation est donc un objet
à part entière, qui **porte sa propre formule en clair** et se retrouve imprimée
dans chaque boîte de paramètres et chaque légende.

Une relation maison s'écrit directement :

```python
from cfd_dispersion import Convention

ma_convention = Convention(
    nom="tabulee",
    formule="biais + FE · c · (1 + c²)",
    appliquer=lambda c, biais, fe: biais + fe * c * (1 + c**2),
)
```

> Une `Convention` bâtie sur une `lambda` n'est pas sérialisable. Pour la passer
> au hook de `batch_plot` (voir [04](04_POLAIRE_DISPERSEE.md)), en faire une
> fonction de niveau module, ou s'en tenir aux noms livrés.

---

## 2.2 Tirer

```python
from cfd_dispersion import charger_lois, tirer, tirer_lot

lois = charger_lois(DICT_DISP_LAWS)

tirage = tirer(lois, graine=42)
tirage["Cm_alpha"]["Biais"]  # -> un flottant
tirage.appliquer({"Cm_alpha": -2.5})  # -> le coefficient dispersé

lot = tirer_lot(lois, 1000, graine=42, methode="lhs")  # -> DataFrame
```

`Tirage` est un `Mapping` : il se passe tel quel au modèle qui attend un
`DICT_DISP_DRAWN`, tout en portant la convention, la graine et le plan
d'échantillonnage — qui finissent dans les boîtes de paramètres des figures.

`appliquer` accepte un scalaire **ou tout un balayage**. Dans le second cas, le
même tirage s'applique en tout point : c'est le cas *corrélé*, celui d'une
erreur de recalage, et c'est le cas physique usuel.

---

## 2.3 Trois plans d'échantillonnage

| `methode` | ce que c'est | quand |
|:--|:--|:--|
| `"mc"` | Monte-Carlo brut | le défaut ; aucune hypothèse |
| `"lhs"` | hypercube latin | remplit mieux à effectif égal |
| `"sobol"` | suite à faible discrépance | convergence la plus régulière |

Le tirage passe par la loi **jointe** de toutes les composantes, et non par
chaque loi séparément. Deux raisons : une corrélation déclarée n'est honorée que
là, et les plans LHS et Sobol ne valent que sur l'ensemble des dimensions —
c'est précisément le remplissage conjoint qu'ils améliorent.

À 400 tirages, le plus gros trou laissé dans le support est mesurablement plus
petit en LHS qu'en Monte-Carlo ; c'est ce qu'un test vérifie.

---

## 2.4 La loi du coefficient dispersé

Les lois du biais et du facteur d'échelle sont connues. Mais la question posée
n'est pas « comment se répartit le biais » : c'est **comment se répartit le
coefficient**, une fois la relation appliquée.

```python
from cfd_dispersion import loi_combinee

combinee = loi_combinee(lois["Cm_alpha"], nominal=-2.5)
combinee.M_theorique, combinee.ET_theorique  # les moments du coefficient dispersé
combinee.pourcent(-2.58)  # -3.25 (%), None si le nominal est nul
combinee.exacte, combinee.methode  # True, "loi exacte (combinaison linéaire)"
```

Deux chemins, essayés dans cet ordre :

| | quand | comment |
|:--|:--|:--|
| **exact** | la relation est affine en (biais, FE) à nominal fixé | `ot.LinearCombinationDistribution` : loi exacte de `a·biais + b·FE + cst` |
| **lissé** | relation maison non affine | 20 000 tirages LHS, densité estimée par noyau (`ot.KernelSmoothing`) |

Les trois conventions livrées sont affines, et toute relation de la forme
`biais + f(c)·FE` l'est aussi — si tordue que soit `f`. La voie exacte couvre
donc presque tout, et vaut mieux qu'un histogramme : elle est juste jusque dans
les queues, là où une loi tronquée se distingue d'une gaussienne pleine.

L'affinité n'est pas **supposée**, elle est **mesurée** : la relation est
évaluée en trois points pour en extraire `(a, b, cst)`, puis en trois autres
pour vérifier qu'elle s'y superpose. Une relation non affine bascule donc sur le
lissage, au lieu de produire une loi « exacte » exactement fausse.

> Une loi combinée n'existe qu'**en un point**. Le facteur d'échelle multiplie
> le nominal : la dispersion absolue du coefficient change le long d'un
> balayage. Pour tout un balayage, c'est [04](04_POLAIRE_DISPERSEE.md) — une
> bande, pas une densité.

---

## 2.5 La figure du tirage

![le tirage en trois panneaux](FIGURES/04_tirage_3_panneaux.png)

Trois panneaux par coefficient :

1. la loi théorique du **biais**, la valeur tirée, et les bornes du support ;
2. la même chose pour le **facteur d'échelle** ;
3. la **loi du coefficient dispersé** — §2.4 — le nominal et la valeur tirée
   repérés, et l'écart en pourcentage.

Le troisième est celui qui compte. Les deux premiers montrent que chaque
composante est bien tombée dans sa loi ; seul le troisième montre ce que cela
fait au coefficient, qui est la question posée.

Chaque panneau porte ses lignes **±1/2/3 σ** (`cfd_plot.add_reference_lines`),
σ étant l'écart-type *exact* de la loi — celui d'une tronquée vaut moins que
`ET/2`, et la figure le montre. Le troisième porte en plus un axe supérieur
gradué en **pourcentage d'écart au nominal** : c'est ainsi qu'une dispersion se
lit et se raconte.

```python
from cfd_dispersion import figure_tirage, figure_tirage_matrice

# Tracer et écrire ne font qu'un appel : SVG, par le gabarit de cfd-plot.
rendue = figure_tirage(
    "Cm_alpha",
    lois["Cm_alpha"],
    tirage,
    nominal=-2.5,
    chemin=sortie / "tirage_Cm_alpha",  # -> tirage_Cm_alpha.svg
)
rendue.figure, rendue.axes, rendue.fichiers

# Quatre coefficients par figure au plus : au-delà, la matrice pagine et
# numérote les fichiers (tirage_01.svg, tirage_02.svg, …).
pages = figure_tirage_matrice(
    lois,
    tirage,
    nominaux={"Cm_alpha": -2.5, "CN": 0.85},
    chemin=sortie / "tirage",
)
```

Sans `chemin`, rien n'est écrit : `rendue.fichiers` est vide et la figure reste
à l'appelant.
