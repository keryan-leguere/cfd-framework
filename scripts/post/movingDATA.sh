#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  movingDATA.sh — Script pour déplacer les résultats de post-traitement
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Ce script est un script pour déplacer les résultats de post-traitement. Afin de
#  de les comparer aux autres cas-test.
#
#  Usage:
#    ./movingDATA.sh <DATA_DIR> [OPTIONS]
#
#  Options:
#    -h, --help              Afficher cette aide
#    -n, --name              Nom du cas-test
#    -c, --chemin_cas        Chemin vers le cas-test
#    <DATA_DIR>              Répertoire contenant les résultats de post-traitement
#
#  Fonctionnement:
#    1. Copie des fichiers: 
#       Note: Cela correspond au résultats de post-traitement indépendant entre chaque cas-test. (Par ex: distribution de pression) Ces résultats
#       représentent une courbe entière sur un graphe.
#      - Un fichier .dat contenant la liste des fichiers à supprimer. Ce fichier .dat est par défaut placé
#        dans $BASE_DIR/10_SCRIPT/POST_TRAITEMENT/BASH/liste_fichier_post_traitement.dat
#      - L'argument --list-fichier permet de spécifier le chemin vers le fichier .dat contenant la liste des fichiers à copier.
#      L'ensemble du contenu du fichier eset d'abord afficher avec des _bullet puis chaque element est copié vers <DATA_DIR>.
#
#    2. Execution des scripts personnalisés
#      Note: Cela correspond au résultats "scalaires" comme les coefficients aérodynamiques, les erreurs L2, les temps de calcul, qu'il faut
#      concaténer dans un meme fichier pour forme une courbe.
#      - Un fichier .dat contenant la liste des scripts à exécuter. Ce fichier .dat est par défaut placé
#        dans $BASE_DIR/10_SCRIPT/POST_TRAITEMENT/BASH/liste_script_post_traitement.dat
#      - L'argument --list-script permet de spécifier le chemin vers le fichier .dat contenant la liste des scripts à executer.
#      Chaque script custom prendra en argument <DATA_DIR>
#      Chaque script sera stocké dans $BASE_DIR/10_SCRIPT/POST_TRAITEMENT/BASH/DEPLACEMENT/nom_du_script.sh
#
#  Variables d'environnement:
#    CFD_FRAMEWORK           Chemin vers le framework CFD
#    CFD_ADAPTATEUR          Adaptateur à utiliser par défaut
#    CASE_NAME               Nom du cas (requis si --name non fourni)
#    CASE_PATH               Chemin vers le cas-test (requis si --chemin_cas non fourni)
#
#  Auteur : KL
#  Licence : MIT
# ═══════════════════════════════════════════════════════════════════════════════

set -Euo pipefail
IFS=$'\n\t'


# ══════════════════════════════════════════════════════════════════════════════
#  📚 VARIABLES GLOBALES
# ══════════════════════════════════════════════════════════════════════════════
METADATA_YAML=".metadata.yaml"

# ─────────────────────────────────────────────────────────────────────────
# 0. Charger la bibliothèque de formatage
# ─────────────────────────────────────────────────────────────────────────
if [[ -z "${CFD_FRAMEWORK:-}" ]]; then
  echo "❌ ERREUR : La variable d'environnement CFD_FRAMEWORK n'est pas définie."
  echo "   Veuillez définir CFD_FRAMEWORK avant d'exécuter ce script."
  exit 1
fi

source "${CFD_FRAMEWORK}/lib/format.sh"

# ──────────────────────────────────────────────────────────────────────────────────────
# 1. Fonction d'aide
# ──────────────────────────────────────────────────────────────────────────────────────
usage() {
  cat <<EOF
Usage: ./movingDATA.sh <DATA_DIR> [OPTIONS]

Arguments:
  <DATA_DIR>              Répertoire de destination pour les résultats

Options:
  -h, --help              Afficher cette aide
  -n, --name NAME         Nom du cas-test (défaut: basename de CASE_PATH)
  -c, --chemin_cas PATH   Chemin vers le cas-test (défaut: \$CASE_PATH ou pwd)
  --list-fichier PATH     Chemin vers liste_fichier_post_traitement.dat
  --list-script PATH      Chemin vers liste_script_post_traitement.dat

Variables d'environnement:
  CFD_FRAMEWORK           Chemin vers le framework CFD (requis)
  CASE_NAME               Nom du cas (utilisé si --name non fourni)
  CASE_PATH               Chemin vers le cas-test (utilisé si --chemin_cas non fourni)

Exemple:
  ./movingDATA.sh /tmp/DATA -c /path/to/case -n Case01
EOF
  exit 0
}

