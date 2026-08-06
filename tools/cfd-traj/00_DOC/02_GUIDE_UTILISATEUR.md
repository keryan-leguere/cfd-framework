# Guide d'utilisation

> Ce document explique **comment se servir de cfd-traj**. Pour comprendre ce
> qu'il calcule, voir [01_METHODE.md](01_METHODE.md).

## 1. Installation

`cfd-traj` dépend de `cfd-atm`, paquet frère de ce dépôt qui porte le modèle
d'atmosphère. Ce n'est pas une publication PyPI : il faut donc l'installer
d'abord, à la main.

```bash
cd tools/cfd-traj
python -m venv .venv && . .venv/bin/activate

pip install -e ../cfd-atm      # dépendance dure
pip install -e ../cfd-plot     # optionnel : figures stylées
pip install -e ".[dev]"
```

Un environnement virtuel dédié n'est pas une précaution de style : les paquets
frères exigent `matplotlib >= 3.8`, souvent plus récent que le Python système.

Sans `cfd-plot`, tout fonctionne — les figures sont simplement rendues en
Matplotlib nu.

## 2. Les six commandes

```
cfd-traj generer      produire un lot de trajectoires synthétiques
cfd-traj inspecter    comprendre ce qu'il y a dans les fichiers
cfd-traj analyser     construire l'enveloppe conditionnelle
cfd-traj doe          en tirer un plan d'expériences
cfd-traj couverture   vérifier que le plan couvre bien les trajectoires
cfd-traj example      copier l'exemple prêt à l'emploi
```

Le chemin le plus court pour se faire une idée :

```bash
cfd-traj example --output /tmp/essai
cd /tmp/essai && bash RUN_EXEMPLE.sh
```

### Codes de retour

| Code | Signification |
|---:|:---|
| `0` | succès ; des avertissements jaunes ont pu être affichés |
| `1` | erreur d'entrée — panneau rouge nommant le fichier et le problème |
| `2` | la commande a abouti mais **le résultat exige une action** : couverture incomplète, plan dépassant le plafond de nœuds |

Le code `2` n'est pas une panne. C'est un résultat qu'il faut lire.

## 3. Le déroulé type

### 3.1 Comprendre le lot

```bash
cfd-traj inspecter TRAJECTOIRES --proposer
```

Sort les statistiques par colonne, les corrélations les plus fortes, et la
**dimension intrinsèque** du nuage. Cette dernière est le diagnostic à regarder
en premier : si elle est nettement inférieure au nombre de variables, le
conditionnement au Mach capture bien les corrélations et la méthode est sur du
solide.

`--proposer` affiche le bloc `parametres:` prêt à coller dans l'étude. **À
faire systématiquement** : les rôles auto-détectés sont une heuristique, et
elle se trompera. Les figer explicitement transforme une devinette en décision
documentée.

### 3.2 Écrire l'étude

Un seul fichier YAML décrit le lot et le plan qu'on veut en tirer. Il se commite
à côté des CSV, se diffe, et se relit ligne par ligne en revue. Voir
[03_FORMAT_ENTREE.md](03_FORMAT_ENTREE.md).

### 3.3 Analyser

```bash
cfd-traj analyser ETUDE.yaml --figure SORTIE/enveloppe.png --csv SORTIE/enveloppe.csv
```

Sort le tableau d'enveloppe — une dizaine de lignes, vérifiables une par une par
un mécanicien du vol — et la figure du nuage montrant le tube réel à l'intérieur
de l'hyperrectangle qu'il remplace.

Le rapport rappelle aussi, en évidence, **ce que le groupe de symétrie déclaré
implique**. C'est délibéré : le code ne peut pas détecter un groupe déclaré à
tort, et l'erreur ampute le plan de moitié.

### 3.4 Produire le plan

```bash
cfd-traj doe ETUDE.yaml --sortie SORTIE/PLAN.csv --excel --figure SORTIE/plan.png
```

Une ligne par cas de calcul : les valeurs de chaque variable, le jeu de
braquages, la configuration de calcul, son coût relatif, les composantes nulles
par théorème.

`--excel` produit le **classeur de revue** : quatre feuilles — `Synthèse`,
`Plan de calcul`, `Enveloppe`, `Paramètres` — en français, filtres et volets
figés posés, mise en page d'impression prête. Sans valeur, il est écrit à côté
du CSV avec l'extension `.xlsx` ; avec une valeur, à l'emplacement indiqué.
C'est ce fichier qu'on pose sur la table en revue de définition.

