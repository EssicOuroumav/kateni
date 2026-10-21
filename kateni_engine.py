"""
Kateni — Moteur de prédiction V1
=================================
Marchés produits : 1N2, Double Chance, Over/Under 2.5 buts, BTTS.
Méthode : ratings Elo (mis à jour match par match) convertis en force
d'attaque/défense, puis distribution de Poisson bivariée pour tous les marchés.

Données attendues : CSV au format football-data.co.uk
Colonnes minimales : Date, HomeTeam, AwayTeam, FTHG, FTAG, FTR

Usage :
    python3 kateni_engine.py --csv historical_data.csv --home "Man United" --away "Fulham"
"""

import argparse
import math
from dataclasses import dataclass, field

import pandas as pd
from scipy.stats import poisson


# ---------------------------------------------------------------------------
# Configuration (bankroll / staking — cf. kateni_decisions.md)
# ---------------------------------------------------------------------------
BANKROLL_INITIALE = 50_000        # FCFA
MISE_MAX_PCT = 0.02               # plafond dur 2% par pari
MIN_EDGE_PCT = 0.03                # seuil minimum d'edge avant de suggérer une mise (règle Kelly documentée)
STOP_LOSS_PCT = 0.30              # pause déclenchée à -30%
K_FACTOR = 20                     # sensibilité Elo
HOME_ADVANTAGE_ELO = 100          # points Elo bonus à domicile
ELO_TO_GOALS_SCALE = 200.0        # calibration : 200 pts Elo ≈ 1 but d'écart attendu
MAX_GOALS = 8                     # troncature de la distribution de Poisson
REGUL_MATCHES_PRIOR = 6           # nombre de matchs "virtuels" ajoutés à la moyenne de ligue
                                   # (régularisation pour équipes avec peu de matchs joués)


# ---------------------------------------------------------------------------
# 1. Ratings Elo
# ---------------------------------------------------------------------------
def calculer_elo(df: pd.DataFrame) -> dict:
    """Calcule les ratings Elo finaux de chaque équipe à partir de l'historique."""
    ratings: dict[str, float] = {}
    df = df.sort_values("Date")

    for _, row in df.iterrows():
        home, away = row["HomeTeam"], row["AwayTeam"]
        ratings.setdefault(home, 1500.0)
        ratings.setdefault(away, 1500.0)

        elo_home = ratings[home] + HOME_ADVANTAGE_ELO
        elo_away = ratings[away]

        # probabilité de victoire domicile attendue (formule Elo classique)
        exp_home = 1 / (1 + 10 ** ((elo_away - elo_home) / 400))

        if row["FTR"] == "H":
            score_home = 1.0
        elif row["FTR"] == "A":
            score_home = 0.0
        else:
            score_home = 0.5

        delta = K_FACTOR * (score_home - exp_home)
        ratings[home] += delta
        ratings[away] -= delta

    return ratings


def calculer_elo_unifie(csv_paths: list[str]) -> dict:
    """
    Calcule un Elo PARTAGÉ par club, à partir de plusieurs compétitions
    combinées (ex: les 5 championnats domestiques + Champions League +
    Europa League). Un même club conserve un seul rating, mis à jour par
    tous ses matchs quelle que soit la compétition — évite d'avoir un
    rating trop peu fiable calculé sur les seuls 8-16 matchs européens
    d'un club par saison.

    Usage : calculer_elo_unifie(["E0_full.csv", "SP1_full.csv", ..., "CL_full.csv", "EL_full.csv"])
    """
    frames = []
    for path in csv_paths:
        try:
            df = pd.read_csv(path, parse_dates=["Date"])
            frames.append(df[["Date", "HomeTeam", "AwayTeam", "FTR"]].dropna())
        except FileNotFoundError:
            continue
    if not frames:
        return {}
    combine = pd.concat(frames, ignore_index=True)
    return calculer_elo(combine)


# ---------------------------------------------------------------------------
# 2. Force d'attaque / défense (moyennes de buts)
# ---------------------------------------------------------------------------
@dataclass
class StrengthModel:
    avg_home_goals: float
    avg_away_goals: float
    attack: dict = field(default_factory=dict)   # ratio buts marqués / moyenne ligue
    defense: dict = field(default_factory=dict)  # ratio buts encaissés / moyenne ligue


