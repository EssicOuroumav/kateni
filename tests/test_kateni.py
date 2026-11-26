import numpy as np
import pandas as pd
import pytest

from kateni.cotes import esperance, lambdas_depuis_cotes, mise, sans_marge
from kateni.equipes import canon
from kateni.live import EtatLive, fraction_restante, predire_live
from kateni.marches import marches, matrice_scores, regler
from kateni.modele import ajuster
from kateni.reglement import gagne, regler_tout
from kateni.stockage import CsvStore, identifiant


def test_marches_somment_a_un():
    p = marches(matrice_scores(1.6, 1.1, -0.06))
    assert sum(p["1N2"].values()) == pytest.approx(1)
    for k, v in p.items():
        if k != "Double chance":
            assert sum(v.values()) == pytest.approx(1), k


def test_fraction_restante_bornes():
    assert fraction_restante(0) == pytest.approx(1)
    assert fraction_restante(95, additionnel_mt2=5) == pytest.approx(0)
    assert fraction_restante(45) < 0.6  # plus de buts en 2e mi-temps


def test_live_fin_de_match_resultat_acquis():
    r = predire_live(1.5, 1.2, EtatLive(minute=95, buts_d=2, buts_e=0, additionnel_mt2=5))
    assert r["marches"]["1N2"]["1"] == pytest.approx(1)
    assert r["marches"]["Ext. marque encore"]["Oui"] == pytest.approx(0)


def test_live_exemple_paris_barcelone():
    r = predire_live(1.6, 1.4, EtatLive(minute=34, buts_d=2, buts_e=0))
    p = r["marches"]
    assert 0.5 < p["1N2"]["1"] < 0.95
    assert "Total buts 1.5" not in p  # ligne déjà dépassée
    assert p["Ext. marque encore"]["Oui"] > p["Dom. marque encore"]["Oui"] * 0.8  # menée -> pousse


def test_rouge_baisse_le_taux():
    a = predire_live(1.5, 1.5, EtatLive(minute=30, buts_d=0, buts_e=0))["restants"]
    b = predire_live(1.5, 1.5, EtatLive(minute=30, buts_d=0, buts_e=0, rouges_d=1))["restants"]
    assert b[0] < a[0] and b[1] > a[1]


def test_mise_nulle_sous_le_seuil():
    assert mise(0.50, 2.0, 50_000)["mise_fcfa"] == 0       # espérance 0 %
    m = mise(0.60, 2.0, 50_000)                            # espérance +20 %
    assert 0 < m["mise_fcfa"] <= 1000                       # plafond 2 % = 1 000 FCFA
    assert esperance(0.6, 2.0) == pytest.approx(0.2)


def test_sans_marge():
    p, marge = sans_marge([2.0, 3.4, 3.8])
    assert sum(p) == pytest.approx(1) and marge > 0


def test_lambdas_depuis_cotes_retrouve_les_probas():
    ld, le = lambdas_depuis_cotes(1.80, 3.80, 4.50, 1.85, 2.00)
    assert ld > le and 2.0 < ld + le < 3.5


def test_alias():
    assert canon("Paris Saint-Germain") == "Paris SG"
    assert canon("Bayern München") == "Bayern Munich"
    assert canon("Barcelona") == "Barcelona"


def test_regler():
    assert regler("1N2", "1", 2, 1) is True
    assert regler("Total buts 2.5", "Plus", 1, 1) is False
    assert regler("Les deux équipes marquent", "Oui", 1, 1) is True
    assert regler("Prochain but", "Dom.", 1, 0) is None
    assert gagne({"marche": "Ext. marque encore", "selection": "Oui", "score_au_pari": "2-0"}, 4, 2) is True
    assert gagne({"marche": "Dom. marque encore", "selection": "Oui", "score_au_pari": "2-0"}, 2, 2) is False


def test_pari_idempotent_et_reglement(tmp_path):
    s = CsvStore(tmp_path / "paris.csv")
    i = identifiant("2026-10-21", "Real Madrid", "RB Leipzig", "1N2", "1", "fictif")
    pari = {"id": i, "date_match": "2026-10-21", "competition": "CL", "dom": "Real Madrid",
            "ext": "RB Leipzig", "marche": "1N2", "selection": "1", "cote": 1.5, "mise_fcfa": 1000,
            "mode": "fictif"}
    assert s.ajouter(pari) is True
    assert s.ajouter(pari) is False  # double clic
    assert len(s.lire()) == 1
    matchs = pd.DataFrame([{"Date": pd.Timestamp("2026-10-21"), "HomeTeam": "Real Madrid",
                            "AwayTeam": "RB Leipzig", "FTHG": 3, "FTAG": 1}])
    assert regler_tout(s, matchs) == 1
    r = s.lire().iloc[0]
    assert r["statut"] == "gagné" and float(r["gain_fcfa"]) == 500


