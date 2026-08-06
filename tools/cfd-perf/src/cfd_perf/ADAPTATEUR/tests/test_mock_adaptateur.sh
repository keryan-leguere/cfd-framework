#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  test_mock_adaptateur.sh — Test bash autonome de l'adaptateur de capture mock
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Vérifie le contrat de capture (adapt_pilote_*) sans solveur ni SLURM.
#  Autonome : aucune dépendance hors de ce répertoire.
#
#  Usage :  bash ADAPTATEUR/tests/test_mock_adaptateur.sh
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADAPTATEUR_DIR="$(cd "${ICI}/.." && pwd)"

# shellcheck disable=SC1091
source "${ADAPTATEUR_DIR}/mock.sh"

ERREURS=0
ok()  { echo "  [OK]  $*"; }
ko()  { echo "  [KO]  $*" >&2; ERREURS=$((ERREURS + 1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "== Adaptateur mock : informations =="
[[ "$(adapt_nom)" == "mock" ]] && ok "adapt_nom = mock" || ko "adapt_nom"
adapt_verifier_installation && ok "installation OK" || ko "installation"
[[ "$(adapt_liste_elements_a_copier | tr '\n' ' ')" == "constant system " ]] \
  && ok "éléments à copier" || ko "éléments à copier"

echo "== Cycle de capture (cœurs = 4 8 16 32) =="
declare -A TPI
for c in 4 8 16 32; do
  d="${TMP}/run_${c}"
  adapt_pilote_preparer "$d" "$c" >/dev/null
  jid="$(adapt_pilote_soumettre "$d" "$c")"
  [[ "$jid" == "LOCAL" ]] || ko "job id (cœurs=$c) : $jid"

  etat="$(adapt_pilote_etat "$d" "$jid")"
  [[ "$etat" == "DONE" ]] || ko "état (cœurs=$c) : $etat"

  temps="$(adapt_pilote_temps_total "$d")"
  niter="$(adapt_pilote_nb_iterations "$d")"
  ram="$(adapt_pilote_ram_crete "$d" "$jid")"

  # Nombres à point décimal (locale neutre), et positifs.
  awk -v t="$temps" 'BEGIN { exit !(t > 0) }' && ok "temps>0 (cœurs=$c) : $temps" \
    || ko "temps (cœurs=$c) : $temps"
  [[ "$niter" == "200" ]] || ko "itérations (cœurs=$c) : $niter"
  awk -v r="$ram" 'BEGIN { exit !(r > 0) }' && ok "ram>0 (cœurs=$c) : $ram" \
    || ko "ram (cœurs=$c) : $ram"

  TPI[$c]="$(awk -v t="$temps" -v n="$niter" 'BEGIN { printf "%.6f", t / n }')"
done

echo "== Temps/itération décroissant au début =="
awk -v a="${TPI[8]}" -v b="${TPI[4]}" 'BEGIN { exit !(a < b) }' \
  && ok "tpi(8) < tpi(4)" || ko "tpi(8) < tpi(4)"
awk -v a="${TPI[16]}" -v b="${TPI[8]}" 'BEGIN { exit !(a < b) }' \
  && ok "tpi(16) < tpi(8)" || ko "tpi(16) < tpi(8)"

echo "== Maillage et itérations cible =="
[[ "$(adapt_maillage_nb_cellules "$TMP")" == "2000000" ]] \
  && ok "nb_cellules (défaut)" || ko "nb_cellules"
echo "750000" > "${TMP}/.mock_cells"
[[ "$(adapt_maillage_nb_cellules "$TMP")" == "750000" ]] \
  && ok "nb_cellules (marqueur)" || ko "nb_cellules marqueur"
[[ "$(adapt_cible_iterations "$TMP")" == "5000" ]] \
  && ok "itérations cible (placeholder)" || ko "itérations cible"

echo ""
if [[ "$ERREURS" -eq 0 ]]; then
  echo "TOUS LES TESTS PASSENT"
  exit 0
else
  echo "ÉCHECS : $ERREURS" >&2
  exit 1
fi
