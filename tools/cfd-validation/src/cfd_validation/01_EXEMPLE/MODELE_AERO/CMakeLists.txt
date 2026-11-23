# Commandes de base du modèle : construire, essayer, valider, nettoyer.
#
#   cmake -B build                           # une fois (choisit Python, vérifie les outils)
#   cmake --build build                      # construit le module f2py (cible « modele »)
#
# « build is not a directory » / « build n'existe pas » : la première ligne n'a pas
# été lancée (ou l'a été depuis un autre dossier). bash cmake.sh <cible> fait les deux :
# configure build/ s'il manque, puis construit la cible, depuis n'importe où.
#   cmake --build build -t validation        # les quatre tests, puis VALIDATION/SORTIE/RECAP.txt
#   cmake --build build -t validation_production   # idem, copie sans option de falsification
#   cmake --build build -t nettoyer          # efface les sorties (SORTIE/, __pycache__/)
#   cmake --build build -t aide              # toutes les cibles et les réglages
#
# Avec CMakePresets.json (CMake >= 3.21) : cmake --preset defaut, puis
# cmake --build --preset validation.
#
# CMake ne compile rien lui-même : il appelle les scripts du projet
# (PYTHON/construire.sh, VALIDATION/RUN_VALIDATION.sh, les scripts de test), qui
# restent utilisables sans lui. Il ajoute les dépendances (le module est
# reconstruit quand une source change, la validation le construit d'abord) et un
# point d'entrée unique.
#
# Réglages (cmake -B build -D<NOM>=<valeur>) :
#   PYTHON          interpréteur qui a numpy et cfd-validation (et meson, ninja si f2py passe par meson)
#                   (défaut : $CFD_VALIDATION_PYTHON, sinon le venv actif, sinon python3)
#   FC              compilateur Fortran (défaut gfortran)
#   FFLAGS          options de compilation (défaut -O2)
#   MODELE_NOM      nom du module (défaut aerolib ; un autre nom = une autre compilation)
#   VALIDATION_JOBS processus pour les polaires du test 3 (défaut 4)
#   VALIDATION_OPTIONS  options transmises à chaque test (ex. "--sans-figures")
#   PDV_YAML        fichier de points de vol de la cible « pdv » (défaut PYTHON/exemple_pdv.yaml)
cmake_minimum_required(VERSION 3.17)
project(MODELE_AERO LANGUAGES NONE)

if(CMAKE_BINARY_DIR STREQUAL CMAKE_SOURCE_DIR)
    message(FATAL_ERROR
        "Construction dans le dossier des sources refusée (elle y sèmerait CMakeFiles/).\n"
        "Utiliser : cmake -B build\n"
        "puis effacer CMakeCache.txt et CMakeFiles/ créés ici.")
endif()

set(RACINE "${CMAKE_CURRENT_SOURCE_DIR}")
set(DOSSIER_PYTHON "${RACINE}/PYTHON")
set(DOSSIER_VALIDATION "${RACINE}/VALIDATION")
set(SORTIE "${DOSSIER_VALIDATION}/SORTIE")

# -- réglages --------------------------------------------------------------------
if(DEFINED ENV{CFD_VALIDATION_PYTHON})
    set(_python_defaut "$ENV{CFD_VALIDATION_PYTHON}")
elseif(DEFINED ENV{VIRTUAL_ENV} AND EXISTS "$ENV{VIRTUAL_ENV}/bin/python")
    set(_python_defaut "$ENV{VIRTUAL_ENV}/bin/python")
else()
    find_program(_python_trouve NAMES python3 python)
    set(_python_defaut "${_python_trouve}")
