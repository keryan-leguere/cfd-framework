/*
 * 90_main.js — état de l'application et câblage de l'interface.
 *
 * Seul fichier à toucher au DOM ; toute la logique utile vit dans les modules
 * 00 à 60, testés indépendamment.
 *
 * Principe directeur : l'état est la seule source de vérité, `redessiner()` et
 * `rafraichirPanneau()` en sont des projections. Aucun handler ne modifie le
 * canevas ou le panneau directement — ils changent l'état puis redemandent un
 * rendu. C'est ce qui permet à « annuler » de se réduire à une restauration.
 */
(function () {
  'use strict';

  var CFDD = globalThis.CFDD;
  var Base = CFDD.Base, Couleur = CFDD.Couleur, Calibration = CFDD.Calibration;
  var Detection = CFDD.Detection, Export = CFDD.Export, Projet = CFDD.Projet;
  var Vue = CFDD.Vue, Trait = CFDD.Trait;

  var COULEURS_SERIE = ['#c1121f', '#1d3557', '#2a9d8f', '#e07a00',
                        '#7b2cbf', '#0b7285', '#a4133c', '#386641'];
  var COULEUR_REPERE = '#1b6ec2';
  var COULEUR_ZONE = '#12b886';
  var COULEUR_EXCLUSION = '#e8590c';

  /* ================== État ================== */

  var etat = {
    image: null,            /* HTMLImageElement | HTMLCanvasElement */
    imageMeta: null,        /* {nom, dataURL, largeur, hauteur} */
    imageData: null,        /* {data, width, height} pour la détection */
    vue: Vue.creer(),
    outil: 'navigation',
    reperes: { x1: null, x2: null, y1: null, y2: null },
    repereActif: 'x1',
    valeurs: { x1: '', x2: '', y1: '', y2: '' },
    logX: false, logY: false,
    calibration: null,
    zone: null,
    exclusions: [],
    series: [],
    serieActive: -1,
    detection: {
      couleur: '#c1121f', tolChroma: 20, tolLum: 30,
      orientation: 'colonnes', mode: 'moyenne',
      pas: 1, longueurMin: 1, longueurMax: 0, simplification: 0,
      filtreTrait: 'tous', comblerLacunes: 0
    },
    apercu: true,
    apercuMode: 'les-deux',
    apercuOpacite: 0.85,
    apercuEpaissir: true,
    grille: { points: 200, espacement: 'lineaire', domaine: 'intersection' },
    calqueMasque: null,     /* {canvas, zone} */
    notes: '',
    curseur: null,          /* dernière position image du curseur */
    tirage: null,           /* rectangle en cours de tracé */
    historique: []
  };

  /* ================== Raccourcis DOM ================== */

  function $(id) { return document.getElementById(id); }
  var scene = $('scene');
  var canevas = $('canevas');
  var ctx = canevas.getContext('2d');
  var loupe = $('loupe');
  var ctxLoupe = loupe.getContext('2d');

  /* ================== Messages ================== */

  var minuteurMessage = null;
  function message(texte, genre) {
    var el = $('etat-message');
    el.textContent = texte || '';
    el.className = genre || '';
    if (minuteurMessage) { clearTimeout(minuteurMessage); minuteurMessage = null; }
    if (texte) { minuteurMessage = setTimeout(function () { el.textContent = ''; el.className = ''; }, 6000); }
  }

  /* ================== Historique ================== */

  /*
   * On ne mémorise que les séries : c'est là que se joue le travail long et
   * pénible à refaire. Repères et zones se replacent en un clic.
   */
  function memoriser() {
    etat.historique.push(JSON.stringify(etat.series));
    if (etat.historique.length > 40) { etat.historique.shift(); }
  }

  function annuler() {
    if (!etat.historique.length) { message('Rien à annuler.'); return; }
    etat.series = JSON.parse(etat.historique.pop());
    if (etat.serieActive >= etat.series.length) { etat.serieActive = etat.series.length - 1; }
    rafraichirSeries(); redessiner(); rafraichirExport();
    message('Action annulée.');
  }

  /* ================== Chargement d'image ================== */

  function chargerDataURL(dataURL, nom) {
    var img = new Image();
    img.onload = function () {
      etat.image = img;
      etat.imageMeta = { nom: nom || 'image', dataURL: dataURL,
                         largeur: img.naturalWidth, hauteur: img.naturalHeight };

      /*
       * Copie hors écran pour getImageData : l'élément <img> ne donne pas
       * accès aux pixels. Comme la source est une data URL, le canevas n'est
       * pas « teinté » et la lecture reste autorisée, y compris en file://.
       */
      var tampon = document.createElement('canvas');
      tampon.width = img.naturalWidth;
      tampon.height = img.naturalHeight;
      var c = tampon.getContext('2d', { willReadFrequently: true });
      c.drawImage(img, 0, 0);
      try {
        etat.imageData = c.getImageData(0, 0, tampon.width, tampon.height);
      } catch (e) {
        etat.imageData = null;
        message('Pixels illisibles : la détection automatique sera indisponible.', 'alerte');
      }

      etat.calqueMasque = null;
      $('accueil').hidden = true;
      $('info-image').textContent = etat.imageMeta.nom + ' — '
        + img.naturalWidth + ' x ' + img.naturalHeight + ' pixels';
      ajusterVue();
      rafraichirZone();
      message('Image chargée.', 'succes');
    };
    img.onerror = function () { message('Image illisible.', 'alerte'); };
    img.src = dataURL;
  }

  function chargerFichierImage(fichier) {
    if (!fichier) { return; }
    if (fichier.type && fichier.type.indexOf('image/') !== 0) {
      message('Ce fichier n’est pas une image.', 'alerte'); return;
    }
    var lecteur = new FileReader();
    lecteur.onload = function () { chargerDataURL(lecteur.result, fichier.name); };
    lecteur.onerror = function () { message('Lecture impossible.', 'alerte'); };
    lecteur.readAsDataURL(fichier);
  }

  /* ================== Vue ================== */

  function dimensionnerCanevas() {
    var ratio = window.devicePixelRatio || 1;
    var l = scene.clientWidth, h = scene.clientHeight;
    if (!l || !h) { return; }
    canevas.width = Math.round(l * ratio);
    canevas.height = Math.round(h * ratio);
    /* Tout le rendu raisonne en pixels CSS ; l'échelle du contexte absorbe
       la densité de l'écran, sans quoi l'affichage serait flou sur un écran HiDPI. */
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  }

  function ajusterVue() {
    if (!etat.image) { return; }
    dimensionnerCanevas();
    etat.vue = Vue.ajuster(etat.image.naturalWidth || etat.image.width,
      etat.image.naturalHeight || etat.image.height,
      scene.clientWidth, scene.clientHeight, 20);
    redessiner();
  }

  function positionImage(evenement) {
    var boite = canevas.getBoundingClientRect();
    return Vue.versImage(etat.vue, evenement.clientX - boite.left, evenement.clientY - boite.top);
  }

  function majZoom() {
    $('etiquette-zoom').textContent = Math.round(etat.vue.echelle * 100) + ' %';
  }

  /* ================== Rendu ================== */

  function redessiner() {
    if (!canevas.width) { dimensionnerCanevas(); }
    var l = scene.clientWidth, h = scene.clientHeight;
    ctx.clearRect(0, 0, l, h);
    if (!etat.image) { majZoom(); return; }

    Vue.dessinerImage(ctx, etat.image, etat.vue);

    if (etat.zone) { Vue.dessinerRectangle(ctx, etat.vue, etat.zone, COULEUR_ZONE, false); }
    for (var i = 0; i < etat.exclusions.length; i++) {
      Vue.dessinerRectangle(ctx, etat.vue, etat.exclusions[i], COULEUR_EXCLUSION, true);
    }
    if (etat.tirage) {
      Vue.dessinerRectangle(ctx, etat.vue, etat.tirage,
        etat.outil === 'exclusion' ? COULEUR_EXCLUSION : COULEUR_ZONE,
        etat.outil === 'exclusion');
    }

    for (var s = 0; s < etat.series.length; s++) {
      var serie = etat.series[s];
      if (serie.masquee) { continue; }
      Vue.dessinerPoints(ctx, etat.vue, serie.points, serie.couleurHex, null);
    }

    /*
     * L'aperçu passe PAR-DESSUS les séries déjà tracées : c'est lui que
     * l'utilisateur règle à cet instant, et des points posés dessus le
     * masqueraient précisément là où il faut le juger.
     */
    if (etat.apercu && etat.calqueMasque) {
      Vue.dessinerMasque(ctx, etat.vue, etat.calqueMasque.canvas,
        etat.calqueMasque.zone, etat.apercuOpacite);
    }

    var cles = Calibration.ORDRE;
    for (var k = 0; k < cles.length; k++) {
      var r = etat.reperes[cles[k]];
      if (r) {
        Vue.dessinerRepere(ctx, etat.vue, r, cles[k].toUpperCase(),
          COULEUR_REPERE, cles[k] === etat.repereActif);
      }
    }

    majZoom();
  }

  function majLoupe() {
    var actifs = ['calibration', 'points', 'gomme', 'pipette'];
    var visible = etat.image && etat.curseur && actifs.indexOf(etat.outil) !== -1;
    loupe.hidden = !visible;
    if (!visible) { return; }
    Vue.dessinerLoupe(ctxLoupe, etat.image, etat.curseur.px, etat.curseur.py, 150, 10, '#1b6ec2');
  }

  /* ================== Calibration ================== */

  function construireLignesReperes() {
    var corps = $('corps-reperes');
    corps.textContent = '';
    Calibration.ORDRE.forEach(function (cle) {
      var tr = document.createElement('tr');
      tr.dataset.repere = cle;

      var tdNom = document.createElement('td');
      var bouton = document.createElement('button');
      bouton.className = 'repere-nom lien';
      bouton.textContent = cle.toUpperCase();
      bouton.title = Calibration.LIBELLES[cle];
      bouton.addEventListener('click', function () {
        etat.repereActif = cle;
        choisirOutil('calibration');
        rafraichirCalibration();
      });
      tdNom.appendChild(bouton);

      var tdValeur = document.createElement('td');
      var champ = document.createElement('input');
      champ.type = 'text';
      champ.inputMode = 'decimal';
      champ.placeholder = (cle[0] === 'x') ? 'valeur X' : 'valeur Y';
      champ.addEventListener('input', function () {
        etat.valeurs[cle] = champ.value;
        recalculerCalibration();
      });
      tdValeur.appendChild(champ);

      var tdPos = document.createElement('td');
      tdPos.className = 'position';

      tr.appendChild(tdNom); tr.appendChild(tdValeur); tr.appendChild(tdPos);
      corps.appendChild(tr);
    });
  }

  /*
   * Accepte la virgule décimale : sur un clavier français, taper « 1,5 » est
   * le geste naturel, et le rejeter silencieusement est un piège classique.
   */
  function lireNombre(texte) {
    if (typeof texte !== 'string' || !texte.trim()) { return NaN; }
    return Number(texte.trim().replace(',', '.'));
  }

  function recalculerCalibration() {
    var reperes = {};
    Calibration.ORDRE.forEach(function (cle) {
      var r = etat.reperes[cle];
      reperes[cle] = r ? { px: r.px, py: r.py, valeur: lireNombre(etat.valeurs[cle]) } : null;
    });

    var soucis = Calibration.verifier(reperes, etat.logX, etat.logY);
    var el = $('etat-calibration');
    if (soucis.length) {
      etat.calibration = null;
      /* Un seul souci à la fois : une liste de six lignes n'aide personne. */
      el.textContent = soucis[0];
      el.className = 'etat-calibration souci';
    } else {
      try {
        etat.calibration = Calibration.creer({ reperes: reperes, logX: etat.logX, logY: etat.logY });
        var res = Calibration.resolutionLocale(etat.calibration,
          reperes.x1.px, reperes.y2.py);
        el.textContent = 'Calibration valide — un pixel vaut environ '
          + Base.formaterNombre(res.x, 2) + ' en X et '
          + Base.formaterNombre(res.y, 2) + ' en Y.';
        el.className = 'etat-calibration ok';
      } catch (e) {
        etat.calibration = null;
        el.textContent = e.message;
        el.className = 'etat-calibration souci';
      }
    }
    rafraichirExport();
  }

  function rafraichirCalibration() {
    var lignes = $('corps-reperes').children;
    for (var i = 0; i < lignes.length; i++) {
      var tr = lignes[i];
      var cle = tr.dataset.repere;
      var r = etat.reperes[cle];
      tr.classList.toggle('actif', cle === etat.repereActif);
      tr.querySelector('input').value = etat.valeurs[cle];
      tr.querySelector('.position').textContent =
        r ? (Math.round(r.px) + ', ' + Math.round(r.py)) : 'non placé';
    }
    recalculerCalibration();
  }

  /* Repère suivant non encore placé : évite de recliquer dans la liste. */
  function avancerRepere() {
    var ordre = Calibration.ORDRE;
    for (var i = 0; i < ordre.length; i++) {
      var candidat = ordre[(ordre.indexOf(etat.repereActif) + 1 + i) % ordre.length];
      if (!etat.reperes[candidat]) { etat.repereActif = candidat; return; }
    }
  }

  /* ================== Zones ================== */

  function rafraichirZone() {
    var texte;
    if (etat.zone) {
      texte = 'Zone : (' + etat.zone.x0 + ', ' + etat.zone.y0 + ') à ('
        + etat.zone.x1 + ', ' + etat.zone.y1 + ')';
    } else {
      texte = 'Zone : image entière.';
    }
    $('info-zone').textContent = texte;

    var liste = $('liste-exclusions');
    liste.textContent = '';
    etat.exclusions.forEach(function (ex, index) {
      var li = document.createElement('li');
      var texteEx = document.createElement('span');
      texteEx.textContent = 'Exclusion ' + (index + 1) + ' — '
        + (ex.x1 - ex.x0 + 1) + ' x ' + (ex.y1 - ex.y0 + 1) + ' px';
      var supprimer = document.createElement('button');
      supprimer.textContent = 'Retirer';
      supprimer.addEventListener('click', function () {
        etat.exclusions.splice(index, 1);
        rafraichirZone(); redessiner();
      });
      li.appendChild(texteEx); li.appendChild(supprimer);
      liste.appendChild(li);
    });
  }

  /* ================== Séries ================== */

  function nouvelleSerie(nom, couleur) {
    var serie = {
      nom: nom || ('Série ' + (etat.series.length + 1)),
      couleurHex: couleur || COULEURS_SERIE[etat.series.length % COULEURS_SERIE.length],
      points: [], masquee: false, detection: null
    };
    etat.series.push(serie);
    etat.serieActive = etat.series.length - 1;
    return serie;
  }

  function serieCourante() {
    if (etat.serieActive < 0 || etat.serieActive >= etat.series.length) { return null; }
    return etat.series[etat.serieActive];
  }

  function rafraichirSeries() {
    var liste = $('liste-series');
    liste.textContent = '';

    if (!etat.series.length) {
      var vide = document.createElement('li');
      vide.className = 'discret';
      vide.textContent = 'Aucune série. Lancez une détection ou pointez à la main.';
      liste.appendChild(vide);
    }

    etat.series.forEach(function (serie, index) {
      var li = document.createElement('li');
      li.className = (index === etat.serieActive) ? 'actif' : '';
      li.addEventListener('click', function (e) {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'BUTTON') { return; }
        etat.serieActive = index;
        $('couleur-cible').value = serie.couleurHex;
        etat.detection.couleur = serie.couleurHex;
        rafraichirSeries();
      });

      var pastille = document.createElement('input');
      pastille.type = 'color';
      pastille.value = serie.couleurHex;
      pastille.style.width = '22px';
      pastille.style.height = '22px';
      pastille.title = 'Couleur d’affichage';
      pastille.addEventListener('input', function () {
        serie.couleurHex = pastille.value;
        redessiner();
      });

      var nom = document.createElement('input');
      nom.type = 'text';
      nom.className = 'nom';
      nom.value = serie.nom;
      nom.addEventListener('input', function () {
        serie.nom = nom.value;
        rafraichirExport();
      });

      var compte = document.createElement('span');
      compte.className = 'compte';
      compte.textContent = serie.points.length;

      var oeil = document.createElement('button');
      oeil.className = 'oeil' + (serie.masquee ? ' masquee' : '');
      oeil.textContent = serie.masquee ? '○' : '●';
      oeil.title = serie.masquee ? 'Afficher' : 'Masquer';
      oeil.addEventListener('click', function () {
        serie.masquee = !serie.masquee;
        rafraichirSeries(); redessiner();
      });

      li.appendChild(pastille); li.appendChild(nom);
      li.appendChild(compte); li.appendChild(oeil);
      liste.appendChild(li);
    });

    rafraichirExport();
  }

  /* ================== Détection ================== */

  function optionsDetection() {
    return {
      tolChroma: etat.detection.tolChroma,
      tolLum: etat.detection.tolLum,
      orientation: etat.detection.orientation,
      mode: etat.detection.mode,
      pas: etat.detection.pas,
      longueurMin: etat.detection.longueurMin,
      longueurMax: etat.detection.longueurMax,
      simplification: etat.detection.simplification,
      filtreTrait: etat.detection.filtreTrait,
      comblerLacunes: etat.detection.comblerLacunes,
      zone: etat.zone,
      zonesExclues: etat.exclusions
    };
  }

  function majApercuMasque() {
    if (!etat.apercu || !etat.imageData) { etat.calqueMasque = null; redessiner(); return; }
    var cible = Couleur.hexVersRgb(etat.detection.couleur);
    if (!cible) { return; }

    var info = Detection.construireMasque(etat.imageData, cible, optionsDetection());

    /*
     * L'aperçu doit montrer ce que la DÉTECTION retiendra, tri du type de trait
     * compris — sinon l'utilisateur règle ses tolérances sur un masque qui
     * n'est pas celui qui sera exploité.
     */
    if (etat.detection.filtreTrait && etat.detection.filtreTrait !== 'tous') {
      info = Trait.filtrer(info, Trait.composantes(info),
        etat.detection.filtreTrait, etat.detection.orientation);
    }

    /*
     * La couleur de surbrillance est choisie pour trancher sur la cible : un
     * aperçu magenta sur une courbe magenta serait invisible, or c'est
     * exactement la courbe que l'utilisateur regarde.
     */
    var surbrillance = Couleur.contrastee(cible, { r: 255, g: 255, b: 255 });

    etat.calqueMasque = {
      canvas: Vue.calqueMasque(info, {
        couleur: surbrillance,
        mode: etat.apercuMode,
        epaissir: etat.apercuEpaissir ? 1 : 0,
        voile: { r: 255, g: 255, b: 255 },
        opaciteVoile: 200
      }, function (l, h) {
        var c = document.createElement('canvas'); c.width = l; c.height = h; return c;
      }),
      zone: info.zone
    };
    redessiner();
  }

  function detecter() {
    if (!etat.imageData) { message('Chargez d’abord une image.', 'alerte'); return; }
    var cible = Couleur.hexVersRgb(etat.detection.couleur);
    if (!cible) { message('Couleur cible invalide.', 'alerte'); return; }

    var debut = performance.now();
    var res = Detection.detecter(etat.imageData, cible, optionsDetection());
    var duree = performance.now() - debut;

    if (!res.points.length) {
      message('Aucun pixel ne correspond : élargissez les tolérances ou vérifiez la zone.', 'alerte');
      $('stats-detection').textContent = '';
      return;
    }

    memoriser();
    var serie = serieCourante();
    /* Une détection remplace la série active si elle est vide, sinon elle en
       crée une nouvelle : on ne détruit jamais un pointage manuel par mégarde. */
    if (!serie || serie.points.length) {
      serie = nouvelleSerie(null, etat.detection.couleur);
    } else {
      serie.couleurHex = etat.detection.couleur;
    }
    serie.points = res.points;
    serie.detection = optionsDetection();

    var s = res.statistiques;
    var detailPoints = String(s.pointsFinaux) + ' points';
    if (s.pointsCombles !== s.pointsBruts) {
      detailPoints += ' (' + s.pointsBruts + ' détectés, '
        + (s.pointsCombles - s.pointsBruts) + ' interpolés)';
    } else if (s.pointsBruts !== s.pointsFinaux) {
      detailPoints += ' (ramenés de ' + s.pointsBruts + ')';
    }
    $('stats-detection').textContent = detailPoints
      + ' — ' + s.lignesRetenues + '/' + s.lignesVues + ' lignes de balayage, '
      + s.pixelsRetenus + ' pixels retenus, ' + duree.toFixed(0) + ' ms.';
    afficherTrait(s.trait);

    rafraichirSeries(); redessiner();
    message('Détection terminée : ' + res.points.length + ' points.', 'succes');
  }

  /*
   * Restitue le type de trait mesuré. Les longueurs de marque et d'espace ne
   * sont pas décoratives : elles donnent directement le plafond à saisir dans
   * « combler les lacunes ».
   */
  function afficherTrait(trait) {
    var el = $('stats-trait');
    if (!trait || trait.style === Trait.STYLES.inconnu) { el.textContent = ''; return; }

    if (trait.style === Trait.STYLES.continu) {
      el.textContent = 'Trait continu (' + trait.nbComposantes
        + (trait.nbComposantes > 1 ? ' tronçons).' : ' tronçon).');
      return;
    }
    el.textContent = 'Trait ' + trait.style + ' : marque ' + Math.round(trait.marque)
      + ' px, espace ' + Math.round(trait.espace) + ' px, sur '
      + trait.nbComposantes + ' tronçons. Combler au-delà de '
      + Math.ceil(trait.espace + 2) + ' px pour raccorder.';
  }

  function proposerPalette() {
    if (!etat.imageData) { message('Chargez d’abord une image.', 'alerte'); return; }
    var couleurs = Detection.couleursDominantes(etat.imageData, {
      zone: etat.zone, zonesExclues: etat.exclusions, maxCouleurs: 10,
      /* Un pixel sur deux dans chaque direction : quatre fois plus rapide, et
         sans effet visible sur des aplats de plusieurs milliers de pixels. */
      pas: 2
    });
    var boite = $('palette');
    boite.textContent = '';
    if (!couleurs.length) {
      boite.textContent = 'Aucune couleur dominante hors du fond.';
      return;
    }
    couleurs.forEach(function (c) {
      var b = document.createElement('button');
      b.style.background = c.hex;
      b.title = c.hex + ' — ' + (c.proportion * 100).toFixed(2) + ' % de la zone';
      b.addEventListener('click', function () {
        etat.detection.couleur = c.hex;
        $('couleur-cible').value = c.hex;
        majApercuMasque();
      });
      boite.appendChild(b);
    });
  }

  /* ================== Export ================== */

  function seriesEnDonnees() {
    if (!etat.calibration) { return null; }
    return Projet.seriesEnDonnees(etat.series.filter(function (s) { return !s.masquee; }),
      etat.calibration);
  }

  function optionsExport() {
    return {
      separateur: $('separateur').value,
      decimales: Math.max(1, Math.min(15, parseInt($('decimales').value, 10) || 6)),
      grillePoints: etat.grille.points,
      grilleEspacement: etat.grille.espacement,
      grilleDomaine: etat.grille.domaine
    };
  }

  function texteExport() {
    var series = seriesEnDonnees();
    if (!series) { return null; }
    return Export.rendre($('format').value, series, optionsExport());
  }

  function rafraichirExport() {
    var zone = $('apercu-export');
    var grille = ($('format').value === 'csv-grille');
    $('reglages-grille').hidden = !grille;

    /*
     * Les séries écartées du ré-échantillonnage (courbe repliée, série trop
     * courte, domaines disjoints) doivent être dites : sans cela une colonne
     * manquerait au tableau sans que rien ne l'explique.
     */
    var avertissements = $('avertissements-grille');
    avertissements.textContent = '';
    if (grille && etat.calibration) {
      var series = seriesEnDonnees();
      if (series && series.length) {
        var resultat = Export.reechantillonner(series, optionsExport());
        if (resultat.avertissements.length) {
          avertissements.textContent = resultat.avertissements.join(' ');
        }
      }
    }

    if (!etat.calibration) {
      zone.value = 'Calibration incomplète : placez les quatre repères et saisissez leurs valeurs.';
      return;
    }
    var series = seriesEnDonnees();
    if (!series || !series.length) { zone.value = 'Aucune série visible.'; return; }

    var texte = texteExport();
    /*
     * Aperçu tronqué : afficher 50 000 lignes dans un <textarea> fige l'onglet
     * plusieurs secondes, sans rien apprendre de plus à l'utilisateur.
     */
    var lignes = texte.split('\n');
    if (lignes.length > 200) {
      zone.value = lignes.slice(0, 200).join('\n')
        + '\n… (' + (lignes.length - 200) + ' lignes supplémentaires à l’export)';
    } else {
      zone.value = texte;
    }
  }

  function telecharger(nom, contenu, type) {
    var blob = new Blob([contenu], { type: (type || 'text/plain') + ';charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = nom;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    /* Libération différée : révoquer trop tôt annule le téléchargement. */
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
  }

  function nomDeBase() {
    var nom = (etat.imageMeta && etat.imageMeta.nom) ? etat.imageMeta.nom : 'donnees';
    return nom.replace(/\.[^.]+$/, '') || 'donnees';
  }

  /* ================== Outils du canevas ================== */

  function choisirOutil(nom) {
    etat.outil = nom;
    scene.dataset.outil = nom;
    var boutons = document.querySelectorAll('.outil');
    for (var i = 0; i < boutons.length; i++) {
      boutons[i].classList.toggle('actif', boutons[i].dataset.outil === nom);
    }
    majLoupe();
  }

  function pointLePlusProche(serie, px, py, rayonEcran) {
    var meilleur = -1, meilleureDist = Infinity;
    var rayonImage = rayonEcran / etat.vue.echelle;
    for (var i = 0; i < serie.points.length; i++) {
      var dx = serie.points[i].px - px, dy = serie.points[i].py - py;
      var d = dx * dx + dy * dy;
      if (d < meilleureDist) { meilleureDist = d; meilleur = i; }
    }
    return (meilleur >= 0 && Math.sqrt(meilleureDist) <= rayonImage) ? meilleur : -1;
  }

  var glissement = null;

  canevas.addEventListener('pointerdown', function (e) {
    if (!etat.image) { return; }
    canevas.setPointerCapture(e.pointerId);
    var p = positionImage(e);

    /* Bouton du milieu ou barre d'espace : déplacement, quel que soit l'outil. */
    var deplacement = (e.button === 1) || espaceEnfonce || etat.outil === 'navigation';

    if (deplacement) {
      glissement = { genre: 'vue', x: e.clientX, y: e.clientY, vue: etat.vue };
      scene.classList.add('saisie');
      e.preventDefault();
      return;
    }

    if (e.button !== 0) { return; }

    if (etat.outil === 'calibration') {
      etat.reperes[etat.repereActif] = { px: p.px, py: p.py };
      glissement = { genre: 'repere', cle: etat.repereActif };
      avancerRepere();
      rafraichirCalibration(); redessiner();

    } else if (etat.outil === 'pipette') {
      preleverCouleur(p.px, p.py, e.shiftKey);

    } else if (etat.outil === 'zone' || etat.outil === 'exclusion') {
      glissement = { genre: 'rect', x0: p.px, y0: p.py };
      etat.tirage = { x0: p.px, y0: p.py, x1: p.px, y1: p.py };

    } else if (etat.outil === 'points') {
      var serie = serieCourante() || nouvelleSerie();
      memoriser();
      serie.points.push({ px: p.px, py: p.py });
      /* Ordre de balayage conservé : un export doit être monotone. */
      var selonX = etat.detection.orientation !== 'lignes';
      serie.points.sort(function (a, b) { return selonX ? (a.px - b.px) : (a.py - b.py); });
      rafraichirSeries(); redessiner();

    } else if (etat.outil === 'gomme') {
      var courante = serieCourante();
      if (courante) {
        var index = pointLePlusProche(courante, p.px, p.py, 12);
        if (index >= 0) {
          memoriser();
          courante.points.splice(index, 1);
          rafraichirSeries(); redessiner();
        }
      }
    }
  });

  canevas.addEventListener('pointermove', function (e) {
    if (!etat.image) { return; }
    var p = positionImage(e);
    etat.curseur = p;

    if (glissement && glissement.genre === 'vue') {
      etat.vue = Vue.contraindre(
        Vue.deplacer(glissement.vue, e.clientX - glissement.x, e.clientY - glissement.y),
        etat.image.naturalWidth, etat.image.naturalHeight,
        scene.clientWidth, scene.clientHeight, 60);
      redessiner();

    } else if (glissement && glissement.genre === 'repere') {
      etat.reperes[glissement.cle] = { px: p.px, py: p.py };
      rafraichirCalibration(); redessiner();

    } else if (glissement && glissement.genre === 'rect') {
      etat.tirage = { x0: glissement.x0, y0: glissement.y0, x1: p.px, y1: p.py };
      redessiner();
    }

    majEtatPosition(p);
    majLoupe();
  });

  function terminerGlissement() {
    if (glissement && glissement.genre === 'rect' && etat.tirage) {
      var zone = Detection.normaliserZone(etat.tirage,
        etat.image.naturalWidth, etat.image.naturalHeight);
      /* Un simple clic ne doit pas créer un rectangle de 1 px. */
      if ((zone.x1 - zone.x0) > 4 && (zone.y1 - zone.y0) > 4) {
        if (etat.outil === 'exclusion') { etat.exclusions.push(zone); }
        else { etat.zone = zone; }
        rafraichirZone();
        if (etat.apercu) { majApercuMasque(); }
      }
    }
    etat.tirage = null;
    glissement = null;
    scene.classList.remove('saisie');
    redessiner();
  }

  canevas.addEventListener('pointerup', terminerGlissement);
  canevas.addEventListener('pointercancel', terminerGlissement);
  canevas.addEventListener('pointerleave', function () {
    etat.curseur = null;
    $('etat-position').textContent = '—';
    majLoupe();
  });

  canevas.addEventListener('wheel', function (e) {
    if (!etat.image) { return; }
    e.preventDefault();
    var boite = canevas.getBoundingClientRect();
    var facteur = Math.pow(1.0015, -e.deltaY);
    etat.vue = Vue.zoomerAutour(etat.vue, e.clientX - boite.left, e.clientY - boite.top, facteur);
    redessiner();
  }, { passive: false });

  function majEtatPosition(p) {
    var texte = 'pixel ' + Math.round(p.px) + ', ' + Math.round(p.py);
    if (etat.calibration) {
      var d = etat.calibration.versDonnees(p.px, p.py);
      texte += '   |   x = ' + Base.formaterNombre(d.x, 5)
             + '   y = ' + Base.formaterNombre(d.y, 5);
    }
    $('etat-position').textContent = texte;
  }

  function preleverCouleur(px, py, dominante) {
    if (!etat.imageData) { message('Pixels indisponibles.', 'alerte'); return; }
    var x = Math.round(px), y = Math.round(py);
    var rgb = dominante
      ? Couleur.echantillonnerDominante(etat.imageData, x, y, 3)
      : Couleur.echantillonner(etat.imageData, x, y, 1);
    if (!rgb) { message('Rien à prélever ici.', 'alerte'); return; }
    var hex = Couleur.rgbVersHex(rgb);
    etat.detection.couleur = hex;
    $('couleur-cible').value = hex;
    majApercuMasque();
    message('Couleur prélevée : ' + hex
      + (dominante ? ' (teinte dominante).' : ' — Maj+clic prend la teinte dominante.'),
      'succes');
  }

  /* ================== Clavier ================== */

  var espaceEnfonce = false;
  var RACCOURCIS_OUTILS = {
    v: 'navigation', c: 'calibration', p: 'pipette',
    z: 'zone', x: 'exclusion', a: 'points', e: 'gomme'
  };

  document.addEventListener('keydown', function (e) {
    var cible = e.target;
    var saisie = cible && (cible.tagName === 'INPUT' || cible.tagName === 'TEXTAREA'
      || cible.tagName === 'SELECT' || cible.isContentEditable);

    if (e.key === ' ' && !saisie) { espaceEnfonce = true; e.preventDefault(); return; }

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
      e.preventDefault(); annuler(); return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
      e.preventDefault(); enregistrerProjet(); return;
    }
    if (saisie) { return; }

    var touche = e.key.toLowerCase();
    if (RACCOURCIS_OUTILS[touche]) { choisirOutil(RACCOURCIS_OUTILS[touche]); return; }

    if (e.key === '+' || e.key === '=') { zoomer(1.25); }
    else if (e.key === '-') { zoomer(0.8); }
    else if (e.key === '0') { ajusterVue(); }
    else if (e.key === 'Delete' || e.key === 'Backspace') {
      var serie = serieCourante();
      if (serie && serie.points.length) {
        memoriser(); serie.points = [];
        rafraichirSeries(); redessiner();
        message('Série vidée.');
      }
    }
  });

  document.addEventListener('keyup', function (e) {
    if (e.key === ' ') { espaceEnfonce = false; }
  });

  function zoomer(facteur) {
    etat.vue = Vue.zoomerAutour(etat.vue, scene.clientWidth / 2, scene.clientHeight / 2, facteur);
    redessiner();
  }

  /* ================== Projet ================== */

  function enregistrerProjet() {
    if (!etat.image) { message('Rien à enregistrer.', 'alerte'); return; }
    var reperes = {};
    Calibration.ORDRE.forEach(function (cle) {
      var r = etat.reperes[cle];
      reperes[cle] = r ? { px: r.px, py: r.py, valeur: lireNombre(etat.valeurs[cle]) } : null;
    });
    var texte = Projet.serialiser({
      image: etat.imageMeta,
      calibration: { reperes: reperes, logX: etat.logX, logY: etat.logY },
      zone: etat.zone,
      series: etat.series,
      notes: $('notes').value
    });
    telecharger(nomDeBase() + '.digit.json', texte, 'application/json');
    message('Projet enregistré.', 'succes');
  }

  function ouvrirProjet(fichier) {
    var lecteur = new FileReader();
    lecteur.onload = function () {
      var lu;
      try {
        lu = Projet.deserialiser(lecteur.result);
      } catch (erreur) {
        message(erreur.message, 'alerte');
        return;
      }

      etat.series = lu.series.map(function (s) {
        return {
          nom: s.nom, couleurHex: s.couleurHex || COULEURS_SERIE[0],
          points: s.points, masquee: false, detection: s.detection
        };
      });
      etat.serieActive = etat.series.length ? 0 : -1;
      etat.zone = lu.zone;
      etat.exclusions = [];
      etat.notes = lu.notes;
      $('notes').value = lu.notes;

      if (lu.calibration && lu.calibration.reperes) {
        etat.logX = lu.calibration.logX;
        etat.logY = lu.calibration.logY;
        $('log-x').checked = etat.logX;
        $('log-y').checked = etat.logY;
        Calibration.ORDRE.forEach(function (cle) {
          var r = lu.calibration.reperes[cle];
          etat.reperes[cle] = r ? { px: r.px, py: r.py } : null;
          etat.valeurs[cle] = (r && Base.estFini(r.valeur)) ? String(r.valeur) : '';
        });
      }

      rafraichirSeries(); rafraichirZone(); rafraichirCalibration();

      if (lu.image && lu.image.dataURL) {
        chargerDataURL(lu.image.dataURL, lu.image.nom || 'image');
      } else {
        message('Projet chargé sans image : rechargez-la pour redétecter.', 'alerte');
        redessiner();
      }
    };
    lecteur.readAsText(fichier);
  }

  /* ================== Câblage ================== */

  function relier() {
    $('btn-ouvrir-image').addEventListener('click', function () { $('fichier-image').click(); });
    $('lien-ouvrir').addEventListener('click', function () { $('fichier-image').click(); });
    $('fichier-image').addEventListener('change', function (e) {
      chargerFichierImage(e.target.files[0]);
      e.target.value = '';
    });

    $('btn-ouvrir-projet').addEventListener('click', function () { $('fichier-projet').click(); });
    $('fichier-projet').addEventListener('change', function (e) {
      if (e.target.files[0]) { ouvrirProjet(e.target.files[0]); }
      e.target.value = '';
    });
    $('btn-enregistrer-projet').addEventListener('click', enregistrerProjet);

    $('btn-exemple').addEventListener('click', function () {
      if (CFDD.Exemple && CFDD.Exemple.dataURL) {
        chargerDataURL(CFDD.Exemple.dataURL, CFDD.Exemple.nom);
        if (CFDD.Exemple.appliquer) { CFDD.Exemple.appliquer(etat, rafraichirTout); }
      } else {
        message('Exemple non embarqué dans cette copie.', 'alerte');
      }
    });

    $('btn-aide').addEventListener('click', function () { $('dialogue-aide').showModal(); });

    var boutons = document.querySelectorAll('.outil');
    for (var i = 0; i < boutons.length; i++) {
      (function (b) {
        b.addEventListener('click', function () { choisirOutil(b.dataset.outil); });
      })(boutons[i]);
    }

    $('btn-zoom-plus').addEventListener('click', function () { zoomer(1.25); });
    $('btn-zoom-moins').addEventListener('click', function () { zoomer(0.8); });
    $('btn-ajuster').addEventListener('click', ajusterVue);

    $('log-x').addEventListener('change', function () {
      etat.logX = $('log-x').checked; recalculerCalibration();
    });
    $('log-y').addEventListener('change', function () {
      etat.logY = $('log-y').checked; recalculerCalibration();
    });

    $('btn-zone-cadre').addEventListener('click', function () {
      etat.zone = null; rafraichirZone(); majApercuMasque();
    });
    $('btn-zone-effacer').addEventListener('click', function () {
      etat.zone = null; etat.exclusions = [];
      rafraichirZone(); majApercuMasque();
    });

    $('btn-ajouter-serie').addEventListener('click', function () {
      memoriser(); nouvelleSerie(); rafraichirSeries(); redessiner();
    });
    $('btn-supprimer-serie').addEventListener('click', function () {
      if (etat.serieActive < 0) { return; }
      memoriser();
      etat.series.splice(etat.serieActive, 1);
      etat.serieActive = Math.min(etat.serieActive, etat.series.length - 1);
      rafraichirSeries(); redessiner();
    });

    $('couleur-cible').addEventListener('input', function () {
      etat.detection.couleur = $('couleur-cible').value;
      majApercuMasque();
    });
    $('btn-pipette').addEventListener('click', function () { choisirOutil('pipette'); });
    $('btn-palette').addEventListener('click', proposerPalette);

    function relierCurseur(id, cle, etiquette) {
      $(id).addEventListener('input', function () {
        etat.detection[cle] = Number($(id).value);
        $(etiquette).textContent = $(id).value;
        majApercuMasque();
      });
    }
    relierCurseur('tol-chroma', 'tolChroma', 'val-chroma');
    relierCurseur('tol-lum', 'tolLum', 'val-lum');

    ['orientation', 'mode'].forEach(function (id) {
      $(id).addEventListener('change', function () {
        etat.detection[id] = $(id).value;
        /* L'orientation change le tri des composantes : l'aperçu doit suivre. */
        if (id === 'orientation') { majApercuMasque(); }
      });
    });

    $('filtre-trait').addEventListener('change', function () {
      etat.detection.filtreTrait = $('filtre-trait').value;
      majApercuMasque();
    });
    $('combler').addEventListener('input', function () {
      etat.detection.comblerLacunes = Number($('combler').value) || 0;
    });

    $('apercu-mode').addEventListener('change', function () {
      etat.apercuMode = $('apercu-mode').value;
      majApercuMasque();
    });
    $('apercu-opacite').addEventListener('input', function () {
      etat.apercuOpacite = Number($('apercu-opacite').value) / 100;
      $('val-apercu-opacite').textContent = $('apercu-opacite').value;
      redessiner();
    });
    $('apercu-epaissir').addEventListener('change', function () {
      etat.apercuEpaissir = $('apercu-epaissir').checked;
      majApercuMasque();
    });

    [['grille-points', 'points'], ['grille-espacement', 'espacement'],
     ['grille-domaine', 'domaine']].forEach(function (paire) {
      $(paire[0]).addEventListener('input', function () {
        var v = $(paire[0]).value;
        etat.grille[paire[1]] = (paire[1] === 'points') ? (Number(v) || 200) : v;
        rafraichirExport();
      });
      $(paire[0]).addEventListener('change', rafraichirExport);
    });
    [['pas', 'pas'], ['longueur-min', 'longueurMin'],
     ['longueur-max', 'longueurMax'], ['simplification', 'simplification']].forEach(function (paire) {
      $(paire[0]).addEventListener('input', function () {
        etat.detection[paire[1]] = Number($(paire[0]).value) || 0;
        if (paire[1] === 'longueurMin' || paire[1] === 'longueurMax') { majApercuMasque(); }
      });
    });

    $('apercu').addEventListener('change', function () {
      etat.apercu = $('apercu').checked;
      majApercuMasque();
    });
    $('btn-detecter').addEventListener('click', detecter);

    ['format', 'separateur', 'decimales'].forEach(function (id) {
      $(id).addEventListener('input', rafraichirExport);
      $(id).addEventListener('change', rafraichirExport);
    });

    $('btn-telecharger').addEventListener('click', function () {
      var texte = texteExport();
      if (!texte) { message('Calibration incomplète.', 'alerte'); return; }
      var format = $('format').value;
      telecharger(nomDeBase() + '.' + Export.extension(format), texte);
      message('Fichier écrit dans vos téléchargements.', 'succes');
    });

    $('btn-copier').addEventListener('click', function () {
      var texte = texteExport();
      if (!texte) { message('Calibration incomplète.', 'alerte'); return; }
      /*
       * navigator.clipboard exige un contexte sécurisé, ce que file:// n'est
       * pas : d'où la solution de repli par execCommand, encore universelle.
       */
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(texte).then(
          function () { message('Copié dans le presse-papiers.', 'succes'); },
          function () { copierParSelection(texte); });
      } else {
        copierParSelection(texte);
      }
    });

    $('notes').addEventListener('input', function () { etat.notes = $('notes').value; });

    /* Glisser-déposer sur toute la scène. */
    ['dragenter', 'dragover'].forEach(function (nom) {
      scene.addEventListener(nom, function (e) {
        e.preventDefault(); scene.classList.add('glisser');
      });
    });
    ['dragleave', 'drop'].forEach(function (nom) {
      scene.addEventListener(nom, function (e) {
        e.preventDefault(); scene.classList.remove('glisser');
      });
    });
    scene.addEventListener('drop', function (e) {
      var fichiers = e.dataTransfer && e.dataTransfer.files;
      if (!fichiers || !fichiers.length) { return; }
      var f = fichiers[0];
      if (/\.json$/i.test(f.name)) { ouvrirProjet(f); } else { chargerFichierImage(f); }
    });

    /* Collage d'une capture d'écran. */
    document.addEventListener('paste', function (e) {
      var elements = e.clipboardData && e.clipboardData.items;
      if (!elements) { return; }
      for (var i = 0; i < elements.length; i++) {
        if (elements[i].type.indexOf('image/') === 0) {
          chargerFichierImage(elements[i].getAsFile());
          e.preventDefault();
          return;
        }
      }
    });

    window.addEventListener('resize', function () {
      dimensionnerCanevas(); redessiner();
    });
  }

  function copierParSelection(texte) {
    var zone = document.createElement('textarea');
    zone.value = texte;
    zone.style.position = 'fixed';
    zone.style.opacity = '0';
    document.body.appendChild(zone);
    zone.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    document.body.removeChild(zone);
    message(ok ? 'Copié dans le presse-papiers.' : 'Copie refusée par le navigateur : sélectionnez l’aperçu à la main.',
      ok ? 'succes' : 'alerte');
  }

  function rafraichirTout() {
    rafraichirSeries(); rafraichirZone(); rafraichirCalibration();
    majApercuMasque(); redessiner();
  }

  /* ================== Démarrage ================== */

  construireLignesReperes();
  relier();
  choisirOutil('navigation');
  rafraichirSeries();
  rafraichirZone();
  rafraichirCalibration();
  dimensionnerCanevas();
  redessiner();

  /* Exposé pour les essais manuels depuis la console du navigateur. */
  CFDD.app = { etat: etat, redessiner: redessiner, rafraichirTout: rafraichirTout };
})();
