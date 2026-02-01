#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  test_utils.sh — Démonstration de la bibliothèque lib/utils.sh
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Objectif:
#  - Montrer comment charger utils.sh
#  - Démontrer les fonctions principales avec des exemples reproductibles
#
#  Usage:
#    export CFD_FRAMEWORK=/chemin/vers/CFD_FRAMEWORK
#    bash tests/lib/test_utils.sh
#
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail
IFS=$'\n\t'

# ── Locale UTF-8 (évite certains soucis sur tr/box-drawing) ────────────────────
# (On ne force pas si indisponible)
export LC_ALL="${LC_ALL:-C.UTF-8}"
export LANG="${LANG:-C.UTF-8}"

# ── Résolution CFD_FRAMEWORK ───────────────────────────────────────────────────
if [[ ! -d "${CFD_FRAMEWORK}/lib" ]]; then
  echo "ERREUR: CFD_FRAMEWORK invalide: ${CFD_FRAMEWORK}" >&2
  exit 1
fi

source "${CFD_FRAMEWORK}/lib/format.sh"
source "${CFD_FRAMEWORK}/lib/utils.sh"

title "=== Test lib/utils.sh ==="

# Petite séparation sans h1/h2 (certains environnements/locale peuvent casser les séparateurs Unicode)
section() {
  echo
  _info "────────────────────────────────────────────────────────────"
  _info "$1"
  _info "────────────────────────────────────────────────────────────"
}

# ══════════════════════════════════════════════════════════════════════════════
#  1) util_verifier_dependances
# ══════════════════════════════════════════════════════════════════════════════
section "1) util_verifier_dependances"
if util_verifier_dependances; then
  _result "Dépendances requises OK"
else
  _error "Dépendances requises manquantes"
  exit 1
fi

# ══════════════════════════════════════════════════════════════════════════════
#  2) util_copier_recursif (equivalent de cp -ra arg1 arg2 ),
# mais avec une sortie plus propre si le dossier arg1 n'existe pas ou que le dossier
# de destination arg2 n'existe pas.
# ══════════════════════════════════════════════════════════════════════════════
section "2) util_copier_recursif"
tmp_root="$(mktemp -d)"
src_dir="${tmp_root}/src"
dst_dir="${tmp_root}/dst"
mkdir -p "${src_dir}/nested"
mkdir -p "${dst_dir}"
echo "hello utils" > "${src_dir}/nested/hello.txt"

util_copier_recursif "${src_dir}/" "${dst_dir}/"

if [[ -f "${dst_dir}/nested/hello.txt" ]]; then
  _result "Copie récursive OK"
  _bullet "Contenu copié: $(cat "${dst_dir}/nested/hello.txt")"
else
  _error "Copie récursive KO: fichier manquant"
  exit 1
fi


# ══════════════════════════════════════════════════════════════════════════════
#  3) util_obtenir_taille
# ══════════════════════════════════════════════════════════════════════════════
section "3) util_obtenir_taille"
taille_src="$(util_obtenir_taille "${src_dir}")" || true
taille_dst="$(util_obtenir_taille "${dst_dir}")" || true
_info "Taille src_dir: ${taille_src}"
_info "Taille dst_dir: ${taille_dst}"
_result "Taille calculée (si du disponible)"

# ══════════════════════════════════════════════════════════════════════════════
#  4) util_nettoyer_chemin
# ══════════════════════════════════════════════════════════════════════════════
section "4) util_nettoyer_chemin"
chemin_bizarre="${tmp_root}//src/../src//nested/hello.txt"
chemin_nettoye="$(util_nettoyer_chemin "${chemin_bizarre}")"
_info "Chemin initial : ${chemin_bizarre}"
_info "Chemin nettoyé : ${chemin_nettoye}"
if [[ -e "${chemin_nettoye}" ]]; then
  _result "Chemin nettoyé pointe vers un fichier existant"
else
  _warn "Chemin nettoyé ne pointe pas vers un fichier existant (outil realpath/readlink non dispo?)"
fi

# ══════════════════════════════════════════════════════════════════════════════
#  5) util_resoudre_liens
# ══════════════════════════════════════════════════════════════════════════════
section "5) util_resoudre_liens"
link_dir="${tmp_root}/links"
mkdir -p "${link_dir}"
echo "target content" > "${link_dir}/target.txt"
ln -s "${link_dir}/target.txt" "${link_dir}/link.txt"

if [[ -L "${link_dir}/link.txt" ]]; then
  _result "Symlink créé"
else
  _warn "Impossible de créer un symlink (permissions/fs?) — test réduit"
fi

ls -larth $link_dir

util_resoudre_liens "${tmp_root}"

if [[ -L "${link_dir}/link.txt" ]]; then
  _error "Résolution des liens KO: link.txt est toujours un symlink"
  exit 1
fi

ls -larth $link_dir

if [[ -f "${link_dir}/link.txt" ]]; then
  _result "Résolution des liens OK (link.txt est maintenant un fichier)"
  _bullet "Contenu: $(cat "${link_dir}/link.txt")"
else
  _warn "link.txt absent après résolution (cas particulier)"
fi

# ══════════════════════════════════════════════════════════════════════════════
#  6) util_verifier_repertoire
# ══════════════════════════════════════════════════════════════════════════════
section "6) util_verifier_repertoire"
case_dir="${tmp_root}/CASE_TEST"
mkdir -p \
  "${case_dir}/01_MAILLAGE" \
  "${case_dir}/02_PARAMS" \
  "${case_dir}/03_DECOMPOSITION" \
  "${case_dir}/04_CONDITION_INITIALE" \
  "${case_dir}/05_DOCUMENTATION" \
  "${case_dir}/06_REFERENCE" \
  "${case_dir}/07_NOTE" \
  "${case_dir}/08_RESULTAT" \
  "${case_dir}/09_POST_TRAITEMENT" \
  "${case_dir}/10_SCRIPT"

if util_verifier_repertoire "${case_dir}"; then
  _result "Structure de cas: OK"
else
  _error "Structure de cas: KO (ne devrait pas)"
  exit 1
fi

rm -rf "${case_dir}/06_REFERENCE"
if util_verifier_repertoire "${case_dir}"; then
  _error "Structure invalide détectée comme OK (ne devrait pas)"
  exit 1
else
  _result "Structure invalide correctement détectée (répertoire manquant)"
fi

# ══════════════════════════════════════════════════════════════════════════════
#  Nettoyage
# ══════════════════════════════════════════════════════════════════════════════
rm -rf "${tmp_root}"
boite_result "Tests utils.sh terminés"