# ──────────────────────────────────────────────────────────────────────────────────────
# 2. Parsing des arguments
# ──────────────────────────────────────────────────────────────────────────────────────
DATA_DIR=""
CASE_NAME_ARG=""
CASE_PATH_ARG=""
LIST_FICHIER_ARG=""
LIST_SCRIPT_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      afficher_aide
      ;;
    -n|--name)
      CASE_NAME_ARG="$2"
      shift 2
      ;;
    -c|--chemin_cas)
      CASE_PATH_ARG="$2"
      shift 2
      ;;
    --list-fichier)
      LIST_FICHIER_ARG="$2"
      shift 2
      ;;
    --list-script)
      LIST_SCRIPT_ARG="$2"
      shift 2
      ;;
    -*)
      die "Option inconnue: $1 (utilisez -h pour l'aide)"
      ;;
    *)
      if [[ -z "$DATA_DIR" ]]; then
        DATA_DIR="$1"
      else
        die "Trop d'arguments positionnels: $1"
      fi
      shift
      ;;
  esac
done

# ──────────────────────────────────────────────────────────────────────────────────────
# 3. Validation et résolution des chemins
# ──────────────────────────────────────────────────────────────────────────────────────

# Vérifier DATA_DIR
if [[ -z "$DATA_DIR" ]]; then
  boite_error "Argument DATA_DIR requis. Utilisez -h pour l'aide."
  usage
fi

# Créer DATA_DIR si nécessaire
mkdir -p "$DATA_DIR" || die "Impossible de créer le répertoire DATA_DIR: $DATA_DIR"
DATA_DIR=$(cd "$DATA_DIR" && pwd) || die "Impossible de résoudre DATA_DIR: $DATA_DIR"

# Résoudre CASE_PATH
if [[ -n "$CASE_PATH_ARG" ]]; then
  CASE_PATH="$CASE_PATH_ARG"
elif [[ -n "${CASE_PATH:-}" ]]; then
  CASE_PATH="$CASE_PATH"
fi

if [[ ! -d "$CASE_PATH" ]]; then
  boite_error "Le chemin du cas global n'existe pas: $CASE_PATH"
  usage
fi

CASE_PATH=$(cd "$CASE_PATH" && pwd)

# Résoudre CASE_NAME
if [[ -n "$CASE_NAME_ARG" ]]; then
  CASE_NAME="$CASE_NAME_ARG"
elif [[ -n "${CASE_NAME:-}" ]]; then
  CASE_NAME="$CASE_NAME"
fi

if [[ ! -n "$CASE_NAME" ]]; then
  boite_error "Le nom du cas n'existe pas: $CASE_NAME"
  usage
fi

# Déterminer BASE_DIR (remonter depuis l'emplacement du script)
BASE_DIR="$CASE_PATH"
LOCAL_CASE_DIR="$(pwd)"


# Listes par défaut
DEFAULT_LIST_FICHIER="$BASE_DIR/10_SCRIPT/POST_TRAITEMENT/BASH/liste_fichier_post_traitement.dat"
DEFAULT_LIST_SCRIPT="$BASE_DIR/10_SCRIPT/POST_TRAITEMENT/BASH/liste_script_post_traitement.dat"
SCRIPT_DEPLACEMENT_DIR="$BASE_DIR/10_SCRIPT/POST_TRAITEMENT/BASH/DEPLACEMENT"

LIST_FICHIER="${LIST_FICHIER_ARG:-$DEFAULT_LIST_FICHIER}"
LIST_SCRIPT="${LIST_SCRIPT_ARG:-$DEFAULT_LIST_SCRIPT}"

# ──────────────────────────────────────────────────────────────────────────────────────
# 4. Affichage de la bannière et configuration
# ──────────────────────────────────────────────────────────────────────────────────────
h1 "Déplacement des résultats de post-traitement"

_info "Configuration:"
kv "Nom du cas" "$CASE_NAME"
kv "Base du projet" "$BASE_DIR"
kv "Répertoire local" "$LOCAL_CASE_DIR"
kv "Répertoire DATA" "$DATA_DIR"

separator

# ──────────────────────────────────────────────────────────────────────────────────────
# 5. Copie des fichiers listés
# ──────────────────────────────────────────────────────────────────────────────────────
h2 "Copie des fichiers de post-traitement"

