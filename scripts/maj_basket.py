"""
Kateni — données de basket (ajouté le 07/11/2026)
==================================================
Sources gratuites et publiques, sans clé :
  - NBA, WNBA, NBL (Australie), NCAA (universités USA, 1re division) : tableau des scores d'ESPN, un jour à
    la fois (score par quart-temps et prolongations ; NCAA : deux mi-temps, rangées en H1 et H3) ;
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
COTES = RACINE / "basket_cotes.csv"   # cotes DraftKings (via ESPN) des matchs à venir, gardées pour mesurer plus tard
A_VENIR = RACINE / "basket_a_venir.csv"
COLONNES = ["ligue", "DateUtc", "HomeTeam", "AwayTeam", "H1", "H2", "H3", "H4", "HOT", "A1", "A2", "A3", "A4",
            "AOT", "HPTS", "APTS", "Neutre"]
ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/{slug}/scoreboard?dates={jour:%Y%m%d}{extra}"
# ligue -> (code ESPN, paramètres en plus, mois sans match officiel, début de l'historique)
LIGUES_ESPN = {
    "NBA": ("nba", "", {7, 8, 9}, date(2024, 10, 15)),
    "WNBA": ("wnba", "", {11, 12, 1, 2, 3, 4}, date(2024, 5, 10)),
    "NBL": ("nbl", "", {4, 5, 6, 7, 8}, date(2024, 9, 15)),
    "NCAA": ("mens-college-basketball", "&groups=50&limit=500", {5, 6, 7, 8, 9, 10}, date(2024, 11, 1)),
}
MI_TEMPS = {"NCAA"}  # deux mi-temps de 20 minutes au lieu de quatre quarts-temps
EUROLEAGUE = "https://api-live.euroleague.net/v2/competitions/{c}/seasons/{c}{a}/games"
PREMIERE_SAISON = 2024           # 2024-25


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
def _americaine(x) -> float | None:
    """Cote américaine (-162, +136) -> cote décimale (1,62 ; 2,36)."""
    try:
        v = float(str(x).replace("+", ""))
    except (TypeError, ValueError):
        return None
    return round(1 + (v / 100 if v > 0 else 100 / -v), 3) if v else None


def _cotes(e: dict, ligue: str) -> dict | None:
    """Cotes du marché (DraftKings) d'un match à venir : handicap et total, cotes vainqueur."""
    c = (e.get("competitions") or [{}])[0]
    o = (c.get("odds") or [None])[0]
    if not o or o.get("overUnder") is None:
        return None
    eq = {x.get("homeAway"): x["team"]["displayName"] for x in c.get("competitors", [])}
    ml = o.get("moneyline") or {}
    return {"ligue": ligue, "DateUtc": e["date"], "HomeTeam": eq.get("home"), "AwayTeam": eq.get("away"),
            "releve": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%SZ"),
            "bookmaker": (o.get("provider") or {}).get("name"), "handicap_dom": o.get("spread"),
            "total": o.get("overUnder"),
            "cote_dom": _americaine(((ml.get("home") or {}).get("close") or {}).get("odds")),
            "cote_ext": _americaine(((ml.get("away") or {}).get("close") or {}).get("odds"))}


COTES_RELEVEES: list[dict] = []


def _nba_ligne(e: dict, ligue: str = "NBA") -> dict | None:
    c = (e.get("competitions") or [{}])[0]
    eq = {x.get("homeAway"): x for x in c.get("competitors", [])}
    if "home" not in eq or "away" not in eq:
        return None
    ligne = {"ligue": ligue, "DateUtc": e["date"], "HomeTeam": eq["home"]["team"]["displayName"],
             "AwayTeam": eq["away"]["team"]["displayName"], "fini": e["status"]["type"].get("completed", False),
             "Neutre": bool(c.get("neutralSite", False))}
    for cote, x in (("H", eq["home"]), ("A", eq["away"])):
        qt = [int(float(l.get("value", 0))) for l in x.get("linescores", [])]
        if ligue in MI_TEMPS:  # 1re mi-temps en H1, 2e en H3 : « 1re mi-temps » = H1 + H2 reste juste
            qt = [qt[0], None, qt[1], None, *qt[2:]] if len(qt) >= 2 else qt
        for i in range(4):
            ligne[f"{cote}{i + 1}"] = qt[i] if len(qt) > i else None
        ligne[f"{cote}OT"] = sum(qt[4:]) if len(qt) > 4 else 0
        ligne[f"{cote}PTS"] = int(float(x["score"])) if x.get("score") not in (None, "") else None
    return ligne


def espn(ligue: str, depuis: date, jusqu_a: date) -> tuple[list[dict], list[dict], int]:
    slug, extra, hors_saison, _ = LIGUES_ESPN[ligue]
    joues, a_venir, rates, jour = [], [], 0, depuis
    while jour <= jusqu_a:
        if jour.month not in hors_saison:
            d = lire_json(ESPN.format(slug=slug, jour=jour, extra=extra))
            if d is None:
                rates += 1
            for e in (d or {}).get("events", []):
                l = _nba_ligne(e, ligue)
                if not l:
                    continue
                if not l["fini"] and (co := _cotes(e, ligue)):
                    COTES_RELEVEES.append(co)
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

    # Ligues ESPN : tout l'historique la première fois, puis les 14 derniers jours ; matchs à venir sur 14 jours
    for ligue, (_, _, _, debut) in LIGUES_ESPN.items():
        deja = ancien[ancien["ligue"] == ligue]
        depuis = (pd.Timestamp(deja["DateUtc"].max()).date() - timedelta(days=14)) if len(deja) else debut
        joues, a_venir, rates = espn(ligue, depuis, date.today() + timedelta(days=14))
        morceaux.append(pd.DataFrame(joues))
        morceaux_av.append(pd.DataFrame(a_venir) if joues or a_venir or not rates
                           else ancien_av[ancien_av["ligue"] == ligue])
        print(f"{ligue} : {len(joues)} matchs joués relus, {len(a_venir)} à venir" + (f" ({rates} jours muets)" if rates else ""))

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
    if COTES_RELEVEES:  # on garde le dernier relevé avant le match (le plus proche de la cote de clôture)
        anc = pd.read_csv(COTES) if COTES.exists() else pd.DataFrame()
        c = pd.concat([anc, pd.DataFrame(COTES_RELEVEES)], ignore_index=True)
        c["DateUtc"] = pd.to_datetime(c["DateUtc"], utc=True, format="ISO8601").dt.strftime("%Y-%m-%d %H:%M:%SZ")
        c = c.drop_duplicates(subset=["ligue", "DateUtc", "HomeTeam", "AwayTeam"], keep="last") \
            .sort_values(["DateUtc", "ligue"], kind="mergesort")
        c.to_csv(COTES, index=False)
        print(f"Cotes du marché (basket) : {len(COTES_RELEVEES)} relevées, {len(c)} gardées en tout")


if __name__ == "__main__":
    main()
