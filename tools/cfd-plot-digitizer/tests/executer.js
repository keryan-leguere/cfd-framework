#!/usr/bin/env node
/*
 * executer.js — lanceur node de la suite de tests.
 *
 * Charge exactement les mêmes fichiers que tests/index.html : ce qui est validé
 * ici est ce qui tourne dans le navigateur.
 *
 *   node tests/executer.js
 */
'use strict';

var path = require('path');
var racine = path.join(__dirname, '..');

var MODULES = ['00_base', '10_couleur', '20_calibration', '25_trait', '30_detection',
               '40_export', '50_projet', '60_vue'];
var SUITES = ['test_base', 'test_couleur', 'test_calibration', 'test_trait',
              'test_detection', 'test_export', 'test_projet', 'test_vue',
              'test_integration'];

MODULES.forEach(function (m) { require(path.join(racine, 'app', 'js', m + '.js')); });
require(path.join(__dirname, '00_cadre.js'));

/*
 * Ressources des tests d'intégration : figures réelles et valeurs qui ont servi
 * à les tracer. Absentes dans le navigateur, où la suite se désactive d'elle-même.
 */
var fs = require('fs');
var dossierExemples = path.join(racine, 'exemples');
var cheminReference = path.join(dossierExemples, 'reference.json');
if (fs.existsSync(cheminReference)) {
  var lirePNG = require(path.join(__dirname, 'png.js')).lirePNG;
  var reference = JSON.parse(fs.readFileSync(cheminReference, 'utf-8'));
  var images = {};
  Object.keys(reference).forEach(function (nom) {
    images[nom] = lirePNG(path.join(dossierExemples, nom));
  });
  globalThis.CFDD.Tests.ressources = { reference: reference, images: images };
} else {
  console.log('exemples/reference.json absent : tests d’intégration ignorés '
    + '(lancer  python3 exemples/generer_exemples.py)');
}

SUITES.forEach(function (s) { require(path.join(__dirname, s + '.js')); });

var ESC = String.fromCharCode(27);
var couleur = process.stdout.isTTY && !process.env.NO_COLOR;
function teinte(code, texte) {
  return couleur ? (ESC + '[' + code + 'm' + texte + ESC + '[0m') : texte;
}

var echecs = [];
var debut = Date.now();

var bilan = globalThis.CFDD.Tests.executer(function (ev) {
  if (ev.type === 'suite') {
    console.log('');
    console.log(teinte('1;36', ev.nom));
  } else if (ev.type === 'ok') {
    console.log('  ' + teinte('32', 'ok') + '    ' + ev.titre);
  } else if (ev.type === 'echec') {
    echecs.push(ev);
    console.log('  ' + teinte('31', 'ECHEC') + ' ' + ev.titre);
    console.log('        ' + teinte('31', ev.erreur.message));
  }
});

var duree = ((Date.now() - debut) / 1000).toFixed(2);
console.log('');
if (bilan.echecs === 0) {
  console.log(teinte('1;32', bilan.total + ' tests passés') + ' en ' + duree + ' s');
} else {
  console.log(teinte('1;31', bilan.echecs + ' échec(s)') + ' sur ' + bilan.total
    + ' tests, en ' + duree + ' s');
  echecs.forEach(function (e) { console.log('  - ' + e.titre + ' : ' + e.erreur.message); });
}
process.exit(bilan.echecs === 0 ? 0 : 1);