if [[ ! -f "$LIST_FICHIER" ]]; then
  boite_warn "Liste des fichiers introuvable: $LIST_FICHIER"
  _note "Aucun fichier ne sera copié"
else
  _info "Lecture de la liste: $LIST_FICHIER"
  
  # Lire les fichiers (ignorer lignes vides et commentaires)
  mapfile -t fichiers < <(grep -v '^\s*$\|^\s*#' "$LIST_FICHIER" || true)
  
  if [[ ${#fichiers[@]} -eq 0 ]]; then
    _note "Aucun fichier à copier dans la liste"
  else
    _info "Fichiers à copier:"
    for f in "${fichiers[@]}"; do
      _bullet "$f"
    done
    echo
    _start "Copie des fichiers..."
    
    copie_ok=0
    copie_echec=0
    
    for fichier_relatif in "${fichiers[@]}"; do
      # Supprimer espaces en début/fin
      fichier_relatif=$(echo "$fichier_relatif" | xargs)
      
      fichier_source="$LOCAL_CASE_DIR/$fichier_relatif"
      fichier_basename=$(basename "$fichier_relatif")
      fichier_dest="$DATA_DIR/${CASE_NAME}_${fichier_basename}"
      
      if [[ -f "$fichier_source" ]]; then
        if cp "$fichier_source" "$fichier_dest"; then
          _check "$fichier_source → $fichier_dest"
          ((copie_ok++))
        else
          _cross "Échec de copie: $fichier_relatif"
          ((copie_echec++))
        fi
      else
        _warn "Fichier source introuvable: $fichier_relatif"
        ((copie_echec++))
      fi
    done
    
    echo
    if [[ $copie_echec -eq 0 ]]; then
      _result "Tous les fichiers copiés avec succès ($copie_ok/$((copie_ok + copie_echec)))"
    else
      _warn "$copie_echec fichier(s) non copié(s), $copie_ok copié(s)"
    fi
  fi
fi

separator 

# ──────────────────────────────────────────────────────────────────────────────────────
# 6. Exécution des scripts personnalisés
# ──────────────────────────────────────────────────────────────────────────────────────
h2 "Exécution des scripts personnalisés"

if [[ ! -f "$LIST_SCRIPT" ]]; then
  boite_warn "Liste des scripts introuvable: $LIST_SCRIPT"
  _note "Aucun script ne sera exécuté"
else
  _info "Lecture de la liste: $LIST_SCRIPT"
  
  # Lire les scripts (ignorer lignes vides et commentaires)
  mapfile -t scripts < <(grep -v '^\s*$\|^\s*#' "$LIST_SCRIPT" || true)
  
  if [[ ${#scripts[@]} -eq 0 ]]; then
    _note "Aucun script à exécuter dans la liste"
  else
    _info "Scripts à exécuter:"
    for s in "${scripts[@]}"; do
      _bullet "$s"
    done
    
    echo
    _start "Exécution des scripts..."
    
    exec_ok=0
    exec_echec=0
    
    for script_nom in "${scripts[@]}"; do
      # Supprimer espaces en début/fin
      script_nom=$(echo "$script_nom" | xargs)
      
      script_path="$SCRIPT_DEPLACEMENT_DIR/$script_nom"
      
      if [[ ! -f "$script_path" ]]; then
        _warn "Script introuvable: $script_path"
        ((exec_echec++))
        continue
      fi
      
      if [[ ! -x "$script_path" ]]; then
        _warn "Script non exécutable: $script_path"
        ((exec_echec++))
        continue
      fi
      
      _info "Exécution: $script_nom..."
      if $script_path $DATA_DIR; then
        _check "$script_nom exécuté avec succès"
        ((exec_ok++))
      else
        _warn "Échec de $script_nom (code de retour: $?)"
        ((exec_echec++))
      fi
    done
    
    echo
    if [[ $exec_echec -eq 0 ]]; then
      _result "Tous les scripts exécutés avec succès ($exec_ok/$((exec_ok + exec_echec)))"
    else
      _warn "$exec_echec script(s) en échec, $exec_ok exécuté(s)"
    fi
  fi
fi

separator_double

# ──────────────────────────────────────────────────────────────────────────────────────
# 7. Résumé final
# ──────────────────────────────────────────────────────────────────────────────────────
_end "Déplacement des résultats terminé"
_result "Résultats disponibles dans: $DATA_DIR"
