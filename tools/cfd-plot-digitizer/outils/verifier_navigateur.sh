#!/usr/bin/env bash
#
# Capture d'écran d'une page dans un vrai Firefox — pour contrôler ce que node
# ne voit pas : rendu du canevas, mise en page, chargement effectif en file://.
#
#   bash outils/verifier_navigateur.sh PAGE.html SORTIE.png [LARGEUR] [HAUTEUR]
#
# Deux pièges, tous deux vérifiés ici plutôt que subis :
#
#   1. Firefox installé en paquet snap (le cas sur Ubuntu depuis 22.04) est
#      confiné : il ne peut lire NI /tmp, NI les dossiers cachés de $HOME.
#      Une page posée là se solde par une capture noire, sans message.
#   2. La capture est prise à l'évènement « load ». Une page qui fait son
#      travail de façon asynchrone après ce moment n'apparaîtra pas dessus ;
#      les pages de vérification embarquent donc leur image en <img> pour
#      qu'elle soit déjà décodée, et opèrent de façon synchrone.
set -euo pipefail

if [ $# -lt 2 ]; then
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
fi

PAGE="$(readlink -f "$1")"
SORTIE="$2"
LARGEUR="${3:-1600}"
HAUTEUR="${4:-1000}"

if [ ! -f "$PAGE" ]; then
  echo "page introuvable : $PAGE" >&2
  exit 1
fi

# Contrôle du confinement snap, qui est la cause n°1 de capture vide.
if readlink -f "$(command -v firefox)" | grep -q snap; then
  case "$PAGE" in
    /tmp/*)
      echo "Firefox (snap) ne peut pas lire /tmp : déplacer la page dans un" >&2
      echo "dossier NON caché de \$HOME avant de relancer." >&2
      exit 1 ;;
    "$HOME"/.*)
      echo "Firefox (snap) ne peut pas lire les dossiers cachés de \$HOME :" >&2
      echo "déplacer la page dans un dossier non caché." >&2
      exit 1 ;;
  esac
fi

rm -f "$SORTIE"
firefox --headless --window-size="$LARGEUR,$HAUTEUR" \
        --screenshot "$(readlink -f "$(dirname "$SORTIE")")/$(basename "$SORTIE")" \
        "file://$PAGE" >/dev/null 2>&1 || true

if [ ! -s "$SORTIE" ]; then
  echo "aucune capture produite — vérifier le confinement et le chemin." >&2
  exit 1
fi

echo "$SORTIE écrit ($(stat -c %s "$SORTIE") octets)"
