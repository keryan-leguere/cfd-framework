# Architecture du Framework / Framework Architecture

## 🏗️ Vue d'ensemble / Overview

Le CFD Framework adopte une architecture modulaire et extensible permettant de gérer différents solveurs CFD via un système d'adaptateurs.

The CFD Framework adopts a modular and extensible architecture enabling management of different CFD solvers through an adapter system.

---

## 📊 Architecture globale / Global Architecture

```mermaid
graph TB
    subgraph userLayer [👤 Couche Utilisateur / User Layer]
        User[Utilisateur<br/>User] -->|Commandes CLI<br/>CLI Commands| CLI[Interface CLI]
    end
    
    subgraph coreLayer [⚙️ Couche Core]
        CLI --> Creer[cfd-creer<br/>Case Creation]
        CLI --> Run[cfd-run<br/>Launch]
        CLI --> RunParam[cfd-run-parametrique<br/>Parametric]
        CLI --> Archive[cfd-archiver<br/>Archive]
        CLI --> Clean[cfd-clean-config<br/>Cleanup]
        
        Run --> WrapperSingle[wrapper_commande_lancement.sh]
        RunParam --> WrapperParam[lancement_parametrique_yaml.sh]
    end
    
    subgraph libLayer [📚 Bibliothèques / Libraries]
        WrapperSingle --> Format[format.sh<br/>Formatting]
        WrapperSingle --> Config[gestion_config.sh<br/>Configuration]
        WrapperSingle --> Timestamp[gestion_timestamps.sh<br/>Timestamps]
        WrapperSingle --> Utils[utils.sh<br/>Utilities]
        WrapperParam --> Params[substitution_params.sh<br/>Parameters]
    end
    
    subgraph adapterLayer [🔌 Couche Adaptateurs / Adapter Layer]
        WrapperSingle --> AdapterInterface[Interface Commune<br/>Common Interface]
        AdapterInterface --> OF[OpenFOAM<br/>Adapter]
        AdapterInterface --> Mock[Mock<br/>Adapter]
        AdapterInterface --> Future[Futurs adaptateurs<br/>Future adapters]
    end
    
    subgraph solverLayer [🔧 Solveurs CFD / CFD Solvers]
        OF --> FoamRun[foamRun]
        Mock --> MockSim[Mock Simulation]
        Future --> OtherSolvers[SU2, Fluent, ...]
    end
    
    style userLayer fill:#e3f2fd,stroke:#1976d2
    style coreLayer fill:#f3e5f5,stroke:#7b1fa2
    style libLayer fill:#fff3e0,stroke:#f57c00
    style adapterLayer fill:#e8f5e9,stroke:#388e3c
    style solverLayer fill:#fce4ec,stroke:#c2185b
```

---

## 🎯 Principes de conception / Design Principles

### 1. Code-Agnostic

Le framework ne dépend d'aucun solveur spécifique.

The framework doesn't depend on any specific solver.

```mermaid
graph LR
    Framework[CFD Framework] -.->|Interface| Adapter1[Adapter 1]
    Framework -.->|Interface| Adapter2[Adapter 2]
    Framework -.->|Interface| AdapterN[Adapter N]
    
    Adapter1 --> Solver1[Solver 1]
    Adapter2 --> Solver2[Solver 2]
    AdapterN --> SolverN[Solver N]
    
    style Framework fill:#2196f3,stroke:#1976d2,color:#fff
```

### 2. Séparation des responsabilités / Separation of Concerns

```mermaid
graph TB
    CLI[CLI Layer<br/>Interface utilisateur<br/>User interface] --> Core[Core Layer<br/>Orchestration<br/>Orchestration]
    Core --> Libs[Library Layer<br/>Fonctions réutilisables<br/>Reusable functions]
    Libs --> Adapters[Adapter Layer<br/>Solveur-spécifique<br/>Solver-specific]
    
    style CLI fill:#4caf50,stroke:#388e3c,color:#fff
    style Core fill:#ff9800,stroke:#f57c00,color:#fff
    style Libs fill:#2196f3,stroke:#1976d2,color:#fff
    style Adapters fill:#9c27b0,stroke:#7b1fa2,color:#fff
```

### 3. Configuration as Code

Tout est défini dans des fichiers versionnés.

Everything is defined in versioned files.

```yaml
# config.yaml - Version controllable
etude:
  nom: "STUDY_NAME"
  description: "..."

adaptateur: "OF"

configurations:
  CONFIG:
    cas:
      - nom: "CASE_1"
        parametres: {...}
```

### 4. Traçabilité / Traceability

Chaque run est horodaté et documenté.

Each run is timestamped and documented.

```
Run: OF_V13_CASE_20260131_151234
     ││  │   │    └─ Timestamp
     ││  │   └─ Case name
     ││  └─ Adapter version
     │└─ Adapter
```

---

## 📁 Structure des répertoires / Directory Structure

### Répertoire framework / Framework Directory

