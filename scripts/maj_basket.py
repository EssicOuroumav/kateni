"""
Kateni — données de basket (ajouté le 07/11/2026)
==================================================
Sources gratuites et publiques, sans clé :
  - NBA : tableau des scores d'ESPN, un jour à la fois (score par quart-temps et prolongations) ;
  - EuroLeague (E) et EuroCup (U) : API officielle publique de l'EuroLeague (saisons entières, matchs
    joués et à venir, score par quart-temps).
Écrit basket_resultats.csv (matchs joués) et basket_a_venir.csv (matchs à venir), heures en UTC
(= heure d'Abidjan). Une source muette garde ses lignes précédentes (jamais de fichier vidé).

    python3 scripts/maj_basket.py
"""

import json
import sys
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kateni.config import RACINE  # noqa: E402

RESULTATS = RACINE / "basket_resultats.csv"
A_VENIR = RACINE / "basket_a_venir.csv"
COLONNES = ["ligue", "DateUtc", "HomeTeam", "AwayTeam", "H1", "H2", "H3", "H4", "HOT", "A1", "A2", "A3", "A4",
            "AOT", "HPTS", "APTS"]
ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={:%Y%m%d}"
EUROLEAGUE = "https://api-live.euroleague.net/v2/competitions/{c}/seasons/{c}{a}/games"
PREMIERE_SAISON = 2024           # 2024-25
NBA_HORS_SAISON = {7, 8, 9}      # juillet à septembre : pas de match officiel


def lire_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Kateni/2 (usage personnel)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except Exception as e:  # réseau, format inattendu
        print(f"  [échec] {url} : {type(e).__name__}")
        return None


def saison_actuelle() -> int:
    return date.today().year if date.today().month >= 8 else date.today().year - 1


# ------------------------------------------------------------------ NBA (ESPN)
def _nba_ligne(e: dict) -> dict | None:
    c = (e.get("competitions") or [{}])[0]
    eq = {x.get("homeAway"): x for x in c.get("competitors", [])}
    if "home" not in eq or "away" not in eq:
        return None
    ligne = {"ligue": "NBA", "DateUtc": e["date"], "HomeTeam": eq["home"]["team"]["displayName"],
             "AwayTeam": eq["away"]["team"]["displayName"], "fini": e["status"]["type"].get("completed", False)}
    for cote, x in (("H", eq["home"]), ("A", eq["away"])):
        qt = [int(float(l.get("value", 0))) for l in x.get("linescores", [])]
        for i in range(4):
            ligne[f"{cote}{i + 1}"] = qt[i] if len(qt) > i else None
        ligne[f"{cote}OT"] = sum(qt[4:]) if len(qt) > 4 else 0
        ligne[f"{cote}PTS"] = int(float(x["score"])) if x.get("score") not in (None, "") else None
    return ligne


def nba(depuis: date, jusqu_a: date) -> tuple[list[dict], list[dict], int]:
    joues, a_venir, rates, jour = [], [], 0, depuis
    while jour <= jusqu_a:
        if jour.month not in NBA_HORS_SAISON:
            d = lire_json(ESPN.format(jour))
            if d is None:
                rates += 1
            for e in (d or {}).get("events", []):
                l = _nba_ligne(e)
                if not l:
                    continue
                (joues if l["fini"] and l["HPTS"] is not None else a_venir).append(l)
            time.sleep(0.15)
        jour += timedelta(days=1)
    return joues, a_venir, rates


# ------------------------------------------------------------------ EuroLeague / EuroCup (API officielle)
def euroleague(code: str, annee: int) -> tuple[list[dict], list[dict]] | None:
    d = lire_json(EUROLEAGUE.format(c=code, a=annee))
    if d is None:
        return None
    joues, a_venir = [], []
    nom = {"E": "EuroLeague", "U": "EuroCup"}[code]
    for g in d.get("data", []):
        loc, vis = g.get("local", {}), g.get("road", {})
        if loc.get("club", {}).get("isVirtual") or vis.get("club", {}).get("isVirtual"):
            continue  # affiche pas encore connue (phase finale)
        ligne = {"ligue": nom, "DateUtc": g.get("utcDate"), "HomeTeam": loc["club"]["name"],
                 "AwayTeam": vis["club"]["name"]}
        for cote, x in (("H", loc), ("A", vis)):
            p = x.get("partials") or {}
            for i in range(4):
                ligne[f"{cote}{i + 1}"] = p.get(f"partials{i + 1}")
            ligne[f"{cote}OT"] = sum(v or 0 for v in (p.get("extraPeriods") or {}).values())
            ligne[f"{cote}PTS"] = x.get("score")
        (joues if g.get("played") else a_venir).append(ligne)
    return joues, a_venir


