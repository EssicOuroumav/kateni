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
from datetime import date, timedelta
from io import StringIO
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kateni.config import COLONNES_BASE, COLONNES_OPTION, COMPETITIONS, ESPN_FOOT, FORMAT_NEW, RACINE  # noqa: E402

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


ESPN_API = "https://site.api.espn.com/apis/site/v2/sports/soccer/{}/scoreboard?dates={}"
MOIS_HORS_SAISON = {"AUS": {6, 7, 8, 9}}  # A-League : d'octobre à fin mai (finales comprises)


def _espn_jour(ligue: str, jour: date) -> list[dict] | None:
    """Matchs d'une journée (ESPN n'accepte qu'un jour à la fois). None si la source ne répond pas."""
    import json
    texte = telecharger(ESPN_API.format(ligue, f"{jour:%Y%m%d}"))
    try:
        return json.loads(texte).get("events", []) if texte else None
    except ValueError:
        return None


def _espn_ligne(e: dict) -> dict | None:
    c = (e.get("competitions") or [{}])[0]
    eq = {x.get("homeAway"): x for x in c.get("competitors", [])}
    if "home" not in eq or "away" not in eq:
        return None
    return {"DateUtc": pd.Timestamp(e["date"]), "HomeTeam": eq["home"]["team"]["displayName"],
            "AwayTeam": eq["away"]["team"]["displayName"], "fini": e["status"]["type"].get("completed", False),
            "FTHG": eq["home"].get("score"), "FTAG": eq["away"].get("score")}


def maj_espn(code: str) -> None:
    """Résultats d'un championnat ESPN, jour par jour : tout l'historique la première fois, puis les 14
    derniers jours. Fichier inchangé si la source ne répond pas."""
    comp = COMPETITIONS[code]
    chemin = RACINE / comp.fichier
    ancien = pd.read_csv(chemin, parse_dates=["Date"]) if chemin.exists() else None
    debut = (ancien["Date"].max().date() - timedelta(days=14)) if ancien is not None and len(ancien) \
        else date(comp.premiere_saison, 10, 1)
    lignes, rates, jour = [], 0, debut
    while jour <= date.today():
        if jour.month not in MOIS_HORS_SAISON.get(code, set()):
            evts = _espn_jour(ESPN_FOOT[code], jour)
            if evts is None:
                rates += 1
            for e in evts or []:
                l = _espn_ligne(e)
                if l and l["fini"] and l["FTHG"] not in (None, "") and l["FTAG"] not in (None, ""):
                    lignes.append(l)
            time.sleep(0.15)
        jour += timedelta(days=1)
    if not lignes:
        print(f"{comp.nom} : rien téléchargé ({rates} jours sans réponse), fichier inchangé")
        return
    neuf = pd.DataFrame(lignes)
    # Date du match à l'heure d'Abidjan (UTC), comme les autres sources
    neuf["Date"] = neuf["DateUtc"].dt.tz_convert(None).dt.normalize()
    neuf["FTHG"], neuf["FTAG"] = neuf["FTHG"].astype(int), neuf["FTAG"].astype(int)
    neuf["FTR"] = ["H" if a > b else "A" if a < b else "D" for a, b in zip(neuf["FTHG"], neuf["FTAG"])]
    neuf = neuf[COLONNES_BASE]
    n_avant = 0 if ancien is None else len(ancien)
    if ancien is not None:
        neuf = pd.concat([ancien, neuf], ignore_index=True)
    neuf = neuf.drop_duplicates(subset=["Date", "HomeTeam", "AwayTeam"], keep="last").sort_values(
        ["Date", "HomeTeam", "AwayTeam"], kind="mergesort")
    neuf.to_csv(chemin, index=False, date_format="%Y-%m-%d")
    print(f"{comp.nom} : {n_avant} -> {len(neuf)} matchs, dernier le {neuf['Date'].max():%d/%m/%Y}"
          + (f" ({rates} jours sans réponse)" if rates else ""))


def a_venir_espn(code: str, jours: int = 28) -> pd.DataFrame | None:
    """Matchs à venir d'un championnat ESPN sur les prochaines semaines (format calendrier_saison.csv)."""
    lignes, ok = [], False
    for k in range(jours):
        jour = date.today() + timedelta(days=k)
        if jour.month in MOIS_HORS_SAISON.get(code, set()):
            continue
        evts = _espn_jour(ESPN_FOOT[code], jour)
        ok = ok or evts is not None
        for e in evts or []:
            l = _espn_ligne(e)
            if l and not l["fini"]:
                lignes.append({"competition": code, "DateUtc": f"{l['DateUtc']:%Y-%m-%d %H:%M:%S}Z",
                               "HomeTeam": l["HomeTeam"], "AwayTeam": l["AwayTeam"]})
        time.sleep(0.15)
    return pd.DataFrame(lignes, columns=["competition", "DateUtc", "HomeTeam", "AwayTeam"]) if ok else None


def maj_competition(code: str) -> None:
    comp = COMPETITIONS[code]
    if code in ESPN_FOOT:
        maj_espn(code)
        return
    if comp.fd_code is None:
        print(f"{comp.nom} : pas de source automatique (saisie avec kateni_add_result.py)")
        return
    DOSSIER_BRUT.mkdir(exist_ok=True)
    morceaux = []
    if comp.fd_code in FORMAT_NEW:
        texte = telecharger(f"{BASE_URL}/new/{comp.fd_code}.csv")
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

    neuf = neuf.drop_duplicates(subset=["Date", "HomeTeam", "AwayTeam"], keep="last").sort_values(["Date", "HomeTeam", "AwayTeam"], kind="mergesort")
    ordre = [c for c in COLONNES_BASE + COLONNES_OPTION if c in neuf.columns]
    neuf[ordre].to_csv(chemin, index=False, date_format="%Y-%m-%d")
    print(f"{comp.nom} : {n_avant} -> {len(neuf)} matchs, dernier le {neuf['Date'].max():%d/%m/%Y}")