def calculer_forces(df: pd.DataFrame) -> StrengthModel:
    # Utilise le xG (expected goals) quand disponible — signal reconnu comme
    # plus prédictif que les buts bruts — sinon retombe sur les buts réels.
    df = df.copy()
    if "HxG" in df.columns:
        df["_buts_home"] = df["HxG"].fillna(df["FTHG"])
        df["_buts_away"] = df["AxG"].fillna(df["FTAG"])
    else:
        df["_buts_home"] = df["FTHG"]
        df["_buts_away"] = df["FTAG"]

    avg_home_goals = df["_buts_home"].mean()
    avg_away_goals = df["_buts_away"].mean()
    moyenne_ligue_marques = (avg_home_goals + avg_away_goals) / 2

    teams = pd.unique(df[["HomeTeam", "AwayTeam"]].values.ravel())
    model = StrengthModel(avg_home_goals=avg_home_goals, avg_away_goals=avg_away_goals)

    for team in teams:
        home_matches = df[df["HomeTeam"] == team]
        away_matches = df[df["AwayTeam"] == team]
        n_matches = len(home_matches) + len(away_matches)

        buts_marques = pd.concat([home_matches["_buts_home"], away_matches["_buts_away"]])
        buts_encaisses = pd.concat([home_matches["_buts_away"], away_matches["_buts_home"]])

        ratio_attaque_brut = buts_marques.mean() / moyenne_ligue_marques if n_matches else 1.0
        ratio_defense_brut = buts_encaisses.mean() / moyenne_ligue_marques if n_matches else 1.0

        # Régularisation (shrinkage) : un club avec peu de matchs est ramené
        # vers la moyenne de ligue (1.0) proportionnellement à son échantillon.
        poids_donnees = n_matches / (n_matches + REGUL_MATCHES_PRIOR)
        model.attack[team] = poids_donnees * ratio_attaque_brut + (1 - poids_donnees) * 1.0
        model.defense[team] = poids_donnees * ratio_defense_brut + (1 - poids_donnees) * 1.0

    return model


# ---------------------------------------------------------------------------
# 3. Lambda Poisson (ajustés par l'écart Elo)
# ---------------------------------------------------------------------------
def calculer_lambdas(home: str, away: str, elo: dict, forces: StrengthModel) -> tuple[float, float]:
    """
    Lambdas basés uniquement sur les forces d'attaque/défense (Poisson).

    NOTE (suite au debug du 06/09) : un ajustement basé sur l'écart Elo a été
    testé puis retiré — il faisait double emploi avec les ratios attaque/défense
    (qui reflètent déjà la force relative des équipes) et produisait des
    probabilités irréalistes (ex. 90%+ sur un écart Elo pourtant modéré).
    L'Elo reste calculé et affiché à titre informatif, mais n'influence plus
    les probabilités tant qu'une méthode de fusion Elo+Poisson n'a pas été
    validée par backtest (cf. feuille de route, Phase 2).
    """
    lambda_home = forces.avg_home_goals * forces.attack.get(home, 1.0) * forces.defense.get(away, 1.0)
    lambda_away = forces.avg_away_goals * forces.attack.get(away, 1.0) * forces.defense.get(home, 1.0)

    return max(0.1, lambda_home), max(0.1, lambda_away)


# ---------------------------------------------------------------------------
# 4. Marchés dérivés de la matrice de Poisson bivariée
# ---------------------------------------------------------------------------
def predire_marches(lambda_home: float, lambda_away: float) -> dict:
    p_home_goals = [poisson.pmf(i, lambda_home) for i in range(MAX_GOALS + 1)]
    p_away_goals = [poisson.pmf(i, lambda_away) for i in range(MAX_GOALS + 1)]

    p_home_win = p_draw = p_away_win = 0.0
    p_over25 = p_btts_yes = 0.0

    for i in range(MAX_GOALS + 1):
        for j in range(MAX_GOALS + 1):
            p = p_home_goals[i] * p_away_goals[j]
            if i > j:
                p_home_win += p
            elif i == j:
                p_draw += p
            else:
                p_away_win += p

            if i + j > 2.5:
                p_over25 += p
            if i >= 1 and j >= 1:
                p_btts_yes += p

    total = p_home_win + p_draw + p_away_win
    p_home_win, p_draw, p_away_win = (x / total for x in (p_home_win, p_draw, p_away_win))

    return {
        "1N2": {"1": p_home_win, "N": p_draw, "2": p_away_win},
        "Double Chance": {
            "1N": p_home_win + p_draw,
            "12": p_home_win + p_away_win,
            "N2": p_draw + p_away_win,
        },
        "Over/Under 2.5": {"Over": p_over25, "Under": 1 - p_over25},
        "BTTS": {"Oui": p_btts_yes, "Non": 1 - p_btts_yes},
    }


