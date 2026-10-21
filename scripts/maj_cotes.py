"""
Kateni — cotes Pinnacle relevées JUSTE AVANT les matchs (OddsPapi)
====================================================================
Pinnacle est le bookmaker de référence ; ses cotes intègrent vite les absences (blessures, suspensions,
compositions publiées environ 1 h avant le coup d'envoi). Le pronostic de Kateni étant à 75 % le marché,
relever la cote au bon moment fait entrer les absences dans la prédiction.

Contraintes OddsPapi (offre gratuite) : 250 requêtes par mois, 5 compétitions au plus par appel.
Stratégie :
  --fenetre (passage horaire 10 h-20 h) : seulement les compétitions dont un match commence dans 20 à 80 min
  --matin   (passage de 5 h 15)         : C1 et C3 si elles jouent dans les 36 h (cotes de la veille)
Rythme : si la consommation du mois dépasse le rythme prévu, seules les compétitions prioritaires sont
relevées ; plafond dur à 230 requêtes. La clé vient de ODDS_API_KEY ou de .streamlit/secrets.toml et
n'est jamais affichée. En cas d'échec, les cotes déjà relevées sont conservées.
"""

import argparse
import calendar
import json
import os
import sys
import tomllib
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
SORTIE = RACINE / "cotes_pinnacle.csv"
EQUIPES = RACINE / "oddspapi_equipes.json"   # identifiant OddsPapi -> nom (cache, évite des requêtes)
API = "https://api.oddspapi.io/v4"
BOOKMAKER = "pinnacle"
LIMITE_SURE = 230
PAR_APPEL = 5

# Identifiants OddsPapi (liste complète : docs/mesures/oddspapi_tournois.json, relevée le 21/10/2026)
TOURNOIS = {"CL": 7, "EL": 679, "PL": 17, "LIGA": 8, "SA": 23, "BL": 35, "L1": 34, "NED": 37, "POR": 238,
            "TUR": 52, "BEL": 38, "CHAMP": 18, "LIGA2": 54, "L2": 182, "SCO": 36, "GRE": 185, "AUT": 45,
            "SUI": 215, "NOR": 20, "DAN": 39, "SUE": 40, "POL": 202, "ROU": 152, "MLS": 242}
PRIORITAIRES = ["CL", "EL", "PL", "LIGA", "SA", "BL", "L1"]   # gardées même quand le budget se resserre
ORDRE = list(TOURNOIS)                                       # ordre de priorité pour former les lots de 5


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
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def prix(marches: dict, marche: str, issue: str) -> float | None:
    try:
        joueur = marches[marche]["outcomes"][issue]["players"]["0"]
        return float(joueur["price"]) if joueur.get("active", True) else None
    except (KeyError, TypeError, ValueError):
        return None


def a_relever(mode: str, maintenant: datetime) -> list[str]:
    """Compétitions qui ont un match dans la fenêtre utile, d'après le calendrier de Kateni."""
    from kateni.calendrier import charger
    cal = charger()
    if not len(cal):
        return []
    debut = pd.to_datetime(cal["Date"] + " " + cal["Heure"].replace("", "12:00"), utc=True, errors="coerce")
    if mode == "fenetre":
        dans = (debut > maintenant + timedelta(minutes=20)) & (debut <= maintenant + timedelta(minutes=80))
        codes = set(cal.loc[dans, "competition"])
    else:  # matin : C1/C3 du jour et du lendemain
        dans = (debut > maintenant) & (debut <= maintenant + timedelta(hours=36))
        codes = set(cal.loc[dans, "competition"]) & {"CL", "EL"}
    return [c for c in ORDRE if c in codes]


def dans_le_rythme(utilisees: int, maintenant: datetime) -> bool:
    """Vrai si la consommation du mois suit le rythme prévu (230 requêtes réparties sur le mois)."""
    jours = calendar.monthrange(maintenant.year, maintenant.month)[1]
    return utilisees <= LIMITE_SURE * maintenant.day / jours + 10