def maj_calendrier() -> None:
    """Matchs à venir des championnats (avec cotes Bet365 quand elles sont publiées) -> a_venir_championnats.csv."""
    par_div = {c.fd_code: c.code for c in COMPETITIONS.values() if c.fd_code}
    codes_new = {c.code for c in COMPETITIONS.values() if c.fd_code in FORMAT_NEW}
    chemin = RACINE / "a_venir_championnats.csv"
    ancien = pd.read_csv(chemin) if chemin.exists() else pd.DataFrame(columns=["competition", "Date"])
    # même présentation que les fichiers téléchargés (date jj/mm/aaaa, colonne Time)
    ancien = ancien.rename(columns={"Heure_UK": "Time"}).assign(
        Date=lambda a: pd.to_datetime(a["Date"], errors="coerce").dt.strftime("%d/%m/%Y"))
    lignes = []
    texte = telecharger(f"{BASE_URL}/fixtures.csv")
    if not texte:  # source muette : on garde ses matchs précédents (jamais de calendrier vidé)
        lignes.append(ancien[~ancien["competition"].isin(codes_new)])
    if texte:
        f = pd.read_csv(StringIO(texte))
        f = f[f["Div"].isin(par_div)]
        f["competition"] = f["Div"].map(par_div)
        lignes.append(f)
    texte = telecharger(f"{BASE_URL}/new_league_fixtures.csv")
    if not texte:
        lignes.append(ancien[ancien["competition"].isin(codes_new)])
    if texte:
        f = pd.read_csv(StringIO(texte)).rename(columns={"Home": "HomeTeam", "Away": "AwayTeam"})
        pays = {"USA": "MLS", "Austria": "AUT", "Switzerland": "SUI", "Norway": "NOR", "Denmark": "DAN",
                "Sweden": "SUE", "Poland": "POL", "Romania": "ROU", "China": "CHN", "Japan": "JPN", "Ireland": "IRL"}
        f["competition"] = f["Country"].map(pays)
        principale = {"USA": "MLS", "Japan": "J1 League", "Ireland": "Premier Division", "China": "Super League"}
        f = f[f["competition"].notna() & (f["League"] == f["Country"].map(principale).fillna(f["League"]))]
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


# Calendrier complet de la saison (fixturedownload.com, gratuit, heures en UTC = heure d'Abidjan)
SAISON_COMPLETE = {"PL": "epl", "LIGA": "la-liga", "SA": "serie-a", "BL": "bundesliga", "L1": "ligue-1",
                   "NED": "eredivisie", "POR": "primeira-liga", "CHAMP": "championship", "SCO": "scottish-premiership",
                   "TUR": "super-lig", "L2": "ligue-2", "MLS": "mls"}


def maj_calendrier_saison() -> None:
    """Tous les matchs à venir de la saison -> calendrier_saison.csv. Une compétition qui ne répond pas
    garde ses lignes précédentes (jamais de calendrier vidé)."""
    import json
    chemin = RACINE / "calendrier_saison.csv"
    ancien = pd.read_csv(chemin) if chemin.exists() else pd.DataFrame(columns=["competition"])
    aujourd_hui = date.today()
    saison = aujourd_hui.year if aujourd_hui.month >= 7 else aujourd_hui.year - 1
    morceaux, rates = [], []
    for code, slug in SAISON_COMPLETE.items():
        annee = aujourd_hui.year if code == "MLS" else saison  # la MLS se joue sur l'année civile
        texte = telecharger(f"https://fixturedownload.com/feed/json/{slug}-{annee}")
        time.sleep(0.5)
        try:
            matchs = json.loads(texte) if texte else None
        except ValueError:
            matchs = None
        if not matchs:
            rates.append(code)
            morceaux.append(ancien[ancien["competition"] == code])
            continue
        a_venir = [{"competition": code, "DateUtc": m["DateUtc"], "HomeTeam": m["HomeTeam"], "AwayTeam": m["AwayTeam"]}
                   for m in matchs if m.get("HomeTeamScore") is None and m.get("HomeTeam") and m.get("AwayTeam")]
        morceaux.append(pd.DataFrame(a_venir))
    for code in ESPN_FOOT:
        a_venir = a_venir_espn(code)
        if a_venir is None:
            rates.append(code)
            morceaux.append(ancien[ancien["competition"] == code])
        else:
            morceaux.append(a_venir)
    cal = pd.concat([m for m in morceaux if len(m)], ignore_index=True) if any(len(m) for m in morceaux) else ancien
    cal = cal.sort_values(["DateUtc", "competition", "HomeTeam"], kind="mergesort")
    cal.to_csv(chemin, index=False)
    print(f"Calendrier de la saison : {len(cal)} matchs à venir, jusqu'au {str(cal['DateUtc'].max())[:10]}"
          + (f" (non mis à jour : {', '.join(rates)})" if rates else ""))


def main():
    codes = sys.argv[1:] or list(COMPETITIONS)
    for code in codes:
        maj_competition(code)
    maj_calendrier()
    maj_calendrier_saison()


if __name__ == "__main__":
    main()
