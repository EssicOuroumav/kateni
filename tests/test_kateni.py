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
