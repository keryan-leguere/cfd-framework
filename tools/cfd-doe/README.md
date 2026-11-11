# cfd-doe — plan d'expériences CFD

Établir le DOE de calcul CFD d'un engin (fusée, missile, avion) en deux temps :

1. **Réduire le domaine** *(disponible)* : à partir des plages des variables, du type de
   trajectoire et des symétries de l'engin, dire quels **sous-domaines** il faut réellement
   calculer.
2. **Remplir les sous-domaines** *(disponible)* : `cfd-doe remplir` construit et compare les
   plans (factoriel, décomposition, grilles creuses, LHS, adaptatif…), écrit le DOE prêt à
   lancer et trace les figures. Méthodes, hypothèses et décomptes :
   [`00_DOC/02_REMPLISSAGE.md`](00_DOC/02_REMPLISSAGE.md).

La théorie est dans [`00_DOC/01_BASE_AERO.md`](00_DOC/01_BASE_AERO.md) : passage en
(αt, φa), repère mixte, symétries, conséquences sur le DOE.

## 1. Installation

```bash
cd tools/cfd-doe
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cfd-doe --help            # ou, sans script console : python -m cfd_doe --help
```

Python ≥ 3.9 ; dépendances : numpy, rich, pyyaml. Aucune dépendance à `$CFD_FRAMEWORK`.

## 2. Usage

```bash
cfd-doe exemple                                    # copie 01_EXEMPLE/ dans ./cfd-doe-exemple
cfd-doe domaine cfd-doe-exemple/ETUDE_FUSEE.yaml   # sous-domaines à calculer
cfd-doe domaine ETUDE.yaml --repere cartesien      # ce que coûterait de rester en (α, β)
cfd-doe domaine ETUDE.yaml --verbose               # + la démarche : comment on obtient les sous-domaines
cfd-doe domaine ETUDE.yaml --export SD.yaml        # pour la phase de remplissage (.yaml / .json)
cfd-doe check ETUDE.yaml                           # validation seule
cfd-doe remplir REMPLISSAGE.yaml                   # peupler les sous-domaines : doe.csv, figures

# Sans fichier :
cfd-doe domaine --traj 6DOF --sym cruciforme \
    --alpha -20 20 --beta -5 5 --dl -10 10 --dm -20 20 --dn -20 20
```

Les options de ligne de commande priment sur le fichier. Code de retour : `0` succès, `1` erreur
d'entrée (panneau rouge, jamais de trace d'appels).

## 3. Fichier d'étude

```yaml
etude:
  nom: FUSEE_ETUDIANTE
trajectoire: 6DOF            # voir § 4
geometrie: cruciforme        # quelconque | plan_vertical | double_symetrie | cruciforme
                             # | revolution | {type: n_ailettes, n_ailettes: 3}
repere: auto                 # auto | cartesien | polaire
limite_braquage: disque      # disque : √(δm² + δn²) ≤ δmax | carre : |δm|, |δn| ≤ δmax
variables:                   # degrés ; [bas, haut] ou une valeur
  alpha: [-20, 20]
  beta: [-5, 5]
  DL: [-10, 10]
  DM: [-20, 20]
  DN: [-20, 20]
# trajectoires:              # types supplémentaires (facultatif)
#   ROULIS_SEUL: {efforts: [A, l], description: "…"}
```

Toute clé inconnue est refusée avec la liste des clés admises : une faute de frappe ne retombe
jamais silencieusement sur un défaut.

## 4. Types de trajectoire (Freeman)

Une variable est **active** si la trajectoire consomme l'effort qu'elle pilote (N ← α, Y ← β,
m ← δm, n ← δn, l ← δl). Les autres sont fixées à 0 ; une plage donnée pour une variable inactive
produit un avertissement.

| Type | Efforts | Variables actives |
|---|---|---|
| `1DOF` | A | — |
| `2DOF` | A, N | α |
| `3DOF_MASSE_PONCTUELLE` | A, N, Y | α, β |
| `3DOF_TANGAGE` | A, N, m | α, δm |
| `4DOF` | A, N, m, l | α, δm, δl |
| `5DOF` | A, N, Y, m, n | α, β, δm, δn |
| `6DOF` | A, N, Y, m, n, l | α, β, δm, δn, δl |

## 5. Ce que fait la réduction

**Choix du repère** (`repere: auto`, §5.4 du document) :