def test_modele_sans_fuite_et_ordre_des_forces():
    rng = np.random.default_rng(0)
    lignes = []
    for k in range(400):
        d, e = ("Fort", "Faible") if k % 2 else ("Faible", "Fort")
        lam = (2.5, 0.6) if d == "Fort" else (0.8, 2.0)
        lignes.append({"Date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=k), "HomeTeam": d, "AwayTeam": e,
                       "FTHG": rng.poisson(lam[0]), "FTAG": rng.poisson(lam[1]), "competition": "PL"})
    df = pd.DataFrame(lignes)
    m = ajuster(df, date_ref=pd.Timestamp("2025-06-01"))
    assert m.date_donnees < pd.Timestamp("2025-06-01")
    assert m.attaque["Fort"] > m.attaque["Faible"]


def test_cote_minimale_coherente_avec_la_decision():
    from kateni.config import MARGE_SUPPOSEE, POIDS_MODELE
    from kateni.cotes import cote_minimale
    for p_mod in (0.2, 0.43, 0.7):
        c = cote_minimale(p_mod)
        def ev(cote):
            p = POIDS_MODELE * p_mod + (1 - POIDS_MODELE) * (1 / cote) / (1 + MARGE_SUPPOSEE)
            return esperance(p, cote)
        assert ev(c + 0.01) >= 0.03 > ev(c - 0.01)   # juste au-dessus : pari ; juste en dessous : non
    assert cote_minimale(0.001) is None


def test_modele_v1_identique_au_moteur_d_origine():
    """kateni/modele_v1.py est une copie fidèle de l'ancien kateni_engine.py (supprimé le 25/11/2026) : ses buts
    attendus, sur les matchs connus au 23/11/2026, sont ceux que donnait l'ancien moteur (relevés avant suppression)."""
    from kateni.donnees import charger_competition
    from kateni.modele_v1 import ajuster_v1
    d = charger_competition("PL")
    m1 = ajuster_v1(d[d["Date"] <= "2026-11-23"])
    assert m1.lambdas("Arsenal", "Chelsea") == pytest.approx((1.8029628277548657, 1.1291197997444895), abs=1e-9)
    assert m1.lambdas("Burnley", "Tottenham") == pytest.approx((1.1247138682893476, 1.7152255805005974), abs=1e-9)


def test_meilleur_modele_par_championnat():
    from kateni.ui import predire
    assert "origine" in predire({"competition": "PL", "dom": "Arsenal", "ext": "Chelsea"})[3]
    assert "global" in predire({"competition": "LIGA", "dom": "Barcelona", "ext": "Real Madrid"})[3]
    assert "global" in predire({"competition": "CL", "dom": "Paris SG", "ext": "Barcelona"})[3]


