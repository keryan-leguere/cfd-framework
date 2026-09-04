# Exemple cfd-dispersion — prêt à tourner

Tout est là : une table de lois, un modèle jouet, et cinq scripts qui
parcourent l'ensemble des fonctions du paquet.

```bash
bash RUN_EXEMPLE.sh          # les cinq, dans l'ordre — sorties dans SORTIE/
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
| `01_tirage.py` | cas d'usage 1 : tirer, reconstruire, la loi du coefficient dispersé, tracer, comparer les plans |
| `02_monte_carlo.py` | cas d'usage 2.1 et 2.2 : valider mille appels, synthétiser, ne tracer que les rejets |
| `03_polaire_batch_plot.py` | cas d'usage 2.3 : la dispersion greffée sur `cfd_plot.batch_plot` |
| `04_bande_et_correlation.py` | corrélé/indépendant, les trois remplissages, deux coefficients liés |
| `05_modele_croise.py` | **la forme d'un vrai modèle** : listes d'axes croisées, tableau large à colonnes dictionnaires |

---

## Ce que chacun montre

### `01_tirage.py` — un tirage, et ce qu'il devient

Charge la table (dict Python **et** YAML), tire une réalisation, la reconstruit
sous les cinq conventions, calcule la **loi du coefficient dispersé**, écrit les
figures, puis compare les trois plans d'échantillonnage sur mille tirages.

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
  `densité lissée (LHS n=20 000)` : les autres ont une loi exacte.

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