- **polaire** (αt, φa), braquages en repère mixte (δl, δmB, δnB), pour un engin à rotation
  d'ordre ≥ 3 (cruciforme, N ailettes) ou de révolution, dès que α et β sont actifs. C'est le seul
  repère où la rotation de 90° et les miroirs à 45° s'exploitent ;
- **cartésien** (α, β) en repère engin sinon. Seuls les miroirs vertical/horizontal et la rotation
  de 180° y sont exploitables ; s'il est imposé à un cruciforme, le rapport dit ce qui est perdu.

**Symétries → sous-domaines.** Le domaine est ramené à un *domaine fondamental* : chaque point du
domaine d'entrée y a exactement un représentant par symétrie. Il se découpe en sous-domaines
disjoints, car sur un plan de symétrie une partie du groupe agit encore, sur les braquages :

| Sous-domaine | Ce qui s'y passe |
|---|---|
| `secteur` | intérieur du secteur φa ∈ ]0, 180°/N[ : toute la grille de braquages |
| `plan` | plan de symétrie φa = φs : le miroir relie (δl, δnB) à (−δl, −δnB), demi-grille |
| `axe` | αt = 0 : φa n'a plus de sens, tout le groupe agit sur les braquages (repère engin) |
| `plan β = 0`… | en cartésien, le plan du miroir et ce qu'il réduit encore |

Les bornes ouvertes comptent : `]0;20]` exclut 0, sans quoi les points du plan seraient
calculés deux fois. Les contraintes non cartésiennes (disque des braquages, secteur à αt = 0) sont
données en renvois sous le tableau, et dans l'export.

**Précautions signalées** :

- plage asymétrique d'une variable qu'une symétrie retourne : elle est étendue à l'enveloppe
  symétrique ;
- en polaire, le disque αt ≤ αt,max couvre le rectangle (α, β), coins compris (§5.4) ;
- limite de braquage en carré : tournée de φa, elle impose le disque de rayon √(δm² + δn²)
  (§7.6).

**Démarche (`--verbose`, `-v`).** Entre l'en-tête et le tableau, le rapport déroule le
raisonnement en cinq étapes, chacune en arbre :

1. *trajectoire* : quel effort pilote chaque variable, lesquelles sont fixées à 0 ;
2. *repère* : pourquoi ce repère ; en polaire, plage d'αt et arc de φa issus du rectangle (α, β),
   passage des braquages en repère mixte et limite (disque, ou carré tourné → disque circonscrit) ;
3. *groupe de symétries* : chaque symétrie et les variables dont elle change le signe (en
   cartésien, vu aussi sur les seules variables libres — des symétries s'y confondent), plages
   étendues pour que le groupe préserve le domaine, symétries perdues en cartésien ;
4. *découpage* : la récurrence qui a réellement tourné — quelle variable est forcée ≥ 0, par
   quelles symétries, ce qui agit encore sur `v > 0` et sur `v = 0` ; en polaire, repliement de
   l'arc de φa dans le secteur fondamental, plans de miroir, axe αt = 0 ;
5. *recollement* des strates contiguës, et numérotation.

Chaque branche terminale porte `→ #k`, la ligne du tableau où elle aboutit : la démarche se lit
contre le résultat. Ce n'est pas un second calcul : le moteur rédige au fil de la réduction
(`engine/demarche.py`, à partir du journal de `stratifier_signes` et de `fusionner`), et refuse de
produire une feuille qui ne tombe pas dans exactement un sous-domaine.

## 6. Conventions de signe

x avant, y droite, z bas ; α = atan(w/u), β = asin(v/V) ; φa = atan2(v, w) ∈ [0, 360[ (document
§1, §2). Les actions des symétries sur les signes de (α, β, δl, δm, δn) sont regroupées dans
`src/cfd_doe/data/geometries.py`. Si vos conventions de braquage diffèrent, c'est le seul
fichier à ajuster (document §8, points ouverts).

## 7. Compléter une table de résultats par symétrie

La CFD ne calcule qu'un représentant par orbite. Un lecteur qui exploite les symétries
*globales* (secteur φa ∈ [0 ; 45°], β ≥ 0) mais qui attend une grille **produit** — un seul
grand domaine — trouve donc des trous sur les plans de symétrie et sur l'axe αt = 0.
`01_EXEMPLE/completer_table.py` (recopié par `cfd-doe exemple`) les bouche. C'est un script
**autonome** (pandas, numpy, pyyaml, rich ; aucun import de `cfd_doe`), à adapter à vos noms de
colonnes :

```bash
pip install -e ".[table]"                         # pandas
cfd-doe domaine ETUDE.yaml --export SD.yaml       # le plan, avec son groupe de symétries
python completer_table.py SD.yaml RESULTATS.csv -o COMPLET.csv --cles Mach \
    --noms alphat=ALPHAT phia=PHIA CN=CNB CY=CYB  # vos noms de colonnes
python exemple_completion.py                      # exemple factice, validé (polaire)
python exemple_completion.py --cartesien --beta-positif
```

```python
from completer_table import completer_table

complet = completer_table(
    df,
    "SD.yaml",
    cles=["Mach"],
    coefficients={"CA": "CAB", "CN": "CNB", "CY": "CYB", "Cl": "ClB", "Cm": "CmB", "Cn": "CnB"},
)
```

- **Grille cible** : produit des valeurs de la table (et de leurs images) sur l'enveloppe des
  sous-domaines ; `domaine={"alpha": (-20, 20)}` (`--domaine alpha -20 20`) si votre code lit plus
  large, par exemple β ≥ 0 seulement.
- **Lignes déduites** : un nœud absent prend la valeur d'une image calculée, `C(x) = s·C(g·x)`.
  Les symétries et les coefficients qu'elles retournent viennent de la clé `symetries` de
  l'export : le script ne réécrit aucune convention de signe.
- **Axe αt = 0** (polaire) : φa n'y est qu'une convention ; le nœud est ramené à φa = 0, braquages
  et coefficients tournés de φa (§3.2, §7.1). Quand l'image tombe entre deux nœuds, la valeur est
  interpolée dans le plan (δm, δn) — exacte pour ce qui est linéaire en braquages, signalée dans
  la colonne `origine` (`interpoler_axe=False` en fait des trous).
- **Trous** : NaN par défaut, pour que la table reste carrée (`trous="omettre"` sinon) —
  typiquement les coins hors du disque des braquages, jamais calculés.
- **Contrôle gratuit** : deux lignes calculées images l'une de l'autre, ou un point sur son
  propre plan de symétrie, doivent respecter la symétrie ; l'écart est affiché. Une convention
  de signe différente de celle du document s'y voit tout de suite.

Hypothèses du document : CN = −CZ, CA = −CX ; en polaire, coefficients et braquages en repère
mixte. Elles ne servent qu'au traitement de l'axe αt = 0.

## 8. Remplir les sous-domaines

`cfd-doe remplir REMPLISSAGE.yaml` lit un second fichier, qui dit **comment** peupler les
sous-domaines de l'étude : conditions (Mach, paramètres indépendants), grille de référence, et
autant de plans nommés qu'on veut comparer. Le plan `retenu` part dans le fichier DOE.

```bash
pip install -e ../cfd-plot                           # pour les figures (facultatif)
cfd-doe remplir REMPLISSAGE_FUSEE.yaml               # rapport, DOE/doe.csv, DOE/FIGURES/
cfd-doe remplir REMPLISSAGE_FUSEE.yaml --verbose     # détail de chaque plan, par Mach et sous-domaine
cfd-doe remplir REMPLISSAGE_FUSEE.yaml --retenu lhs --repere polaire --sortie DOE_LHS
```

```yaml
etude: ETUDE_FUSEE.yaml          # donne les sous-domaines
repere: cartesien                # surcharge facultative
mach: [0.6, 0.8, 0.95, 1.05, 1.2, 1.5, 2.0, 3.0]
parametres:
  moteur: {niveaux: [0, 0.5, 1], nominal: 0}        # discret: true → jamais facteur continu
niveaux:                         # grille de référence : liste, {pas: p} ou {n: k}
  alpha: {pas: 5}
  DM: [-20, -10, 0, 10, 20]
plans:
  complet: {type: factoriel}
  ordre_1: {type: decomposition, ordre: 1, controle: {fraction: 0.15}}
  lhs: {type: lhs, regle: 30, part_plans: 0.25, test: 0.15}
retenu: ordre_1
exclure:
  - mach >= 2 and abs(alpha) > 15
sortie: {dossier: DOE, csv: doe.csv, figures: true, tous_les_csv: false}
```

| Type | Options | Ce que contient le DOE |
|---|---|---|
| `factoriel` | `niveaux` (surcharge → niveaux inégaux) | `calcul` : tous les nœuds |
| `etoile` | `niveaux` | `calcul` : un balayage par facteur |
| `decomposition` | `ordre`, `primaires`, `increments_fonction_de`, `increments`, `couplages`, `croiser`, `controle` | `calcul` : base + une table par effet ; `controle` : nœuds croisés |
| `composite_centre`, `box_behnken`, `grille_creuse` | `fraction`, `niveau`, `test` | `calcul` : le plan ; `test` : points indépendants |
| `lhs`, `halton` | `regle` ou `points_par_mach`, `part_plans`, `test`, `graine`, `decale_par_mach` | `calcul` + `test` |
| `adaptatif` | comme `lhs` (règle 10·d) | `calcul` : le lot initial ; `test` |
| `multi_fidelite` | comme `lhs`, `regle_hf` ou `points_hf_par_mach` | colonne `fidelite` : `BF`, et `HF` emboîté |

**Le fichier DOE** (`doe.csv`, séparé par des tabulations) : une ligne par calcul, colonnes
`id`, `role`, `table`, `sous_domaine`, (`fidelite`), `mach`, les paramètres, puis les variables du
repère de travail. En polaire s'ajoutent `alpha`, `beta`, `DM`, `DN` : le point en repère engin,
celui qu'on impose au solveur. `role` vaut `calcul`, `controle` ou `test` : le rapport donne, pour
chaque plan, la **démarche** — quoi lancer, dans quel ordre, quoi comparer.

**Ce qui est garanti** : chaque point est dans un sous-domaine, une seule fois. Un plan sur grille
ne garde que les nœuds des sous-domaines (les autres sont leurs images) ; un plan structuré, dont
l'image d'un point n'est pas toujours dans le plan, est **replié** sur les sous-domaines ; un plan
tiré l'est directement dedans, contraintes comprises (disque des braquages).

**Souplesse** :

- un même fichier vaut pour les deux repères : les niveaux de l'autre repère sont ignorés, un
  effet nommé `DM` désigne `DMB` en polaire, et une exclusion écrite en `alpha` reste valable ;
- `exclure` accepte comparaisons, `and`/`or`/`not`, arithmétique, `abs`/`min`/`max` sur `mach`,
  les paramètres et les variables — c'est ainsi qu'on fait dépendre le domaine du Mach. À garder
  compatible avec les symétries (`abs(alpha)`, pas `alpha`) ;
- toute clé inconnue est refusée, avec la liste des clés admises.

**Figures** (`DOE/FIGURES/`, avec `cfd-plot`) : `domaine.png` (ce que les symétries épargnent),
`plan_<nom>.png` (chaque plan projeté sur tous les couples de facteurs, rôles en couleur),
`comparaison_calculs.png` et `comparaison_plans.png`. Sans `cfd-plot`, le rapport et le DOE sont
produits quand même.

## 9. Organisation

```
00_DOC/              théorie (FR) : 01 base aéro et symétries, 02 méthodes de remplissage
                     (figures : generer_figures.py, avec cfd-plot ; décomptes : compter_remplissage.py)
src/cfd_doe/
  core/              calcul pur : intervalles, angles, groupes de signes, domaine fondamental
  data/              variables, trajectoires, géométries, fichier d'étude
  engine/            reduire(etude) → Reduction ; vers_dict pour l'export ;
                     remplir(remplissage) → plans, ecrire_csv
  report/            rendu Rich (FR, sans gras ; CFD_DOE_GRAS=1 le rétablit)
  cli/               cfd-doe domaine | remplir | check | exemple
  01_EXEMPLE/        ETUDE_FUSEE.yaml, REMPLISSAGE_FUSEE.yaml, completer_table.py,
                     exemple_completion.py (données de paquet)
tests/               pytest ; test_architecture.py vérifie la règle de couches
```

La règle de couches `cli → report → engine → data → core` est vérifiée sur les imports. Le test
central est celui des **orbites** (`tests/test_reduction.py`) : pour chaque point d'une grille, on
énumère son orbite complète et on vérifie qu'exactement une image tombe dans les sous-domaines.
Les décomptes du document (45, 78, 144, 265 au §5.3 ; 63 et 33 au §5.4 ; 4 200 au §7.4) sont
retrouvés sur les sous-domaines produits.

```bash
pytest && ruff check . && mypy src
```
