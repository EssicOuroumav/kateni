"""
Kateni — résultats et calendrier européens (C1, C3) depuis Wikipédia
======================================================================
Aucune source gratuite en CSV n'est à jour pour la saison 2026-27 :
on lit les « Football box » des pages Wikipédia (anglais) de la phase de
ligue, via l'API officielle de Wikipédia (texte brut, pas de scraping HTML).

Produit :
  - CL_full.csv / EL_full.csv : matchs joués ajoutés (saison 2026-27)
  - a_venir.csv               : matchs pas encore joués (pour l'onglet « Mes paris »)
  - buts_minutes.csv          : minute de chaque but (servira à calibrer le module live)

Usage :
    python3 scripts/maj_europe.py
"""

import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kateni.config import COMPETITIONS, RACINE  # noqa: E402

SAISON = "2026-27"
PAGES = {
    "CL": f"{SAISON.replace('-', '–')} UEFA Champions League league phase",
    "EL": f"{SAISON.replace('-', '–')} UEFA Europa League league phase",
}
API = "https://en.wikipedia.org/w/api.php"

RE_BOX = re.compile(r"\{\{#invoke:Football box\|main(.*?)\n\}\}", re.S)
RE_CHAMP = re.compile(r"^\|(\w+)\s*=\s*(.*?)(?=^\|\w+\s*=|\Z)", re.S | re.M)
RE_LIEN = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]+)\]\]")
RE_DATE = re.compile(r"Start date\|(\d{4})\|(\d{1,2})\|(\d{1,2})")
RE_SCORE = re.compile(r"(\d+)\s*[–−-]\s*(\d+)")
RE_BUT = re.compile(r"\{\{goal\|([^}]*)\}\}")


def wikitexte(titre: str) -> str:
    params = urllib.parse.urlencode({"action": "parse", "page": titre, "prop": "wikitext",
                                     "format": "json", "formatversion": "2"})
    req = urllib.request.Request(f"{API}?{params}", headers={"User-Agent": "Kateni/2 (usage personnel)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["parse"]["wikitext"]


def nom_equipe(brut: str) -> str:
    brut = re.sub(r"\{\{fbaicon\|\w+\}\}", "", brut)
    m = RE_LIEN.search(brut)
    return (m.group(1) if m else brut).strip()


def minutes_buts(brut: str) -> list[int]:
    """'{{goal|80||85|pen.}}' -> [80, 85] ; '90+3' -> 90 (temps additionnel ramené à 90)."""
    minutes = []
    for bloc in RE_BUT.findall(brut):
        for morceau in bloc.split("|"):
            m = re.match(r"^\s*(\d+)(?:\+\d+)?\s*$", morceau)
            if m:
                minutes.append(int(m.group(1)))
    return minutes


def parser(texte: str) -> tuple[list[dict], list[dict], list[dict]]:
    joues, a_venir, buts = [], [], []
    for box in RE_BOX.findall(texte):
        champs = {k: v.strip() for k, v in RE_CHAMP.findall(box)}
        d = RE_DATE.search(champs.get("date", ""))
        if not d or "team1" not in champs:
            continue
        date = f"{d.group(1)}-{int(d.group(2)):02d}-{int(d.group(3)):02d}"
        home, away = nom_equipe(champs["team1"]), nom_equipe(champs["team2"])
        heure = re.match(r"(\d{1,2}:\d{2})", champs.get("time", ""))
        s = RE_SCORE.search(re.sub(r"<ref.*?</ref>|<ref[^>]*/>", "", champs.get("score", "")))
        if s:
            fthg, ftag = int(s.group(1)), int(s.group(2))
            ftr = "H" if fthg > ftag else ("A" if ftag > fthg else "D")
            m_h, m_a = minutes_buts(champs.get("goals1", "")), minutes_buts(champs.get("goals2", ""))
            ht_h, ht_a = sum(m <= 45 for m in m_h), sum(m <= 45 for m in m_a)
            ligne = {"Date": date, "HomeTeam": home, "AwayTeam": away, "FTHG": fthg, "FTAG": ftag,
                     "FTR": ftr, "Saison": SAISON}
            # Mi-temps seulement si les minutes sont complètes (sinon on ne devine pas)
            if len(m_h) == fthg and len(m_a) == ftag:
                ligne.update({"HTHG": ht_h, "HTAG": ht_a})
                buts += [{"Date": date, "HomeTeam": home, "AwayTeam": away, "equipe": "H", "minute": m}
                         for m in m_h]
                buts += [{"Date": date, "HomeTeam": home, "AwayTeam": away, "equipe": "A", "minute": m}
                         for m in m_a]
            joues.append(ligne)
        else:
            a_venir.append({"Date": date, "Heure_CET": heure.group(1) if heure else "",
                            "HomeTeam": home, "AwayTeam": away})
    return joues, a_venir, buts


def main():
    tous_a_venir, tous_buts = [], []
    for code, titre in PAGES.items():
        comp = COMPETITIONS[code]
        try:
            joues, a_venir, buts = parser(wikitexte(titre))
        except Exception as e:
            print(f"{comp.nom} : échec de lecture Wikipédia ({e}) — fichier inchangé")
            continue
        chemin = RACINE / comp.fichier
        ancien = pd.read_csv(chemin) if chemin.exists() else pd.DataFrame()
        ancien = ancien[ancien.get("Saison", "") != SAISON] if len(ancien) else ancien
        neuf = pd.concat([ancien, pd.DataFrame(joues)], ignore_index=True)
        neuf = neuf.drop_duplicates(subset=["Date", "HomeTeam", "AwayTeam"], keep="last").sort_values("Date")
        neuf.to_csv(chemin, index=False)
        print(f"{comp.nom} {SAISON} : {len(joues)} matchs joués, {len(a_venir)} à venir "
              f"(fichier : {len(ancien)} -> {len(neuf)} matchs)")
        tous_a_venir += [{"competition": code, **m} for m in a_venir]
        tous_buts += [{"competition": code, **b} for b in buts]

    pd.DataFrame(tous_a_venir).to_csv(RACINE / "a_venir.csv", index=False)
    if tous_buts:
        pd.DataFrame(tous_buts).to_csv(RACINE / "buts_minutes.csv", index=False)
    print(f"a_venir.csv : {len(tous_a_venir)} matchs ; buts_minutes.csv : {len(tous_buts)} buts")


if __name__ == "__main__":
    main()