endif()
set(PYTHON "${_python_defaut}" CACHE FILEPATH "interpréteur Python (numpy, cfd-validation ; meson, ninja si besoin)")
set(FC "gfortran" CACHE STRING "compilateur Fortran")
set(FFLAGS "-O2" CACHE STRING "options du compilateur Fortran")
set(MODELE_NOM "aerolib" CACHE STRING "nom du module f2py")
set(VALIDATION_JOBS "4" CACHE STRING "processus pour les polaires du test 3")
set(VALIDATION_OPTIONS "" CACHE STRING "options transmises à chaque test (séparées par des espaces)")
set(PDV_YAML "${CMAKE_CURRENT_SOURCE_DIR}/PYTHON/exemple_pdv.yaml" CACHE FILEPATH "points de vol de la cible pdv")
separate_arguments(_options UNIX_COMMAND "${VALIDATION_OPTIONS}")

# -- vérifications (des avertissements : nettoyer doit marcher sans compilateur) --
if(NOT PYTHON OR NOT EXISTS "${PYTHON}")
    message(FATAL_ERROR "Python introuvable : -DPYTHON=/chemin/vers/python")
endif()
execute_process(
    COMMAND "${PYTHON}" -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX'))"
    OUTPUT_VARIABLE EXT_SUFFIX OUTPUT_STRIP_TRAILING_WHITESPACE RESULT_VARIABLE _rc)
if(NOT _rc EQUAL 0)
    message(FATAL_ERROR "${PYTHON} ne répond pas")
endif()

function(verifier_module module role)
    execute_process(COMMAND "${PYTHON}" -c "import ${module}" RESULT_VARIABLE rc OUTPUT_QUIET ERROR_QUIET)
    if(rc EQUAL 0)
        message(STATUS "  ${module} : oui")
    else()
        message(WARNING "${module} absent de ${PYTHON} : ${role}")
    endif()
endfunction()

find_program(FC_CHEMIN NAMES "${FC}")
message(STATUS "Python      : ${PYTHON}")
message(STATUS "Fortran     : ${FC} ${FFLAGS}  (${FC_CHEMIN})")
if(NOT FC_CHEMIN)
    message(WARNING "${FC} introuvable : la cible « modele » échouera")
endif()
verifier_module(numpy "f2py est dans numpy (pip install numpy)")
# f2py choisit son backend seul : distutils tant que numpy.distutils existe, meson sinon.
execute_process(COMMAND "${PYTHON}" -c "import numpy.distutils" RESULT_VARIABLE _sans_distutils OUTPUT_QUIET ERROR_QUIET)
if(_sans_distutils EQUAL 0)
    message(STATUS "  backend f2py : distutils")
else()
    message(STATUS "  backend f2py : meson")
    verifier_module(mesonbuild "f2py passe par meson et en a besoin (pip install meson ninja)")
    verifier_module(ninja "f2py passe par meson et en a besoin (pip install meson ninja)")
endif()
verifier_module(cfd_validation "les tests de VALIDATION/ en ont besoin (pip install -e tools/cfd-validation)")

# -- construire le module ----------------------------------------------------------
set(MODULE "${DOSSIER_PYTHON}/${MODELE_NOM}${EXT_SUFFIX}")
# Les motifs de PYTHON/construire.sh (MOTIFS), plus les INCLUDE
file(GLOB SOURCES_FORTRAN CONFIGURE_DEPENDS
    "${RACINE}/SOURCES/*.f" "${RACINE}/SOURCES/*.F" "${RACINE}/SOURCES/*.for"
    "${RACINE}/SOURCES/*.f90" "${RACINE}/SOURCES/*.F90"
    "${RACINE}/SOURCES/*.inc" "${RACINE}/SOURCES/*.h" "${RACINE}/SOURCES/*.fi")
message(STATUS "Module      : ${MODULE}")