def main():
    ancien = pd.read_csv(RESULTATS) if RESULTATS.exists() else pd.DataFrame(columns=COLONNES)
    ancien_av = pd.read_csv(A_VENIR) if A_VENIR.exists() else pd.DataFrame(columns=COLONNES)
    morceaux, morceaux_av = [ancien], []

    # NBA : tout depuis 2024-25 la première fois, puis les 14 derniers jours ; matchs à venir sur 14 jours
    deja = ancien[ancien["ligue"] == "NBA"]
    depuis = (pd.Timestamp(deja["DateUtc"].max()).date() - timedelta(days=14)) if len(deja) \
        else date(PREMIERE_SAISON, 10, 15)
    joues, a_venir, rates = nba(depuis, date.today() + timedelta(days=14))
    morceaux.append(pd.DataFrame(joues))
    morceaux_av.append(pd.DataFrame(a_venir) if joues or a_venir else ancien_av[ancien_av["ligue"] == "NBA"])
    print(f"NBA : {len(joues)} matchs joués relus, {len(a_venir)} à venir" + (f" ({rates} jours muets)" if rates else ""))

    # EuroLeague et EuroCup : saisons entières (anciennes une seule fois, saison en cours à chaque fois)
    for code in ("E", "U"):
        nom = {"E": "EuroLeague", "U": "EuroCup"}[code]
        connues = set(pd.to_datetime(ancien.loc[ancien["ligue"] == nom, "DateUtc"], utc=True, format="ISO8601").dt.year)
        for annee in range(PREMIERE_SAISON, saison_actuelle() + 1):
            if annee < saison_actuelle() and {annee, annee + 1} <= connues:
                continue
            r = euroleague(code, annee)
            time.sleep(0.5)
            if r is None:
                if annee == saison_actuelle():
                    morceaux_av.append(ancien_av[ancien_av["ligue"] == nom])
                continue
            morceaux.append(pd.DataFrame(r[0]))
            if annee == saison_actuelle():
                morceaux_av.append(pd.DataFrame(r[1]))
            print(f"{nom} {annee}-{str(annee + 1)[2:]} : {len(r[0])} joués, {len(r[1])} à venir")

    res = pd.concat([m for m in morceaux if len(m)], ignore_index=True)[COLONNES]
    res["DateUtc"] = pd.to_datetime(res["DateUtc"], utc=True, format="ISO8601").dt.strftime("%Y-%m-%d %H:%M:%SZ")
    res = res.drop_duplicates(subset=["ligue", "DateUtc", "HomeTeam", "AwayTeam"], keep="last") \
        .sort_values(["DateUtc", "ligue", "HomeTeam"], kind="mergesort")
    res.to_csv(RESULTATS, index=False)
    av = pd.concat([m for m in morceaux_av if len(m)], ignore_index=True) if any(len(m) for m in morceaux_av) \
        else pd.DataFrame(columns=COLONNES)
    av = av.reindex(columns=COLONNES)
    av["DateUtc"] = pd.to_datetime(av["DateUtc"], utc=True, format="ISO8601").dt.strftime("%Y-%m-%d %H:%M:%SZ")
    av = av[pd.to_datetime(av["DateUtc"], utc=True, format="ISO8601") >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=3)]
    av.sort_values(["DateUtc", "ligue"], kind="mergesort").to_csv(A_VENIR, index=False)
    print(f"Basket : {len(res)} matchs joués en tout, {len(av)} à venir")


if __name__ == "__main__":
    main()