def test_maj_europe_ne_vide_jamais_le_calendrier(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("me", "scripts/maj_europe.py")
    me = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(me)
    (tmp_path / "a_venir.csv").write_text("competition,Date,HomeTeam,AwayTeam\nCL,2026-11-03,A,B\n")
    (tmp_path / "buts_minutes.csv").write_text("minute\n" + "10\n" * 5)
    monkeypatch.setattr(me, "RACINE", tmp_path)

    def refus(titre):
        raise OSError("HTTP Error 429: Too Many Requests")
    monkeypatch.setattr(me, "wikitexte", refus)
    me.main()
    assert "A,B" in (tmp_path / "a_venir.csv").read_text()          # calendrier conservé
    assert len((tmp_path / "buts_minutes.csv").read_text().splitlines()) == 6  # minutes conservées


def test_calibration_renforce_le_favori_et_garde_les_sommes():
    from kateni.marches import calibrer
    p = marches(matrice_scores(2.4, 0.8, -0.06))
    c = calibrer(p)
    assert c["1N2"]["1"] > p["1N2"]["1"]                       # favori plus probable
    assert sum(c["1N2"].values()) == pytest.approx(1)
    assert c["1N2"]["N"] / c["1N2"]["2"] == pytest.approx(p["1N2"]["N"] / p["1N2"]["2"])  # proportions gardées
    assert c["Double chance"]["12"] == pytest.approx(c["1N2"]["1"] + c["1N2"]["2"])
    assert c["Total buts 2.5"] == p["Total buts 2.5"]          # autres marchés inchangés


def test_calendrier_heure_abidjan_et_sans_doublon(tmp_path):
    from datetime import date
    from kateni.calendrier import charger
    # Même match dans football-data (avec cotes) et dans le calendrier de saison : gardé une fois, avec les cotes
    (tmp_path / "a_venir_championnats.csv").write_text(
        "competition,Date,Heure_UK,HomeTeam,AwayTeam,B365H,B365D,B365A\nLIGA,2026-10-21,19:00,Levante,Ath Bilbao,3.4,3.5,2.15\n")
    (tmp_path / "calendrier_saison.csv").write_text(
        "competition,DateUtc,HomeTeam,AwayTeam\nLIGA,2026-10-21 18:00:00Z,Levante UD,Athletic Club\n"
        "PL,2026-10-31 15:00:00Z,Arsenal,Spurs\n")
    # C1 : 18:45 à Paris le 21/10 (heure d'été) puis le 04/11 (heure d'hiver)
    (tmp_path / "a_venir.csv").write_text(
        "competition,Date,Heure_CET,HomeTeam,AwayTeam\nCL,2026-10-21,18:45,Como,Manchester United\n"
        "CL,2026-11-04,18:45,Lille,Galatasaray\n")
    c = charger(tmp_path, depuis=date(2026, 10, 20))
    levante = c[c.dom == "Levante"]
    assert len(levante) == 1 and levante.iloc[0].source == "football-data" and levante.iloc[0].Heure == "18:00"
    assert c[c.dom == "Como"].iloc[0].Heure == "16:45"       # Paris heure d'été = Abidjan + 2 h
    assert c[c.dom == "Lille"].iloc[0].Heure == "17:45"      # Paris heure d'hiver = Abidjan + 1 h
    assert c[c.dom == "Arsenal"].iloc[0].ext == "Tottenham"  # nom de la nouvelle source relié


def test_cotes_pinnacle_rattachees_au_calendrier(tmp_path):
    from datetime import date
    from kateni.calendrier import charger
    (tmp_path / "a_venir.csv").write_text("competition,Date,Heure_CET,HomeTeam,AwayTeam\nCL,2026-10-21,18:45,Como,Manchester United\n")
    (tmp_path / "cotes_pinnacle.csv").write_text(
        "competition,DateUtc,HomeTeam,AwayTeam,B365H,B365D,B365A,B365>2.5,B365<2.5,BTTS_oui,BTTS_non,bookmaker\n"
        "CL,2026-10-21T16:45:00.000Z,Como 1907,Manchester United,2.46,3.8,2.79,1.558,2.52,1.48,2.78,Pinnacle\n")
    r = charger(tmp_path, depuis=date(2026, 10, 20)).iloc[0]
    assert r.dom == "Como" and r.bookmaker == "Pinnacle" and float(r.B365H) == 2.46


def test_evenements_classes_et_coherents():
    from kateni.affichage import evenements, pronostic
    m = {"competition": "CL", "dom": "Como", "ext": "Man United", "date": "2026-10-21"}
    e = evenements(m, pronostic(m, {"B365H": 2.46, "B365D": 3.8, "B365A": 2.79, "B365>2.5": 1.558,
                                    "B365<2.5": 2.52, "bookmaker": "Pinnacle"}))
    assert list(e["Chance"]) == sorted(e["Chance"], reverse=True)          # du plus probable au moins probable
    c = dict(zip(e["Événement"], e["Chance"]))
    assert c["Résultat : Como gagne"] + c["Résultat : match nul"] + c["Résultat : Man United gagne"] == pytest.approx(1)
    assert c["Nombre de buts : plus de 2,5"] + c["Nombre de buts : moins de 2,5"] == pytest.approx(1)
    assert c["Double chance : Como ou nul"] == pytest.approx(c["Résultat : Como gagne"] + c["Résultat : match nul"])
    assert c["Como marque"] + c["Como ne marque pas"] == pytest.approx(1)


def test_rattachement_strict_des_cotes(tmp_path):
    from datetime import date
    from kateni.calendrier import charger, ressemblance
    assert ressemblance("Arsenal FC", "Arsenal") == 1.0
    assert ressemblance("Manchester City", "Man United") < 0.75      # pas de confusion entre les deux Manchester
    (tmp_path / "calendrier_saison.csv").write_text(
        "competition,DateUtc,HomeTeam,AwayTeam\nPL,2026-10-24 11:30:00Z,Aston Villa,Man City\n"
        "PL,2026-10-24 14:00:00Z,Man Utd,Brighton\n")
    (tmp_path / "cotes_pinnacle.csv").write_text(
        "competition,DateUtc,HomeTeam,AwayTeam,B365H,B365D,B365A,B365>2.5,B365<2.5,BTTS_oui,BTTS_non,bookmaker,releve\n"
        "PL,2026-10-24T11:30:00.000Z,Aston Villa FC,Manchester City FC,3.9,3.9,1.9,1.7,2.2,1.6,2.3,Pinnacle,2026-10-24 10:45\n"
        "PL,2026-10-24T14:00:00.000Z,Chelsea FC,Arsenal FC,2.5,3.3,2.9,1.8,2.0,1.7,2.1,Pinnacle,2026-10-24 13:00\n")
    c = charger(tmp_path, depuis=date(2026, 10, 23)).set_index("dom")
    assert c.loc["Aston Villa", "bookmaker"] == "Pinnacle" and float(c.loc["Aston Villa", "B365A"]) == 1.9
    assert c.loc["Aston Villa", "releve"] == "2026-10-24 10:45"
    assert pd.isna(c.loc["Man United", "B365H"])                      # Chelsea–Arsenal ne se rattache à rien


def test_rythme_du_budget_oddspapi():
    import importlib.util
    from datetime import datetime, timezone
    spec = importlib.util.spec_from_file_location("mc", "scripts/maj_cotes.py")
    mc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mc)
    jour10 = datetime(2026, 10, 10, tzinfo=timezone.utc)                # 10/31 du mois -> rythme ≈ 74 + 10
    assert mc.dans_le_rythme(60, jour10) and not mc.dans_le_rythme(100, jour10)