add_custom_command(
    OUTPUT "${MODULE}"
    COMMAND ${CMAKE_COMMAND} -E env "FC=${FC}" "FFLAGS=${FFLAGS}" "CFD_VALIDATION_PYTHON=${PYTHON}"
            bash "${DOSSIER_PYTHON}/construire.sh" "${MODELE_NOM}" "${DOSSIER_PYTHON}"
    DEPENDS ${SOURCES_FORTRAN} "${DOSSIER_PYTHON}/construire.sh"
    COMMENT "f2py : SOURCES/ -> PYTHON/${MODELE_NOM}${EXT_SUFFIX} (${FC} ${FFLAGS}), journal PYTHON/${MODELE_NOM}.compilation.log"
    USES_TERMINAL VERBATIM)
add_custom_target(modele ALL DEPENDS "${MODULE}")
set(JOURNAL_COMPILATION "${DOSSIER_PYTHON}/${MODELE_NOM}.compilation.log")
set_property(DIRECTORY APPEND PROPERTY ADDITIONAL_CLEAN_FILES "${MODULE}" "${JOURNAL_COMPILATION}")

# -- essayer -----------------------------------------------------------------------
add_custom_target(exemple
    COMMAND "${PYTHON}" exemple_appel.py
    WORKING_DIRECTORY "${DOSSIER_PYTHON}"
    DEPENDS modele
    COMMENT "Un point et un DataFrame de 180 cas (PYTHON/exemple_appel.py)"
    USES_TERMINAL VERBATIM)

add_custom_target(pdv
    COMMAND "${PYTHON}" calcul_yaml.py "${PDV_YAML}" --module "${MODELE_NOM}"
    WORKING_DIRECTORY "${DOSSIER_PYTHON}"
    DEPENDS modele
    COMMENT "Points de vol de ${PDV_YAML} -> CSV (PYTHON/calcul_yaml.py)"
    USES_TERMINAL VERBATIM)

# -- valider -----------------------------------------------------------------------
add_custom_target(validation
    COMMAND ${CMAKE_COMMAND} -E env "CFD_VALIDATION_PYTHON=${PYTHON}"
            bash "${DOSSIER_VALIDATION}/RUN_VALIDATION.sh" --module "${MODELE_NOM}" ${_options}
    DEPENDS modele
    COMMENT "Les quatre tests, puis VALIDATION/SORTIE/RECAP.txt"
    USES_TERMINAL VERBATIM)
# La copie de production : mêmes tests, aucune option pour en fausser un.
add_custom_target(validation_production
    COMMAND ${CMAKE_COMMAND} -E env "CFD_VALIDATION_PYTHON=${PYTHON}"
            bash "${RACINE}/VALIDATION_PRODUCTION/RUN_VALIDATION.sh" --module "${MODELE_NOM}" ${_options}
    DEPENDS modele
    COMMENT "Les quatre tests (copie de production), puis VALIDATION_PRODUCTION/SORTIE/RECAP.txt"
    USES_TERMINAL VERBATIM)

# Un test seul : cible, répertoire, script, options propres.
# ctest construit d'abord le module (test « modele », fixture des autres).
enable_testing()
add_test(NAME modele COMMAND ${CMAKE_COMMAND} --build "${CMAKE_BINARY_DIR}" --target modele)
set_tests_properties(modele PROPERTIES FIXTURES_SETUP module)
function(test_validation cible repertoire script)
    set(commande "${PYTHON}" "${DOSSIER_VALIDATION}/${repertoire}/${script}"
        --module "${MODELE_NOM}" --sortie "${SORTIE}/${repertoire}" ${ARGN} ${_options})
    add_custom_target(${cible}
        COMMAND ${commande}
        DEPENDS modele
        COMMENT "${repertoire} -> VALIDATION/SORTIE/${repertoire}/"
        USES_TERMINAL VERBATIM)
    # ctest : code 0 = conforme ; 2 = non conforme, donc échec du test
    add_test(NAME ${repertoire} COMMAND ${commande})
    set_tests_properties(${repertoire} PROPERTIES LABELS validation FIXTURES_REQUIRED module)
