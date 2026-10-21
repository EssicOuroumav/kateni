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
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kateni.config import COMPETITIONS, RACINE  # noqa: E402

SAISON = "2026-27"  # saison en cours : ses matchs à venir alimentent a_venir.csv
# (compétition, saison) -> pages Wikipédia. Les saisons passées comblent les trous des autres sources
# (la Ligue Europa 2025-26 manquait dans openfootball).
PAGES = {
    ("CL", "2026-27"): ["2026–27 UEFA Champions League league phase", "2026–27 UEFA Champions League knockout phase"],
    ("EL", "2026-27"): ["2026–27 UEFA Europa League league phase", "2026–27 UEFA Europa League knockout phase"],
    ("EL", "2025-26"): ["2025–26 UEFA Europa League league phase", "2025–26 UEFA Europa League knockout phase"],
}
API = "https://en.wikipedia.org/w/api.php"

RE_BOX = re.compile(r"\{\{(?:#invoke:Football box\|main|Football box)\s*(.*?)\n\}\}", re.S)
RE_CHAMP = re.compile(r"^\|(\w+)\s*=\s*(.*?)(?=^\|\w+\s*=|\Z)", re.S | re.M)
RE_LIEN = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]+)\]\]")
RE_DATE = re.compile(r"Start date\|(\d{4})\|(\d{1,2})\|(\d{1,2})")
RE_SCORE = re.compile(r"(\d+)\s*[–−-]\s*(\d+)")
RE_BUT = re.compile(r"\{\{goal\|([^}]*)\}\}")


def wikitexte(titre: str) -> str:
    """Texte brut d'une page ; chaîne vide si la page n'existe pas encore (phase finale à venir)."""
    params = urllib.parse.urlencode({"action": "parse", "page": titre, "prop": "wikitext",
                                     "format": "json", "formatversion": "2"})
    req = urllib.request.Request(f"{API}?{params}", headers={"User-Agent": "Kateni/2 (usage personnel)"})
    for essai in range(4):
        time.sleep(1.5)  # politesse envers Wikipédia (limite de débit : erreur 429)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r).get("parse", {}).get("wikitext", "")
        except urllib.error.HTTPError as e:
            if e.code != 429 or essai == 3:
                raise
            time.sleep(10 * (essai + 1))  # attendre avant de réessayer
    return ""


def nom_equipe(brut: str) -> str:
    brut = re.sub(r"\{\{(?:fbaicon|flagicon|fbicon)\|[^}]*\}\}", "", brut)
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


def parser(texte: str, saison: str = SAISON) -> tuple[list[dict], list[dict], list[dict]]:
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
                     "FTR": ftr, "Saison": saison}
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
    courantes_ok = True
    par_comp: dict[str, list[tuple[str, list[dict]]]] = {}
    for (code, saison), titres in PAGES.items():
        joues, a_venir, buts = [], [], []
        try:
            for titre in titres:
                j, a, b = parser(wikitexte(titre), saison)
                joues += j; a_venir += a; buts += b
        except Exception as e:
            print(f"{COMPETITIONS[code].nom} {saison} : échec de lecture Wikipédia ({e}) — inchangé")
            courantes_ok = courantes_ok and saison != SAISON
            continue
        print(f"{COMPETITIONS[code].nom} {saison} : {len(joues)} matchs joués, {len(a_venir)} à venir")
        if joues:
            par_comp.setdefault(code, []).append((saison, joues))
        if saison == SAISON:
            tous_a_venir += [{"competition": code, **m} for m in a_venir]
        tous_buts += [{"competition": code, "Saison": saison, **b} for b in buts]

    for code, lots in par_comp.items():
        chemin = RACINE / COMPETITIONS[code].fichier
        ancien = pd.read_csv(chemin) if chemin.exists() else pd.DataFrame(columns=["Saison"])
        saisons = {s for s, _ in lots}
        garde = ancien[~ancien["Saison"].isin(saisons)]
        neuf = pd.concat([garde] + [pd.DataFrame(j) for _, j in lots], ignore_index=True)
        neuf = neuf.drop_duplicates(subset=["Date", "HomeTeam", "AwayTeam"], keep="last").sort_values(["Date", "HomeTeam", "AwayTeam"], kind="mergesort")
        neuf.to_csv(chemin, index=False)
        print(f"  {chemin.name} : {len(ancien)} -> {len(neuf)} matchs")

    # Le calendrier n'est réécrit que si TOUTES les pages de la saison en cours ont répondu
    if courantes_ok:
        pd.DataFrame(tous_a_venir).to_csv(RACINE / "a_venir.csv", index=False)
    else:
        print("a_venir.csv conservé : une page de la saison en cours n'a pas répondu")
    # Ne jamais réduire le fichier des minutes de buts si une page n'a pas répondu cette fois
    chemin_buts = RACINE / "buts_minutes.csv"
    avant = len(pd.read_csv(chemin_buts)) if chemin_buts.exists() else 0
    if len(tous_buts) >= avant:
        pd.DataFrame(tous_buts).to_csv(chemin_buts, index=False)
    else:
        print(f"buts_minutes.csv conservé ({avant} buts) : une page n'a pas répondu ({len(tous_buts)} lus)")
    print(f"a_venir.csv : {len(tous_a_venir)} matchs ; buts_minutes.csv : {len(tous_buts)} buts")


if __name__ == "__main__":
    main()
