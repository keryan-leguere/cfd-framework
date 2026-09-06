# Exemple cfd-dispersion — prêt à tourner

Tout est là : une table de lois, un modèle jouet, un exemple de tableau de
sortie, et neuf scripts qui
parcourent l'ensemble des fonctions du paquet.

```bash
bash RUN_EXEMPLE.sh          # les neuf, dans l'ordre — sorties dans SORTIE/
```

Ou, pour en copier un ailleurs et le triturer :

```bash
cfd-dispersion exemple /tmp/ex && cd /tmp/ex && bash RUN_EXEMPLE.sh
```

Chaque script s'exécute aussi seul, avec `--sortie` pour choisir où écrire :

```bash
python 02_monte_carlo.py --sortie /tmp/mc -n 2000 --tout-tracer
```

---

## Les fichiers

| fichier | rôle |
|:--|:--|
| `LOIS.yaml` | la **table de lois** : six clés par coefficient, la corrélation en option |
| `modele.py` | le **modèle jouet** — à remplacer par le vôtre ; c'est lui qui montre le contrat d'entrée/sortie |
| `01_tirage.py` | cas d'usage 1 : tirer, reconstruire, la loi du coefficient dispersé, tracer, le lot à donner au modèle, comparer les plans |
| `02_monte_carlo.py` | cas d'usage 2.1 et 2.2 : valider mille appels, synthétiser, ne tracer que les rejets |
| `03_polaire_batch_plot.py` | cas d'usage 2.3 : la dispersion greffée sur `cfd_plot.batch_plot` |
| `04_bande_et_correlation.py` | corrélé/indépendant, les trois remplissages, deux coefficients liés |
| `05_modele_croise.py` | **la forme d'un vrai modèle** : listes d'axes croisées, tableau large à colonnes dictionnaires |
| `sortie_modele.py` | **un exemple écrit en dur du tableau de sortie** : 4 points de vol × 100 tirages, les deux dictionnaires, les métadonnées — plus la base de référence, tirage neutre |
| `06_tirages_par_pdv.py` | le parcours des points de vol : une figure par (PDV × tirage × coefficient) |
| `07_histogrammes_par_pdv.py` | le même parcours, mais **tous les tirages d'un coup** : une figure d'histogrammes par (PDV × coefficient) |
| `08_polaire_depuis_tableau.py` | une **polaire dispersée** posée sur votre figure, à partir du tableau à plat |
| `09_batch_plot_dispersion.py` | le **lot entier de `batch_plot`** dispersé par un hook : le nominal dans la config, le dispersé dans `on_before_save` |

---

## Ce que chacun montre

### `01_tirage.py` — un tirage, et ce qu'il devient

Charge la table (dict Python **et** YAML), tire une réalisation, la reconstruit
sous les cinq conventions, calcule la **loi du coefficient dispersé**, écrit les
figures, tire un **lot** de mille, puis compare les trois plans
d'échantillonnage.

`tirer_lot` rend la **liste** des tirages : chaque élément est le
`DICT_DISP_DRAWN` que votre modèle attend, et il n'y a qu'à boucler dessus.
Le script ne fait tourner aucun modèle à cet endroit — il montre l'interface,
et ce qu'on lui passerait :

```python
for tirage in tirer_lot(lois, 1000, graine=42, methode="lhs"):
    resultats.append(mon_modele(L_MACH, L_ALPHA, tirage))
```

`tableau_des_tirages(lot)` remet ensuite le lot à plat, pour le CSV.

Les figures s'écrivent d'elles-mêmes : `figure_tirage(..., chemin=…)` trace
**et** enregistre, en SVG. `figure_tirage_matrice` pagine à quatre coefficients
par figure — forcée ici à deux, pour montrer la numérotation `_01`, `_02`.

À regarder :

* `tirage_matrice.svg` — le troisième panneau de chaque ligne porte la loi du
  coefficient dispersé, ses lignes ±1/2/3 σ, et un axe supérieur en pourcentage
  d'écart au nominal ;
* dans la sortie terminal, l'écart entre les conventions — `relatif` donne ici
  un coefficient **deux fois** le nominal, alors que `lineaire` le déplace de
  5 %. Rien sur une courbe ne trahirait l'erreur ;
* toujours au terminal, `saturee` (relation non affine) est la seule à sortir en
  `densité lissée (LHS n=20 000)` : les autres ont une loi exacte ;
