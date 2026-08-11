# 3. Régimes de fonctionnement et performances

## Le paramètre unique : le NPR

Une tuyère de rapport de section ε fixé n'a **qu'un seul** point de conception
supersonique. Ce qui décide de son comportement réel, c'est le rapport de
pressions

```
NPR = p0 / pa            (Nozzle Pressure Ratio)
```

Trois NPR critiques découpent l'axe en cinq régimes. `Nozzle.critical_ratios()`
les calcule :

| Seuil | Définition | Formule |
|---|---|---|
| **NPR₁** | amorçage : le col atteint tout juste M = 1, la sortie reste subsonique | `p0/p(Me_sub)` avec A/A*(Me_sub) = ε, branche subsonique |
| **NPR₂** | un choc droit se tient exactement dans le plan de sortie | `NPR₃ / (p₂/p₁)(Me_sup)` |
| **NPR₃** | adaptation : détente supersonique complète, pe = pa | `p0/p(Me_sup)` — **le point de conception** |

![Les cinq régimes d'une tuyère de Laval](FIGURES/03_regimes_tuyere.png)

## Les cinq régimes

| NPR | Régime | Ce qui se passe |
|---|---|---|
| < NPR₁ | **Venturi** (non amorcée) | Le col n'est pas sonique, le divergent agit en diffuseur. Aucune poussée utile. |
| NPR₁ … NPR₂ | **Choc droit interne** | Le col est amorcé, mais un choc droit se tient dans le divergent et la sortie est subsonique à pa. Le choc recule vers la sortie quand le NPR monte. |
| NPR₂ … NPR₃ | **Sur-détendue** | Détente supersonique complète, mais pe < pa : la recompression se fait par des chocs obliques **à l'extérieur**. La tuyère est trop longue pour cette altitude. |
| = NPR₃ | **Adaptée** | pe = pa. Poussée optimale pour ce ε. |
| > NPR₃ | **Sous-détendue** | pe > pa : la détente se poursuit dehors en faisceau de Prandtl-Meyer. Un divergent plus long gagnerait de la poussée. |

Point clé, et source d'erreur classique : **dès que le col est amorcé et que
l'écoulement est supersonique en sortie, la pression aval n'a plus aucune
influence sur l'intérieur de la tuyère**. Me et pe sont fixés par ε seul. Seul
le terme de pression de la poussée change avec pa.

### Position du choc interne

Le choc se place là où la recompression subsonique aval débouche exactement à
pa. En aval du choc la section sonique de référence vaut A2* = At/(p02/p01),
donc la sortie voit un rapport de section effectif ε·(p02/p01) :

```
trouver M_choc tel que   p0 · (p02/p01) / (p0/p)(Me)  =  pa
avec  Me = A/A*⁻¹( ε·(p02/p01), branche subsonique )
```

`Nozzle.shock_in_divergent()` résout ça par dichotomie et renvoie
`(M_choc, A_choc/A_col)`.

## Performances : la décomposition de Sutton

Trois grandeurs indépendantes, et deux rendements qui n'agissent pas au même
endroit. C'est la convention de Sutton (*Rocket Propulsion Elements*), choisie
ici parce qu'elle est la seule qui reste **cohérente avec elle-même** :

```
c*   = η_c* · √(R·T0) / Γ(γ)              vitesse caractéristique [m/s]
ṁ    = p0 · At / c*                       ⟹  ṁ · c* = p0·At  exactement
Cf   = λ · Cf_mom + (pe − pa)/p0 · ε      coefficient de poussée [-]
F    = Cf · p0 · At                       poussée [N]
Isp  = F / (ṁ·g₀) = Cf · c* / g₀          impulsion spécifique [s]
```

avec le terme de quantité de mouvement

```
Cf_mom = √( 2γ²/(γ−1) · (2/(γ+1))^((γ+1)/(γ−1)) · (1 − (pe/p0)^((γ−1)/γ)) )
```

Qui fait quoi :

- **c\* ne dépend que de la chambre** (gaz + T0) — c'est la mesure de la qualité
  de la combustion.
- **Cf ne dépend que de la détente** (ε, pe/p0, pa) — c'est la mesure de la
  qualité de la tuyère.
- **η_c\* < 1** (combustion imparfaite) fait *monter* le débit nécessaire pour
  tenir p0, et fait *baisser* l'Isp d'autant. La poussée, elle, ne bouge pas :
  elle passe par Cf.
- **λ < 1** (perte par divergence) ne dégrade que le terme de quantité de
  mouvement, pas le débit. Pour un cône de demi-angle α, λ = (1 + cos α)/2 ;
  `NozzleContour` le fournit.

> ⚠️ Le script d'origine appliquait η_c* **deux fois de façon contradictoire**
> (débit × η *et* c* × η), ce qui violait la définition même c* ≡ p0·At/ṁ d'un
> facteur η². La décomposition ci-dessus est testée comme invariant exact
> (`tests/core/test_nozzle.py::test_sutton_decomposition_is_self_consistent`).

Dans les régimes à **sortie subsonique** (venturi, choc interne), la corrélation
en Cf ne s'applique pas : la poussée est alors intégrée directement,
F = ṁ·Ve + (pe − pa)·Ae, et Cf en est déduit.

## Le compromis sur ε

`Nozzle.optimal_area_ratio(p0, pa)` donne le ε qui adapterait ce point. Comme pa
varie le long d'une trajectoire, **aucun ε fixe n'est optimal partout** :

```
ε   alt. adaptation    F(0 m)      F(vide)   Isp(vide)
 8              0 m   502.16 kN   527.63 kN     276.9 s
16          4 068 m   501.07 kN   552.00 kN     289.7 s
30          9 661 m   474.41 kN   569.90 kN     299.1 s
```

(`01_EXEMPLE/balayage_altitude.py`, moteur LOX/RP-1 de 200 mm au col.)
Passer de ε = 8 à ε = 30 gagne 22 s d'Isp sous vide, mais coûte 28 kN au niveau
de la mer — et fait entrer la tuyère en zone de décollement.

## La limite du modèle : le décollement

**Le modèle n'a pas de couche limite.** En sur-détente profonde, la réalité est
que la couche limite décolle dans le divergent bien avant que le modèle ne le
laisse deviner : la tuyère se « raccourcit » toute seule, avec des charges
latérales qui peuvent casser le moteur au démarrage.

Le critère de Summerfield — `pe/pa < 0.35` (`SEPARATION_RATIO`) — est le
garde-fou grossier retenu ici. Le rapport l'affiche en avertissement :

```
! pe/pa = 0.318 < 0.35 : risque sérieux de décollement dans le divergent
  (critère de Summerfield).
```

Quand cet avertissement apparaît, **les chiffres de poussée sont optimistes** et
il faut une simulation visqueuse.

## En pratique

```bash
cfd-nozzle tuyere --p0 100e5 --t0 3500 --pa 1.013e5 \
    --diametre-col 0.20 --eps 16 --gaz lox_rp1 --eta-cstar 0.96 --lambda-contour

cfd-nozzle run CAS.yaml --figure SORTIE
```

```python
from cfd_nozzle import GAS_LIBRARY, Nozzle

tuyere = Nozzle(0.0314, 16.0, GAS_LIBRARY["lox_rp1"], eta_cstar=0.96, lambda_div=0.985)
etat = tuyere.solve(p0=100e5, t0=3500.0, pa=1.013e5)
etat.regime.label, etat.thrust, etat.isp, etat.warnings
```

## Le champ le long de l'axe

`Nozzle.flow_field(x, area, p0, t0, pa)` distribue M, p, T, ρ et V le long du
contour, choc interne inclus. C'est la distribution purement gaz-dynamique :
η_c* et λ n'agissent que sur les performances intégrales, pas sur le champ
local. Le débit ρ·V·A y est conservé à 10⁻⁶ près (c'est un test).
