"""
Kateni — Ajout rapide d'un résultat (Champions League / Europa League)
=========================================================================
Pas d'automatisation possible ici : aucune source gratuite et fiable ne
met à jour en direct les résultats de Champions League/Europa League
(contrairement aux 5 championnats domestiques). Ce script simplifie la
SAISIE manuelle — il évite d'éditer le CSV à la main et empêche les
erreurs de format (colonnes dans le mauvais ordre, FTR mal calculé, etc.).

Usage :
    python3 kateni_add_result.py --competition CL --date 2026-09-08 \\
        --home "AEK Athen" --away LASK --score 2-1

Si le club existe déjà sous un autre nom dans le fichier, utilise
exactement l'orthographe déjà présente (vérifiable avec --liste-equipes).
"""

import argparse
import os

import pandas as pd

FICHIERS = {"CL": "CL_full.csv", "EL": "EL_full.csv"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--competition", required=True, choices=["CL", "EL"])
    parser.add_argument("--date", help="Format AAAA-MM-JJ")
    parser.add_argument("--home")
    parser.add_argument("--away")
    parser.add_argument("--score", help="Format buts_domicile-buts_exterieur, ex: 2-1")
    parser.add_argument("--saison", help='Ex: "2026-27" — déduite de la date si absente')
    parser.add_argument("--liste-equipes", action="store_true",
                         help="Affiche la liste des équipes déjà connues pour cette compétition, sans rien ajouter")
    args = parser.parse_args()

    fichier = FICHIERS[args.competition]
    df = pd.read_csv(fichier) if os.path.exists(fichier) else pd.DataFrame(
        columns=["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "Saison"])

    if args.liste_equipes:
        equipes = sorted(pd.unique(df[["HomeTeam", "AwayTeam"]].values.ravel()))
        print("\n".join(equipes))
        return

    if not (args.date and args.home and args.away and args.score):
        print("Il manque --date, --home, --away ou --score (ou utilise --liste-equipes seul).")
        return

    buts_h, buts_a = map(int, args.score.split("-"))
    ftr = "H" if buts_h > buts_a else ("A" if buts_a > buts_h else "D")
    saison = args.saison or f"{args.date[:4]}-{str(int(args.date[2:4]) + 1).zfill(2)}"

    nouvelle_ligne = pd.DataFrame([{
        "Date": args.date, "HomeTeam": args.home, "AwayTeam": args.away,
        "FTHG": buts_h, "FTAG": buts_a, "FTR": ftr, "Saison": saison,
    }])

    # Alerte si l'équipe n'existe pas encore sous ce nom exact (risque de doublon)
    equipes_connues = set(pd.unique(df[["HomeTeam", "AwayTeam"]].values.ravel())) if len(df) else set()
    for equipe in (args.home, args.away):
        if equipe not in equipes_connues and equipes_connues:
            proches = [e for e in equipes_connues if equipe.lower() in e.lower() or e.lower() in equipe.lower()]
            if proches:
                print(f"⚠️  '{equipe}' n'existe pas exactement — noms proches trouvés : {proches}")
                print("   Vérifie l'orthographe avant de continuer (ou ignore si c'est bien un nouveau club).")

    df = pd.concat([df, nouvelle_ligne], ignore_index=True)
    df.to_csv(fichier, index=False)
    print(f"Ajouté : {args.home} {buts_h}-{buts_a} {args.away} ({args.date}) -> {fichier}")


if __name__ == "__main__":
    main()
