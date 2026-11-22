# 03 — Interpolation des tables

Entre les nœuds de ses tables, le code rend-il l'interpolation multilinéaire
de la table ? Pour chaque table, deux familles de points, chacune un
**groupe** du rapport :

- **par axe** : l'axe placé dans chacune de ses mailles à ¼, ½ et ¾, les autres
  axes sur tous leurs nœuds ; une maille fautive se localise (colonne `maille`,
  indices de base 1 comme le Fortran) ;
- **centres** : le centre de chaque maille, tous les axes à mi-maille. Les 2ᵈ
  coins y pèsent autant, et un couplage faux entre axes (une somme
  d'interpolations 1D) s'y voit alors qu'il passe le long des axes.

```bash
python 03_interpolation_tables.py                  # 8 tables, 40 270 appels, 121 polaires
python 03_interpolation_tables.py --jobs 4         # polaires tracées sur 4 processus
python 03_interpolation_tables.py --fractions 0.1 0.5 0.9
python 03_interpolation_tables.py --defaut         # CM relu en palier (simulé) : NON CONFORME (code 2)
```

Pour chaque groupe, le rapport donne le comportement **observé** : linéaire,
palier (le code rend un coin de la maille), indiscernable (maille plate) ou ni
l'un ni l'autre. Une faute se lit directement : « CM alpha : attendu linéaire,
observé palier ».

## Les polaires

Le test trace aussi, par `cfd_plot.batch_plot`, les **polaires** de chaque
table : pour chaque abscisse et chaque condition (les autres axes sur un de
leurs nœuds), la courbe du code de 10 % de l'étendue avant la première borne à
10 % après la dernière. Elles montrent les trois tests d'un coup d'œil :

| Ce qu'on regarde | Test |
|------------------|------|
| la courbe passe par les points bleus (nœuds de la table) | lecture |
| elle est droite entre deux points | interpolation |
| dans les zones grisées, elle est plate (`sature`) ou prolonge la dernière maille (`extrapole`) | bornes |

Une figure par condition, plus une figure **superposée** par abscisse
(`fold` « overlay » de `batch_plot`, dossier `SUPERPOSITION/`) : une couleur par
valeur de l'axe superposé, trait pour le code, points pour la table. Tout en
SVG, profil « paper ».

Les polaires à tracer sont déclarées dans `../tables_modele.py` (`POLAIRES`) :
toutes par défaut, ce qui va en 2D (14 courbes pour une 7 × 7) mais pas en 5D
(3 125) ; DCMG est restreinte à Mach 1, trois incidences, deux azimuts, DN nul.
Les libellés des axes (`LIBELLES`, mathtext) y sont aussi.

Les pièces vont dans `SORTIE/<scénario>/` (ou le dossier passé par `--sortie`) :
- `interpolation_tables.log` : le rapport complet ;
- `resume.json` ;
- `RESULTATS/` : par table, un appel par ligne, avec `groupe`, `maille`,
  `fraction`, `valeur_ATTENDUE`, `valeur_CODE`, `ecart` et `conforme` ;
- `POLAIRES/<TABLE>/POLAIRE_<AXE>/…` : les polaires et leurs superpositions.

Le mécanisme est décrit dans `00_DOC/05_INTERPOLATION_TABLES.md`, à la racine
de `cfd-validation`.
