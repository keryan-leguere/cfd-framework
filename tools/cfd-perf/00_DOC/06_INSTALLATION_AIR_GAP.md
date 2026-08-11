# Installation sur calculateur isolé (air-gap)

> Cas visé : une machine **sans accès Internet** disposant déjà d'**Anaconda**
> (ou d'un Python avec `numpy`, `matplotlib`, `pandas`, `rich`, `pyyaml`). Rien
> à télécharger : on copie les sources et on installe sans toucher au réseau.

cfd-perf ne dépend que de `numpy`, `matplotlib`, `rich`, `pyyaml` — toutes dans
Anaconda — et tourne à partir de **Python 3.9**, celui des bases RHEL 8 /
Rocky 8 encore courantes sur ces machines. Les figures « style maison » viennent
du paquet compagnon **`cfd-plot`**, qui n'a besoin que de `matplotlib`, `numpy`,
`pandas` — également dans Anaconda.

`cfd-plot` est **facultatif** : sans lui, cfd-perf trace les mêmes figures en
Matplotlib brut, sans le style maison. Rien d'autre ne change.

Rien d'autre n'est requis : les adaptateurs bash et l'exemple sont **embarqués
dans le paquet** (`src/cfd_perf/ADAPTATEUR/`, `src/cfd_perf/01_EXEMPLE/`). Une
fois installé, cfd-perf ne cherche plus rien sur le disque et les sources
copiées peuvent être effacées.

## Recette

**1. Copier les sources** sur la machine isolée. Les deux paquets sont
indépendants ; seule l'installation de `cfd-plot` est en plus :

```
outils/
├── cfd-perf/   ← l'outil
└── cfd-plot/   ← la bibliothèque de tracé (facultative)
```

**2. Installer les deux paquets, sans réseau ni dépendances** (Anaconda les
fournit déjà) :

```bash
cd outils
pip install ./cfd-plot --no-deps --no-build-isolation --no-index   # facultatif
pip install ./cfd-perf --no-deps --no-build-isolation --no-index
```

| Drapeau | Rôle |
|:---|:---|
| `--no-deps` | ne réinstalle pas `numpy`/… — on garde ceux d'Anaconda |
| `--no-build-isolation` | utilise le `setuptools` d'Anaconda, pas de build isolé à télécharger |
| `--no-index` | interdit tout accès au réseau (garde-fou) |

> `--no-deps` est ce qui rend l'opération hors-ligne possible, mais c'est aussi
> une promesse : **vous** garantissez que `numpy`, `matplotlib`, `pandas`,
> `rich` et `pyyaml` sont déjà là. `pip` ne vérifiera rien.

> ⚠️ **`--no-build-isolation` exige `setuptools` dans l'environnement.**
> Anaconda le fournit. En revanche un venv nu créé par `python3 -m venv` sous
> Python ≥ 3.12 ne contient **que `pip`** : l'installation échoue alors sur
> `ModuleNotFoundError: No module named 'setuptools'`. Remède, une fois pour
> toutes dans l'environnement cible :
>
> ```bash
> pip install setuptools          # ou : conda install setuptools
> ```

**3. Vérifier :**

```bash
cfd-perf example -o /tmp/verif                                   # l'exemple livré
cfd-perf run /tmp/verif/ONERA_M6_CRUISE.yaml --figure /tmp/fig.png

# Le style maison est-il actif ?
python -c "from cfd_perf.report._plotting_lib import get_plotting; \
print('style maison' if get_plotting() else 'repli matplotlib nu')"
```

## Transporter une roue plutôt que les sources

Si le poste connecté et la machine isolée partagent le même Python, le plus
simple est de construire la roue une fois et de ne transporter qu'un fichier —
elle contient déjà les adaptateurs et l'exemple :

```bash
# poste connecté
python -m build --wheel cfd-perf          # → dist/cfd_perf-<version>-py3-none-any.whl

# machine isolée
pip install cfd_perf-<version>-py3-none-any.whl --no-deps --no-index
```

La roue est `py3-none-any` : elle ne contient pas de code compilé et convient à
n'importe quelle machine Python ≥ 3.9.

## Si la machine cible n'a pas Anaconda

Python nu, sans les paquets scientifiques : il faut transporter les dépendances
sous forme de *roues* (wheels). Sur un poste connecté, avec le **même** couple
OS / version de Python que la cible :

On télécharge les **dépendances**, pas cfd-perf lui-même : ni `cfd-perf` ni
`cfd-plot` ne sont publiés sur PyPI, ils voyagent avec les sources.

```bash
pip download numpy matplotlib pandas rich pyyaml setuptools -d roues/
```

Copier `roues/` **et** les sources sur la machine isolée, puis :

```bash
pip install --no-index --find-links roues/ numpy matplotlib pandas rich pyyaml setuptools
pip install ./cfd-plot --no-build-isolation --no-index --find-links roues/
pip install ./cfd-perf --no-build-isolation --no-index --find-links roues/
```

Noter la disparition de `--no-deps` : ici on *veut* que pip résolve les
dépendances, simplement depuis `roues/` au lieu de PyPI. `--no-index` garantit
qu'il n'ira jamais sur le réseau.

## Si Python vient d'une image conteneur (`.sif`)

Beaucoup de calculateurs isolés distribuent Python par **image
Apptainer/Singularity** : `module load python/3.9` monte une `.sif` au lieu
d'exposer un interpréteur du disque. L'installation se passe alors ainsi :

```bash
module load python/3.9
pip install -e .        # « … n'a pas les droits sur le site-packages partagé »
                        # → pip bascule tout seul sur --user, et réussit
```

L'import fonctionne (`$HOME` est monté dans l'image : le `site-packages`
utilisateur est le même dedans et dehors), mais **la commande, elle, peut être
morte** :

