"""
Kateni — cotes de Ligue des champions et Ligue Europa (OddsPapi, bookmaker Pinnacle)
=====================================================================================
football-data ne publie pas de cotes pour les coupes d'Europe : ce script les récupère chez OddsPapi
(offre gratuite : 250 requêtes par mois, remises à zéro le 1er du mois).

Coût : 1 requête par passage (C1 et C3 ensemble) + 1 requête si une nouvelle équipe apparaît.
Deux passages par jour ≈ 60 requêtes par mois. Garde-fou : rien n'est demandé au-delà de 230.
La clé vient de la variable ODDS_API_KEY (robot GitHub) ou de .streamlit/secrets.toml (Mac) ;
elle n'est jamais affichée ni écrite dans un fichier suivi par Git.

Produit cotes_europe.csv (lu par kateni/calendrier.py). En cas d'échec, l'ancien fichier est conservé.
"""

import json
import os
import sys
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / "cotes_europe.csv"
EQUIPES = RACINE / "oddspapi_equipes.json"   # identifiant OddsPapi -> nom (cache, évite des requêtes)
TOURNOIS = {7: "CL", 679: "EL"}               # identifiants OddsPapi (référence du 21/10/2026)
BOOKMAKER = "pinnacle"
LIMITE_SURE = 230                             # sur 250 requêtes gratuites par mois
API = "https://api.oddspapi.io/v4"


def cle() -> str | None:
    if os.environ.get("ODDS_API_KEY"):
        return os.environ["ODDS_API_KEY"]
    s = RACINE / ".streamlit" / "secrets.toml"
    if s.exists():
        return tomllib.loads(s.read_text(encoding="utf-8")).get("odds_api", {}).get("key")
    return None


def appel(chemin: str, k: str, **params):
    params["apiKey"] = k
    req = urllib.request.Request(f"{API}/{chemin}?{urllib.parse.urlencode(params)}",
                                 headers={"User-Agent": "Kateni/2 (usage personnel)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def prix(marches: dict, marche: str, issue: str) -> float | None:
    try:
        joueur = marches[marche]["outcomes"][issue]["players"]["0"]
        return float(joueur["price"]) if joueur.get("active", True) else None
    except (KeyError, TypeError, ValueError):
        return None


def main():
    k = cle()
    if not k:
        print("Cotes C1/C3 : pas de clé OddsPapi configurée — étape ignorée.")
        return
    try:
        compte = appel("account", k)  # gratuit, jamais décompté
        sub = next(s for s in compte["subscriptions"] if s["subscription_id"] == compte["current_subscription_id"])
        utilisees, limite = sub["request_count"], sub["request_limit"]
    except Exception as e:
        print(f"Cotes C1/C3 : compte OddsPapi illisible ({type(e).__name__}) — cotes précédentes conservées.")
        return
    if utilisees >= min(LIMITE_SURE, limite - 5):
        print(f"Cotes C1/C3 : budget du mois atteint ({utilisees}/{limite} requêtes) — cotes précédentes conservées.")
        return

    try:
        matchs = appel("odds-by-tournaments", k, bookmaker=BOOKMAKER,
                       tournamentIds=",".join(map(str, TOURNOIS)), oddsFormat="decimal")
    except Exception as e:
        print(f"Cotes C1/C3 : échec de la requête ({type(e).__name__} {getattr(e, 'code', '')}) — "
              "cotes précédentes conservées.")
        return
    depense = 1

    noms = json.loads(EQUIPES.read_text(encoding="utf-8")) if EQUIPES.exists() else {}
    manquants = {str(m[c]) for m in matchs for c in ("participant1Id", "participant2Id")} - set(noms)
    if manquants:
        try:
            tous = appel("participants", k, sportId=10)
            depense += 1
            noms.update({i: tous[i] for i in manquants if i in tous})
            EQUIPES.write_text(json.dumps(dict(sorted(noms.items())), ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:
            print(f"Cotes C1/C3 : noms d'équipes indisponibles ({type(e).__name__}) — matchs concernés ignorés.")

    lignes = []
    for m in matchs:
        dom, ext = noms.get(str(m["participant1Id"])), noms.get(str(m["participant2Id"]))
        bk = (m.get("bookmakerOdds") or {}).get(BOOKMAKER, {})
        mk = bk.get("markets", {})
        if not (dom and ext and mk):
            continue
        lignes.append({
            "competition": TOURNOIS.get(m["tournamentId"]), "DateUtc": m["startTime"],
            "HomeTeam": dom, "AwayTeam": ext,
            "B365H": prix(mk, "101", "101"), "B365D": prix(mk, "101", "102"), "B365A": prix(mk, "101", "103"),
            "B365>2.5": prix(mk, "1010", "1010"), "B365<2.5": prix(mk, "1010", "1011"),
            "BTTS_oui": prix(mk, "104", "104"), "BTTS_non": prix(mk, "104", "105"),
            "bookmaker": "Pinnacle",
        })
    if not lignes:
        print("Cotes C1/C3 : aucune cote publiée pour l'instant — cotes précédentes conservées.")
        return
    neuf = pd.DataFrame(lignes).sort_values(["DateUtc", "competition", "HomeTeam"], kind="mergesort")
    neuf.to_csv(SORTIE, index=False)
    print(f"Cotes C1/C3 : {len(neuf)} matchs (Pinnacle) · requêtes OddsPapi : {utilisees + depense}/{limite} ce mois-ci")


if __name__ == "__main__":
    sys.exit(main())