def test_corners_marches_et_live():
    from kateni.corners import marches_corners
    p = marches_corners(5.5, 4.5)
    assert abs(p["Corners total 9.5"]["Plus"] + p["Corners total 9.5"]["Moins"] - 1) < 1e-9
    assert p["Corners total 8.5"]["Plus"] > p["Corners total 9.5"]["Plus"] > p["Corners total 10.5"]["Plus"]
    assert p["Corners Dom. 4.5"]["Plus"] > p["Corners Ext. 4.5"]["Plus"]
    # live : 9 corners déjà à la 80e -> « plus de 8,5 » déjà joué, n'apparaît plus ; « plus de 9,5 » probable
    live = marches_corners(5.5, 4.5, 5, 4, 0.15)
    assert "Corners total 8.5" not in live and live["Corners total 9.5"]["Plus"] > 0.5
    assert marches_corners(5.5, 4.5, 0, 0, 0.0) == {}


def test_reglement_corners():
    p = {"marche": "Corners total 9.5", "selection": "Plus"}
    assert gagne(p, 1, 0, 6, 4) is True
    assert gagne(p, 1, 0, 5, 4) is False
    assert gagne(p, 1, 0) is None  # corners pas encore publiés
    assert gagne({"marche": "Corners Ext. 4.5", "selection": "Moins"}, 0, 0, 9, 3) is True


def test_terrain_neutre():
    from kateni.modele import terrain_neutre
    assert terrain_neutre("CL", "2027-05-29") and terrain_neutre("EL", "2027-05-19")
    assert not terrain_neutre("CL", "2027-05-05") and not terrain_neutre("PL", "2027-05-29")


def test_cotes_imminentes_releve_seulement_les_matchs_proches(monkeypatch):
    from datetime import datetime, timedelta, timezone
    import kateni.pinnacle as pin
    import kateni.ui as ui
    appels = []
    monkeypatch.setattr(pin, "cle", lambda secrets=None: "cle-de-test")
    monkeypatch.setattr(pin, "compte", lambda k: (10, 250))
    monkeypatch.setattr(pin, "relever", lambda codes, *a, **kw: (appels.append(codes) or ([{"x": 1}], codes, 1)))
    monkeypatch.setattr(pin, "enregistrer", lambda *a: None)
    ui._essais_cotes()["derniers"].clear()
    now = datetime.now(timezone.utc)
    def ligne(comp, dans, releve):
        t = now + dans
        return {"competition": comp, "Date": f"{t:%Y-%m-%d}", "Heure": f"{t:%H:%M}", "releve": releve}
    vieux = f"{now - timedelta(hours=5):%Y-%m-%d %H:%M}"
    frais = f"{now - timedelta(minutes=10):%Y-%m-%d %H:%M}"
    cal = pd.DataFrame([ligne("CL", timedelta(minutes=40), vieux),    # proche, cote ancienne -> relevé
                        ligne("PL", timedelta(hours=3), vieux),        # trop loin
                        ligne("LIGA", timedelta(minutes=40), frais)])  # cote déjà fraîche
    assert ui.cotes_imminentes(cal) is True and appels == [["CL"]]
    assert ui.cotes_imminentes(cal) is False and len(appels) == 1  # pas deux relevés dans la demi-heure


def test_combine_reglement_perdu_des_qu_une_selection_rate(tmp_path):
    from kateni.combine import ecrire_selections, lire_selections
    s = CsvStore(tmp_path / "paris.csv")
    sel = [{"date_match": "2026-10-22", "competition": "EL", "dom": "Lech Poznan", "ext": "Sunderland",
            "marche": "Dom. marque", "selection": "Oui", "statut": "en attente"},
           {"date_match": "2026-10-22", "competition": "EL", "dom": "Ararat-Armenia", "ext": "AZ Alkmaar",
            "marche": "Dom. marque", "selection": "Oui", "statut": "en attente"},
           {"date_match": "2026-10-25", "competition": "PL", "dom": "Arsenal", "ext": "Chelsea",
            "marche": "1N2", "selection": "1", "statut": "en attente"}]
    pari = {"id": "c1", "date_match": "2026-10-25", "dom": "Combiné (3)", "ext": "", "type": "combiné",
            "marche": "Combiné", "selection": "3 sélections", "cote": 5.0, "mise_fcfa": 1000, "mode": "réel",
            "selections": ecrire_selections(sel)}
    assert s.ajouter(pari)
    matchs = pd.DataFrame([{"Date": pd.Timestamp("2026-10-22"), "HomeTeam": "Lech Poznan", "AwayTeam": "Sunderland",
                            "FTHG": 1, "FTAG": 1}])
    assert regler_tout(s, matchs) == 0                       # 1 gagnée, les autres pas jouées : en attente
    r = s.lire().iloc[0]
    assert r["statut"] == "en attente" and lire_selections(r["selections"])[0]["statut"] == "gagné"
    matchs.loc[1] = [pd.Timestamp("2026-10-22"), "Ararat-Armenia", "AZ Alkmaar", 0, 4]
    assert regler_tout(s, matchs) == 1                       # Ararat ne marque pas : perdu sans attendre Arsenal
    r = s.lire().iloc[0]
    assert r["statut"] == "perdu" and float(r["gain_fcfa"]) == -1000


