# Capture automatique des données pilotes

> Objectif : supprimer la saisie manuelle. À partir d'un cas **prêt à lancer**,
> `cfd-perf capture` lance les runs pilotes, extrait temps/itérations/RAM,
> renseigne la machine, génère un fichier d'étude validé, et recommande — sans
> pilote à relever ni YAML à écrire à la main.

## 1. Le flux en deux phases

Les runs HPC attendent en file : la capture est donc **découplée** en deux
commandes. On soumet tout, on revient plus tard collecter.

```
   ┌─ Phase 1 : soumission ──────────────────────────────────────┐
   │  cfd-perf capture --coeurs "48 96 192 384" \                │
   │      --adaptateur OF --queue normal --case-dir .            │
   │                                                            │
   │   pour chaque nombre de cœurs :                            │
   │     • crée PILOTE/<adaptateur>_<cœurs>_<horodatage>/       │
   │     • copie les entrées (adapt_liste_elements_a_copier)    │
   │     • prépare (adapt_pilote_preparer)                      │
   │     • soumet (adapt_pilote_soumettre) → identifiant de job │
   │   écrit PILOTE/manifest.json, puis rend la main            │
   └────────────────────────────────────────────────────────────┘
                          (les jobs tournent sur le calculateur)
   ┌─ Phase 2 : collecte ────────────────────────────────────────┐
   │  cfd-perf capture --collect --case-dir . --figure scal.png │
   │                                                            │
   │   • relit le manifeste, vérifie l'état de chaque run       │
   │       ↳ si certains tournent encore : les liste, code 3   │
   │   • extrait temps_total / nb_itérations / RAM crête       │
   │       time_per_iter_s = temps_total / nb_itérations       │
   │   • détecte la machine, écrit ETUDE.yaml (validé)         │
   │   • lance la recommandation (rapport + figure)            │
   └────────────────────────────────────────────────────────────┘
```

Avec l'adaptateur **mock**, la « soumission » s'exécute de façon synchrone et le
run est aussitôt terminé : on peut enchaîner soumission puis `--collect`.

### Essayer tout de suite (sans solveur)

```bash
mkdir -p /tmp/cas_demo/AILE_M6
cfd-perf capture --coeurs "8 16 32 64 128" --adaptateur mock --case-dir /tmp/cas_demo/AILE_M6
cfd-perf capture --collect --case-dir /tmp/cas_demo/AILE_M6 --figure /tmp/cas_demo/AILE_M6/scal.png
```

## 2. Ce qui est renseigné automatiquement

| Champ d'étude | Source automatique | Surcharge |
|:---|:---|:---|
| `study.name` | nom du répertoire du cas | — |
| `study.n_iterations` | `adapt_cible_iterations` (**placeholder** `sed`) | `--n-iterations` |
| `mesh.num_cells` | `adapt_maillage_nb_cellules` | `--num-cells` |
| `pilot[*]` | temps/itér + RAM crête mesurés par run | — |
| `machine.*` | détection auto → `hotes.yaml` → défauts | `--cores-per-node`, `--ram-per-node`, `--max-nodes`, `--max-walltime` |
| `objective.*` | défauts cfd-perf | `--strategy`, `--max-efficiency-loss`, `--deadline`, `--cores-max` |

> **Deux placeholders assumés** (v1) : `study.n_iterations` (itérations de
> production, pas celles du pilote) et `mesh.num_cells` reposent sur des
> fonctions d'adaptateur volontairement simples. Vérifiez-les, ou passez
> `--n-iterations` / `--num-cells`.

## 3. Détection de la machine

`--collect` renseigne la section `machine` par ordre de priorité décroissante :

1. **options CLI** (`--cores-per-node`, `--ram-per-node`, `--max-nodes`, `--max-walltime`) ;
2. **détection automatique** : `scontrol show node $(hostname)` (`CPUTot`,
   `RealMemory`), sinon `nproc` et `/proc/meminfo` ;
3. **`ADAPTATEUR/hotes.yaml`**, indexé par nom d'hôte (le préfixe le plus long
   qui matche) ;
4. la clé **`defaut`** de `hotes.yaml` ;
5. les **valeurs par défaut** de cfd-perf (`cores_per_node = 1`).

Toutes les commandes système sont protégées : hors calculateur, la détection
échoue en silence et on retombe sur les niveaux suivants. Renseignez vos
machines dans `ADAPTATEUR/hotes.yaml` pour un résultat fiable partout.

## 4. RAM crête (SLURM)

La RAM crête **totale** (ce que consomme le modèle mémoire) est lue après le run
par l'implémentation par défaut de `ADAPTATEUR/interface.sh` :

```
sacct -j <job_id> --format=MaxRSS,NTasks -P
total = MaxRSS (par tâche) × NTasks   → converti en Go (base 1024)
```

Hors SLURM (job « LOCAL », ou `sacct` absent), la fonction renvoie une valeur
vide → la RAM n'est pas mesurée et les contraintes mémoire sont simplement
ignorées (le reste de la recommandation fonctionne). Un adaptateur peut
surcharger `adapt_pilote_ram_crete` (le mock le fait avec une valeur synthétique).

## 5. Le contrat d'adaptateur

Chaque adaptateur est un script bash **autonome** de `ADAPTATEUR/` qui source
`interface.sh` et implémente :

| Fonction | Arguments | Écrit sur stdout / renvoie |
|:---|:---|:---|
| `adapt_nom` | — | identifiant (ex. `OF`) |
| `adapt_verifier_installation` | — | code 0 si le solveur est là |
| `adapt_liste_elements_a_copier` | — | éléments à copier (un par ligne) |
| `adapt_pilote_preparer` | `run_dir cores` | prépare le cas pour N cœurs |
| `adapt_pilote_soumettre` | `run_dir cores [queue]` | identifiant de job (`LOCAL` si synchrone) |
| `adapt_pilote_etat` | `run_dir job_id` | `PENDING`/`RUNNING`/`DONE`/`FAILED` |
| `adapt_pilote_temps_total` | `run_dir` | temps solveur total (s) |
| `adapt_pilote_nb_iterations` | `run_dir` | itérations effectuées (entier) |
| `adapt_pilote_ram_crete` | `run_dir job_id` | RAM crête totale (Go) — défaut SLURM |
| `adapt_maillage_nb_cellules` | `case_dir` | nombre de mailles (entier) |
| `adapt_cible_iterations` | `case_dir` | `study.n_iterations` (placeholder `sed`) |

Guide complet de rédaction : [`../ADAPTATEUR/README.md`](../ADAPTATEUR/README.md).
Modèles fournis : `mock.sh` (simulé, testable) et `OF.sh` (OpenFOAM, référence).

## 6. Codes de sortie

| Code | Sens |
|---:|:---|
| 0 | succès (soumission, ou collecte + recommandation) |
| 2 | collecte réussie mais **aucune configuration réalisable** |
| 3 | collecte : **des runs ne sont pas terminés** (relancez `--collect` plus tard) |
| 1 | erreur (cas introuvable, adaptateur introuvable, manifeste absent, YAML invalide…) |

## 7. Limites (v1)

- **Un run par nombre de cœurs.** Pour moyenner des répétitions, relancez la
  soumission : les points de mêmes cœurs sont automatiquement moyennés à la
  collecte.
- `OF.sh` et les chemins SLURM ne sont pas testés ici (pas d'OpenFOAM/SLURM) :
  ils servent de référence à adapter à votre installation.
- Le manifeste (`PILOTE/manifest.json`) relie les deux phases : ne le déplacez
  pas entre soumission et collecte.
