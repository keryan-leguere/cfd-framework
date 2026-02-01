#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  test_gestion_config.sh — Démonstration de la bibliothèque gestion_config.sh
# ═══════════════════════════════════════════════════════════════════════════════

# Charger les bibliothèques
if [[ -z "${CFD_FRAMEWORK}" ]]; then
  echo "ERREUR: Variable CFD_FRAMEWORK non définie" >&2
  exit 1
fi

source "${CFD_FRAMEWORK}/lib/format.sh"
source "${CFD_FRAMEWORK}/lib/gestion_config.sh"

# ══════════════════════════════════════════════════════════════════════════════
#  PRÉPARATION DES FICHIERS DE TEST
# ══════════════════════════════════════════════════════════════════════════════

# Créer un répertoire temporaire pour les tests
TEST_DIR=$(mktemp -d -t test_gestion_config_XXXXXX)
trap "rm -rf $TEST_DIR" EXIT

# Créer un fichier config.yaml de test
cat > "$TEST_DIR/config_test.yaml" <<'EOF'
etude:
  nom: "Test Showcase"
  description: "Démonstration gestion_config.sh"
  date_creation: "2026-01-29"
  auteur: "Test"

adaptateur: "OF"

ressources:
  nb_coeurs: 4
  memoire: "16GB"
  temps_max: "12:00:00"
  partition: "standard"

configurations:
  BASELINE:
    description: "Configuration de référence"
    ressources:
      nb_coeurs: 8
      memoire: "32GB"
    cas:
      - nom: "CASE_1"
        parametres:
          angle_attaque: 0.0
          reynolds: 6000000.0
          maillage: "mesh_fine.cgns"
          nb_iterations: 5000
          
      - nom: "CASE_2"
        parametres:
          angle_attaque: 10.0
          reynolds: 8000000.0
          maillage: "mesh_ultra.cgns"
          nb_iterations: 10000
  
  SENSIBILITE_MAILLAGE:
    description: "Étude de sensibilité maillage"
    cas:
      - nom: "MESH_COARSE"
        parametres:
          angle_attaque: 5.0
          reynolds: 6000000.0
          maillage: "mesh_coarse.cgns"
          nb_iterations: 3000
          
  VALIDATION:
    description: "Cas de validation"
    cas:
      - nom: "VAL_1"
        parametres:
          angle_attaque: 2.5
          reynolds: 5000000.0
          maillage: "mesh_medium.cgns"
          nb_iterations: 8000
  
  REYNOLDS_SWEEP:
    description: "Balayage Reynolds avec boucle"
    adaptateur: "OF"
    boucle:
      reynolds: [1000000, 2000000, 3000000, 4000000, 5000000]
    cas:
      - nom: "REYNOLDS_LOOP"
        parametres:
          angle_attaque: 5.0
          maillage: "mesh_coarse.cgns"
          nb_iterations: 8000

  ANGLE_ARRAY:
    description: "Array d'angles d'incidence"
    boucle:
      angle_attaque:
        debut: 0
        fin: 20
        pas: 2.5
    cas:
      - nom: "ANGLE_SWEEP"
        parametres:
          reynolds: 6000000.0
          maillage: "mesh_fine.cgns"
          nb_iterations: 10000
EOF

# Créer un fichier YAML invalide pour tester la validation
cat > "$TEST_DIR/config_invalide.yaml" <<'EOF'
etude:
  nom: "Configuration Invalide"

# Manque la section "configurations" obligatoire
parametres:
  angle_attaque: 5.0
EOF

# ══════════════════════════════════════════════════════════════════════════════
#  DÉMONSTRATION
# ══════════════════════════════════════════════════════════════════════════════

reset_counters

h1 "SHOWCASE : gestion_config.sh"

separator_wave

# ─────────────────────────────────────────────────────────────────────────────
h2 "1. Chargement de configuration YAML"
separator

_info "Fonction: cfg_charger() avec fichier YAML"

