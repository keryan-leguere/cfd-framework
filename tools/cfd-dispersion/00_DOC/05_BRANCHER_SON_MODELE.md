# 5. Brancher son propre modèle

Cette page est le mode d'emploi pratique : **quels dictionnaires fournir, quelle
fonction écrire, quelles colonnes rendre** pour que la validation, les figures et
la greffe sur `batch_plot` marchent sans rien adapter.

Tout tient en quatre objets, dans cet ordre :

```
DICT_DISP_LAWS            ->  JeuDeLois        ->  Tirage            ->  DataFrame
{coeff: {Biais_*, FE_*}}      charger_lois()       tirer()               votre modèle
la table d'établissement      les lois            DICT_DISP_DRAWN       une ligne par appel
```

Le seul que vous écrivez est le premier. Le dernier est le seul que **votre
modèle** doit produire, et son contrat tient en un tableau de noms de colonnes
(§5.4).

---

## 5.1 L'entrée : la table de lois

Un dictionnaire Python, ou le même en YAML. **Une entrée par coefficient, six
clés chacune** — pas cinq, pas sept, et les noms sont exacts :

```python
DICT_DISP_LAWS = {
    "CN": {
        "Biais_Type": 5,  # la famille du biais, entier 1..6
        "Biais_M": 0.0,  # sa moyenne
        "Biais_ET": 0.02,  # sa DEMI-ÉTENDUE (σ = ET/2), pas son écart-type
        "FE_Type": 6,  # idem pour le facteur d'échelle
        "FE_M": 1.0,  #   M = 1 avec la convention `lineaire` :
        "FE_ET": 0.08,  #   c'est le facteur neutre
    },
    "Cm_alpha": {...},
}

from cfd_dispersion import charger_lois, charger_lois_yaml

lois = charger_lois(DICT_DISP_LAWS)  # -> JeuDeLois
lois = charger_lois_yaml("LOIS.yaml")  # le même, depuis un fichier
```

