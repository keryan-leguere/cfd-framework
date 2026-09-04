# 3. Le tirage réalisé suit-il la loi demandée ?

On appelle le modèle mille fois par point de vol. Reste la question qui décide
de tout : **ce qui a été tiré correspond-il à ce qui a été prescrit ?**

---

## 3.1 Trois contrôles, dans cet ordre

Ils échouent pour des raisons différentes, et le motif doit dire laquelle.

### 1. Support

Un seul point hors des bornes de la loi est rédhibitoire.

C'est le contrôle qui attrape une loi tronquée tirée comme une gaussienne
pleine, et **aucun test de distance ne le ferait de façon fiable** : sur mille
points, la queue fautive en compte quelques dizaines. Mesuré sur ce cas précis,
le test de Kolmogorov–Smirnov rend p = 0.13 et validerait.

### 2. Moments

Moyenne et écart-type, contre les valeurs **exactes** d'OpenTURNS — pas contre
les paramètres. Une gaussienne tronquée est plus resserrée que la gaussienne
dont elle sort (×0.88 au type 6) : comparer à `ET/2` rejetterait des tirages
corrects.

Les écarts sont exprimés en grandeurs *pratiques* : `ecart_M` est un décalage de
moyenne en unités de σ, `ecart_ET` une erreur relative.

### 3. Kolmogorov–Smirnov

`ot.FittingTest.Kolmogorov` contre la fonction de répartition exacte, et non
contre un histogramme. C'est lui qui attrape ce que les moments laissent
passer : une loi bimodale de même moyenne, même écart-type et même support est
rejetée avec p ≈ 10⁻²³⁵.

Les lois dégénérées (types 1 et 2, et tout `ET = 0`) sautent ce test — il n'est
défini que pour des lois continues — et se vérifient à l'égalité.

---

## 3.2 Les tolérances et le bruit d'échantillonnage

Une tolérance pratique fixe se ferait piéger sur les petits effectifs, où le
bruit d'échantillonnage la dépasse. Le seuil appliqué est donc
`max(tolérance, marge de bruit)`, la marge valant quatre erreurs-types :
`4/√n` pour la moyenne (en unités de σ) et `4/√(2n)` pour l'écart-type.

Un tirage correct passe alors quel que soit *n*, et une erreur de facteur 2 sur
`ET` échoue quel que soit *n* — les deux sont vérifiés à n = 50, 200, 1000 et
20 000.

---

## 3.3 Le piège de la multiplicité

Le test de Kolmogorov–Smirnov rejette à tort dans α des cas : c'est sa
définition. Sur **un** tirage, 5 % est acceptable. Sur un tableau de cinquante
points de vol et quatre composantes, cela fait deux cents tests, donc une
dizaine de cases rouges de pur bruit — dans un livrable dont tout l'intérêt est
qu'on ne regarde *que* les cases rouges.

`valider_lot` sait combien de tests il lance et corrige le seuil pour tenir α
**sur l'ensemble du tableau** (Šidák par défaut : `α_test = 1 − (1−α)^(1/m)`).

Mesuré sur 20 études de 12 points de vol × 4 composantes, toutes conformes :

| | fausses alertes | études intactes |
|:--|--:|--:|
| sans correction | 58 / 960 | 3 / 20 |
| avec Šidák | 1 / 960 | 19 / 20 |

La correction ne coûte rien en détection réelle : une loi tirée de travers donne
une p-valeur si petite qu'aucun seuil raisonnable ne la sauve. C'est vérifié
dans les deux sens.

`valider` seul ne corrige rien — il ne sait pas combien d'autres tests
l'accompagnent. `correction=None` retrouve ce comportement.

---

## 3.4 Loi prescrite contre loi réalisée

```python
from cfd_dispersion import valider_lot
from cfd_dispersion.figures.monte_carlo import figures_par_pdv

verdicts = valider_lot(resultats, lois, par=("Mach", "Altitude_m"))
```

Un cas conforme :

![comparaison validée](FIGURES/05_comparaison_valide.png)

Le même coefficient avec un `ET` doublé :

![comparaison rejetée](FIGURES/05_comparaison_rejete.png)

Trois panneaux, comme au tirage, mais chaque loi théorique porte maintenant la
densité empirique du modèle (lissage à noyau `ot.KernelSmoothing`), plus la
boîte de verdict. On *voit* le FE réalisé déborder de son support prescrit.

Le troisième panneau confronte la loi **prescrite du coefficient dispersé** —
biais et FE combinés, [voir 02 §2.4](02_CONVENTIONS_ET_TIRAGE.md#24-la-loi-du-coefficient-dispersé) —
à l'histogramme réellement obtenu, sur un axe supérieur gradué en pourcentage
d'écart au nominal. C'est là que se lit ce qu'une erreur sur une composante
coûte à la grandeur livrée : ±15 % prescrits contre ±30 % obtenus.

`qq=True` remplace la densité empirique par un diagramme quantile-quantile : un
histogramme se lit bien au centre et mal dans les queues, or c'est dans les
queues qu'une loi tronquée dérape.

---

## 3.5 La synthèse

![la synthèse](FIGURES/06_synthese.png)

```python
from cfd_dispersion.figures.synthese import (
    figure_synthese,
    pdv_rejetes,
    synthese,
    table_rich,
    tableau_par_pdv,
)

synthese(verdicts)  # taux de validation et motifs, par composante
tableau_par_pdv(verdicts)  # le damier
table_rich(verdicts)  # la même chose au terminal
pdv_rejetes(verdicts)  # -> [{"Mach": 0.85, "Altitude_m": 10000.0}]
```

Le dernier appel est l'essentiel du cas d'usage. Son résultat se passe tel quel
à `figures_par_pdv(..., seulement=...)` : sur cinquante points de vol et six
composantes, on ne regarde pas trois cents figures — on regarde les quatre qui
ont échoué.

```python
for cles, coefficient, figure in figures_par_pdv(
    resultats, lois, par=PAR, seulement=pdv_rejetes(verdicts)
):
    figure.savefig(...)
```

---

## 3.6 Ce que porte un verdict

| champ | sens |
|:--|:--|
| `valide`, `motif` | le verdict, et le contrôle qui a échoué |
| `n` | effectif |
| `ks_D`, `ks_p` | statistique et p-valeur (`nan` si loi dégénérée) |
| `M_empirique`, `ET_empirique` | mesurés |
| `M_theorique`, `ET_theorique` | exacts, depuis OpenTURNS |
| `ecart_M` | décalage de moyenne, en unités de σ |
| `ecart_ET` | erreur relative sur l'écart-type |
| `hors_support` | nombre de points hors bornes |

Les motifs possibles : `effectif`, `support`, `moyenne`, `écart-type`, `forme`.
