"""
Kateni — relevé des cotes Pinnacle (OddsPapi), partagé par le robot (scripts/maj_cotes.py) et par l'app
=========================================================================================================
Pinnacle est le bookmaker de référence ; ses cotes intègrent vite les absences (blessures, suspensions,
compositions publiées environ 1 h avant le coup d'envoi). Le pronostic de Kateni étant à 75 % le marché,
relever la cote au bon moment fait entrer les absences dans la prédiction.

Contraintes OddsPapi (offre gratuite) : 250 requêtes par mois, 5 compétitions au plus par appel.
La clé n'est jamais affichée. En cas d'échec, les cotes déjà relevées sont conservées.
"""

import calendar
import json
import os
import tomllib
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

import pandas as pd

from kateni.config import RACINE

SORTIE = RACINE / "cotes_pinnacle.csv"
EQUIPES = RACINE / "oddspapi_equipes.json"   # identifiant OddsPapi -> nom (cache, évite des requêtes)
API = "https://api.oddspapi.io/v4"
BOOKMAKER = "pinnacle"
LIMITE_SURE = 230
PAR_APPEL = 5

# Identifiants OddsPapi (liste complète : docs/mesures/oddspapi_tournois.json, relevée le 21/10/2026)
TOURNOIS = {"CL": 7, "EL": 679, "ECL": 34480, "PL": 17, "LIGA": 8, "SA": 23, "BL": 35, "L1": 34, "NED": 37, "POR": 238,
            "TUR": 52, "BEL": 38, "CHAMP": 18, "LIGA2": 54, "L2": 182, "SCO": 36, "GRE": 185, "AUT": 45,
            "SUI": 215, "NOR": 20, "DAN": 39, "SUE": 40, "POL": 202, "ROU": 152, "MLS": 242,
            "BL2": 44, "CHN": 649, "JPN": 196, "IRL": 192}
PRIORITAIRES = ["CL", "EL", "PL", "LIGA", "SA", "BL", "L1"]   # gardées même quand le budget se resserre
ORDRE = list(TOURNOIS)                                       # ordre de priorité pour former les lots de 5


def cle(secrets: dict | None = None) -> str | None:
    """Clé OddsPapi : environnement (robot GitHub), secrets Streamlit (app en ligne), ou fichier du Mac."""
    if os.environ.get("ODDS_API_KEY"):
        return os.environ["ODDS_API_KEY"]
    if secrets and secrets.get("key"):
        return secrets["key"]
    s = RACINE / ".streamlit" / "secrets.toml"
    if s.exists():
        return tomllib.loads(s.read_text(encoding="utf-8")).get("odds_api", {}).get("key")
    return None


def appel(chemin: str, k: str, **params):
    params["apiKey"] = k
    req = urllib.request.Request(f"{API}/{chemin}?{urllib.parse.urlencode(params)}",
                                 headers={"User-Agent": "Kateni/2 (usage personnel)"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def prix(marches: dict, marche: str, issue: str) -> float | None:
    try:
        joueur = marches[marche]["outcomes"][issue]["players"]["0"]
        return float(joueur["price"]) if joueur.get("active", True) else None
    except (KeyError, TypeError, ValueError):
        return None


def compte(k: str) -> tuple[int, int]:
    """(requêtes utilisées ce mois-ci, limite). Appel gratuit, jamais décompté."""
    c = appel("account", k)
    sub = next(s for s in c["subscriptions"] if s["subscription_id"] == c["current_subscription_id"])
    return sub["request_count"], sub["request_limit"]


def dans_le_rythme(utilisees: int, maintenant: datetime) -> bool:
    """Vrai si la consommation du mois suit le rythme prévu (230 requêtes réparties sur le mois)."""
    jours = calendar.monthrange(maintenant.year, maintenant.month)[1]
    return utilisees <= LIMITE_SURE * maintenant.day / jours + 10


def relever(codes: list[str], k: str, utilisees: int, limite: int, maintenant: datetime,
            journal=print) -> tuple[list[dict], list[str], int]:
    """Relève les cotes des compétitions `codes` (par lots de 5). Rend (lignes, compétitions faites, requêtes)."""
    lots = [codes[i:i + PAR_APPEL] for i in range(0, len(codes), PAR_APPEL)]
    matchs, faits, depense = [], [], 0
    for lot in lots:
        if utilisees + depense >= min(LIMITE_SURE, limite - 5):
            journal(f"Cotes Pinnacle : plafond atteint ({utilisees + depense}/{limite}) — arrêt.")
            break
        try:
            matchs += appel("odds-by-tournaments", k, bookmaker=BOOKMAKER,
                            tournamentIds=",".join(str(TOURNOIS[c]) for c in lot), oddsFormat="decimal")
            faits += lot
        except Exception as e:
            journal(f"Cotes Pinnacle : échec pour {lot} ({type(e).__name__} {getattr(e, 'code', '')}).")
        depense += 1
    if not faits:
        return [], [], depense

    noms = json.loads(EQUIPES.read_text(encoding="utf-8")) if EQUIPES.exists() else {}
    manquants = {str(m[c]) for m in matchs for c in ("participant1Id", "participant2Id")} - set(noms)
    if manquants and utilisees + depense < min(LIMITE_SURE, limite - 5):
        try:
            tous = appel("participants", k, sportId=10)
            depense += 1
            noms.update({i: tous[i] for i in manquants if i in tous})
            EQUIPES.write_text(json.dumps(dict(sorted(noms.items())), ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:
            journal(f"Cotes Pinnacle : noms d'équipes indisponibles ({type(e).__name__}).")

    code_de = {v: k_ for k_, v in TOURNOIS.items()}
    releve = maintenant.strftime("%Y-%m-%d %H:%M")  # UTC = heure d'Abidjan
    lignes = []
    for m in matchs:
        dom, ext = noms.get(str(m["participant1Id"])), noms.get(str(m["participant2Id"]))
        mk = ((m.get("bookmakerOdds") or {}).get(BOOKMAKER) or {}).get("markets", {})
        if not (dom and ext and mk):
            continue
        lignes.append({
            "competition": code_de.get(m["tournamentId"]), "DateUtc": m["startTime"], "HomeTeam": dom, "AwayTeam": ext,
            "B365H": prix(mk, "101", "101"), "B365D": prix(mk, "101", "102"), "B365A": prix(mk, "101", "103"),
            "B365>2.5": prix(mk, "1010", "1010"), "B365<2.5": prix(mk, "1010", "1011"),
            "BTTS_oui": prix(mk, "104", "104"), "BTTS_non": prix(mk, "104", "105"),
            "bookmaker": "Pinnacle", "releve": releve,
        })
    return lignes, faits, depense


def enregistrer(lignes: list[dict], faits: list[str], maintenant: datetime) -> None:
    """Remplace les lignes des compétitions relevées, garde les autres ; oublie le passé."""
    ancien = pd.read_csv(SORTIE) if SORTIE.exists() else pd.DataFrame(columns=["competition", "DateUtc"])
    garde = ancien[~ancien["competition"].isin(faits)]
    neuf = pd.concat([garde, pd.DataFrame(lignes)], ignore_index=True)
    neuf = neuf[pd.to_datetime(neuf["DateUtc"], utc=True, errors="coerce") > maintenant - timedelta(days=1)]
    neuf = neuf.sort_values(["DateUtc", "competition", "HomeTeam"], kind="mergesort")
    neuf.to_csv(SORTIE, index=False)