echo ""
_start "Chargement de config_test.yaml"
if cfg_charger "$TEST_DIR/config_test.yaml"; then
  _result "Configuration YAML chargée avec succès"
  kv "Fichier actif" "$_CFG_FICHIER_ACTIF"
else
  _error "Échec du chargement"
fi

separator_double

sleep 0.1

# ─────────────────────────────────────────────────────────────────────────────
h2 "2. Extraction de valeurs simples"
separator

_info "Fonction: cfg_obtenir_valeur()"

echo ""
_start "Extraction de valeurs de niveau 1 et 2"

# Valeurs simples
etude_nom=$(cfg_obtenir_valeur "etude.nom")
etude_description=$(cfg_obtenir_valeur "etude.description")
adaptateur=$(cfg_obtenir_valeur "adaptateur")

kv "Nom de l'étude" "$etude_nom"
kv "Description" "$etude_description"
kv "Adaptateur" "$adaptateur"

echo ""
_start "Extraction de paramètres de ressources"

nb_coeurs=$(cfg_obtenir_valeur "ressources.nb_coeurs")
memoire=$(cfg_obtenir_valeur "ressources.memoire")
temps_max=$(cfg_obtenir_valeur "ressources.temps_max")

kv "Nombre de cœurs" "$nb_coeurs"
kv "Mémoire" "$memoire"
kv "Temps max" "$temps_max"

separator_double

sleep 0.1

# ─────────────────────────────────────────────────────────────────────────────
h2 "3. Extraction de valeurs complexes"
separator

_info "Fonction: cfg_obtenir_valeur() avec chemins imbriqués"

echo ""
_start "Extraction de paramètres d'un cas spécifique"

# Accéder aux tableaux et structures imbriquées
angle1=$(cfg_obtenir_valeur "configurations.BASELINE.cas[0].parametres.angle_attaque")
reynolds1=$(cfg_obtenir_valeur "configurations.BASELINE.cas[0].parametres.reynolds")
maillage1=$(cfg_obtenir_valeur "configurations.BASELINE.cas[0].parametres.maillage")

_bullet "BASELINE - Cas 1:"
kv "  Angle d'attaque" "$angle1°"
kv "  Reynolds" "$reynolds1"
kv "  Maillage" "$maillage1"

echo ""
angle2=$(cfg_obtenir_valeur "configurations.BASELINE.cas[1].parametres.angle_attaque")
reynolds2=$(cfg_obtenir_valeur "configurations.BASELINE.cas[1].parametres.reynolds")

_bullet "BASELINE - Cas 2:"
kv "  Angle d'attaque" "$angle2°"
kv "  Reynolds" "$reynolds2"

separator_double

# ─────────────────────────────────────────────────────────────────────────────
h2 "4. Listage des configurations disponibles"
separator

_info "Fonction: cfg_lister_configurations()"

echo ""
_start "Récupération de toutes les configurations"

configs=$(cfg_lister_configurations)
if [[ -n "$configs" ]]; then
  _result "Configurations trouvées:"
  echo "$configs" | while IFS= read -r config; do
    _bullet "$config"
    # Obtenir la description si disponible
    if command -v yq &>/dev/null; then
      desc=$(cfg_obtenir_valeur "configurations.${config}.description")
      if [[ -n "$desc" ]]; then
        echo "    → $desc"
      fi
    fi
  done
else
  _warn "Aucune configuration trouvée"
fi

separator_double

# ─────────────────────────────────────────────────────────────────────────────
h2 "5. Validation du schéma de configuration"
separator

_info "Fonction: cfg_valider_schema()"

echo ""
_start "Validation de la structure YAML"

if cfg_valider_schema; then
  _check "Schéma valide : toutes les sections requises sont présentes"
else
  _cross "Schéma invalide : sections manquantes détectées"
fi

echo ""
_start "Test avec une configuration invalide"

if cfg_charger "$TEST_DIR/config_invalide.yaml" 2>/dev/null; then
  if cfg_valider_schema; then
    _warn "Configuration acceptée malgré les erreurs"
  else
    _result "Erreurs de validation détectées correctement"
  fi