Les cellules y restent **numériques** : le tableau se trie, se filtre et se
calcule. Ce sont les formats de nombre d'Excel qui donnent la virgule décimale
et l'espace des milliers, sur un poste français comme ailleurs.

Si le plan dépasse `doe.noeuds_max`, la commande s'arrête en code 2 **avant
d'allouer quoi que ce soit** et propose les deux issues :

```bash
cfd-traj doe ETUDE.yaml --methode lhs      # hypercube latin, borné par bande
```

ou rétrograder des colonnes en `discret` ou `ignore` dans l'étude.

### 3.5 Vérifier

```bash
cfd-traj couverture ETUDE.yaml --csv SORTIE/hors_domaine.csv --pires 20
```

Rejoue toutes les trajectoires à travers l'enveloppe. Le pourcentage n'est pas
la sortie importante : la **liste nommée** des tirs et instants fautifs l'est.
Chacun est un point que la base devra extrapoler.

## 4. Lire les rapports

### Le rapport d'enveloppe

Une ligne par bande de Mach, une colonne par variable. Les plages mécaniques
sont rappelées une seule fois en tête : elles sont identiques dans toutes les
bandes par construction, et les répéter noierait le tableau.

Ce qu'il faut y regarder : **les bornes d'une bande sont-elles nettement plus
serrées que les bornes globales ?** Si oui, le conditionnement paie. La figure
répond visuellement, panneau de droite.

### Le rapport de plan

```
1 737 cas de calcul   méthode « tensoriel »

coût total           1 351,0 équivalents configuration complète
sans les symétries   1 737,0
économie             22,2 %
```

Le coût total est le chiffre à retenir : c'est le budget de simulation réel,
une fois que chaque cas est calculé sur le plus petit domaine que sa symétrie
autorise. L'économie est ce que les symétries ont rapporté.

### Le rapport de couverture

Le taux global, puis le taux par bande, puis les variables fautives, puis les
points les plus éloignés — dans cet ordre, du plus synthétique au plus
actionnable.

## 5. Que faire quand la couverture n'est pas de 100 %

Dans l'ordre de préférence :

1. **Regarder les points fautifs.** Sont-ils concentrés sur un tir ? Sur une
   phase de vol ? Un excès de 0,01 sur une variable n'a pas le même sens qu'un
   excès de 2,0.
2. **Élargir la marge** (`enveloppe.marge`) si les dépassements sont marginaux.
   C'est exactement ce à quoi elle sert.
3. **Desserrer les quantiles** vers `0` / `1` si le lot est petit et qu'on veut
   la garantie stricte. La couverture devient alors 100 % par construction, au
   prix d'un domaine tiré par les tirages extrêmes.
4. **Ajouter des nœuds localement** en subdivisant la bande concernée.
5. **Documenter l'exception** si le point sort pour une raison connue et
   acceptée.

Ce qu'il ne faut pas faire : lire « couverture 99,7 % » et hausser les épaules.

## 6. Réglages qui comptent

| Clé | Effet | Quand y toucher |
|:---|:---|:---|
| `bandes.bornes` | découpage du Mach | dès que les régimes sont connus — préférable au mode automatique |
| `enveloppe.marge` | élargissement des bornes | si la couverture manque de peu |
| `symetrie.groupe` | tout le gain de symétrie | une fois, au début, en connaissance de cause |
| `doe.noeuds_max` | garde-fou d'explosion | le laisser bas et réagir quand il se déclenche |
| `parametres.<col>.role` | ce que devient chaque colonne | systématiquement, après `inspecter --proposer` |

## 7. Dépannage

**« colonne(s) requise(s) absente(s) »** — un des fichiers n'a pas les huit
colonnes obligatoires. Le message nomme le fichier et les colonnes.

**« colonnes incohérentes avec … »** — deux fichiers du lot n'ont pas le même
jeu de colonnes. Le message donne le delta dans les deux sens.

**« une seule colonne détectée »** — le CSV utilise `;` comme séparateur ou la
virgule décimale. Le format attendu est la virgule séparatrice et le point
décimal.

**« nom(s) de colonne réservé(s) au calcul »** — une colonne s'appelle comme une
grandeur dérivée (`alpha_tot`, `Re_ref`, `q_inf`…). Renommez-la.

**« le plan demanderait N nœuds »** — voir §3.4.

**Le plan avale son propre résultat** — si `etude.source` est un répertoire et
que la sortie va dans ce même répertoire, le plan écrit y sera relu comme un
tir. Utilisez un motif (`TRAJECTOIRES/tir_*.csv`) ou un répertoire de sortie
distinct ; c'est ce que fait `cfd-traj generer`.
