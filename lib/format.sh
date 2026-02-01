#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  format.sh — Bibliothèque de formatage professionnelle pour scripts CFD
# ═══════════════════════════════════════════════════════════════════════════════
#
#  📚 Fonctions disponibles :
#     • Logging        : _info, _warn, _error, _result, _debug, _note, _bullet, die
#     • Titres         : title, h1, h2, h3
#     • Séparateurs    : separator, separator_eq, separator_double
#     • Progression    : progres_init, progres_update, progres_done
#     • Interactivité  : confirmer, choisir_option
#     • Affichage TTY  : inline, inline_done, spinner
#     • Bannières CFD  : titre_surveillance, titre_archivage, titre_deploiement,
#                        title_post_processing, title_launch_simulation
#
#  Auteur : KL
#  Licence : MIT
# ═══════════════════════════════════════════════════════════════════════════════

# ── Détection si le fichier est sourcé ou exécuté ─────────────────────────────
_is_sourced() {
  # Retourne 0 si sourcé, 1 si exécuté
  (return 0 2>/dev/null)
}

# Mode strict uniquement en exécution directe (PAS quand sourcé)
if ! _is_sourced; then
  set -Eeuo pipefail
  IFS=$'\n\t'
fi

# ══════════════════════════════════════════════════════════════════════════════
#  🎨 PALETTE DE COULEURS PROFESSIONNELLES (TTY-aware)
# ══════════════════════════════════════════════════════════════════════════════

if [[ -t 1 ]]; then
  # Styles de base
  RESET="\033[0m"
  BOLD="\033[1m"
  DIM="\033[2m"
  ITALIC="\033[3m"
  UNDERLINE="\033[4m"
  BLINK="\033[5m"
  
  # Couleurs principales (vives et professionnelles)
  BLACK="\033[0;30m"
  RED="\033[1;31m"
  GREEN="\033[1;32m"
  YELLOW="\033[1;33m"
  BLUE="\033[1;34m"
  MAGENTA="\033[1;35m"
  CYAN="\033[1;36m"
  WHITE="\033[1;37m"
  
  # Couleurs douces (pastels)
  LIGHT_RED="\033[0;91m"
  LIGHT_GREEN="\033[0;92m"
  LIGHT_YELLOW="\033[0;93m"
  LIGHT_BLUE="\033[0;94m"
  LIGHT_MAGENTA="\033[0;95m"
  LIGHT_CYAN="\033[0;96m"
  
  # Couleurs de fond
  BG_RED="\033[41m"
  BG_GREEN="\033[42m"
  BG_YELLOW="\033[43m"
  BG_BLUE="\033[44m"
  BG_MAGENTA="\033[45m"
  BG_CYAN="\033[46m"
  BG_WHITE="\033[47m"
  
  # Couleurs thématiques pour CFD
  COLOR_INFO="$CYAN"
  COLOR_WARN="$YELLOW"
  COLOR_ERROR="$RED"
  COLOR_SUCCESS="$GREEN"
  COLOR_DEBUG="$DIM"
  COLOR_NOTE="$LIGHT_MAGENTA"
  COLOR_TITLE="$BOLD$GREEN"
  COLOR_HEADER="$BOLD$CYAN"
  COLOR_ACCENT="$MAGENTA"
else
  # Mode non-TTY : pas de couleurs
  RESET=""; BOLD=""; DIM=""; ITALIC=""; UNDERLINE=""; BLINK=""
  BLACK=""; RED=""; GREEN=""; YELLOW=""; BLUE=""; MAGENTA=""; CYAN=""; WHITE=""
  LIGHT_RED=""; LIGHT_GREEN=""; LIGHT_YELLOW=""; LIGHT_BLUE=""; LIGHT_MAGENTA=""; LIGHT_CYAN=""
  BG_RED=""; BG_GREEN=""; BG_YELLOW=""; BG_BLUE=""; BG_MAGENTA=""; BG_CYAN=""; BG_WHITE=""
  COLOR_INFO=""; COLOR_WARN=""; COLOR_ERROR=""; COLOR_SUCCESS=""
  COLOR_DEBUG=""; COLOR_NOTE=""; COLOR_TITLE=""; COLOR_HEADER=""; COLOR_ACCENT=""
