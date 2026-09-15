# 2. Déclarer ses tables

Une déclaration dit **où** est une table dans le code compilé, et **comment** la
lire. Elle s'écrit en Python ou en YAML — même structure, mêmes clés.

```python
TABLES = {
    "CN": {
        "bloc": "tab_cn",
        "tableau": "tab_cn",
        "colonnes": ["mach", "alpha", "delta", "CN"],
        "qoi": ["CN"],
        "lignes": "npt_cn",
        "constantes": {"altitude": 0.0},
        "rtol": 1e-9,
        "atol": 1e-12,
    },
}
```

```yaml
tables:
  CN:
    bloc: tab_cn
    colonnes: [mach, alpha, delta, CN]
    lignes: npt_cn
```

La forme attendue du tableau est **longue** : une ligne par point, une colonne
par variable, les valeurs tabulées en dernier.

```fortran
      DOUBLE PRECISION TAB_CN(320, 4)
      INTEGER NPT_CN
      COMMON /TAB_CN/ TAB_CN, NPT_CN
```

| mach | alpha | delta | CN |
|---:|---:|---:|---:|
| 0.30 | −4.0 | −4.0 | −0.4603 |
| 0.30 | −4.0 | −2.0 | −0.4099 |
| … | … | … | … |

---

## Les clés

### `bloc` — obligatoire

Le nom du COMMON block, **tel que f2py l'expose**. f2py met tout en minuscules :
`COMMON /TAB_CN/` devient `module.tab_cn`. La résolution ne tient pas compte de
la casse, donc `TAB_CN` marche aussi.

Si le nom est faux, le message liste ce que le module expose réellement. C'est
aussi ce que donne `cfd-validation inspecter --module …`, et c'est le premier
réflexe devant un module inconnu.

### `tableau` — par défaut, le nom du bloc

Le tableau à l'intérieur du bloc. `COMMON /TAB_CN/ TAB_CN` est le cas le plus
fréquent, et la clé peut alors être omise.

### `colonnes` — obligatoire

Un nom par colonne du tableau, **dans l'ordre**. Ces noms sont les vôtres : ils
servent à nommer les axes dans le rapport et les figures, et rien dans le paquet
ne les interprète.

### `qoi` — par défaut, la dernière colonne

Les grandeurs contrôlées. Tout le reste est une variable **indépendante**, c'est-
à-dire une coordonnée dans la table.

Une table peut en porter plusieurs : `qoi: [CN, CM]` avec
`colonnes: [mach, alpha, CN, CM]`. Chacune est comparée séparément et obtient sa
propre ligne de rapport.

Il faut au moins une variable indépendante : une table qui ne serait que des QOI
est une liste, pas une table.

### `lignes` — fortement recommandé

Le nombre de lignes **réellement renseignées**. Soit un entier, soit le nom d'un
entier du même COMMON block (le cas normal).

> Un tableau Fortran est dimensionné au maximum et un `NPTS` dit combien de
> lignes sont écrites. Sans cette clé, le contrôle compare le modèle à des
> lignes de remplissage — et sort rouge sur un code parfaitement juste.

La clé est facultative, et son absence n'est pas devinée : rogner les lignes
nulles de la fin supprimerait un nœud légitimement nul. Le détecteur
`queue_non_renseignee` rattrape le cas et nomme le remède.

### `constantes` — facultatif

Les colonnes que votre modèle réclame mais que **cette table-ci ne balaie pas**.

Un modèle aérodynamique veut souvent une altitude, un dérapage, une position de
centre de gravité, là où la table `CN` n'est fonction que de (mach, incidence,
braquage). Ces valeurs complètent le cadre d'entrée et ne participent pas à la
comparaison.

Une constante qui porte le nom d'une colonne de la table est refusée : la table
fait foi, et laisser passer choisirait silencieusement l'une des deux.

### `orientation` — facultatif, inféré

`lignes` (une ligne = un point) ou `colonnes` (une colonne = un point).

L'orientation s'infère de la dimension qui vaut `len(colonnes)`. Elle ne peut
pas s'inférer d'un tableau **carré** qui porte autant de colonnes que déclaré :
la déclaration est alors exigée, plutôt que de tirer au sort la lecture de toute
une table.

### `rtol`, `atol` — par défaut `1e-9` et `1e-12`

Un point est conforme si `|Δ| ≤ atol + rtol·|référence|`.

Le défaut suppose une relecture exacte, ce qui est le cas normal. Desserrer est
légitime quand la chaîne d'appel comporte une conversion ; ça ne l'est plus
quand c'est pour faire taire un écart qu'on ne s'explique pas.

### `tolerances` — facultatif

Une surcharge par grandeur, pour une table qui en porte plusieurs d'échelles
différentes :

```yaml
rtol: 1e-9
tolerances:
  CM: {rtol: 1e-6, atol: 1e-9}
```

### `libelles`, `unites` — facultatif

De quoi rendre les figures lisibles : `{alpha: incidence}`, `{alpha: "°"}`. Sans
eux, le nom brut de la colonne sert de libellé et l'unité vaut `-`.

---

## Les clés inconnues sont refusées

```
table « CN » : clé(s) inconnue(s) ['rtl'].
Clés admises : ['atol', 'bloc', 'colonnes', 'constantes', 'libelles',
                'lignes', 'orientation', 'qoi', 'rtol', 'tableau',
                'tolerances', 'unites'].
```

Une clé mal orthographiée est silencieuse par nature : `rtl: 1e-3` laisserait la
tolérance par défaut et ferait passer une table fausse pour bonne. C'est le seul
mode de défaillance qui coûte plus cher que pas de contrôle du tout.

## Vérifier sans rien exécuter

```bash
cfd-validation check --tables TABLES.yaml
```

Valide la déclaration seule — ni module, ni modèle. Utile en revue, et en
intégration continue avant d'avoir compilé quoi que ce soit.