fi

# Recharger la bonne configuration
cfg_charger "$TEST_DIR/config_test.yaml" >/dev/null 2>&1

separator_double


# ─────────────────────────────────────────────────────────────────────────────
h2 "7. Affichage formaté de la configuration"
separator

_info "Fonction: cfg_afficher()"

echo ""
cfg_afficher

separator_double

# ─────────────────────────────────────────────────────────────────────────────
h2 "8. Extraction flexible avec cascade"
separator

_info "Fonction: cfg_obtenir_valeur_cascade()"

echo ""
_start "Test de la cascade cas → config → global"

# Adaptateur global
adaptateur_global=$(cfg_obtenir_valeur "adaptateur")
_bullet "Adaptateur global:"
kv "  Valeur" "$adaptateur_global"

echo ""
_start "Cascade pour cas BASELINE (pas d'override)"
adaptateur_cas1=$(cfg_obtenir_valeur_cascade "adaptateur" "configurations.BASELINE.cas[0]")
_bullet "Adaptateur cascade BASELINE.cas[0]:"
kv "  Valeur" "$adaptateur_cas1"
_note "Devrait être '$adaptateur_global' (valeur globale)"

echo ""
_start "Cascade pour cas REYNOLDS_SWEEP (override au niveau config)"
adaptateur_cas2=$(cfg_obtenir_valeur_cascade "adaptateur" "configurations.REYNOLDS_SWEEP.cas[0]")
_bullet "Adaptateur cascade REYNOLDS_SWEEP.cas[0]:"
kv "  Valeur" "$adaptateur_cas2"
_note "Devrait être 'OF' (override dans la configuration)"

echo ""
_start "Test cascade sur paramètre défini dans le cas"
angle_cascade=$(cfg_obtenir_valeur_cascade "angle_attaque" "configurations.BASELINE.cas[0]")
_bullet "Angle d'attaque (cascade):"
kv "  Valeur" "$angle_cascade"
_note "Valeur vient du cas lui-même"

separator_double

# ─────────────────────────────────────────────────────────────────────────────
h2 "9. Expansion des boucles"
separator

_info "Fonction: cfg_expander_cas()"

echo ""
_start "Test avec boucle sur Reynolds (format tableau)"

cas_expanded=$(cfg_expander_cas "configurations.REYNOLDS_SWEEP.cas[0]")
nb_cas_reynolds=$(echo "$cas_expanded" | jq 'length')

_result "Nombre de cas générés: $nb_cas_reynolds"
_note "Attendu: 5 (tableau de 5 valeurs Reynolds)"

echo ""
_bullet "Aperçu des valeurs Reynolds générées:"
for i in {0..4}; do
  reynolds_val=$(echo "$cas_expanded" | jq -r ".[$i].parametres.reynolds" 2>/dev/null)
  [[ -n "$reynolds_val" ]] && echo "    - Cas $((i+1)): $reynolds_val"
done

separator

echo ""
_start "Test avec boucle sur angles (format range)"

cas_expanded_angle=$(cfg_expander_cas "configurations.ANGLE_ARRAY.cas[0]")
nb_cas_angle=$(echo "$cas_expanded_angle" | jq 'length')

_result "Nombre de cas générés: $nb_cas_angle"
_note "Attendu: 9 (range 0 → 20 avec pas 2.5)"

echo ""
_bullet "Aperçu des angles générés:"
for i in {0..8}; do
  angle_val=$(echo "$cas_expanded_angle" | jq -r ".[$i].parametres.angle_attaque" 2>/dev/null)
  [[ -n "$angle_val" ]] && echo "    - Cas $((i+1)): ${angle_val}°"
done

separator_double

# ─────────────────────────────────────────────────────────────────────────────
h2 "10. Utilisation avec le fichier config.yaml réel du projet"
separator

_info "Test avec la configuration d'exemple du framework"

