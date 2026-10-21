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
    import kateni_engine as origine
    from kateni.donnees import charger_competition
    from kateni.modele_v1 import ajuster_v1
    brut = pd.read_csv("E0_full.csv", parse_dates=["Date"]).dropna(subset=["FTHG", "FTAG", "FTR"])
    f = origine.calculer_forces(brut)
    m1 = ajuster_v1(charger_competition("PL"))
    for h, a in [("Arsenal", "Chelsea"), ("Burnley", "Tottenham")]:
        assert m1.lambdas(h, a) == pytest.approx(origine.calculer_lambdas(h, a, {}, f), abs=1e-9)


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
