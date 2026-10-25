# Annexe prête à coller dans un rapport

Deux livrables, autonomes l'un comme l'autre.

| Fichier | Ce que c'est |
| --- | --- |
| `ANNEXE_TRAINEE_MARCHES.docx` | 30 pages, en français, une section par géométrie. Pour chacune : la planche d'origine du rapport AGARD telle quelle, la superposition qui prouve l'extraction, l'extraction seule, et les formules appliquées. Se colle en annexe sans retouche. |
| `trainee_marches.py` | le calcul, **tout dans un seul fichier**. Aucune dépendance au paquet `cfd-aq`. |

```bash
python3 trainee_marches.py                 # l'exemple de l'annexe, déroulé
python3 trainee_marches.py --figures ./out  # + les planches d'extraction
```

Le script n'a besoin que de NumPy. Les paquets frères sont utilisés s'ils
sont là, et seulement s'ils sont là : [`cfd-atm`](../../cfd-atm) pour
l'atmosphère (ISA ± ΔT, altitude pression, conversions Vc / EAS / TAS), et
[`cfd-plot`](../../cfd-plot) pour le style des figures. Sinon le script
retombe sur une ISA interne et sur Matplotlib nu, et refuse explicitement ce
qu'il ne sait pas faire.

Les valeurs rendues par ce fichier sont **identiques au bit près** à celles
du paquet `cfd-aq` : les deux portent les mêmes tables extraites du rapport.
Le script est la version à livrer, le paquet la version à maintenir.

## Reconstruire l'annexe

```bash
python3 outils/extraire_figures.py     # FIGURES/ : captures, superpositions, extractions
npm install docx                       # une fois
NODE_PATH=<...>/node_modules node outils/construire_docx.js
```

`extraire_figures.py` demande `pdftoppm` (poppler-utils) et le rapport source
`DTIC_ADA106030.pdf` à la racine du paquet. Les planches `ext_*.png` sont
tracées par `trainee_marches.py` lui-même : les figures de l'annexe sortent
donc bien du fichier livré au client, et non d'une source parallèle.

## Les images de `FIGURES/`

| Préfixe | Contenu |
| --- | --- |
| `orig_4_xx.png` | la figure du rapport, capture directe du PDF, recadrée et binarisée |
| `verif_4_xx.png` | la même, avec les courbes du script en tiretés par-dessus |
| `ext_4_xx.png` | l'extraction seule, redessinée depuis les tables du script |
| `schema_geometries.png` | le schéma des trois géométries et des trois corrections |
