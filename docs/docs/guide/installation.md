# Installation

## 📋 Prérequis / Prerequisites

### Système d'exploitation / Operating System

=== "Linux"
    
    ✅ **Recommandé / Recommended**
    
    - Ubuntu 20.04+ / Debian 11+
    - RHEL 8+ / CentOS 8+ / Rocky Linux 8+
    - Arch Linux

=== "macOS"
    
    ⚠️ **Compatible** (avec GNU tools)
    
    - macOS 11 (Big Sur) ou supérieur
    - Homebrew installé

=== "Windows"
    
    ⚠️ **Via WSL2 uniquement**
    
    - Windows 10/11 avec WSL2
    - Distribution Ubuntu recommandée

### Outils requis / Required Tools

| Outil / Tool | Version minimale | Obligatoire / Required | Installation |
|--------------|------------------|------------------------|--------------|
| **bash** | ≥ 4.0 | ✅ Oui / Yes | Préinstallé / Pre-installed |
| **git** | ≥ 2.0 | ✅ Oui / Yes | `apt install git` / `brew install git` |
| **yq** | ≥ 4.0 | ⚠️ Recommandé | `pip install yq` / `brew install yq` |
| **rsync** | ≥ 3.0 | ⚠️ Recommandé | `apt install rsync` |
| **tmux** | ≥ 2.0 | ⚠️ Recommandé | `apt install tmux` |
| **GNU Parallel** | - | ❌ Optionnel | `apt install parallel` |

!!! tip "Note sur yq"
    Si `yq` n'est pas disponible, le framework utilisera un parser YAML natif en bash (plus lent).
    
    If `yq` is not available, the framework will use a native bash YAML parser (slower).

---

## 🚀 Installation du Framework / Framework Installation

### Méthode 1 : Installation standard / Standard Installation

```bash
# 1. Cloner le dépôt / Clone the repository
cd ~/Documents
git clone https://github.com/user/CFD_FRAMEWORK.git
cd CFD_FRAMEWORK

# 2. Configurer l'environnement / Configure environment
export CFD_FRAMEWORK="$(pwd)"
echo "export CFD_FRAMEWORK=\"$(pwd)\"" >> ~/.bashrc

# 3. Ajouter les binaires au PATH / Add binaries to PATH
export PATH="$CFD_FRAMEWORK/bin:$PATH"
echo "export PATH=\"\$CFD_FRAMEWORK/bin:\$PATH\"" >> ~/.bashrc

# 4. Recharger la configuration / Reload configuration
source ~/.bashrc

# 5. Vérifier l'installation / Verify installation
cfd-run --help
```

### Méthode 2 : Installation depuis un emplacement personnalisé / Custom Location

```bash
# Installation dans /opt/CFD_FRAMEWORK
sudo mkdir -p /opt/CFD_FRAMEWORK
sudo chown $USER:$USER /opt/CFD_FRAMEWORK
cd /opt
git clone https://github.com/user/CFD_FRAMEWORK.git
cd CFD_FRAMEWORK

# Configuration
export CFD_FRAMEWORK="/opt/CFD_FRAMEWORK"
echo "export CFD_FRAMEWORK=\"/opt/CFD_FRAMEWORK\"" >> ~/.bashrc
export PATH="$CFD_FRAMEWORK/bin:$PATH"
echo "export PATH=\"\$CFD_FRAMEWORK/bin:\$PATH\"" >> ~/.bashrc

source ~/.bashrc
```

---

## 🔧 Configuration des adaptateurs / Adapter Configuration

### OpenFOAM

```bash
# Vérifier l'installation OpenFOAM / Check OpenFOAM installation
which foamRun

# Si non installé / If not installed:
# Ubuntu/Debian
sudo apt install openfoam-default

# macOS (via Docker)
docker pull openfoam/openfoam-default

# Définir l'adaptateur par défaut / Set default adapter
export CFD_ADAPTATEUR="OF"
echo "export CFD_ADAPTATEUR=\"OF\"" >> ~/.bashrc
```

### Adaptateur Mock (pour tests / for testing)

```bash
# Aucune installation requise / No installation required
export CFD_ADAPTATEUR="mock"
echo "export CFD_ADAPTATEUR=\"mock\"" >> ~/.bashrc
```

---

## ✅ Vérification de l'installation / Installation Verification

### Test rapide / Quick Test

```bash
# Vérifier les commandes disponibles / Check available commands
cfd-creer --help
cfd-run --help
cfd-archiver --help

# Créer un cas de test / Create a test case
cd /tmp
cfd-creer --name TEST_INSTALL --template TEMPLATE_CASE_DEFAULT

# Vérifier la structure / Check structure
ls -la TEST_INSTALL/
```

### Test complet avec adaptateur mock / Full test with mock adapter

```bash
# Créer et lancer un cas mock / Create and launch a mock case
cd /tmp
cfd-creer --name VERIFICATION
cd VERIFICATION/02_PARAMS

# Créer une configuration minimale / Create minimal configuration
mkdir -p BASELINE
cd BASELINE

# Lancer avec mock / Launch with mock
export CASE_NAME="VERIF"
cfd-run --adaptateur mock --name VERIF --in-place

# Si succès, vous devriez voir / If successful, you should see:
# ✅ Cas préparé
# ✅ Calcul lancé
```

