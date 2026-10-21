"""
Kateni — Parseur Champions League / Europa League (source : openfootball)
============================================================================
Convertit les fichiers texte openfootball/champions-league (cl.txt, el.txt)
en CSV au format Kateni (Date, HomeTeam, AwayTeam, FTHG, FTAG, FTR).

Source : https://github.com/openfootball/champions-league (domaine public,
gratuit). Aucune cote bookmaker disponible dans cette source — ces
compétitions seront donc prédictibles (Elo/Poisson) mais sans analyse
d'edge possible (pas de comparaison au marché).

Usage :
    python3 kateni_parse_cl_el.py --dossier cl_data --competition cl --sortie CL_full.csv
    python3 kateni_parse_cl_el.py --dossier cl_data --competition el --sortie EL_full.csv
"""

import argparse
import re
from pathlib import Path

import pandas as pd

# Ligne de match, ex :
#   18:45  BSC Young Boys (SUI)    v Aston Villa FC (ENG)     0-3 (0-2)
LIGNE_MATCH = re.compile(
    r"^\s*(?:\d{1,2}:\d{2}\s+)?(.+?)\s+v\s+(.+?)\s+(\d+)-(\d+)\b"
)
LIGNE_DATE = re.compile(r"^\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+\w+\s+\d{1,2}(?:\s+\d{4})?\s*$")


def nettoyer_nom_equipe(nom: str) -> str:
    # Retire le code pays entre parenthèses, ex "Aston Villa FC (ENG)" -> "Aston Villa FC"
    nom = re.sub(r"\s*\([A-Z]{3}\)\s*$", "", nom).strip()
    return normaliser_nom_club(nom)


# Préfixes/suffixes génériques à retirer pour éviter qu'un même club apparaisse
# sous plusieurs noms selon la saison (ex: "Real Madrid" vs "Real Madrid CF").
# Liste non exhaustive — à enrichir si des doublons sont repérés plus tard.
MOTS_GENERIQUES = [
    "FC", "CF", "AC", "SSC", "AS", "BSC", "SC", "SK", "SL", "PAE", "PFC",
    "KV", "KAA", "RSC", "1.", "VfB", "VfL", "TSG", "FK", "NK", "Clube",
    "Real", "Royal",
]


def normaliser_nom_club(nom: str) -> str:
    mots = nom.split()
    mots_filtres = [m for m in mots if m not in MOTS_GENERIQUES or m == "Real"]
    # "Real" est ambigu (Real Madrid, Real Sociedad...) -> on le garde toujours
    resultat = " ".join(m for m in mots if not (m in MOTS_GENERIQUES and m != "Real"))
    return resultat.strip() or nom


def parser_fichier(chemin: Path, saison: str) -> list[dict]:
    lignes = chemin.read_text(encoding="utf-8", errors="ignore").splitlines()
    matchs = []
    date_courante = None
    annee_courante = int(saison.split("-")[0])  # année de départ de la saison, mise à jour si la source la précise

    for ligne in lignes:
        m_date = re.match(r"^\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\w+)\s+(\d{1,2})(?:\s+(\d{4}))?\s*$", ligne)
        if m_date:
            mois, jour = m_date.group(2), m_date.group(3)
            if m_date.group(4):
                annee_courante = int(m_date.group(4))  # la source précise l'année -> on la retient pour la suite
            try:
                date_courante = pd.to_datetime(f"{jour} {mois} {annee_courante}", format="%d %b %Y")
            except ValueError:
                date_courante = None
            continue

        m = LIGNE_MATCH.match(re.sub(r"\d+-\d+\s+pen\.\s*", "", ligne))
        if m and date_courante is not None:
            home, away, buts_h, buts_a = m.groups()
            home, away = nettoyer_nom_equipe(home), nettoyer_nom_equipe(away)
            buts_h, buts_a = int(buts_h), int(buts_a)
            ftr = "H" if buts_h > buts_a else ("A" if buts_a > buts_h else "D")
            matchs.append({
                "Date": date_courante, "HomeTeam": home, "AwayTeam": away,
                "FTHG": buts_h, "FTAG": buts_a, "FTR": ftr, "Saison": saison,
            })

    return matchs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dossier", required=True, help="Dossier cloné openfootball/champions-league")
    parser.add_argument("--competition", required=True, choices=["cl", "el"],
                         help="cl = Champions League, el = Europa League")
    parser.add_argument("--sortie", required=True)
    args = parser.parse_args()

    tous_matchs = []
    dossier = Path(args.dossier)
    for dossier_saison in sorted(dossier.glob("20*-*")):
        fichier = dossier_saison / f"{args.competition}.txt"
        if fichier.exists():
            saison = dossier_saison.name
            matchs = parser_fichier(fichier, saison)
            tous_matchs.extend(matchs)
            print(f"  {saison}: {len(matchs)} matchs")

    df = pd.DataFrame(tous_matchs)
    df = df.dropna(subset=["Date"]).sort_values("Date")
    df.to_csv(args.sortie, index=False)
    print(f"\n{len(df)} matchs écrits dans {args.sortie}")
    print(f"Équipes distinctes : {len(pd.unique(df[['HomeTeam','AwayTeam']].values.ravel()))}")


if __name__ == "__main__":
    main()