fi

# ══════════════════════════════════════════════════════════════════════════════
#  🔧 CONFIGURATION ET UTILITAIRES
# ══════════════════════════════════════════════════════════════════════════════

# Niveau de verbosité (0=silencieux, 1=info, 2=debug)
: "${VERBOSE:=2}"

# Horodatage formaté
ts() { date +"%Y-%m-%dT%H:%M:%S%z"; }

# Largeur du terminal
_get_terminal_width() {
  local cols="${COLUMNS:-$(tput cols 2>/dev/null || echo 80)}"
  echo "$cols"
}

# ══════════════════════════════════════════════════════════════════════════════
#  📝 FONCTIONS DE LOGGING AVEC EMOJIS PROFESSIONNELS
# ══════════════════════════════════════════════════════════════════════════════

# Messages d'information
_info() {
  [[ $VERBOSE -ge 1 ]] && printf "%b%s [INFO]  ℹ️  %s%b\n" "$COLOR_INFO" "$(ts)" "$*" "$RESET"
}

# Avertissements
_warn() {
  printf "%b%s [AVERT] ⚠️  %s%b\n" "$COLOR_WARN" "$(ts)" "$*" "$RESET" >&2
}

# Erreurs
_error() {
  printf "%b%s [ERREUR] ❌ %s%b\n" "$COLOR_ERROR" "$(ts)" "$*" "$RESET" >&2
}

# Succès / Résultats positifs
_result() {
  printf "%b%s [OK]    ✅ %s%b\n" "$COLOR_SUCCESS" "$(ts)" "$*" "$RESET"
}

# Points de liste
_bullet() {
  printf "%b  •%b %s\n" "$COLOR_ACCENT" "$RESET" "$*"
}

# Coche verte pour liste de tâches
_check() {
  printf "%b  ✓%b %s\n" "$COLOR_SUCCESS" "$RESET" "$*"
}

# Croix rouge pour échec
_cross() {
  printf "%b  ✗%b %s\n" "$COLOR_ERROR" "$RESET" "$*"
}

# Note (texte atténué)
_note() {
  printf "%b📝 %s%b\n" "$COLOR_NOTE" "$*" "$RESET"
}

# Messages de débogage (verbosité >= 2)
_debug() {
  [[ $VERBOSE -ge 2 ]] && printf "%b%s [DEBUG] 🔍 %s%b\n" "$COLOR_DEBUG" "$(ts)" "$*" "$RESET"
}

# Message de démarrage d'une action
_start() {
  printf "%b%s [DÉBUT] 🚀 %s%b\n" "$COLOR_SUCCESS" "$(ts)" "$*" "$RESET"
}

# Message de fin d'une action
_end() {
  printf "%b%s [FIN]   🏁 %s%b\n" "$COLOR_SUCCESS" "$(ts)" "$*" "$RESET"
}

# Attente / Traitement en cours
_wait() {
  printf "%b%s [WAIT]  ⏳ %s%b\n" "$COLOR_INFO" "$(ts)" "$*" "$RESET"
}

# Erreur fatale avec sortie
die() {
  _error "$*"
  exit 1
}

# ══════════════════════════════════════════════════════════════════════════════
#  🔢 COMPTEURS POUR TITRES HIÉRARCHIQUES
# ══════════════════════════════════════════════════════════════════════════════

sec=0; sub=0; subsub=0

# Réinitialiser les compteurs
reset_counters() {
  sec=0; sub=0; subsub=0
}

# ══════════════════════════════════════════════════════════════════════════════
#  🎯 BLOCS DE TITRE
# ══════════════════════════════════════════════════════════════════════════════

