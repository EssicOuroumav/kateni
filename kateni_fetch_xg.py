"""
Kateni — Récupération de xG historique (Understat)
====================================================
Objectif : donner au moteur Kateni plusieurs SAISONS de xG d'un coup,
au lieu d'attendre semaine après semaine que la saison 2026/27 avance.

Source : understat.com, via la librairie open-source `understatapi`
(PyPI, maintenue, ~0,7.1 au moment de l'écriture). Couvre gratuitement
les 5 grands championnats depuis 2014/15.

IMPORTANT — je n'ai pas pu tester ce script en conditions réelles :
mon environnement sandbox n'a pas accès à understat.com (domaine non
autorisé). Le code est basé sur la documentation officielle de la
librairie. Lance-le et colle-moi le résultat (ou l'erreur) — je
l'ajuste immédiatement si la structure des données a changé.

Installation préalable (terminal VS Code) :
    pip3 install understatapi --break-system-packages

Usage :
    python3 kateni_fetch_xg.py --league EPL --seasons 2021 2022 2023 2024 2025
"""

import argparse
import csv

from understatapi import UnderstatClient

# Correspondance entre le nom de ligue Understat et le code football-data.co.uk
LEAGUE_CODES = {
    "EPL": "E0",
    "La_Liga": "SP1",
    "Bundesliga": "D1",
    "Serie_A": "I1",
    "Ligue_1": "F1",
}

# Table de correspondance des noms d'équipes Understat -> football-data.co.uk
# (à compléter au fil des erreurs constatées — liste non exhaustive)
TEAM_NAME_MAP = {
    "Manchester United": "Man United",
    "Manchester City": "Man City",
    "Newcastle United": "Newcastle",
    "Wolverhampton Wanderers": "Wolves",
    "Tottenham": "Tottenham",
    "West Ham": "West Ham",
    "Brighton": "Brighton",
    "Nottingham Forest": "Nott'm Forest",
    "Paris Saint Germain": "Paris SG",
    "Atletico Madrid": "Ath Madrid",
    "Real Sociedad": "Sociedad",
    "Athletic Club": "Athletic Bilbao",
    "Celta Vigo": "Celta",
    "Rayo Vallecano": "Vallecano",
    "Deportivo Alaves": "Alaves",
    "Borussia Dortmund": "Dortmund",
    "Borussia M.Gladbach": "M'gladbach",
    "Bayern Munich": "Bayern Munich",
    "Eintracht Frankfurt": "Ein Frankfurt",
    "FC Koln": "FC Koln",
    "Bayer Leverkusen": "Leverkusen",
    "Hamburger SV": "Hamburg",
    "Inter": "Inter",
    "AC Milan": "Milan",
    "AS Roma": "Roma",
    "Hellas Verona": "Verona",
}


def normaliser_equipe(nom_understat: str) -> str:
    return TEAM_NAME_MAP.get(nom_understat, nom_understat)


def fetch_league_xg(league: str, seasons: list[str]) -> list[dict]:
    lignes = []
    with UnderstatClient() as understat:
        for season in seasons:
            matches = understat.league(league=league).get_match_data(season=season)
            print(f"  Saison {season} : {len(matches)} matchs récupérés")

            if matches and season == seasons[0]:
                print(f"  [debug] Clés disponibles sur un match : {list(matches[0].keys())}")

            for m in matches:
                try:
                    # La structure exacte peut varier selon la version de l'API —
                    # ce bloc tente les clés documentées, à ajuster si erreur.
                    home = m["h"]["title"]
                    away = m["a"]["title"]
                    date = m["datetime"].split(" ")[0]
                    fthg = int(m["goals"]["h"])
                    ftag = int(m["goals"]["a"])
                    hxg = round(float(m["xG"]["h"]), 2)
                    axg = round(float(m["xG"]["a"]), 2)
                    ftr = "H" if fthg > ftag else ("A" if ftag > fthg else "D")

                    lignes.append({
                        "Date": date,
                        "HomeTeam": normaliser_equipe(home),
                        "AwayTeam": normaliser_equipe(away),
                        "FTHG": fthg,
                        "FTAG": ftag,
                        "FTR": ftr,
                        "HxG": hxg,
                        "AxG": axg,
                    })
                except (KeyError, TypeError, ValueError) as e:
                    print(f"  [attention] Match ignoré (structure inattendue) : {e}")
    return lignes


def main():
    parser = argparse.ArgumentParser(description="Récupère plusieurs saisons de xG depuis Understat")
    parser.add_argument("--league", required=True, choices=list(LEAGUE_CODES.keys()),
                         help="Ligue Understat : EPL, La_liga, Bundesliga, Serie_A, Ligue_1")
    parser.add_argument("--seasons", nargs="+", required=True,
                         help="Années de départ des saisons, ex: 2021 2022 2023 2024 2025")
    args = parser.parse_args()

    print(f"Récupération xG — {args.league}, saisons {args.seasons}")
    lignes = fetch_league_xg(args.league, args.seasons)

    code = LEAGUE_CODES[args.league]
    out_path = f"{code}_understat_xg.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "HxG", "AxG"])
        writer.writeheader()
        writer.writerows(lignes)

    print(f"\n{len(lignes)} matchs écrits dans {out_path}")


if __name__ == "__main__":
    main()
