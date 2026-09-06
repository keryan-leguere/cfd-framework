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
modèle** doit produire, et il est accepté sous deux formes (§5.4) :

* **à plat** — une colonne par composante tirée, `CN_Biais`, `CN_FE`, … ;
* **large** — le tableau porte les *dictionnaires* eux-mêmes, `DICT_TIRAGE` et
  `DICT_LAW_DISPERSION`, plus autant de métadonnées qu'on veut. C'est la forme
  d'un vrai modèle d'établissement, et `lire_sortie_modele` la traduit en une
  ligne.

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

Pour appeler le modèle mille fois, `tirer_lot` rend la **liste** des tirages —
et c'est le seul chemin qui honore un plan LHS ou Sobol.

```python
from cfd_dispersion import tableau_des_tirages, tirer_lot

lot = tirer_lot(lois, 1000, graine=42, methode="lhs")  # list[Tirage]

for tirage in lot:
    resultats.append(mon_modele(L_MACH, L_ALPHA, tirage))  # DICT_DISP_DRAWN

tableau_des_tirages(lot)
# DataFrame, 1000 lignes × colonnes "CN_Biais", "CN_FE", "CA_Biais", …
```

Une boucle `tirer(lois, graine=graine + i)` donne aussi *n* tirages
Monte-Carlo indépendants, et rien ne l'interdit ; mais aucun plan ne peut y
améliorer le remplissage, puisque chaque tirage ignore les autres.

---

## 5.3 Votre fonction modèle

Elle n'a rien à importer de ce paquet. Le contrat porte sur ses **entrées et sa
sortie**, pas sur sa signature.

### Le cas courant : des listes d'axes, croisées

C'est la forme d'un modèle d'établissement. Il reçoit des listes — `L_MACH`,
`L_ALTITUDE`, `L_ALPHA` —, il les croise lui-même, il initialise une
bibliothèque de calcul une fois pour toutes, il tire les dispersions, et il rend
**un seul tableau**.

```python
from cfd_dispersion import plan_croise, tirer


def mon_modele(L_MACH, L_ALTITUDE, L_ALPHA, DICT_LAW_DISPERSION, *, n_tirages=1000):
    """Un appel du modèle par tirage, sur tous les points croisés."""
    lois = charger_lois(DICT_LAW_DISPERSION)
    contexte = initialiser_bibliotheque_fortran()  # une fois, pas n fois
    points = plan_croise(Mach=L_MACH, Altitude_m=L_ALTITUDE, alpha=L_ALPHA)

    lignes = []
    for indice in range(n_tirages):
        tirage = tirer(lois, graine=1000 + indice)  # une graine par appel

        for point in points:
            coefficients = solveur(point, tirage, contexte)  # votre appel Fortran
            lignes.append(
                {
                    **point,  # Mach, Altitude_m, alpha
                    **coefficients,  # CN, CA, Cm_alpha, …
                    "version_solveur": contexte["version"],  # autant de métadonnées
                    "convergence": True,  #   que vous voulez
                    "DICT_LAW_DISPERSION": DICT_LAW_DISPERSION,
                    "DICT_TIRAGE": dict(tirage),
                }
            )

    return pd.DataFrame(lignes)
```

`plan_croise(**axes)` rend le produit cartésien sous forme de liste de
dictionnaires, dans l'ordre des axes donnés, le dernier variant le plus vite. Il
**refuse un axe vide** : le produit serait vide, et un plan vide ne se remarque
qu'au moment de tracer.

Trois choses valent d'être notées dans cette boucle.

* **Une graine par appel, dérivée d'une graine d'étude.** `graine=None` tire au
  fil de l'eau et l'étude n'est plus reproductible ; une graine *constante*
  donne mille fois le même tirage, ce qui ne se voit qu'à la validation.
* **Le tirage est partagé par tous les points croisés.** C'est le cas physique —
  une erreur de recalage est la même sur toute la polaire — et c'est ce qui
  impose de dédoublonner avant de valider (§5.7).
* **Le tableau porte ses propres lois.** `DICT_LAW_DISPERSION` dans une colonne
  n'est pas une redondance : c'est ce qui permet de relire le tableau dans six
  mois sans retrouver le YAML de l'époque, et ce qui interdit de le valider
  contre les lois d'une autre étude.

