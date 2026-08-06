# Format des entrées

Deux fichiers d'entrée : les **CSV de trajectoire**, un par tir, et le **fichier
d'étude** qui décrit ce qu'on veut en tirer.

---

## 1. Les fichiers de trajectoire

Un fichier CSV par tir, tous dans le même répertoire. Séparateur **virgule**,
séparateur décimal **point**, encodage UTF-8.

```csv
time,Mach,Altitude,alpha,beta,dl,dm,dn,PARA1,PARA2
0,0.103027,150,4.11365,0.727837,0,-4.11365,-0.800621,60.3529,779.05
0.25,0.216041,155.216,4.00784,1.03428,0.0854,-4.00784,-1.13771,63.4523,782.7
…
```

### Les huit colonnes obligatoires

| Colonne | Grandeur | Unité |
|:---|:---|:---|
| `time` | temps | s |
| `Mach` | nombre de Mach | — |
| `Altitude` | altitude **géométrique** | m |
| `alpha` | incidence | deg |
| `beta` | dérapage | deg |
| `dl` | braquage de roulis | deg |
| `dm` | braquage de tangage | deg |
| `dn` | braquage de lacet | deg |

L'ordre des colonnes n'a pas d'importance ; seuls les noms comptent.

### Les colonnes de paramètres

**Tout le reste** est une colonne de paramètre générique. Il peut y en avoir
zéro, une, ou trente, sous n'importe quels noms — `PARA1`, `rapport_pression`,
`TEMP 42`, `é_accentué`. Rien dans l'outil ne reconnaît une colonne autrement
que par ses valeurs ou par ce que l'étude en déclare.

Seule restriction : un nom de colonne ne peut pas être celui d'une grandeur
**dérivée**, que l'outil calcule lui-même et ajouterait au même endroit :

```
alpha_tot  phi  phi_fold  phi_defined  tir
p_inf  T_inf  rho_inf  a_inf  mu_inf  V_inf  q_inf  Re_m  Re_ref
```

### Ce qui est toléré

- des tirs de **longueurs différentes** — c'est même le cas normal ;
- des **valeurs manquantes** : comptées, signalées, et exclues des statistiques ;
- un **temps non strictement croissant** : signalé en jaune, jamais bloquant ;
- des noms de colonnes avec espaces, accents, chiffres en tête.

### Ce qui est refusé

- une colonne obligatoire absente ;
- deux fichiers du lot avec des jeux de colonnes différents ;
- un fichier vide, ou réduit à son en-tête ;
- un séparateur `;` ou une virgule décimale.

---

## 2. Le fichier d'étude

Un seul fichier YAML. Seules les sections `etude` et `reference` sont
obligatoires ; tout le reste a des valeurs par défaut. **Toute section ou clé
inconnue est une erreur** : une faute de frappe ne doit jamais produire
silencieusement un plan amputé d'une dimension.

### 2.1 Squelette minimal

```yaml
etude:
  nom: "LOT_MC_2026_REV_B"
  source: "TRAJECTOIRES/tir_*.csv"

reference:
  longueur_m: 2.5
```

### 2.2 Schéma complet

```yaml
etude:
  nom: "LOT_MC_2026_REV_B"        # requis — titre des rapports
  source: "TRAJECTOIRES/tir_*.csv"  # requis — répertoire ou motif,
                                    #   résolu relativement à CE fichier
  sortie: "SORTIE"                  # répertoire des fichiers produits

reference:
  longueur_m: 2.5                 # requis — longueur de référence du Reynolds
  surface_m2: 0.049               # optionnel, documentaire

atmosphere:
  delta_t_K: 0.0                  # écart ISA constant appliqué au lot entier

symetrie:
  groupe: "C4v"                   # C4v | C4 | Cs | C1 | Cinfv
  plan_reference_deg: 0.0         # quel plan du corps est appelé φ = 0°
  n_azimuts: 3                    # surcharge le nombre de niveaux de φ

bandes:
  bornes: [0.5, 0.8, 0.95, 1.2, 1.8, 2.5, 3.2]   # mode explicite
  # --- ou bien, en commentant « bornes » : ---
  # n_bandes: 8
  # transsonique: [0.8, 1.2]
  # raffinement_transsonique: 2   # sous-divisions dans le transsonique
  points_min: 30                  # sous ce seuil, la bande est fusionnée

enveloppe:
  quantile_bas: 0.001             # 0,1 % — stable, contrairement au min absolu
  quantile_haut: 0.999
  marge: 0.05                     # relative à la largeur inter-quantile

parametres:
  # indexé par NOM DE COLONNE — voir §2.3
  PARA1: { role: conditionnel, niveaux: 3, echelle: log }
  dl:    { role: mecanique, plage: [-20.0, 20.0], niveaux: 3 }

doe:
  methode: "tensoriel"            # tensoriel | lhs
  coins: true                     # inclure les coins du domaine conditionnel
  n_lhs_par_bande: 24             # méthode lhs uniquement
  graine: 12345                   # reproductibilité stricte
  noeuds_max: 2000                # au-delà : code 2, sans rien allouer
  fraction_discret: 0.25          # part des nœuds au second niveau discret
  braquages:
    - { nom: "neutre",  dl: 0.0,  dm: 0.0,  dn: 0.0 }
    - { nom: "tangage", dl: 0.0,  dm: 15.0, dn: 0.0 }
    - { nom: "roulis",  dl: 15.0, dm: 0.0,  dn: 0.0 }
```

