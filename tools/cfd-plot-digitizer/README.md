# cfd-plot-digitizer

Récupérer les données chiffrées d'un graphique dont on n'a plus que l'image :
figure d'un article, courbe d'une notice constructeur, planche d'un rapport
scanné. On charge l'image, on cale les axes, **on désigne la couleur d'une
courbe et l'outil l'extrait tout entière**.

Conçu pour une machine **coupée du réseau** : une page HTML qu'on ouvre dans un
navigateur. Pas de serveur, pas d'installation, pas de dépendance, aucune donnée
qui sorte du poste.

```
firefox index.html
```

C'est tout. Ou, plus commode encore pour transporter l'outil sur une clé :
`cfd-plot-digitizer.html` à la racine est un **fichier unique de 254 ko** —
interface, code et figure d'exemple compris — versionné tel quel, à copier et à
ouvrir. Rien d'autre à emporter.

Cliquer sur **Exemple** charge un cas complet, calibration et zones déjà posées,
pour prendre l'outil en main en une minute.

Après toute modification des sources, le reconstruire — et le vérifier :

```
python3 outils/construire_autonome.py              # reconstruit
python3 outils/construire_autonome.py --verifier   # 0 si à jour, 1 sinon
```

Un fichier construit et versionné peut se désynchroniser de ses sources sans
que rien ne le signale, et un fichier périmé livré sur une clé est pire que pas
de fichier du tout : il a l'air de fonctionner. D'où `--verifier`, à brancher
dans un contrôle avant commit.

## Ce que ça fait

- **Détection d'une courbe par sa couleur**, avec aperçu en direct des pixels
  retenus, et proposition automatique des couleurs présentes dans le graphique.
- **Tri par type de trait** — continu, tirets, pointillé — pour séparer des
  courbes que *rien d'autre* ne distingue, cas des planches en noir et blanc.
  Avec comblement des lacunes, pour qu'une courbe en tirets ressorte continue.
- **Axes linéaires ou logarithmiques**, y compris **inclinés ou cisaillés** :
  une figure scannée de travers se calibre sans redressement.
- **Détection automatique du cadre** : un bouton place les quatre repères sur
  les axes, à moins de deux pixels près sur les figures d'essai — il ne reste
  qu'à saisir les valeurs. `X1` et `Y1` sont liés par défaut au coin d'origine,
  soit trois repères à poser au lieu de quatre, et chaque position se corrige
  aussi au clavier.
- **Zones d'analyse et d'exclusion** — indispensables pour écarter la légende,
  qui contient des segments de la couleur exacte des courbes.
- **Pointage manuel** à la loupe, mélangeable avec la détection dans une même
  série. Marqueur réglable par série — couleur, forme (dont anneau, croix,
  plus, qui laissent voir la courbe dessous) et taille. La gomme retire un
  point au clic, ou tout un rectangle en glissant.
- **Réglages illustrés** : chaque option de détection porte une vignette qui
  montre ce qu'elle fait, plutôt qu'un intitulé de trois mots à deviner.
- **Export** CSV (long, large, ou **grille X commune interpolée**), texte,
  JSON, Python/NumPy, MATLAB — présentés en fiches, avec un exemple du rendu et
  un bilan de ce qui sera écrit avant de l'écrire.
- **Projets `.digit.json`** autonomes : image, calibration, séries et réglages
  dans un seul fichier, rouvrable ailleurs.

Exactitude mesurée sur des figures matplotlib dont on connaît les données
exactes : **écart médian de 0,1 à 0,5 pixel** entre la courbe extraite et la
courbe vraie (voir « Tests » plus bas).

## Prise en main

1. **Ouvrir une image** — bouton, glisser-déposer, ou <kbd>Ctrl</kbd>+<kbd>V</kbd>
   pour coller une capture d'écran.
2. **Caler les axes** — bouton *Détecter le cadre automatiquement*, puis
   saisir les quatre valeurs. À défaut, outil *Repères* : viser des graduations
   franches et les écarter au maximum ; la loupe est là pour ça.
3. **Cadrer** — outil *Zone* sur le tracé, outil *Exclure* sur la légende.
4. **Prélever la couleur** — outil *Pipette*, clic sur la courbe. Cocher
   *Aperçu du masque* et régler les deux tolérances jusqu'à ce que la courbe
   ressorte, continue, sans que le fond ne s'allume.
