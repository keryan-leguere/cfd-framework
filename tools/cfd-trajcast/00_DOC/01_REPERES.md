# Repères, unités, attitude

Tout ce qui entre dans `cfd-trajcast` est ramené, **dès la lecture**, à une seule
convention. Le reste du code n'en voit jamais d'autre.

| Grandeur | Convention interne |
|---|---|
| Référence | ENU local : x Est, y Nord, z Haut ; origine à la rampe |
| Corps | FRD : x vers le nez, y à droite, z vers le bas |
| Attitude | quaternion de Hamilton `(w, x, y, z)`, rotation **active** corps → ENU : `v_ENU = q ⊗ v_corps ⊗ q*` |
| Unités | mètres, secondes, radians |

## 1. Ce qu'il faut déclarer

Rien n'est deviné. Quand une valeur par défaut s'applique, `cfd-trajcast check`
l'affiche dans le rapport.

```yaml
trajectoire:
  fichier: vol.csv
  repere: NED                    # obligatoire : ENU ou NED
  unites: { temps: s, longueur: m, angle: deg }   # défauts : s, m, deg
  colonnes: { t: t, x: n, y: e, z: d }            # en NED : x, y, z = Nord, Est, Bas
  attitude:                      # obligatoire
    type: quaternion             # quaternion | euler
    colonnes: [q0, q1, q2, q3]   # sinon : q0..q3, qw..qz ou e0..e3 s'ils existent
    ordre: wxyz                  # wxyz (défaut) | xyzw
    sens: corps_vers_reference   # (défaut) | reference_vers_corps
    corps: FRD                   # FRD (défaut) | FLU
```

En angles d'Euler :

```yaml
  attitude:
    type: euler
    sequence: ZYX                # majuscules = intrinsèque, minuscules = extrinsèque
    colonnes: [lacet, tangage, roulis]   # dans l'ordre de la séquence
```

Les événements peuvent aussi venir d'un fichier exporté par la simulation :
`evenements: mon_vol_evenements.csv` (colonnes `t,nom`, lignes `#` ignorées).

**Sans attitude, la lecture échoue** (`ErreurAttitude`). Elle n'est jamais déduite
de la vitesse : une fusée qui roule, qui part en incidence ou qui oscille sous
parachute serait montrée fausse sans que rien ne le signale.

### Unités acceptées

| Clé | Valeurs |
|---|---|
| `temps` | `s`, `ms`, `min` |
| `longueur` | `m`, `km`, `mm`, `ft` |
| `angle` | `deg`, `rad` |

## 2. Le référentiel : ENU ou NED

```
p_ENU = M · p_NED,   M = | 0 1  0 |
                         | 1 0  0 |
                         | 0 0 -1 |
```

`M` est une rotation propre (déterminant +1) : un demi-tour autour de l'axe
(1, 1, 0)/√2. L'attitude suit : `q_corps→ENU = q_NED→ENU ⊗ q_corps→NED`.

## 3. Le repère corps : FRD ou FLU

FLU (x avant, y gauche, z haut) est FRD retourné d'un demi-tour autour de x :
`q_FRD→réf = q_FLU→réf ⊗ (0, 1, 0, 0)`. L'axe du nez ne change pas ; seuls y et z
changent de signe, ce qui se voit au roulis.

## 4. Angles d'Euler

Les douze séquences sont acceptées (Tait-Bryan comme `ZYX`, Euler propres comme
`ZXZ`). Angles nuls : le repère corps coïncide avec le repère de référence.

* **Intrinsèque** (`ZYX`) : on tourne de ψ autour de z, puis de θ autour du *nouvel* y,
  puis de φ autour du *nouvel* x — `q = q_z(ψ) ⊗ q_y(θ) ⊗ q_x(φ)`. C'est la séquence
  lacet-tangage-roulis de la mécanique du vol, relative au NED, corps FRD.
* **Extrinsèque** (`xyz`) : axes fixes ; `xyz` d'angles (φ, θ, ψ) est la même rotation
  que `ZYX` d'angles (ψ, θ, φ).

Le passage quaternion → Euler (`core/rotations.vers_euler`) suit la méthode directe
de Bernardes & Viollet (2022), celle de SciPy. Près du **blocage de cardan**
(tangage ±90° pour `ZYX`), la lecture lève une alerte : seule la somme ou la
différence de deux angles y est définie. L'interpolation se fait toujours en
quaternions, donc la vidéo reste juste ; c'est la donnée d'entrée qui est mal
conditionnée.

