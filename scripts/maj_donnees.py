"""
Kateni — mise à jour des données depuis football-data.co.uk
=============================================================
Télécharge toutes les saisons de chaque championnat (depuis la première
saison déjà présente dans le *_full.csv), garde les colonnes utiles
(mi-temps, cartons rouges, xG, cotes d'ouverture ET de clôture, plus/moins
2,5 buts) et fusionne avec l'existant sans perdre le xG Understat déjà
présent pour les anciennes saisons.

La Champions League et l'Europa League n'ont pas de source gratuite à jour :
utiliser `python3 kateni_add_result.py` pour les saisir.

Usage :
    python3 scripts/maj_donnees.py            # tous les championnats
    python3 scripts/maj_donnees.py PL L1      # seulement ceux-là
"""

import sys
import time
import urllib.request
from datetime import date
from io import StringIO
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kateni.config import COLONNES_BASE, COLONNES_OPTION, COMPETITIONS, RACINE  # noqa: E402

BASE_URL = "https://www.football-data.co.uk"
DOSSIER_BRUT = RACINE / "data_brut"


def telecharger(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": "Kateni/2 (usage personnel)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status != 200:
                return None
            return r.read().decode("utf-8-sig", errors="replace")
    except Exception as e:  # réseau, 404...
        print(f"  [échec] {url} : {e}")
        return None


def saison_code(annee: int) -> str:
    """2026 -> '2627' (saison 2026-27)."""
    return f"{annee % 100:02d}{(annee + 1) % 100:02d}"


def normaliser(df: pd.DataFrame) -> pd.DataFrame:
    if "Home" in df.columns:  # format "new/" (MLS)
        df = df.rename(columns={"Home": "HomeTeam", "Away": "AwayTeam", "HG": "FTHG",
                                "AG": "FTAG", "Res": "FTR"})
    df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"])
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce", format="mixed")
    df = df.dropna(subset=["Date"])
    garder = [c for c in COLONNES_BASE + COLONNES_OPTION if c in df.columns]
    return df[garder]


def maj_competition(code: str) -> None:
    comp = COMPETITIONS[code]
    if comp.fd_code is None:
        print(f"{comp.nom} : pas de source automatique (saisie avec kateni_add_result.py)")
        return
    DOSSIER_BRUT.mkdir(exist_ok=True)
    morceaux = []
    if comp.fd_code == "USA":
        texte = telecharger(f"{BASE_URL}/new/USA.csv")
        if texte:
            morceaux.append(normaliser(pd.read_csv(StringIO(texte))))
    else:
        derniere = date.today().year if date.today().month >= 7 else date.today().year - 1
        for annee in range(comp.premiere_saison, derniere + 1):
            url = f"{BASE_URL}/mmz4281/{saison_code(annee)}/{comp.fd_code}.csv"
            texte = telecharger(url)
            if texte:
                (DOSSIER_BRUT / f"{comp.fd_code}_{saison_code(annee)}.csv").write_text(texte, encoding="utf-8")
                morceaux.append(normaliser(pd.read_csv(StringIO(texte), on_bad_lines="skip")))
            time.sleep(0.5)  # politesse envers le site source
    if not morceaux:
        print(f"{comp.nom} : rien téléchargé, fichier inchangé")
        return

    neuf = pd.concat(morceaux, ignore_index=True)
    chemin = RACINE / comp.fichier
    if chemin.exists():
        ancien = pd.read_csv(chemin, parse_dates=["Date"])
        # Récupère le xG Understat des anciennes saisons quand la nouvelle source n'en a pas
        if "HxG" in ancien.columns:
            cle = ["Date", "HomeTeam", "AwayTeam"]
            xg = ancien[cle + ["HxG", "AxG"]].rename(columns={"HxG": "_hxg", "AxG": "_axg"})
            neuf = neuf.merge(xg, on=cle, how="left")
            if "HxG" not in neuf.columns:
                neuf["HxG"], neuf["AxG"] = float("nan"), float("nan")
            neuf["HxG"] = neuf["HxG"].fillna(neuf["_hxg"])
            neuf["AxG"] = neuf["AxG"].fillna(neuf["_axg"])
            neuf = neuf.drop(columns=["_hxg", "_axg"])
        n_avant = len(ancien)
    else:
        n_avant = 0

    neuf = neuf.drop_duplicates(subset=["Date", "HomeTeam", "AwayTeam"], keep="last").sort_values("Date")
    ordre = [c for c in COLONNES_BASE + COLONNES_OPTION if c in neuf.columns]
    neuf[ordre].to_csv(chemin, index=False, date_format="%Y-%m-%d")
    print(f"{comp.nom} : {n_avant} -> {len(neuf)} matchs, dernier le {neuf['Date'].max():%d/%m/%Y}")


def maj_calendrier() -> None:
    """Matchs à venir des championnats (avec cotes Bet365 quand elles sont publiées) -> a_venir_championnats.csv."""
    par_div = {c.fd_code: c.code for c in COMPETITIONS.values() if c.fd_code}
    lignes = []
    texte = telecharger(f"{BASE_URL}/fixtures.csv")
    if texte:
        f = pd.read_csv(StringIO(texte))
        f = f[f["Div"].isin(par_div)]
        f["competition"] = f["Div"].map(par_div)
        lignes.append(f)
    texte = telecharger(f"{BASE_URL}/new_league_fixtures.csv")
    if texte:
        f = pd.read_csv(StringIO(texte)).rename(columns={"Home": "HomeTeam", "Away": "AwayTeam"})
        f = f[(f["Country"] == "USA") & (f["League"] == "MLS")]
        f["competition"] = "MLS"
        lignes.append(f)
    if not lignes:
        print("Calendrier des championnats : rien téléchargé")
        return
    cal = pd.concat(lignes, ignore_index=True)
    cal["Date"] = pd.to_datetime(cal["Date"], dayfirst=True, errors="coerce").dt.strftime("%Y-%m-%d")
    garder = ["competition", "Date", "Time", "HomeTeam", "AwayTeam", "B365H", "B365D", "B365A", "B365>2.5", "B365<2.5"]
    cal = cal[[c for c in garder if c in cal.columns]].rename(columns={"Time": "Heure_UK"})
    cal.to_csv(RACINE / "a_venir_championnats.csv", index=False)
    print(f"Calendrier des championnats : {len(cal)} matchs à venir ({cal['Date'].min()} -> {cal['Date'].max()})")


def main():
    codes = sys.argv[1:] or list(COMPETITIONS)
    for code in codes:
        maj_competition(code)
    maj_calendrier()


if __name__ == "__main__":
    main()
