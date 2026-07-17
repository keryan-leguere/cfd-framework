# Format du fichier d'étude

Une étude tient dans **un seul fichier YAML**, versionnable à côté du cas.

Exemple complet et commenté : [`01_EXEMPLE/ONERA_M6_CRUISE.yaml`](../01_EXEMPLE/ONERA_M6_CRUISE.yaml).

Valider un fichier sans lancer le calcul :

```bash
cfd-perf check mon_etude.yaml
```

## Vue d'ensemble

| Section | Requise | Rôle |
|:---|:---:|:---|
| `study` | **oui** | nom et nombre d'itérations |
| `mesh` | **oui** | taille du maillage |
| `pilot` | **oui** | les mesures réelles |
| `machine` | non | nœuds, RAM, limites de la partition |
| `constraints` | non | limites de faisabilité |
| `objective` | non | ce qu'on optimise |

Toute section inconnue est **rejetée** avec un message explicite (une faute de
frappe ne doit jamais être ignorée en silence).

---

## `study` — requis

```yaml
study:
  name: "Aile ONERA M6 - croisière transsonique"
  n_iterations: 12000
```

| Clé | Type | Défaut | Sens |
|:---|:---|:---|:---|
| `name` | texte | `unnamed study` | titre du rapport et de la figure |
| `n_iterations` | entier > 0 | **requis** | itérations pour converger |

> `n_iterations` vient de votre expérience d'un cas similaire. **Durée et coût
> lui sont directement proportionnels** : une estimation à ±30 % donne une
> réponse à ±30 %.

---

## `mesh` — requis

```yaml
mesh:
  num_cells: 20000000
  num_faces: 61200000
  mem_per_cell_bytes: 7600
  cell_type_distribution:
    hex: 0.78
    prism: 0.14
```

| Clé | Type | Défaut | Sens |
|:---|:---|:---|:---|
| `num_cells` | entier > 0 | **requis** | nombre de mailles |
| `num_faces` | entier > 0 | — | informatif |
| `mem_per_cell_bytes` | réel > 0 | déduit du pilote | octets par maille |
| `cell_type_distribution` | table | — | **documentaire**, sans effet sur le calcul |

### Résolution de la mémoire par maille

1. `mem_per_cell_bytes` explicite ;
2. sinon déduit de `peak_ram_total_gb` du pilote (`RAM crête / num_cells`) ;
3. sinon **inconnue** → les contraintes mémoire sont ignorées.

La source est affichée dans le rapport (`measured (pilot)`, `user`, `unknown`) :
un chiffre deviné produirait un nombre de nœuds faux mais confiant, donc on ne
devine pas.

---

## `pilot` — requis

```yaml
pilot:
  - {cores:   48, time_per_iter_s: 3.85, peak_ram_total_gb: 142.0}
  - {cores:   96, time_per_iter_s: 2.18, peak_ram_total_gb: 142.0}
  - {cores:  192, time_per_iter_s: 1.41, peak_ram_total_gb: 143.0}
```

| Clé | Type | Requis | Sens |
|:---|:---|:---:|:---|
| `cores` | entier > 0 | oui | cœurs du run pilote |
| `time_per_iter_s` | réel > 0 | oui | temps/itération en régime établi |
| `peak_ram_total_gb` | réel > 0 | non | RAM crête **cumulée** sur tous les rangs |

Règles :

- **≥ 2 points** obligatoires, **≥ 3** pour le terme de communication,
  **4 à 6** recommandés ;
- l'ordre est libre (tri automatique) ; les **doublons** de `cores` sont refusés ;
- le point le plus bas devient la **référence** (accélération = 1) ;
- la RAM totale retenue est le **maximum** observé, pas celle de la référence :
  l'empreinte croît avec les cœurs, dimensionner sur le minimum sous-provisionne.

---

## `machine` — optionnel

```yaml
machine:
  name: "cluster-a (skylake)"
  cores_per_node: 48
  ram_per_node_gb: 192
  max_nodes: 32
  max_walltime_hours: 24
```

| Clé | Type | Défaut | Sens |
|:---|:---|:---|:---|
| `name` | texte | `generic` | affichage |
| `cores_per_node` | entier > 0 | `1` | **arrondi aux nœuds entiers** |
| `ram_per_node_gb` | réel > 0 | — | rejette ce qui ne tient pas en mémoire |
| `max_nodes` | entier > 0 | — | limite de la partition |
| `max_walltime_hours` | réel > 0 | — | limite de l'ordonnanceur |

> **Renseignez `cores_per_node`.** Sinon cfd-perf peut répondre « 531 cœurs »,
> inutilisable : vous demanderez 12 nœuds (576 cœurs) et serez facturé pour 12.

---

## `constraints` — optionnel

```yaml
constraints:
  min_cells_per_core: 10000
  min_ram_per_core_gb: 0.5
  max_core_hours: 250000
  max_walltime_hours: 12
```

| Clé | Type | Défaut | Sens |
|:---|:---|:---|:---|
| `min_cells_per_core` | entier > 0 | `10000` | plancher de charge par cœur |
| `min_ram_per_core_gb` | réel > 0 | — | plancher mémoire par cœur |
| `max_walltime_hours` | réel > 0 | — | cumulé avec celui de `machine` (le plus strict gagne) |
| `max_core_hours` | réel > 0 | — | budget d'allocation |

Sous ~10 000 mailles/cœur, l'échange de halos domine le travail utile du
solveur pour un volumes finis non structuré RANS typique. C'est un **plancher**,
pas une cible.

---

## `objective` — optionnel

```yaml
objective:
  strategy: efficiency
  max_efficiency_loss: 0.30
  deadline_hours: 6
  cores_min: 96
  cores_max: 1536
```

| Clé | Type | Défaut | Sens |
|:---|:---|:---|:---|
| `strategy` | `efficiency` \| `deadline` \| `fastest` | `efficiency` | voir le guide |
| `max_efficiency_loss` | réel dans (0,1) | `0.30` | perte tolérée |
| `deadline_hours` | réel > 0 | — | **requis** si `strategy: deadline` |
| `cores_min` | entier > 0 | cœurs de référence du pilote | borne basse |
| `cores_max` | entier > 0 | déduit du maillage et de la machine | borne haute |

Sans `cores_max`, la borne est déduite du plancher mailles/cœur, de
`machine.max_nodes`, et d'une marge au-delà de la plage pilote.

---

## Surcharges en ligne de commande

Les options CLI l'emportent sur le fichier, pour tester une variante sans
l'éditer :

```bash
cfd-perf run etude.yaml --strategy deadline --deadline 4.5
cfd-perf run etude.yaml --cores-max 768
cfd-perf run etude.yaml --model amdahl
```

| Option | Surcharge |
|:---|:---|
| `--strategy` | `objective.strategy` |
| `--deadline HOURS` | `objective.deadline_hours` |
| `--cores-max N` | `objective.cores_max` |
| `--model` | choix automatique du modèle |
| `--figure CHEMIN` | écrit la figure |
| `-v` | affiche toute la courbe |
