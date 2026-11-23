# Efface les sorties du projet : cmake -DRACINE=<MODELE_AERO> [-DTOUT=ON] -P nettoyer.cmake
#
# Sorties : tout dossier nommé SORTIE/ ou __pycache__/ sous RACINE.
# TOUT=ON : aussi les modules compilés PYTHON/*.so et leurs journaux *.compilation.log.
# Rien d'autre n'est touché : ni les sources, ni le dossier de construction CMake.
cmake_minimum_required(VERSION 3.17)

if(NOT RACINE OR NOT EXISTS "${RACINE}/SOURCES" OR NOT EXISTS "${RACINE}/PYTHON/construire.sh")
    message(FATAL_ERROR "RACINE=${RACINE} n'est pas un projet MODELE_AERO (SOURCES/, PYTHON/construire.sh)")
endif()

file(GLOB_RECURSE _tout LIST_DIRECTORIES true "${RACINE}/*")
set(_effaces)
foreach(chemin IN LISTS _tout)
    get_filename_component(nom "${chemin}" NAME)
    if(IS_DIRECTORY "${chemin}" AND (nom STREQUAL "SORTIE" OR nom STREQUAL "__pycache__"))
        list(APPEND _effaces "${chemin}")
    endif()
endforeach()
if(TOUT)
    file(GLOB _modules "${RACINE}/PYTHON/*.so" "${RACINE}/PYTHON/*.pyd" "${RACINE}/PYTHON/*.compilation.log")
    list(APPEND _effaces ${_modules})
endif()

if(NOT _effaces)
    message(STATUS "Rien à effacer.")
    return()
endif()
foreach(chemin IN LISTS _effaces)
    if(EXISTS "${chemin}")  # un dossier déjà parti avec son parent
        file(RELATIVE_PATH rel "${RACINE}" "${chemin}")
        message(STATUS "efface ${rel}")
        file(REMOVE_RECURSE "${chemin}")
    endif()
endforeach()
