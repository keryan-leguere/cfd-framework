# 04 — Test d'intégration

Le code construit ici redonne-t-il, cas par cas, les résultats obtenus dans un
**autre environnement** (autre machine, autre compilateur, ancienne chaîne de
calcul) ?

```
04_INTEGRATION/
├── 04_integration.py       le test
├── generer_reference.py    fabrique REFERENCE/ pour l'exemple (démonstration seulement)
└── REFERENCE/              les CSV de l'autre environnement, un par campagne
    ├── campagne_A_incidence.csv    459 lignes, en-têtes « Alpha (deg) »
    ├── campagne_B_propulsion.csv   152 lignes, en-têtes « ALPHA [deg] », PROPULSION ON/OFF
    └── campagne_C_gouvernes.csv    405 lignes, idem
```

```bash
python 04_integration.py               # conforme : quelques ULP d'écart, dans la tolérance
python 04_integration.py --defaut      # Cm décalé de 1e-9 à |DM| = 20° : NON CONFORME, attribué à dm
python 04_integration.py --reference /ailleurs/CSV
```

## Ce que fait le script

1. **Lecture** — `cfd_validation.lire_dossier(REFERENCE, renommer=normaliser_colonnes,
   colonne_fichier="campagne")` : tous les CSV du dossier, relus au bit près,
   chacun passé au helper de renommage, puis mis bout à bout. Les fichiers
   doivent avoir les mêmes colonnes une fois renommés, sinon la lecture est
   refusée en nommant le fichier et les colonnes en cause. La colonne
   `campagne` garde le fichier d'origine de chaque ligne.
2. **Le helper** — `normaliser_colonnes` est le seul morceau propre à ces
   fichiers. `nom_type` retire l'unité entre `()` ou `[]`, passe en
   minuscules, remplace les espaces par `_`, puis applique `ALIAS`
   (`propulsion → ipropu`, `biais_cx → biaicx`, `delta_m → dm`…). La
   propulsion `ON`/`OFF` devient 1/0. Une colonne sans équivalent dans le
   modèle est refusée : on complète `ALIAS`, on ne l'ignore pas en silence.
3. **Rejeu** — les entrées de la référence passent dans
   `ModeleAero.calcul_aero_elementaire`, le code d'ici.
4. **Comparaison** — `valider_integration` : lignes appariées sur leurs
   entrées, `campagne` comprise (un échec se rattache donc aussi à son fichier) ;
   CX … Cn à `|Δ| ≤ 1e-14 + 1e-12·|réf|` (justifié dans le script, à partir
   des écarts mesurés entre les deux compilations), IERR à l'identique. Les
   SHA-256 des CSV de référence sont repris dans l'identification du rapport.

## Pour vos propres CSV

Déposer les fichiers dans `REFERENCE/` (ou passer `--reference DIR`), puis
compléter `ALIAS` jusqu'à ce que la lecture ne refuse plus rien. Les
tolérances (`RTOL`, `ATOL`, `JUSTIFICATION`) se règlent sur les écarts
attendus entre les deux environnements, et la justification dit pourquoi.

`generer_reference.py` n'existe que pour l'exemple : il produit `REFERENCE/`
avec le même Fortran compilé en `-O3 -ffast-math -march=native`
(`FFLAGS="…" bash construire.sh aerolib_autre`), écrit sous deux conventions
d'en-tête. Écarts mesurés contre `-O2` : au plus 1 ULP sur la plupart des
sorties, 64 ULP (8,6e-15 relatif) sur Cm près de zéro, IERR identique.

## Pièces (`SORTIE/<scénario>/`)

`integration.log` (rapport complet, SHA-256 des autres pièces), `resume.json`,
`lignes.csv`, `ecarts.csv`, `FIGURES/` en SVG (synthèse par sortie, marges, répartition,
taux d'échec selon chaque entrée qui varie ; pour une sortie en échec, sa marge
selon chaque entrée, et la liaison entrée × sortie).
