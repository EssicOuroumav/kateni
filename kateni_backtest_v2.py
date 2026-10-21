"""
Kateni — Backtest V2 (optimisé, incrémental)
==============================================
Même logique que kateni_backtest.py (aucune fuite de données : chaque match
est prédit avec uniquement l'historique antérieur), mais en une seule passe
sur les données au lieu de recalculer Elo/forces depuis zéro à chaque match.
Nécessaire pour tenir sur de gros volumes (2000+ matchs par championnat).

Usage : identique à kateni_backtest.py
    python3 kateni_backtest_v2.py --csv E0_full.csv --league "Premier League"
"""

import argparse

import pandas as pd
from scipy.stats import poisson

K_FACTOR = 20
HOME_ADVANTAGE_ELO = 100
MAX_GOALS = 8
REGUL_MATCHES_PRIOR = 6
BANKROLL_INITIALE = 50_000
MISE_MAX_PCT = 0.02
MIN_EDGE_PCT = 0.03
MIN_HISTORIQUE = 20

OUTCOME_MAP = {"H": "1", "D": "N", "A": "2"}
COTE_COLONNES = {"1": "B365H", "N": "B365D", "2": "B365A"}


def predire_marches(lambda_home: float, lambda_away: float) -> dict:
    ph = [poisson.pmf(i, lambda_home) for i in range(MAX_GOALS + 1)]
    pa = [poisson.pmf(i, lambda_away) for i in range(MAX_GOALS + 1)]
    p1 = pn = p2 = 0.0
    for i in range(MAX_GOALS + 1):
        for j in range(MAX_GOALS + 1):
            p = ph[i] * pa[j]
            if i > j:
                p1 += p
            elif i == j:
                pn += p
            else:
                p2 += p
    total = p1 + pn + p2
    return {"1": p1 / total, "N": pn / total, "2": p2 / total}


def mise_suggeree(prob: float, cote: float, bankroll: float, kelly_fraction: float = 0.25) -> float:
    b = cote - 1
    edge = prob - (1 / cote)
    if edge < MIN_EDGE_PCT:
        return 0.0
    full_kelly = max(0.0, (b * prob - (1 - prob)) / b)
    pct = min(kelly_fraction * full_kelly, MISE_MAX_PCT)
    return round(pct * bankroll)


def backtest_league(csv_path: str, league_name: str) -> dict:
    df = pd.read_csv(csv_path, parse_dates=["Date"])
    df = df.dropna(subset=["FTHG", "FTAG", "FTR"]).sort_values("Date").reset_index(drop=True)

    elo: dict[str, float] = {}
    buts_marques: dict[str, float] = {}
    buts_encaisses: dict[str, float] = {}
    n_matchs: dict[str, int] = {}

    total_home_goals, total_away_goals, total_matches = 0.0, 0.0, 0

    bankroll = BANKROLL_INITIALE
    n_bets = corrects = n_predictions = 0
    brier_total = 0.0

    for _, row in df.iterrows():
        home, away = row["HomeTeam"], row["AwayTeam"]
        for t in (home, away):
            elo.setdefault(t, 1500.0)
            buts_marques.setdefault(t, 0.0)
            buts_encaisses.setdefault(t, 0.0)
            n_matchs.setdefault(t, 0)

        # --- Prédiction AVANT mise à jour (utilise uniquement l'historique passé) ---
        if total_matches >= MIN_HISTORIQUE:
            avg_home = total_home_goals / total_matches
            avg_away = total_away_goals / total_matches
            moy_ligue = (avg_home + avg_away) / 2

            def force(team, buts, n):
                brut = (buts[team] / n_matchs[team]) / moy_ligue if n_matchs[team] else 1.0
                poids = n_matchs[team] / (n_matchs[team] + REGUL_MATCHES_PRIOR)
                return poids * brut + (1 - poids) * 1.0

            att_home = force(home, buts_marques, n_matchs)
            def_home = force(home, buts_encaisses, n_matchs)
            att_away = force(away, buts_marques, n_matchs)
            def_away = force(away, buts_encaisses, n_matchs)

            lam_home = max(0.1, avg_home * att_home * def_away)
            lam_away = max(0.1, avg_away * att_away * def_home)

            probs = predire_marches(lam_home, lam_away)
            actual = OUTCOME_MAP[row["FTR"]]

            pred_class = max(probs, key=probs.get)
            corrects += int(pred_class == actual)
            brier_total += sum((probs[k] - (1.0 if k == actual else 0.0)) ** 2 for k in probs)
            n_predictions += 1

            for outcome_key, cote_col in COTE_COLONNES.items():
                cote = row.get(cote_col)
                if pd.isna(cote):
                    continue
                stake = mise_suggeree(probs[outcome_key], float(cote), bankroll)
                if stake > 0:
                    gain = stake * (float(cote) - 1) if actual == outcome_key else -stake
                    bankroll += gain
                    n_bets += 1

        # --- Mise à jour APRES la prédiction (Elo + moyennes de buts) ---
        elo_home_eff = elo[home] + HOME_ADVANTAGE_ELO
        exp_home = 1 / (1 + 10 ** ((elo[away] - elo_home_eff) / 400))
        score_home = 1.0 if row["FTR"] == "H" else (0.0 if row["FTR"] == "A" else 0.5)
        delta = K_FACTOR * (score_home - exp_home)
        elo[home] += delta
        elo[away] -= delta

        buts_marques[home] += row["FTHG"]
        buts_marques[away] += row["FTAG"]
        buts_encaisses[home] += row["FTAG"]
        buts_encaisses[away] += row["FTHG"]
        n_matchs[home] += 1
        n_matchs[away] += 1
        total_home_goals += row["FTHG"]
        total_away_goals += row["FTAG"]
        total_matches += 1

    accuracy = corrects / n_predictions if n_predictions else float("nan")
    brier = brier_total / n_predictions if n_predictions else float("nan")
    roi_pct = (bankroll - BANKROLL_INITIALE) / BANKROLL_INITIALE * 100

    return {
        "league": league_name,
        "n_matchs_testes": n_predictions,
        "accuracy_1n2": accuracy,
        "brier_score": brier,
        "n_paris_simules": n_bets,
        "bankroll_finale": round(bankroll),
        "roi_simule_pct": round(roi_pct, 1),
    }


def main():
    parser = argparse.ArgumentParser(description="Kateni — backtest V2 optimisé")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--league", required=True)
    args = parser.parse_args()

    r = backtest_league(args.csv, args.league)
    print(f"\n=== Backtest Kateni V2 — {r['league']} ===")
    print(f"Matchs testés : {r['n_matchs_testes']}")
    print(f"Accuracy 1N2 : {r['accuracy_1n2']*100:.1f}%")
    print(f"Brier score  : {r['brier_score']:.4f}")
    print(f"Paris simulés : {r['n_paris_simules']}")
    print(f"Bankroll : {BANKROLL_INITIALE} FCFA -> {r['bankroll_finale']} FCFA (ROI simulé : {r['roi_simule_pct']}%)")


if __name__ == "__main__":
    main()
