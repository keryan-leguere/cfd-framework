// Écrit les couleurs et les polices d'un thème dans un .pptx produit par pptxgenjs.
//
// pptxgenjs ne sait pas écrire le jeu de couleurs du thème : les couleurs « de schéma »
// (pres.SchemeColor) retombent sinon sur la palette Office. On remplace donc
// <a:clrScheme> et les polices <a:majorFont>/<a:minorFont> de chaque ppt/theme/*.xml.
// jszip est une dépendance de pptxgenjs : aucune installation de plus.
const fs = require("fs");
const JSZip = require("jszip");

const ORDRE = ["dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4",
  "accent5", "accent6", "hlink", "folHlink"];

const echapper = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");

async function appliquerTheme(fichier, theme) {
  const manque = ORDRE.filter((k) => !/^[0-9A-Fa-f]{6}$/.test(theme.colors[k] || ""));
  if (manque.length) throw new Error(`thème : couleur(s) absente(s) ou invalide(s) ${manque.join(", ")}`);
  const zip = await JSZip.loadAsync(fs.readFileSync(fichier));
  const themes = Object.keys(zip.files).filter((n) => /^ppt\/theme\/theme\d+\.xml$/.test(n));
  if (!themes.length) throw new Error(`${fichier} : aucun ppt/theme/theme*.xml`);
  const schema = `<a:clrScheme name="${echapper(theme.name)}">` +
    ORDRE.map((k) => `<a:${k}><a:srgbClr val="${theme.colors[k].toUpperCase()}"/></a:${k}>`).join("") +
    "</a:clrScheme>";
  for (const nom of themes) {
    let xml = await zip.file(nom).async("string");
    const avant = xml;
    xml = xml.replace(/<a:clrScheme\b[\s\S]*?<\/a:clrScheme>/, schema);
    xml = xml.replace(/(<a:majorFont>\s*<a:latin typeface=")[^"]*"/, `$1${echapper(theme.headFontFace)}"`);
    xml = xml.replace(/(<a:minorFont>\s*<a:latin typeface=")[^"]*"/, `$1${echapper(theme.bodyFontFace)}"`);
    if (xml === avant) throw new Error(`${nom} : jeu de couleurs introuvable`);
    zip.file(nom, xml);
  }
  fs.writeFileSync(fichier, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
}

module.exports = { appliquerTheme };
