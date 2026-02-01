# Plan d'Implémentation du Framework CFD

**Auteur**: KL  
**Date**: 2026-01-26  
**Version**: 1.0  

---

## Table des Matières

1. [Vue d'Ensemble](#vue-densemble)
2. [Architecture Globale](#architecture-globale)
3. [Conventions de Nommage](#conventions-de-nommage)
4. [Phases d'Implémentation](#phases-dimplémentation)
5. [Sprints et Priorités](#sprints-et-priorités)
6. [Exemples de Configuration](#exemples-de-configuration)

---

## Vue d'Ensemble

### Objectifs du Framework

Le framework CFD doit permettre de :

- ✅ **Gérer des cas tests uniques** (debug, mise au point interactive)
- ✅ **Automatiser des études paramétriques** à grande échelle
- ✅ **Assurer la traçabilité et la reproductibilité** des calculs
- ✅ **Maintenir une organisation standardisée** des données et scripts
- ✅ **Rester code-agnostique** via un système d'adaptateurs

### Principes de Conception

1. **Code-agnostique** : L'architecture reste indépendante du solveur CFD utilisé
2. **Scripts Bash** : Tous les scripts en bash sauf si techniquement impossible
3. **Nomenclature française** : Noms standardisés et professionnels en français
4. **Réutilisabilité** : Bibliothèques et scripts génériques centralisés
5. **Traçabilité** : Versionnement git et horodatage systématique

---

## Architecture Globale

### Structure Racine du CFD_FRAMEWORK

```
CFD_FRAMEWORK/
├── bin/                          # Exécutables principaux
│   ├── cfd-creer                 # Création de cas / ou reconnection tmux à un cas-test
│   ├── cfd-lancer                # Lancer un calcul
│   ├── cfd-surveiller            # Surveiller un calcul en cours
│   ├── cfd-archiver              # Archiver des résultats
│   ├── cfd-post-traiter          # Post-traiter un cas
│   └── cfd-deployer              # Préparer un cas pour déploiement
├── lib/                          # Bibliothèques bash réutilisables
│   ├── format.sh                 # Formatage/logging
│   ├── gestion_config.sh         # Chargement/validation configuration
│   ├── substitution_params.sh    # Substitution paramètres dans templates .org
│   ├── gestion_timestamps.sh     # Création/gestion répertoires horodatés
│   ├── surveillance.sh           # Fonctions de monitoring
│   └── utils.sh                  # Utilitaires généraux
├── adaptateurs/                  # Adaptateurs spécifiques par code CFD
│   ├── interface.sh              # Interface commune (contrat)
│   ├── mock.sh                   # Adapteur de test/dev
│   ├── openfoam/
│   │   ├── adaptateur.sh
│   │   ├── templates/
│   │   └── config.yaml
│   ├── su2/
│   └── fluent/
├── scripts/                      # Scripts d'orchestration
│   ├── lancement/
│   │   ├── lancer_cas_unique.sh
│   │   ├── lancer_etude_parametrique.sh
│   │   └── generer_jeu_donnees.sh
│   ├── post_traitement/
│   │   ├── executer_post_traitement.sh
│   │   ├── deplacer_donnees.sh
│   │   └── post_traiter_configuration.sh
│   ├── archivage/
│   │   ├── deplacer_resultats.sh
│   │   ├── compresser_cas.sh
│   │   └── nettoyer_temporaires.sh
│   └── deploiement/
│       └── preparer_deploiement.sh
├── templates/                    # Templates normalisés
│   └── TEMPLATE_CASE/           
│       ├── 01_MAILLAGE/
│       ├── 02_PARAMS/
│       ├── 03_DECOMPOSITION/
│       ├── 04_CONDITION_INITIALE/
│       ├── 05_DOCUMENTATION/
│       ├── 06_REFERENCE/
│       ├── 07_NOTE/
│       ├── 08_RESULTAT/
│       ├── 09_POST_TRAITEMENT/
│       │   ├── DATA/
│       │   └── FIGURE/
│       └── 10_SCRIPT/
│           ├── LANCEMENT_CALCUL/
│           └── POST_TRAITEMENT/
├── docs/                         # Documentation
│   ├── installation.md
│   ├── guide_utilisateur.md
│   ├── plan_implementation.md    # Ce document
│   └── adaptateurs/
│       └── creer_adaptateur.md
└── tests/                        # Tests du framework
```

---

## Conventions de Nommage

### Fichiers et Répertoires

| Type | Convention | Exemple |
|------|------------|---------|
| Scripts bash | `snake_case.sh` | `lancer_cas_unique.sh` |
| Exécutables CLI | `cfd-action` (kebab-case) | `cfd-lancer` |
| Templates | `nom_fichier.org` | `solver_input.org` |
| Configuration | `nom_fichier.yaml` | `config.yaml` |
| Répertoires | `MAJUSCULES_SNAKE` | `02_PARAMS/` |

### Fonctions Bash (standardisées et professionnelles)

Les fonctions sont organisées par préfixe pour faciliter la lecture et la maintenance :

| Préfixe | Catégorie | Exemples |
|---------|-----------|----------|
| `cfg_*` | Configuration | `cfg_charger`, `cfg_valider`, `cfg_obtenir_valeur` |
| `cas_*` | Gestion cas | `cas_creer`, `cas_archiver`, `cas_lister` |
| `calc_*` | Calculs | `calc_lancer`, `calc_surveiller`, `calc_arreter` |
| `pp_*` | Post-traitement | `pp_executer`, `pp_extraire_donnees` |
| `param_*` | Paramètres | `param_substituer`, `param_valider` |
| `ts_*` | Timestamps | `ts_creer_repertoire`, `ts_formater`, `ts_supprimer` |
| `adapt_*` | Adaptateurs | `adapt_charger`, `adapt_executer`, `adapt_verifier` |
| `util_*` | Utilitaires | `util_verifier_dependances`, `util_resoudre_liens` |
| `log_*` | Logging | `_info`, `_warn`, `_error` (depuis format.sh) |
| `surv_*` | Surveillance | `surv_analyser_residus`, `surv_calculer_qoi` |

### Variables d'Environnement

| Variable | Description | Exemple |
|----------|-------------|---------|
| `CFD_FRAMEWORK` | Chemin racine du framework | `/path/to/CFD_FRAMEWORK` |
| `CFD_ADAPTATEUR` | Adaptateur à utiliser | `openfoam`, `su2`, `mock` |
| `CASE_NAME` | Nom du cas test en cours | `NACA0012` |
| `VERBOSE` | Niveau de verbosité (0-2) | `2` |

---

## Phases d'Implémentation

### Phase 1 : Bibliothèques Bash Core 📚

#### 1.1 Enrichir `lib/format.sh` ✅

**Objectif** : Ajouter des fonctions de formatage spécifiques au workflow CFD

**Fonctions à ajouter** :
```bash
# Gestion état de progression
progres_init()       # Initialiser barre de progression
progres_update()     # Mettre à jour progression (%)
progres_done()       # Terminer progression

# Confirmations utilisateur
confirmer()          # Demander confirmation (oui/non)
choisir_option()     # Menu de choix numéroté

# Titres spécifiques CFD
titre_surveillance()          # Titre pour surveillance
titre_archivage()             # Titre pour archivage
titre_deploiement()           # Titre pour déploiement
```

**Complexité** : Faible  
**Dépendances** : Aucune  
**Fichiers modifiés** : `lib/format.sh`

---

#### 1.2 Créer `lib/gestion_config.sh`

**Objectif** : Gérer le chargement et la validation des fichiers de configuration YAML/ENV

**Fonctions principales** :
```bash
cfg_charger()               # Charger config.yaml d'un cas
cfg_obtenir_valeur()        # Extraire une valeur spécifique
cfg_lister_configurations() # Lister toutes les configs (BASELINE, etc.)
cfg_valider_schema()        # Valider structure YAML
cfg_exporter_env()          # Exporter en variables d'environnement
cfg_afficher()              # Afficher config formatée
```

**Approche technique** :
- Utiliser `yq` si disponible (recommandé)
- Fallback sur parser bash pur si `yq` non installé
- Format supporté : YAML, ENV (fichier `.env`)

**Complexité** : Moyenne  
**Dépendances** : `yq` (optionnel)  
**Fichiers créés** : `lib/gestion_config.sh`

---

#### 1.3 Créer `lib/substitution_params.sh`

**Objectif** : Substituer les paramètres dans les fichiers templates `.org`

**Fonctions principales** :
```bash
param_substituer_tout()      # Substituer tous les paramètres d'un template
param_trouver_balises()      # Identifier toutes les balises dans .org
param_remplacer_balise()     # Remplacer une balise spécifique
param_valider_template()     # Vérifier cohérence template/config
```

**Format des balises** :
- Format recommandé : `@PARAM_NAME@`
- Alternative : `{{PARAM_NAME}}`

**Exemple** :
```bash
# Template (solver_input.org)
angle_of_attack = @ANGLE_ATTAQUE@
reynolds = @REYNOLDS@

# Après substitution (solver_input)
angle_of_attack = 5.0
reynolds = 6000000.0
```

**Complexité** : Moyenne  
**Dépendances** : `sed`, `awk`  
**Fichiers créés** : `lib/substitution_params.sh`

---

#### 1.4 Créer `lib/gestion_timestamps.sh`

**Objectif** : Gérer la création et manipulation des répertoires horodatés

**Fonctions principales** :
```bash
ts_generer()                 # Générer timestamp (YYYYMMDD_HHMMSS)
ts_creer_repertoire()        # Créer répertoire avec timestamp
ts_supprimer_timestamp()     # Retirer timestamp d'un nom
ts_extraire_timestamp()      # Extraire timestamp d'un chemin
ts_trier_par_date()          # Trier répertoires par timestamp
ts_plus_recent()             # Obtenir répertoire le plus récent
```

**Format timestamp** : `YYYYMMDD_HHMMSS`  
**Exemple** : `BASELINE_20260126_143052`

**Complexité** : Faible  
**Dépendances** : `date`  
**Fichiers créés** : `lib/gestion_timestamps.sh`

---

#### 1.5 Créer `lib/surveillance.sh`

**Objectif** : Fonctions de monitoring des calculs en cours

**Fonctions principales** :
```bash
surv_lister_fichiers()       # Lister fichiers dans répertoire exécution
surv_suivre_listing()        # Tail du fichier listing
surv_analyser_residus()      # Analyser et afficher résidus
surv_calculer_qoi()          # Calculer quantités d'intérêt
surv_estimer_temps_restant() # Estimer temps restant basé sur progression
surv_verifier_convergence()  # Vérifier critères convergence
```

**Note** : Ces fonctions appellent l'adaptateur pour extraire les données spécifiques au solveur

**Complexité** : Élevée  
**Dépendances** : Adaptateurs  
**Fichiers créés** : `lib/surveillance.sh`

---

#### 1.6 Créer `lib/utils.sh`

**Objectif** : Utilitaires généraux réutilisables

**Fonctions principales** :
```bash
util_verifier_dependances()  # Vérifier présence outils (rsync, yq, git, etc)
util_resoudre_liens()        # Résoudre liens symboliques -> fichiers réels
util_copier_recursif()       # Copie récursive intelligente (rsync/cp)
util_obtenir_taille()        # Obtenir taille répertoire (human-readable)
util_nettoyer_chemin()       # Normaliser chemin (absolu, sans //)
util_verifier_repertoire()   # Vérifier structure répertoire cas test
```

**Complexité** : Faible  
**Dépendances** : `rsync` (optionnel), `du`, `realpath`  
**Fichiers créés** : `lib/utils.sh`

---

### Phase 2 : Système d'Adaptateurs 🔌

#### 2.1 Créer `adaptateurs/interface.sh`

**Objectif** : Définir le contrat que tous les adaptateurs doivent respecter

**Interface commune** :
```bash
#!/usr/bin/env bash
# Interface commune - tous les adaptateurs doivent implémenter ces fonctions

# Informations adaptateur
adapt_nom()                  # Retourne nom du solveur
adapt_version()              # Retourne version
adapt_description()          # Description courte

# Vérifications
adapt_verifier_installation() # Vérifie que le solveur est installé

# Préparation et lancement
adapt_preparer_entree()      # Préparer fichiers d'entrée
adapt_lancer_calcul()        # Lancer le solveur
adapt_lancer_parallele()     # Lancer en parallèle

# Monitoring
adapt_verifier_etat()        # Vérifier état calcul (running/done/failed)
adapt_extraire_residus()     # Extraire résidus pour monitoring
adapt_extraire_qoi()         # Extraire quantités d'intérêt
adapt_obtenir_iteration()    # Obtenir itération courante

# Post-traitement
adapt_extraire_champs()      # Extraire champs pour ParaView/Tecplot
adapt_nettoyer()             # Nettoyer fichiers temporaires
```

**Complexité** : Moyenne  
**Fichiers créés** : `adaptateurs/interface.sh`

---

#### 2.2 Créer `adaptateurs/mock.sh`

**Objectif** : Adaptateur de test/développement qui simule un solveur

**Fonctionnalités** :
- Simule un calcul avec sleep et progression
- Génère des résidus factices
- Crée des fichiers de sortie fictifs
- Permet de tester le framework sans solveur réel

**Utilisation** :
```bash
export CFD_ADAPTATEUR="mock"
cfd-lancer --config BASELINE
```

**Complexité** : Moyenne  
**Fichiers créés** : `adaptateurs/mock.sh`

---

#### 2.3 Structure type d'un Adaptateur

Exemple pour OpenFOAM :

```
adaptateurs/openfoam/
├── adaptateur.sh             # Implémentation interface
├── templates/                # Templates spécifiques OpenFOAM
│   ├── controlDict.org
│   ├── fvSchemes.org
│   ├── fvSolution.org
│   └── decomposeParDict.org
├── config.yaml               # Configuration par défaut
└── README.md                 # Documentation adaptateur
```

**Fichier `adaptateur.sh`** :
```bash
#!/usr/bin/env bash
source "${CFD_FRAMEWORK}/adaptateurs/interface.sh"

adapt_nom() { echo "OpenFOAM"; }
adapt_version() { openfoam -version 2>/dev/null || echo "unknown"; }

adapt_lancer_calcul() {
    local rep_cas="$1"
    local nb_procs="${2:-1}"
    
    cd "$rep_cas" || return 1
    
    if [[ $nb_procs -gt 1 ]]; then
        mpirun -np "$nb_procs" simpleFoam -parallel > log.simpleFoam 2>&1
    else
        simpleFoam > log.simpleFoam 2>&1
    fi
}

# ... autres fonctions
```

---

### Phase 3 : Scripts de Lancement 🚀

#### 3.1 Créer `scripts/lancement/lancer_cas_unique.sh`

**Objectif** : Lancer un cas CFD unique avec timestamp

**Fonction principale** :
```bash
lancer_cas_unique() {
    local repertoire_config="$1"  # 02_PARAMS/BASELINE
    local nom_cas="$2"             # CASE_1 (optionnel si spécifié dans config)
    
    h1 "Lancement cas unique"
    
    # 1. Générer timestamp
    local timestamp=$(ts_generer)
    local nom_exec="${nom_cas}_${timestamp}"
    local rep_exec="${repertoire_config}/${nom_exec}"
    
    _info "Création répertoire : ${rep_exec}"
    mkdir -p "$rep_exec"
    
    # 2. Copier données configuration
    _info "Copie données de configuration..."
    util_copier_recursif "${repertoire_config}/template/" "$rep_exec/"
    
    # 3. Charger configuration
    cfg_charger "${rep_exec}/config.yaml"
    
    # 4. Charger adaptateur
    local adaptateur="${CFD_ADAPTATEUR:-mock}"
    source "${CFD_FRAMEWORK}/adaptateurs/${adaptateur}/adaptateur.sh"
    
    # 5. Préparer entrée via adaptateur
    _info "Préparation entrée avec adaptateur $(adapt_nom)..."
    adapt_preparer_entree "$rep_exec"
    
    # 6. Lancer calcul
    _info "Lancement du calcul..."
    adapt_lancer_calcul "$rep_exec"
    
    # 7. Logger informations
    echo "$timestamp" > "${rep_exec}/.timestamp"
    
    _result "Calcul lancé : ${rep_exec}"
}
```

**Complexité** : Moyenne  
**Dépendances** : `lib/gestion_timestamps.sh`, `lib/gestion_config.sh`, adaptateurs  
**Fichiers créés** : `scripts/lancement/lancer_cas_unique.sh`

---

#### 3.2 Créer `scripts/lancement/generer_jeu_donnees.sh`

**Objectif** : Générer jeu de données pour une configuration en substituant paramètres

**Fonction principale** :
```bash
generer_jeu_donnees() {
    local template_dir="$1"    # Répertoire avec fichiers .org
    local output_dir="$2"      # Répertoire de sortie
    local config_file="$3"     # Fichier avec paramètres (YAML/ENV)
    
    h2 "Génération jeu de données"
    
    # 1. Charger paramètres
    cfg_charger "$config_file"
    
    # 2. Lister tous les fichiers .org
    local templates=($(find "$template_dir" -name "*.org"))
    
    _info "Trouvé ${#templates[@]} templates à traiter"
    
    # 3. Pour chaque template
    for template in "${templates[@]}"; do
        local output="${output_dir}/$(basename ${template%.org})"
        
        _debug "Traitement : $template -> $output"
        
        # 4. Substituer paramètres
        param_substituer_tout "$template" "$output" "$config_file"
        
        _bullet "Généré : $(basename $output)"
    done
    
    # 5. Valider fichiers générés
    _info "Validation des fichiers générés..."
    # TODO: validation spécifique
    
    _result "Jeu de données généré dans : $output_dir"
}
```

**Complexité** : Moyenne  
**Dépendances** : `lib/substitution_params.sh`, `lib/gestion_config.sh`  
**Fichiers créés** : `scripts/lancement/generer_jeu_donnees.sh`

---

#### 3.3 Créer `scripts/lancement/lancer_etude_parametrique.sh`

**Objectif** : Lancer une étude paramétrique complète en lisant config.yaml

**Fonction principale** :
```bash
lancer_etude_parametrique() {
    local fichier_config="$1"  # 02_PARAMS/config.yaml
    local config_name="$2"     # BASELINE, ANGLE_OF_ATTACK, etc.
    local parallele="${3:-false}"
    
    titre_launch_simulation
    h1 "Étude paramétrique : ${config_name}"
    
    # 1. Charger fichier config.yaml
    cfg_charger "$fichier_config"
    
    # 2. Extraire liste des cas pour cette configuration
    local nb_cas=$(cfg_obtenir_valeur "configurations.${config_name}.cas" | wc -l)
    
    _info "Nombre de cas à lancer : $nb_cas"
    
    # 3. Créer répertoire de configuration
    local base_dir="02_PARAMS/${config_name}"
    mkdir -p "$base_dir"
    
    # 4. Pour chaque cas
    local cas_list=($(cfg_lister_cas "$config_name"))
    
    if [[ "$parallele" == "true" ]]; then
        _info "Lancement en parallèle avec GNU Parallel"
        printf '%s\n' "${cas_list[@]}" | parallel -j 4 lancer_un_cas {}
    else
        for cas in "${cas_list[@]}"; do
            lancer_un_cas "$cas"
        done
    fi
    
    _result "Étude paramétrique terminée"
}

lancer_un_cas() {
    local cas="$1"
    # Appelle lancer_cas_unique avec les bons paramètres
}
```

**Complexité** : Élevée  
**Dépendances** : `lancer_cas_unique.sh`, `generer_jeu_donnees.sh`, `GNU Parallel` (optionnel)  
**Fichiers créés** : `scripts/lancement/lancer_etude_parametrique.sh`

---

### Phase 4 : Scripts de Surveillance 👁️

#### 4.1 Créer `bin/cfd-surveiller`

**Objectif** : CLI pour surveiller un calcul en cours

**Usage** :
```bash
cfd-surveiller [OPTIONS] REPERTOIRE_CALCUL

Options:
  -l, --listing       Suivre le listing (tail -f)
  -r, --residus       Afficher résidus
  -q, --qoi           Afficher QoI
  -t, --temps         Estimer temps restant
  -a, --all           Tout surveiller (dashboard)
  -h, --help          Afficher aide
```

**Implementation** :
```bash
#!/usr/bin/env bash

source "${CFD_FRAMEWORK}/lib/format.sh"
source "${CFD_FRAMEWORK}/lib/surveillance.sh"

surveiller_calcul() {
    local rep_calcul="$1"
    local mode="${2:-all}"
    
    titre_surveillance
    
    case "$mode" in
        "listing")
            surv_suivre_listing "$rep_calcul"
            ;;
        "residus")
            surv_analyser_residus "$rep_calcul"
            ;;
        "qoi")
            surv_calculer_qoi "$rep_calcul"
            ;;
        "temps")
            surv_estimer_temps_restant "$rep_calcul"
            ;;
        "all")
            # Dashboard complet avec rafraîchissement
            while true; do
                clear
                titre_surveillance
                h2 "État du calcul"
                surv_lister_fichiers "$rep_calcul"
                h2 "Résidus"
                surv_analyser_residus "$rep_calcul"
                h2 "Quantités d'Intérêt"
                surv_calculer_qoi "$rep_calcul"
                h2 "Temps restant estimé"
                surv_estimer_temps_restant "$rep_calcul"
                sleep 5
            done
            ;;
    esac
}
```

**Complexité** : Élevée  
**Dépendances** : `lib/surveillance.sh`  
**Fichiers créés** : `bin/cfd-surveiller`

---

### Phase 5 : Scripts d'Archivage 💾

#### 5.1 Créer `scripts/archivage/deplacer_resultats.sh`

**Objectif** : Implémenter le script `mvResults` (déplacer de 02_PARAMS vers 08_RESULTAT)

**Fonction principale** :
```bash
deplacer_resultats() {
    local source="$1"          # 02_PARAMS/BASELINE/CAS_1_20260126_143052
    local config="$2"          # BASELINE
    local force="${3:-false}"  # --force pour écraser
    
    h1 "Déplacement des résultats"
    
    # 1. Vérifier source existe
    [[ -d "$source" ]] || die "Source inexistante : $source"
    
    # 2. Créer destination si inexistante
    local dest_base="08_RESULTAT/${config}"
    mkdir -p "$dest_base"
    
    # 3. Extraire nom sans timestamp
    local nom_cas=$(basename "$source")
    local nom_propre=$(ts_supprimer_timestamp "$nom_cas")
    
    local destination="${dest_base}/${nom_propre}"
    
    # 4. Gérer conflits
    if [[ -d "$destination" ]]; then
        if [[ "$force" == "true" ]]; then
            _warn "Écrasement de : $destination"
            rm -rf "$destination"
        else
            _warn "Destination existe, conservation du timestamp"
            destination="${dest_base}/${nom_cas}"
        fi
    fi
    
    # 5. Déplacer
    _info "Déplacement : $source -> $destination"
    mv "$source" "$destination"
    
    _result "Résultats archivés : $destination"
}
```

**Usage** :
```bash
deplacer_resultats "02_PARAMS/BASELINE/CAS_1_20260126_143052" "BASELINE"
deplacer_resultats "02_PARAMS/BASELINE/CAS_1_20260126_143052" "BASELINE" "--force"
```

**Complexité** : Moyenne  
**Dépendances** : `lib/gestion_timestamps.sh`  
**Fichiers créés** : `scripts/archivage/deplacer_resultats.sh`

---

#### 5.2 Créer `scripts/archivage/compresser_cas.sh`

**Objectif** : Compresser un cas ou une configuration

**Fonction principale** :
```bash
compresser_cas() {
    local repertoire="$1"
    local sortie="${2:-${repertoire}.tar.gz}"
    local exclure_volumineux="${3:-false}"
    
    h1 "Compression du cas"
    
    _info "Répertoire : $repertoire"
    _info "Archive : $sortie"
    
    # Liste des exclusions
    local exclusions=()
    if [[ "$exclure_volumineux" == "true" ]]; then
        exclusions+=(
            "--exclude=*.vtk"
            "--exclude=*.vtu"
            "--exclude=processor*"
        )
    fi
    
    # Compression
    tar -czf "$sortie" "${exclusions[@]}" -C "$(dirname $repertoire)" "$(basename $repertoire)"
    
    local taille=$(util_obtenir_taille "$sortie")
    _result "Archive créée : $sortie ($taille)"
}
```

**Complexité** : Faible  
**Fichiers créés** : `scripts/archivage/compresser_cas.sh`

---

#### 5.3 Créer `bin/cfd-archiver`

**Objectif** : CLI unifié pour archivage

**Usage** :
```bash
cfd-archiver deplacer REPERTOIRE_SOURCE CONFIG [--force]
cfd-archiver compresser REPERTOIRE [SORTIE]
cfd-archiver nettoyer CONFIG  # Nettoie 02_PARAMS/CONFIG
```

**Complexité** : Moyenne  
**Fichiers créés** : `bin/cfd-archiver`

---

### Phase 6 : Scripts de Post-Traitement 📊

#### 6.1 Créer Template `PP.sh`

**Objectif** : Template standardisé pour post-traitement personnalisé

**Localisation** : `TEMPLATE_CASE/10_SCRIPT/POST_TRAITEMENT/PP.sh`

**Contenu** :
```bash
#!/usr/bin/env bash
# Template de post-traitement personnalisé
# Ce fichier doit être adapté pour chaque cas test

set -euo pipefail

# Charger bibliothèques
CFD_FRAMEWORK="${CFD_FRAMEWORK:-$(git rev-parse --show-toplevel)}"
source "${CFD_FRAMEWORK}/lib/format.sh"

titre_post_traitement

# ============================================================================
h1 "Configuration"
# ============================================================================

# Adapter ces variables selon le cas
LISTE_ITERATIONS="1000 2000 5000 10000"
FORMAT_SORTIE="csv"

_info "Format sortie : $FORMAT_SORTIE"

# ============================================================================
h1 "Extraction des données"
# ============================================================================

h2 "Chargement adaptateur"
ADAPTATEUR="${CFD_ADAPTATEUR:-mock}"
source "${CFD_FRAMEWORK}/adaptateurs/${ADAPTATEUR}/adaptateur.sh"
_info "Adaptateur : $(adapt_nom)"

h2 "Extraction résidus"
adapt_extraire_residus . > residus.${FORMAT_SORTIE}
_bullet "Résidus extraits : residus.${FORMAT_SORTIE}"

h2 "Extraction QoI"
adapt_extraire_qoi . > qoi.${FORMAT_SORTIE}
_bullet "QoI extraits : qoi.${FORMAT_SORTIE}"

# ============================================================================
h1 "Traitement spécifique"
# ============================================================================

# TODO: Ajouter traitement spécifique (Python, ParaView, etc.)
# Exemple:
# python3 extract_cp.py
# pvpython macro_iso_surface.py

# ============================================================================
h1 "Génération des graphiques"
# ============================================================================

# TODO: Générer graphiques (gnuplot, matplotlib, etc.)
# Exemple:
# gnuplot plot_residuals.gp
# python3 plot_polar.py

# ============================================================================
h1 "Export des résultats"
# ============================================================================

_info "Résultats disponibles dans le répertoire courant"
ls -lh *.${FORMAT_SORTIE} 2>/dev/null || true

_result "Post-traitement terminé"
```

**Complexité** : Moyenne  
**Fichiers créés** : `templates/TEMPLATE_CASE/10_SCRIPT/POST_TRAITEMENT/PP.sh`

---

#### 6.2 Créer `scripts/post_traitement/executer_post_traitement.sh`

**Objectif** : Exécuter PP.sh et movingDATA.sh pour un cas donné

**Fonction principale** :
```bash
executer_post_traitement() {
    local repertoire_cas="$1"
    
    h1 "Exécution post-traitement"
    _info "Cas : $repertoire_cas"
    
    cd "${repertoire_cas}" || die "Impossible d'accéder à ${repertoire_cas}"
    
    # 1. Exécuter PP.sh
    if [[ -f "./PP.sh" ]]; then
        h2 "Exécution PP.sh"
        bash PP.sh
    else
        _warn "PP.sh non trouvé, ignoré"
    fi
    
    # 2. Exécuter movingDATA.sh
    if [[ -f "./movingDATA.sh" ]]; then
        h2 "Exécution movingDATA.sh"
        bash movingDATA.sh
    else
        _warn "movingDATA.sh non trouvé, ignoré"
    fi
    
    cd - > /dev/null
    _result "Post-traitement terminé pour : $repertoire_cas"
}
```

**Complexité** : Faible  
**Fichiers créés** : `scripts/post_traitement/executer_post_traitement.sh`

---

#### 6.3 Créer `scripts/post_traitement/post_traiter_configuration.sh`

**Objectif** : Post-traiter tous les cas d'une configuration (avec parallélisation)

**Fonction principale** :
```bash
post_traiter_configuration() {
    local repertoire_config="$1"  # 08_RESULTAT/BASELINE
    local parallele="${2:-false}"
    
    h1 "Post-traitement configuration"
    _info "Configuration : $repertoire_config"
    
    # Lister tous les cas
    local cas_list=($(find "$repertoire_config" -mindepth 1 -maxdepth 1 -type d))
    local nb_cas=${#cas_list[@]}
    
    _info "Nombre de cas à traiter : $nb_cas"
    
    if [[ "$parallele" == "true" ]]; then
        _info "Traitement en parallèle"
        printf '%s\n' "${cas_list[@]}" | \
            parallel -j 4 "${CFD_FRAMEWORK}/scripts/post_traitement/executer_post_traitement.sh {}"
    else
        for cas in "${cas_list[@]}"; do
            executer_post_traitement "$cas"
        done
    fi
    
    _result "Post-traitement configuration terminé"
}
```

**Complexité** : Moyenne  
**Dépendances** : `GNU Parallel` (optionnel)  
**Fichiers créés** : `scripts/post_traitement/post_traiter_configuration.sh`

---

### Phase 7 : Déploiement 📦

#### 7.1 Créer `scripts/deploiement/preparer_deploiement.sh`

**Objectif** : Implémenter le runbook de déploiement (packaging pour transfert)

**Fonction principale** :
```bash
preparer_deploiement() {
    local cas_source="$1"
    local sortie="${2:-${cas_source}_deploy.tar.gz}"
    
    titre_deploiement
    h1 "Préparation déploiement"
    
    # ================================================================
    h2 "1. Duplication du cas"
    # ================================================================
    local tmp_dir=$(mktemp -d)
    local nom_cas=$(basename "$cas_source")
    local cas_tmp="${tmp_dir}/${nom_cas}"
    
    _info "Copie vers : $cas_tmp"
    util_copier_recursif "$cas_source" "$cas_tmp"
    
    # ================================================================
    h2 "2. Suppression des résultats"
    # ================================================================
    _info "Nettoyage 02_PARAMS..."
    find "$cas_tmp/02_PARAMS" -type d -name "*_[0-9]*" -exec rm -rf {} + 2>/dev/null || true
    
    _info "Nettoyage 08_RESULTAT..."
    rm -rf "$cas_tmp/08_RESULTAT/"* 2>/dev/null || true
    
    _info "Nettoyage 09_POST_TRAITEMENT..."
    rm -rf "$cas_tmp/09_POST_TRAITEMENT/DATA/"* 2>/dev/null || true
    rm -rf "$cas_tmp/09_POST_TRAITEMENT/FIGURE/"* 2>/dev/null || true
    
    # ================================================================
    h2 "3. Nettoyage développement"
    # ================================================================
    _info "Suppression .git et fichiers dev..."
    rm -rf "$cas_tmp/.git" "$cas_tmp/.gitignore" 2>/dev/null || true
    find "$cas_tmp" -name "*.bak" -o -name "*~" -delete 2>/dev/null || true
    
    # ================================================================
    h2 "4. Résolution des liens symboliques"
    # ================================================================
    _info "Résolution des liens vers fichiers réels..."
    util_resoudre_liens "$cas_tmp"
    
    # ================================================================
    h2 "5. Vérification reproductibilité"
    # ================================================================
    _info "Vérification fichiers essentiels..."
    util_verifier_repertoire "$cas_tmp"
    
    # ================================================================
    h2 "6. Packaging"
    # ================================================================
    _info "Création archive : $sortie"
    tar -czf "$sortie" -C "$tmp_dir" "$nom_cas"
    
    # Nettoyage
    rm -rf "$tmp_dir"
    
    local taille=$(util_obtenir_taille "$sortie")
    _result "Cas déployable créé : $sortie ($taille)"
}
```

**Complexité** : Moyenne  
**Fichiers créés** : `scripts/deploiement/preparer_deploiement.sh`

---

### Phase 8 : CLI Unifiée 🖥️

#### 8.1 Créer les Binaires CLI

Tous les exécutables dans `bin/` suivent le même pattern :

##### `bin/cfd-lancer`
```bash
#!/usr/bin/env bash
# Lancer un calcul CFD

source "${CFD_FRAMEWORK}/lib/format.sh"
source "${CFD_FRAMEWORK}/scripts/lancement/lancer_cas_unique.sh"
source "${CFD_FRAMEWORK}/scripts/lancement/lancer_etude_parametrique.sh"

usage() {
    cat <<EOF
Usage: cfd-lancer [OPTIONS] CONFIG

Lancer un calcul CFD

OPTIONS:
  --cas NOM           Lancer un cas spécifique
  --parametrique      Lancer étude paramétrique complète
  --parallele         Paralléliser les lancements
  -h, --help          Afficher cette aide

EXEMPLES:
  cfd-lancer BASELINE --cas CASE_1
  cfd-lancer ANGLE_OF_ATTACK --parametrique --parallele
EOF
}

# Parse arguments et dispatch vers bonnes fonctions
```

##### `bin/cfd-post-traiter`
```bash
#!/usr/bin/env bash
# Post-traiter un calcul CFD

# Structure similaire
```

**Fichiers créés** :
- `bin/cfd-lancer`
- `bin/cfd-surveiller`
- `bin/cfd-archiver`
- `bin/cfd-post-traiter`
- `bin/cfd-deployer`

---

#### 8.2 Créer `Makefile` Template

**Localisation** : `templates/TEMPLATE_CASE/Makefile`

**Contenu** :
```makefile
# Makefile pour cas CFD
# Facilite l'exécution des tâches courantes

# ============================================================================
# Configuration
# ============================================================================

CFD_FRAMEWORK ?= $(shell git rev-parse --show-toplevel 2>/dev/null || echo "../CFD_FRAMEWORK")
CONFIG ?= BASELINE
CAS ?= 
ADAPTATEUR ?= mock

export CFD_FRAMEWORK
export CFD_ADAPTATEUR = $(ADAPTATEUR)

# ============================================================================
# Targets
# ============================================================================

.PHONY: help lancer lancer-parametrique surveiller post-traiter archiver nettoyer deployer

help:
	@echo "Makefile pour cas CFD"
	@echo ""
	@echo "Targets disponibles:"
	@echo "  lancer               Lancer un calcul (CONFIG=$(CONFIG))"
	@echo "  lancer-parametrique  Lancer étude paramétrique (CONFIG=$(CONFIG))"
	@echo "  surveiller           Surveiller dernier calcul"
	@echo "  post-traiter         Post-traiter résultats (CONFIG=$(CONFIG))"
	@echo "  archiver             Archiver résultats (CONFIG=$(CONFIG))"
	@echo "  nettoyer             Nettoyer temporaires (CONFIG=$(CONFIG))"
	@echo "  deployer             Préparer déploiement"
	@echo ""
	@echo "Variables:"
	@echo "  CONFIG=$(CONFIG)"
	@echo "  ADAPTATEUR=$(ADAPTATEUR)"

lancer:
	@$(CFD_FRAMEWORK)/bin/cfd-lancer $(CONFIG) $(if $(CAS),--cas $(CAS),)

lancer-parametrique:
	@$(CFD_FRAMEWORK)/bin/cfd-lancer $(CONFIG) --parametrique

surveiller:
	@$(CFD_FRAMEWORK)/bin/cfd-surveiller --all $$(ls -td 02_PARAMS/$(CONFIG)/*/ | head -1)

post-traiter:
	@$(CFD_FRAMEWORK)/bin/cfd-post-traiter $(CONFIG)

archiver:
	@$(CFD_FRAMEWORK)/bin/cfd-archiver deplacer 02_PARAMS/$(CONFIG) 08_RESULTAT/$(CONFIG)

nettoyer:
	@rm -rf 02_PARAMS/$(CONFIG)/*_[0-9]*
	@echo "✅ Temporaires nettoyés"

deployer:
	@$(CFD_FRAMEWORK)/bin/cfd-deployer .
```

**Complexité** : Faible  
**Fichiers créés** : `templates/TEMPLATE_CASE/Makefile`

---

### Phase 9 : Documentation 📖

#### 9.1 Créer Documentation

**Fichiers à créer** :

##### `docs/installation.md`
- Prérequis système
- Installation du framework
- Configuration initiale
- Vérification installation

##### `docs/guide_utilisateur.md`
- Workflow complet
- Création d'un cas
- Lancement de calculs
- Surveillance
- Post-traitement
- Archivage

##### `docs/adaptateurs/creer_adaptateur.md`
- Structure d'un adaptateur
- Interface à implémenter
- Exemples
- Bonnes pratiques

---

#### 9.2 Enrichir `.gitignore`

**Localisation** : `templates/TEMPLATE_CASE/.gitignore`

```gitignore
# ============================================================================
# Résultats de calculs
# ============================================================================

# Calculs temporaires
02_PARAMS/*/CAS_*
02_PARAMS/*/*/*_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_*

# Résultats archivés (optionnel selon stratégie)
08_RESULTAT/*/

# ============================================================================
# Post-traitement
# ============================================================================

09_POST_TRAITEMENT/DATA/
09_POST_TRAITEMENT/FIGURE/

# ============================================================================
# Fichiers temporaires
# ============================================================================

*.log
*.err
*.tmp
*.bak
*~
.*.swp

# ============================================================================
# Spécifique solveurs
# ============================================================================

# OpenFOAM
processor*/
*.foam
postProcessing/

# SU2
forces_*.csv
history_*.csv

# ============================================================================
# Divers
# ============================================================================

.DS_Store
Thumbs.db
```

---

## Sprints et Priorités

### Sprint 1 : Fondations (Priorité ⭐⭐⭐ Haute)

**Objectif** : Mettre en place les bibliothèques core et le système d'adaptateurs

**Tâches** :
- [ ] Enrichir `lib/format.sh` (nouvelles fonctions)
- [ ] Créer `lib/gestion_config.sh`
- [ ] Créer `lib/substitution_params.sh`
- [ ] Créer `lib/gestion_timestamps.sh`
- [ ] Créer `lib/utils.sh`
- [ ] Créer `adaptateurs/interface.sh`
- [ ] Créer `adaptateurs/mock.sh`

**Durée estimée** : 3-4 jours  
**Validation** : Tests unitaires sur chaque bibliothèque

---

### Sprint 2 : Lancement de Calculs (Priorité ⭐⭐⭐ Haute)

**Objectif** : Permettre le lancement de cas uniques

**Tâches** :
- [ ] Créer `scripts/lancement/lancer_cas_unique.sh`
- [ ] Créer `scripts/lancement/generer_jeu_donnees.sh`
- [ ] Créer `bin/cfd-lancer` (cas unique)
- [ ] Tester avec adaptateur mock

**Durée estimée** : 2-3 jours  
**Validation** : Lancer un cas mock du début à la fin

---

### Sprint 3 : Archivage (Priorité ⭐⭐ Moyenne)

**Objectif** : Gérer le déplacement et la compression des résultats

**Tâches** :
- [ ] Créer `scripts/archivage/deplacer_resultats.sh`
- [ ] Créer `scripts/archivage/compresser_cas.sh`
- [ ] Créer `bin/cfd-archiver`

**Durée estimée** : 1-2 jours  
**Validation** : Archiver un cas mock

---

### Sprint 4 : Surveillance (Priorité ⭐⭐ Moyenne)

**Objectif** : Permettre le monitoring des calculs en cours

**Tâches** :
- [ ] Créer `lib/surveillance.sh`
- [ ] Impl. surveillance dans adaptateur mock
- [ ] Créer `bin/cfd-surveiller`

**Durée estimée** : 2-3 jours  
**Validation** : Surveiller un calcul mock en temps réel

---

### Sprint 5 : Post-Traitement (Priorité ⭐⭐ Moyenne)

**Objectif** : Automatiser le post-traitement

**Tâches** :
- [ ] Créer template `PP.sh`
- [ ] Créer `scripts/post_traitement/executer_post_traitement.sh`
- [ ] Créer `scripts/post_traitement/post_traiter_configuration.sh`
- [ ] Créer `bin/cfd-post-traiter`

**Durée estimée** : 2-3 jours  
**Validation** : Post-traiter un cas mock

---

### Sprint 6 : Études Paramétriques (Priorité ⭐⭐⭐ Haute)

**Objectif** : Supporter les études paramétriques multi-cas

**Tâches** :
- [ ] Créer `scripts/lancement/lancer_etude_parametrique.sh`
- [ ] Enrichir `lib/gestion_config.sh` (parsing YAML complet)
- [ ] Supporter parallélisation (GNU Parallel)
- [ ] Enrichir `bin/cfd-lancer` (mode paramétrique)

**Durée estimée** : 3-4 jours  
**Validation** : Lancer étude paramétrique mock avec 5+ cas

---

### Sprint 7 : Déploiement (Priorité ⭐ Basse)

**Objectif** : Packaging pour transfert/collaboration

**Tâches** :
- [ ] Créer `scripts/deploiement/preparer_deploiement.sh`
- [ ] Créer `bin/cfd-deployer`

**Durée estimée** : 1-2 jours  
**Validation** : Déployer un cas et le relancer ailleurs

---

### Sprint 8 : Documentation & Polish (Priorité ⭐⭐ Moyenne)

**Objectif** : Finaliser documentation et outils

**Tâches** :
- [ ] Créer Makefile template
- [ ] Écrire `docs/installation.md`
- [ ] Écrire `docs/guide_utilisateur.md`
- [ ] Écrire `docs/adaptateurs/creer_adaptateur.md`
- [ ] Enrichir `.gitignore`
- [ ] Tests end-to-end complets

**Durée estimée** : 3-4 jours  
**Validation** : Utilisateur externe peut utiliser le framework

---

## Exemples de Configuration

### Exemple 1 : config.yaml Simple

```yaml
# 02_PARAMS/config.yaml

etude:
  nom: "Validation NACA0012"
  description: "Étude paramétrique angle d'attaque"
  date_creation: "2026-01-26"
  auteur: "KL"

# Adaptateur CFD à utiliser
adaptateur: "mock"

# Configuration des ressources
ressources:
  nb_coeurs: 8
  memoire: "16GB"
  temps_max: "24:00:00"
  partition: "compute"

# Configurations d'étude
configurations:
  BASELINE:
    description: "Configuration de référence"
    cas:
      - nom: "CASE_1"
        parametres:
          angle_attaque: 0.0
          reynolds: 6000000.0
          maillage: "mesh_coarse.cgns"
          nb_iterations: 10000
          
      - nom: "CASE_2"
        parametres:
          angle_attaque: 5.0
          reynolds: 6000000.0
          maillage: "mesh_coarse.cgns"
          nb_iterations: 10000
          
      - nom: "CASE_3"
        parametres:
          angle_attaque: 10.0
          reynolds: 6000000.0
          maillage: "mesh_medium.cgns"
          nb_iterations: 15000
```

---

### Exemple 2 : config.yaml Étude Paramétrique

```yaml
# 02_PARAMS/config.yaml

etude:
  nom: "Étude Reynolds NACA0012"
  description: "Influence du nombre de Reynolds"

adaptateur: "openfoam"

configurations:
  REYNOLDS:
    description: "Variation Reynolds à alpha=5°"
    parametres_fixes:
      angle_attaque: 5.0
      maillage: "mesh_fine.cgns"
      nb_iterations: 20000
      
    parametres_variables:
      reynolds: [1e6, 3e6, 6e6, 9e6, 12e6]
    
    # Les cas seront générés automatiquement:
    # REYNOLDS/RE_1E6, REYNOLDS/RE_3E6, etc.
    
  ANGLE_OF_ATTACK:
    description: "Variation angle d'attaque à Re=6M"
    parametres_fixes:
      reynolds: 6000000.0
      maillage: "mesh_medium.cgns"
      nb_iterations: 15000
      
    parametres_variables:
      angle_attaque: [-5, -2, 0, 2, 5, 8, 10, 12, 15]
```

---

### Exemple 3 : Template .org avec Balises

**Fichier** : `02_PARAMS/BASELINE/template/solver_input.org`

```
# CFD Solver Input File
# Generated from template

# Flow conditions
angle_of_attack = @ANGLE_ATTAQUE@
reynolds_number = @REYNOLDS@
mach_number = 0.15

# Mesh
mesh_file = "@MAILLAGE@"

# Solver parameters
max_iterations = @NB_ITERATIONS@
convergence_tolerance = 1e-6

# Output
output_frequency = 100
save_fields = true
```

**Après substitution** (par `param_substituer_tout`) :

```
# CFD Solver Input File
# Generated from template

# Flow conditions
angle_of_attack = 5.0
reynolds_number = 6000000.0
mach_number = 0.15

# Mesh
mesh_file = "mesh_medium.cgns"

# Solver parameters
max_iterations = 15000
convergence_tolerance = 1e-6

# Output
output_frequency = 100
save_fields = true
```

---

## Points de Vigilance

### Dépendances Externes

Le framework nécessite les outils suivants :

| Outil | Requis | Utilisation |
|-------|--------|-------------|
| `bash` ≥ 4.0 | ✅ Oui | Scripts |
| `git` | ✅ Oui | Versionnement |
| `yq` | ⚠️ Recommandé | Parsing YAML (fallback possible) |
| `rsync` | ⚠️ Recommandé | Copie efficace (fallback cp) |
| `GNU Parallel` | ❌ Optionnel | Parallélisation études |
| `tmux` | ⚠️ Recommandé | Sessions persistantes |

### Portabilité

- **Linux** : Support complet
- **macOS** : Compatible (tester GNU vs BSD tools)
- **Windows** : WSL2 requis

### Performance

- Substitution paramètres : O(n×m) où n=nb_fichiers, m=nb_paramètres
- Archivage : Temps proportionnel à taille des résultats
- Parallélisation recommandée pour études >10 cas

---

## Roadmap Future

### Version 1.0 (MVP)
- ✅ Sprints 1-6 completés
- ✅ Adaptateur mock fonctionnel
- ✅ Documentation de base

### Version 1.1
- Support adaptateur OpenFOAM
- Dashboard web de surveillance (optionnel)
- Amélioration gestion erreurs

### Version 2.0
- Support multi-adaptateurs simultanés
- Intégration CI/CD
- Matrice de couverture des cas tests
- Site web documentation (mkdocs)

---

## Conclusion

Ce plan d'implémentation fournit une roadmap complète pour développer le framework CFD.

**Ordre recommandé d'exécution** :
1. Sprint 1 (Fondations)
2. Sprint 2 (Lancement)
3. Sprint 6 (Études paramétriques)
4. Sprint 3 (Archivage)
5. Sprint 4 (Surveillance)
6. Sprint 5 (Post-traitement)
7. Sprint 8 (Documentation)
8. Sprint 7 (Déploiement)

**Durée totale estimée** : 18-24 jours de développement

---

**Document créé le** : 2026-01-26  
**Dernière mise à jour** : 2026-01-26  
**Auteur** : Assistant IA pour KL
