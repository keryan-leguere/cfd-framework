# 4. La polaire dispersée

Le livrable : la dispersion superposée sur les polaires que le framework produit
déjà.

![polaire dispersée](FIGURES/07_polaire_dispersee.png)

```python
from cfd_dispersion import superposer_dispersion

superposer_dispersion(
    ax,
    alpha,
    CN,
    loi=lois["CN"],  # la bande théorique
    tirages=courbes,  # les courbes réellement obtenues, (n, npts)
    serie="CFD",  # se rattacher à cette courbe-là
)
```

---

## 4.1 Se rattacher à une série

`serie="CFD"` va chercher la couleur de la courbe intitulée ainsi sur les axes :
le remplissage la reprend en transparence, la moyenne dispersée en **plus
sombre**. La dispersion se lit alors comme appartenant à cette série, sans
légende supplémentaire — ce qui compte dès qu'il y en a trois sur la figure.

À défaut, `couleur="C3"` trace un faisceau autonome.

---

## 4.2 Les courbes par tirage

Mille appels du modèle donnent un tableau à plat : une ligne par (tirage × point
du balayage). `courbes_par_tirage` le remet en forme.

```python
from cfd_dispersion import courbes_par_tirage

x, courbes = courbes_par_tirage(
    resultats,
    x="alpha",
    y="CN",
    par=["Cm_alpha_Biais", "Cm_alpha_FE"],
)
# -> courbes.shape == (n_tirages, npts)
```

`par` nomme les colonnes qui identifient un tirage — les composantes tirées, ou
un simple numéro. La fonction **refuse** des tirages qui ne partagent pas la
même abscisse : les empiler donnerait un tableau dont les colonnes ne
correspondraient pas au même point du balayage.

`max_tirages` plafonne le nombre de courbes réellement dessinées (200 par
défaut) : mille courbes opaques ne montrent rien de plus que deux cents, et
coûtent un fichier vectoriel dix fois plus lourd.

### En une ligne, depuis le tableau

Le regroupement, la courbe de référence et la superposition tiennent en un
appel — c'est l'entrée à préférer quand la polaire dispersée est déjà dans un
tableau à plat :

```python
from cfd_dispersion import superposer_depuis_tableau

figure, ax = nouvelle_figure()
tracer_ligne(ax, alpha, cn_reference, label="CN", color="C0")

superposer_depuis_tableau(
    ax,
    df_disperse,
    x="alpha",
    y="CN",
    reference=df_reference,  # le modèle, tirage neutre
    serie="CN",
)
```

`reference=` prend un `DataFrame` de même forme (une ligne par point du
balayage), ou un tableau de valeurs déjà aligné. **Omise**, la moyenne des
tirages en tient lieu : correct tant que les lois sont centrées, faux dès
qu'elles ne le sont pas — la bande se centre alors sur elle-même, et le biais
qu'on cherchait devient invisible.

Toutes les options de `superposer_dispersion` passent au travers.

---

## 4.3 Ce qui se trace, et ce qui se coupe

Tout ce que la superposition dessine est une option :

| option | ce qu'elle retire |
|:--|:--|
| `remplissage=None` | toute l'enveloppe |
| `remplir=False` | l'intérieur peint ; les deux bords restent |
| `bordures=False` | les deux bords ; le remplissage reste |
| `montrer_tirages=False` | le faisceau des courbes individuelles |
| `montrer_moyenne=False` | la moyenne dispersée |
| `sigmas=()` | les lignes ±kσ |
| `etiquettes_sigma=False` | leurs étiquettes |
| `boite_parametres=False` | la boîte de paramètres |
| `chiffres_legende=False` | le pourcentage en légende |

Les teintes en découlent, et elles ne sont pas décoratives — c'est leur ordre
qui fait la lisibilité :

* le **faisceau** est *éclairci* : cent courbes de la teinte de la série
  s'empileraient en un bloc plus sombre que les lignes qu'elles sont censées
  soutenir ;
* les **bords** de l'enveloppe sont légèrement assombris : à teinte égale, un
  bord ne se voit pas sur son propre remplissage ;
* les **±kσ** sont franchement plus sombres, et discontinus : ils passent *sur*
  le remplissage ;
* la **moyenne dispersée** est la ligne la plus marquée. C'est celle qu'on
  cherche.

Les étiquettes ±kσ sont enfin posées sur un cartouche **translucide** : opaque,
il percerait un trou blanc dans le faisceau qu'on venait regarder.

---

## 4.4 Remplissages

![les trois remplissages](FIGURES/08_remplissages.png)

| `remplissage` | ce que la bande recouvre |
|:--|:--|
| `"minmax"` *(défaut)* | tout le nuage, sans hypothèse |
| `"percentile"` | une fraction de couverture, queues écartées |
| `"sigma"` | moyenne ± kσ — suppose une forme |

Préférer les percentiles aux σ pour les composantes uniformes ou tronquées,
dont les queues ne sont pas gaussiennes.

---

## 4.5 Les lignes ±kσ, étiquetées sur la courbe

Matplotlib n'offre pas d'équivalent public de `clabel` en dehors des contours.
`etiqueter_ligne` le fait à la main : elle prend le point à une fraction donnée
de la courbe, calcule la pente locale **en coordonnées d'affichage**, et pose un
texte incliné dans un cartouche de la couleur du fond.

