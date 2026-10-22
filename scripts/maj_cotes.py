"""
Kateni — cotes Pinnacle relevées JUSTE AVANT les matchs (OddsPapi)
====================================================================
Pinnacle est le bookmaker de référence ; ses cotes intègrent vite les absences (blessures, suspensions,
compositions publiées environ 1 h avant le coup d'envoi). Le pronostic de Kateni étant à 75 % le marché,
relever la cote au bon moment fait entrer les absences dans la prédiction.

Contraintes OddsPapi (offre gratuite) : 250 requêtes par mois, 5 compétitions au plus par appel.
Le code du relevé est dans kateni/pinnacle.py (partagé avec l'app, qui relève aussi elle-même les cotes
quand on l'ouvre peu avant un match : voir kateni/ui.py, cotes_imminentes). Stratégie :
  --fenetre (passage horaire 10 h-20 h) : seulement les compétitions dont un match commence dans 20 à 80 min
  --matin   (passage de 5 h 15)         : C1, C3 et Ligue Conférence si elles jouent dans les 36 h (cotes de la veille)
Rythme : si la consommation du mois dépasse le rythme prévu, seules les compétitions prioritaires sont
relevées ; plafond dur à 230 requêtes. La clé vient de ODDS_API_KEY ou de .streamlit/secrets.toml et
n'est jamais affichée. En cas d'échec, les cotes déjà relevées sont conservées.
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from kateni.pinnacle import (ORDRE, PRIORITAIRES, cle, compte, dans_le_rythme, enregistrer,  # noqa: E402,F401
                             relever)


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
        codes = set(cal.loc[dans, "competition"]) & {"CL", "EL", "ECL"}
    return [c for c in ORDRE if c in codes]


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
        utilisees, limite = compte(k)
    except Exception as e:
        print(f"Cotes Pinnacle : compte OddsPapi illisible ({type(e).__name__}) — cotes précédentes conservées.")
        return
    if not dans_le_rythme(utilisees, maintenant):
        codes = [c for c in codes if c in PRIORITAIRES]
        print(f"Cotes Pinnacle : rythme du mois dépassé ({utilisees} requêtes) — compétitions prioritaires seules.")
    lignes, faits, depense = relever(codes, k, utilisees, limite, maintenant)
    if not faits:
        return
    enregistrer(lignes, faits, maintenant)
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
