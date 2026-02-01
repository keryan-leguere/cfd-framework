#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  test_substitution_params.sh — Showcase + tests pour lib/substitution_params.sh
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Objectif:
#   - Démontrer les fonctions de substitution de balises dans des templates
#   - Vérifier les cas principaux avec des assertions (script non-interactif)
#
#  Usage:
#    export CFD_FRAMEWORK=/chemin/vers/CFD_FRAMEWORK
#    bash tests/lib/test_substitution_params.sh
#
#  Option:
#    KEEP_TEST_FILES=1   -> conserve le répertoire temporaire
#
# ═══════════════════════════════════════════════════════════════════════════════

# ── Locale UTF-8 (évite certains soucis d'affichage et assure cohérence du tri) ──
export LC_ALL="C.UTF-8"
export LANG="C.UTF-8"

# ── Pré-requis ────────────────────────────────────────────────────────────────
if [[ -z "${CFD_FRAMEWORK:-}" ]] || [[ ! -d "${CFD_FRAMEWORK}/lib" ]]; then
  echo "ERREUR: Variable CFD_FRAMEWORK non définie ou invalide: '${CFD_FRAMEWORK:-}'" >&2
  exit 1
fi

# yq est requis par gestion_config.sh
if ! command -v yq &>/dev/null; then
  echo "ERREUR: 'yq' est requis pour ces tests (gestion_config.sh)" >&2
  exit 1
fi

source "${CFD_FRAMEWORK}/lib/format.sh"
source "${CFD_FRAMEWORK}/lib/gestion_config.sh"
source "${CFD_FRAMEWORK}/lib/substitution_params.sh"

# ── Helpers d'assertion (simples, mais stricts) ────────────────────────────────
fail() {
  _error "$*"
  exit 1
}

assert_eq() {
  local expected="$1"
  local actual="$2"
  local msg="${3:-Assertion failed}"

  if [[ "$expected" != "$actual" ]]; then
    echo ""
    _error "$msg"
    kv "Attendu" "$expected"
    kv "Obtenu" "$actual"
    exit 1
  fi
  _check "$msg"
}

assert_file_contains() {
  local file="$1"
  local needle="$2"
  local msg="${3:-Fichier contient la chaîne attendue}"

  [[ -f "$file" ]] || fail "Fichier introuvable: $file"
  if grep -Fq -- "$needle" "$file"; then
    _check "$msg"
  else
    echo ""
    _error "$msg"
    kv "Fichier" "$file"
    kv "Chaîne" "$needle"
    _note "Contenu du fichier:"
    sed -n '1,200p' "$file" || true
    exit 1
  fi
}

assert_file_not_contains() {
  local file="$1"
  local needle="$2"
  local msg="${3:-Fichier ne contient pas la chaîne}"

  [[ -f "$file" ]] || fail "Fichier introuvable: $file"
  if grep -Fq -- "$needle" "$file"; then
    echo ""
    _error "$msg"
    kv "Fichier" "$file"
    kv "Chaîne" "$needle"
    _note "Contenu du fichier:"
    sed -n '1,200p' "$file" || true
    exit 1
  fi
  _check "$msg"
}

# ══════════════════════════════════════════════════════════════════════════════
#  Préparation fixtures
# ══════════════════════════════════════════════════════════════════════════════

TEST_DIR="$(mktemp -d -t test_substitution_params_XXXXXX)"
if [[ "${KEEP_TEST_FILES:-0}" == "1" ]]; then
  _note "KEEP_TEST_FILES=1 -> répertoire conservé: $TEST_DIR"
else
  trap 'rm -rf "$TEST_DIR"' EXIT
fi

TEMPLATE_BALISES="${TEST_DIR}/template_balises.txt"
TEMPLATE_REMPLACE="${TEST_DIR}/template_remplace.txt"
TEMPLATE_COMPLET="${TEST_DIR}/template_complet.txt"

OUT_REMPLACE="${TEST_DIR}/out_remplace.txt"
OUT_COMPLET="${TEST_DIR}/out_complet.txt"

CFG_ROOT="${TEST_DIR}/config_root.yaml"
CFG_CASE="${TEST_DIR}/config_case.yaml"

