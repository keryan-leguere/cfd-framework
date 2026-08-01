# Installation sur calculateur isolé (air-gap)

> Cas visé : une machine **sans accès Internet** disposant déjà d'**Anaconda**
> (ou d'un Python avec `numpy`, `matplotlib`, `pandas`, `rich`, `pyyaml`). Rien
> à télécharger : on copie les sources et on installe sans toucher au réseau.

cfd-perf ne dépend que de `numpy`, `matplotlib`, `rich`, `pyyaml` — toutes dans
Anaconda. Les figures « style maison » viennent du paquet voisin **`cfd-plot`**
(`tools/cfd-plot`), qui n'a besoin que de `matplotlib`, `numpy`, `pandas` —
également dans Anaconda.

`cfd-plot` est **facultatif** : sans lui, cfd-perf trace les mêmes figures en
Matplotlib brut, sans le style maison. Rien d'autre ne change.

## Recette

**1. Copier les sources** sur la machine isolée. Les deux paquets sont
indépendants ; seule l'installation de `cfd-plot` est en plus :

```
CFD_FRAMEWORK/
└── tools/
    ├── cfd-perf/   ← l'outil
    └── cfd-plot/   ← la bibliothèque de tracé (facultative)
```

**2. Installer les deux paquets, sans réseau ni dépendances** (Anaconda les
fournit déjà) :

```bash
cd "$CFD_FRAMEWORK"
pip install -e tools/cfd-plot --no-deps --no-build-isolation --no-index   # facultatif
pip install -e tools/cfd-perf --no-deps --no-build-isolation --no-index
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
cfd-perf run tools/cfd-perf/01_EXEMPLE/ONERA_M6_CRUISE.yaml --figure /tmp/fig.png

# Le style maison est-il actif ?
python -c "from cfd_perf.report._plotting_lib import get_plotting; \
print('style maison' if get_plotting() else 'repli matplotlib nu')"
```

## Pourquoi `CFD_FRAMEWORK` n'est plus nécessaire

Historiquement, `cfd-plot` n'était pas un paquet pip : cfd-perf allait le
*chercher sur le disque* via `$CFD_FRAMEWORK`, en insérant le chemin dans
`sys.path`. Ce n'est plus le cas — `cfd-plot` s'installe normalement et
`import cfd_plot` suffit. `CFD_FRAMEWORK` reste utile au *framework* bash, mais
plus du tout à cfd-perf.

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
pip install -e tools/cfd-plot --no-build-isolation --no-index --find-links roues/
pip install -e tools/cfd-perf --no-build-isolation --no-index --find-links roues/
```

Noter la disparition de `--no-deps` : ici on *veut* que pip résolve les
dépendances, simplement depuis `roues/` au lieu de PyPI. `--no-index` garantit
qu'il n'ira jamais sur le réseau.

## Dépannage

| Symptôme | Cause | Remède |
|:---|:---|:---|
| figures sans style maison (`repli matplotlib`) | `cfd-plot` non installé, ou `pandas` manquant | `pip install -e tools/cfd-plot --no-deps --no-build-isolation --no-index` ; vérifier `pandas` |
| `pip` tente de joindre le réseau | `--no-index` oublié | toujours `--no-index` (+ `--find-links` si roues locales) |
| `ModuleNotFoundError: numpy` (etc.) | Anaconda incomplet, ou `--no-deps` sur un Python nu | `conda install numpy matplotlib pandas rich pyyaml` depuis votre canal local, ou passer par les roues (ci-dessus) |
| `error: externally-managed-environment` | Python système protégé (PEP 668) | créer un venv : `python3 -m venv .venv && source .venv/bin/activate` |
| `ModuleNotFoundError: No module named 'setuptools'` | `--no-build-isolation` dans un venv nu (Python ≥ 3.12 n'y met que `pip`) | `pip install setuptools` dans l'environnement cible |

Voir aussi : [02_GUIDE_UTILISATEUR.md](02_GUIDE_UTILISATEUR.md),
[05_CAPTURE_PILOTE.md](05_CAPTURE_PILOTE.md).