EXEMPLE_CONFIG="${CFD_FRAMEWORK}/tests/exemple_cas/02_PARAMS/config.yaml"

if [[ -f "$EXEMPLE_CONFIG" ]]; then
  echo ""
  _start "Chargement de $EXEMPLE_CONFIG"
  
  if cfg_charger "$EXEMPLE_CONFIG"; then
    _result "Configuration d'exemple chargée"
    
    echo ""
    cfg_afficher
    
    echo ""
    _start "Extraction d'informations spécifiques"
    
    nom_etude=$(cfg_obtenir_valeur "etude.nom")
    description=$(cfg_obtenir_valeur "etude.description")
    
    kv "Nom de l'étude" "$nom_etude"
    kv "Description" "$description"
    
    echo ""
    _start "Configurations disponibles dans l'exemple"
    configs=$(cfg_lister_configurations)
    echo "$configs" | while IFS= read -r config; do
      _bullet "$config"
    done
    
    echo ""
    _start "Paramètres du premier cas"
    
    angle=$(cfg_obtenir_valeur "configurations.BASELINE.cas[0].parametres.angle_attaque")
    reynolds=$(cfg_obtenir_valeur "configurations.BASELINE.cas[0].parametres.reynolds")
    iterations=$(cfg_obtenir_valeur "configurations.BASELINE.cas[0].parametres.nb_iterations")
    
    kv "Angle d'attaque" "$angle°"
    kv "Reynolds" "$reynolds"
    kv "Nb iterations" "$iterations"
  fi
else
  _warn "Fichier d'exemple non trouvé: $EXEMPLE_CONFIG"
fi

separator_double

# ─────────────────────────────────────────────────────────────────────────────
h2 "11. Gestion des erreurs"
separator

_info "Tests de robustesse"

echo ""
_start "Test: Chargement d'un fichier inexistant"
if cfg_charger "/chemin/inexistant/config.yaml" 2>/dev/null; then
  _cross "Erreur non détectée"
else
  _check "Erreur correctement détectée et gérée"
fi

echo ""
_start "Test: Extraction de valeur sans configuration chargée"
_CFG_FICHIER_ACTIF=""  # Réinitialiser
if cfg_obtenir_valeur "test.valeur" 2>/dev/null; then
  _cross "Erreur non détectée"
else
  _check "Erreur correctement détectée"
fi

# Recharger une configuration valide
cfg_charger "$TEST_DIR/config_test.yaml" >/dev/null 2>&1

echo ""
_start "Test: Extraction de clé inexistante"
valeur=$(cfg_obtenir_valeur "cle.qui.nexiste.pas")
if [[ -z "$valeur" ]]; then
  _check "Valeur vide retournée pour clé inexistante (comportement attendu)"
else
  _warn "Valeur inattendue: $valeur"
fi

separator_double

# ─────────────────────────────────────────────────────────────────────────────
h2 "12. Tableau récapitulatif des fonctions"
separator

tableau_init "Fonction" "Description" "Exemple"

tableau_add "cfg_charger()" \
  "Charger un fichier YAML" \
  "cfg_charger config.yaml"

tableau_add "cfg_obtenir_valeur()" \
  "Extraire une valeur par clé" \
  "cfg_obtenir_valeur 'etude.nom'"

tableau_add "cfg_obtenir_valeur_cascade()" \
  "Extraire avec cascade (cas→config→global)" \
  "cfg_obtenir_valeur_cascade 'adaptateur' 'cas[0]'"

tableau_add "cfg_lister_configurations()" \
  "Lister toutes les configurations" \
  "cfg_lister_configurations"

tableau_add "cfg_lister_cas()" \
  "Lister cas avec expansion boucles" \
  "cfg_lister_cas 'BASELINE'"

tableau_add "cfg_expander_cas()" \
  "Expander un cas avec ses boucles" \
  "cfg_expander_cas 'config.cas[0]'"

tableau_add "cfg_valider_schema()" \
  "Valider structure YAML et boucles" \
  "cfg_valider_schema"

