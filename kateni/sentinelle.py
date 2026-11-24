"""
Kateni — sentinelle des données (24/11/2026)
=============================================
Repère un championnat dont les résultats n'arrivent plus alors qu'il est en pleine saison (exemple réel : la
source football-data n'a rien publié du 08/11 au 24/11/2026 pour l'Autriche, la Suisse, l'Argentine…).

Règle, pour chaque championnat (foot) ou ligue (basket) :
  - « en saison » : au moins 6 journées de match dans les 60 derniers jours ;
  - « en retard » : aucun résultat depuis plus de max(10 jours, 3 × l'écart habituel entre deux journées) ;
  - et « attendu » : l'an dernier, à la même période (du dernier résultat à aujourd'hui), le championnat avait
    joué au moins 2 jours de match (évite les fausses alertes de fin de saison et de trêve propre au championnat) ;
  - trêve générale : si plus de la moitié des championnats en saison sont « en retard » en même temps, c'est une
    trêve (internationale, Noël), pas une panne : aucune alerte.
Le robot écrit alertes_donnees.json ; l'app l'affiche au propriétaire (page Calendrier).
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd

FICHIER = "alertes_donnees.json"


def _retard(dates: pd.Series, aujourd_hui: pd.Timestamp) -> dict | None:
    jours = pd.Series(sorted(pd.to_datetime(dates).dt.normalize().unique()))
    recents = jours[jours >= aujourd_hui - pd.Timedelta(days=60)]
    if len(recents) < 6:
        return None  # hors saison ou trop peu de matchs pour juger
    ecart = float(recents.diff().dt.days.median())
    seuil = max(10.0, 3 * ecart)
    attente = (aujourd_hui - jours.iloc[-1]).days
    an = pd.Timedelta(days=364)  # même jour de la semaine, un an plus tôt
    l_an_dernier = int(((jours > jours.iloc[-1] - an) & (jours <= aujourd_hui - an)).sum())
    return {"dernier": f"{jours.iloc[-1]:%d/%m/%Y}", "jours": int(attente), "seuil": int(seuil),
            "jours_de_match_l_an_dernier": l_an_dernier, "en_retard": attente > seuil and l_an_dernier >= 2}


def verifier(foot: pd.DataFrame, basket: pd.DataFrame | None = None, aujourd_hui: date | None = None) -> dict:
    """foot : colonnes competition, Date ; basket : colonnes ligue, DateUtc. Renvoie {"alertes": [...], "treve": bool}."""
    auj = pd.Timestamp(aujourd_hui or date.today())
    etats = {}
    for code, g in foot.groupby("competition"):
        if code in ("INT", "INTN"):  # sélections : fenêtres internationales, irrégulières par nature
            continue
        r = _retard(g["Date"], auj)
        if r:
            etats[code] = r
    if basket is not None and len(basket):
        t = pd.to_datetime(basket["DateUtc"], utc=True, format="ISO8601").dt.tz_convert(None)
        for lg, g in t.groupby(basket["ligue"]):
            r = _retard(g, auj)
            if r:
                etats[lg] = r
    en_retard = {k: v for k, v in etats.items() if v["en_retard"]}
    treve = len(etats) > 0 and len(en_retard) > len(etats) / 2
    alertes = [] if treve else [{"championnat": k, **v} for k, v in sorted(en_retard.items())]
    return {"verifie_le": f"{auj:%d/%m/%Y}", "en_saison": len(etats), "treve": treve, "alertes": alertes}


def ecrire(resultat: dict, chemin) -> None:
    chemin.write_text(json.dumps(resultat, ensure_ascii=False, indent=1), encoding="utf-8")
