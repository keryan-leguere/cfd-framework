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

## 2.4 La figure du tirage

![le tirage en trois panneaux](FIGURES/04_tirage_3_panneaux.png)

Trois panneaux par coefficient :

1. la loi théorique du **biais**, la valeur tirée, et les bornes du support ;
2. la même chose pour le **facteur d'échelle** ;
3. la **reconstruction** — le nominal, le dispersé, la formule employée et
   l'écart obtenu.

Le troisième est celui qui compte. Les deux premiers montrent que chaque
composante est bien tombée dans sa loi ; seul le troisième montre ce que cela
fait au coefficient, qui est la question posée.

```python
from cfd_dispersion import figure_tirage, figure_tirage_matrice

figure, axes = figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5)
figure, grille = figure_tirage_matrice(lois, tirage, nominaux={"Cm_alpha": -2.5, ...})
```
