#!/usr/bin/env python3
"""Construit le document Word de transmission de connaissance.

    python construire_docx.py

Enchaîne pandoc (Markdown → .docx) puis une passe de mise en page que pandoc
ne sait pas faire seul : format A4, marges de 2 cm, pied de page numéroté, et
élargissement des images et des tableaux à la largeur utile réelle de la page
(pandoc les dimensionne d'après son document de référence, au format US).

Prérequis : ``pandoc`` et ``python-docx``. Les figures doivent exister dans
``FIGURES/`` — ``tools/cfd-perf/00_DOC/generer_figures.py`` produit 01 à 05
(à recopier ici), ``generer_schemas.py`` produit 06 à 09.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ICI = Path(__file__).resolve().parent
SOURCE = ICI / "TRANSMISSION_CONNAISSANCE.md"
DOCX = ICI / "TRANSMISSION_CONNAISSANCE.docx"

LARGEUR_UTILE_CM = 16.6

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

PIED_DE_PAGE = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="{W}" xmlns:r="{R}">
  <w:p>
    <w:pPr><w:jc w:val="center"/></w:pPr>
    <w:r><w:rPr><w:sz w:val="18"/><w:color w:val="808080"/></w:rPr>
      <w:t xml:space="preserve">cfd-perf — transmission de connaissance   |   </w:t></w:r>
    <w:r><w:rPr><w:sz w:val="18"/><w:color w:val="808080"/></w:rPr>
      <w:fldChar w:fldCharType="begin"/></w:r>
    <w:r><w:rPr><w:sz w:val="18"/><w:color w:val="808080"/></w:rPr>
      <w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>
    <w:r><w:rPr><w:sz w:val="18"/><w:color w:val="808080"/></w:rPr>
      <w:fldChar w:fldCharType="separate"/></w:r>
    <w:r><w:rPr><w:sz w:val="18"/><w:color w:val="808080"/></w:rPr><w:t>1</w:t></w:r>
    <w:r><w:rPr><w:sz w:val="18"/><w:color w:val="808080"/></w:rPr>
      <w:fldChar w:fldCharType="end"/></w:r>
  </w:p>
</w:ftr>
"""

SECTION = (
    "<w:sectPr>"
    '<w:footerReference w:type="default" r:id="rIdFooterCfdPerf"/>'
    '<w:pgSz w:w="11906" w:h="16838"/>'
    '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"'
    ' w:header="709" w:footer="709" w:gutter="0"/>'
    "</w:sectPr>"
)


def convertir() -> None:
    """Markdown → .docx, table des matières comprise."""
    subprocess.run(
        ["pandoc", str(SOURCE), "-o", str(DOCX), "--toc", "--toc-depth=2",
         "--highlight-style=tango", f"--resource-path={ICI}"],
        check=True,
    )


def mettre_en_page() -> None:
    """Format A4, marges de 2 cm, pied de page numéroté."""
    brut = DOCX.with_suffix(".brut.docx")
    shutil.copy(DOCX, brut)
    with zipfile.ZipFile(brut) as zin:
        elements = {nom: zin.read(nom) for nom in zin.namelist()}
    brut.unlink()

    doc = elements["word/document.xml"].decode()
    if doc.count("<w:sectPr") != 1:
        raise SystemExit("propriétés de section inattendues dans la sortie pandoc")
    elements["word/document.xml"] = doc.replace("<w:sectPr />", SECTION).encode()

    rels = elements["word/_rels/document.xml.rels"].decode()
    elements["word/_rels/document.xml.rels"] = rels.replace(
        "</Relationships>",
        f'<Relationship Id="rIdFooterCfdPerf" Type="{R}/footer"'
        ' Target="footer1.xml"/></Relationships>',
    ).encode()

    types = elements["[Content_Types].xml"].decode()
    elements["[Content_Types].xml"] = types.replace(
        "</Types>",
        '<Override PartName="/word/footer1.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/></Types>',
    ).encode()
    elements["word/footer1.xml"] = PIED_DE_PAGE.encode()

    with zipfile.ZipFile(DOCX, "w", zipfile.ZIP_DEFLATED) as zout:
        for nom, donnees in elements.items():
            zout.writestr(nom, donnees)


def elargir() -> None:
    """Étire images et tableaux à la largeur utile de la page A4."""
    from docx import Document
    from docx.shared import Cm

    doc = Document(str(DOCX))
    cible = Cm(LARGEUR_UTILE_CM)

    for forme in doc.inline_shapes:
        ratio = forme.height / forme.width
        forme.width = cible
        forme.height = int(cible * ratio)

    for tableau in doc.tables:
        largeurs = [colonne.width for colonne in tableau.columns]
        facteur = cible / sum(largeurs)
        tableau.autofit = False
        for colonne, largeur in zip(tableau.columns, largeurs, strict=True):
            nouvelle = int(largeur * facteur)
            colonne.width = nouvelle
            for cellule in colonne.cells:
                cellule.width = nouvelle

    doc.save(str(DOCX))


def main() -> int:
    if not SOURCE.is_file():
        raise SystemExit(f"source introuvable : {SOURCE}")
    convertir()
    mettre_en_page()
    elargir()
    print(f"{DOCX.name} : A4, marges 2 cm, pied de page numéroté, contenu élargi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