Deux conséquences, toutes deux voulues :

* l'inclinaison suit la pente **réellement tracée**, y compris sur un axe
  logarithmique ou avec des échelles x et y sans rapport — où l'angle en unités
  de données n'a aucun sens visuel ;
* les étiquettes doivent être posées **en dernier**, après tout artiste
  susceptible de déplacer les limites. `superposer_dispersion` s'en charge, et
  c'est la raison de son ordre de tracé.

Les positions par défaut (`0.55`, `0.72`, `0.89`) étalent les trois σ le long de
la courbe plutôt que de les grouper près du bord, et la branche basse est
décalée de 0.07 : à la même abscisse, `+kσ` et `−kσ` se chevauchent dès que la
bande est étroite — et une bande est étroite précisément là où elle est
intéressante.

---

## 4.6 La boîte de paramètres, et les chiffres

Elle nomme la loi effectivement tirée — type, M, ET, convention, effectif,
corrélé ou non, et le nombre de tirages du modèle. **Une figure ne doit jamais
pouvoir cacher quelle dispersion l'a produite.** `boite_parametres=False` la
retire.

Elle chiffre en plus l'enveloppe, parce qu'une bande se regarde mais se raconte
mal :

```
enveloppe max 0.278 (15.55 %) à x = 12
σ max 0.0678 (3.79 %)
écart moyen/nominal max +0.00491
```

Ces trois lignes sont celles de `resume_dispersion(bande)`, qui les rend sans
figure — pour un compte rendu. La bande, elle, se récupère dans
`artistes["objet_bande"]`, ou se fabrique depuis des courbes déjà obtenues :

```python
from cfd_dispersion import bande_depuis_courbes, resume_dispersion

bande = bande_depuis_courbes(x, nominal, courbes)  # sans rien retirer
resume_dispersion(bande).resume
```

L'étiquette du remplissage porte enfin le chiffre de tête — la hauteur maximale
de l'enveloppe en pourcentage du nominal — de sorte que la légende réponde déjà
à « de combien ? ». `chiffres_legende=False` l'enlève.

---

## 4.7 Corrélé ou indépendant

La distinction compte plus que le choix de l'intervalle, et se tromper dessus
est la façon classique de publier une mauvaise enveloppe.

Une erreur de recalage est normalement *la même erreur* en tout point du
balayage : une réalisation décale ou incline la courbe entière. C'est
`correle=True`, le défaut, et ses réalisations sont des courbes lisses.

Tirer une erreur indépendante par point — `correle=False` — modélise un bruit
point à point, un résidu mal convergé par exemple. Ses réalisations sont
hachées.

L'enveloppe sort semblable dans les deux cas ; ce qui change, c'est ce qu'il y a
dedans. **Seule l'enveloppe corrélée se lit « la vraie courbe est là-dedans »**,
qui est pourtant l'affirmation qu'on croit faire.

---

## 4.8 Greffe sur `cfd_plot.batch_plot`

```python
from cfd_dispersion.batch import hook_dispersion

batch_plot(
    ...,
    on_before_save=hook_dispersion(lois, serie="CFD", tirages=tirages, n=6000),
)
```

Le hook se branche sur `on_before_save`, le seul point de mutation de
`batch_plot`, appelé une fois les courbes, les libellés, la légende et le titre
posés et juste avant l'enregistrement. Tout ce qu'il dessine se retrouve dans le
SVG **et** dans la page du rapport PDF.

**La courbe nominale n'est pas à redonner** : elle est déjà sur les axes. Le hook
va chercher la série nommée, en lit l'abscisse et l'ordonnée, et disperse
celles-là. Une divergence entre les données tracées et les données dispersées
devient impossible.

### Pourquoi une classe et non une fermeture

`batch_plot` sérialise le hook pour l'envoyer à ses processus de travail, et
**retombe silencieusement sur `n_jobs=1`** — avec un simple `UserWarning` — quand
il n'y parvient pas. Une fermeture capturant un `DataFrame` coûterait tous les
cœurs de la machine sans rien dire de plus qu'un avertissement noyé dans la
sortie.

`HookDispersion` est une classe de niveau module dont tous les attributs sont
des données simples : elle est sérialisable, et un test le vérifie. Seule
réserve, une `Convention` maison bâtie sur une `lambda` ne l'est pas — passer
son nom, ou définir sa relation comme une fonction de niveau module.

### Et cfd-plot dans tout ça

Il est exigé deux fois : par `batch_plot` lui-même, et par le tracé de la
superposition — **toutes** les figures du paquet passent par cfd-plot, qui
définit le format du framework. Seul le calcul (lois, tirage, validation,
synthèse chiffrée) tourne sans lui.

`hook_dispersion` le vérifie à la construction du hook et lève un `ImportError`
nommant la commande d'installation, pour que l'échec survienne à la ligne où on
le construit et non au milieu d'un lot de deux cents figures.

### Les quatre dictionnaires de `batch_plot`

Ils sont écrits au complet, clé par clé, dans
[05 §5.9](05_BRANCHER_SON_MODELE.md#59-la-greffe-sur-batch_plot), avec la
construction du dictionnaire `tirages` et de sa clé. L'exemple livré
(`01_EXEMPLE/03_polaire_batch_plot.py`) est le même code, exécutable.