## 5. La maquette

```yaml
maquette:
  fichier: Aim9.stp
  unite: mm                      # obligatoire pour STL/OBJ/PLY/GLB ; contrôle pour un STEP
  axe_nez: "-X"                  # axe CAO qui pointe vers le nez → x corps
  axe_haut: "+Z"                 # axe CAO vers le haut à roulis nul → −z corps
  origine: [19.05, 0, 0]         # base | centre_volume | [x, y, z] en unité du fichier
  longueur_imposee: 2.87         # m : mise à l'échelle ; ou longueur_attendue : contrôle
```

* **Unités** : un STEP déclare la sienne et OpenCASCADE le convertit en mètres ; si
  `unite` est donnée et la contredit, c'est une erreur. Un maillage n'en a pas.
* **Origine** : le point de la fusée dont la trajectoire donne la position — souvent le
  centre de gravité (RocketPy). La fusée tourne autour de lui. `base` = centre du culot ;
  `centre_volume` = centre de masse à densité uniforme (le CG réel en diffère : moteur,
  charge utile), au centre des surfaces si le maillage n'est pas fermé.
* **`longueur_attendue`** (contrôle à 5 %) nomme la confusion d'unités la plus probable
  (mm/m, pouces/mm…). **`longueur_imposee`** met à l'échelle une maquette réduite ;
  les deux s'excluent.

## 6. Ce que `check` contrôle

Par défaut, **seuls des contrôles valables pour toute trajectoire** : `check` ne
suppose ni montée, ni apogée, ni sol. Un vol plané, une descente sous parachute ou
un tronçon de vol sont des trajectoires légitimes.

| Contrôle | Niveau | Ce qu'il attrape |
|---|---|---|
| temps strictement croissant, valeurs finies | erreur de lecture | lignes dupliquées, trous |
| `‖q‖ − 1` | < 1e-6 rien ; < 1e-2 renormalisé + alerte ; au-delà erreur | colonnes ou ordre faux, précision d'écriture |
| continuité q / −q | info | sauts de signe (sinon l'interpolation prend le grand arc) |
| blocage de cardan | alerte | angles d'Euler mal conditionnés |
| étendue > 2 000 km, Mach > 30 | alerte | unités de longueur ou de temps |
| longueur de la CAO, axe du nez = plus grande dimension | erreur / alerte | unité de la CAO, `axe_nez` |

### Option `--coherence` : nez contre vitesse pendant la montée

`cfd-trajcast check --coherence CONFIG.yaml` (ou `verifier(..., coherence=True)`)
ajoute un contrôle **à ne demander que si la trajectoire contient une montée**.
Une convention fausse ne fait rien planter, elle produit une vidéo fausse ; or
pendant une montée, une fusée stable vole nez au vent. Sur les échantillons de
montée (avant le point le plus haut, vitesse verticale positive, vitesse > 20 % du
maximum), un **angle médian nez/vitesse au-delà de 20°** déclenche une alerte. La
conversion est alors rejouée sous les autres conventions — repère ENU/NED, ordre
`wxyz`/`xyzw`, sens, séquence intrinsèque ou extrinsèque — et celles qui rendraient
le vol cohérent sont nommées :

```
alerte  pendant la montée, l'axe du nez fait 120° (médiane) avec la vitesse :
        convention d'attitude probablement fausse
        convention(s) qui rendraient le vol cohérent : sens corps vers reference → 0.0°
```

C'est un **diagnostic** : rien n'est corrigé, l'attitude n'est jamais remplacée par
la vitesse, et une fusée réellement en forte incidence le déclencherait à tort.

## 7. Le vol de référence

`core/vol_reference.py` donne un vol **analytique** : 4 s de poussée à 100 m/s²
(trajectoire rectiligne, puisque l'accélération totale est constante), puis
balistique ; nez dans la vitesse, roulis de 90 °/s, cap 30°. Mach 1 à 3,744 s,
apogée à 40,565 s et 7 273 m. L'exemple l'écrit deux fois — ENU + quaternion,
NED + Euler ZYX — et les tests vérifient que toutes les lectures retombent sur les
valeurs exactes (écart d'attitude < 1e-7°).
