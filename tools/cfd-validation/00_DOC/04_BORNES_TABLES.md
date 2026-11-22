# Test des bornes de table

## 1. La question

Un code tabulé finit toujours par être appelé en dehors de ses tables : un
Mach plus élevé que le dernier tabulé, une incidence au-delà de la polaire. Ce
qu'il fait alors est une **exigence**, pas un détail d'implémentation. Il peut
saturer (rendre la valeur au bord) ou extrapoler (prolonger la dernière maille),
et pas forcément de la même façon selon l'axe et le côté. Ce test vérifie, pour
chaque table, chaque axe et chaque côté, que le code fait ce que la consigne
déclarée demande.

Il complète le test de lecture de table, il ne le remplace pas. Sur les nœuds,
saturer ou extrapoler ne change rien ; un code qui extrapole mal passe la
lecture sans broncher (vérifié : § 7).

## 2. Déclarer les consignes

La consigne fait partie de la déclaration de la table (`TableReference`),
partagée par les deux tests :

```python
TableReference("CX", ..., bornes={"mach": "sature", "alpha": "extrapole"})
TableReference("DCMG", ..., bornes={
    "mach": "sature",
    "alphat": ("inatteignable", "extrapole"),   # (côté min, côté max)
    "phia": "inatteignable",
    "dm": "sature", "dn": "sature",
})
```

| Consigne        | Ce que le code doit rendre au-delà de la borne            |
|-----------------|-----------------------------------------------------------|
| `sature`        | la valeur au bord de la grille                            |
| `extrapole`     | le prolongement linéaire de la dernière maille            |
| `inatteignable` | rien : aucune entrée du modèle ne produit ce point        |

`inatteignable` existe parce qu'une colonne de table n'est pas toujours une
entrée. alphaT = acos(cos α · cos β) n'est jamais négatif, et phiA = atan2(…)
ne sort jamais de [−180°, 180°]. Appeler le code « à alphaT = −2° » n'a pas de
sens : l'inversion rendrait un α, β que le code transformerait en alphaT = +2°,
et le test échouerait sur un faux problème. Le côté est déclaré, non testé, et
le rapport le dit.

Un axe non déclaré prend `consigne_defaut` (`sature`), marquée d'un `*` au
rapport : une consigne par défaut n'est pas une exigence vérifiée.

## 3. Les points

Pour chaque **face** (un axe, un côté), l'axe est placé à
`ecart × (max − min)` au-delà de la borne (10 % par défaut, `ecarts={"alpha":
0.25}` par axe). Les autres axes parcourent **tous** leurs nœuds, en ordre de
lecture Fortran. C'est la face de la table, déplacée vers l'extérieur :

| Table | Faces | Points par face | Appels |
|-------|-------|-----------------|--------|
| 2D 7×7 | 4 | 7 | 28 |
| 1D 7 | 2 | 1 | 2 |
| 5D 5⁵ | 10, dont 3 inatteignables | 625 | 4 375 |

Une fraction de l'**étendue**, et non de la borne : « 10 % de la borne » n'a
pas de sens pour α ∈ [−20°, 20°] (−22° ? −18° ?), ni pour une borne nulle.

Les autres axes restent sur leurs nœuds : la seule chose qui sort de la grille
est l'axe de la face, si bien qu'un échec se localise à une face.

## 4. L'oracle et l'observé

**Attendu.** L'interpolation multilinéaire de la table, avec la règle de bord
de chaque axe (`core/bornes.interpoler`). Pour chaque axe, `(i, t)` donne la
position du point dans sa grille ; au-delà de la grille, `t` est borné à 0 ou 1
(saturation) ou laissé hors de [0, 1] (extrapolation). C'est la formule du code,
refaite à partir de la table elle-même. Vérification indépendante : sur une
table tirée d'une fonction multilinéaire, l'extrapolation rend la fonction
exacte.

**Observé.** Chaque face est aussi comparée aux **deux** consignes possibles.
Le rapport dit ce que le code fait réellement :