### La variante minimale

Si votre modèle ne croise rien et applique la convention lui-même, il peut
rendre directement les colonnes à plat, sans dictionnaires :

```python
for coefficient, valeur in nominaux.items():
    biais = tirage[coefficient]["Biais"]
    fe = tirage[coefficient]["FE"]
    ligne[f"{coefficient}_Biais"] = biais  # ← §5.4
    ligne[f"{coefficient}_FE"] = fe  # ← §5.4
    ligne[coefficient] = relation(valeur, biais, fe)  # le dispersé
```

`relation` vient de `convention("lineaire")` : la convention est un objet, pas
une multiplication écrite à la main, pour que la figure et le calcul disent la
même chose — c'est le même objet qui imprime sa formule dans la boîte de
paramètres.

`01_EXEMPLE/modele.py` porte les deux formes : `appeler_modele` pour la variante
minimale, `appeler_modele_croise` pour la forme complète.

---

## 5.4 Le contrat de sortie

Deux formes sont acceptées. Le reste du paquet — validation, figures, synthèse —
ne lit que la première ; la seconde s'y ramène en une ligne.

### Forme 1 — les colonnes à plat

Un tableau, une ligne par appel :

| colonne | obligatoire | contenu |
|:--|:--:|:--|
| `<coefficient>_Biais` | **oui** | le biais tiré, tel qu'il a servi |
| `<coefficient>_FE` | **oui** | le facteur d'échelle tiré |
| `<coefficient>` | pour le 3ᵉ panneau | le coefficient dispersé obtenu |
| les clés de point de vol | si `par=` | `Mach`, `Altitude_m`, … |
| `tirage` | pour dédoublonner (§5.7) | un identifiant de tirage |

C'est exactement ce que `tableau_des_tirages(lot)` produit ; `lois.colonnes`
énumère les noms attendus.

### Forme 2 — le tableau large, à colonnes dictionnaires

Le tableau porte les dictionnaires eux-mêmes, et autant de métadonnées qu'on
veut :

| colonne | contenu |
|:--|:--|
| `Mach`, `Altitude_m`, `alpha`, … | le point croisé |
| `CN`, `CA`, `Cm_alpha`, … | les coefficients rendus par le solveur |
| `version_solveur`, `convergence`, `temps_calcul_s`, … | vos métadonnées, en nombre libre |
| `DICT_LAW_DISPERSION` | la table de lois de l'étude |
| `DICT_TIRAGE` | le tirage appliqué à cette ligne |

Une seule ligne le traduit :

```python
from cfd_dispersion import lire_sortie_modele

resultats, lois = lire_sortie_modele(df)
```

Ce que la fonction fait, et qui vaut d'être su :

* elle **étale** `DICT_TIRAGE` en colonnes `<coeff>_Biais` / `<coeff>_FE` ;
* elle **numérote** les tirages **distincts** dans une colonne `tirage` — par
  contenu et non par ordre de ligne, donc le même tirage porte le même numéro à
  tous les points croisés. C'est lui qui sert à `unique_par=` et à
  `courbes_par_tirage` ;
* elle **relit** la table de lois depuis le tableau, et refuse d'aller plus loin
  si deux lignes ne décrivent pas la même — valider une étude contre deux tables
  n'a pas de sens ;
* elle **ne touche à rien d'autre** : les métadonnées voyagent intactes, le
  paquet ne lisant que les colonnes qu'il nomme. Elle rend une copie ; le
  tableau d'origine n'est jamais modifié.

Les noms de colonnes sont réglables, et les composantes sont reconnues à la
casse près (`Biais`, `biais`, `BIAIS`) :

```python
resultats, lois = lire_sortie_modele(df, tirage="draw", lois="laws", numero="n_tirage")
```

> **Un aller-retour par CSV ne casse rien.** Un `DataFrame` qui porte un
> dictionnaire par ligne le perd dès qu'il passe par un fichier : il en revient
> sous forme de chaîne, en JSON ou en `repr` Python selon l'écrivain. Les deux
> sont relus. C'est le cas d'usage normal — le modèle tourne sur le calculateur,
> l'analyse se fait ailleurs.

### Quand les colonnes portent d'autres noms

Ne renommez pas le tableau : donnez la correspondance.

