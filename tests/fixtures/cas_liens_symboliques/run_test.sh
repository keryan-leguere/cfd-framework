#!/usr/bin/env bash
# Lance archivage_cas.sh sur la fixture liens symboliques et vérifie le résultat.
set -Euo pipefail

FIXTURE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFD_FRAMEWORK="$(cd "${FIXTURE_DIR}/../../.." && pwd)"
ARCHIVAGE="${CFD_FRAMEWORK}/scripts/archivage/archivage_cas.sh"
LINK_CAS="${FIXTURE_DIR}/link_cas"

# (Re)créer la fixture
"${FIXTURE_DIR}/setup.sh"

if [[ ! -x "$ARCHIVAGE" ]]; then
  chmod +x "$ARCHIVAGE"
fi

echo ""
echo "═══ Archivage via link_cas (symlink logique) ═══"
"$ARCHIVAGE" --no-archive "$LINK_CAS"

# Retrouver le staging (conservé avec --no-archive)
STAGING="$(find "$(dirname "$LINK_CAS")" -maxdepth 1 -type d -name '.cfd-staging-link_cas-*' -printf '%T@ %p\n' 2>/dev/null \
  | sort -rn | head -1 | cut -d' ' -f2-)"
STAGING_CAS="${STAGING}/link_cas"

if [[ ! -d "$STAGING_CAS" ]]; then
  echo "ERREUR: staging introuvable sous $(dirname "$LINK_CAS")" >&2
  exit 1
fi

echo ""
echo "═══ Liens dans le staging après relativisation ═══"
find "$STAGING_CAS" -type l -exec ls -la {} \;

echo ""
echo "═══ Vérifications ═══"
errors=0

check_relative() {
  local name="$1"
  local link="${STAGING_CAS}/${name}"
  local target
  target="$(readlink -n "$link")"
  if [[ "$target" == /* ]]; then
    echo "  ECHEC  $name encore absolu → $target"
    errors=$((errors + 1))
  else
    echo "  OK     $name → $target"
  fi
}

check_still_relative() {
  local name="$1"
  local link="${STAGING_CAS}/${name}"
  local target
  target="$(readlink -n "$link")"
  if [[ "$target" == /* ]]; then
    echo "  ECHEC  $name devenu absolu → $target"
    errors=$((errors + 1))
  else
    echo "  OK     $name toujours relatif → $target"
  fi
}

check_absolute() {
  local name="$1"
  local link="${STAGING_CAS}/${name}"
  local target
  target="$(readlink -n "$link")"
  if [[ "$target" != /* ]]; then
    echo "  ECHEC  $name devrait rester absolu (hors cas) → $target"
    errors=$((errors + 1))
  else
    echo "  OK     $name absolu externe → $target"
  fi
}

check_relative "link_abs_phys"
check_relative "link_abs_log"
check_still_relative "link_rel"
check_relative "data/link_chain"
check_relative "link_dir_phys"
check_absolute "link_external"

echo ""
if (( errors > 0 )); then
  echo "Résultat : $errors erreur(s)" >&2
  exit 1
fi
echo "Résultat : tous les tests passent"
echo "Staging conservé : $STAGING_CAS"
