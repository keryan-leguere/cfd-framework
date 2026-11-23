# 01 — Lecture de table

Le code, appelé sur chaque nœud de chaque table, rend-il la valeur de la
table ? Les dix tables du modèle (onze déclarations : DCXB des deux côtés) sont relues :
- six tables 2D 7×7 : CX, CZ, CM sur (mach, alpha), et CY, CL, CN sur (mach, beta) ;
- la table de propulsion 1D (DCXP, sur mach) ;
- la table des gouvernes 5D 5×5×5×5×5 (DCMG, sur mach, alphat, phia, dm, dn).
- deux tables 2D à lecture indirecte (`DOC/01_SOURCES.md` §4.4) : DCZR, tabulée en
  alpha **en radians** (`vers_entrees` convertit en degrés), et DCXB, tabulée en
  **|beta|**, déclarée deux fois (DCXB pour beta > 0, DCXB_NEG pour beta < 0).

```bash
python 01_lecture_tables.py                 # entrées libres aux défauts
python 01_lecture_tables.py --combinaisons  # + toutes les combinaisons des autres entrées
python 01_lecture_tables.py --defaut        # une valeur de CM faussée : NON CONFORME (code 2)
```

Les pièces sont écrites dans `SORTIE/<scénario>/` (ou dans le dossier passé par `--sortie`) :
- `lecture_tables.log` : le rapport complet ;
- `resume.json` ;
- `TABLES/` : les tables de référence à plat ;
- `RESULTATS/` : par table, une ligne par appel, avec `valeur_TAB`, `valeur_CODE`, `ecart` et `conforme` ;
- `FIGURES/synthese_tables_*.svg` : la synthèse.

Ce que montre chaque table :

| Table | Ce qu'elle illustre |
|-------|---------------------|
| CX … CN | Cas direct : les colonnes de la table sont des entrées du modèle. Identité bit pour bit attendue et obtenue. |
| DCXP | Une table lue sous condition : sans `fixes={"ipropu": 1}`, la sonde reste NaN et le test échoue en le disant. |
| DCMG | 5D, colonnes qui ne sont **pas** des entrées : (alphat, phia) → (alpha, beta) par `vers_entrees`. L'aller-retour ne retombe pas au bit près sur le nœud, d'où une tolérance déclarée et justifiée. |

**Pour un autre code**, on réécrit `../tables_modele.py` (`declarer_tables` ; les valeurs par
défaut viennent du modèle, `DEFAUTS` et `DEFAUTS_CALCUL` de sa classe), commun à tous les tests. Le
mécanisme est décrit dans `00_DOC/03_LECTURE_TABLES.md`, à la racine de
`cfd-validation`.
