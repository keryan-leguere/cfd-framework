"""Le modèle enveloppé, sous la forme où un module f2py se présente.

Un module compilé par f2py expose ses COMMON blocks comme de simples attributs
de module : ``aero.tab_cn.tab_cn`` est le tableau du bloc ``TAB_CN``. Ce module
Python fait exactement la même chose, sans compilateur — c'est ce qui permet de
dérouler tout l'exemple partout.

Pour le jumeau réellement compilé, voir ``MODELE_FORTRAN/aero.f`` et le script
``05_fortran_reel.py``.
"""

from __future__ import annotations

from cfd_validation.wrap.factice import module_factice

_module = module_factice()

#: Le COMMON block ``TAB_CN`` : le tableau et son compteur de lignes.
tab_cn = _module.tab_cn

#: Le COMMON block ``TAB_CA``.
tab_ca = _module.tab_ca
