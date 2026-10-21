"""
Kateni — calendrier unifié des matchs à venir, en heure d'Abidjan (UTC, sans changement d'heure)
==================================================================================================
Trois sources, de la plus riche à la plus lointaine :
  1. a_venir_championnats.csv (football-data) : quelques jours à l'avance, AVEC les cotes ; heure de Londres
  2. a_venir.csv (Wikipédia) : C1 et C3 ; heure de Paris
  3. calendrier_saison.csv (fixturedownload) : toute la saison ; déjà en UTC
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
            "B365H", "B365D", "B365A", "B365>2.5", "B365<2.5"]


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

    depuis = depuis or date.today()
    d = d[d["instant"].dt.date >= depuis - timedelta(days=1)]
    d["Date"] = d["instant"].dt.strftime("%Y-%m-%d")
    # Heure inconnue (Wikipédia sans heure) -> vide plutôt qu'un faux « 12:00 »
    d["Heure"] = d["instant"].dt.strftime("%H:%M").where(d["heure_connue"].fillna(False).astype(bool), "")
    for c in COLONNES:
        if c not in d.columns:
            d[c] = pd.NA
    return d.sort_values(["instant", "competition", "dom"], kind="mergesort")[COLONNES].reset_index(drop=True)
