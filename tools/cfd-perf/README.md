# cfd-perf

**Sur combien de cœurs lancer ma simulation CFD ?**

Estimateur de scalabilité forte pour du RANS stationnaire. À partir de quelques
mesures pilotes de votre vrai cas, il ajuste un modèle de performance et répond
par un **nombre de nœuds demandable tel quel à l'ordonnanceur**, avec la durée,
le coût et les réserves qui vont avec.

```
╭──── Réponse  (efficacité : le plus de cœurs sans gaspiller l'allocation) ────╮
│ Lancer sur 144 cœurs  =  3 nœuds de 48 cœurs                                 │
│                                                                              │
│        Durée  5,6 h                                                          │
│         Coût  808 h·cœur                                                     │
│ Accélération  2,3× vs 48 cœurs                                              │
│   Efficacité  75 %  (25 % perdu)                                             │
│       Charge  138 889 mailles/cœur                                           │
│      Mémoire  1,03 Go/cœur                                                   │
╰──────────────────────────────────────────────────────────────────────────────╯
```

![Figure de sortie](01_EXEMPLE/SORTIE/scalabilite.png)

## Démarrage

```bash
cd tools/cfd-perf
pip install -e ".[dev]"

cfd-perf example -o mon_etude          # copie l'exemple prêt à l'emploi
cd mon_etude && ./RUN_EXEMPLE.sh       # le rejoue sous les 3 stratégies
```

Puis remplacez les mesures pilotes par les vôtres et relancez :

```bash
cfd-perf check mon_etude.yaml                             # valider + qualité du pilote
cfd-perf run   mon_etude.yaml --figure SORTIE/fig.png -v  # répondre
```

## Les trois questions

| Stratégie | Question | Réponse sur l'exemple |
|:---|:---|---:|
| `efficiency` *(défaut)* | « je ne veux pas gaspiller » | **144 cœurs** — 5,6 h, 808 h·cœur |
| `deadline` | « il me le faut dans 4 h 30 » | **240 cœurs** — 4,3 h, 1 024 h·cœur |
| `fastest` | « le plus vite possible » | **528 cœurs** — 3,5 h, 1 853 h·cœur |

Même courbe, mêmes contraintes : seule la question change la réponse.

> `fastest` n'est **jamais** « le maximum de cœurs » : la courbe a un minimum,
> au-delà duquel plus de cœurs = plus lent *et* plus cher. cfd-perf ne le
> franchit jamais.

## Organisation

```
tools/cfd-perf/
├── 00_DOC/              documentation illustrée
│   ├── 01_MODELE.md              le modèle et sa physique
│   ├── 02_GUIDE_UTILISATEUR.md   méthode, lecture des résultats
│   ├── 03_FORMAT_ENTREE.md       schéma du fichier d'étude
│   ├── FIGURES/                  illustrations (regénérables)
│   └── generer_figures.py
├── 01_EXEMPLE/          exemple prêt à l'exécution (données réalistes)
│   ├── ONERA_M6_CRUISE.yaml
│   ├── RUN_EXEMPLE.sh
│   └── SORTIE/
├── src/cfd_perf/        le paquet
│   ├── core/                modèle, mémoire, contraintes, check-point
│   ├── data/                pilote, maillage, machine, fichier d'étude
│   ├── engine/              décision : « combien de cœurs ? »
│   ├── report/              rapport Rich + figures (françaises)
│   └── cli/
└── tests/
```

> Les répertoires livrables sont en majuscules, suivant la convention du
> *framework*. `src/` et `tests/` restent en minuscules : les noms de paquets
> Python doivent être importables.

## Le modèle

```
T(Nc) = t_ser  +  t_par / Nc  +  t_comm · Nc^γ
        plancher   se divise     MPI : croît
        d'Amdahl   (on gagne)    (on perd)
```

Le troisième terme est ce qui permet de représenter la courbe en U que montre
toute machine réelle : le temps descend, atteint un minimum, puis **remonte**
quand la communication l'emporte. Sur les mesures réelles de l'exemple, il reste
à **2,5 % d'erreur max**. Détails : [00_DOC/01_MODELE.md](00_DOC/01_MODELE.md).

## Ce que l'outil vous dit toujours

- **la qualité de l'ajustement**, point de pilote par point de pilote — si la
  courbe ne suit pas vos mesures, c'est écrit en chiffres avant même la figure ;
- **quand il extrapole** hors de la plage pilote ;
- **pourquoi** une configuration a été rejetée (jamais un « rejeté » sec) ;
- **ce qu'auraient coûté** les autres stratégies.

## Développement

```bash
pip install -e ".[dev]"
pytest                  # 145 tests
ruff check src tests
mypy src
```

Dépendances : `numpy`, `matplotlib`, `rich`, `pyyaml` — toutes en *wheels*, donc
installables sur un calculateur isolé (voir le guide). Les figures utilisent la
bibliothèque interne `plotting` (`scripts/post/plot`) si elle est trouvable, avec
repli automatique sur Matplotlib nu.

## Aussi dans ce répertoire

- `checkpoint_demo.py` — intervalle optimal de check-point (`cfd_perf.core.checkpoint`).
