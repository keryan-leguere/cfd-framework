"""Compatibilité Python 3.9 : ce qui casserait silencieusement selon la version.

Les énumérations texte du paquet finissent dans des messages d'erreur et dans
le YAML généré par ``cfd-perf capture``. Le formatage des énumérations mixtes a
changé en Python 3.11 ; ces tests figent le résultat attendu, identique de 3.9
à aujourd'hui.
"""

from __future__ import annotations

import yaml

from cfd_perf._compat import StrEnum
from cfd_perf.core.model import ModelKind
from cfd_perf.engine.recommend import Strategy


class TestStrEnum:
    def test_les_membres_sont_leur_valeur(self):
        assert Strategy.FASTEST == "fastest"
        assert ModelKind.AMDAHL == "amdahl"

    def test_str_donne_la_valeur(self):
        assert str(Strategy.EFFICIENCY) == "efficiency"
        assert str(ModelKind.AMDAHL_COMM) == "amdahl+comm"

    def test_le_formatage_donne_la_valeur(self):
        assert f"{Strategy.DEADLINE}" == "deadline"
        assert f"{ModelKind.AMDAHL_COMM}" == "amdahl+comm"
        assert f"{Strategy.FASTEST:>10}" == "   fastest"

    def test_construction_depuis_la_valeur(self):
        assert Strategy("deadline") is Strategy.DEADLINE
        assert ModelKind("amdahl+comm") is ModelKind.AMDAHL_COMM

    def test_serialisable_en_yaml_par_sa_valeur(self):
        assert yaml.safe_dump({"strategy": Strategy.FASTEST.value}).strip() == (
            "strategy: fastest"
        )

    def test_sous_classe_libre(self):
        class Couleur(StrEnum):
            ROUGE = "rouge"

        assert f"{Couleur.ROUGE}" == "rouge"
        assert Couleur.ROUGE.upper() == "ROUGE"