# ---------------------------------------------------------------------------
# 5. Calcul de la mise suggérée (Kelly fractionné, plafonné)
# ---------------------------------------------------------------------------
def mise_suggeree(prob_modele: float, cote_bookmaker: float, bankroll: float,
                   kelly_fraction: float = 0.25) -> dict:
    b = cote_bookmaker - 1
    edge = prob_modele - (1 / cote_bookmaker)

    full_kelly = max(0.0, (b * prob_modele - (1 - prob_modele)) / b)
    fractional_kelly = kelly_fraction * full_kelly
    pct_finale = min(fractional_kelly, MISE_MAX_PCT)  # plafond dur

    if edge < MIN_EDGE_PCT:  # pas de mise si l'edge est sous le seuil minimum
        pct_finale = 0.0

    return {
        "edge_pct": round(edge * 100, 2),
        "kelly_theorique_pct": round(full_kelly * 100, 2),
        "mise_pct": round(pct_finale * 100, 2),
        "mise_fcfa": round(pct_finale * bankroll),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Kateni — moteur de prédiction V1")
    parser.add_argument("--csv", required=True, help="Chemin du CSV historique (format football-data.co.uk)")
    parser.add_argument("--home", required=True, help="Équipe à domicile")
    parser.add_argument("--away", required=True, help="Équipe à l'extérieur")
    parser.add_argument("--cote1", type=float, help="Cote Betclic victoire domicile (optionnel, pour l'edge)")
    parser.add_argument("--date", help="Date de coupure JJ/MM/AAAA : n'utilise que les matchs AVANT cette date "
                                        "(indispensable pour tester un match déjà présent dans le CSV sans fuite de données)")
    args = parser.parse_args()

    df = pd.read_csv(args.csv, parse_dates=["Date"], dayfirst=True)
    df = df.dropna(subset=["FTHG", "FTAG", "FTR"])

    if args.date:
        cutoff = pd.to_datetime(args.date, dayfirst=True)
        avant = len(df)
        df = df[df["Date"] < cutoff]
        print(f"[Filtrage anti-fuite] {avant - len(df)} match(s) exclu(s) car à partir du {args.date}")

    elo = calculer_elo(df)
    forces = calculer_forces(df)
    lambda_home, lambda_away = calculer_lambdas(args.home, args.away, elo, forces)
    marches = predire_marches(lambda_home, lambda_away)

    print(f"\n=== Kateni — {args.home} vs {args.away} ===")
    print(f"Elo {args.home}: {elo.get(args.home, 1500):.0f} | Elo {args.away}: {elo.get(args.away, 1500):.0f}")
    print(f"Lambda buts attendus — {args.home}: {lambda_home:.2f} | {args.away}: {lambda_away:.2f}\n")

    for marche, probs in marches.items():
        ligne = " | ".join(f"{k}: {v*100:.1f}%" for k, v in probs.items())
        print(f"{marche:<18} {ligne}")

    if args.cote1:
        m = mise_suggeree(marches["1N2"]["1"], args.cote1, BANKROLL_INITIALE)
        print(f"\n--- Mise suggérée (victoire {args.home}, cote {args.cote1}) ---")
        print(f"Edge: {m['edge_pct']}% | Kelly théorique: {m['kelly_theorique_pct']}% "
              f"| Mise retenue: {m['mise_pct']}% ({m['mise_fcfa']} FCFA)")


if __name__ == "__main__":
    main()
