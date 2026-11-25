"""
Kateni — fiabilité de chaque type de pari, avec la méthode ACTUELLE de l'app (25/11/2026)
==========================================================================================
Pronostic tiré des cotes du marché quand elles existent (buts attendus implicites dans le 1N2 et le plus/moins
2,5, puis tous les paris), comme la page Football depuis le 24/11/2026. Matchs de championnat d'août 2025 à
octobre 2026 avec cotes Bet365. Pour chaque type de pari et chaque tranche de chance annoncée : combien de fois le
pari est vraiment passé. Écrit docs/mesures/fiabilite_actuelle.json (affiché dans la page Bilan).

Usage : python3 scripts/mesure_fiabilite_actuelle.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ameliorer import CHAMPIONNATS, TEST  # noqa: E402
from kateni.cotes import lambdas_depuis_cotes, sans_marge  # noqa: E402
from kateni.donnees import charger_tout  # noqa: E402
from kateni.marches import calibrer, marches, matrice_scores, mi_temps, regler  # noqa: E402

FAMILLES = [("Résultat (1N2)", ("1N2",)), ("Double chance", ("Double chance",)),
            ("Nombre de buts", ("Total buts",)), ("Les 2 équipes marquent", ("Les deux équipes marquent",)),
            ("Une équipe marque", ("Dom. marque", "Ext. marque"))]
BANDES = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0)]

df = charger_tout()
t = df[df["competition"].isin(CHAMPIONNATS) & (df["Date"] >= TEST[0]) & (df["Date"] < TEST[1])]
c = t[["B365H", "B365D", "B365A", "B365>2.5", "B365<2.5"]].astype(float)
t = t[(c > 1).all(axis=1).to_numpy()].reset_index(drop=True)
lignes = []
for _, r in t.iterrows():
    c1, cn, c2, cp, cm = (float(r[k]) for k in ("B365H", "B365D", "B365A", "B365>2.5", "B365<2.5"))
    ld, le = lambdas_depuis_cotes(c1, cn, c2, cp, cm, -0.06)
    p = calibrer(marches(matrice_scores(ld, le, -0.06)))
    q = sans_marge([c1, cn, c2])[0]
    p["1N2"] = {"1": q[0], "N": q[1], "2": q[2]}
    p["Double chance"] = {"1N": q[0] + q[1], "12": q[0] + q[2], "N2": q[1] + q[2]}
    pl = sans_marge([cp, cm])[0][0]
    p["Total buts 2.5"] = {"Plus": pl, "Moins": 1 - pl}
    for mk, d in p.items():
        if mk in ("Total buts 0.5", "Total buts 5.5"):
            continue
        for sel, v in d.items():
            if v >= 0.5:
                lignes.append({"marche": mk, "p": float(v), "ok": bool(regler(mk, sel, int(r["FTHG"]), int(r["FTAG"])))})
d = pd.DataFrame(lignes)
out = {"matchs": len(t), "periode": f"{TEST[0]:%d/%m/%Y} - {TEST[1]:%d/%m/%Y}", "familles": {}}
print(f"{len(t)} matchs\n")
for nom, prefixes in FAMILLES:
    g = d[d["marche"].str.startswith(prefixes)]
    cases = []
    for a, b in BANDES:
        s = g[(g["p"] >= a) & (g["p"] < b)]
        cases.append(None if len(s) < 30 else {"annonce": round(float(s["p"].mean()), 3),
                                               "arrive": round(float(s["ok"].mean()), 3), "n": int(len(s))})
    out["familles"][nom] = cases
    print(f"{nom:24}", " | ".join("–" if x is None else f"{x['annonce']:.0%}->{x['arrive']:.0%} ({x['n']})" for x in cases))
s = d[(d["marche"] == "Total buts 1.5") & (d["p"] >= 0.80) & (d["p"] < 0.85)]
out["exemple_plus_1_5_80_85"] = {"annonce": round(float(s["p"].mean()), 3), "arrive": round(float(s["ok"].mean()), 3),
                                 "n": int(len(s))}
print(f"\nPlus de 1,5 but annoncé 80-85 % : {len(s)} paris, annoncé {s['p'].mean():.0%} -> passé {s['ok'].mean():.0%}")
Path(__file__).resolve().parent.parent.joinpath("docs/mesures/fiabilite_actuelle.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