```
bash: /home/moi/.local/bin/cfd-perf: /opt/python/3.9/bin/python3: bad interpreter: No such file or directory
```

`pip` grave dans le script console le chemin de l'interpréteur qui a lancé
l'installation. Ici c'est un chemin *interne à l'image*, invisible depuis
l'hôte. Deux réponses :

```bash
python -m cfd_perf run ETUDE.yaml     # équivalent exact, marche toujours

python -m cfd_perf shim               # ou, une fois pour toutes : ~/bin/cfd-perf
export PATH="$HOME/bin:$PATH"         # dans ~/.bashrc
```

Le lanceur écrit par `shim` résout `python3` sur le `PATH` au moment de
l'appel : il suit le module chargé au lieu d'un chemin figé. Il affiche aussi
les `cfd-perf` concurrents du `PATH` — un script console mort dans
`~/.local/bin` masque volontiers le lanceur. Détail : README §3.7.

## Dépannage

| Symptôme | Cause | Remède |
|:---|:---|:---|
| figures sans style maison (`repli matplotlib`) | `cfd-plot` non installé, ou `pandas` manquant | `pip install ./cfd-plot --no-deps --no-build-isolation --no-index` ; vérifier `pandas` |
| `pip` tente de joindre le réseau | `--no-index` oublié | toujours `--no-index` (+ `--find-links` si roues locales) |
| `ModuleNotFoundError: numpy` (etc.) | Anaconda incomplet, ou `--no-deps` sur un Python nu | `conda install numpy matplotlib pandas rich pyyaml` depuis votre canal local, ou passer par les roues (ci-dessus) |
| `error: externally-managed-environment` | Python système protégé (PEP 668) | créer un venv : `python3 -m venv .venv && source .venv/bin/activate` |
| `ModuleNotFoundError: No module named 'setuptools'` | `--no-build-isolation` dans un venv nu (Python ≥ 3.12 n'y met que `pip`) | `pip install setuptools` dans l'environnement cible |
| `cfd-perf` : `bad interpreter: No such file or directory` | `pip` a gravé un chemin d'interpréteur invalide ici (Python en conteneur, venv déplacé, chemin > 127 octets) | `python -m cfd_perf shim`, puis `export PATH="$HOME/bin:$PATH"` |
| `cfd-perf capture -a MONSOLVEUR` : « adaptateur introuvable » | adaptateur maison hors du paquet | donner son chemin (`-a ./MONSOLVEUR.sh`) ou exporter `CFD_PERF_ADAPTATEUR_DIR` |

Voir aussi : [02_GUIDE_UTILISATEUR.md](02_GUIDE_UTILISATEUR.md),
[05_CAPTURE_PILOTE.md](05_CAPTURE_PILOTE.md).
