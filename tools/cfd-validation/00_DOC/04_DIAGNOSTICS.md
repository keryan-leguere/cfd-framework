# 4. Les motifs de panne

Un rapport qui dit « 347 points sur 2 100 sont hors tolérance » a fait la moitié
du travail. L'autre moitié est de dire **pourquoi**.

Les façons dont un code se trompe en lisant une table sont en petit nombre, et
chacune laisse une signature nette dans les écarts. Le paquet en reconnaît huit.

## Le tableau

| motif | signature | correctif |
|:--|:--|:--|
| `queue_non_renseignee` | les fautifs sont exactement la fin du tableau | déclarer `lignes` |
| `ecretage` | décalage confiné aux bornes d'un axe | une borne d'indice à reprendre |
| `axes_transposes` | la valeur rendue est celle du nœud aux deux axes échangés | l'ordre des arguments d'indexation |
| `axe_ignore` | la valeur ne bouge pas quand un axe seul bouge | un axe absent de l'indexation |
| `decalage_indice` | la valeur rendue est celle du nœud voisin | base 0/1, ou un `+1` de trop |
| `facteur_echelle` | `obtenu ≈ k·référence` | une unité, un signe, un demi |
| `decalage_constant` | `obtenu ≈ référence + c` | un offset sur le tableau de valeurs |
| `diffus` | aucun motif | à regarder à la main |

## Comment ils sont classés

**Tous les motifs qui se déclenchent sont rapportés**, classés par la **part des
points fautifs qu'ils expliquent**.

Un « premier trouvé » masquerait un défaut composite, et un facteur d'unité
*plus* un décalage d'indice arrivent très bien ensemble — n'avoir que le premier
coûte une deuxième campagne.

À part égale, le plus **spécifique** passe devant. C'est le cas d'`ecretage`
contre `decalage_indice` : le second englobe le premier, mais le correctif n'est
pas le même — une borne à reprendre plutôt qu'une base d'indexation.

Un motif qui explique moins d'un quart des points fautifs n'est pas rapporté :
il ferait du bruit sans orienter. `diffus` fait exception — il n'explique rien
par construction, et c'est pour cela qu'il sort toujours en dernier.

## Comment ils sont détectés

Cinq des huit détecteurs sont **constructifs** : ils vont chercher, dans la
table elle-même, la valeur que le modèle *aurait* rendue sous l'hypothèse, et
regardent si c'est bien celle-là.

Pour `axes_transposes`, par exemple : on prend les coordonnées du point fautif,
on échange deux d'entre elles, on cherche ce nœud-là dans la table, et on compare
sa valeur tabulée à ce que le modèle a rendu. Pas de seuil à régler, et aucune
autre panne ne produit cette coïncidence par hasard.

C'est pourquoi la déclaration des colonnes compte : deux axes ne peuvent être
reconnus comme transposés que s'ils partagent leur jeu de valeurs. Une incidence
et un braquage, tous deux en degrés sur la même plage, le partagent — et c'est
justement là que la confusion arrive en vrai.

Les trois autres — `facteur_echelle`, `decalage_constant`, `queue_non_renseignee`
— sont statistiques ou structurels, et rapportent le chiffre qui les étaye : le
facteur, le décalage, la première ligne fautive.

## Les conversions nommées

`facteur_echelle` ne se contente pas de donner `k` : quand `k` ressemble à une
conversion connue, il la nomme.

| `k` | ce que ça veut dire |
|:--|:--|
| −1 | signe inversé |
| π/180 | des degrés lus comme des radians |
| 180/π | des radians lus comme des degrés |
| 0.01 / 100 | pourcentage contre fraction |
| 0.5 / 2 | un facteur 2 — pression dynamique ? |
| 9.80665 | des kgf lus comme des newtons |
| 4.448 | des lbf lus comme des newtons |
| 0.3048 | des pieds lus comme des mètres |
| 0.4536 | des livres lues comme des kilogrammes |

## Les éprouver soi-même

Le paquet livre un générateur de pannes. Chaque motif a un cas de référence,
reproductible en trois lignes :

```python
from cfd_validation import valider_tables
from cfd_validation.wrap.factice import BUGS, ModeleFactice, TABLES, module_factice

module = module_factice()
for panne, motif_attendu in BUGS.items():
    rapport = valider_tables(module, TABLES, modele=ModeleFactice(module, bug=panne))
    trouve = rapport["CN"].grandeur("CN").motif_principal
    print(f"{panne:12} → {trouve.nom}")
```

`01_EXEMPLE/03_diagnostics.py` est la version complète, tableau récapitulatif
compris. Et `01_EXEMPLE/05_fortran_reel.py` rejoue trois de ces pannes dans du
**Fortran réellement compilé**, pas dans une simulation Python.

## En ajouter un

Un détecteur est une fonction `Contexte -> Motif | None` :

```python
def mon_motif(contexte: Contexte) -> Motif | None:
    fautifs = contexte.fautifs
    if fautifs.size == 0:
        return None
    hypothese = ...  # ce que le modèle aurait rendu
    explique = contexte.tolere(hypothese, contexte.ecart.obtenu)
    part = float(explique[fautifs].sum()) / fautifs.size
    if part < PART_MINIMALE:
        return None
    return Motif(nom="mon_motif", part_expliquee=part, message="…", preuve={})
```

Deux règles :

* **`contexte.tolere` et rien d'autre** pour juger d'une concordance. C'est le
  critère du contrôle lui-même : un détecteur avec son propre seuil expliquerait
  des points que le contrôle n'a pas jugés fautifs.
* **Ne reconnaissez pas une colonne à son nom.** `contexte.noms` sert à écrire
  le message, jamais à décider. Un détecteur qui saurait ce qu'est un « mach »
  ne marcherait que sur vos tables — et `tests/test_genericite.py` le refuse.

Ajoutez ensuite le nom à `ORDRE_SPECIFICITE` et la fonction à `DETECTEURS`, dans
`core/motifs.py`. Un test vérifie que les deux listes coïncident.