| clé | type | sens |
|:--|:--|:--|
| `Biais_Type`, `FE_Type` | `int` 1 à 6 | la famille — voir [01](01_LOIS_DE_DISPERSION.md#12-les-six-familles) |
| `Biais_M`, `FE_M` | `float` | la moyenne, ou le centre |
| `Biais_ET`, `FE_ET` | `float` ≥ 0 | la **demi-étendue** |

Le YAML porte les mêmes clés sous une racine `lois:`, plus une racine
`correlation:` facultative :

```yaml
lois:
  CN:
    Biais_Type: 5
    Biais_M: 0.0
    Biais_ET: 0.02
    FE_Type: 6
    FE_M: 1.0
    FE_ET: 0.08
correlation:
  "CN, Cm_alpha": 0.6      # facultatif — corrèle biais↔biais et FE↔FE
```

Ce que `charger_lois` **refuse**, en nommant le coupable :

```python
charger_lois({"CN": {"Biais_Type": 5, "Biais_M": 0.0}})
# ValueError: coefficient 'CN' : clé(s) manquante(s) ['Biais_ET', 'FE_Type', 'FE_M', 'FE_ET']

charger_lois({"CN": {..., "Biais_Type": 9, ...}})
# ValueError: coefficient 'CN', Biais : type de loi inconnu : 9 ; attendu l'un de [1, 2, 3, 4, 5, 6]

charger_lois({"CN": {..., "FE_ET": -0.1, ...}})
# ValueError: coefficient 'CN', FE : ET est une demi-étendue et ne peut pas être négatif, reçu -0.1
```

Ce que `JeuDeLois` vous rend ensuite :

```python
lois["CN"]  # LoiCoefficient — .biais et .fe
lois["CN"].biais  # LoiDispersion — .pdf, .cdf, .tirer, .support, .M_theorique…
list(lois)  # ["CN", "CA", "Cm_alpha"]
lois.colonnes  # ("CN_Biais", "CN_FE", "CA_Biais", …) ← le contrat de §5.4
lois.composantes()  # ((coefficient, composante, loi), …)
lois.independantes  # False si une corrélation a été déclarée
```

---

## 5.2 Le tirage : ce que votre modèle reçoit

```python
from cfd_dispersion import tirer

tirage = tirer(lois, graine=42)
```

`Tirage` **est** un `Mapping` : c'est le `DICT_DISP_DRAWN` que votre modèle
attend, utilisable tel quel, sans conversion.

```python
tirage["CN"]["Biais"]  # -> float
tirage["CN"]["FE"]  # -> float
dict(tirage)  # -> {"CN": {"Biais": …, "FE": …}, …} si vous préférez un dict nu
```

Il porte en plus ce qu'un dictionnaire nu ne peut pas porter :

```python
tirage.appliquer({"CN": 0.85})  # -> {"CN": array(0.8307)} — applique la convention
tirage.appliquer({"CN": courbe})  # un balayage entier, même tirage en tout point
tirage.convention  # la relation employée
tirage.graine, tirage.methode  # ce qui a produit ce tirage
```

Pour appeler le modèle mille fois, ne bouclez pas sur `tirer` : `tirer_lot` rend
directement un tableau, et c'est le seul chemin qui honore un plan LHS ou Sobol.

```python
from cfd_dispersion import tirer_lot

lot = tirer_lot(lois, 1000, graine=42, methode="lhs")
# DataFrame, 1000 lignes × colonnes "CN_Biais", "CN_FE", "CA_Biais", …
```

---

## 5.3 Votre fonction modèle

Elle n'a rien à importer de ce paquet. Le contrat est celui de ses **entrées et
de sa sortie**, pas de sa signature — voici la forme habituelle :

```python
def mon_modele(points_de_vol, lois, coefficients, tirage):
    """Un appel du modèle, sous un tirage donné.

    points_de_vol : liste de dicts, p. ex. [{"Mach": 0.8, "Altitude_m": 8000}, …]
    lois          : la table (souvent inutile ici — le tirage est déjà fait)
    coefficients  : {coeff: valeur nominale}
    tirage        : {coeff: {"Biais": …, "FE": …}}   ← le Tirage, tel quel
    """
    ...
    return pd.DataFrame(lignes)
```

Et la boucle qui la pilote — c'est le squelette complet, à copier :

```python
import pandas as pd
from cfd_dispersion import charger_lois_yaml, convention, tirer

lois = charger_lois_yaml("LOIS.yaml")
relation = convention("lineaire")  # biais + FE · c
morceaux = []

for i in range(1000):
    tirage = tirer(lois, graine=1000 + i)  # une graine par appel

    for point in POINTS_DE_VOL:
        nominaux = mes_coefficients(point)  # {coeff: valeur}
        ligne = dict(point)  # Mach, Altitude_m, …
        ligne["tirage"] = i

        for coefficient, valeur in nominaux.items():
            biais = tirage[coefficient]["Biais"]
            fe = tirage[coefficient]["FE"]
            ligne[f"{coefficient}_Biais"] = biais  # ← §5.4
            ligne[f"{coefficient}_FE"] = fe  # ← §5.4
            ligne[coefficient] = relation(valeur, biais, fe)  # le dispersé

        morceaux.append(ligne)

resultats = pd.DataFrame(morceaux)
```

Deux points valent d'être notés :

* **une graine par appel, dérivée d'une graine d'étude.** `graine=None` tire
  au fil de l'eau et l'étude n'est plus reproductible ; une graine *constante*
  donne mille fois le même tirage, ce qui ne se voit qu'à la validation.
* **la convention est un objet, pas une multiplication écrite à la main.**
  `relation(valeur, biais, fe)` et la boîte de paramètres des figures diront la
  même chose, parce que c'est le même objet.

`modele.py`, dans [`01_EXEMPLE/`](../src/cfd_dispersion/01_EXEMPLE/modele.py), est
exactement ce squelette en un peu plus étoffé — un modèle jouet à remplacer par
le vôtre.

---

## 5.4 Le contrat de sortie : les colonnes

C'est **le** point d'accroche du paquet. `valider_lot`, `figures_par_pdv` et la
synthèse lisent tous le même tableau à plat, une ligne par (point de vol ×
tirage), avec ces colonnes :

| colonne | obligatoire | contenu |
|:--|:--:|:--|
| `<coefficient>_Biais` | **oui** | le biais tiré, tel qu'il a servi |
| `<coefficient>_FE` | **oui** | le facteur d'échelle tiré |
| `<coefficient>` | pour le 3ᵉ panneau | le coefficient dispersé obtenu |
| les clés de point de vol | si `par=` | `Mach`, `Altitude_m`, … |
| `tirage` | pratique | le numéro d'appel |

Les noms `"<coefficient>_Biais"` et `"<coefficient>_FE"` sont la convention par
défaut — celle que `tirer_lot` produit déjà, donc rien à faire si vous partez de
lui. `lois.colonnes` les énumère.

Si votre modèle nomme ses colonnes autrement, ne renommez pas le tableau :
donnez la correspondance.

```python
verdicts = valider_lot(
    resultats,
    lois,
    par=("Mach", "Altitude_m"),
    colonnes={
        ("CN", "Biais"): "bias_CN",  # {(coefficient, composante): colonne}
        ("CN", "FE"): "scale_CN",
    },
)
```

`figures_par_pdv` accepte le même argument `colonnes=`, avec le même sens.

Une colonne manquante est refusée tout de suite, et le message donne les deux
listes :

```
ValueError: colonne(s) absente(s) du tableau : ['CN_FE'] ;
            il porte ['CN', 'CN_Biais', 'Mach', 'Altitude_m', 'tirage']
```

À partir de là, tout s'enchaîne :

```python
from cfd_dispersion import valider_lot
from cfd_dispersion.figures.monte_carlo import figures_par_pdv
from cfd_dispersion.figures.synthese import figure_synthese, pdv_rejetes, table_rich

verdicts = valider_lot(resultats, lois, par=("Mach", "Altitude_m"))
print(table_rich(verdicts))  # le damier au terminal
figure, _ = figure_synthese(verdicts)  # le même en figure

for cles, coefficient, figure in figures_par_pdv(
    resultats, lois, par=("Mach", "Altitude_m"), seulement=pdv_rejetes(verdicts)
):
    ...  # seulement les cas fautifs
```

---

## 5.5 Le cas d'un balayage : une courbe par tirage

Pour une polaire, la sortie du modèle a une ligne de plus par point du
balayage : **(tirage × point)**. C'est la forme naturelle d'un tableau à plat, et
celle que `courbes_par_tirage` remet en matrice.

| `tirage` | `alpha` | `CN` | `CN_Biais` | `CN_FE` | `Mach` |
|--:|--:|--:|--:|--:|--:|
| 0 | 0.0 | 0.031 | 0.004 | 1.03 | 0.80 |
| 0 | 0.5 | 0.093 | 0.004 | 1.03 | 0.80 |
| … | | | | | |
| 1 | 0.0 | 0.028 | −0.002 | 0.97 | 0.80 |

```python
from cfd_dispersion import courbes_par_tirage

x, courbes = courbes_par_tirage(resultats, x="alpha", y="CN", par=["tirage"])
courbes.shape  # (n_tirages, n_points) — c'est ce qu'attend `tirages=`
```

`par=` nomme les colonnes qui **identifient un tirage**. Un numéro d'appel suffit
(`["tirage"]`) ; à défaut, les composantes tirées font l'affaire
(`["CN_Biais", "CN_FE"]`), puisqu'elles sont constantes le long d'une courbe.

La fonction **refuse** des tirages qui ne partagent pas la même abscisse : les
empiler donnerait une matrice dont les colonnes ne correspondent pas au même
point du balayage — une figure fausse, et lisse.

Ces courbes se superposent alors directement :

```python
from cfd_dispersion import superposer_dispersion

superposer_dispersion(
    ax,
    x,
    CN_nominal,
    loi=lois["CN"],  # la bande théorique
    tirages=courbes,  # les courbes réellement obtenues
    serie="CFD",  # reprendre la couleur de cette courbe-là
)
```

---

## 5.6 La greffe sur `batch_plot`

`batch_plot` (paquet [cfd-plot](../../cfd-plot)) prend **quatre dictionnaires** et
écrit tout un arbre de figures. La dispersion s'y ajoute par son unique point de
greffe, `on_before_save`.

### Les quatre dictionnaires, au complet

```python
configuration_dict = {
    # une entrée par source de données ; `df` est le DataFrame chargé,
    # le reste part en mots-clés de style vers plot_line.
    "CFD": {"name": "CFD", "label": "CFD", "df": donnees, "color": "C0", "marker": "o"},
}

y_axis_dict = {
    # une figure par entrée : les grandeurs tracées.
    "CN": {
        "col_name": "CN",  # la colonne dans `df`
        "literal_name": "Coefficient normal",  # le nom en toutes lettres
        "symbol": r"$C_N$",
        "unit": "-",
        "y_save_name": "CN",  # ce qui apparaît dans le nom de fichier
    },
}

sweep_dict = {
    # les variables qui peuvent aller en abscisse.
    "alpha": {
        "col_name": "alpha",
        "literal_name": "Incidence",
        "symbol": r"$\alpha$",
        "unit": "°",
        "x_save_name": "alpha",
        "polar_prefix": "ALPHA_POLAR",  # le niveau haut de l'arborescence
        "label": r"$\alpha$",
        "save_name": "ALPHA",  # quand ce balayage est figé dans le chemin
    },
}

flight_point_dict = {
    # les paramètres qui définissent un point de vol.
    "Mach": {"values": [0.80], "label": "M", "save_name": "M", "unit": "-"},
    "Altitude_m": {"values": [8000.0], "label": "Z", "save_name": "Z", "unit": "m"},
}
```

### Le hook

```python
from cfd_plot import batch_plot
from cfd_dispersion.batch import hook_dispersion

hook = hook_dispersion(
    lois,  # {coefficient: loi} — confronté à context.y_key
    serie="CFD",  # la courbe à disperser, par son libellé
    tirages=tirages,  # facultatif : les courbes obtenues (§5.7)
    n=6000,  # effectif de la bande théorique
    graine=1,
    max_tirages=150,
)

batch_plot(
    configuration_dict=configuration_dict,
    y_axis_dict=y_axis_dict,
    sweep_dict=sweep_dict,
    flight_point_dict=flight_point_dict,
    output_base="09_POST_TRAITEMENT/FIGURE",
    formats=("png",),
    on_before_save=hook,  # ← toute la greffe tient là
)
```

**La courbe nominale n'est pas à redonner.** Le hook va chercher sur les axes la
courbe intitulée `serie=`, en lit l'abscisse et l'ordonnée, et disperse
celles-là. Une divergence entre ce qui est tracé et ce qui est dispersé devient
impossible.

**Le nom de la grandeur doit correspondre au nom du coefficient.** Le hook
confronte `context.y_key` (la clé de `y_axis_dict`) aux clés de `lois`. Quand
les deux nomenclatures diffèrent, donner la correspondance plutôt que renommer
quoi que ce soit :

```python
hook_dispersion(lois, serie="CFD", coefficients={"CN_total": "CN"})
```

Une grandeur sans loi n'est pas une erreur : le hook passe son tour, et la
figure sort non décorée. C'est ce qui permet de tracer vingt grandeurs et d'en
disperser trois.

---

## 5.7 Le dictionnaire `tirages` et sa clé

`batch_plot` produit une figure par (grandeur × balayage × point de vol) ; le
hook, lui, reçoit un seul dictionnaire. Il faut donc une **clé** pour retrouver
les bonnes courbes, et c'est `cle_par_defaut` qui la donne :

```python
def cle_par_defaut(context):
    return (context.y_key, context.sweep_key)  # ("CN", "alpha")
```

D'où la construction du dictionnaire :

```python
from cfd_dispersion import courbes_par_tirage

tirages = {}
for coefficient in lois:
    _, courbes = courbes_par_tirage(a_plat, x="alpha", y=coefficient, par=["tirage"])
    tirages[(coefficient, "alpha")] = courbes  # (n_tirages, npts)
```

Une dispersion qui **change d'un point de vol à l'autre** demande une clé plus
fine — et donc votre propre fonction :

```python
def ma_cle(context):  # de niveau module : voir plus bas
    return (context.y_key, context.sweep_key, context.flight_point["Mach"])


hook_dispersion(lois, serie="CFD", tirages=tirages, cle=ma_cle)
```

`tirages` peut rester vide : la bande théorique suffit à décorer la figure. À
l'inverse, une clé absente n'est pas une erreur — cette figure-là n'aura que la
bande.

> **Tout ce que reçoit le hook doit être sérialisable.** `batch_plot` envoie son
> hook aux processus de travail et **retombe silencieusement sur `n_jobs=1`**,
> avec un simple `UserWarning`, quand il n'y parvient pas. D'où une classe de
> niveau module (`HookDispersion`) plutôt qu'une fermeture, une fonction de clé
> de niveau module plutôt qu'une `lambda`, et le **nom** d'une convention plutôt
> qu'une `Convention` bâtie sur une `lambda`.

---

## 5.8 Récapitulatif des formats

| ce que vous fournissez | forme exacte |
|:--|:--|
| la table de lois | `{coeff: {"Biais_Type", "Biais_M", "Biais_ET", "FE_Type", "FE_M", "FE_ET"}}` |
| ce que le modèle reçoit | `{coeff: {"Biais": float, "FE": float}}` — un `Tirage`, ou `dict(tirage)` |
| la sortie du modèle (points de vol) | `DataFrame`, une ligne par (point de vol × tirage) ; colonnes `<coeff>_Biais`, `<coeff>_FE`, `<coeff>`, plus les clés de point de vol |
| la sortie du modèle (balayage) | `DataFrame`, une ligne par (tirage × point) ; plus la colonne de balayage et un identifiant de tirage |
| `tirages=` du hook | `{(y_key, sweep_key): tableau (n_tirages, npts)}` |
| les figures `batch_plot` | les quatre dictionnaires de §5.6 |