```python
verdicts = valider_lot(
    resultats,
    lois,
    par=("Mach", "Altitude_m"),
    colonnes={("CN", "Biais"): "bias_CN", ("CN", "FE"): "scale_CN"},
)
```

`figures_par_pdv` accepte le même argument. Une colonne manquante est refusée
tout de suite, avec les deux listes :

```
ValueError: colonne(s) absente(s) du tableau : ['CN_FE'] ;
            il porte ['CN', 'CN_Biais', 'Mach', 'Altitude_m', 'tirage']
```

---

## 5.5 Un exemple de sortie, écrit en dur

Plutôt que de décrire ce tableau, le paquet en livre un :
`01_EXEMPLE/sortie_modele.py`. Il ne contient **pas de modèle** — seulement la
forme de sa sortie, écrite noir sur blanc, à comparer à la vôtre :

```
4 points de vol × 100 tirages = 400 lignes
```

Le lot est tiré **une fois** et rejoué à chaque point de vol : le tirage n° 7
est le même partout, et y porte le même numéro. C'est ce que fait un modèle
appelé en croisé, et c'est ce qui permet de dédoublonner ensuite (§5.7).

| famille | colonnes |
|:--|:--|
| point de vol | `Mach`, `Altitude_m` |
| métadonnées | `cas`, `maillage`, `solveur`, `version_modele`, `date`, `convergence` |
| coefficients dispersés | `CN`, `CA`, `Cm_alpha` |
| valeurs nominales | `CN_nominal`, `CA_nominal`, `Cm_alpha_nominal` |
| les deux dictionnaires | `DICT_LAW_DISPERSION`, `DICT_TIRAGE` |
| numéro de tirage | `tirage` |

```python
from sortie_modele import sortie_modele

df = sortie_modele(100)  # -> 400 lignes
df.to_csv("SORTIE_MODELE.csv", index=False)
```

Les deux familles de coefficients méritent un mot, parce que c'est le point où
deux modèles ne se ressemblent pas : `<coeff>` porte ici le coefficient
**dispersé** — il change d'une ligne à l'autre — et `<coeff>_nominal` la valeur
non dispersée du point de vol, constante sur ses cent lignes. Les figures
cherchent la valeur nominale d'abord dans la colonne du **même nom** que le
coefficient, puis dans `<coeff>_nominal` ; si votre modèle ne sort que la
première et qu'elle est constante par point de vol, c'est elle qui sert.

---

## 5.6 Les figures de tirage, point de vol par point de vol

Le tableau porte quatre cents lignes ; les figures du tirage parlent d'**un**
tirage. Entre les deux, une fonction :

```python
from cfd_dispersion import figures_tirage_par_pdv

inventaire = figures_tirage_par_pdv(
    df,
    points_de_vol={  # la forme du flight_point_dict
        "Mach": {"values": [0.70, 0.85], "label": "M", "save_name": "M"},
        "Altitude_m": {"values": [0, 10_000], "label": "Z", "save_name": "Z", "unit": " m"},
    },
    racine=sortie / "TIRAGES",
    max_tirages=15,  # par point de vol
    n_jobs=-1,  # tous les cœurs
)
```

Elle découpe le tableau par point de vol, prend ses premiers tirages, et écrit
pour chacun une figure par coefficient plus la matrice qui les empile :

```
TIRAGES/M_0.7/Z_0/tirage_000/CN.svg
TIRAGES/M_0.7/Z_0/tirage_000/matrice.svg
…
```

Un dossier par clé **qui varie** — une clé à valeur unique n'ajoute qu'un niveau
à traverser — et le point de vol est rappelé dans le titre de chaque figure, un
SVG se transmettant seul. Ce qui est rendu est l'**inventaire** : une ligne par
fichier écrit, avec son point de vol, son tirage et sa figure. Les figures, elles,
sont fermées au fur et à mesure ; un parcours en produit des centaines.

Trois points d'attention :

* **Quinze tirages par point de vol**, pas cent. Quatre cents figures par
  coefficient, personne ne les regarde. `max_tirages=None` les prend toutes.
