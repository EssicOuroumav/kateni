"""
Kateni — scores en direct (source gratuite : tableau des scores public d'ESPN)
==============================================================================
Score, minute et cartons rouges des matchs en cours, pour les compétitions suivies par Kateni.
Source non officielle et sans clé : si elle ne répond pas ou change de format, la page Live revient à la
saisie à la main (aucune erreur affichée). Rien n'est envoyé : simple lecture publique.
"""

import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from kateni.config import ESPN_INTER, NOMS_INTER

API = "https://site.api.espn.com/apis/site/v2/sports/soccer/{}/scoreboard"
# Code Kateni -> ligue ESPN (la Pologne n'est pas proposée par la source)
LIGUES = {"PL": "eng.1", "LIGA": "esp.1", "L1": "fra.1", "SA": "ita.1", "BL": "ger.1", "NED": "ned.1",
          "POR": "por.1", "TUR": "tur.1", "BEL": "bel.1", "CHAMP": "eng.2", "LIGA2": "esp.2", "L2": "fra.2",
          "MLS": "usa.1", "SCO": "sco.1", "GRE": "gre.1", "AUT": "aut.1", "SUI": "sui.1", "NOR": "nor.1",
          "DAN": "den.1", "SUE": "swe.1", "ROU": "rou.1", "BL2": "ger.2", "CHN": "chn.1", "JPN": "jpn.1",
          "IRL": "irl.1", "AUS": "aus.1", "ARG": "arg.1", "BRA": "bra.1", "MEX": "mex.1",
          "RUS": "rus.1", "INT": ESPN_INTER, "CL": "uefa.champions", "EL": "uefa.europa", "ECL": "uefa.europa.conf"}


# Statistiques du moment fournies par la source -> noms de Kateni
# (corners et fautes retirés de l'app le 07/11/2026)
STATS_SOURCE = {"Tirs": "totalShots", "Tirs cadrés": "shotsOnTarget"}


def _stat(equipe: dict, nom: str) -> int | None:
    for s in equipe.get("statistics", []):
        if s.get("name") == nom:
            try:
                return int(float(s.get("displayValue")))
            except (TypeError, ValueError):
                return None
    return None


def _lire(ligue: str) -> dict:
    req = urllib.request.Request(API.format(ligue), headers={"User-Agent": "Kateni/2 (usage personnel)"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.load(r)


def minute_de(statut: dict) -> tuple[int, str]:
    """(minute de jeu, texte affiché) à partir du statut ESPN : « 17' », « 45'+2' », mi-temps…"""
    nom = statut.get("type", {}).get("name", "")
    if nom == "STATUS_HALFTIME":
        return 45, "mi-temps"
    horloge = str(statut.get("displayClock") or "")
    m = re.match(r"\s*(\d+)'?(?:\s*\+\s*(\d+))?", horloge)
    if not m:
        return 0, horloge
    minute = int(m.group(1))
    return min(minute, 120), (f"{minute}'+{m.group(2)}'" if m.group(2) else f"{minute}'")


def matchs_de(code: str, donnees: dict) -> list[dict]:
    """Matchs EN COURS d'une ligue (tableau ESPN déjà lu)."""
    out = []
    for e in donnees.get("events", []):
        statut = e.get("status", {})
        if statut.get("type", {}).get("state") != "in":
            continue
        c = (e.get("competitions") or [{}])[0]
        equipes = {x.get("homeAway"): x for x in c.get("competitors", [])}
        if "home" not in equipes or "away" not in equipes:
            continue
        ids = {equipes["home"]["team"]["id"]: "d", equipes["away"]["team"]["id"]: "e"}
        rouges = {"d": 0, "e": 0}
        for detail in c.get("details", []):
            if detail.get("redCard") and detail.get("team", {}).get("id") in ids:
                rouges[ids[detail["team"]["id"]]] += 1
        stats = {}
        for nom, cle in STATS_SOURCE.items():
            v = [_stat(equipes[c], cle) for c in ("home", "away")]
            if None not in v:
                stats[nom] = tuple(v)
        minute, texte = minute_de(statut)
        try:
            buts_d, buts_e = int(equipes["home"].get("score") or 0), int(equipes["away"].get("score") or 0)
        except ValueError:
            continue
        out.append({"competition": code, "dom_source": equipes["home"]["team"].get("displayName", ""),
                    "ext_source": equipes["away"]["team"].get("displayName", ""),
                    "buts_d": buts_d, "buts_e": buts_e, "minute": minute, "minute_texte": texte,
                    "rouges_d": rouges["d"], "rouges_e": rouges["e"], "stats": stats})
    return out


def en_direct(codes: list[str] | None = None) -> list[dict] | None:
    """Tous les matchs en cours des compétitions demandées ; None si la source ne répond pas du tout."""
    codes = [c for c in (codes or LIGUES) if c in LIGUES]
    resultats, echecs = [], 0

    def un(code):
        ligues = LIGUES[code] if isinstance(LIGUES[code], tuple) else (LIGUES[code],)
        out, ok = [], False
        for ligue in ligues:  # sélections nationales : plusieurs compétitions ESPN
            try:
                out += matchs_de(code, _lire(ligue))
                ok = True
            except Exception:  # réseau, format inattendu : cette compétition est ignorée
                continue
        for m in out:
            m["dom_source"] = NOMS_INTER.get(m["dom_source"], m["dom_source"])
            m["ext_source"] = NOMS_INTER.get(m["ext_source"], m["ext_source"])
        return out if ok else None

    with ThreadPoolExecutor(max_workers=8) as pool:
        for r in pool.map(un, codes):
            if r is None:
                echecs += 1
            else:
                resultats += r
    return None if codes and echecs == len(codes) else resultats


def rattacher(direct: dict, candidats: list[tuple[str, str]], ressemblance) -> tuple[str, str] | None:
    """Trouve, parmi les affiches (dom, ext) de Kateni, celle qui correspond au match de la source."""
    meilleur, score = None, 0.0
    for dom, ext in candidats:
        s = min(ressemblance(direct["dom_source"], dom), ressemblance(direct["ext_source"], ext))
        if s > score:
            meilleur, score = (dom, ext), s
    return meilleur if score >= 0.6 else None