# Template de base pour détection de balises (mix @...@ et {{...}})
cat > "$TEMPLATE_BALISES" <<'EOF'
Nom étude: @ETUDE_NOM@
Cas: {{CASE_NAME}}
AoA: @angle_attaque@ (aussi {{angle_attaque}})
Re: {{reynolds}}
Re (bis): @reynolds@
Maillage: @maillage@
EOF

# Template de remplacement ciblé (une balise)
cat > "$TEMPLATE_REMPLACE" <<'EOF'
Angle @angle_attaque@ deg
Angle (alt) {{angle_attaque}} deg
EOF

# Template complet pour substitution globale
cat > "$TEMPLATE_COMPLET" <<'EOF'
Adaptateur: @adaptateur@
Cas: {{CASE_NAME}}
Angle: @angle_attaque@
Reynolds: {{reynolds}}
Maillage: @maillage@
Iterations: @nb_iterations@
Inconnue: @NOT_FOUND@
EOF

# Config "root" pour valider template avec clés simples
cat > "$CFG_ROOT" <<'EOF'
ETUDE_NOM: "Showcase Substitution"
adaptateur: "OF"
angle_attaque: "2.5"
reynolds: "6000000"
maillage: "mesh_fine.cgns"
nb_iterations: "5000"
EOF

# Config "case" pour tester chemin_cas + fallback global
cat > "$CFG_CASE" <<'EOF'
adaptateur: "OF"
configurations:
  BASELINE:
    cas:
      - nom: "CASE_1"
        parametres:
          angle_attaque: "5.0"
          reynolds: "7000000"
          maillage: "mesh_ultra.cgns"
          nb_iterations: "10000"
EOF

reset_counters
separator_wave
h1 "SHOWCASE : substitution_params.sh"
separator_wave

# ══════════════════════════════════════════════════════════════════════════════
#  1) param_trouver_balises
# ══════════════════════════════════════════════════════════════════════════════
h2 "1) Détection des balises (param_trouver_balises)"
separator

_start "Extraction des balises depuis template_balises.txt"
balises="$(param_trouver_balises "$TEMPLATE_BALISES")"
_result "Balises détectées (triées, dédupliquées):"
echo "$balises" | while IFS= read -r b; do [[ -n "$b" ]] && _bullet "$b"; done

# Sort -u => ordre lexicographique (uppercase avant lowercase en LC_ALL=C.UTF-8)
expected_balises=$'CASE_NAME\nETUDE_NOM\nangle_attaque\nmaillage\nreynolds'
assert_eq "$expected_balises" "$balises" "Liste des balises détectées conforme"

separator_double

# ══════════════════════════════════════════════════════════════════════════════
#  2) param_remplacer_balise
# ══════════════════════════════════════════════════════════════════════════════
h2 "2) Remplacement d'une balise (param_remplacer_balise)"
separator

_start "Remplacement de angle_attaque par 12.5"
param_remplacer_balise "$TEMPLATE_REMPLACE" "$OUT_REMPLACE" "angle_attaque" "12.5"

assert_file_contains "$OUT_REMPLACE" "Angle 12.5 deg" "Format @...@ remplacé"
assert_file_contains "$OUT_REMPLACE" "Angle (alt) 12.5 deg" "Format {{...}} remplacé"
assert_file_not_contains "$OUT_REMPLACE" "@angle_attaque@" "Plus de placeholder @angle_attaque@"
assert_file_not_contains "$OUT_REMPLACE" "{{angle_attaque}}" "Plus de placeholder {{angle_attaque}}"

separator

_start "Remplacement avec caractères spéciaux regex (escapés)"
TEMPLATE_ESCAPE="${TEST_DIR}/template_escape.txt"
cat > "$TEMPLATE_ESCAPE" <<'EOF'
Formula: @formula@
Pattern: {{pattern}}
EOF

OUT_ESCAPE="${TEST_DIR}/out_escape.txt"

# Test with regex metacharacters that should be escaped
param_remplacer_balise "$TEMPLATE_ESCAPE" "$OUT_ESCAPE" "formula" "a+b(c)?^"
param_remplacer_balise "$OUT_ESCAPE" "$OUT_ESCAPE" "pattern" "x.*y\$z"

