# Après `pip install` : lanceurs et complétion

`pip` grave dans chaque commande (`~/.local/bin/cfd-trajcast`…) le chemin absolu de
l'interpréteur qui l'a installée. Il n'offre aucun moyen d'en choisir un autre. Ce
script réécrit les lanceurs de **tous** les paquets de `tools/` en
`#!/usr/bin/env python3` et installe la complétion bash de leurs commandes.

```bash
python3 tools/installation/installer_lanceurs.py            # après chaque pip install
python3 tools/installation/installer_lanceurs.py --a-blanc  # dire sans rien écrire
source ~/.bashrc                                            # ou ouvrir un terminal
cfd-trajcast <TAB><TAB>
```

- Lancez-le avec **le même `python3`** que celui qui a servi à `pip install`. Il ne
  traite que les paquets installés dans cet interpréteur.
- **À relancer après chaque installation ou mise à jour.** pip réécrit ses lanceurs à
  chaque fois, et la complétion est figée au moment de sa génération.
- Un lanceur n'est réécrit que si le `python3` du `PATH` importe **maintenant** le
  paquet. Sinon la commande cesserait de marcher (venv non activé, autre Python en
  tête du PATH) : le script le dit et n'y touche pas. `--forcer` passe outre.
- Les scripts qui ne viennent pas de pip, comme le lanceur bash de `cfd-perf shim`,
  ne sont jamais modifiés.
- La complétion est **statique** : sous-commandes, options, valeurs permises
  (`choices`), et des noms de fichiers ailleurs (sauf pour les options numériques).
  Elle est écrite dans `~/.local/share/cfd-framework/completion.bash`, et une ligne
  balisée est ajoutée une seule fois à `~/.bashrc` (`--sans-bashrc` pour l'ajouter
  vous-même). Elle ne dépend pas du paquet `bash-completion`.
- Bibliothèque standard seulement, Python ≥ 3.9. Tests : `pytest tools/installation`.
