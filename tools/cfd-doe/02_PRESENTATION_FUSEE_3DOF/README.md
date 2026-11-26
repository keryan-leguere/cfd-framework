# Présentation : base aéro d'une fusée étudiante en 3DOF tangage

Diaporama (`Fusee_3DOF_base_aero.pptx`, et sa version `.pdf`) sur le domaine de vol, le DOE,
la modélisation des coefficients et les résultats d'une fusée étudiante à gouvernes en X. Il
est construit **par la chaîne réelle** de `cfd-doe`, mais **toutes les valeurs sont
factices** : la CFD y est remplacée par un modèle aéro inventé.

```bash
bash construire.sh                     # tout : données → tracés → .pptx
PYTHON=~/venv/bin/python JOBS=8 bash construire.sh
```

Prérequis : `cfd-doe`, `cfd-plot` et `cfd-atm` installés dans l'interpréteur
(`pip install -e ../ -e ../../cfd-plot -e ../../cfd-atm`), plus pandas. Le deck demande
Node.js ; `pptxgenjs` s'installe dans `deck/` au premier passage.

## Les trois étapes

| Étape | Script | Produit |
|---|---|---|
| 1. Données | `generer_donnees.py` | `SORTIE/DOE/doe.csv` (344 calculs), « CFD » factice, **`DONNEES/tables_carrees.csv`** (table carrée Mach × α × DM complétée par symétrie, 684 nœuds), **`DONNEES/increment_dzca.csv`** (ΔzCA(Mach, altitude)), planches hors tables, `DONNEES/chiffres_doe.json` |
| 2. Tracés | `tracer_base_aero.py` | `SORTIE/FIGURES/` (toutes les figures), les planches du deck dans `PLANCHES/`, `PLANCHES/chiffres_tables.json` |
| 3. Deck | `deck/deck.js` | `Fusee_3DOF_base_aero.pptx` |

Les chiffres cités sur les planches sont **lus dans les deux JSON**, jamais recopiés à la
main : une figure régénérée et son commentaire ne peuvent pas diverger.

## Le cas

- Trajectoire `3DOF_TANGAGE` (variables actives α et δm), géométrie cruciforme.
- Gouvernes en X : vue de l'arrière, δ1 en bas à droite puis sens horaire ; δi > 0 quand
  la gouverne braque vers la suivante. Braquage équivalent
  `DM = √2/4 · (δ1 − δ2 − δ3 + δ4)`, donc `DM = √2 · δ` en tangage pur.
- Mach 0,6 → 1,5 par pas de 0,3 (saturé en dessous), α de 0 à 45° par pas de 5°,
  **9 braquages physiques** de −30 à 30° (pas 7,5°), soit DM de −42,4 à 42,4° par pas de 10,6°.
- `CA = CA(M, α, DM) + ΔzCA(M, z)`, avec ΔzCA semi-empirique (frottement turbulent
  Prandtl-Schlichting corrigé de la compressibilité, atmosphère standard de `cfd-atm`) ;
  CN et Cm ne dépendent pas de l'altitude.

## `tracer_base_aero.py` : les tracés d'une base aéro, avec vos tables

Le script ne connaît pas le modèle factice : il ne lit que deux DataFrames, et sert tel quel
sur de vraies tables.

```bash
python tracer_base_aero.py TABLES.csv INCREMENT.csv                     # noms par défaut
python tracer_base_aero.py TABLES.csv INCREMENT.csv \
    --col mach=Mach alpha=ALPHA dm=DM_EQ CA=CA_TOT \
    --col-increment altitude=Z increment=DCA_Z \
    --sortie SORTIE/FIGURES --planches PLANCHES --jobs 4
```

```python
from tracer_base_aero import Options, tracer_base_aero

planches = tracer_base_aero(
    df_tables, df_increment, "SORTIE/FIGURES",
    colonnes={"mach": "Mach", "alpha": "ALPHA", "dm": "DM_EQ"},
    colonnes_increment={"altitude": "Z", "increment": "DCA_Z"},
    planches="PLANCHES",
    options=Options(profil="paper", facteur_braquage=2**0.5, n_jobs=4),
)
```

| Clé | Défaut | Contenu |
|---|---|---|
| `mach`, `alpha`, `dm` | `mach`, `alpha`, `DM` | les trois axes de la table, degrés |
| `CA`, `CN`, `Cm` | idem | les coefficients |
| incrément : `mach`, `altitude`, `increment` | `mach`, `altitude`, `DZCA` | ΔzCA, altitude en m |

La table doit être **carrée** (produit complet des trois axes, sans doublon ni trou) : le
script refuse sinon, en donnant le décompte. α = 0 et DM = 0 doivent être des nœuds
intérieurs (dérivées par différences centrées).

| Dossier | Figures | cfd-plot |
|---|---|---|
| `COURBES/` | CA, CN, Cm selon α (une figure par Mach) et selon Mach (α épinglé), une courbe par DM ; zoom sur la zone linéaire ; feuilles « 4 Mach » et « 3 coefficients » | `batch_plot`, `ZoomSpec`, `FoldSpec` |
| `CARTES/` | CA, CN, Cm dans le plan (α, DM), un panneau par Mach, échelle partagée ; Cm = 0 = ligne d'équilibre | `batch_carto`, `CartoSpec`, sous-dict `CARTO` |
| `INCREMENT/` | ΔzCA(Mach) par altitude ; CA lu comme le simulateur (saturation, multilinéaire + incrément), médaillon sur l'écart d'altitude | `batch_plot`, zoom en médaillon |
| `EQUILIBRE/` | α et CN d'équilibre selon DM, par Mach | `batch_plot`, `FoldSpec(kind="y")` |
| `DERIVEES/` | CNα, Cmα, CNδ, Cmδ et marge statique selon Mach | `batch_plot`, `FoldSpec(kind="y")` |

Un même crochet `on_before_save` (`Habillage`, classe de module donc picklable :
`--jobs` garde son pool) hachure la zone α < 0 « déduit par symétrie », trace y = 0, la
bande de marge statique usuelle, sort les légendes nombreuses du cadre et ôte l'en-tête
anglais des feuilles repliées (la planche porte son titre). `Table3D` et
`lire_increment` sont la lecture du simulateur, réutilisables telles quelles.

## Ce qui est versionné

Les sources, les deux YAML de l'étude, `DONNEES/`, `PLANCHES/` et le `.pptx`/`.pdf`.
`SORTIE/` (DOE, résultats, arborescence complète des figures) et `deck/node_modules/` sont
régénérés et ignorés.