assert_file_contains "$OUT_ESCAPE" "Formula: a+b(c)?^" "Métacaractères regex escapés correctement (@)"
assert_file_contains "$OUT_ESCAPE" "Pattern: x.*y\$z" "Métacaractères regex escapés correctement ({{}})"

separator_double

# ══════════════════════════════════════════════════════════════════════════════
#  3) param_valider_template
# ══════════════════════════════════════════════════════════════════════════════
h2 "3) Validation template/config (param_valider_template)"
separator

_start "Validation d'un template simple via config_root.yaml"
TEMPLATE_VALIDE="${TEST_DIR}/template_valide.txt"
cat > "$TEMPLATE_VALIDE" <<'EOF'
Adaptateur: @adaptateur@
Angle: @angle_attaque@
Reynolds: {{reynolds}}
Maillage: @maillage@
Iterations: @nb_iterations@
EOF

if param_valider_template "$TEMPLATE_VALIDE" "$CFG_ROOT"; then
  _result "Template validé (toutes les balises résolues via config)"
else
  fail "La validation aurait dû réussir avec CFG_ROOT"
fi

separator

_start "Validation échoue si une balise n'est résolue nulle part"
TEMPLATE_INCOMPLET="${TEST_DIR}/template_incomplet.txt"
cat > "$TEMPLATE_INCOMPLET" <<'EOF'
Valeur: @A_EXISTE@
Manquante: @B_MANQUANTE@
EOF
cat > "${TEST_DIR}/config_incomplet.yaml" <<'EOF'
A_EXISTE: "ok"
EOF

if param_valider_template "$TEMPLATE_INCOMPLET" "${TEST_DIR}/config_incomplet.yaml" 2>/dev/null; then
  fail "La validation aurait dû échouer (B_MANQUANTE absent)"
else
  _check "Balise manquante correctement détectée"
fi

separator

_start "Validation réussit avec balise résolue via variable d'environnement"
TEMPLATE_ENV="${TEST_DIR}/template_env.txt"
cat > "$TEMPLATE_ENV" <<'EOF'
Valeur config: @A_EXISTE@
Valeur env: @ENV_ONLY@
EOF

export ENV_ONLY="from_environment"
if param_valider_template "$TEMPLATE_ENV" "${TEST_DIR}/config_incomplet.yaml" 2>/dev/null; then
  _check "Balise résolue via variable d'environnement"
else
  fail "La validation aurait dû réussir (ENV_ONLY défini en env)"
fi
unset ENV_ONLY

separator

_start "Validation réussit avec balise résolue via PARAM_ prefix"
TEMPLATE_PARAM="${TEST_DIR}/template_param.txt"
cat > "$TEMPLATE_PARAM" <<'EOF'
Valeur config: @A_EXISTE@
Valeur PARAM_: @PARAM_ONLY@
EOF

export PARAM_PARAM_ONLY="from_PARAM_prefix"
if param_valider_template "$TEMPLATE_PARAM" "${TEST_DIR}/config_incomplet.yaml" 2>/dev/null; then
  _check "Balise résolue via préfixe PARAM_"
else
  fail "La validation aurait dû réussir (PARAM_PARAM_ONLY défini)"
fi
unset PARAM_PARAM_ONLY

separator_double

# ══════════════════════════════════════════════════════════════════════════════
#  4) param_substituer_tout
# ══════════════════════════════════════════════════════════════════════════════
h2 "4) Substitution complète (param_substituer_tout)"
separator

_start "Substitution complète avec chemin_cas=configurations.BASELINE.cas[0]"
param_substituer_tout \
  "$TEMPLATE_COMPLET" \
  "$OUT_COMPLET" \
  "$CFG_CASE" \
  "configurations.BASELINE.cas[0]"

# Champs attendus (valeurs depuis le cas)
assert_file_contains "$OUT_COMPLET" "Adaptateur: OF" "Valeur globale substituée"
assert_file_contains "$OUT_COMPLET" "Angle: 5.0" "Valeur cas substituée (@angle_attaque@)"
assert_file_contains "$OUT_COMPLET" "Reynolds: 7000000" "Valeur cas substituée ({{reynolds}})"
assert_file_contains "$OUT_COMPLET" "Maillage: mesh_ultra.cgns" "Valeur cas substituée (@maillage@)"
assert_file_contains "$OUT_COMPLET" "Iterations: 10000" "Valeur cas substituée (@nb_iterations@)"