def test_combine_meme_match_calcule_ensemble():
    from kateni.combine import chance_combine
    from kateni.marches import matrice_scores
    mat = matrice_scores(1.5, 1.0, 0.0)
    r = {"mat": mat, "p1n2": (0.45, 0.27, 0.28), "plus25": 0.5, "p": {}}
    pron = lambda m: r  # noqa: E731
    a = {"date_match": "d", "competition": "X", "dom": "A", "ext": "B", "marche": "Total buts 4.5", "selection": "Moins"}
    b = {**a, "marche": "Ext. marque", "selection": "Oui"}
    i, j = np.indices(mat.shape)
    attendu = mat[(i + j < 5) & (j > 0)].sum() / mat.sum()
    assert abs(chance_combine([a, b], pron) - attendu) < 1e-9
    autre = {**a, "dom": "C", "ext": "D", "marche": "1N2", "selection": "1"}
    assert abs(chance_combine([a, b, autre], pron) - attendu * 0.45) < 1e-9


def test_minute_estimee_depuis_le_coup_d_envoi():
    from kateni.live import minute_estimee
    assert minute_estimee(10) == (10, "10e minute")
    assert minute_estimee(50) == (45, "mi-temps")
    assert minute_estimee(80) == (63, "63e minute")
    assert minute_estimee(112)[0] == 90


def test_statistiques_marches_et_reglement():
    from kateni.statistiques import marches_stat, plus_grand_nombre
    pg = plus_grand_nombre(16.0, 12.0, 19.0)
    assert abs(sum(pg.values()) - 1) < 1e-9 and pg["1"] > pg["2"] > pg["N"]
    p = marches_stat("Tirs", 16.0, 12.0)
    assert p["Tirs total 23.5"]["Plus"] > p["Tirs total 29.5"]["Plus"]
    stats = {"Tirs": (15, 9), "Tirs cadrés": (5, 2), "Fautes": (10, 13)}
    assert gagne({"marche": "Tirs plus grand nombre", "selection": "1"}, 0, 0, None, None, stats) is True
    assert gagne({"marche": "Tirs cadrés total 6.5", "selection": "Plus"}, 0, 0, None, None, stats) is True
    assert gagne({"marche": "Fautes Ext. 12.5", "selection": "Moins"}, 0, 0, None, None, stats) is False
    assert gagne({"marche": "Corners plus grand nombre", "selection": "N"}, 0, 0, 5, 5, stats) is True
    assert gagne({"marche": "Tirs total 23.5", "selection": "Plus"}, 0, 0) is None


def test_scores_direct_et_statistiques_live():
    from kateni.scores_direct import matchs_de, minute_de
    from kateni.statistiques import marches_stat_live
    assert minute_de({"type": {"name": "STATUS_HALFTIME"}}) == (45, "mi-temps")
    assert minute_de({"type": {"name": "STATUS_IN_PROGRESS"}, "displayClock": "45'+2'"}) == (45, "45'+2'")
    eq = lambda i, n, buts, st: {"homeAway": n, "score": buts, "team": {"id": i, "displayName": n},  # noqa: E731
                                 "statistics": [{"name": k, "displayValue": v} for k, v in st.items()]}
    donnees = {"events": [{"status": {"type": {"state": "in", "name": "STATUS_IN_PROGRESS"}, "displayClock": "17'"},
                           "competitions": [{"competitors": [eq("1", "home", "1", {"wonCorners": "3", "totalShots": "5"}),
                                                             eq("2", "away", "0", {"wonCorners": "1", "totalShots": "2"})],
                                             "details": [{"redCard": True, "team": {"id": "2"}}]}]}]}
    m = matchs_de("PL", donnees)[0]
    assert (m["buts_d"], m["buts_e"], m["minute"], m["rouges_e"]) == (1, 0, 17, 1)
    assert m["stats"] == {"Tirs": (5, 2)}  # corners retirés de l'app (07/11/2026)
    p = marches_stat_live("Tirs", 12.0, 10.0, 5, 2, 0.8)
    assert "Tirs Dom. 4.5" not in p and p["Tirs plus grand nombre"]["1"] > p["Tirs plus grand nombre"]["2"]
    assert marches_stat_live("Tirs", 12.0, 10.0, 5, 2, 0.0) == {}


