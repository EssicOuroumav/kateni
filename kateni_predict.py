"""
Kateni — Outil de prédiction pour analyse/apprentissage
==========================================================
AVERTISSEMENT : le backtest de ce modèle (voir kateni_bilan_final.md) a
montré qu'il ne bat pas le marché (cotes bookmaker) sur les 5 championnats
couverts. Cet outil est destiné à l'analyse et à l'apprentissage
personnel — PAS à guider des mises réelles.

Usage simple (nom de championnat au lieu du nom de fichier CSV) :
    python3 kateni_predict.py --league PL --home "Chelsea" --away "Man City"
    python3 kateni_predict.py --league PL --home "Chelsea" --away "Man City" --cote1 2.10

Championnats disponibles : PL (Premier League), LIGA (La Liga),
L1 (Ligue 1), SA (Serie A), BL (Bundesliga)

Chaque prédiction est automatiquement ajoutée à journal_predictions.csv
pour permettre une comparaison future avec le résultat réel.
"""

import argparse
import csv
import os
from datetime import datetime

import pandas as pd

from kateni_engine import (
    calculer_elo_unifie,
    calculer_forces,
    calculer_lambdas,
    predire_marches,
    mise_suggeree,
    BANKROLL_INITIALE,
)

# Nom court -> fichier de données (historique complet 2020-2026 + xG)
LEAGUES = {
    "PL": ("E0_full.csv", "Premier League", True),
    "LIGA": ("SP1_full.csv", "La Liga", True),
    "L1": ("F1_full.csv", "Ligue 1", True),
    "SA": ("I1_full.csv", "Serie A", True),
    "BL": ("D1_full.csv", "Bundesliga", True),
    "POR": ("P1_full.csv", "Primeira Liga (Portugal)", True),
    "TUR": ("T1_full.csv", "Süper Lig (Turquie)", True),
    "MLS": ("USA_full.csv", "MLS (USA)", True),
    "BEL": ("B1_full.csv", "Pro League (Belgique)", True),
    "NED": ("N1_full.csv", "Eredivisie (Pays-Bas)", True),
    "CHAMP": ("E1_full.csv", "Championship (Angleterre)", True),
    "LIGA2": ("SP2_full.csv", "La Liga 2 (Espagne)", True),
    "L2": ("F2_full.csv", "Ligue 2 (France)", True),
    "CL": ("CL_full.csv", "Champions League", False),
    "EL": ("EL_full.csv", "Europa League", False),
}
# True/False = cotes disponibles pour cette compétition (analyse d'edge possible ou non)

TOUS_LES_FICHIERS = [f for f, _, _ in LEAGUES.values()]

JOURNAL_PATH = "journal_predictions.csv"
JOURNAL_COLONNES = [
    "date_generation", "league", "home", "away",
    "prob_1", "prob_N", "prob_2",
    "prob_over25", "prob_btts_oui",
    "cote_fournie", "edge_pct", "mise_suggeree_fcfa",
    "resultat_reel",  # à remplir manuellement plus tard
]


def enregistrer_dans_journal(ligne: dict):
    fichier_existe = os.path.exists(JOURNAL_PATH)
    with open(JOURNAL_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=JOURNAL_COLONNES)
        if not fichier_existe:
            writer.writeheader()
        writer.writerow(ligne)


def main():
    parser = argparse.ArgumentParser(description="Kateni — prédiction pour analyse/apprentissage")
    parser.add_argument("--league", required=True, choices=list(LEAGUES.keys()),
                         help="PL, LIGA, L1, SA, BL, CL ou EL")
    parser.add_argument("--home", required=True)
    parser.add_argument("--away", required=True)
    parser.add_argument("--cote1", type=float, help="Cote observée (Betclic) pour victoire domicile, optionnel")
    args = parser.parse_args()

    csv_path, league_name, cotes_disponibles = LEAGUES[args.league]
    if not os.path.exists(csv_path):
        print(f"Fichier introuvable : {csv_path} (doit être dans le même dossier que ce script)")
        return

    df = pd.read_csv(csv_path, parse_dates=["Date"])
    df = df.dropna(subset=["FTHG", "FTAG", "FTR"])

    elo = calculer_elo_unifie(TOUS_LES_FICHIERS)  # rating partagé toutes compétitions confondues
    forces = calculer_forces(df)  # forces attaque/défense propres à cette compétition
    lambda_home, lambda_away = calculer_lambdas(args.home, args.away, elo, forces)
    marches = predire_marches(lambda_home, lambda_away)

    print(f"\n{'='*60}")
    print(f"KATENI — {league_name} — {args.home} vs {args.away}")
    print(f"{'='*60}")
    print("[Outil d'apprentissage personnel — ne bat pas le marché, ne pas parier dessus]")
    if not cotes_disponibles:
        print("[Pas de cotes disponibles pour cette compétition — analyse d'edge impossible]")
    print(f"\nElo {args.home}: {elo.get(args.home, 1500):.0f} | Elo {args.away}: {elo.get(args.away, 1500):.0f}")
    print(f"Buts attendus — {args.home}: {lambda_home:.2f} | {args.away}: {lambda_away:.2f}\n")

    for marche, probs in marches.items():
        ligne = " | ".join(f"{k}: {v*100:.1f}%" for k, v in probs.items())
        print(f"{marche:<18} {ligne}")

    edge_pct = mise_fcfa = ""
    if args.cote1 and cotes_disponibles:
        m = mise_suggeree(marches["1N2"]["1"], args.cote1, BANKROLL_INITIALE)
        edge_pct, mise_fcfa = m["edge_pct"], m["mise_fcfa"]
        print(f"\n--- Analyse edge (victoire {args.home}, cote {args.cote1}) ---")
        print(f"Edge: {edge_pct}% | Mise théorique (à titre indicatif) : {mise_fcfa} FCFA")

    enregistrer_dans_journal({
        "date_generation": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "league": league_name,
        "home": args.home,
        "away": args.away,
        "prob_1": round(marches["1N2"]["1"], 3),
        "prob_N": round(marches["1N2"]["N"], 3),
        "prob_2": round(marches["1N2"]["2"], 3),
        "prob_over25": round(marches["Over/Under 2.5"]["Over"], 3),
        "prob_btts_oui": round(marches["BTTS"]["Oui"], 3),
        "cote_fournie": args.cote1 or "",
        "edge_pct": edge_pct,
        "mise_suggeree_fcfa": mise_fcfa,
        "resultat_reel": "",
    })
    print(f"\n[Prédiction enregistrée dans {JOURNAL_PATH}]")


if __name__ == "__main__":
    main()