# Titre principal avec bordure élégante
title() {
  echo
  local str="$1"
  local len=${#str}
  local border
  printf -v border '%*s' "$((len + 4))" ''
  border=${border// /═}
  printf "%b╔%s╗%b\n" "$COLOR_TITLE" "$border" "$RESET"
  printf "%b║  %s  ║%b\n" "$COLOR_TITLE" "$str" "$RESET"
  printf "%b╚%s╝%b\n" "$COLOR_TITLE" "$border" "$RESET"
}

# Titre avec icône personnalisée
title_icon() {
  echo
  local icon="$1"
  local str="$2"
  local len=$(( ${#str} + ${#icon} + 3 ))
  local border
  printf -v border '%*s' "$((len + 4))" ''
  border=${border// /═}
  printf "%b╔%s╗%b\n" "$COLOR_TITLE" "$border" "$RESET"
  printf "%b║  %s  %s  ║%b\n" "$COLOR_TITLE" "$icon" "$str" "$RESET"
  printf "%b╚%s╝%b\n" "$COLOR_TITLE" "$border" "$RESET"
}

# ══════════════════════════════════════════════════════════════════════════════
#  📋 EN-TÊTES HIÉRARCHIQUES : h1 / h2 / h3
# ══════════════════════════════════════════════════════════════════════════════

h1() {
  ((sec++)); sub=0; subsub=0
  local header="══ ${sec}. $1 ══"
  echo
  printf '%*s\n' "${#header}" '' | tr ' ' '═'
  printf "%b%s%b\n" "$BOLD$COLOR_HEADER" "$header" "$RESET"
  printf '%*s\n\n' "${#header}" '' | tr ' ' '═'
}

h2() {
  ((sub++)); subsub=0
  local header="── ${sec}.${sub} $1 ──"
  echo
  printf "%b%s%b\n" "$BOLD$LIGHT_CYAN" "$header" "$RESET"
  printf '%*s\n\n' "${#header}" '' | tr ' ' '─'
}

h3() {
  ((subsub++))
  printf "\n%b  ▸ %s.%s.%s %s%b\n\n" "$BOLD" "$sec" "$sub" "$subsub" "$1" "$RESET"
}

# ══════════════════════════════════════════════════════════════════════════════
#  ➖ SÉPARATEURS VISUELS
# ══════════════════════════════════════════════════════════════════════════════

separator() {
  local cols="$(_get_terminal_width)"
  local wave=""
  for ((i=0; i<cols; i++)); do wave+="─"; done
  printf "%b%s%b\n" "$LIGHT_CYAN" "$wave" "$RESET"
}

separator_eq() {
  local cols="$(_get_terminal_width)"
  local wave=""
  for ((i=0; i<cols; i++)); do wave+="="; done
  printf "%b%s%b\n" "$LIGHT_CYAN" "$wave" "$RESET"
}

separator_double() {
  local cols="$(_get_terminal_width)"
  local wave=""
  for ((i=0; i<cols; i++)); do wave+="═"; done
  printf "%b%s%b\n" "$LIGHT_CYAN" "$wave" "$RESET"
}

separator_wave() {
  local cols="$(_get_terminal_width)"
  local wave=""
  for ((i=0; i<cols; i++)); do wave+="~"; done
  printf "%b%s%b\n" "$LIGHT_CYAN" "$wave" "$RESET"
}

# ══════════════════════════════════════════════════════════════════════════════
#  📊 BARRE DE PROGRESSION
# ══════════════════════════════════════════════════════════════════════════════

# Variables globales pour la progression
_PROGRES_TOTAL=100
_PROGRES_CURRENT=0
_PROGRES_MSG=""
_PROGRES_WIDTH=40

_PROGRES_START_TS=0
_PROGRES_LAST_TS=0


now_ts() {
  date +%s
}

format_eta() {
  local sec="$1"
  (( sec < 0 )) && sec=0

  if (( sec >= 3600 )); then
    printf "%02dh%02dm%02ds" \
      $((sec/3600)) $((sec%3600/60)) $((sec%60))
  elif (( sec >= 60 )); then
    printf "%02dm%02ds" $((sec/60)) $((sec%60))
  else
    printf "%02ds" "$sec"
  fi
}

# Initialiser la barre de progression
progres_init() {
  local msg="${1:-Progression}"
  local total="${2:-100}"

  _PROGRES_MSG="$msg"
  _PROGRES_TOTAL="$total"
  _PROGRES_CURRENT=0

  _PROGRES_START_TS=$(now_ts)
  _PROGRES_LAST_TS=$_PROGRES_START_TS

  progres_update 0
}


# Mettre à jour la progression
progres_update() {
  local current="${1:-$_PROGRES_CURRENT}"
  _PROGRES_CURRENT="$current"

  local now pct filled empty
  now=$(now_ts)

  if [[ $_PROGRES_TOTAL -gt 0 ]]; then
    pct=$(( current * 100 / _PROGRES_TOTAL ))
  else
    pct=0
  fi

  filled=$(( pct * _PROGRES_WIDTH / 100 ))
  empty=$(( _PROGRES_WIDTH - filled ))

  local bar=""
  for ((i=0; i<filled; i++)); do bar+="█"; done
  for ((i=0; i<empty; i++)); do bar+="░"; done

  # ───── vitesse & ETA
  local elapsed=$(( now - _PROGRES_START_TS ))
  local speed eta

  if (( elapsed > 0 && current > 0 )); then
    speed=$(awk "BEGIN { printf \"%.2f\", $current / $elapsed }")
    eta=$(awk "BEGIN { printf \"%d\", ($_PROGRES_TOTAL - $current) / ($current / $elapsed) }")
  else
    speed="0.00"
    eta=0
  fi

  if [[ -t 1 ]]; then
    printf "\r\033[2K%b⏳ %s [%s] %3d%% | %s/s | ETA %s%b" \
      "$COLOR_INFO" \
      "$_PROGRES_MSG" \
      "$bar" \
      "$pct" \
      "$speed" \
      "$(format_eta "$eta")" \
      "$RESET"
  else
    printf "%b⏳ %s [%s] %3d%% | %s/s | ETA %s%b\n" \
      "$COLOR_INFO" \
      "$_PROGRES_MSG" \
      "$bar" \
      "$pct" \
      "$speed" \
      "$(format_eta "$eta")" \
      "$RESET"
  fi
}


progres_done() {
  local msg="${1:-Terminé}"
  local bar=""

  for ((i=0; i<_PROGRES_WIDTH; i++)); do bar+="█"; done

  local total_time=$(( $(now_ts) - _PROGRES_START_TS ))

  printf "\r\033[2K%b✅ %s [%s] 100%% | %s%b\n" \
    "$COLOR_SUCCESS" \
    "$msg" \
    "$bar" \
    "$(format_eta "$total_time")" \
    "$RESET"
}


# ══════════════════════════════════════════════════════════════════════════════
#  🔄 SPINNER D'ATTENTE
# ══════════════════════════════════════════════════════════════════════════════

spinner() {
  local msg="$1"; shift
  printf "%b⏳ %s %b" "$COLOR_INFO" "$msg" "$RESET"
  eval "$@" &
  local pid=$!
  local sp='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏' i=0
  
  while kill -0 "$pid" 2>/dev/null; do
    printf "\b%s" "${sp:i%${#sp}:1}"
    sleep 0.1
    ((i++))
  done
  
  wait "$pid"
  local ret=$?
  
  if [[ $ret -eq 0 ]]; then
    printf "\b%b✅ [Fait]%b\n" "$COLOR_SUCCESS" "$RESET"
  else
    printf "\b%b❌ [Échec]%b\n" "$COLOR_ERROR" "$RESET"
  fi
  return $ret
}

# ══════════════════════════════════════════════════════════════════════════════
#  💬 AFFICHAGE INLINE (TTY-AWARE)
# ══════════════════════════════════════════════════════════════════════════════

inline() {
  local text="$*"
  if [[ -t 1 ]]; then
    local cols="$(_get_terminal_width)"
    printf "\r%b%-*s%b" "$COLOR_INFO" "$cols" "$text" "$RESET"
  else
    printf "%s\n" "$text"
  fi
}

inline_done() {
  [[ -t 1 ]] && printf "\n"
}

# ══════════════════════════════════════════════════════════════════════════════
#  ❓ INTERACTIONS UTILISATEUR
# ══════════════════════════════════════════════════════════════════════════════

# Demander une confirmation oui/non
confirmer() {
  local question="${1:-Voulez-vous continuer ?}"
  local default="${2:-n}"

  local prompt
  if [[ "$default" == "o" ]]; then
    prompt="[${BOLD}O${RESET}${COLOR_INFO}/n]"
  else
    prompt="[o/${BOLD}N${RESET}${COLOR_INFO}]"
  fi

  printf "%b❓ %s %b : %b" "$COLOR_INFO" "$question" "$prompt" "$RESET" > /dev/tty
  read -r reponse < /dev/tty

  reponse="${reponse:-$default}"
  reponse="${reponse,,}"

  [[ "$reponse" == "o" || "$reponse" == "oui" || "$reponse" == "y" || "$reponse" == "yes" ]]
}



# Menu de sélection numéroté
choisir_option() {
  local titre="$1"
  shift
  local options=("$@")

  {
    echo
    printf "%b╭─ 📋 %s%b\n" "$COLOR_HEADER" "$titre" "$RESET"
    printf "%b│%b\n" "$COLOR_HEADER" "$RESET"

    local i=1
    for opt in "${options[@]}"; do
      printf "%b│%b  %b%d)%b %s\n" "$COLOR_HEADER" "$RESET" "$BOLD" "$i" "$RESET" "$opt"
      ((i++))
    done

    printf "%b│%b\n" "$COLOR_HEADER" "$RESET"
    printf "%b╰─ Votre choix [1-%d] : %b" "$COLOR_HEADER" "${#options[@]}" "$RESET"
  } > /dev/tty

  local choix
  read -r choix < /dev/tty

  if [[ "$choix" =~ ^[0-9]+$ ]] &&
     [[ "$choix" -ge 1 ]] &&
     [[ "$choix" -le "${#options[@]}" ]]; then
    echo "${options[$((choix-1))]}"
    return 0
  else
    _error "Choix invalide : $choix"
    return 1
  fi
}


# ══════════════════════════════════════════════════════════════════════════════
#  🎨 BANNIÈRES ASCII ART POUR CFD
# ══════════════════════════════════════════════════════════════════════════════

title_post_processing() {
  printf "%b" "$COLOR_TITLE"
  cat <<'EOF'
 ╔════════════════════════════════════════════════════════════════════════════════════════════╗
 ║                                                                                            ║
 ║      ██████╗  ██████╗ ███████╗████████╗                                                    ║
 ║      ██╔══██╗██╔═══██╗██╔════╝╚══██╔══╝                                                    ║
 ║      ██████╔╝██║   ██║███████╗   ██║                                                       ║
 ║      ██╔═══╝ ██║   ██║╚════██║   ██║                                                       ║
 ║      ██║     ╚██████╔╝███████║   ██║                                                       ║
 ║      ╚═╝      ╚═════╝ ╚══════╝   ╚═╝                                                       ║
 ║      ████████╗██████╗  █████╗ ██╗████████╗███████╗███╗   ███╗███████╗███╗   ██║████████╗   ║
 ║      ╚══██╔══╝██╔══██╗██╔══██╗██║╚══██╔══╝██╔════╝████╗ ████║██╔════╝████╗  ██║╚══██╔══╝   ║
 ║         ██║   ██████╔╝███████║██║   ██║   █████╗  ██╔████╔██║█████╗  ██╔██╗ ██║   ██║      ║
 ║         ██║   ██╔══██╗██╔══██║██║   ██║   ██╔══╝  ██║╚██╔╝██║██╔══╝  ██║╚██╗██║   ██║      ║
 ║         ██║   ██║  ██║██║  ██║██║   ██║   ███████╗██║ ╚═╝ ██║███████╗██║ ╚████║   ██║      ║
 ║         ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝   ╚═╝   ╚══════╝╚═╝     ╚═╝╚══════╝╚═╝  ╚═══║   ╚═╝      ║
 ║                                                                                            ║
 ║                           📊 Post-traitement CFD                                     KL    ║
 ╚════════════════════════════════════════════════════════════════════════════════════════════╝
EOF
  printf "%b\n" "$RESET"
}

title_launch_simulation() {
  printf "%b" "$COLOR_SUCCESS"
  cat <<'EOF'
 ╔═══════════════════════════════════════════════════════════════════════════════════════╗
 ║                                                                                       ║
 ║      ███████╗██╗███╗   ███╗██╗   ██╗██╗      █████╗ ████████╗██╗ ██████╗ ███╗   ██║   ║
 ║      ██╔════╝██║████╗ ████║██║   ██║██║     ██╔══██╗╚══██╔══╝██║██╔═══██╗████╗  ██║   ║
 ║      ███████╗██║██╔████╔██║██║   ██║██║     ███████║   ██║   ██║██║   ██║██╔██╗ ██║   ║
 ║      ╚════██║██║██║╚██╔╝██║██║   ██║██║     ██╔══██║   ██║   ██║██║   ██║██║╚██╗██║   ║
 ║      ███████║██║██║ ╚═╝ ██║╚██████╔╝███████╗██║  ██║   ██║   ██║╚██████╔╝██║ ╚████║   ║
 ║      ╚══════╝╚═╝╚═╝     ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝   ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═══║   ║
 ║                                                                                       ║
 ║                          🚀 Lancement du Calcul CFD                              KL   ║
 ╚═══════════════════════════════════════════════════════════════════════════════════════╝
EOF
  printf "%b\n" "$RESET"
}

titre_surveillance() {
  printf "%b" "$CYAN"
  cat <<'EOF'
╔═════════════════════════════════════════════════════════════════════════════════════════════════════╗
║                                                                                                     ║
║   ███████╗██╗   ██╗██████╗ ██╗   ██╗███████╗██╗██╗     ██╗      █████╗ ███╗   ██║ ██████╗███████╗   ║
║   ██╔════╝██║   ██║██╔══██╗██║   ██║██╔════╝██║██║     ██║     ██╔══██╗████╗  ██║██╔════╝██╔════╝   ║
║   ███████╗██║   ██║██████╔╝██║   ██║█████╗  ██║██║     ██║     ███████║██╔██╗ ██║██║     █████╗     ║
║   ╚════██║██║   ██║██╔══██╗╚██╗ ██╔╝██╔══╝  ██║██║     ██║     ██╔══██║██║╚██╗██║██║     ██╔══╝     ║
║   ███████║╚██████╔╝██║  ██║ ╚████╔╝ ███████╗██║███████╗███████╗██║  ██║██║ ╚████║╚██████╗███████╗   ║
║   ╚══════╝ ╚═════╝ ╚═╝  ╚═╝  ╚═══╝  ╚══════╝╚═╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═══║ ╚═════╝╚══════╝   ║
║                                                                                                     ║
║                         👁️  Surveillance en temps réel                                         KL   ║
╚═════════════════════════════════════════════════════════════════════════════════════════════════════╝
EOF
  printf "%b\n" "$RESET"
}

titre_archivage() {
  printf "%b" "$MAGENTA"
  cat <<'EOF'
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                           ║
║    █████╗ ██████╗  ██████╗██╗  ██╗██╗██╗   ██╗ █████╗  ██████╗ ███████╗   ║
║   ██╔══██╗██╔══██╗██╔════╝██║  ██║██║██║   ██║██╔══██╗██╔════╝ ██╔════╝   ║
║   ███████║██████╔╝██║     ███████║██║██║   ██║███████║██║  ███╗█████╗     ║
║   ██╔══██║██╔══██╗██║     ██╔══██║██║╚██╗ ██╔╝██╔══██║██║   ██║██╔══╝     ║
║   ██║  ██║██║  ██║╚██████╗██║  ██║██║ ╚████╔╝ ██║  ██║╚██████╔╝███████╗   ║
║   ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═══╝  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ║
║                                                                           ║
║                         💾 Archivage des Résultats CFD               KL   ║
╚═══════════════════════════════════════════════════════════════════════════╝
EOF
  printf "%b\n" "$RESET"
}

titre_deploiement() {
  printf "%b" "$YELLOW"
  cat <<'EOF'
╔═══════════════════════════════════════════════════════════════════════════════════════════════╗
║                                                                                               ║         
║   ██████╗ ███████╗██████╗ ██╗      ██████╗ ██╗███████╗███╗   ███╗███████╗███╗  ██║████████╗   ║
║   ██╔══██╗██╔════╝██╔══██╗██║     ██╔═══██╗██║██╔════╝████╗ ████║██╔════╝████╗ ██║╚══██╔══╝   ║
║   ██║  ██║█████╗  ██████╔╝██║     ██║   ██║██║█████╗  ██╔████╔██║█████╗  ██╔██╗██║   ██║      ║
║   ██║  ██║██╔══╝  ██╔═══╝ ██║     ██║   ██║██║██╔══╝  ██║╚██╔╝██║██╔══╝  ██║╚████║   ██║      ║
║   ██████╔╝███████╗██║     ███████╗╚██████╔╝██║███████╗██║ ╚═╝ ██║███████╗██║ ╚███║   ██║      ║
║   ╚═════╝ ╚══════╝╚═╝     ╚══════╝ ╚═════╝ ╚═╝╚══════╝╚═╝     ╚═╝╚══════╝╚═╝  ╚══║   ╚═╝      ║
║                                                                                               ║         
║                         🚀 Déploiement vers Production                                   KL   ║         
╚═══════════════════════════════════════════════════════════════════════════════════════════════╝
EOF
  printf "%b\n" "$RESET"
}

# ══════════════════════════════════════════════════════════════════════════════
#  📦 AFFICHAGE DE TABLEAUX
# ══════════════════════════════════════════════════════════════════════════════


declare -a _TABLE_HEADERS
declare -a _TABLE_WIDTHS
declare -a _TABLE_ROWS

# ─────────────────────────────────────────────────────────────────────────────
# Largeur UTF-8
str_width() {
  printf "%s" "$1" | wc -m
}

# ─────────────────────────────────────────────────────────────────────────────
tableau_init() {
  _TABLE_HEADERS=("$@")
  _TABLE_ROWS=()
  _TABLE_WIDTHS=()

  for i in "${!_TABLE_HEADERS[@]}"; do
    _TABLE_WIDTHS[$i]=$(str_width "${_TABLE_HEADERS[$i]}")
  done
}

# ─────────────────────────────────────────────────────────────────────────────
tableau_add() {
  local row=("$@")
  _TABLE_ROWS+=("$(printf "%s\t" "${row[@]}")")

  for i in "${!row[@]}"; do
    local w
    w=$(str_width "${row[$i]}")
    (( w > _TABLE_WIDTHS[$i] )) && _TABLE_WIDTHS[$i]=$w
  done
}

# ─────────────────────────────────────────────────────────────────────────────
print_cell() {
  local text="$1"
  local width="$2"

  local len pad
  len=$(str_width "$text")
  pad=$(( width - len ))
  (( pad < 0 )) && pad=0

  printf " %s%*s │" "$text" "$pad" ""
}

# ─────────────────────────────────────────────────────────────────────────────
print_line() {
  local left="$1" mid="$2" right="$3"

  printf "%b%s" "$COLOR_HEADER" "$left"
  for i in "${!_TABLE_WIDTHS[@]}"; do
    printf "─%.0s" $(seq 1 $((_TABLE_WIDTHS[$i] + 2)))
    [[ $i -lt $((${#_TABLE_WIDTHS[@]} - 1)) ]] && printf "%s" "$mid" || printf "%s" "$right"
  done
  printf "%b\n" "$RESET"
}

# ─────────────────────────────────────────────────────────────────────────────
tableau_print() {
  local title="$1"

  printf "\n%b┌─ %s%b\n" "$COLOR_HEADER" "$title" "$RESET"
  print_line "├" "┬" "┤"

  # En-têtes
  printf "%b│" "$DIM"
  for i in "${!_TABLE_HEADERS[@]}"; do
    print_cell "${_TABLE_HEADERS[$i]}" "${_TABLE_WIDTHS[$i]}"
  done
  printf "%b\n" "$RESET"

  print_line "├" "┼" "┤"

  # Lignes
  for row in "${_TABLE_ROWS[@]}"; do
    IFS=$'\t' read -r -a cols <<< "$row"
    printf "│"

    for ((i=0; i<${#_TABLE_WIDTHS[@]}; i++)); do
      print_cell "${cols[$i]:-}" "${_TABLE_WIDTHS[$i]}"
    done

    printf "\n"
  done

  print_line "└" "┴" "┘"
  printf "\n"
}

# ══════════════════════════════════════════════════════════════════════════════
#  🎭 ENCADRÉS ET BOÎTES
# ══════════════════════════════════════════════════════════════════════════════

# Encadré d'information
boite_info() {
  local msg="$1"
  local len=${#msg}
  local border
  printf -v border '%*s' "$((len + 5))" ''
  border=${border// /─}
  
  printf "\n%b╭%s╮%b\n" "$COLOR_INFO" "$border" "$RESET"
  printf "%b│ ℹ️ %s │%b\n" "$COLOR_INFO" "$msg" "$RESET"
  printf "%b╰%s╯%b\n\n" "$COLOR_INFO" "$border" "$RESET"
}

# Encadré d'avertissement
boite_warn() {
  local msg="$1"
  local len=${#msg}
  local border
  printf -v border '%*s' "$((len + 5))" ''
  border=${border// /─}
  
  printf "\n%b╭%s╮%b\n" "$COLOR_WARN" "$border" "$RESET"
  printf "%b│ ⚠️ %s │%b\n" "$COLOR_WARN" "$msg" "$RESET"
  printf "%b╰%s╯%b\n\n" "$COLOR_WARN" "$border" "$RESET"
}

# Encadré d'erreur
boite_error() {
  local msg="$1"
  local len=${#msg}
  local border
  printf -v border '%*s' "$((len + 5))" ''
  border=${border// /─}
  
  printf "\n%b╭%s╮%b\n" "$COLOR_ERROR" "$border" "$RESET"
  printf "%b│ ❌ %s │%b\n" "$COLOR_ERROR" "$msg" "$RESET"
  printf "%b╰%s╯%b\n\n" "$COLOR_ERROR" "$border" "$RESET"
}

# Encadré de succès
boite_result() {
  local msg="$1"
  local len=${#msg}
  local border
  printf -v border '%*s' "$((len + 5))" ''
  border=${border// /─}
  
  printf "\n%b╭%s╮%b\n" "$COLOR_SUCCESS" "$border" "$RESET"
  printf "%b│ ✅ %s │%b\n" "$COLOR_SUCCESS" "$msg" "$RESET"
  printf "%b╰%s╯%b\n\n" "$COLOR_SUCCESS" "$border" "$RESET"
}

# ══════════════════════════════════════════════════════════════════════════════
#  🔧 AFFICHAGE DE CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

# Afficher une paire clé-valeur
kv() {
  local cle="$1"
  local valeur="$2"

  local width=20
  local cle_len
  cle_len=$(printf "%s" "$cle" | wc -m)

  local pad=$(( width - cle_len ))
  (( pad < 0 )) && pad=0

  printf "%b  %s%*s :%b %s\n" \
    "$COLOR_ACCENT" \
    "$cle" "$pad" "" \
    "$RESET" "$valeur"
}


# ══════════════════════════════════════════════════════════════════════════════
#  🏃 DÉMO QUAND EXÉCUTÉ DIRECTEMENT
# ══════════════════════════════════════════════════════════════════════════════

if ! _is_sourced; then
  title_launch_simulation
  
  h1 "Démonstration des fonctionnalités"
  
  h2 "Messages de logging"
  _info   "Chargement de la configuration..."
  _warn   "Option dépréciée détectée"
  _error  "Connexion échouée (simulation)"
  _result "Tous les tests réussis"
  _debug  "Ceci apparaît si VERBOSE>=2"
  _start  "Démarrage du processus"
  _end    "Processus terminé"
  _wait   "En attente de ressources..."
  _note   "Note importante à lire"
  
  h2 "Listes et points"
  _bullet "Premier élément"
  _bullet "Deuxième élément"
  _check  "Tâche terminée"
  _cross  "Tâche échouée"
  
  h2 "Encadrés"
  boite_info "Ceci est un message d'information"
  boite_succes "Opération réussie avec succès"
  boite_avertissement "Attention à cette action"
  boite_erreur "Erreur critique détectée"
  
  h2 "Affichage clé-valeur"
  kv "Solveur" "OpenFOAM v2312"
  kv "Maillage" "3.2M cellules"
  kv "Itérations" "10000"
  
  h3 "Sous-détail"
  
  separator
  
  h2 "Progression animée"
  progres_init "Traitement des données" 100
  for i in {1..100..10}; do
    progres_update $i
    sleep 0.1
  done
  progres_done "Traitement terminé"
  
  separator_eq
  
  h2 "Spinner en action"
  spinner "Opération en cours..." "sleep 1"
  
  separator_wave
  
  _result "Démonstration terminée !"
fi
