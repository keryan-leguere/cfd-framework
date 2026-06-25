#!/usr/bin/env bash
# Crée un mini-cas avec liens symboliques variés pour tester archivage_cas.sh.
set -Euo pipefail

FIXTURE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REAL_CAS="${FIXTURE_DIR}/real_cas"
LINK_CAS="${FIXTURE_DIR}/link_cas"
EXTERNAL_FILE="${FIXTURE_DIR}/external_data.txt"

rm -rf "$REAL_CAS" "$LINK_CAS" "$EXTERNAL_FILE"
mkdir -p \
  "${REAL_CAS}/01_MAILLAGE/FICHIER_PARAMETRE" \
  "${REAL_CAS}/02_PARAMS/BASELINE/template" \
  "${REAL_CAS}/03_DECOMPOSITION" \
  "${REAL_CAS}/data"

# Fichiers réels
echo "contenu maillage" > "${REAL_CAS}/01_MAILLAGE/mesh_SURfacique.stp"
echo "param"            > "${REAL_CAS}/01_MAILLAGE/FICHIER_PARAMETRE/params.txt"
echo "job"              > "${REAL_CAS}/03_DECOMPOSITION/job.data"
echo "solver template"  > "${REAL_CAS}/02_PARAMS/BASELINE/template/solver_input.org"
echo "donnee interne"   > "${REAL_CAS}/data/real_file.txt"
echo "donnee externe"   > "$EXTERNAL_FILE"

REAL_PHYS="$(cd "$REAL_CAS" && pwd -P)"

# ── Liens internes (doivent être relativisés) ────────────────────────────────

# 1. Absolu PHYSIQUE — cas typique (readlink -f, outils CFD)
ln -s "${REAL_PHYS}/data/real_file.txt" "${REAL_CAS}/link_abs_phys"

# 2. Absolu LOGIQUE — via chemin logique du cas
ln -s "${REAL_CAS}/data/real_file.txt" "${REAL_CAS}/link_abs_log"

# 3. Relatif — déjà portable, ne doit pas être modifié
ln -s "data/real_file.txt" "${REAL_CAS}/link_rel"

# 4. Chaîne : absolu physique vers un autre lien interne
ln -s "${REAL_PHYS}/data/real_file.txt" "${REAL_CAS}/data/link_chain"

# 5. Lien vers un répertoire interne (absolu physique)
ln -s "${REAL_PHYS}/02_PARAMS" "${REAL_CAS}/link_dir_phys"

# ── Lien externe (doit rester absolu ou être copié avec --copy-external-links) ─
ln -s "$EXTERNAL_FILE" "${REAL_CAS}/link_external"

# ── Accès au cas via symlink (reproduit le bug logique/physique) ─────────────
ln -s "$REAL_CAS" "$LINK_CAS"

cat <<EOF
Fixture créée dans : $FIXTURE_DIR

Structure :
  real_cas/          — cas réel (chemin physique)
  link_cas -> real_cas   — accès logique via symlink

Liens à tester dans real_cas/ :
  link_abs_phys   → cible absolue physique (data/real_file.txt)
  link_abs_log    → cible absolue logique
  link_rel        → cible relative (déjà OK)
  link_chain      → absolu physique (sous data/)
  link_dir_phys   → répertoire 02_PARAMS
  link_external   → fichier hors cas ($EXTERNAL_FILE)

Essai rapide :
  $FIXTURE_DIR/run_test.sh

Archivage manuel :
  scripts/archivage/archivage_cas.sh --no-archive $LINK_CAS
EOF
