# Transmission de connaissance — cfd-perf

Document Word de transmission (support de passation, hors paquet). Il vivait
auparavant dans `tools/cfd-perf/00_DOC/07_TRANSMISSION/` ; il a été sorti du
paquet pour que `cfd-perf` reste un paquet Python autonome et publiable.

| Fichier | Rôle |
|:---|:---|
| `TRANSMISSION_CONNAISSANCE.md` | la source, en Markdown |
| `TRANSMISSION_CONNAISSANCE.docx` | le livrable Word (A4, marges 2 cm, pied de page numéroté) |
| `generer_schemas.py` | produit les figures 06 à 09 dans `FIGURES/` |
| `construire_docx.py` | pandoc + mise en page → `.docx` |
| `FIGURES/` | 01 à 05 recopiées de la doc du paquet, 06 à 09 propres au document |

## Reconstruire

```bash
python generer_schemas.py                    # figures 06 à 09
cp ../../tools/cfd-perf/00_DOC/FIGURES/0[1-5]_*.png FIGURES/   # figures communes
python construire_docx.py                    # → TRANSMISSION_CONNAISSANCE.docx
```

Prérequis : `pandoc`, `python-docx`, `matplotlib`.
