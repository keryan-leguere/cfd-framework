# 02 — Le test d'intégration

> Le même code, exécuté dans deux environnements, donne-t-il les mêmes sorties ?

**Référence** : le code exécuté là où il est validé. **Test** : le même code
exécuté ailleurs (autre machine, autre compilateur ou options, intégré à un
workflow). Les deux tables ont les mêmes colonnes : des **entrées**, qui
identifient un cas, et des **sorties**, qu'on compare.

```python
from cfd_validation import valider_integration

res = valider_integration(
    reference, test,
    entrees=["Mach", "alpha", "beta"],
    sorties=["CN", "CA", "Cm"],
    rtol=1e-9, atol=1e-12, justification="changement de compilateur : quelques ULP",
    tolerances={"Cm": {"rtol": 1e-8, "justification": "compensation de moments"}},
    identifiant="INT-01",
    metadonnees={"code": "aero v3.2", "commit": "a1b2c3", "compilateur": "gfortran 13 -O2"},
    sortie="VALIDATION/INT-01",
)
res.conforme        # booléen
res.lignes          # DataFrame : une ligne par cas
res.ecarts          # DataFrame : une ligne par (cas × sortie)
```

```bash
cfd-validation integration REF.csv TEST.csv --config INTEGRATION.yaml -o VALIDATION/INT-01
echo $?             # 0 conforme, 1 erreur d'entrée, 2 non conforme
```

## 1. Appariement des lignes

Par défaut, une ligne de test correspond à la ligne de référence qui a **les
mêmes valeurs d'entrée** : l'ordre peut différer, des cas peuvent manquer
(plantage) ou être en trop. Les entrées numériques sont comparées en double
précision (`2` apparie `2.0`, `-0.0` apparie `0.0`).

- `chiffres_cle=6` arrondit les entrées à 6 chiffres significatifs avant
  appariement, quand l'autre environnement les écrit tronquées.
- Une combinaison d'entrées répétée est appariée dans l'ordre d'apparition,
  et signalée : c'est presque toujours une entrée non déclarée.
- `alignement="position"` apparie la i-ème ligne avec la i-ème. Les entrées
  sont alors **vérifiées** : une paire aux entrées différentes n'est pas
  comparée, elle est déclarée « entrées divergentes ».
- `renommage_test={"cn": "CN"}` corrige des noms de colonnes différents.

## 2. Critère

Une valeur testée `t` est acceptée contre sa référence `r` si

    |t − r| ≤ atol + rtol·|r|

C'est le critère de `numpy.isclose`, **asymétrique** à dessein : la référence
est l'oracle et fixe l'échelle. Les cas particuliers :

| Référence | Test | Statut |
|---|---|---|
| `x` | `x` (bit pour bit) | **identique** |
| `x` | dans la tolérance | **dans la tolérance** |
| `x` | hors tolérance | **hors tolérance** |
| `NaN` | `NaN` | identique (le comportement n'a pas changé) |
| `x` | `NaN` ou `±inf` | **non fini divergent**, marge infinie |
| colonne texte | | égalité stricte |

`rtol = atol = 0` exige l'identité bit pour bit, ce qu'on peut viser quand
seul le workflow change (même binaire, même machine).

**Choisir la tolérance.** Un changement de compilateur ou d'options déplace
une sortie de quelques ULP (≈ 1e-16 en relatif) tant que le code n'accumule
pas d'erreur. Une sommation réordonnée (OpenMP, MPI) peut en coûter beaucoup
plus sur une somme à termes compensés. Le paquet ne choisit pas pour vous :
la valeur par défaut (`rtol = 1e-9`, `atol = 1e-12`) est **signalée comme non
justifiée** dans le rapport.

## 3. Mesures

Pour chaque valeur : `ecart = t − r`, `ecart_rel = |Δ|/|r|`, `ulp` (nombre
de flottants double précision entre `r` et `t`), et la **marge**.

### La marge

    marge = (test − réf) / (atol + rtol·|réf|)

Le dénominateur est l'**écart autorisé** en ce point ; la marge est donc
l'écart constaté **exprimé en nombre d'écarts autorisés**. Le critère
d'acceptation se lit directement : `|marge| ≤ 1`.

| Marge | Lecture |
|---|---|
| `0` | identique bit pour bit |
| `±1e-7` | l'écart consomme un dix-millionième de la tolérance (arrondi d'un autre compilateur) |
| `±0.5` | la moitié de la tolérance est consommée : conforme, mais à surveiller |
| `±1` | exactement à la limite, encore accepté |
| `2e5` | 200 000 fois l'écart autorisé : une régression |
| `inf` | un côté NaN ou infini : aucun seuil ne l'admet |

Le signe dit le sens : positif, le test est au-dessus de la référence.

Exemple, tiré de l'exemple livré : Cm vaut `−0.579790` en référence et
`−0.580950` en test, avec `rtol = 1e-8`, `atol = 1e-12`. Écart
`Δ = −1.16e-3`, écart autorisé `1e-12 + 1e-8 × 0.5798 = 5.8e-9`, marge
`−1.16e-3 / 5.8e-9 ≈ −2.0e5`.

