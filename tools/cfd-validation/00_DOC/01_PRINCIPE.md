# 01 — Principe : ce que « prouver qu'un code fonctionne » veut dire

## 1. Un test ne prouve pas l'absence de bug

Il prouve qu'une **affirmation précise** tient, sur un **domaine précis**, avec
un **critère précis**. Un dossier de vérification rassemble donc des preuves
**traçables** : ce qu'on affirme, comment on l'a vérifié, avec quel critère,
sur quelle version, et comment le rejouer. Chaque contrôle de `cfd-validation`
produit ces cinq éléments, et rien n'y est écrit à la main.

## 2. Vérification et validation

| | Question | Moyen |
|---|---|---|
| **Vérification** | Le code résout-il correctement les équations qu'il prétend résoudre ? | mathématiques, logiciel : ce paquet |
| **Validation** | Ces équations représentent-elles la réalité ? | comparaison à l'expérience : hors de ce paquet |

(ASME V&V 10/20, Oberkampf & Roy, *Verification and Validation in Scientific Computing*.)

## 3. Toute méthode de test répond à une question : d'où vient la bonne réponse ?

| Méthode | Oracle | Ce que ça prouve | Dans le paquet |
|---|---|---|---|
| Test d'intégration | le même code, exécuté dans l'environnement de référence | l'environnement testé ne change pas les sorties | **`valider_integration`** |
| Solution analytique | une formule exacte | exactitude sur des cas particuliers | à venir |
| Solutions manufacturées + ordre de convergence | une solution choisie, son terme source | le schéma converge à l'ordre théorique | à venir |
| Invariants, propriétés | une loi que la sortie doit respecter | cohérence sur tout un domaine | à venir |
| Tests métamorphiques | une relation entre deux exécutions | utile quand aucun oracle n'existe | à venir |
| Non-régression | une version antérieure | rien n'a bougé (pas que c'était juste) | `valider_integration` |

## 4. Exigences des normes, et ce que le paquet y répond

Le rapport vise la rigueur des référentiels de qualité logicielle les plus
exigeants du domaine. Le tableau dit quelle exigence chaque pièce couvre. Il ne
vaut **pas** certification : DO-178C ou ECSS demandent aussi un plan, une
revue indépendante et la gestion de configuration, qui sont hors d'un outil.

| Exigence | Référence | Réponse de `cfd-validation` |
|---|---|---|
| Identifier l'article testé et l'environnement d'essai | DO-178C §11.15 (SECI) et §11.16 (SCI) ; IEEE 29119-3 *Test Environment Readiness Report* ; ECSS-E-ST-40C (gestion de configuration) | section *1. Identification* : date UTC, hôte, système, versions, **SHA-256 du contenu** des deux tables, métadonnées libres (code, commit, compilateur, options) |
| Critère de réussite défini **avant** l'essai, justifié | DO-178C §11.13 (cas et procédures de vérification : résultats attendus, critères) ; NASA-STD-7009A (critères d'acceptation documentés) | tolérance par sortie, avec origine (**défaut** / **déclarée**) et justification ; toute tolérance non justifiée est signalée |
| Résultat de chaque cas de test | DO-178C §11.14 (SVR) ; IEEE 29119-3 *Test Execution Log* | `integration.log` et `lignes.csv` : **chaque ligne**, son statut, sa sortie la plus en écart |
| Verdict univoque | IEEE 29119-3 *Test Completion Report* | CONFORME / NON CONFORME + motifs, code de retour 0/2 |
| Analyse des écarts constatés | IEEE 29119-3 *Test Incident Report* ; ECSS-Q-ST-80C (traitement des non-conformités) | *5. Attribution* : sur quelle entrée les échecs se concentrent ; figures 03 à 05 |
| Reproductibilité, intégrité des pièces | ECSS-E-ST-40C ; NASA-STD-7009A (traçabilité des résultats de M&S) | `resume.json` (paramètres complets), SHA-256 de chaque pièce dans le journal, `cfd-validation integration … --config` rejoue à l'identique |
| Domaine couvert explicite | NASA-STD-7009A (domaine d'utilisation) | les niveaux de chaque entrée, et les lignes absentes ou en trop, sont listés |

Les numéros de section DO-178C sont ceux de l'édition 2011 ; pour ECSS et la
NASA, le renvoi est fait au document, et la clause exacte reste à relever
dans l'édition applicable au contrat.

## 5. Les conventions du paquet

- **Rien n'est saisi à la main dans un rapport** : chaque chiffre est calculé,
  chaque pièce porte son empreinte. Un rapport retouché n'est plus une preuve.
- **Un test qui ne peut pas échouer n'est pas un test** : chaque contrôle est
  livré avec des cas d'échec connus (`01_EXEMPLE/`, `tests/`) et la preuve
  qu'il les détecte.
- **Refuser plutôt que deviner** : une clé inconnue, une colonne en double, une
  tolérance pour une sortie non déclarée ou une entrée absente du test sont des
  erreurs, pas des avertissements.