def test_marches_retires_et_une_des_deux_gagne():
    from kateni.affichage import EVENEMENTS
    from kateni.combine import CHOIX_PARIS
    from kateni.statistiques import marches_stat
    from kateni.ui import libelle
    for liste in (EVENEMENTS, CHOIX_PARIS):
        assert not any(m.startswith(("Corners", "Fautes")) for m, _ in liste)
        assert ("Tirs plus grand nombre", "N") not in liste
    assert "N" not in marches_stat("Tirs", 12.0, 10.0)["Tirs plus grand nombre"]
    assert "N" in marches_stat("Tirs cadrés", 4.0, 3.0)["Tirs cadrés plus grand nombre"]
    assert libelle("Double chance", "12", "Roma", "Cagliari") == "Une des deux équipes gagne (Roma ou Cagliari)"


def test_basket_modele_et_marches():
    import pandas as pd
    from kateni.basket import ajuster, libelle, marches
    # Ligue fictive : A bat toujours B de 10 points, chez lui comme ailleurs
    lignes = []
    for k in range(40):
        dom, ext = ("A", "B") if k % 2 == 0 else ("B", "A")
        pa, pb = 110, 100
        lignes.append({"ligue": "NBA", "DateUtc": f"2025-01-{1 + k % 28:02d} 01:00:00Z", "HomeTeam": dom,
                       "AwayTeam": ext, "HPTS": pa if dom == "A" else pb, "APTS": pb if dom == "A" else pa,
                       **{f"H{q}": 25 for q in range(1, 5)}, **{f"A{q}": 25 for q in range(1, 5)}})
    m = ajuster(pd.DataFrame(lignes), date_ref="2025-02-01", rappel=0.1)
    a, b = m.points("A", "B", "NBA", neutre=True)
    assert abs((a - b) - 10) < 1 and abs((a + b) - 210) < 1
    p = marches(a, b, 12.0, 18.0)
    assert abs(sum(p["Vainqueur"].values()) - 1) < 1e-9 and p["Vainqueur"]["1"] > 0.7
    assert abs(sum(p["Temps réglementaire"].values()) - 1) < 1e-9
    assert abs(sum(p["Écart final"].values()) - 1) < 0.01
    assert libelle("Match : handicap -5.5", "1", "A", "B") == "Handicap A -5,5"
    assert libelle("Match : handicap -5.5", "2", "A", "B") == "Handicap B +5,5"
    assert libelle("1re mi-temps : total 110.5", "Plus", "A", "B") == "1re mi-temps · Total de points : plus de 110,5"


def test_basket_equipe_connue_des_5_vrais_matchs():
    """Une équipe qui a joué 6 matchs il y a quelques semaines est connue (avant : 6 matchs « pondérés par l'âge »
    pesaient moins de 5, et toute l'EuroCup de début de saison restait sans pronostic)."""
    import pandas as pd
    from kateni.basket import ajuster
    lignes = [{"ligue": "EuroCup", "DateUtc": f"2026-10-{1 + 4 * k:02d} 19:00:00Z", "HomeTeam": "A" if k % 2 else "B",
               "AwayTeam": "B" if k % 2 else "A", "HPTS": 80, "APTS": 75,
               **{f"H{q}": 20 for q in range(1, 5)}, **{f"A{q}": 19 for q in range(1, 5)}} for k in range(6)]
    m = ajuster(pd.DataFrame(lignes), date_ref="2026-11-11")
    assert m.n_matchs["A"] < 5 and m.connait("A") and m.connait("B")
    m4 = ajuster(pd.DataFrame(lignes[:4]), date_ref="2026-11-11")
    assert not m4.connait("A")


def test_correction_les_deux_marquent():
    from kateni.marches import calibrer, marches, matrice_scores
    brut = marches(matrice_scores(2.2, 1.9, -0.06))
    corr = calibrer(brut)
    b, c = brut["Les deux équipes marquent"]["Oui"], corr["Les deux équipes marquent"]["Oui"]
    assert b > 0.6 and c < b  # un « oui » très probable est ramené vers le bas
    assert abs(sum(corr["Les deux équipes marquent"].values()) - 1) < 1e-9
    assert corr["Total buts 2.5"] == brut["Total buts 2.5"]  # les buts ne sont pas touchés


def test_mi_temps_foot():
    from kateni.marches import mi_temps
    p = mi_temps(1.8, 1.0)
    assert abs(sum(p["Mi-temps 1N2"].values()) - 1) < 1e-6
    assert p["Mi-temps 1N2"]["1"] > p["Mi-temps 1N2"]["2"]
    assert p["Mi-temps 1N2"]["N"] > 0.3  # à la pause, l'égalité est fréquente
    assert p["Mi-temps total 0.5"]["Plus"] > p["Mi-temps total 1.5"]["Plus"]


