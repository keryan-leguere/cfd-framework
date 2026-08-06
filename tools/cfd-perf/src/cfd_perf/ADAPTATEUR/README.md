# ADAPTATEUR/ — adaptateurs de capture pilote

Un adaptateur rend la capture **solveur-agnostique** : c'est un script bash
autonome qui sait, pour *votre* code, préparer un cas, lancer un run, et lire le
temps, les itérations, la RAM crête et la taille du maillage. cfd-perf
l'orchestre (boucle sur les cœurs, machine, YAML, recommandation).

## Fichiers

| Fichier | Rôle |
|:---|:---|
| `interface.sh` | contrat + implémentations par défaut (RAM via SLURM, log) |
| `mock.sh` | solveur simulé (aucune dépendance) — sert aux tests et à la démo |
| `OF.sh` | OpenFOAM (foamRun) — **référence** à adapter |
| `hotes.yaml` | paramètres machine par hôte (repli de la détection auto) |
| `tests/test_mock_adaptateur.sh` | test bash autonome du mock |

Résolution : `cfd-perf capture --adaptateur X` cherche `ADAPTATEUR/X.sh` puis
`ADAPTATEUR/X/adaptateur.sh`.

## Écrire un adaptateur pour votre solveur

1. Copiez `mock.sh` (ou `OF.sh` si vous êtes proche d'OpenFOAM) vers
   `ADAPTATEUR/MONSOLVEUR.sh`.
2. Gardez l'en-tête qui source `interface.sh` :

   ```bash
   _ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
   source "${_ICI}/interface.sh"
   ```

3. Implémentez les fonctions du contrat (voir le tableau ci-dessous). Chacune
   **écrit son résultat sur stdout** (ou renvoie un code pour
   `adapt_verifier_installation`).
4. Testez : `cfd-perf capture --coeurs "4 8 16" --adaptateur MONSOLVEUR --case-dir .`

## Le contrat

| Fonction | Args | Sortie attendue |
|:---|:---|:---|
| `adapt_nom` | — | identifiant court (ex. `MONSOLVEUR`) |
| `adapt_verifier_installation` | — | **code** 0 si le solveur est disponible |
| `adapt_liste_elements_a_copier` | — | fichiers/dossiers à copier dans le run (un par ligne) |
| `adapt_pilote_preparer` | `run_dir cores` | prépare le cas pour N cœurs (décomposition…) ; code 0 |
| `adapt_pilote_soumettre` | `run_dir cores [queue]` | **identifiant de job** ; `LOCAL` si lancement synchrone |
| `adapt_pilote_etat` | `run_dir job_id` | `PENDING` \| `RUNNING` \| `DONE` \| `FAILED` |
| `adapt_pilote_temps_total` | `run_dir` | temps solveur total, en **secondes** |
| `adapt_pilote_nb_iterations` | `run_dir` | itérations effectuées (**entier**) |
| `adapt_pilote_ram_crete` | `run_dir job_id` | RAM crête **totale** en **Go** (défaut : SLURM `MaxRSS × NTasks`) |
| `adapt_maillage_nb_cellules` | `case_dir` | nombre de mailles (**entier**) |
| `adapt_cible_iterations` | `case_dir` | `study.n_iterations` de production (**entier**) |

`time_per_iter_s` est calculé côté Python : `temps_total / nb_iterations`.

## Règles importantes

- **Nombres à point décimal.** `interface.sh` impose `LC_ALL=C` : gardez-le, et
  laissez `awk`/`printf` produire des points (jamais de virgule décimale), car
  Python relit ces valeurs.
- **Autonomie.** Ne dépendez pas de `$CFD_FRAMEWORK`. `interface.sh` fournit des
  `_info/_warn/_error` de repli si le framework est absent (installation isolée).
- **RAM par défaut.** Ne réimplémentez `adapt_pilote_ram_crete` que si votre
  mesure diffère du `sacct MaxRSS × NTasks` fourni.
- **Placeholders.** `adapt_cible_iterations` et `adapt_maillage_nb_cellules`
  peuvent démarrer simples (un `sed`, une valeur par défaut) ; l'utilisateur peut
  toujours passer `--n-iterations` / `--num-cells`.

## Paramètres machine — `hotes.yaml`

Renseignez vos calculateurs pour que la section `machine` soit correcte même
sans SLURM. Clé = préfixe de `hostname` ; champs : `cores_per_node` (requis),
`ram_per_node_gb`, `max_nodes`, `max_walltime_hours`. Voir le fichier fourni.