```
CFD_FRAMEWORK/
├── bin/                    # Exécutables CLI / CLI executables
│   ├── cfd-creer
│   ├── cfd-run
│   ├── cfd-run-parametrique
│   ├── cfd-archiver
│   └── cfd-clean-config
│
├── lib/                    # Bibliothèques Bash / Bash libraries
│   ├── format.sh
│   ├── gestion_config.sh
│   ├── substitution_params.sh
│   ├── gestion_timestamps.sh
│   └── utils.sh
│
├── adaptateurs/            # Adaptateurs solveurs / Solver adapters
│   ├── interface.sh
│   ├── OF.sh
│   └── mock.sh
│
├── scripts/                # Scripts d'orchestration / Orchestration scripts
│   ├── lancement/
│   │   ├── wrapper_commande_lancement.sh
│   │   └── lancement_parametrique_yaml.sh
│   └── archivage/
│       └── deplacer_resultats.sh
│
├── templates/              # Templates de cas / Case templates
│   └── TEMPLATE_CASE_DEFAULT/
│
├── docs/                   # Documentation
│   └── docs/
│
└── tests/                  # Tests unitaires / Unit tests
    └── lib/
```

### Répertoire de cas / Case Directory

```
MON_CAS/
├── 01_MAILLAGE/           # Fichiers de maillage / Mesh files
├── 02_PARAMS/             # Configurations
│   ├── config.yaml
│   ├── BASELINE/
│   │   ├── template/
│   │   └── OF_V13_CASE_20260131_151234/  # Run horodaté / Timestamped run
│   ├── ANGLE_STUDY/
│   └── REYNOLDS_STUDY/
├── 03_DECOMPOSITION/      # Décomposition domaine / Domain decomposition
├── 04_CONDITION_INITIALE/ # Conditions initiales / Initial conditions
├── 05_DOCUMENTATION/      # Documentation projet / Project documentation
├── 06_REFERENCE/          # Données de référence / Reference data
├── 07_NOTE/               # Notes / Notes
├── 08_RESULTAT/           # Résultats archivés / Archived results
│   ├── BASELINE/
│   ├── ANGLE_STUDY/
│   └── REYNOLDS_STUDY/
├── 09_POST_TRAITEMENT/    # Post-traitement / Post-processing
│   ├── DATA/
│   └── FIGURE/
└── 10_SCRIPT/             # Scripts personnalisés / Custom scripts
    ├── LANCEMENT_CALCUL/
    └── POST_TRAITEMENT/
```

---

## 🔄 Flux de données / Data Flow

### Lancement d'un cas unique / Single Case Launch

```mermaid
sequenceDiagram
    participant U as Utilisateur<br/>User
    participant CLI as cfd-run
    participant W as Wrapper
    participant A as Adaptateur<br/>Adapter
    participant S as Solveur<br/>Solver
    
    U->>CLI: cfd-run --adaptateur OF
    CLI->>W: Appeler wrapper<br/>Call wrapper
    W->>W: Résoudre CFD_FRAMEWORK
    W->>W: Charger bibliothèques<br/>Load libraries
    W->>W: Parse arguments
    W->>A: Charger adaptateur OF<br/>Load OF adapter
    A->>A: Vérifier installation<br/>Check installation
    A-->>W: ✅ Vérifié / Verified
    W->>W: Générer timestamp
    W->>W: Créer répertoire run<br/>Create run directory
    W->>W: Copier éléments<br/>Copy elements
    W->>A: Préparer entrée<br/>Prepare input
    A->>A: Substitution templates
    A-->>W: ✅ Prêt / Ready
    W->>A: Lancer calcul<br/>Launch calculation
    A->>S: foamRun
    S-->>A: ✅ Terminé / Done
    A-->>W: ✅ Succès / Success
    W-->>CLI: ✅ Résultats / Results
    CLI-->>U: ✅ Cas terminé<br/>Case completed
```

### Étude paramétrique / Parametric Study

```mermaid
sequenceDiagram
    participant U as Utilisateur<br/>User
    participant CLI as cfd-run-parametrique
    participant W as Wrapper Param
    participant Config as gestion_config.sh
    participant Run as cfd-run
    
    U->>CLI: cfd-run-parametrique<br/>--config STUDY
    CLI->>W: Appeler wrapper
    W->>Config: Charger config.yaml<br/>Load config.yaml
    Config-->>W: Configurations chargées<br/>Configs loaded
    W->>W: Lister cas (3 cas)<br/>List cases (3 cases)
    
    loop Pour chaque cas / For each case
        W->>W: Extraire paramètres<br/>Extract parameters
        W->>W: Substituer templates<br/>Substitute templates
        W->>Run: Lancer cas<br/>Launch case
        Run-->>W: ✅ Terminé / Done
    end
    
    W-->>CLI: Résumé: 3/3 réussis<br/>Summary: 3/3 successful
    CLI-->>U: ✅ Étude terminée<br/>Study completed
```

---

## 🔌 Système d'adaptateurs / Adapter System

### Interface commune / Common Interface

```bash
# adaptateurs/interface.sh
adapt_nom()                    # Nom du solveur / Solver name
adapt_version()                # Version / Version
adapt_description()            # Description
adapt_verifier_installation()  # Vérifier installation / Check installation
adapt_preparer_entree()        # Préparer fichiers / Prepare files
adapt_lancer_calcul()          # Lancer / Launch
adapt_liste_elements_a_copier() # Éléments à copier / Elements to copy
```