def test_sentinelle_repere_un_championnat_bloque_sans_fausse_alerte():
    from datetime import date
    from kateni.sentinelle import verifier
    jours = pd.date_range("2025-08-02", "2026-11-23", freq="7D")  # un championnat qui joue chaque samedi
    lignes = [{"competition": c, "Date": d} for c in ("AAA", "BBB", "CCC") for d in jours]
    df = pd.DataFrame(lignes)
    ok = verifier(df, aujourd_hui=date(2026, 11, 24))
    assert ok["alertes"] == [] and not ok["treve"]
    bloque = df[~((df["competition"] == "AAA") & (df["Date"] > "2026-11-01"))]  # AAA ne reçoit plus rien
    r = verifier(bloque, aujourd_hui=date(2026, 11, 24))
    assert [a["championnat"] for a in r["alertes"]] == ["AAA"]
    tous = df[df["Date"] <= "2026-11-01"]  # tout le monde s'arrête : trêve, pas de panne
    assert verifier(tous, aujourd_hui=date(2026, 11, 24))["alertes"] == []


def test_coupon_reconnait_matchs_paris_et_cotes():
    from kateni.coupon import cote_totale_lue, reconnaitre, verdict
    cal = pd.DataFrame([{"competition": "CL", "Date": "2026-11-24", "Heure": "17:45", "dom": "Bodo/Glimt", "ext": "LASK"},
                        {"competition": "CL", "Date": "2026-11-24", "Heure": "20:00", "dom": "Galatasaray", "ext": "Aston Villa"},
                        {"competition": "PL", "Date": "2026-11-28", "Heure": "16:00", "dom": "Arsenal", "ext": "Chelsea"}])
    texte = """Mon coupon
Bodo/Glimt 1,45
Résultat du match
Bodo/Glimt - LASK
Galatasaray ou Nul 1,62
Double chance
Galatasaray - Aston Villa
Plus de 2,5 buts 1,80
Nombre total de buts
Arsenal - Chelsea
Cote totale 4,23
"""
    r = reconnaitre(texte, cal)
    assert [(x["i_cal"], x["marche"], x["selection"], x["cote"]) for x in r] == [
        (0, "1N2", "1", 1.45), (1, "Double chance", "1N", 1.62), (2, "Total buts 2.5", "Plus", 1.80)]
    assert cote_totale_lue(texte) == 4.23
    assert verdict(0.8)[0] == "Solide" and verdict(0.5)[0] == "Risqué"


TEXTE_BETCLIC_CI = """5 sélections eee
Simple Combiné Systeme
© Slavia Prague - Villarreal X
+ de 1,5 1 16
Nombre total de buts (t. rég)
, €) Atlético Madrid - Viking FK x
Atlético Madrid ou Nul 1.02
Double chance (t. rég)
, @) Club Bruges - Liverpool x
+de2,5 1.30
Nombre total de buts (t. rég)
©) Inter Milan - Stuttgart x
Oui
Les 2 équipes marquent (t. rég) 1,47
© Lille - Bayern Munich X
Bayern Munich 163
Résultat du match (t. rég) ,
Mise F 3,69
"""


def test_coupon_vrai_format_betclic_ci():
    """Vrai coupon Betclic CI (25/11/2026) : le match est écrit AVANT le pari et la cote ; cotes parfois lues « 1 16 »."""
    from kateni.coupon import reconnaitre
    cal = pd.DataFrame([
        {"competition": "CL", "Date": "2026-11-25", "dom": "Slavia Prague", "ext": "Villarreal", "HomeTeam": "Slavia Prague", "AwayTeam": "Villarreal"},
        {"competition": "CL", "Date": "2026-11-25", "dom": "Ath Madrid", "ext": "Viking", "HomeTeam": "Atlético Madrid", "AwayTeam": "Viking"},
        {"competition": "CL", "Date": "2026-11-25", "dom": "Club Brugge", "ext": "Liverpool", "HomeTeam": "Club Brugge", "AwayTeam": "Liverpool"},
        {"competition": "CL", "Date": "2026-11-25", "dom": "Inter", "ext": "Stuttgart", "HomeTeam": "Inter Milan", "AwayTeam": "VfB Stuttgart"},
        {"competition": "CL", "Date": "2026-11-25", "dom": "Lille", "ext": "Bayern Munich", "HomeTeam": "Lille", "AwayTeam": "Bayern Munich"}])
    from kateni.coupon import cote_totale_lue
    assert cote_totale_lue(TEXTE_BETCLIC_CI) == 3.69  # « Mise F 3,69 » : la cote totale, jamais celle d'un pari
    r = reconnaitre(TEXTE_BETCLIC_CI, cal)
    assert [(x["i_cal"], x["marche"], x["selection"], x["cote"]) for x in r] == [
        (0, "Total buts 1.5", "Plus", 1.16), (1, "Double chance", "1N", 1.02), (2, "Total buts 2.5", "Plus", 1.30),
        (3, "Les deux équipes marquent", "Oui", 1.47), (4, "1N2", "2", 1.63)]


