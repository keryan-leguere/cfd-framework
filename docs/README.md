# CFD Framework Documentation

## 📖 Documentation complète / Complete Documentation

Cette documentation est construite avec [MkDocs Material](https://squidfunk.github.io/mkdocs-material/).

This documentation is built with [MkDocs Material](https://squidfunk.github.io/mkdocs-material/).

---

## 🚀 Visualiser la documentation / View Documentation

### Option 1 : Serveur de développement / Development Server

```bash
cd docs
mkdocs serve
```

Puis ouvrir : http://127.0.0.1:8000

Then open: http://127.0.0.1:8000

### Option 2 : Build statique / Static Build

```bash
cd docs
mkdocs build
```

La documentation est générée dans `docs/site/`.

Documentation is generated in `docs/site/`.

---

## 📦 Installation de MkDocs / MkDocs Installation

### Via pip

```bash
pip install mkdocs-material
```

### Dépendances complètes / Complete Dependencies

```bash
pip install mkdocs-material \
            pymdown-extensions \
            mkdocs-glightbox
```

---

## 📁 Structure

```
docs/
├── mkdocs.yml              # Configuration MkDocs
├── docs/                   # Sources de la documentation / Documentation sources
│   ├── index.md            # Page d'accueil / Home page
│   ├── guide/              # Guides utilisateur / User guides
│   ├── architecture/       # Architecture du framework / Framework architecture
│   ├── cli/                # Référence CLI / CLI reference
│   ├── api/                # API Bash
│   ├── adapters/           # Adaptateurs / Adapters
│   ├── workflows/          # Workflows spécifiques / Specific workflows
│   ├── examples/           # Exemples / Examples
│   └── dev/                # Développement / Development
├── site/                   # Site généré (git-ignored) / Generated site (git-ignored)
└── README.md               # Ce fichier / This file
```

---

## ✨ Fonctionnalités / Features

- 🌍 **Bilingue** : Français + Anglais / French + English
- 📊 **Diagrammes Mermaid** : Graphes de décision / Decision graphs
- 🎨 **Material Theme** : Design moderne / Modern design
- 🔍 **Recherche** : Multilingue / Multilingual
- 📱 **Responsive** : Mobile-friendly
- 🎯 **Navigation** : Structurée et intuitive / Structured and intuitive
- 💻 **Syntax Highlighting** : Code coloré / Colored code
- 📋 **Admonitions** : Notes, warnings, tips

---

## 🔧 Commandes utiles / Useful Commands

```bash
# Lancer le serveur de développement / Start dev server
mkdocs serve

# Build la documentation / Build documentation
mkdocs build

# Déployer sur GitHub Pages / Deploy to GitHub Pages
mkdocs gh-deploy

# Vérifier la configuration / Check configuration
mkdocs build --strict
```

---

## 📝 Contribuer à la documentation / Contribute to Documentation

### Ajouter une page / Add a Page

1. Créer le fichier Markdown dans `docs/docs/`
2. Ajouter l'entrée dans `mkdocs.yml` section `nav:`

```yaml
nav:
  - Ma section:
    - ma-page.md
```

### Conventions / Conventions

- **Noms de fichiers** : `kebab-case.md`
- **Titres** : Niveau 1 (`#`) pour le titre principal
- **Bilingue** : Français puis anglais séparés par `/`
- **Code** : Utiliser des blocs de code avec syntax highlighting
- **Diagrammes** : Utiliser Mermaid pour les graphes

### Exemple de page / Page Example

```markdown
# Mon Titre / My Title

## Section 1

Texte en français.

English text.

### Sous-section

\`\`\`bash
# Commande exemple / Example command
cfd-run --help
\`\`\`

\`\`\`mermaid
graph LR
    A[Début] --> B[Fin]
\`\`\`
```

---

## 🎨 Personnalisation / Customization

### CSS custom

Modifiez `docs/docs/stylesheets/extra.css` pour personnaliser l'apparence.

Edit `docs/docs/stylesheets/extra.css` to customize appearance.

### Thème

Configuration dans `mkdocs.yml` section `theme:`.

Configuration in `mkdocs.yml` section `theme:`.

---

## 📚 Ressources / Resources

- [MkDocs](https://www.mkdocs.org/)
- [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)
- [Mermaid Documentation](https://mermaid.js.org/)
- [PyMdown Extensions](https://facelessuser.github.io/pymdown-extensions/)

---

## 🐛 Problèmes / Issues

### MkDocs ne trouve pas les pages / MkDocs Can't Find Pages

Vérifiez que :
- Les fichiers `.md` sont dans `docs/docs/`
- Les chemins dans `nav:` sont corrects
- Pas de caractères spéciaux dans les noms

Check that:
- `.md` files are in `docs/docs/`
- Paths in `nav:` are correct
- No special characters in names

### Diagrammes Mermaid ne s'affichent pas / Mermaid Diagrams Don't Display

Vérifiez dans `mkdocs.yml` :

```yaml
markdown_extensions:
  - pymdownx.superfences:
      custom_fences:
        - name: mermaid
          class: mermaid
          format: !!python/name:pymdownx.superfences.fence_code_format
```

---

## 📄 Licence / License

Documentation sous licence MIT - Copyright © 2026 KL

Documentation under MIT License - Copyright © 2026 KL
