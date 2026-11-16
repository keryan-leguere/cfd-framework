# Propulsion, jets et scénarios

## 1. Section `propulsion`

Ce qui sort des tuyères, phase par phase. Une **phase** couvre un intervalle de
vol, borné par des instants (s) ou des **noms d'événements**, et porte un **jet** :
une flamme, une fumée, les deux ou rien.

```yaml
propulsion:
  tuyeres: [[-8.0, 0.5, 0.0], [-8.0, -0.5, 0.0]]   # FRD (m) depuis le point de référence ;
                                                   # absent : une tuyère au centre du culot
  rayon_tuyere: 0.38                               # m ; absent : 4 % de la taille de la maquette
  fondu: 0.3                                       # s de vol : fondu enchaîné entre phases
  phases:
    - { de: "Mise en puissance", a: "Palier", jet: postcombustion }
    - { de: "Palier", a: "Boucle", jet: reacteur }
    - { de: "Boucle", a: 142.0, jet: { base: postcombustion, flamme: { longueur: 12 } } }
    - { de: "Panne moteur", jet: panne }             # sans `a` : jusqu'à la fin du vol
```

`jet` est un préréglage, ou un dict `{base: <préréglage>, flamme: {...}|false,
fumee: {...}|false}` qui surcharge les clés données (`false` supprime la partie).

### Préréglages

| Jet | Flamme | Fumée |
|---|---|---|
| `fusee_poudre` | longue (20 r), très évasée (16°), blanc → jaune → orange → rouge | épaisse, blanc chaud → gris, s'ouvre à 7°, turbulente |
| `fusee_liquide` | bleutée (blanc → bleu → orange au bout), 5 disques de Mach | légère, presque transparente |
| `postcombustion` | 9 r, bleu → orange, 5 disques de Mach | aucune |
| `reacteur` | courte, pâle (gaz chauds) | aucune |
| `panne` | courte, très ouverte (25°), orange, vacillante (scintillement 0,35) | noire → grise, épaisse, très turbulente, 12 s |
| `fumee` | aucune | fumée par défaut |
| `aucun` | — | — |

### Flamme

```yaml
flamme:
  longueur: 20        # en rayons de tuyère
  evasement: 16       # demi-angle d'ouverture (°)
  couleurs: ["#fff8e0", "#ffc04d", "#ff6a1a", "#b8301a"]   # de la tuyère au bout (2 à 6)
  opacite: 0.9
  coeur: 0.45         # longueur relative du cœur blanc (0 : pas de cœur)
  diamants: 0         # disques de Mach (0 à 12)
  scintillement: 0.1  # variation relative de longueur, bruit déterministe
```

Surface de révolution autour de l'axe de la tuyère (−x corps) : rayon
`(r₀ + s·tan θ)·√(1 − u³)` — elle s'évase puis se referme en douceur — couleur
interpolée le long de `couleurs`, opacité décroissante vers le bout. Un cœur blanc
plus court et plus étroit, et des disques de Mach en ellipsoïdes brillants. Elle
est dessinée **sans éclairage** (elle émet), attachée au corps : elle suit
l'attitude et scintille.

### Fumée

```yaml
fumee:
  couleur_debut: "#fff1d6"   # à l'émission
  couleur_fin: "#b4b8bd"     # à la fin de sa durée de vie
  opacite: 0.85
  duree: 8.0                 # s : âge où elle a disparu
  rayon: 1.5                 # rayon initial, en rayons de tuyère
  evasement: 7.0             # ° : ouverture en cône le long de la fumée
  expansion: 2.0             # m/s d'âge : élargissement dans l'air
  turbulence: 0.8            # m/s d'âge : dérive latérale (bruit lisse)
```

