# Exemple cfd-validation — prêt à tourner

Un modèle aérodynamique à deux tables, et le contrôle qui vérifie qu'il les
relit correctement. Tout tourne **sans compilateur** ; le script `05` compile du
vrai Fortran quand la machine le permet, et le dit proprement sinon.

```bash
bash RUN_EXEMPLE.sh
```

---

## Les fichiers

| | |
|:--|:--|
| `TABLES.yaml` | la déclaration des deux tables, commentée clé par clé |
| `aero_factice.py` | le modèle enveloppé, sous la forme où un module f2py se présente |
| `mon_modele.py` | **ce que vous écrivez** : la fonction qui appelle votre modèle |
| `MODELE_FORTRAN/aero.f` | le jumeau Fortran réel, avec ses COMMON blocks |
| `SORTIE/` | tout ce que l'exemple écrit (régénérable, ignoré par git) |

## Ce que chacun montre

### `01_lire_table.py` — voir ce que le paquet voit

Liste les COMMON blocks que le module expose, valide la déclaration, et affiche
les tables lues. Finit par la démonstration que la clé `lignes` sert : sans
elle, la table CN emporte les 26 lignes de remplissage que le Fortran n'a jamais
écrites.

C'est le premier réflexe devant un module inconnu, et la première cause d'échec.

### `02_valider.py` — le contrôle, en trois lignes

```python
rapport = valider_tables(aero_factice, charger_fichier("TABLES.yaml"), modele=mon_modele.appeler)
sys.exit(imprimer_rapport(rapport))
```

Sort en **0**. Le modèle relit exactement ses tables : c'est ce qu'un code juste
fait, puisqu'une interpolation vaut la valeur tabulée à chacun de ses nœuds.

### `03_diagnostics.py` — une panne, un motif

Rejoue les sept pannes que le paquet sait injecter, plus la huitième qui est
dans la *déclaration* (oublier `lignes`), et montre que le diagnostic nomme à
chaque fois la bonne. Finit par le rapport complet d'une de ces pannes.

C'est la démonstration que les détecteurs font ce qu'ils annoncent — sur des
cas, pas sur un raisonnement.

### `04_figures_batch_plot.py` — les planches

Un appel de `cfd_plot.batch_plot` par table. Deux configurations, `TABLE` et
`MODELE`, superposées ; une polaire par variable indépendante ; les points hors
tolérance entourés de rouge et reliés à leur valeur tabulée.

```bash
python3 04_figures_batch_plot.py --a-blanc          # énumère sans écrire
python3 04_figures_batch_plot.py --juste            # le modèle juste
python3 04_figures_batch_plot.py --toutes-valeurs   # sans échantillonner
```

Nécessite `cfd-plot` : `pip install -e ../../cfd-plot`.

### `05_fortran_reel.py` — le même contrôle, sur du Fortran compilé

Compile `MODELE_FORTRAN/aero.f` par f2py, charge le module, et lui fait subir le
contrôle des scripts précédents. Le Fortran porte un interrupteur
`regler_bug(mode)` qui injecte une **vraie** erreur de lecture dans le code
compilé.

Demande gfortran et le moteur de compilation de f2py ; `cfd-validation
toolchain` dit ce qui manque. Sans cela, le script le dit et sort en 0.

---

## Le contrat de votre modèle, en trois lignes

`mon_modele.py` est la seule pièce que cfd-validation ne peut pas fournir.

* elle reçoit un `DataFrame` portant les colonnes **indépendantes** de la table
  et les constantes déclarées — jamais les QOI, sans quoi le contrôle ne
  prouverait rien ;
* elle rend un `DataFrame` de **même longueur**, **dans le même ordre**, portant
  les QOI ;
* elle ne trie rien et ne regroupe rien.

Avec un vrai module f2py, elle tient en une ligne :

```python
rendu["CN"] = aero.eval_cn(df["mach"].to_numpy(), df["alpha"].to_numpy(), df["delta"].to_numpy())
```

Voir `00_DOC/03_BRANCHER_SON_MODELE.md`.

## Sans cfd-plot

Les scripts `01`, `02`, `03` et `05` n'en ont pas besoin. Seul `04` trace.
