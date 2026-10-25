"""
Kateni — fiabilité des pronostics de la page Kamikaze
=======================================================
Pour chaque match de championnat de la période de test (2025-26 et début 2026-27), avec le pronostic de
l'app (25 % modèle global + 75 % cotes du marché, marge retirée ; matchs avec cotes seulement) :
  - favori = l'équipe qui a la plus grande chance de gagner (domicile ou extérieur) ;
  - « victoire » = le favori gagne ; « gagne ou nul » = le favori ne perd pas.
On range les matchs par chance annoncée et on compte ce qui est réellement arrivé.
Résultat : docs/mesures/kamikaze_fiabilite.json (lu par la page Kamikaze).

Usage : python3 scripts/mesure_kamikaze.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ameliorer import CHAMPIONNATS, TEST, lambdas_v2, proba_1n2  # noqa: E402
from kateni.config import POIDS_MODELE, RACINE  # noqa: E402
from kateni.donnees import charger_tout  # noqa: E402

TRANCHES = [0.0, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01]


def main():
    df = charger_tout()
    tst = df[df["competition"].isin(CHAMPIONNATS) & (df["Date"] >= TEST[0]) & (df["Date"] < TEST[1])]
    cotes = tst[["B365H", "B365D", "B365A"]].apply(pd.to_numeric, errors="coerce")
    tst = tst[cotes.notna().all(axis=1)].reset_index(drop=True)
    cotes = tst[["B365H", "B365D", "B365A"]].astype(float).to_numpy()
    lam = lambdas_v2(df, tst, *TEST)
    p_mod = np.array([proba_1n2(a, b, -0.06)[0] for a, b in lam])
    p_mar = (1 / cotes) / (1 / cotes).sum(axis=1, keepdims=True)
    p = POIDS_MODELE * p_mod + (1 - POIDS_MODELE) * p_mar
    fav_dom = p[:, 0] >= p[:, 2]
    p_vic = np.where(fav_dom, p[:, 0], p[:, 2])
    p_dc = p_vic + p[:, 1]
    res = tst["FTR"].to_numpy()
    vic = np.where(fav_dom, res == "H", res == "A")
    dc = vic | (res == "D")
    out = {"matchs": int(len(tst)), "periode": f"{TEST[0]:%d/%m/%Y} – {tst['Date'].max():%d/%m/%Y}"}
    for nom, prob, ok in (("victoire", p_vic, vic), ("gagne_ou_nul", p_dc, dc)):
        lignes = []
        for lo, hi in zip(TRANCHES[:-1], TRANCHES[1:]):
            s = (prob >= lo) & (prob < hi)
            if s.sum() >= 30:
                lignes.append({"de": lo, "a": min(hi, 1.0), "matchs": int(s.sum()),
                               "annonce": round(float(prob[s].mean()), 3), "arrive": round(float(ok[s].mean()), 3)})
        out[nom] = lignes
        print(f"\n{nom} ({len(tst)} matchs)")
        for l in lignes:
            print(f"  {l['de']:.0%}-{l['a']:.0%} : {l['matchs']:5d} matchs · annoncé {l['annonce']:.1%} · arrivé {l['arrive']:.1%}")
    (RACINE / "docs" / "mesures" / "kamikaze_fiabilite.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