| Observé | Sens |
|---------|------|
| `sature` / `extrapole` | le code fait cela, sur tous les points de la face |
| `indiscernable` | la dernière maille est plate : les deux consignes donnent la même valeur |
| `ni l'un ni l'autre` | autre chose (mauvaise maille, mauvais axe…) |
| `sonde non atteinte` | la sonde est restée NaN |

« attendu extrapole, observé sature » se lit sans ouvrir un CSV.

## 5. Critère

`|code − attendu| ≤ atol + rtol·|attendu|`. Si la table déclare une tolérance,
c'est la sienne. Sinon :

- face saturée : **identité bit pour bit**, le code relit un nœud ;
- face extrapolée : `rtol = 1e-12`, `atol = 1e-15`, car l'oracle refait le
  calcul du code mais pas forcément dans le même ordre d'opérations.

Les deux sont des défauts, marqués comme tels au rapport. Sur le modèle
d'exemple, toutes les faces 2D sortent identiques au bit près, extrapolées
comprises.

## 6. Pièces et figure

| Pièce | Contenu |
|-------|---------|
| `bornes_tables.log` | Le rapport complet : identification, consignes de chaque axe et de chaque côté (`*` = défaut), tolérances justifiées, résultats par face (attendu, observé), tous les points en échec, verdict, SHA-256 des pièces. |
| `resume.json` | Le même, en types JSON. Les clés `tables[].nom / appels / echecs / conforme` sont celles que lit le récapitulatif de `VALIDATION/`. |
| `RESULTATS/<NOM>.csv` | Un appel par ligne : `face`, `point`, `consigne`, colonnes de la table, entrées injectées, `valeur_ATTENDUE`, `valeur_SATURATION`, `valeur_EXTRAPOLATION`, `valeur_CODE`, `ecart`, `ulp`, `marge`, `statut`, `conforme`. |
| `FIGURES/synthese_bornes*.svg` | Un panneau par table, six par page. |

**Figure.** En x, les points hors bornes face après face, chaque face
séparée par un trait et étiquetée en tête (`alpha+ E`, en vermillon si elle
échoue). En y, la grandeur :

- les **points bleus** donnent la valeur attendue ;
- les **cercles gris** donnent celle de l'*autre* consigne ;
- les **croix vermillon** donnent le code, au-dessus, plus petites que les points ;
- un **anneau noir** marque un point hors tolérance.

Quand le code ne suit pas la consigne, ses croix tombent sur les cercles gris.

## 7. Éprouvé sur le vrai code

Le modèle d'exemple a des consignes mixtes : saturation en Mach, braquages et
propulsion ; extrapolation en α, β et alphaT (`DOC/01_SOURCES.md`). Trois
scénarios :

| Scénario | Résultat |
|----------|----------|
| code livré | 33 faces conformes, 3 inatteignables, 4 545 appels |
| consigne d'α de CX déclarée `sature` (`--defaut`) | CX α− et α+ : « attendu sature, observé extrapole », 7/7 |
| faute dans `CHERCH` : le côté haut ignore la consigne et sature toujours | les 7 faces hautes extrapolées échouent, « observé sature » ; les faces basses et saturées restent conformes. **Le test de lecture reste conforme** : sur les nœuds, la faute ne se voit pas. |

## 8. API

```python
from cfd_validation import valider_bornes_tables

res = valider_bornes_tables(
    tables, evaluer=modele.calcul_aero_elementaire, defauts=DEFAUTS,
    ecart=0.10, ecarts=None, consigne_defaut="sature",
    identifiant="VAL-TAB-02", metadonnees={...}, sortie="BORNES_TABLES",
)
res.conforme, res.motifs_non_conformite, res.tables[0].faces
```

`verifier_bornes` fait le même calcul sans rien afficher ni écrire. Exemple
complet : `src/cfd_validation/01_EXEMPLE/MODELE_AERO/VALIDATION/02_BORNES_TABLES/02_bornes_tables.py`.
