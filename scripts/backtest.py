"""
Kateni V2 — backtest sans fuite, mesuré CONTRE LE MARCHÉ
==========================================================
Le modèle est réajusté chaque semaine avec uniquement les matchs passés,
puis prédit les matchs de la semaine suivante. On compare, match par match :
  - log loss du modèle (plus bas = mieux)
  - log loss du marché (cotes Bet365 d'ouverture, marge retirée)
  - log loss de mélanges modèle/marché
  - ROI des paris à espérance >= seuil, au prix d'ouverture et (si dispo)
    CLV : la cote prise est-elle meilleure que la cote de clôture ?

Usage :
    python3 scripts/backtest.py                       # 1N2, depuis le 01/08/2025
    python3 scripts/backtest.py --depuis 2024-08-01 --ridge 5 --demi-vie 300
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kateni.config import MIN_EDGE_PCT  # noqa: E402
from kateni.cotes import sans_marge  # noqa: E402
from kateni.donnees import charger_tout  # noqa: E402
from kateni.marches import marches, matrice_scores  # noqa: E402
from kateni.modele import ajuster  # noqa: E402

POIDS = [0.0, 0.25, 0.5, 0.75, 1.0]  # poids du modèle dans le mélange (0 = marché seul)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--depuis", default="2025-08-01")
    ap.add_argument("--ridge", type=float, default=None)
    ap.add_argument("--demi-vie", type=float, default=None)
    args = ap.parse_args()
    kw = {}
    if args.ridge is not None:
        kw["ridge"] = args.ridge
    if args.demi_vie is not None:
        kw["demi_vie"] = args.demi_vie

    df = charger_tout()
    test = df[(df["Date"] >= args.depuis) & df[["B365H", "B365D", "B365A"]].notna().all(axis=1)]
    lignes = []
    semaines = pd.date_range(args.depuis, df["Date"].max() + pd.Timedelta(days=7), freq="7D")
    for debut, fin in zip(semaines[:-1], semaines[1:]):
        bloc = test[(test["Date"] >= debut) & (test["Date"] < fin)]
        if not len(bloc):
            continue
        m = ajuster(df, date_ref=debut, **kw)
        for _, r in bloc.iterrows():
            ld, le = m.lambdas(r.HomeTeam, r.AwayTeam, r.competition)
            p = marches(matrice_scores(ld, le, m.rho))
            pm = np.array([p["1N2"]["1"], p["1N2"]["N"], p["1N2"]["2"]])
            cotes = np.array([r.B365H, r.B365D, r.B365A], float)
            pk = np.array(sans_marge(list(cotes))[0])
            res = {"H": 0, "D": 1, "A": 2}[r.FTR]
            ligne = {"competition": r.competition, "res": res}
            for w in POIDS:
                ligne[f"ll_{w}"] = -np.log(max(1e-9, (w * pm + (1 - w) * pk)[res]))
            # paris simulés à 1 FCFA, mélange 50/50, espérance >= seuil
            for w in (0.5, 1.0):
                pb = w * pm + (1 - w) * pk
                ev = pb * cotes - 1
                k = int(np.argmax(ev))
                if ev[k] >= MIN_EDGE_PCT:
                    ligne[f"pari_{w}"] = 1
                    ligne[f"gain_{w}"] = cotes[k] - 1 if k == res else -1
                    cl = [r.get(c) for c in ("B365CH", "B365CD", "B365CA")]
                    if pd.notna(cl[k]):
                        ligne[f"clv_{w}"] = cotes[k] / float(cl[k]) - 1
            lignes.append(ligne)

    t = pd.DataFrame(lignes)
    print(f"\n{len(t)} matchs testés depuis le {args.depuis} (réglages : {kw or 'par défaut'})\n")
    print("Log loss 1N2 (plus bas = mieux) — poids du modèle dans le mélange :")
    print(t[[f"ll_{w}" for w in POIDS]].mean().rename(lambda c: c.replace("ll_", "modèle ")).round(4).to_string())
    print("\nPar compétition (marché seul / modèle seul / 50-50) :")
    g = t.groupby("competition")[["ll_0.0", "ll_1.0", "ll_0.5"]].mean().round(4)
    g["matchs"] = t.groupby("competition").size()
    print(g.to_string())
    for w in (0.5, 1.0):
        if f"pari_{w}" in t:
            p = t[t[f"pari_{w}"] == 1]
            clv = p[f"clv_{w}"].mean() * 100 if f"clv_{w}" in p else float("nan")
            print(f"\nParis simulés (modèle {w:.0%}) : {len(p)} paris, ROI {p[f'gain_{w}'].mean()*100:+.1f} %, "
                  f"CLV moyenne {clv:+.1f} % (positif = on bat la clôture)")


if __name__ == "__main__":
    main()
