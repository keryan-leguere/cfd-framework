# cfd-atm

Un **modèle d'atmosphère** solver-agnostic, pensé comme un bloc de schéma-bloc.

**Entrée** : une altitude (géométrique, géopotentielle ou altitude-pression) + un modèle de
température (`ISA`, `ISA±ΔT`, ou un profil `T°` custom).
**Sortie fonctionnelle** : les conditions de l'air (`p`, `T`, `ρ`) et les grandeurs dérivées
(vitesse du son, viscosité, ratios `θ/δ/σ`).
**Sortie monitorable** : toutes les altitudes équivalentes (`z`, `H`, `zp`, `zρ`) et, à partir
d'une information de vitesse, **toutes** les grandeurs de vitesse de la mécanique du vol —
Mach, `Vc` (CAS), `EAS`, `TAS` — en **subsonique et supersonique**.

## Installation

```bash
cd tools/cfd-atm
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
pip install -e ../cfd-plot   # facultatif : style maison des figures
```

## Utilisation

En ligne de commande :

```bash
# Un point : FL350, ISA+10, Vc = 280 kt
cfd-atm point --altitude 35000 --nature pression --unite-altitude ft \
  --modele ISA+X --dt 10 --vitesse 280 --grandeur cas --unite-vitesse kt

# Générer les diagrammes iso-Vc / iso-TAS
cfd-atm diagramme --sortie SORTIE --profil 01_EXEMPLE/profil_T_custom.yaml

# Copier l'exemple exécutable
cfd-atm example mon_exemple && cd mon_exemple && bash RUN_EXEMPLE.sh
```

En tant que fonction :

```python
from cfd_atm import AtmosphereModel, airspeeds

st = AtmosphereModel.isa_offset(10.0).state_from_pressure_altitude(10668.0)  # FL350, ISA+10
s = airspeeds(st.p, st.t, cas=280 * 0.514444)     # Vc = 280 kt
print(s.mach, s.tas, s.eas)
```

## Documentation

- [`00_DOC/01_MODELE_ATMOSPHERE.md`](00_DOC/01_MODELE_ATMOSPHERE.md) — le modèle, les altitudes,
  ISA / ISA±ΔT / profil custom, l'intégration hydrostatique, les grandeurs dérivées.
- [`00_DOC/02_GRANDEURS_VITESSE.md`](00_DOC/02_GRANDEURS_VITESSE.md) — la reconstruction des
  vitesses (qc, subso + superso Rayleigh) et la subtilité iso-Vc / iso-TAS.

## Structure

`src/cfd_atm/core/` (physique : `constants`, `isa`, `altitudes`, `thermo`, `airspeed`,
`atmosphere`), `src/cfd_atm/report/` (unités, rapport Rich, figures), `src/cfd_atm/cli/`.
Tests sous `tests/`. Exemple exécutable sous `01_EXEMPLE/`.