* `tirage_sans_nominal.svg` — le même coefficient sans valeur nominale : les
  deux panneaux de composantes valent toujours, le troisième reste vide et dit
  ce qui lui manque plutôt que d'inventer un nominal.

### `02_monte_carlo.py` — le tirage réalisé suit-il la loi demandée ?

Appelle le modèle 800 fois sur quatre points de vol, valide, synthétise, et ne
trace que les points de vol rejetés.

**Le modèle fausse volontairement une composante** à M = 0.85 : la demi-étendue
y est prise pour un écart-type, donc doublée. C'est l'erreur numéro un du
modèle, elle est invisible à l'œil, et c'est exactement ce que la validation
doit rattraper. Un exemple où tout passe ne prouverait rien.

À regarder : `synthese.png` (le damier), puis
`qq_Mach0.85_Altitude_m10000_Cm_alpha.png` — le diagramme quantile-quantile du
FE s'écarte franchement de la diagonale, et la boîte dit `REJETÉ — écart-type`.

### `03_polaire_batch_plot.py` — le livrable

`cfd_plot.batch_plot` avec `on_before_save=hook_dispersion(...)`. Les quatre
dictionnaires y sont écrits au complet, clé par clé : c'est le morceau à venir
copier. Le rendu tourne sur deux processus, ce qui ne marche que parce que le
hook est sérialisable.

À regarder : `POLAIRES/ALPHA_POLAR/CN_vs_alpha.png` — bande théorique, courbes
par tirage, remplissage min/max, ±1σ/2σ/3σ étiquetés *sur* la courbe, et la
boîte nommant la loi employée.

### `04_bande_et_correlation.py` — les réglages qui changent le sens

