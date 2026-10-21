"""
Kateni — calendrier unifié des matchs à venir, en heure d'Abidjan (UTC, sans changement d'heure)
==================================================================================================
Trois sources, de la plus riche à la plus lointaine :
  1. a_venir_championnats.csv (football-data) : quelques jours à l'avance, AVEC les cotes ; heure de Londres
  2. a_venir.csv (Wikipédia) : C1 et C3 ; heure de Paris
  3. calendrier_saison.csv (fixturedownload) : toute la saison ; déjà en UTC
Puis les cotes Pinnacle (cotes_pinnacle.csv, relevées juste avant les matchs) remplacent les autres cotes.
Un même match présent dans deux sources (même compétition, mêmes équipes, dates à moins de 3 jours)
n'est gardé qu'une fois, dans la source la plus riche (celle qui a les cotes).
"""

from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from kateni.config import RACINE
from kateni.equipes import canon

UTC = ZoneInfo("UTC")
COLONNES = ["competition", "Date", "Heure", "HomeTeam", "AwayTeam", "dom", "ext", "source",
            "B365H", "B365D", "B365A", "B365>2.5", "B365<2.5", "bookmaker", "releve"]
COTES = ["B365H", "B365D", "B365A", "B365>2.5", "B365<2.5"]


def _norm(nom: str) -> str:
    import re
    import unicodedata
    n = unicodedata.normalize("NFKD", str(nom)).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"\b(fc|cf|ac|sc|afc|ssc|as|fk|sk|bk|if|club|cd|ud|rcd|sd|ca|rc|sv|vfl|vfb|tsg|ogc|osc|kv|sl|"
               r"de|la|calcio|1907|1909|04|05|07)\b", " ", n)
    return re.sub(r"[^a-z0-9]", "", n)


def ressemblance(a: str, b: str) -> float:
    """0 à 1 : « Arsenal FC » ~ « Arsenal » = 1 ; « Man City » ~ « Man United » < 0,7."""
    import re
    from difflib import SequenceMatcher
    y = _norm(b)
    # Variantes du nom : tel quel, puis sans « FC », « AFC »… avant de consulter la table d'alias
    sans = re.sub(r"\b(FC|AFC|CF|SC|AC|FK|SK|BK|CD|SL)\b", "", str(a)).strip()
    meilleur = 0.0
    for v in {a, sans}:
        x = _norm(canon(v))
        if not x or not y:
            continue
        if x == y or (min(len(x), len(y)) >= 5 and (x in y or y in x)):
            return 1.0
        meilleur = max(meilleur, SequenceMatcher(None, x, y).ratio())
    return meilleur


def _ajouter_cotes_pinnacle(d: pd.DataFrame, racine: Path) -> pd.DataFrame:
    """Cotes Pinnacle (relevées juste avant les matchs, voir scripts/maj_cotes.py) rattachées au calendrier.
    Rattachement strict : même compétition, deux noms ressemblants (≥ 0,75 chacun) et un seul match candidat
    net, coup d'envoi à moins de 6 h. Si les deux noms correspondent EXACTEMENT, jusqu'à 4 jours d'écart :
    le match a été déplacé (télévisions) et la date/heure de Pinnacle, plus récente, remplace celle du
    calendrier. Les cotes Pinnacle remplacent alors les cotes Bet365."""
    ce = _lire(racine / "cotes_pinnacle.csv")
    if not len(ce):
        return d
    ce["instant"] = pd.to_datetime(ce["DateUtc"], utc=True, errors="coerce")
    if "releve" not in ce.columns:
        ce["releve"] = pd.NA
    for _, c in ce.dropna(subset=["instant"]).iterrows():
        cand = d[(d["competition"] == c["competition"])
                 & ((d["instant"] - c["instant"]).abs() < pd.Timedelta(days=4))]
        scores = []
        for i, r in cand.iterrows():
            sc = min(ressemblance(c["HomeTeam"], r["dom"]), ressemblance(c["AwayTeam"], r["ext"]))
            proche = abs(r["instant"] - c["instant"]) < pd.Timedelta(hours=6)
            if sc >= 0.999 or (proche and sc >= 0.75):
                scores.append((sc, i))
        scores.sort(reverse=True)
        if not scores or (len(scores) > 1 and scores[1][0] >= scores[0][0] - 0.05):
            continue
        i = scores[0][1]
        if abs(d.at[i, "instant"] - c["instant"]) >= pd.Timedelta(hours=6):
            d.at[i, "instant"] = c["instant"]       # match déplacé : on suit Pinnacle
            d.at[i, "heure_connue"] = True
        for col in COTES:
            d.at[i, col] = c[col]
        d.at[i, "bookmaker"] = "Pinnacle"
        d.at[i, "releve"] = c["releve"]
    return d