def test_coupon_basket_chances_reglement_et_lecture():
    from kateni.basket import ajuster, chance_selection, marches, pari_lu, regler_selection
    from kateni.coupon import reconnaitre
    lignes = []
    for k in range(40):  # A bat B de 10 points, total 210
        dom, ext = ("A", "B") if k % 2 == 0 else ("B", "A")
        lignes.append({"ligue": "NBA", "DateUtc": f"2025-01-{1 + k % 28:02d} 01:00:00Z", "HomeTeam": dom, "AwayTeam": ext,
                       "HPTS": 110 if dom == "A" else 100, "APTS": 100 if dom == "A" else 110,
                       **{f"H{q}": 25 for q in range(1, 5)}, **{f"A{q}": 25 for q in range(1, 5)}})
    m = ajuster(pd.DataFrame(lignes), date_ref="2025-02-01", rappel=0.1)
    s = {"dom": "A", "ext": "B", "competition": "NBA"}
    a, b = m.points("A", "B", "NBA")
    v = marches(a, b, *m.ecarts_types("NBA"))["Vainqueur"]["1"]
    assert chance_selection(m, {**s, "marche": "Basket Vainqueur", "selection": "1"}) == pytest.approx(v)
    p_plus = chance_selection(m, {**s, "marche": "Basket Total", "selection": "Plus", "ligne": 200.5})
    p_moins = chance_selection(m, {**s, "marche": "Basket Total", "selection": "Moins", "ligne": 200.5})
    assert p_plus > 0.5 and p_plus + p_moins == pytest.approx(1)
    h1 = chance_selection(m, {**s, "marche": "Basket Handicap", "selection": "1", "ligne": -5.5})
    h2 = chance_selection(m, {**s, "marche": "Basket Handicap", "selection": "2", "ligne": 5.5})
    assert h1 + h2 == pytest.approx(1)
    assert regler_selection({"marche": "Basket Handicap", "selection": "1", "ligne": -5.5}, 110, 100) is True
    assert regler_selection({"marche": "Basket Total", "selection": "Moins", "ligne": 221.5}, 110, 110) is True
    assert regler_selection({"marche": "Basket Points Ext.", "selection": "Plus", "ligne": 100.0}, 110, 100) is None
    assert pari_lu("+ de 221,5 1,85\nNombre total de points", "Boston Celtics", "Miami Heat") == ("Basket Total", "Plus", 221.5)
    assert pari_lu("Boston Celtics 1,40\nFace à face (prolongations incluses)", "Boston Celtics", "Miami Heat") == (
        "Basket Vainqueur", "1", None)
    cal = pd.DataFrame([{"sport": "basket", "competition": "NBA", "Date": "2026-11-26", "dom": "Boston Celtics",
                         "ext": "Miami Heat", "HomeTeam": "Boston Celtics", "AwayTeam": "Miami Heat"}])
    r = reconnaitre("2 sélections\nBoston Celtics - Miami Heat x\n+ de 221,5 1,85\nNombre total de points\n", cal)
    assert [(x["marche"], x["selection"], x["ligne"], x["cote"]) for x in r] == [("Basket Total", "Plus", 221.5, 1.85)]


def test_coupon_noms_courts_et_traits_d_union():
    """Coupon Betclic CI du 26/11/2026 : « Ajax Amsterdam » = « Ajax », « Brann-Bergen - AGF Aarhus » = Brann – Aarhus."""
    from kateni.coupon import reconnaitre
    cal = pd.DataFrame([
        {"competition": "ECL", "Date": "2026-11-26", "dom": "Kairat", "ext": "Mjallby", "HomeTeam": "Kairat", "AwayTeam": "Mjällby AIF"},
        {"competition": "ECL", "Date": "2026-11-26", "dom": "Ajax", "ext": "Thun", "HomeTeam": "Ajax", "AwayTeam": "Thun"},
        {"competition": "ECL", "Date": "2026-11-26", "dom": "Brann", "ext": "Aarhus", "HomeTeam": "Brann", "AwayTeam": "AGF"},
        {"competition": "ECL", "Date": "2026-12-17", "dom": "CSKA Sofia", "ext": "Thun", "HomeTeam": "CSKA Sofia", "AwayTeam": "Thun"}])
    texte = """3 sélections
Simple Combiné Systeme
© Kairat Almaty - Mjallby AIF X
- de 2,5 1.89
Nombre total de buts (t. rég) ,
© Ajax Amsterdam - FC Thun X
Non 2,08
Les 2 équipes marquent (t. rég)
© Brann-Bergen - AGF Aarhus X
Brann-Bergen 2,10
Résultat du match (t. rég)
"""
    r = reconnaitre(texte, cal)
    assert [(x["i_cal"], x["marche"], x["selection"], x["cote"]) for x in r] == [
        (0, "Total buts 2.5", "Moins", 1.89), (1, "Les deux équipes marquent", "Non", 2.08), (2, "1N2", "1", 2.10)]