### 2.3 La section `parametres`

C'est ici que se joue la généricité. Le tableau est indexé par **nom de colonne
tel qu'il apparaît dans l'en-tête des CSV**. Aucune hypothèse de nommage ni de
nombre. Une colonne non déclarée reçoit un rôle auto-détecté, signalé en jaune.

#### Les cinq rôles

| Rôle | Ce que ça veut dire | Niveaux par défaut |
|:---|:---|---:|
| `principal` | dimension de grille propre | 5 |
| `conditionnel` | conditionnée au Mach : bornes recalculées par bande | 3 |
| `discret` | facteur à deux niveaux, appliqué par superposition | 2 |
| `mecanique` | couvre une **plage mécanique déclarée**, jamais la plage trajectoire | 3 |
| `ignore` | présente dans les CSV, exclue de tout | — |

Le rôle `mecanique` mérite un mot. Restreindre les braquages aux valeurs
commandées par la loi de pilotage actuelle rendrait la base **circulaire** et
interdirait toute évolution du guidage-pilotage. On couvre donc la butée
mécanique des gouvernes, indépendamment de ce que la trajectoire fait.

#### Les clés d'une entrée

| Clé | Type | Effet |
|:---|:---|:---|
| `role` | requis | un des cinq ci-dessus |
| `niveaux` | entier | nombre de niveaux dans la grille |
| `echelle` | `lineaire` \| `log` | bornes, niveaux et ACP en espace log |
| `plage` | `[bas, haut]` | requis pour `mecanique` |
| `min_physique` | flottant | plancher appliqué à la borne basse |
| `quantile_bas` / `quantile_haut` | flottant | surcharge locale |
| `marge` | flottant | surcharge locale |
| `unite`, `libelle` | texte | affichage seulement |

#### Les noms réservés

Les grandeurs dérivées se déclarent comme les autres :

```yaml
parametres:
  alpha_tot: { role: principal, niveaux: 5, unite: "deg" }
  phi_fold:  { role: principal }        # niveaux imposés par le groupe
  Mach:      { role: principal, niveaux: 3 }
  Re_ref:    { role: discret, niveaux: 2, echelle: log }
```

Deux d'entre elles ignorent leurs bornes déclarées, par construction :

- **`Mach`** prend pour bornes la bande elle-même. Les bornes de bande sont
  exactes ; les élargir placerait des nœuds à un Mach n'appartenant à aucune
  bande, et ferait se chevaucher les bandes de façon ambiguë.
- **`phi_fold`** prend ses niveaux du groupe de symétrie. `niveaux` n'a donc
  pas de sens ici ; c'est `symetrie.n_azimuts` qui commande.

### 2.4 Les règles d'auto-détection

Appliquées à toute colonne non déclarée, et **pilotées par les valeurs, jamais
par le nom** :

1. `time`, `Altitude`, `alpha`, `beta` → `ignore` (absorbées par les dérivées) ;
   `Mach` → `principal`.
2. `dl`, `dm`, `dn` → `mecanique`. Sans `plage` déclarée, repli sur
   `±1,5 × max|valeur observée|` arrondi, avec une note jaune explicite.
3. Toute autre colonne :
   - ≤ 2 valeurs distinctes → `discret` ;
   - sinon `|ρ_Spearman(colonne, Mach)| ≥ 0,7` → `conditionnel`, 3 niveaux ;
   - sinon → `principal`, 3 niveaux ;
   - échelle `log` si toutes les valeurs sont > 0 et que max/min ≥ 100.

Le ρ mesuré est **affiché** pour chaque colonne dans le rapport d'inspection.
Le seuil de 0,7 est le paramètre le plus arbitraire de l'outil : il n'est
volontairement pas réglable, mais la valeur mesurée est donnée pour que la
décision se prenne en connaissance de cause.

`cfd-traj inspecter --proposer` produit le bloc `parametres:` prêt à coller.

---

## 3. Les fichiers produits

| Fichier | Contenu |
|:---|:---|
| `PLAN.xlsx` | le classeur de revue : synthèse, plan, enveloppe, paramètres |
| `PLAN.csv` | une ligne par cas de calcul |
| `PLAN.yaml` | le même plan, groupé par bande |
| `ENVELOPPE.csv` | une ligne par (bande, variable) |
| `STATISTIQUES.csv` | une ligne par colonne |
| `HORS_DOMAINE.csv` | les points de trajectoire en extrapolation |

### Colonnes de `PLAN.csv`

```
node_id  bande  mach_bas  mach_haut
<une colonne par variable active, dans l'ordre de l'enveloppe>
braquage  dl  dm  dn  configuration  cout_relatif  composantes_nulles  origine
```

L'ordre des colonnes variables est **dérivé de l'enveloppe**, jamais d'une liste
codée en dur : un lot à douze colonnes génériques produit douze colonnes.

`origine` vaut `grille`, `lhs` ou `coin`. `cout_relatif` est le coût du cas en
équivalents configuration complète. `composantes_nulles` liste les composantes
identiquement nulles par théorème à ce nœud.

Les nombres y sont écrits avec un **point décimal machine** : le formatage
français est réservé aux rapports du terminal.