5. **Détecter**, corriger à la main si besoin, **exporter**.

### Le réglage qui compte

Deux tolérances plutôt qu'une, et c'est délibéré :

- **teinte** — distingue les courbes entre elles ;
- **clarté** — absorbe l'anticrénelage des bords du trait.

Pour une courbe **noire ou grise**, la teinte ne discrimine rien (a\* et b\*
sont nuls des deux côtés) : **seule la clarté travaille**, il faut donc la
resserrer, pas l'élargir. C'est le seul réglage contre-intuitif de l'outil.

### Deux courbes que la couleur ne sépare pas

Sur une planche en noir et blanc, les courbes ne diffèrent que par leur tracé.
Aucune tolérance ne peut les séparer — elles ont la même couleur. Ce qui les
sépare est **structurel** : un trait plein forme une composante connexe qui
traverse le graphique, un trait discontinu en forme des dizaines. Le réglage
**type de trait** trie là-dessus.

Sur la figure d'essai `exemples/exemple_traits.png` (trois courbes noires,
trois tracés), chaque filtre isole sa courbe avec plus de 97 % des points
correctement attribués. Le réglage **combler les lacunes** raccorde ensuite les
tronçons d'un trait discontinu, sans jamais franchir une vraie interruption.

### Comparer deux courbes entre elles

Deux courbes digitalisées séparément n'ont jamais les mêmes abscisses, ce qui
interdit de les soustraire ou de les aligner dans un tableur. Le format
**CSV — grille X commune** les interpole toutes sur une même abscisse. Hors du
domaine d'une série, la cellule reste vide : l'outil n'extrapole pas. Une
courbe repliée — une polaire — est écartée en le disant, plutôt que d'être
silencieusement écrasée sur elle-même.

### Le piège qui coûte cher

Une **polaire** `Cz(Cx)` est un arc couché : deux `Cz` pour un même `Cx`.
Balayée en colonnes, l'outil rend le milieu des deux branches, c'est-à-dire une
courbe fausse. Passer le **balayage en lignes** : la courbe redevient une
fonction et se lit exactement. Règle générale : *balayer perpendiculairement à
la courbe*.

Second piège, plus sournois : **oublier d'exclure la légende**. Sur la figure de
convergence livrée en exemple, cet oubli fait passer l'erreur de 0,03 % à
1,9 décade — et les points parasites se fondent dans le lot.

Les deux sont détaillés dans [`00_DOC/02_DETECTION_COULEUR.md`](00_DOC/02_DETECTION_COULEUR.md).

## Raccourcis

| Touche | Effet |
|--------|-------|
| <kbd>V</kbd> <kbd>C</kbd> <kbd>P</kbd> <kbd>Z</kbd> <kbd>X</kbd> <kbd>A</kbd> <kbd>E</kbd> | naviguer, repères, pipette, zone, exclure, pointer, gommer |
| <kbd>+</kbd> <kbd>−</kbd> <kbd>0</kbd> | zoom avant, arrière, ajuster |
| molette | zoom autour du curseur |
| <kbd>Espace</kbd>+glisser, ou bouton du milieu | déplacer l'image |
| <kbd>Ctrl</kbd>+<kbd>Z</kbd> | annuler |
| <kbd>Ctrl</kbd>+<kbd>S</kbd> | enregistrer le projet |
| <kbd>Suppr</kbd> | vider la série active |

## Organisation

```
index.html                  l'application
cfd-plot-digitizer.html     la même, en un seul fichier (construit, versionné)
app/css/style.css           feuille unique, aucune police distante
app/js/
  00_base.js                algèbre, formatage, Douglas-Peucker
  10_couleur.js             sRGB -> CIE L*a*b*, critère de correspondance
  15_cadre.js               détection du cadre du tracé (profils d'encre)
  20_calibration.js         pixels <-> grandeurs physiques
  25_trait.js               composantes connexes, type de tracé
  30_detection.js           masque, balayage, extraction
  40_export.js              CSV, JSON, Python, MATLAB
  50_projet.js              sauvegarde et relecture
  60_vue.js                 cadrage, zoom, rendu du canevas, marqueurs
  70_vignettes.js           illustrations SVG des réglages
  80_exemple.js             figure de démonstration embarquée (engendré)
  90_main.js                état et câblage de l'interface
00_DOC/                     01 calibration, 02 détection, 03 export
exemples/                   figures d'essai + valeurs de référence
outils/                     construction du fichier unique, vérifications
tests/                      suite de tests (node et navigateur)
```

