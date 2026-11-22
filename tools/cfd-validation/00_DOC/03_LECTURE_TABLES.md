# Test de lecture de table

## 1. La question

Un code aérodynamique tabulé fait d'abord une chose : **lire ses tables**.
Avant de juger une interpolation, un report de moments ou une logique de
domaine, il faut établir que, posé sur un nœud, le code rend la valeur qui est
dans la table. Ce test l'établit pour toutes les tables, à toutes les
dimensions, nœud par nœud.

Ce qu'il détecte :
- une table **transposée** (indices permutés dans l'appel) ;
- une **grille décalée** (une grille pour une autre) ;
- une **mauvaise table** (CY lue à la place de CN) ;
- une valeur **altérée** dans le source ;
- une lecture qui **dépend d'une entrée** qu'elle ne devrait pas regarder ;
- une table que le code **ne lit jamais** dans les conditions déclarées.

Ce qu'il ne détecte pas : une erreur d'interpolation **entre** les nœuds. Sur
un nœud, les poids d'interpolation valent 0 ou 1, et c'est ce qui rend la
réponse exacte. L'entre-nœuds est un autre test.

## 2. L'oracle et la sonde

**L'oracle est la table elle-même**, lue là où le code la lit : dans le
`COMMON` que remplit le `BLOCK DATA`, exposé par f2py (`modele.lire("aertab.tcx")`).
Pas de copie dans un fichier à part, qui pourrait diverger du code testé.

**La sonde** est la valeur que le code a lue, recopiée juste après la lecture,
avant toute transformation (incrément propulsif, gouvernes, report des
moments au CDG) :

```fortran
      CX = INTE2D(TMACH, NM, ISATU, TALPHA, NA, IEXTR, TCX, NM,
     &            MACH, ALPHA, IS)
      VALID_TAB_CX = CX
```

Les sondes vivent dans un `COMMON /PROBE/` (`aero_probe.inc`). Comparer la
sortie finale ne suffirait pas : `CX` reçoit ensuite l'incrément propulsif et
`CM` les gouvernes et le report des moments, si bien qu'une sortie juste peut
cacher une lecture fausse compensée ailleurs.

Côté Python, `ModeleF2py` (attribut `SONDES = ("probe",)`) remet chaque sonde
à **NaN avant chaque appel**, puis la rend comme une colonne de plus. Une
table que l'appel n'a pas lue donne donc NaN, pas la valeur de l'appel
précédent. Le test classe ce cas en échec (« sonde non atteinte »), jamais en
lecture juste.

## 3. Déclarer une table

```python
TableReference(
    "CX",                                          # nom (rapport, fichiers)
    modele.lire("aertab.tcx"),                     # valeurs, telles que le code les voit
    {"mach": modele.lire("aertab.tmach"),          # colonnes et grilles,
     "alpha": modele.lire("aertab.talpha")},       #   dans l'ordre des indices Fortran
    sonde="valid_tab_cx",
)
```

**Orientation.** Les axes se déclarent dans l'ordre des indices du Fortran :
`TCX(NM, NA)` → `(mach, alpha)`. f2py rend un tableau de même forme. La forme
est vérifiée : chaque axe doit avoir la taille de sa grille, et en cas d'écart
le message propose l'ordre qui irait. Sur une table **carrée**, la forme ne
peut pas trancher : (alpha, mach) passe la vérification et désigne la
transposée. C'est alors le test qui le révèle, les valeurs ne correspondant
plus.

**Ordre de lecture.** Les nœuds sont parcourus dans l'ordre mémoire du
Fortran, premier indice le plus rapide, qui est celui des `DATA`. La k-ième
valeur listée dans le source est le k-ième point de la figure et du CSV.

## 4. Des colonnes de la table aux entrées du modèle

`defauts` donne la valeur de **chaque** entrée du modèle ; ses clés sont la
liste des entrées. Pour chaque nœud, le point injecté est construit ainsi :

1. les `defauts` ;
2. les `fixes` de la table (`{"ipropu": 1}` : une table de propulsion n'est
   lue que propulsion allumée) ;
3. les colonnes de la table :
   - **directement**, quand une colonne porte le nom d'une entrée ;
   - sinon par **`vers_entrees`**, la relation inverse de celle du code.

Une colonne qui n'est pas une entrée, sans `vers_entrees`, est refusée et
nommée.

```python
# Table en (mach, alphat, phia, dm, dn) ; le code calcule
#   cos(alphaT) = cos(alpha)·cos(beta),  phiA = atan2(sin(beta), sin(alpha)·cos(beta))
def polaire_vers_cartesien(df):
    at, phi = np.radians(df["alphat"]), np.radians(df["phia"])
    return {"alpha": np.degrees(np.arctan(np.tan(at) * np.cos(phi))),
            "beta":  np.degrees(np.arcsin(np.sin(at) * np.sin(phi)))}

# Variante simple : table en (mach, alphat), sans azimut
vers_entrees=lambda df: {"alpha": df["alphat"], "beta": 0.0}
```

Un aller-retour par des fonctions transcendantes ne retombe pas au bit près
sur le nœud. La table 5D de l'exemple sort à 13 ULP au plus, et sa tolérance
(`rtol=1e-12`) est déclarée **avec sa justification**. Le rapport distingue
toujours une tolérance par défaut d'une tolérance déclarée.

**Piège de l'axe singulier.** À alphaT = 0, phiA n'est pas défini : le code y
calcule phiA = 0 quel que soit le nœud. La table doit donc y être
indépendante de phiA. La table de l'exemple est générée ainsi, et le test le
vérifie de fait : un nœud (alphaT = 0, phiA = 90) relit la valeur en phiA = 0.

## 5. Combinaisons : la lecture dépend-elle d'autre chose ?

```python
combinaisons={"alpha": [-5, 0, 5], "beta": [-5, 0, 5], "xg": [1.0, 1.4], "ipropu": [0, 1]}
```

Chaque nœud est rejoué pour toutes les combinaisons des entrées que la table
**ne pilote pas** et qui ne sont **pas fixées**. Les autres sont ignorées et
le rapport le dit. La combinaison 0 est toujours celle des défauts. Pour CX
sur (mach, alpha), on combine donc beta, xg et ipropu, et alpha est ignoré.
La lecture de CX ne doit dépendre d'aucune de ces entrées.

**Attribution.** Hors combinaison 0, le plan est un produit complet : une
entrée sans effet a le même taux d'échec pour chacune de ses valeurs. Le
rapport nomme celle dont le taux varie :

```
La lecture dépend de ipropu (échecs par valeur)  ipropu=0 : 0/882  ipropu=1 : 882/882
```

C'est ce qu'il affiche quand la sonde de CX est placée *après* l'incrément
propulsif : faute invisible aux défauts (`ipropu = 0`), révélée seulement
par les combinaisons. Quand le taux est le même partout, le rapport conclut
« lecture fausse, pas dépendance à une autre entrée ». La combinaison 0
est écartée de ce calcul : une valeur par défaut absente des valeurs combinées
(`xg = 1.2` contre `{1.0, 1.4}`) n'y apparaîtrait qu'une fois et prendrait un
taux à elle sans rien dire de l'entrée. Le journal liste en plus les échecs
par combinaison (les 12 premières).

**Éprouvé sur le vrai code** : trois fautes injectées dans le Fortran, chacune
dans une copie compilée à part.

| Faute injectée | Défauts seuls | Avec combinaisons |
|----------------|---------------|-------------------|
| CY lue avec la grille d'alpha au lieu de celle de beta | CY non conforme, 42/49 (justes : β = 0, où les deux grilles coïncident) | idem, « lecture fausse » |
| sonde de CX écrite après l'incrément propulsif | **conforme** | CX non conforme, « dépend de ipropu » |
| DM et DN permutés à l'appel de la table 5D | DCMG non conforme, 2 500/3 125 (justes : DM = DN) | idem, « lecture fausse » |

Coût : le produit des valeurs, multiplié par le nombre de nœuds. Le rapport
l'annonce (« Comb. », « Appels »).

## 6. Critère

`|code − table| ≤ atol + rtol·|table|`, la table étant l'oracle. Par défaut,
`rtol = atol = 0` : **identité bit pour bit**, justifiée par les poids
d'interpolation exacts sur un nœud. Une sonde NaN contre une valeur finie est
`NON_FINI`, d'écart infini. Mesures par appel : écart signé, ULP, marge
(écart en unités de tolérance), statut. Ce sont les mêmes fonctions que le test
d'intégration (`core/ecarts.py`).

## 7. Pièces

| Pièce | Contenu |
|-------|---------|
| `lecture_tables.log` | Le rapport complet, écrit en dernier, avec le SHA-256 de chaque autre pièce. Identification (versions, empreinte du contenu de chaque table), spécification, résultats, **tous** les points en échec, verdict. |
| `resume.json` | Le même, en types JSON. |
| `TABLES/<NOM>.csv` | La table de référence à plat : colonnes des axes, `valeur`, en ordre de lecture. |
| `RESULTATS/<NOM>.csv` | Un appel par ligne : `noeud`, `combinaison`, colonnes de la table, entrées injectées, `valeur_TAB`, `valeur_CODE`, `ecart`, `ulp`, `marge`, `statut`, `conforme`. 17 chiffres significatifs : relu exactement. |
| `FIGURES/synthese_tables*.svg` | Un panneau par table, six par page. SVG seul par défaut (`formats=("png", "pdf")` pour d'autres). |

Les coordonnées d'un point en échec tiennent dans **une** colonne
(`mach=0.95  alpha=5`) : le rapport garde la même largeur en 2D qu'en 5D.

## 8. Lire la figure

- **x** : rang du nœud dans l'ordre de lecture ; **y** : la grandeur.
- **Points bleus** : la table. **Croix vermillon** : le code, pour toutes les
  combinaisons, au rang de leur nœud. Les croix sont toujours **au-dessus**,
  plus petites que les points : chacune garde un liseré bleu, si bien qu'on
  voit les deux même quand ils coïncident, et une croix sans liseré s'écarte.
  Une lecture invariante pose la même croix à chaque combinaison : seuls les
  couples (nœud, valeur lue) distincts sont tracés.
- **Traits verticaux** : changements de l'axe le plus lent (le dernier),
  étiquetés en tête par sa valeur. En 2D, ce sont les colonnes de la table ; en
  5D, les grands blocs, à l'intérieur desquels on devine les suivants.
- **Cercle noir** : hors tolérance. **Triangle au pied** : sonde non atteinte.
- Au-delà de 2 000 marqueurs, le nuage est tramé (une image dans le SVG) pour
  que le fichier reste léger ; axes et texte restent vectoriels. Les cercles
  « hors tolérance » rapetissent quand ils sont des milliers, pour ne pas
  former une tache.

## 9. API

```python
from cfd_validation import TableReference, valider_lecture_tables

res = valider_lecture_tables(
    tables, evaluer=modele.calcul_aero_elementaire, defauts=DEFAUTS,
    combinaisons=None, identifiant="VAL-TAB-01", metadonnees={...},
    sortie="LECTURE_TABLES", figures=True, nettoyer=False,
)
res.conforme, res.verdict, res.tables[0].echecs()
```

`evaluer` est n'importe quelle fonction `DataFrame → DataFrame` : une ligne
par point, colonnes = les entrées, rendue dans le même ordre avec les colonnes
de sonde. Le test ne sait rien de f2py. `relire_tables` fait le même calcul
sans rien afficher ni écrire.

Exemple complet : `src/cfd_validation/01_EXEMPLE/MODELE_AERO/VALIDATION/01_LECTURE_TABLES/01_lecture_tables.py`,
lancé avec les autres tests par `VALIDATION/RUN_VALIDATION.sh`, qui écrit le
récapitulatif `SORTIE/RECAP.txt`.