La fumée est figée dans l'air (repère terrestre), émise par chaque tuyère. Son
rayon vaut `r₀·rayon + d·tan(evasement) + expansion·âge`, `d` étant la distance
derrière la tuyère : le panache **s'ouvre** dans l'image même quand l'engin va
vite. Elle apparaît progressivement derrière la flamme au lieu de la recouvrir,
et elle est éclairée par le soleil (ombrée côté opposé). Chaque portion garde le
jet de la **phase de son émission** : la fumée blanche d'un étage 1 continue de
vieillir pendant que l'étage 2 émet la sienne, et la fumée noire d'une panne
reste noire.

L'ancienne écriture `style.trainee` (une fumée seule) reste acceptée quand il n'y a
pas de section `propulsion` ; elle n'est plus activée par le préréglage
`conference`, faute de connaître la fin de propulsion de votre vol.

## 2. Trajectoires synthétiques : `cfd_trajcast.core.manoeuvres`

Pour fabriquer un scénario sans code de mécanique du vol : un point matériel piloté
par segments de consignes.

```python
from cfd_trajcast.core.manoeuvres import Conditions, Mobile, Segment, simuler

sim = simuler(Conditions(position=(0, 0, 4000), vitesse=150, cap=0), [
    Segment(15, "Croisière", vitesse=150, pente=0, inclinaison=0),
    Segment(40, "Grand virage", pente=-7, inclinaison=45),
    Segment(90, "Spirale", facteur_charge=1.8, inclinaison=82),
], arret_sous=150)
sim.t, sim.positions, sim.attitudes, sim.donnees["n"], sim.evenements
```

Modèle (ENU) : `a = (T − k·V²)·x̂ + n·g₀·(−ẑ_w) + g`, avec `x̂` la direction de la
vitesse, `ẑ_w` le « bas » du repère aérodynamique incliné de `μ`. Consignes par
segment, chacune reprise du segment précédent si absente :

| Groupe | Consignes (l'une ou l'autre) |
|---|---|
| poussée | `vitesse` (asservie) · `poussee` (m/s², fixe) |
| plan vertical | `pente` (asservie, n en découle) · `facteur_charge` (fixe) |
| latéral | `cap` (asservi, l'inclinaison en découle) · `inclinaison` · `taux_roulis` (°/s imposé : tonneau, boucle sans roulis) |
| sol | `au_sol: true` (roulage) |

L'attitude est le repère aérodynamique cabré de l'incidence
`α = incidence_par_g × n` (0 pour `Mobile.fusee()`). Les commandes convergent
avec des constantes de temps : pas d'à-coup. Vérifié : virage coordonné
(n = 1/cos μ, taux g·tan μ / V), boucle fermée, fusée balistique d'incidence nulle.

**Ce n'est pas un simulateur de vol** : pas d'aérodynamique réelle, pas de
décrochage, pas de train d'atterrissage. C'est une cinématique cohérente pour des
vidéos et des tests.

## 3. Scénarios livrés : `01_EXEMPLE/SCENARIOS/`

Voir son `README.md`. Trois vols — avion qui manœuvre, avion en panne qui part en
spirale, fusée à deux étages — avec leurs événements (CSV `t,nom` lu directement par
`trajectoire.evenements`) et `RUN_SCENARIOS.sh`. La maquette est partout la CAO de
l'exemple (`MAQUETTE/Aim9.stl`), trajectoires d'avion comprises : la trajectoire et la
maquette sont indépendantes.

## 4. Généricité : ce qui ne suppose plus une fusée

* Aucun contrôle par défaut ne suppose de profil de vol (montée, apogée, sol).
* Les caméras cadrent la **taille** de la maquette, la plus grande de sa longueur et
  de son envergure.
* `style.sol.altitude` : cote du sol dans le repère de la trajectoire (une maquette
  dont l'axe roule à 0,4 m du sol, une trajectoire dont l'origine n'est pas au sol).
* Télémétrie : `facteur_de_charge` (force spécifique ressentie, 1 g en palier),
  `cap`, `pente`, `roulis`, `tangage`, `lacet` (Euler ZYX par rapport au NED).
* `sequence[].de` et les bornes de phases acceptent des noms d'événements.
* Vue d'ensemble : « maquette agrandie ».