Les modules `00` à `70` ne touchent jamais au DOM et sont testés isolément ;
seul `90_main.js` connaît l'interface.

**Aucun module ES.** Firefox refuse les `import` sur une page ouverte en
`file://` (origine opaque) : les scripts sont donc chargés en balises
classiques et s'accrochent à un espace de noms `CFDD`. C'est ce qui permet
d'ouvrir `index.html` sans serveur — la contrainte de départ.

## Tests

```
node tests/executer.js          # 172 tests, environ une seconde
```

ou, sans node — ce qui arrive sur un poste verrouillé — **ouvrir
`tests/index.html` dans le navigateur** : mêmes fichiers, mêmes tests.

Les quatorze tests d'intégration lisent de vraies figures matplotlib et
comparent au jeu de données qui a servi à les tracer — courbes extraites, et
cadre détecté contre la boîte que matplotlib a réellement dessinée ; ils ne tournent que sous node et se
désactivent d'eux-mêmes dans le navigateur. Ils mesurent la distance entre
courbe extraite et courbe vraie, dans un repère normalisé par l'étendue des
axes — la seule mesure honnête, un écart vertical étant amplifié par la pente
là où la courbe est raide.

Régénérer les figures d'essai (nécessite matplotlib) :

```
python3 exemples/generer_exemples.py
python3 outils/generer_exemple_embarque.py
```

Vérifier le rendu dans un vrai navigateur, ce que node ne peut pas voir :

```
bash outils/verifier_navigateur.sh tests/index.html controle.png
```

Le script refuse d'emblée les chemins que Firefox en paquet snap ne sait pas
lire — `/tmp` et les dossiers cachés de `$HOME` — qui donnent sinon une capture
noire sans le moindre message.

## Limites connues

- **Deux courbes de même couleur superposées** : rien ne permet de les séparer
  là où elles sont confondues. Le mode *suivi* traite les croisements, pas les
  recouvrements ; et là où deux tracés se croisent, ils fusionnent en une seule
  composante que le tri par type de trait attribue en bloc.
- **Fond texturé, tramé ou photographié** : le critère de couleur suppose des
  aplats.
- **Là où la courbe devient parallèle au balayage**, l'écart monte à 1 ou 2
  pixels au lieu de 0,1 à 0,5. Changer d'orientation.

## Pourquoi une page web et pas un programme Python

Le reste de `tools/` est en Python ; ici l'exigence est différente. Sur un poste
hors réseau, une page HTML n'a besoin de rien : le navigateur est déjà installé,
il n'y a ni interpréteur à provisionner, ni roue à faire entrer, ni pile
graphique à faire fonctionner. Un équivalent Python demanderait NumPy, Pillow et
une bibliothèque d'interface — trois occasions d'être bloqué le jour où l'on en
a besoin.

Le canevas HTML donne par ailleurs gratuitement ce qui fait le confort de ce
type d'outil : zoom, déplacement, loupe, aperçu en direct, glisser-déposer,
collage de capture d'écran.

Python garde tout son intérêt **en aval** : le CSV exporté se lit avec pandas et
se trace avec `cfd-plot` (voir [`00_DOC/03_EXPORT_ET_PROJET.md`](00_DOC/03_EXPORT_ET_PROJET.md)).

## Origine

L'ergonomie s'inspire de [PinPoint Digitizer](https://github.com/mhismail/PinPoint-Digitizer)
(MIT, Mohamed H. Ismail) : loupe à réticule, repères d'axes, séries nommées.
Le code, lui, est entièrement nouveau. PinPoint est une application **Electron**
— `require('electron')`, `remote`, `fs`, plus jQuery, DataTables et jQuery-UI
tirés de `node_modules` — et ne peut pas fonctionner en ouvrant son
`index.html` dans un navigateur. Le porter revenait à le réécrire ; la
détection automatique par couleur, les zones d'exclusion et le balayage en
lignes n'y existent pas.