* **La valeur nominale vient de `reference=`**, le tableau du tirage neutre
  (§5.5) : ses colonnes `<coeff>` *sont* les nominaux. À défaut, `nominaux=`
  l'impose, ou une colonne `<coeff>_nominal` du tableau la porte. Sans nominal,
  les deux panneaux de composantes sont tracés quand même et le troisième dit
  ce qui lui manque.
* **Le modèle est confronté au calcul.** La colonne `<coeff>` est la sortie
  dispersée ; le paquet recalcule `convention(nominal, biais, FE)` et compare.
  Les deux doivent tomber sur le même nombre — sinon c'est une convention
  différente de part et d'autre, une référence qui n'est pas celle qu'a vue le
  modèle, ou un modèle qui n'applique pas la dispersion là où on croit. Le
  verdict est écrit sur la figure (en rouge s'il y a désaccord) et dans
  l'inventaire, colonnes `calcul`, `modele`, `ecart`, `accord`.
* **Lois et sorties ne parlent pas forcément des mêmes coefficients.** La table
  de lois disperse ce que le modèle *consomme* ; le tableau rend ce qu'il
  *produit*. Un `CX0` interne au modèle a donc des lois mais aucune colonne de
  sortie, et un `CA` rendu par le modèle peut n'avoir ni biais ni FE. Les deux
  cas sont traités, et différemment : `CX0` garde ses **deux premiers
  panneaux** — les lois de ses composantes ne dépendent d'aucun nominal — et son
  troisième dit ce qui lui manque ; `CA` n'est pas tracé du tout, faute de
  tirage, et le demander en `coefficients=` est **refusé en le nommant**.
* **Une référence ambiguë est refusée.** Si le tableau de référence donne deux
  valeurs de `CN` pour ce que `points_de_vol` appelle un point de vol, c'est que
  le point de vol est sous-défini : le message nomme les colonnes qui le
  distingueraient plutôt que d'en choisir une au hasard.
* **Une figure coûte une demi-seconde** à écrire — la police du gabarit est
  vectorisée glyphe par glyphe. Un parcours de 4 × 15 tirages écrit 240 fichiers
  en une minute sur tous les cœurs, quatre en séquence. D'où `n_jobs`.

> **Pourquoi pas `batch_plot` directement ?** Son point de greffe,
> `on_before_save(fig, ax, context)`, arrive sur une figure **qu'il a déjà
> construite** : un axe, une courbe par source, un balayage en abscisse. Les
> figures de tirage n'ont ni balayage, ni courbe, ni axe unique. S'y greffer
> supposerait de lui faire tracer des courbes pour les effacer aussitôt. C'est
> donc sa **logique de parcours** qui est reprise — le `flight_point_dict` et
> l'arborescence — et non la fonction. Pour les polaires dispersées, en
> revanche, c'est bien `batch_plot` qui trace : voir §5.9.

`01_EXEMPLE/06_tirages_par_pdv.py` est ce parcours de bout en bout.

---

## 5.7 Le piège du croisement

**Un modèle appelé en croisé applique le même tirage à tous les points du
balayage.** Sur sept incidences, chaque valeur tirée apparaît sept fois dans le
tableau. Valider celui-ci tel quel serait une erreur, et elle ne se voit pas.

La fonction de répartition empirique est inchangée — donc la statistique *D* de
Kolmogorov–Smirnov aussi. Mais l'effectif est sept fois trop grand, le seuil se
resserre d'un facteur √7, et des tirages parfaitement corrects se font rejeter.
Mesuré sur 500 tirages conformes, croisés sur treize incidences :

| | n | D | p | verdict |
|:--|--:|--:|--:|:--|
| tel quel | 500 | 0.0336 | 0.61 | validé |
| croisé ×13 | 6500 | 0.0336 | 8·10⁻⁷ | rejeté |

Le remède tient en un argument :

```python
verdicts = valider_lot(resultats, lois, par=("Mach", "Altitude_m"), unique_par=("tirage",))
```

`unique_par` nomme les colonnes qui identifient un tirage ; les lignes qui les
répètent sont retirées **dans chaque groupe** avant validation. `figures_par_pdv`
prend le même argument, pour la même raison : sans lui, l'histogramme a la bonne
forme mais l'effectif affiché et le verdict sont faux.

**L'oubli n'est pas silencieux.** `valider_lot` refuse un groupe dont les
tirages sont massivement répétés, et le message nomme le remède :

```
ValueError: tirages massivement répétés en Mach=0.85 : 200 tirages distincts pour
1400 lignes, soit chacun ×7. C'est la signature d'un modèle appelé en croisé […]
    Dédoublonner : valider_lot(..., unique_par=("tirage",))
```

C'est un refus et non un avertissement, parce que le symptôme d'un oubli est un
*rejet de validation* — c'est-à-dire exactement ce que l'utilisateur est venu
chercher, et qu'il n'a aucune raison de mettre en doute. Le contrôle porte sur
le n-uplet complet des composantes, si bien qu'une composante constante (loi de
type 1 ou 2) ne le déclenche pas ; `redondance_max=1.0` le désactive.

