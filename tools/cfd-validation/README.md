# cfd-validation

Utilitaires de **vérification de code** (Fortran 77, C) : des contrôles qui
produisent des pièces justificatives traçables plutôt qu'un simple « les tests
passent ». Rapport terminal (Rich, français), journal complet, CSV, JSON et
figures prêtes pour un rapport (via `cfd-plot`).

Premier contrôle : le **test d'intégration**. Le même code, exécuté dans deux
environnements, donne-t-il les mêmes sorties ?

## Installation

```bash
cd tools/cfd-validation
python3 -m venv .venv && source .venv/bin/activate
pip install -e ../cfd-plot          # figures (paquet frère, pas sur PyPI)
pip install -e ".[dev]"
pytest
```

Sans `cfd-plot`, tout fonctionne sauf les figures (un avertissement le dit).
Python ≥ 3.9 ; numpy, pandas, rich, pyyaml. La compatibilité 3.9 est vérifiée en
exécutant la suite sous un interpréteur 3.9, avec les versions courantes et avec les
planchers déclarés (numpy 1.26, pandas 1.5, rich 13.0) ; mypy ne sait plus cibler 3.9,
ruff (`target-version = "py39"`) refuse la syntaxe trop récente.

## Test d'intégration en 30 secondes

```python
from cfd_validation import valider_integration

res = valider_integration(
    reference, test,                       # deux DataFrames de même format
    entrees=["Mach", "alpha", "beta"],
    sorties=["CN", "CA", "Cm"],
    rtol=1e-9, atol=1e-12, justification="changement de compilateur",
    sortie="VALIDATION/INT-01",
)
print(res.verdict)   # CONFORME — identique bit pour bit / dans les tolérances / NON CONFORME
```

```bash
cfd-validation integration REF.csv TEST.csv --config INTEGRATION.yaml -o VALIDATION/INT-01
cfd-validation exemple                     # recopier l'exemple (tables factices, 3 scénarios)
```

Le rapport donne, dans l'ordre : identification (versions, SHA-256 des
données), spécification (tolérance et justification de chaque sortie),
structure (lignes appariées, absentes, en trop), résultats par sortie
(identiques / tolérées / hors tolérance, max |Δ|, ULP, biais, marge, pire
point), **attribution des échecs aux entrées**, lignes en échec, verdict.

Codes de retour : `0` conforme, `1` erreur d'entrée, `2` non conforme.

Sans colonne d'entrée (`entrees` omis, ou `--sorties` seul en ligne de
commande), les lignes sont appariées dans l'ordre, la i-ème contre la i-ème,
sans vérification ni attribution des échecs.

## Test de lecture de table

Le code, appelé sur chaque nœud de chaque table (1D à 5D), rend-il la valeur
de la table ? La valeur lue est prise par une **sonde** placée dans le code
juste après la lecture ; la table de référence est celle que le code contient.

```python
from cfd_validation import TableReference, valider_lecture_tables

res = valider_lecture_tables(
    [TableReference("CX", modele.lire("aertab.tcx"),
                    {"mach": modele.lire("aertab.tmach"), "alpha": modele.lire("aertab.talpha")},
                    sonde="valid_tab_cx")],
    evaluer=modele.calculer_df,             # DataFrame d'entrées → DataFrame avec les sondes
    defauts={"mach": 0.8, "alpha": 0.0, ...},
    combinaisons={"beta": [-5, 0, 5]},      # option : la lecture n'en dépend pas
    sortie="LECTURE_TABLES",
)
```

Exemple complet sur un code Fortran encapsulé par f2py :
`src/cfd_validation/01_EXEMPLE/MODELE_AERO/` (`VALIDATION/01_LECTURE_TABLES/`, tous les tests par `bash VALIDATION/RUN_VALIDATION.sh`).

## Documentation

- `00_DOC/01_PRINCIPE.md` : vérification et validation, oracles, et ce que
  chaque pièce répond aux normes (DO-178C, ECSS-E-ST-40C/Q-ST-80C,
  NASA-STD-7009A, IEEE 29119-3) ;
- `00_DOC/02_TEST_INTEGRATION.md` : appariement, critère, mesures,
  attribution, pièces, lecture des figures ;
- `00_DOC/03_LECTURE_TABLES.md` : sondes, déclaration d'une table,
  orientation, inversion, combinaisons, pièces, lecture de la figure ;
- `src/cfd_validation/01_EXEMPLE/` : l'exemple exécutable (`bash RUN_EXEMPLE.sh`),
  et `MODELE_AERO/`, un code Fortran 77 encapsulé par f2py et sa validation.

## Architecture

```
cli/     →  report, engine, data, core       ligne de commande
report/  →          engine, data, core       Rich (terminal, journal), figures cfd-plot
engine/  →                  data, core       appariement, comparaison, environnement
data/    →                        core       spécification, lecture des fichiers
core/    →  NumPy seulement                  tolérance, écarts/ULP, attribution
integration.py                               la façade : calcul → rendu → pièces
```

La règle est vérifiée sur les imports par `tests/test_architecture.py`.