---

## 🎨 Configuration optionnelle / Optional Configuration

### Alias personnalisés / Custom Aliases

Ajoutez à votre `~/.bashrc` ou `~/.zshrc`:

```bash
# Alias CFD Framework
alias cfd-ls='ls -lhrt $PWD/*_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_*'
alias cfd-last='cd $(ls -td $PWD/*_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_* | head -1)'
alias cfd-clean-all='find . -maxdepth 2 -type d -name "*_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_*" -exec rm -rf {} +'
```

### Completion bash

```bash
# Activer la complétion bash / Enable bash completion
cat >> ~/.bashrc << 'EOF'
# CFD Framework completion
_cfd_complete() {
    local cur=${COMP_WORDS[COMP_CUR]}
    case "${COMP_WORDS[1]}" in
        cfd-run)
            COMPREPLY=($(compgen -W "--adaptateur --in-place --dry-run --name --help" -- "$cur"))
            ;;
        cfd-archiver)
            COMPREPLY=($(compgen -W "--append --force --un-safe --help" -- "$cur"))
            ;;
        *)
            COMPREPLY=()
            ;;
    esac
}
complete -F _cfd_complete cfd-run cfd-archiver cfd-clean-config
EOF

source ~/.bashrc
```

---

## 🐛 Dépannage / Troubleshooting

### Problème : bash version trop ancienne / bash version too old

```bash
# Vérifier la version / Check version
bash --version

# Si < 4.0, mettre à jour / If < 4.0, upgrade
# Ubuntu/Debian
sudo apt update && sudo apt install --only-upgrade bash

# macOS (utiliser bash de Homebrew)
brew install bash
echo "/usr/local/bin/bash" | sudo tee -a /etc/shells
chsh -s /usr/local/bin/bash
```

### Problème : CFD_FRAMEWORK non défini / not defined

```bash
# Vérifier / Check
echo $CFD_FRAMEWORK

# Si vide / If empty
export CFD_FRAMEWORK="/chemin/vers/CFD_FRAMEWORK"
echo "export CFD_FRAMEWORK=\"/chemin/vers/CFD_FRAMEWORK\"" >> ~/.bashrc
source ~/.bashrc
```

### Problème : commandes cfd-* introuvables / commands not found

```bash
# Vérifier le PATH / Check PATH
echo $PATH | grep CFD_FRAMEWORK

# Si absent / If missing
export PATH="$CFD_FRAMEWORK/bin:$PATH"
echo "export PATH=\"\$CFD_FRAMEWORK/bin:\$PATH\"" >> ~/.bashrc
source ~/.bashrc

# Vérifier les permissions / Check permissions
chmod +x $CFD_FRAMEWORK/bin/*
```

### Problème : yq introuvable / yq not found

```bash
# Installation via pip
pip3 install yq

# Ou via package manager / Or via package manager
# Ubuntu/Debian
sudo apt install python3-yq

# macOS
brew install yq

# Vérification / Verification
yq --version
```

---

## 📦 Installation sur cluster HPC / HPC Cluster Installation

### Module Environment

```bash
# Créer un module pour le framework / Create a module for the framework
# Dans /opt/modules/cfd-framework/1.0
cat > /opt/modules/cfd-framework/1.0 << 'EOF'
#%Module1.0
proc ModulesHelp { } {
    puts stderr "CFD Framework v1.0"
}

module-whatis "CFD Framework - Generic parametric CFD studies"

set root /opt/CFD_FRAMEWORK
setenv CFD_FRAMEWORK $root
prepend-path PATH $root/bin
EOF

# Charger le module / Load the module
module load cfd-framework/1.0
```

### Slurm Integration

```bash
# Exemple de script Slurm / Example Slurm script
cat > run_cfd.sh << 'EOF'
#!/bin/bash
#SBATCH --job-name=cfd-calc
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=16
#SBATCH --time=24:00:00

module load cfd-framework/1.0
module load openfoam/v2312

cd $SLURM_SUBMIT_DIR
cfd-run --adaptateur OF --name MY_CASE
EOF
```

---

## ✅ Checklist post-installation / Post-Installation Checklist

- [ ] Variables d'environnement définies / Environment variables set
- [ ] Commandes cfd-* accessibles / cfd-* commands accessible
- [ ] Adaptateur configuré / Adapter configured
- [ ] Test de cas réussi / Test case successful
- [ ] Documentation accessible / Documentation accessible

---

## 📖 Étapes suivantes / Next Steps

- [Démarrage rapide](quickstart.md) - Créer votre premier cas / Create your first case
- [Configuration](configuration.md) - Configurer les paramètres / Configure parameters
- [Workflow](workflow.md) - Comprendre le flux de travail / Understand the workflow

---

**Besoin d'aide ?** Consultez la [FAQ](faq.md) ou ouvrez une [issue](https://github.com/user/CFD_FRAMEWORK/issues).

**Need help?** Check the [FAQ](faq.md) or open an [issue](https://github.com/user/CFD_FRAMEWORK/issues).