Pourquoi elle plutôt que l'écart relatif : les sorties n'ont ni les mêmes
unités ni les mêmes tolérances (un `CY` nul par symétrie ne supporte aucun
écart relatif, un `Cm` à compensation en supporte davantage). La marge les
ramène toutes à une même échelle, où 1 est la frontière : c'est elle qu'on
trace, qu'on trie et qu'on compare d'une sortie à l'autre. Pour une ligne,
« marge » désigne la plus grande |marge| de ses sorties.

Par sortie : les comptes de chaque statut, les maxima, le **biais** (moyenne
de Δ : un bruit d'arrondi est centré, une constante fausse ne l'est pas), le
RMS, et le **point le plus éloigné** de la référence, avec ses entrées.

## 4. Attribution aux entrées

Une régression frappe rarement au hasard : elle suit une branche du code,
donc une plage d'entrée. Pour chaque entrée, discrétisée en niveaux (ses
valeurs si elle en a au plus 12, sinon 8 classes de quantiles), on calcule :

- le **taux d'échec par niveau**, absentes comprises (un cas qui a planté est
  l'échec le plus localisé de tous) ;
- le **V de Cramér** (niveau × échec), dans [0, 1] : 0 si l'échec ne dépend pas
  de l'entrée, 1 s'il est entièrement déterminé par son niveau. Lecture :
  ≥ 0.5 forte, ≥ 0.3 marquée, ≥ 0.1 faible.

Le rapport conclut en une phrase : *« les échecs se concentrent sur Mach ∈
{1.2, 1.5, 2} : 90.9 % des lignes y échouent, contre 0.4 % ailleurs »*, ou
*« écart diffus »* si aucune entrée ne ressort. En dessous de 30 lignes, le V
est instable : le rapport le signale, et il faut alors lire les taux par niveau.

## 5. Pièces produites

```
sortie/
├── integration.log    le rapport complet en texte : chaque ligne, chaque niveau
├── resume.json        verdict, paramètres, bilans, empreintes
├── lignes.csv         une ligne par cas : statut, sortie la pire, marge
├── ecarts.csv         une ligne par (cas × sortie) : réf, test, Δ, ULP, seuil, marge
└── FIGURES/           PNG 300 dpi + PDF, profil « paper » de cfd-plot
```

Le journal est écrit en dernier et liste la **SHA-256** de chaque autre pièce :
une figure jointe à un rapport se rattache ainsi à une exécution précise.

## 6. Lire les figures

Toutes tracent la **marge** sur un axe *symlog* : linéaire dans [−1, 1] (la
bande bleue, l'acceptation), logarithmique au-delà. Un bruit d'arrondi
s'y lit à l'échelle et une régression reste visible plus haut.

| Figure | Ce qu'elle montre |
|---|---|
| `01_synthese_sorties` | une ligne par sortie : \|marge\| de la médiane au maximum, 99e centile marqué, part identique et échecs à droite. La pièce de tête, lisible à 15, 30 ou 50 sorties (30 par page) |
| `02_marges_par_sortie` | marge contre valeur de référence, 12 sorties par page : l'écart dépend-il du niveau de la sortie ? |
| `03_repartition_marges` | fonction de répartition de \|marge\|, 7 sorties par page (une couleur chacune) ; l'ordonnée à l'origine est la part identique bit pour bit, un palier final < 1 trahit des non finis |
| `04_marges_<k>_<sortie>` | marge contre chaque entrée, l'entrée la plus liée aux échecs en premier ; par défaut **pour les seules sorties en échec** (`figures_par_entree="toutes"` ou `"aucune"`, `--figures-entrees`) |
| `05_taux_echec_par_entree` | taux d'échec par niveau, entrées les plus liées d'abord, absentes hachurées, taux global en tireté |
| `06_liaison_entrees_sorties` | V de Cramér entrée × sortie (seulement s'il y a des échecs) |

`<k>` est le rang de la sortie dans la déclaration : `CN` et `Cn` donneraient
sinon le même nom de fichier sur un disque insensible à la casse (Windows,
macOS), et l'une écraserait l'autre sans bruit.

## 7. Beaucoup d'entrées et de sorties

Vérifié sur 10 entrées × 15 sorties (`tests/test_grande_table.py`) :

- **terminal** : la table ligne à ligne montre les entrées qui tiennent dans
  la largeur, **les plus liées aux échecs d'abord**, et nomme celles qu'elle
  masque ; le point le plus éloigné n'est montré que pour les sorties en
  échec, avec ses 3 entrées les plus pertinentes. Rien n'est rogné en 80 colonnes ;
- **journal** : toujours tout. Sa largeur croît pour loger chaque colonne
  d'entrée (216 caractères pour 10 entrées) ;
- **figures** : pages de 12 panneaux (une page A4), synthèse d'une ligne par
  sortie, figures par entrée limitées aux sorties en échec.

Couleurs Okabe-Ito, lisibles en cas de daltonisme ; les statuts se distinguent
aussi par la forme du marqueur, donc en niveaux de gris.

## 8. Le fichier de configuration

Voir `01_EXEMPLE/INTEGRATION.yaml`. Clés : `identifiant`, `description`,
`entrees`, `sorties`, `alignement`, `chiffres_cle`, `renommage_test`,
`tolerances` (`defaut` et `sorties`, chacune `{rtol, atol, justification}`),
`metadonnees`. Une clé inconnue est refusée. Les options de la ligne de
commande priment sur le fichier.
