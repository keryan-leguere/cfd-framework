# Exemple — test d'intégration sur des tables factices

Un « modèle aéro » analytique tient lieu de code Fortran. On l'exécute une fois
pour obtenir la **référence**, puis on fabrique trois **tests** qui imitent le
même code exécuté ailleurs.

| Scénario     | Ce qui change                                          | Verdict attendu                   |
|--------------|--------------------------------------------------------|-----------------------------------|
| `identique`  | les cas reviennent dans le désordre                    | CONFORME — identique bit pour bit |
| `arrondi`    | quelques ULP sur chaque sortie (autre compilateur)     | CONFORME — dans les tolérances    |
| `regression` | Cm faux de 0.2 % pour Mach ≥ 1.2, 3 cas plantés, 1 NaN | NON CONFORME, attribué à Mach     |

Et sur une table à l'échelle d'une vraie base aéro (`02_grande_table.py`) :

| Scénario       | Ce qui change                                                                  | Verdict attendu                                     |
|----------------|--------------------------------------------------------------------------------|-----------------------------------------------------|
| `grande_table` | 10 entrées × 15 sorties, 3 000 cas : 1 ULP partout, Cm et Cm_alpha faux de 0.1 % pour `braquage_profondeur ≥ 15`, 20 cas plantés | NON CONFORME, attribué à `braquage_profondeur ∈ {15, 20}` |

C'est l'exemple à lancer pour voir comment le rapport se tient quand tout ne
rentre pas à l'écran : le terminal garde les entrées les plus liées aux échecs
et nomme les autres, le journal a toutes les colonnes, la synthèse
(`01_synthese_sorties`) met les 15 sorties sur une page et les figures « par
entrée » ne sont tracées que pour les deux sorties en échec.

```bash
bash RUN_EXEMPLE.sh                          # tout : API Python puis ligne de commande
python 01_test_integration.py regression     # un seul scénario
python 01_test_integration.py --sans-figures # plus rapide
python 02_grande_table.py                    # 10 entrées × 15 sorties
python 02_grande_table.py --figures-entrees toutes   # figure par entrée pour les 15 sorties
```

Fichiers :

- `01_test_integration.py` : le modèle factice, le plan de calcul
  (7 Mach × 11 α × 3 β × 2 configurations = 462 cas), les trois scénarios et
  l'appel à `valider_integration` — **le bloc à recopier pour vos tables** ;
- `02_grande_table.py` : même déroulé sur 10 entrées × 15 sorties (dont
  `CN`/`Cn` et `CM`/`Cm`, qui ne diffèrent que par la casse) ;
- `INTEGRATION.yaml` : la spécification de `01_test_integration.py` pour la ligne de commande ;
- `RUN_EXEMPLE.sh` : enchaîne les deux scripts, puis la ligne de commande.

Les pièces sont écrites dans `SORTIE_INTEGRATION/<scénario>/` : `integration.log`
(le rapport complet), `resume.json`, `lignes.csv`, `ecarts.csv` et `FIGURES/`.
Les tables factices sont dans `SORTIE_INTEGRATION/DONNEES/`.