### Graphe de décision : Sélection adaptateur / Decision Graph: Adapter Selection

```mermaid
graph TB
    Start([Démarrage<br/>Start]) --> CheckOpt{Option<br/>--adaptateur?}
    
    CheckOpt -->|Oui / Yes| UseOpt[Utiliser option<br/>Use option]
    CheckOpt -->|Non / No| CheckEnv{$CFD_ADAPTATEUR<br/>défini?<br/>defined?}
    
    CheckEnv -->|Oui / Yes| UseEnv[Utiliser env var<br/>Use env var]
    CheckEnv -->|Non / No| CheckYAML{adaptateur<br/>dans YAML?}
    
    CheckYAML -->|Oui / Yes| UseYAML[Utiliser YAML<br/>Use YAML]
    CheckYAML -->|Non / No| Default[Défaut: OF<br/>Default: OF]
    
    UseOpt --> Load[Charger adaptateur<br/>Load adapter]
    UseEnv --> Load
    UseYAML --> Load
    Default --> Load
    
    Load --> Verify{Vérification<br/>OK?}
    Verify -->|Oui / Yes| Done([✅ Prêt / Ready])
    Verify -->|Non / No| Error([❌ Erreur / Error])
    
    style Start fill:#4caf50,stroke:#388e3c,color:#fff
    style CheckOpt fill:#ff9800,stroke:#f57c00,color:#fff
    style CheckEnv fill:#ff9800,stroke:#f57c00,color:#fff
    style CheckYAML fill:#ff9800,stroke:#f57c00,color:#fff
    style Verify fill:#ff9800,stroke:#f57c00,color:#fff
    style Done fill:#2196f3,stroke:#1976d2,color:#fff
    style Error fill:#f44336,stroke:#c62828,color:#fff
```

---

## 📚 Bibliothèques / Libraries

### Dépendances entre bibliothèques / Library Dependencies

```mermaid
graph TB
    Scripts[Scripts CLI<br/>bin/*] --> Format[format.sh]
    Scripts --> Config[gestion_config.sh]
    Scripts --> Timestamp[gestion_timestamps.sh]
    Scripts --> Utils[utils.sh]
    Scripts --> Params[substitution_params.sh]
    
    Config --> Format
    Params --> Config
    Timestamp --> Format
    Utils --> Format
    
    Wrapper[Wrapper Scripts] --> Scripts
    Wrapper --> Adapters[Adaptateurs<br/>Adapters]
    
    style Scripts fill:#2196f3,stroke:#1976d2,color:#fff
    style Format fill:#4caf50,stroke:#388e3c,color:#fff
    style Wrapper fill:#ff9800,stroke:#f57c00,color:#fff
    style Adapters fill:#9c27b0,stroke:#7b1fa2,color:#fff
```

### Fonctions clés par bibliothèque / Key Functions per Library

| Bibliothèque / Library | Fonctions principales / Main Functions |
|------------------------|---------------------------------------|
| **format.sh** | `_info`, `_error`, `h1`, `progres_init`, `confirmer` |
| **gestion_config.sh** | `cfg_charger`, `cfg_obtenir_valeur`, `cfg_lister_cas` |
| **substitution_params.sh** | `param_substituer_tout`, `param_valider_template` |
| **gestion_timestamps.sh** | `ts_generer`, `ts_supprimer_timestamp`, `ts_plus_recent` |
| **utils.sh** | `util_copier_recursif`, `util_obtenir_taille` |

---

## 🎯 Points d'extension / Extension Points

### 1. Créer un adaptateur / Create an Adapter

```bash
# adaptateurs/mon_solveur.sh
source "${CFD_FRAMEWORK}/adaptateurs/interface.sh"

adapt_nom() { echo "MonSolveur"; }
adapt_version() { mon_solveur --version; }

adapt_lancer_calcul() {
    local rep_exec="$1"
    cd "$rep_exec"
    mon_solveur input.dat > log.txt 2>&1
}

# ... autres fonctions
```

### 2. Créer un template / Create a Template

```bash
cp -r $CFD_FRAMEWORK/templates/TEMPLATE_CASE_DEFAULT \
      $CFD_FRAMEWORK/templates/MON_TEMPLATE

# Personnaliser / Customize
# Utiliser / Use:
cfd-creer --template MON_TEMPLATE
```

### 3. Ajouter une bibliothèque / Add a Library

```bash
# lib/ma_bibliotheque.sh
#!/usr/bin/env bash

ma_fonction() {
    # Implementation
}

# Utiliser / Use:
source "${CFD_FRAMEWORK}/lib/ma_bibliotheque.sh"
```

---

## 📖 Voir aussi / See Also

- [Structure détaillée](structure.md) - Détails de la structure / Structure details
- [Adaptateurs](adapters.md) - Système d'adaptateurs / Adapter system
- [Bibliothèques](libraries.md) - Documentation bibliothèques / Library documentation
- [Créer un adaptateur](../adapters/create-adapter.md) - Guide création / Creation guide