Corrélé contre indépendant (l'enveloppe est la même, son contenu non), les trois
remplissages côte à côte, et deux coefficients issus du même recalage.

À regarder : `correle_vs_independant.png`. À gauche, chaque réalisation est une
courbe lisse — une erreur de recalage. À droite, un bruit point à point. Les
deux enveloppes se ressemblent ; **seule celle de gauche se lit « la vraie
courbe est là-dedans »**, qui est pourtant l'affirmation qu'on croit faire.

### `05_modele_croise.py` — la forme d'un vrai modèle

Celui-ci est l'exemple à copier si votre modèle reçoit des **listes d'axes**
(`L_MACH`, `L_ALTITUDE`, `L_ALPHA`), les croise lui-même, initialise une
bibliothèque Fortran, et rend **un seul tableau large** portant le point de vol,
les coefficients, ses métadonnées, et les deux dictionnaires
(`DICT_LAW_DISPERSION`, `DICT_TIRAGE`).

Tout le branchement tient alors en une ligne :

```python
resultats, lois = lire_sortie_modele(df)
```

À regarder : la sortie terminal, qui montre les colonnes ajoutées
(`CN_Biais`, `CN_FE`, …, `tirage`) et les lois relues **depuis le tableau** —
personne n'a redonné le YAML. Puis
`POLAIRES/ALPHA_POLAR/M_0.85/Cm_alpha_vs_alpha.png` : la bande réellement
obtenue y déborde des lignes ±3σ théoriques, parce que c'est le point de vol
faussé.

> **Le piège du croisement.** Un appel croisé applique le même tirage à tous les
> points du balayage : sur sept incidences, chaque valeur tirée apparaît sept
> fois. Valider tel quel multiplierait l'effectif par sept et rejetterait des
> tirages corrects. D'où `unique_par=("tirage",)` dans ce script — et le refus
> explicite de `valider_lot` si on l'oublie.

### `sortie_modele.py` — la forme d'une sortie, écrite en dur

Pas un modèle : la **forme** de sa sortie, à comparer à la vôtre. Quatre points
de vol, cent tirages, 400 lignes. Le lot est tiré une fois et rejoué à chaque
point de vol — le tirage n° 7 est le même partout, et y porte le même numéro.

`<coeff>` y porte le coefficient **dispersé** : il change à chaque ligne. La
valeur nominale, elle, vient d'un second tableau de même structure —
`sortie_modele_reference()`, le même modèle tourné une fois avec un tirage
neutre (`tirage_neutre`, `FE = 1` en convention linéaire).

À regarder : `SORTIE_MODELE.csv`, `SORTIE_MODELE_REFERENCE.csv`, et la liste des
colonnes qu'affiche le script.

### `06_tirages_par_pdv.py` — une figure par point de vol et par tirage

Un dict de points de vol — la forme du `flight_point_dict` de `batch_plot` — et
la fonction boucle : elle isole chaque point de vol, prend ses **quinze
premiers** tirages, et écrit pour chacun une figure par coefficient plus la
matrice qui les empile. Soit ici 4 × 15 × (3 + 1) = 240 fichiers, en une minute
sur tous les cœurs.

Le troisième panneau confronte en plus le coefficient **rendu par le modèle** à
celui que le paquet recalcule, et dit si les deux concordent : c'est le seul
contrôle qui porte sur le modèle lui-même.

À regarder :

* `TIRAGES/M_0.7/Z_0/tirage_000/matrice.svg` — le point de vol est rappelé dans
  le titre, un SVG se transmettant seul ;
* `INVENTAIRE_TIRAGES.csv`, qui dit ce qui a été écrit ligne par ligne, avec le
  verdict (`calcul`, `modele`, `ecart`, `accord`) ;
* `tirage_desaccord.svg` — **un désaccord volontaire de 1 %** : la boîte de
  paramètres passe au rouge et chiffre l'écart. C'est ce qu'on verrait si le
  modèle et le paquet n'appliquaient pas la même convention ;
* `ASYMETRIQUE/…` — le cas où **lois et sorties ne parlent pas des mêmes
  coefficients** : les lois dispersent un `CX0` interne au modèle, le tableau
  rend un `CA`. `CX0` garde ses deux premiers panneaux et un troisième qui dit
  ce qui lui manque ; `CA` n'est pas tracé, faute de tirage, et le demander est
  refusé en le nommant.

### `07_histogrammes_par_pdv.py` — ce que les cent tirages ont donné

Même tableau, même dict de points de vol, autre question. Le script 06 demande
« qu'est-ce qu'**un** tirage fait à mon coefficient » et rend 240 figures ; le
07 demande « qu'est-ce que les **cent** tirages ont donné » et en rend 16 : par
point de vol et par coefficient, l'histogramme du biais, celui du FE et celui du
coefficient, chacun superposé à la loi qui le prescrivait.

À regarder :

* `HISTOGRAMMES/M_0.85/Z_10000/CN.svg` — le troisième panneau confronte
  l'histogramme obtenu à la **loi combinée prescrite** : un modèle qui disperse
  plus que demandé se voit là, et nulle part ailleurs ;
* `HISTOGRAMMES_DECALES/CA.svg` — **la différence avec le script 06** : `CA`
  n'a aucune loi, mais on a bien cent valeurs obtenues, et leur histogramme est
  tracé. Le script 06 ne pouvait en montrer que le nominal et une valeur ;
* dans la sortie terminal, le refus d'un tableau **croisé** : trois incidences
  par tirage, et l'histogramme mélangerait le balayage et la dispersion.

### `08_polaire_depuis_tableau.py` — la dispersion sur votre polaire

Vous avez isolé une polaire dans un tableau à plat — une ligne par (tirage ×
incidence) — et vous tracez votre courbe de référence sur une figure cfd-plot.

**La figure est la vôtre** : le script la monte avec `cfd_plot` appelé
directement — `style_context`, `new_figure`, `plot_line`, `format_axis_label`,
`set_title`. cfd-dispersion n'ajoute qu'une ligne, sur des axes qui existent
déjà :

```python
superposer_depuis_tableau(ax, df_disperse, x="alpha", y="CN", reference=df_reference, serie="CN")
```

et elle ajoute les cent courbes en teinte claire, le faisceau min/max rempli,
les lignes ±1/2/3 σ étiquetées sur la courbe, et la boîte qui chiffre
l'enveloppe. La **courbe nominale reste au premier plan**, et la légende ne
gagne aucune entrée : celle de la série devient `CN (100 LHS · 17.3 %)`.

À regarder :

* `polaire_CN.svg` — la figure complète, sur un balayage qui va de −4 à 20°,
  décrochage compris : CN s'aplatit, CA suit sa polaire de traînée, Cm_alpha
  casse à 14°. Une enveloppe se juge là où la courbe se casse ;
* `polaire_options.svg` — **le catalogue** : une option par panneau, toujours la
  même figure avec un seul réglage changé. Le dernier est tracé **sans
  référence** : la moyenne des tirages tient lieu de nominal, et l'écart
  moyenne/nominal tombe à zéro — le biais devient invisible, ce qui est
  exactement le piège ;
* `polaire_enveloppes.svg` — min/max, percentile 95 %, ±2σ ;
* `transsonique.svg` — **un autre balayage** : en Mach, autour de la divergence
  de traînée. CA double en dix centièmes de Mach, CN perd sa portance au choc,
  Cm_alpha bascule. La dispersion relative n'a pas changé — les lois sont les
  mêmes — mais l'enveloppe s'ouvre en valeur absolue à mesure que le
  coefficient monte, et c'est ce qu'un dossier doit voir ;
* `transsonique_trois_alpha.svg` — **trois séries dispersées sur les mêmes
  axes**, dans trois couleurs de la palette « okabe_ito » de cfd-plot. Une
  entrée de légende par série, la boîte coupée, et seulement les ±3σ : sur une
  figure à trois faisceaux, la paire extérieure suffit et ne croise aucune
  courbe ;
* dans la sortie terminal, les chiffres sans figure : `resume_dispersion` réduit
  une bande à l'enveloppe maximale, son abscisse, le σ maximal et l'écart moyen.

### `09_batch_plot_dispersion.py` — le lot entier, dispersé

Le script 08 décore **une** figure que vous montez vous-même. Celui-ci décore
**tout un arbre** de figures que `cfd_plot.batch_plot` produit, sans en monter
aucune.

Le partage tient en deux lignes, et c'est tout l'intérêt :

```python
batch_plot(
    configuration_dict={"CFD": {"df": df_reference}},  # les COURBES (tirage neutre)
    on_before_save=hook_dispersion_tableau(df_disperse),  # la DISPERSION (n tirages)
    ...,
)
```

Aucune mise en forme préalable : pour chaque figure, le hook lit sur le
`context` le point de vol et la grandeur, découpe le tableau dispersé du **même
filtre** que `batch_plot` a appliqué à la référence, regroupe en une courbe par
tirage, et superpose.

Trois points de vol × trois coefficients = neuf figures par lot, et le script en
écrit quatre lots pour montrer les variantes. À regarder :

* `ORDINAIRE/…/CN_vs_alpha.png` — le rendu complet : faisceau, enveloppe
  min/max, ±1/2/3 σ, boîte de paramètres, et la légende qui porte l'effectif et
  la dispersion sur l'entrée de la série ;
* `SOBRE/…` — la lecture qui tient dans un dossier : `montrer_tirages=False`,
  `sigmas=()`, la seule enveloppe et son cerne. `bordures` n'est pas à régler,
  il suit les σ ;
* `PRESCRIT/…` — `lois=` ajoute la bande **prescrite** par-dessus le nuage
  **obtenu**. Un modèle qui disperse plus que demandé se voit là et nulle part
  ailleurs ;
* `COMPARAISON/…` — `batch_compare_flight_points` met les trois points de vol
  côte à côte : le hook est appelé une fois par panneau, chacun reçoit ses
  propres tirages ;
* dans la sortie terminal, le refus d'un tableau dispersé **amputé** d'un point
  de vol — l'alternative étant un lot entier de figures nues, qui se lisent
  comme un modèle sans dispersion.

---

## Le contrat, en deux tableaux

Ce que vous fournissez, dans `LOIS.yaml` ou dans un dict Python :

```python
{
    "CN": {
        "Biais_Type": 5,
        "Biais_M": 0.0,
        "Biais_ET": 0.02,
        "FE_Type": 6,
        "FE_M": 1.0,
        "FE_ET": 0.08,
    }
}
```

Ce que votre modèle doit rendre — un tableau à plat, une ligne par appel :

| colonne | contenu |
|:--|:--|
| `<coefficient>_Biais`, `<coefficient>_FE` | les composantes tirées, telles qu'elles ont servi |
| `<coefficient>` | le coefficient dispersé obtenu |
| `Mach`, `Altitude_m`, … | les clés de point de vol |
| `tirage` | le numéro d'appel |

Le détail complet — y compris quand vos colonnes portent d'autres noms — est
dans [`00_DOC/05_BRANCHER_SON_MODELE.md`](../../../00_DOC/05_BRANCHER_SON_MODELE.md).

---

## Sans cfd-plot

Les figures exigent [`cfd-plot`](../../../../cfd-plot) — c'est lui qui définit le
format. `03` l'exige de surcroît pour `batch_plot` lui-même.

```bash
pip install -e tools/cfd-plot
```

`RUN_EXEMPLE.sh` saute les étapes graphiques quand il n'est pas installé, et le
dit.