# Balise inconnue: laissée telle quelle
assert_file_contains "$OUT_COMPLET" "Inconnue: @NOT_FOUND@" "Balise non résolue conservée"

separator

_start "Substitution avec sources multiples: config, env, PARAM_, uppercase"
TEMPLATE_MULTI="${TEST_DIR}/template_multi.txt"
cat > "$TEMPLATE_MULTI" <<'EOF'
Config: @adaptateur@
Direct env: @FROM_ENV@
PARAM_ prefix: @FROM_PARAM@
Uppercase fallback: @angle_attaque@
Unresolved: @UNKNOWN_TAG@
EOF

CFG_MULTI="${TEST_DIR}/config_multi.yaml"
cat > "$CFG_MULTI" <<'EOF'
adaptateur: "Mock"
EOF

OUT_MULTI="${TEST_DIR}/out_multi.txt"

# Set up environment variables for different resolution paths
export FROM_ENV="direct_env_value"
export PARAM_FROM_PARAM="param_prefix_value"
export ANGLE_ATTAQUE="5.5"  # uppercase fallback for angle_attaque

param_substituer_tout "$TEMPLATE_MULTI" "$OUT_MULTI" "$CFG_MULTI" ""

assert_file_contains "$OUT_MULTI" "Config: Mock" "Valeur depuis config"
assert_file_contains "$OUT_MULTI" "Direct env: direct_env_value" "Valeur depuis env directe"
assert_file_contains "$OUT_MULTI" "PARAM_ prefix: param_prefix_value" "Valeur depuis PARAM_ prefix"
assert_file_contains "$OUT_MULTI" "Uppercase fallback: 5.5" "Valeur depuis uppercase fallback"
assert_file_contains "$OUT_MULTI" "Unresolved: @UNKNOWN_TAG@" "Balise non résolue conservée"

# Cleanup env vars
unset FROM_ENV PARAM_FROM_PARAM ANGLE_ATTAQUE

separator_double

# ══════════════════════════════════════════════════════════════════════════════
#  5) Gestion des erreurs (fichiers manquants)
# ══════════════════════════════════════════════════════════════════════════════
h2 "5) Gestion des erreurs - fichiers manquants"
separator

_start "param_trouver_balises avec template inexistant"
if param_trouver_balises "/chemin/inexistant/template.txt" 2>/dev/null; then
  fail "param_trouver_balises aurait dû retourner une erreur"
else
  _check "Erreur correctement détectée (retour non-zéro)"
fi

separator

_start "param_valider_template avec template inexistant"
if param_valider_template "/chemin/inexistant/template.txt" "$CFG_ROOT" 2>/dev/null; then
  fail "param_valider_template aurait dû retourner une erreur"
else
  _check "Erreur correctement détectée (retour non-zéro)"
fi

separator

_start "param_substituer_tout avec template inexistant"
OUT_ERROR="${TEST_DIR}/out_error.txt"
if param_substituer_tout "/chemin/inexistant/template.txt" "$OUT_ERROR" "$CFG_ROOT" 2>/dev/null; then
  fail "param_substituer_tout aurait dû retourner une erreur"
else
  _check "Erreur correctement détectée (retour non-zéro)"
fi

separator_double

# ══════════════════════════════════════════════════════════════════════════════
#  6) Récapitulatif API
# ══════════════════════════════════════════════════════════════════════════════
h2 "6) Tableau récapitulatif"
separator

tableau_init "Fonction" "Rôle" "Exemple"
tableau_add "param_trouver_balises()" "Lister balises @...@ et {{...}}" "param_trouver_balises template.txt"
tableau_add "param_remplacer_balise()" "Remplacer une balise" "param_remplacer_balise tpl out KEY VALUE"
tableau_add "param_valider_template()" "Valider résolutions template/config" "param_valider_template tpl config.yaml"
tableau_add "param_substituer_tout()" "Substituer toutes les balises" "param_substituer_tout tpl out config.yaml chemin_cas"
tableau_print "API substitution_params.sh"

boite_result "Showcase substitution_params.sh terminé avec succès"

echo ""
_note "Répertoire de test: $TEST_DIR"

