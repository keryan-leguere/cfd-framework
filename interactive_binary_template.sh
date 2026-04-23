#!/usr/bin/env bash
# Template : lancer un binaire interactif avec des réponses prédéfinies (ex: 1, 6, 2).
# Si le programme lit depuis /dev/tty au lieu de stdin, utilisez `expect` ou l’option
# du programme pour le mode non interactif.

set -euo pipefail

# --- configuration ---
BINARY="${BINARY:-./mon_programme}"   # chemin du binaire (surcharge : BINARY=/chemin/vers/foo ./script.sh)
ANSWERS=(
  "1"
  "6"
  "2"
)

# Construit les lignes à envoyer sur stdin (une réponse par ligne).
build_stdin() {
  local line
  for line in "${ANSWERS[@]}"; do
    printf '%s\n' "$line"
  done
}

main() {
  if [[ ! -f "$BINARY" ]]; then
    echo "Erreur : binaire introuvable : $BINARY" >&2
    exit 1
  fi
  if [[ ! -x "$BINARY" ]]; then
    echo "Erreur : pas exécutable : $BINARY (chmod +x ?)" >&2
    exit 1
  fi

  # Exécution : les réponses sont injectées dans l’ordre.
  build_stdin | "$BINARY" "$@"
}

main "$@"