endfunction()
test_validation(lecture 01_LECTURE_TABLES 01_lecture_tables.py --combinaisons)
test_validation(bornes 02_BORNES_TABLES 02_bornes_tables.py)
test_validation(interpolation 03_INTERPOLATION_TABLES 03_interpolation_tables.py --jobs "${VALIDATION_JOBS}")
test_validation(integration 04_INTEGRATION 04_integration.py)

# -- tables du BLOCK DATA ------------------------------------------------------------
add_custom_target(verifier_tables
    COMMAND "${PYTHON}" "${RACINE}/OUTILS/generer_tables.py" --verifier
    COMMENT "SOURCES/aero_tables.f est-il à jour de OUTILS/generer_tables.py ?"
    USES_TERMINAL VERBATIM)
add_custom_target(tables
    COMMAND "${PYTHON}" "${RACINE}/OUTILS/generer_tables.py"
    COMMENT "Régénère SOURCES/aero_tables.f (le module sera reconstruit au prochain build)"
    USES_TERMINAL VERBATIM)
add_test(NAME tables_a_jour COMMAND "${PYTHON}" "${RACINE}/OUTILS/generer_tables.py" --verifier)

# -- nettoyer ----------------------------------------------------------------------
add_custom_target(nettoyer
    COMMAND ${CMAKE_COMMAND} -DRACINE=${RACINE} -DTOUT=OFF -P "${RACINE}/OUTILS/nettoyer.cmake"
    COMMENT "Efface les sorties : SORTIE/ et __pycache__/"
    VERBATIM)
add_custom_target(nettoyer_tout
    COMMAND ${CMAKE_COMMAND} -DRACINE=${RACINE} -DTOUT=ON -P "${RACINE}/OUTILS/nettoyer.cmake"
    COMMENT "Efface les sorties et les modules compilés (PYTHON/*.so)"
    VERBATIM)

# -- aide --------------------------------------------------------------------------
set(_aide
    "Cibles (cmake --build ${CMAKE_BINARY_DIR} -t <cible>) :"
    "  modele           construit PYTHON/${MODELE_NOM}${EXT_SUFFIX} et PYTHON/${MODELE_NOM}.compilation.log"
    "  exemple          lance PYTHON/exemple_appel.py"
    "  pdv              points de vol d'un YAML -> CSV (PDV_YAML, défaut PYTHON/exemple_pdv.yaml)"
    "  validation       les quatre tests puis VALIDATION/SORTIE/RECAP.txt"
    "  validation_production  idem avec VALIDATION_PRODUCTION/ (sans option --defaut)"
    "  lecture          test 1 seul : lecture des tables (--combinaisons)"
    "  bornes           test 2 seul : au-delà des bornes"
    "  interpolation    test 3 seul : entre les nœuds, et les polaires"
    "  integration      test 4 seul : REFERENCE/*.csv d'un autre environnement contre ce code"
    "  verifier_tables  SOURCES/aero_tables.f à jour ?"
    "  tables           régénère SOURCES/aero_tables.f"
    "  nettoyer         efface SORTIE/ et __pycache__/"
    "  nettoyer_tout    idem, et les modules PYTHON/*.so"
    "  clean            efface le module ${MODELE_NOM} et son journal"
    "ctest --test-dir ${CMAKE_BINARY_DIR} : construit, puis les quatre tests et le contrôle des tables"
    ""
    "Réglages (cmake -B ${CMAKE_BINARY_DIR} -D<NOM>=<valeur>) :"
    "  PYTHON=${PYTHON}"
    "  FC=${FC}  FFLAGS=${FFLAGS}  MODELE_NOM=${MODELE_NOM}"
    "  VALIDATION_JOBS=${VALIDATION_JOBS}  VALIDATION_OPTIONS=${VALIDATION_OPTIONS}"
    "  PDV_YAML=${PDV_YAML}")
set(_commandes)
foreach(ligne IN LISTS _aide)
    list(APPEND _commandes COMMAND ${CMAKE_COMMAND} -E echo "${ligne}")
endforeach()
add_custom_target(aide ${_commandes} VERBATIM)
