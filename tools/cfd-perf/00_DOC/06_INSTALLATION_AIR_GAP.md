# Installation sur calculateur isolé (air-gap)

> Cas visé : une machine **sans accès Internet** disposant déjà d'**Anaconda**
> (ou d'un Python avec `numpy`, `matplotlib`, `pandas`, `rich`, `pyyaml`). Rien
> à télécharger : on copie les sources et on installe sans toucher au réseau.

cfd-perf ne dépend que de `numpy`, `matplotlib`, `rich`, `pyyaml` — toutes dans
Anaconda. Les figures « style maison » utilisent la bibliothèque interne
`plotting` (`scripts/post/plot`), qui n'a besoin que de `matplotlib`, `numpy`,
`pandas` — également dans Anaconda.

## Recette

**1. Copier les sources** sur la machine isolée, en gardant la disposition du
*framework* (au minimum `tools/cfd-perf/` **et** `scripts/post/plot/` sous une
même racine `CFD_FRAMEWORK`) :

```
CFD_FRAMEWORK/
├── tools/cfd-perf/        ← l'outil
└── scripts/post/plot/     ← la bibliothèque de tracé (plotting)
```

**2. Pointer `CFD_FRAMEWORK`** (déjà fait si vous utilisez le *framework* bash) :

```bash
export CFD_FRAMEWORK=/chemin/vers/CFD_FRAMEWORK
```

**3. Installer cfd-perf sans réseau ni dépendances** (Anaconda les fournit déjà) :

```bash
cd "$CFD_FRAMEWORK/tools/cfd-perf"
pip install -e . --no-deps --no-build-isolation --no-index
```

| Drapeau | Rôle |
|:---|:---|
| `--no-deps` | ne réinstalle pas `numpy`/… — on garde ceux d'Anaconda |
| `--no-build-isolation` | utilise le `setuptools` d'Anaconda, pas de build isolé à télécharger |
| `--no-index` | interdit tout accès au réseau (garde-fou) |

**4. Vérifier :**

```bash
cfd-perf run tools/cfd-perf/01_EXEMPLE/ONERA_M6_CRUISE.yaml --figure /tmp/fig.png
```

## Et `plotting` ? — rien à installer

`plotting` **n'est pas** un paquet pip : cfd-perf le trouve *sur le disque*, dans
l'ordre : (1) déjà importable ; (2) `$CFD_FRAMEWORK/scripts/post/plot` ; (3) en
remontant l'arborescence depuis les sources. Il suffit donc que le dossier
`scripts/post/plot/` soit présent et que `CFD_FRAMEWORK` soit défini.

Contrôle rapide :

```bash
python -c "from cfd_perf.report._plotting_lib import get_plotting; \
print('style maison' if get_plotting() else 'repli matplotlib nu')"
```

## Dépannage

| Symptôme | Cause | Remède |
|:---|:---|:---|
| figures sans style maison (`repli matplotlib`) | `scripts/post/plot/` absent, `CFD_FRAMEWORK` non défini, ou `pandas` manquant | copier `scripts/post/plot/`, définir `CFD_FRAMEWORK`, vérifier `pandas` |
| `pip` tente de joindre le réseau | `--no-index` oublié | toujours `--no-deps --no-build-isolation --no-index` |
| `ModuleNotFoundError: numpy` (etc.) | Anaconda incomplet | `conda install numpy matplotlib pandas rich pyyaml` depuis votre canal local |

> Si un jour la machine cible **n'a pas** Anaconda (Python nu, sans les
> paquets), il faut alors transporter les dépendances sous forme de roues
> (`pip download` sur un poste connecté → `pip install --no-index
> --find-links`). Ce n'est pas nécessaire ici.

Voir aussi : [02_GUIDE_UTILISATEUR.md](02_GUIDE_UTILISATEUR.md),
[05_CAPTURE_PILOTE.md](05_CAPTURE_PILOTE.md).