def main(mode: str = "fenetre", forcer: list[str] | None = None):
    maintenant = datetime.now(timezone.utc)
    codes = [c for c in ORDRE if c in (forcer or [])] if forcer else a_relever(mode, maintenant)
    if not codes:
        print(f"Cotes Pinnacle ({mode}) : aucun match dans la fenêtre — aucune requête.")
        return
    k = cle()
    if not k:
        print("Cotes Pinnacle : pas de clé OddsPapi configurée — étape ignorée.")
        return
    try:
        compte = appel("account", k)  # gratuit, jamais décompté
        sub = next(s for s in compte["subscriptions"] if s["subscription_id"] == compte["current_subscription_id"])
        utilisees, limite = sub["request_count"], sub["request_limit"]
    except Exception as e:
        print(f"Cotes Pinnacle : compte OddsPapi illisible ({type(e).__name__}) — cotes précédentes conservées.")
        return
    if not dans_le_rythme(utilisees, maintenant):
        codes = [c for c in codes if c in PRIORITAIRES]
        print(f"Cotes Pinnacle : rythme du mois dépassé ({utilisees} requêtes) — compétitions prioritaires seules.")
    lots = [codes[i:i + PAR_APPEL] for i in range(0, len(codes), PAR_APPEL)]

    matchs, faits, depense = [], [], 0
    for lot in lots:
        if utilisees + depense >= min(LIMITE_SURE, limite - 5):
            print(f"Cotes Pinnacle : plafond atteint ({utilisees + depense}/{limite}) — arrêt.")
            break
        try:
            matchs += appel("odds-by-tournaments", k, bookmaker=BOOKMAKER,
                            tournamentIds=",".join(str(TOURNOIS[c]) for c in lot), oddsFormat="decimal")
            faits += lot
        except Exception as e:
            print(f"Cotes Pinnacle : échec pour {lot} ({type(e).__name__} {getattr(e, 'code', '')}).")
        depense += 1
    if not faits:
        return

    noms = json.loads(EQUIPES.read_text(encoding="utf-8")) if EQUIPES.exists() else {}
    manquants = {str(m[c]) for m in matchs for c in ("participant1Id", "participant2Id")} - set(noms)
    if manquants and utilisees + depense < min(LIMITE_SURE, limite - 5):
        try:
            tous = appel("participants", k, sportId=10)
            depense += 1
            noms.update({i: tous[i] for i in manquants if i in tous})
            EQUIPES.write_text(json.dumps(dict(sorted(noms.items())), ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:
            print(f"Cotes Pinnacle : noms d'équipes indisponibles ({type(e).__name__}).")

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
    # Fusion : on remplace les lignes des compétitions relevées, on garde les autres ; on oublie le passé
    ancien = pd.read_csv(SORTIE) if SORTIE.exists() else pd.DataFrame(columns=["competition", "DateUtc"])
    garde = ancien[~ancien["competition"].isin(faits)]
    neuf = pd.concat([garde, pd.DataFrame(lignes)], ignore_index=True)
    neuf = neuf[pd.to_datetime(neuf["DateUtc"], utc=True, errors="coerce") > maintenant - timedelta(days=1)]
    neuf = neuf.sort_values(["DateUtc", "competition", "HomeTeam"], kind="mergesort")
    neuf.to_csv(SORTIE, index=False)
    print(f"Cotes Pinnacle ({mode}) : {', '.join(faits)} — {len(lignes)} matchs relevés · "
          f"requêtes OddsPapi : {utilisees + depense}/{limite} ce mois-ci")
    rapport_rattachement(pd.DataFrame(lignes))


def rapport_rattachement(lignes: pd.DataFrame) -> None:
    """Liste les cotes relevées qui ne se rattachent à aucun match du calendrier (nom d'équipe à ajouter
    dans equipes_alias.csv). Ne coûte aucune requête."""
    from kateni.calendrier import charger
    if not len(lignes):
        return
    cal = charger()
    pin = cal[cal["bookmaker"] == "Pinnacle"]
    cles = set(zip(pin["competition"], pin["B365H"].astype(float).round(3), pin["B365A"].astype(float).round(3)))
    seuls = [r for _, r in lignes.iterrows()
             if (r["competition"], round(float(r["B365H"] or 0), 3), round(float(r["B365A"] or 0), 3)) not in cles]
    print(f"Rattachement au calendrier : {len(lignes) - len(seuls)}/{len(lignes)} matchs")
    for r in seuls:
        print(f"  non rattaché : {r['competition']} {str(r['DateUtc'])[:16]} {r['HomeTeam']} – {r['AwayTeam']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["fenetre", "matin"], default="fenetre")
    ap.add_argument("--competitions", nargs="*", help="relevé manuel de ces compétitions (ex. : PL LIGA)")
    a = ap.parse_args()
    sys.exit(main(a.mode, a.competitions))
