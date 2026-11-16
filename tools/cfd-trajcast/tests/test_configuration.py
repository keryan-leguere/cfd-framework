"""Fichier YAML : clés refusées par leur chemin, chemins relatifs au fichier."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cfd_trajcast.data.configuration import ErreurConfiguration, charger_configuration


def _ecrire(tmp_path: Path, exemple: Path, modif) -> Path:  # type: ignore[no-untyped-def]
    d = yaml.safe_load((exemple / "CONFIG.yaml").read_text(encoding="utf-8"))
    modif(d)
    chemin = tmp_path / "C.yaml"
    chemin.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    return chemin


def test_exemples_se_chargent(exemple: Path) -> None:
    cfg = charger_configuration(exemple / "CONFIG.yaml")
    assert cfg.trajectoire.fichier == exemple / "vol_reference.csv"
    assert cfg.maquette.origine == (19.05, 0.0, 0.0)
    assert [e.nom for e in cfg.trajectoire.evenements][-1] == "Apogée"
    cfg = charger_configuration(exemple / "CONFIG_EULER.yaml")
    assert cfg.trajectoire.declaration.attitude.sequence == "ZYX"
    assert cfg.trajectoire.declaration.x == "n"


@pytest.mark.parametrize(
    ("modif", "motif"),
    [
        (lambda d: d["trajectoire"]["attitude"].update(ordree="wxyz"), r"trajectoire\.attitude : clé\(s\) inconnue\(s\) ordree"),
        (lambda d: d["trajectoire"].pop("attitude"), "jamais déduite de la vitesse"),
        (lambda d: d["trajectoire"].pop("repere"), "obligatoire.*repere"),
        (lambda d: d["maquette"].update(axe_nez="+W"), "axe"),
        (lambda d: d.update(cameras={}), r"configuration : clé\(s\) inconnue\(s\) cameras"),
        (lambda d: d["trajectoire"].update(source="rocketpy"), "inutile"),
        (lambda d: d["trajectoire"]["unites"].update(longueur="pouce"), "unité de longueur"),
        (lambda d: d["video"].update(resolution=[1921, 1080]), "paires"),
        (lambda d: d["video"].update(resolution="8K"), "1080p"),
        (lambda d: d["video"].update(duree=10), "s'excluent"),
        (lambda d: d["video"]["codec"].update(preset="turbo"), "preset"),
        (lambda d: d["vues"]["poursuite"].update(mode="drone"), "mode"),
        (lambda d: d["vues"]["poursuite"].update(elevation=95), r"vues\.poursuite : elevation"),
        (lambda d: d["vues"]["poursuite"].update(zoom=2), "zoom"),
    ],
)
def test_erreurs(tmp_path: Path, exemple: Path, modif, motif: str) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ErreurConfiguration, match=motif):
        charger_configuration(_ecrire(tmp_path, exemple, modif))


def test_plus_de_section_a_venir(exemple: Path) -> None:
    assert charger_configuration(exemple / "CONFIG.yaml").a_venir == ()


def test_video_et_vues(exemple: Path, tmp_path: Path) -> None:
    cfg = charger_configuration(exemple / "CONFIG.yaml")
    assert cfg.video.resolution == (1920, 1080) and cfg.video.ips == 30
    nom, vue = cfg.vues[0]
    assert nom == "poursuite" and vue.distance is None and vue.azimut == 60
    # Sans section video ni vues : valeurs par défaut.
    cfg = charger_configuration(_ecrire(tmp_path, exemple, lambda d: (d.pop("video"), d.pop("vues"))))
    assert cfg.video.resolution == (1920, 1080) and cfg.vues[0][0] == "poursuite"


def test_yaml_invalide(tmp_path: Path) -> None:
    f = tmp_path / "C.yaml"
    f.write_text("trajectoire: [", encoding="utf-8")
    with pytest.raises(ErreurConfiguration, match="YAML invalide"):
        charger_configuration(f)


def _multivues(tmp_path: Path, exemple: Path, modif) -> Path:  # type: ignore[no-untyped-def]
    import shutil

    d = yaml.safe_load((exemple / "CONFIG_MULTIVUES.yaml").read_text(encoding="utf-8"))
    modif(d)
    shutil.copy(exemple / "logo.png", tmp_path / "logo.png")
    chemin = tmp_path / "M.yaml"
    d["trajectoire"]["fichier"] = str(exemple / "vol_reference.csv")
    d["maquette"]["fichier"] = str(exemple / "MAQUETTE" / "Aim9.stl")
    chemin.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    return chemin


def test_multivues_se_charge(exemple: Path) -> None:
    cfg = charger_configuration(exemple / "CONFIG_MULTIVUES.yaml")
    assert [n for n, _ in cfg.vues] == ["poursuite", "sol", "embarquee"]
    assert cfg.disposition.type == "incrustation" and len(cfg.sequence) == 3
    assert cfg.sequence[1].disposition == cfg.disposition and cfg.sequence[1].transition == "fondu"
    assert cfg.telemetrie is not None and cfg.montage.logo is not None and not cfg.remarques


@pytest.mark.parametrize(
    ("modif", "motif"),
    [
        (lambda d: d["disposition"].update(principale="drone"), "vue « drone » inconnue"),
        (lambda d: d.pop("telemetrie"), "section telemetrie manque"),
        (lambda d: d["sequence"][2].update(de=1.0), "strictement croissants"),
        (lambda d: d["sequence"][1].update(transition="volet"), "coupe, fondu"),
        (lambda d: d["vues"]["sol"].pop("position"), "position"),
        (lambda d: d["vues"]["embarquee"].update(visee=[0, 0, 0]), "non nulle"),
        (lambda d: d["telemetrie"].update(grandeurs=[]), "1 à 8"),
        (lambda d: d["telemetrie"].update(grandeurs=["mach"] * 9), "1 à 8"),
        (lambda d: d["telemetrie"].update(grandeurs=["mach", "mach"]), "deux fois"),
        (lambda d: d["telemetrie"]["unites"].update(vitesse="mph"), "km/h"),
        (lambda d: d["telemetrie"].update(grandeurs=[{"colonne": "q0", "grandeur": "mach"}]), "soit"),
        (lambda d: d["telemetrie"].update(grandeurs=[{"grandeur": "pression"}]), "sinon, `colonne`"),
        (lambda d: d["telemetrie"].update(grandeurs=[{"grandeur": "mach", "facteur": 2}]), "facteur"),
        (lambda d: d["telemetrie"].update(grandeurs=[{"grandeur": "altitude", "unite": "mi"}]), "permises"),
        (lambda d: d["telemetrie"].update(grandeurs=[{"colonne": "q0", "decimales": 9}]), "0 à 6"),
        (lambda d: d["telemetrie"].update(grandeurs=[{"colonne": "q0", "couleur": "rouge"}]), "rrggbb"),
        (lambda d: d["telemetrie"].update(grandeurs=[{"colonne": "q0", "plage": [5, 1]}]), "min < max"),
        (lambda d: d["montage"]["logo"].update(fichier="absent.png"), "introuvable"),
        (lambda d: d["montage"].update(fondu=-1), "positive"),
        (lambda d: d["vues"].update(telemetrie={"mode": "poursuite"}), "réservé"),
    ],
)
def test_erreurs_multivues(tmp_path: Path, exemple: Path, modif, motif: str) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ErreurConfiguration, match=motif):
        charger_configuration(_multivues(tmp_path, exemple, modif))


def test_remarques(tmp_path: Path, exemple: Path) -> None:
    def modif(d):  # type: ignore[no-untyped-def]
        d["vues"]["drone"] = {"mode": "poursuite"}
        d.pop("sequence")
        d["disposition"] = {"type": "unique", "principale": "poursuite", "telemetrie": "aucune"}

    cfg = charger_configuration(_multivues(tmp_path, exemple, modif))
    assert any("drone" in r for r in cfg.remarques)
    assert any("sol" in r for r in cfg.remarques)
    assert any("telemetrie" in r for r in cfg.remarques)


def test_ensemble_se_charge(exemple: Path) -> None:
    from cfd_trajcast.core.camera import ParametresEnsemble

    cfg = charger_configuration(exemple / "CONFIG_ENSEMBLE.yaml")
    vues = dict(cfg.vues)
    assert isinstance(vues["ensemble"], ParametresEnsemble) and vues["ensemble"].azimut is None
    assert cfg.disposition.type == "libre" and cfg.montage.position_titre == "haut"
    assert cfg.montage.coin_bandeaux == "haut_gauche" and not cfg.remarques


@pytest.mark.parametrize(("modif", "motif"), [
    (lambda d: d["montage"].update(position_titre="milieu"), "haut, centre, bas"),
    (lambda d: d["montage"].update(coin_bandeaux="gauche"), "coin_bandeaux"),
    (lambda d: d["vues"]["poursuite"].update(mode="ensemble", lissage=1.0), "lissage"),
])
def test_erreurs_ensemble(tmp_path: Path, exemple: Path, modif, motif: str) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ErreurConfiguration, match=motif):
        charger_configuration(_multivues(tmp_path, exemple, modif))


def test_grandeurs_libres(tmp_path: Path, exemple: Path) -> None:
    def modif(d):  # type: ignore[no-untyped-def]
        d["telemetrie"] = {"grandeurs": [
            "mach", "DL",
            {"colonne": "q0", "libelle": "q₀", "unite": "kPa", "facteur": 0.001, "decimales": 1,
             "couleur": "#ff0000", "plage": [0, 80]},
            {"grandeur": "altitude", "unite": "km", "libelle": "Alt."},
        ]}

    g = charger_configuration(_multivues(tmp_path, exemple, modif)).telemetrie.grandeurs  # type: ignore[union-attr]
    assert [x.cle for x in g] == ["mach", "DL", "q0", "altitude"]
    assert g[0].colonne is None and g[1].colonne == "DL" and g[1].unite == ""
    assert (g[2].facteur, g[2].unite, g[2].decimales, g[2].plage) == (0.001, "kPa", 1, (0.0, 80.0))
    assert g[3].libelle == "Alt." and g[3].facteur == pytest.approx(1e-3) and g[3].unite == "km"


def test_ensemble_affiche_les_qoi_de_l_exemple(exemple: Path) -> None:
    g = charger_configuration(exemple / "CONFIG_ENSEMBLE.yaml").telemetrie.grandeurs  # type: ignore[union-attr]
    assert [x.cle for x in g] == ["altitude", "mach", "q0", "incidence_totale", "roulis"]


def test_style_preset_et_surcharges(tmp_path: Path, exemple: Path) -> None:
    def modif(d):  # type: ignore[no-untyped-def]
        d["style"] = {"preset": "conference", "ciel": {"haut": "#000000"}, "sol": {"type": "damier", "maille": 50},
                      "trainee": {"active": True, "jusqu_a": "Apogée", "duree": 3}, "eclairage": {"soleil": [90, 10]},
                      "fusee": {"couleur": "#ff0000", "metal": 0.2}, "trace": True}

    st = charger_configuration(_multivues(tmp_path, exemple, modif)).style
    assert st.preset == "conference" and st.ciel_haut == "#000000" and st.ciel_bas == "#b4d2ec"
    assert (st.sol, st.sol_maille, st.trainee, st.trainee_duree, st.trainee_jusqu_a) == ("damier", 50.0, True, 3.0, "Apogée")
    assert st.soleil == (90.0, 10.0) and st.fusee_couleur == "#ff0000" and st.trace
    assert charger_configuration(exemple / "CONFIG.yaml").style.preset == "sobre"


@pytest.mark.parametrize(("modif", "motif"), [
    (lambda d: d.update(style={"preset": "cinema"}), "sobre, conference"),
    (lambda d: d.update(style={"sol": {"type": "herbe"}}), "grille"),
    (lambda d: d.update(style={"ciel": {"haut": "bleu"}}), "rrggbb"),
    (lambda d: d.update(style={"eclairage": {"soleil": [1, 2, 3]}}), "azimut"),
    (lambda d: d.update(style={"fusee": {"metal": 2}}), "entre 0 et 1"),
    (lambda d: d["video"].update(ralentis=[{"de": 5, "a": 2, "vitesse": 0.5}]), "de < a"),
    (lambda d: d["video"].update(ralentis=[{"de": 1, "a": 5, "vitesse": 0.5}, {"de": 4, "a": 6, "vitesse": 0.5}]), "disjoints"),
    (lambda d: d["video"].update(duree=10, vitesse=None, ralentis=[{"de": 1, "a": 2, "vitesse": 0.5}]), "s'excluent"),
    (lambda d: d["vues"].update(o={"mode": "images_cles", "cles": []}), "au moins|liste"),
    (lambda d: d["vues"].update(o={"mode": "orbite", "elevation": 90}), "elevation"),
])
def test_erreurs_j4(tmp_path: Path, exemple: Path, modif, motif: str) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ErreurConfiguration, match=motif):
        charger_configuration(_multivues(tmp_path, exemple, modif))


def test_virage_se_charge(exemple: Path) -> None:
    from cfd_trajcast.core.camera import ParametresImagesCles, ParametresOrbite

    cfg = charger_configuration(exemple / "CONFIG_VIRAGE.yaml")
    vues = dict(cfg.vues)
    assert isinstance(vues["cinema"], ParametresImagesCles) and len(vues["cinema"].cles) == 6
    assert isinstance(vues["orbite"], ParametresOrbite)
    assert len(cfg.video.ralentis) == 2 and not cfg.style.trainee     # plus de traînée implicite
    assert cfg.propulsion is not None and cfg.propulsion.phases[0].a == "Fin de propulsion"


def test_propulsion(tmp_path: Path, exemple: Path) -> None:
    from cfd_trajcast.data.configuration import JETS

    def modif(d):  # type: ignore[no-untyped-def]
        d["propulsion"] = {
            "tuyeres": [[-1.4, 0.2, 0.0], [-1.4, -0.2, 0.0]], "rayon_tuyere": 0.05, "fondu": 0.5,
            "phases": [
                {"de": 0, "a": "Fin de propulsion", "jet": "fusee_poudre"},
                {"de": "Fin de propulsion", "jet": {"base": "fusee_liquide", "flamme": {"longueur": 30,
                 "couleurs": ["#ffffff", "#0000ff"]}, "fumee": False}},
            ]}

    p = charger_configuration(_multivues(tmp_path, exemple, modif)).propulsion
    assert p is not None and p.tuyeres == ((-1.4, 0.2, 0.0), (-1.4, -0.2, 0.0)) and p.fondu == 0.5
    assert p.phases[0].jet == JETS["fusee_poudre"] and p.phases[0].a == "Fin de propulsion"
    j = p.phases[1].jet
    assert j.fumee is None and j.flamme is not None and j.flamme.longueur == 30
    assert j.flamme.couleurs == ("#ffffff", "#0000ff") and j.flamme.diamants == JETS["fusee_liquide"].flamme.diamants  # type: ignore[union-attr]


@pytest.mark.parametrize(("phases", "motif"), [
    ([{"de": 0, "jet": "turbopropulseur"}], "inconnu"),
    ([{"de": 0, "jet": {"flamme": {"evasement": 80}}}], "evasement"),
    ([{"de": 0, "jet": {"fumee": {"opacite": 2}}}], "opacite"),
    ([{"de": 0, "jet": {"flamme": {"diamants": 50}}}], "0 à 12"),
    ([], "liste"),
])
def test_propulsion_erreurs(tmp_path: Path, exemple: Path, phases: list, motif: str) -> None:  # type: ignore[type-arg]
    with pytest.raises(ErreurConfiguration, match=motif):
        charger_configuration(_multivues(tmp_path, exemple, lambda d: d.update(propulsion={"phases": phases})))


def test_evenements_depuis_un_fichier(tmp_path: Path, exemple: Path) -> None:
    (tmp_path / "evts.csv").write_text("# exporté\nt,nom\n1.5,Allumage\n12,Séparation\n", encoding="utf-8")
    cfg = charger_configuration(_multivues(tmp_path, exemple, lambda d: d["trajectoire"].update(evenements="evts.csv")))
    assert [(e.t, e.nom) for e in cfg.trajectoire.evenements] == [(1.5, "Allumage"), (12.0, "Séparation")]
    with pytest.raises(ErreurConfiguration, match="introuvable"):
        charger_configuration(_multivues(tmp_path, exemple, lambda d: d["trajectoire"].update(evenements="x.csv")))


@pytest.mark.parametrize("nom", ["AVION_MANOEUVRES", "AVION_PANNE", "FUSEE_BI_ETAGE"])
def test_scenarios_se_chargent(exemple: Path, nom: str) -> None:
    from cfd_trajcast.data.constats import ALERTE, ERREUR
    from cfd_trajcast.data.maquette import Maquette
    from cfd_trajcast.data.trajectoire import Trajectoire
    from cfd_trajcast.data.validation import verifier
    from cfd_trajcast.engine.pipeline import Film

    cfg = charger_configuration(exemple / "SCENARIOS" / f"{nom}.yaml")
    ct = cfg.trajectoire
    traj = Trajectoire.depuis_csv(ct.fichier, declaration=ct.declaration, evenements=ct.evenements)
    constats = verifier(traj, Maquette.depuis_declaration(cfg.maquette))
    assert not [c for c in constats if c.niveau in (ALERTE, ERREUR)]
    film = Film.depuis_configuration(cfg)             # événements des phases et de la séquence résolus
    assert film.propulsion is not None and all(isinstance(p.de, float) for p in film.propulsion.phases)
