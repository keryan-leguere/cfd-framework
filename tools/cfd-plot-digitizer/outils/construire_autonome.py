#!/usr/bin/env python3
"""Assemble l'application en un seul fichier HTML autonome.

Sur une machine coupée du réseau, transporter un dossier de quinze fichiers est
une source d'erreurs : il suffit d'en oublier un pour que la page s'ouvre à
moitié. Ce script produit un `cfd-plot-digitizer.html` unique — CSS, scripts et
figure d'exemple compris — qu'on copie sur une clé et qu'on ouvre directement.

    python3 outils/construire_autonome.py [-s SORTIE]
    python3 outils/construire_autonome.py --verifier

Le fichier construit étant versionné, il peut se désynchroniser des sources
sans que rien ne le signale — et un fichier périmé livré sur une clé est pire
que pas de fichier du tout, puisqu'il a l'air de fonctionner. `--verifier`
reconstruit en mémoire et compare : à brancher dans un contrôle avant commit.

Bibliothèque standard uniquement. Aucune minification : le fichier reste
lisible et modifiable sur place, ce qui compte davantage que sa taille quand on
ne peut rien réinstaller.
"""
import argparse
import html.parser
import io
import pathlib
import sys

RACINE = pathlib.Path(__file__).resolve().parent.parent


class Collecteur(html.parser.HTMLParser):
    """Relève les <link rel=stylesheet> et <script src> locaux à remplacer."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.feuilles = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "link" and a.get("rel") == "stylesheet" and a.get("href"):
            if not a["href"].startswith(("http:", "https:", "//", "data:")):
                self.feuilles.append(a["href"])
        elif tag == "script" and a.get("src"):
            if not a["src"].startswith(("http:", "https:", "//", "data:")):
                self.scripts.append(a["src"])


def lire(chemin):
    with io.open(chemin, encoding="utf-8") as f:
        return f.read()


def proteger(source, quoi):
    """Refuse une source qui casserait le document une fois incorporée.

    Un `</script>` à l'intérieur d'un littéral JavaScript ferme la balise pour
    l'analyseur HTML, quel que soit le contexte JavaScript : le reste du fichier
    devient du texte. Même piège avec `</style>`. Mieux vaut s'arrêter avec un
    message clair que produire un fichier silencieusement cassé.
    """
    for motif in ("</script", "</style"):
        if motif in source.lower():
            raise SystemExit(
                "%s contient « %s », qui refermerait la balise une fois "
                "incorporé. Découper la chaîne (par exemple '<\\/script') "
                "avant de reconstruire." % (quoi, motif)
            )
    return source


def assembler():
    """Rend le document complet, sans rien écrire."""
    page = lire(RACINE / "index.html")

    collecteur = Collecteur()
    collecteur.feed(page)

    for href in collecteur.feuilles:
        chemin = RACINE / href
        if not chemin.exists():
            raise SystemExit("feuille de style introuvable : %s" % href)
        contenu = proteger(lire(chemin), href)
        balise = '<link rel="stylesheet" href="%s">' % href
        if balise not in page:
            raise SystemExit("balise <link> non retrouvée telle quelle : %s" % href)
        page = page.replace(
            balise, "<style>\n/* %s */\n%s\n</style>" % (href, contenu), 1)

    for src in collecteur.scripts:
        chemin = RACINE / src
        if not chemin.exists():
            raise SystemExit("script introuvable : %s" % src)
        contenu = proteger(lire(chemin), src)
        balise = '<script src="%s"></script>' % src
        if balise not in page:
            raise SystemExit("balise <script> non retrouvée telle quelle : %s" % src)
        page = page.replace(
            balise, "<script>\n/* %s */\n%s\n</script>" % (src, contenu), 1)

    entete = (
        "<!--\n"
        "  cfd-plot-digitizer — fichier unique et autonome.\n"
        "  Engendré par outils/construire_autonome.py ; ne pas modifier à la\n"
        "  main, les corrections se font dans les sources puis on reconstruit.\n"
        "  Aucun script distant, aucune requête réseau : ouvrir dans un\n"
        "  navigateur suffit.\n"
        "-->\n"
    )
    page = page.replace("<!DOCTYPE html>", "<!DOCTYPE html>\n" + entete, 1)

    reste = [m for m in ('src="app/', "href=\"app/") if m in page]
    if reste:
        raise SystemExit("des références locales subsistent : %s" % reste)

    return page, len(collecteur.feuilles), len(collecteur.scripts)


def construire(sortie):
    page, feuilles, scripts = assembler()
    with io.open(sortie, "w", encoding="utf-8") as f:
        f.write(page)
    return feuilles, scripts, sortie.stat().st_size


def verifier(cible):
    """Compare le fichier versionné à une reconstruction. 0 si à jour."""
    attendu, _, _ = assembler()
    if not cible.exists():
        print("%s absent — lancer la construction." % cible.name)
        return 1
    if lire(cible) != attendu:
        print("%s est périmé : les sources ont changé depuis sa construction."
              % cible.name)
        print("Reconstruire avec :  python3 outils/construire_autonome.py")
        return 1
    print("%s est à jour." % cible.name)
    return 0


def main():
    analyseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analyseur.add_argument(
        "-s", "--sortie", default=str(RACINE / "cfd-plot-digitizer.html"),
        help="fichier HTML à écrire (défaut : cfd-plot-digitizer.html à la racine)")
    analyseur.add_argument(
        "--verifier", action="store_true",
        help="ne rien écrire : vérifier que le fichier existant est à jour")
    args = analyseur.parse_args()

    if args.verifier:
        return verifier(pathlib.Path(args.sortie))

    feuilles, scripts, taille = construire(pathlib.Path(args.sortie))
    print("%s écrit — %d feuille(s) de style, %d script(s), %.0f ko"
          % (args.sortie, feuilles, scripts, taille / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
