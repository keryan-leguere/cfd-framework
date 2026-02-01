#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  test_format.sh — Démonstration de la bibliothèque format.sh
# ═══════════════════════════════════════════════════════════════════════════════

# Charger les bibliothèques
if [[ -z "${CFD_FRAMEWORK}" ]]; then
  echo "ERREUR: Variable CFD_FRAMEWORK non définie" >&2
  exit 1
fi

source "${CFD_FRAMEWORK}/lib/format.sh"

# ══════════════════════════════════════════════════════════════════════════════
#  DÉMONSTRATION
# ══════════════════════════════════════════════════════════════════════════════

reset_counters

h1 "Fonctions de logging"

_info   "Message d'information standard"
_warn   "Avertissement : attire l'attention"
_error  "Erreur : signale un problème"
_result "Succès : opération réussie"
_debug  "Debug : message de débogage (VERBOSE>=2)"
_start  "Démarrage d'une action"
_end    "Fin d'une action"
_wait   "En attente de ressources..."
_note   "Note importante"

separator_double

h2 "Listes et tâches"

_bullet "Premier élément"
_bullet "Deuxième élément"
_check  "Tâche terminée"
_cross  "Tâche échouée"

separator

h2 "Encadrés"

boite_info "Message d'information"
boite_result "Opération réussie"
boite_warn "Attention requise"
boite_error "Erreur critique"

separator

h2 "Affichage clé-valeur"
h3 "test1"
h3 "test2"
h3 "test3"

confirmer "Ça s'affiche ?" o && echo OK || echo KO

action=$(choisir_option "Action principale" \
  "Lancer la simulation" \
  "Afficher les paramètres" \
  "Quitter") || exit 1

case "$action" in
  "Lancer la simulation")
    confirmer "Confirmer le lancement ?" o || exit 0
    _result "Simulation lancée"
    ;;

  "Afficher les paramètres")
    _result "Affichage des paramètres"
    ;;

  "Quitter")
    _error "Au revoir"  
    ;;
esac


kv "Solveur" "OpenFOAM v2312"
kv "Maillage" "3.2M cellules"
kv "Itérations" "10000"

separator

h2 "Tableaux"

tableau_init "Paramètre" "Valeur" "Unité"

tableau_add "Solveur" "OpenFOAM v2312" ""
tableau_add "Maillage" "3.2M cellules" ""
tableau_add "Itérations" "10 000" ""
tableau_add "Temps" "1.25" "s"

tableau_print "Simulation CFD"


separator

h2 "Barre de progression"

progres_init "Traitement" 1000
for i in {1..1000}; do
  progres_update $i
  sleep 0.01
done
progres_done "Terminé"

separator

h2 "Spinner"

spinner "Opération en cours..." "sleep 10"

separator

h2 "Affichage inline"

for step in "Étape 1/3..." "Étape 2/3..." "Étape 3/3..."; do
  inline "$step"
  sleep 5
done
inline "✅ Terminé"
inline_done

separator_eq

h1 "Bannières CFD"

title_post_processing
titre_surveillance
titre_archivage
titre_deploiement
title_launch_simulation

separator_wave

boite_result "Démonstration terminée"
