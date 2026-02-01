# Documentation de `lib/format.sh`

`lib/format.sh` est une bibliothèque de formatage professionnelle pour les scripts Bash, particulièrement optimisée pour les flux de travail CFD (Computational Fluid Dynamics). Elle offre des outils pour le logging, les titres hiérarchiques, les barres de progression, l'interactivité et des bannières ASCII élégantes.

## Installation

Pour utiliser cette bibliothèque dans vos scripts, sourcez-la simplement :

```bash
source "chemin/vers/lib/format.sh"
```

## Fonctionnalités principales

### 1. Logging et Messages
Des fonctions avec emojis et couleurs pour différents niveaux d'information.

| Fonction | Description | Emoji |
| :--- | :--- | :--- |
| `_info` | Message d'information | ℹ️ |
| `_warn` | Avertissement | ⚠️ |
| `_error` | Erreur critique | ❌ |
| `_result` | Succès d'une opération | ✅ |
| `_debug` | Debug (si `$VERBOSE >= 2`) | 🔍 |
| `_start` / `_end` | Début/Fin d'action | 🚀 / 🏁 |
| `_wait` | Message d'attente | ⏳ |
| `_bullet` | Élément de liste | • |
| `_check` / `_cross` | Succès/Échec visuel | ✓ / ✗ |
| `die "msg"` | Erreur et arrêt du script | ❌ |

**Exemple :**
```bash
_info "Chargement des paramètres..."
_result "Configuration chargée avec succès."
```

### 2. Titres et Organisation
Structurez vos scripts avec des titres et des en-têtes numérotés automatiquement.

| Fonction | Description |
| :--- | :--- |
| `title "Texte"` | Titre principal encadré |
| `title_icon "🔥" "Texte"` | Titre principal avec icône personnalisée |
| `h1 "Section"` | En-tête de niveau 1 (ex: 1. Section) |
| `h2 "Sous-section"` | En-tête de niveau 2 (ex: 1.1 Sous-section) |
| `h3 "Détail"` | En-tête de niveau 3 (ex: ▸ 1.1.1 Détail) |
| `reset_counters` | Réinitialise la numérotation automatique |

### 3. Séparateurs Visuels
| Fonction | Style |
| :--- | :--- |
| `separator` | Ligne simple `───` |
| `separator_eq` | Ligne double `═══` |
| `separator_double` | Ligne accentuée épaisse |
| `separator_wave` | Ligne de vagues `~~~` |

### 4. Barre de Progression et ETA
Gérez des barres de progression animées avec estimation du temps restant (ETA) et vitesse.

*   `progres_init "Message" Total` : Initialise la barre.
*   `progres_update Valeur` : Met à jour la progression.
*   `progres_done "Terminé"` : Finalise la barre à 100%.

**Exemple :**
```bash
progres_init "Calcul CFD" 100
for i in {1..100}; do
  progres_update $i
  sleep 0.1
done
progres_done "Calcul terminé"
```

### 5. Tableaux Formatés
Affichez des données tabulaires propres.

1.  `tableau_init "Entête 1" "Entête 2"` : Définit les colonnes.
2.  `tableau_add "Valeur 1" "Valeur 2"` : Ajoute des lignes.
3.  `tableau_print "Titre du tableau"` : Affiche le tableau complet.

### 6. Encadrés (Boxes)
Idéal pour mettre en évidence des messages importants.

*   `boite_info "Message"`
*   `boite_result "Succès"`
*   `boite_warn "Attention"`
*   `boite_error "Erreur"`

### 7. Interactivité utilisateur
*   `confirmer "Voulez-vous continuer ?" [o/n]` : Retourne vrai/faux selon la réponse.
*   `choisir_option "Titre" "Option 1" "Option 2"` : Affiche un menu numéroté et retourne l'option choisie.

### 8. Bannières CFD (Ascii Art)
Bannières géantes pour les étapes majeures du framework :
*   `title_launch_simulation` : Lancement du calcul.
*   `titre_surveillance` : Monitoring en temps réel.
*   `title_post_processing` : Post-traitement.
*   `titre_archivage` : Sauvegarde des résultats.
*   `titre_deploiement` : Déploiement vers production.

## Configuration
Le comportement peut être ajusté via des variables d'environnement :
*   `VERBOSE` : Définit le niveau de détail (0, 1 ou 2). Par défaut : `2`.
*   La bibliothèque détecte automatiquement si la sortie est un terminal (TTY) pour activer ou désactiver les couleurs et animations.

---
*Documentation générée pour le Framework CFD.*