---

## 5.8 Le cas d'un balayage : une courbe par tirage

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

`par=` nomme les colonnes qui **identifient un tirage**. Le numéro posé par
`lire_sortie_modele` fait l'affaire (`["tirage"]`) ; à défaut, les composantes
tirées aussi (`["CN_Biais", "CN_FE"]`), puisqu'elles sont constantes le long
d'une courbe.

**Sur un tableau croisé, figer d'abord le point de vol.** Une polaire se lit à
Mach et altitude constants ; sans ce filtre, les points de plusieurs points de
vol se retrouveraient sur la même abscisse.

```python
bloc = resultats.loc[(resultats["Mach"] == 0.85) & (resultats["Altitude_m"] == 8000.0)]
x, courbes = courbes_par_tirage(bloc, x="alpha", y="CN", par=["tirage"])
```

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

## 5.9 La greffe sur `batch_plot`

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
    tirages=tirages,  # facultatif : les courbes obtenues (§5.10)
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

## 5.10 Le dictionnaire `tirages` et sa clé

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

Sur un tableau **croisé**, il y a une polaire par point de vol, donc un jeu de
courbes par point de vol : la clé par défaut ne suffit plus, et il faut la
vôtre.

```python
def cle_par_pdv(context):  # de niveau module : voir l'encadré ci-dessous
    return (context.y_key, context.sweep_key, context.flight_point["Mach"])


tirages = {}
for coefficient in lois:
    for mach in L_MACH:
        bloc = resultats.loc[resultats["Mach"] == mach]
        _, courbes = courbes_par_tirage(bloc, x="alpha", y=coefficient, par=["tirage"])
        tirages[(coefficient, "alpha", mach)] = courbes


hook_dispersion(lois, serie="CFD", tirages=tirages, cle=cle_par_pdv)
```

C'est exactement ce que fait `01_EXEMPLE/05_modele_croise.py`, qui sort une
polaire dispersée par Mach.

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

## 5.11 Récapitulatif des formats

| ce que vous fournissez | forme exacte |
|:--|:--|
| le plan d'appels | `plan_croise(Mach=L_MACH, Altitude_m=L_ALTITUDE, alpha=L_ALPHA)` |
| la table de lois | `{coeff: {"Biais_Type", "Biais_M", "Biais_ET", "FE_Type", "FE_M", "FE_ET"}}` |
| ce que le modèle reçoit | `{coeff: {"Biais": float, "FE": float}}` — un `Tirage`, ou `dict(tirage)` |
| la base de référence | le même modèle avec `tirage_neutre(lois)`, une ligne par point de vol |
| la sortie, forme à plat | `DataFrame`, une ligne par appel ; colonnes `<coeff>_Biais`, `<coeff>_FE`, `<coeff>`, les clés de point de vol, un identifiant de tirage |
| la sortie, forme large | `DataFrame` + colonnes `DICT_TIRAGE` et `DICT_LAW_DISPERSION` (dict ou chaîne) + vos métadonnées → `lire_sortie_modele(df)` |
| la validation d'un tableau croisé | `valider_lot(..., par=…, unique_par=("tirage",))` |
| la sortie sur un balayage | une ligne par (tirage × point) ; plus la colonne de balayage et un identifiant de tirage |
| `tirages=` du hook | `{(y_key, sweep_key): tableau (n_tirages, npts)}` |
| les figures `batch_plot` | les quatre dictionnaires de §5.9 |
| les figures de tirage par point de vol | `figures_tirage_par_pdv(df, points_de_vol={…}, racine=…)` — §5.6 |