tableau_add "cfg_exporter_env()" \
  "Exporter paramètres avec cascade" \
  "cfg_exporter_env 'cas[0]' 'PREFIX_'"

tableau_add "cfg_afficher()" \
  "Afficher résumé formaté" \
  "cfg_afficher"

tableau_print "API gestion_config.sh"

separator_double

# ─────────────────────────────────────────────────────────────────────────────
h2 "13. Cas d'usage typiques"
separator

boite_info "Scénario 1 : Validation d'une configuration avant lancement"

cat <<'USAGE1'
#!/usr/bin/env bash
source "${CFD_FRAMEWORK}/lib/gestion_config.sh"

# Charger et valider
cfg_charger "02_PARAMS/config.yaml"
cfg_valider_schema || exit 1

# Extraire paramètres avec cascade
adaptateur=$(cfg_obtenir_valeur_cascade "adaptateur" "configurations.BASELINE.cas[0]")
nb_coeurs=$(cfg_obtenir_valeur "ressources.nb_coeurs")

echo "Lancement avec $adaptateur sur $nb_coeurs cœurs"
USAGE1

separator

boite_info "Scénario 2 : Export avec cascade pour utilisation dans un script"

cat <<'USAGE2'
#!/usr/bin/env bash
source "${CFD_FRAMEWORK}/lib/gestion_config.sh"

# Charger config
cfg_charger "config.yaml"

# Exporter un cas spécifique (avec cascade automatique)
cfg_exporter_env "configurations.BASELINE.cas[0]" "SIM_"

# Les variables sont maintenant disponibles
echo "Angle: $SIM_angle_attaque"
echo "Reynolds: $SIM_reynolds"
echo "Adaptateur: $SIM_adaptateur"  # Via cascade!
USAGE2

separator

boite_info "Scénario 3 : Expansion de boucles pour génération de cas"

cat <<'USAGE3'
#!/usr/bin/env bash
source "${CFD_FRAMEWORK}/lib/gestion_config.sh"

cfg_charger "config.yaml"

# Expander les cas d'une configuration avec boucles
cas_json=$(cfg_lister_cas "REYNOLDS_SWEEP")

# Parcourir tous les cas générés
echo "$cas_json" | jq -c '.[]' | while read -r cas; do
  nom=$(echo "$cas" | jq -r '.nom')
  reynolds=$(echo "$cas" | jq -r '.parametres.reynolds')
  echo "Cas: $nom - Reynolds: $reynolds"
done
USAGE3

separator_double

# ─────────────────────────────────────────────────────────────────────────────
boite_result "Démonstration terminée avec succès"

echo ""
_note "Fichiers de test créés dans: $TEST_DIR"
_note "Ils seront automatiquement supprimés à la sortie"

separator_wave

h2 "Résumé"

_info "La bibliothèque gestion_config.sh fournit:"
echo ""
_bullet "Support YAML exclusif avec yq (obligatoire)"
_bullet "Extraction de valeurs simples et complexes"
_bullet "Extraction flexible avec cascade (cas → config → global)"
_bullet "Support des boucles avec expansion automatique"
_bullet "Formats de boucle: tableau direct et range (debut/fin/pas)"
_bullet "Produit cartésien pour boucles multiples"
_bullet "Validation du schéma avec vérification des boucles"
_bullet "Export en variables d'environnement avec cascade"
_bullet "Affichage formaté des configurations"
_bullet "Gestion robuste des erreurs"

echo ""
_check "Toutes les fonctionnalités ont été démontrées"
echo ""
_note "yq est maintenant obligatoire (vérifié au chargement)"
_note "Le support .env a été retiré pour simplification"

separator_eq

# Optionnel : garder les fichiers de test pour inspection
if [[ "${KEEP_TEST_FILES:-0}" == "1" ]]; then
  trap - EXIT
  _note "Fichiers de test conservés dans: $TEST_DIR"
  _note "Pour les supprimer: rm -rf $TEST_DIR"
fi