def _en_utc(jour: pd.Series, heure: pd.Series, fuseau: str) -> pd.Series:
    """Date + heure locales d'un fuseau -> instant UTC (gère le changement d'heure)."""
    h = heure.fillna("").astype(str).str.slice(0, 5)
    texte = jour.astype(str) + " " + h.where(h.str.match(r"^\d{1,2}:\d{2}$"), "12:00")
    locale = pd.to_datetime(texte, errors="coerce", format="mixed")
    return locale.dt.tz_localize(ZoneInfo(fuseau), ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert(UTC)


def _lire(chemin: Path) -> pd.DataFrame:
    return pd.read_csv(chemin) if chemin.exists() else pd.DataFrame()


def charger(racine: Path = RACINE, depuis: date | None = None) -> pd.DataFrame:
    morceaux = []
    fd = _lire(racine / "a_venir_championnats.csv")
    if len(fd):
        fd["instant"] = _en_utc(fd["Date"], fd.get("Heure_UK", pd.Series([""] * len(fd))), "Europe/London")
        fd["source"], fd["priorite"] = "football-data", 0
        fd["heure_connue"] = fd.get("Heure_UK", pd.Series([""] * len(fd))).astype(str).str.match(r"^\d{1,2}:\d{2}")
        morceaux.append(fd)
    wiki = _lire(racine / "a_venir.csv")
    if len(wiki):
        wiki["instant"] = _en_utc(wiki["Date"], wiki.get("Heure_CET", pd.Series([""] * len(wiki))), "Europe/Paris")
        wiki["source"], wiki["priorite"] = "wikipedia", 1
        wiki["heure_connue"] = wiki.get("Heure_CET", pd.Series([""] * len(wiki))).astype(str).str.match(r"^\d{1,2}:\d{2}")
        morceaux.append(wiki)
    saison = _lire(racine / "calendrier_saison.csv")
    if len(saison):
        saison["instant"] = pd.to_datetime(saison["DateUtc"], utc=True, errors="coerce")
        saison["source"], saison["priorite"] = "saison", 2
        saison["heure_connue"] = True
        morceaux.append(saison)
    if not morceaux:
        return pd.DataFrame(columns=COLONNES)

    d = pd.concat(morceaux, ignore_index=True).dropna(subset=["instant"])
    d["dom"] = d["HomeTeam"].map(canon)
    d["ext"] = d["AwayTeam"].map(canon)
    # Dédoublonnage : on parcourt par priorité ; un match déjà vu à moins de 3 jours est écarté
    d = d.sort_values(["priorite", "instant"], kind="mergesort")
    vus: dict[tuple, list] = {}
    garder = []
    for idx, cle, t in zip(d.index, zip(d["competition"], d["dom"], d["ext"]), d["instant"]):
        deja = vus.setdefault(cle, [])
        if any(abs((t - u).total_seconds()) < 3 * 86400 for u in deja):
            continue
        deja.append(t)
        garder.append(idx)
    d = d.loc[garder]
    if "bookmaker" not in d.columns:
        d["bookmaker"] = pd.NA
    d.loc[d["source"] == "football-data", "bookmaker"] = "Bet365"
    for col in COTES:
        if col not in d.columns:
            d[col] = pd.NA
    d["releve"] = pd.NA
    d = _ajouter_cotes_pinnacle(d, racine)

    depuis = depuis or date.today()
    d = d[d["instant"].dt.date >= depuis - timedelta(days=1)]
    d["Date"] = d["instant"].dt.strftime("%Y-%m-%d")
    # Heure inconnue (Wikipédia sans heure) -> vide plutôt qu'un faux « 12:00 »
    d["Heure"] = d["instant"].dt.strftime("%H:%M").where(d["heure_connue"].fillna(False).astype(bool), "")
    for c in COLONNES:
        if c not in d.columns:
            d[c] = pd.NA
    return d.sort_values(["instant", "competition", "dom"], kind="mergesort")[COLONNES].reset_index(drop=True)
