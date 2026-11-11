"""
Kateni — correction de « les deux équipes marquent » (11/11/2026)
==================================================================
Constat (scripts/mesure_marches.py) : quand le modèle annonce « oui » au-dessus de 60 %, le pari passe moins
souvent qu'annoncé (72 % annoncé -> 65 % arrivé). Correction testée : p' = sigmoïde(a · logit(p) + b),
a et b réglés sur 2024-25 (log loss minimal), mesurés sur août 2025-octobre 2026, sans fuite (modèle
réajusté chaque semaine). Adoptée seulement si elle améliore la mesure finale.

Usage : python3 scripts/mesure_btts.py
"""

import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ameliorer import CHAMPIONNATS, REGLAGE, TEST, bin_ll, lambdas_v2, proba_1n2  # noqa: E402
from kateni.donnees import charger_tout  # noqa: E402


def chances(df, debut, fin):
    t = df[df["competition"].isin(CHAMPIONNATS) & (df["Date"] >= debut) & (df["Date"] < fin)].reset_index(drop=True)
    lam = lambdas_v2(df, t, debut, fin)
    p = np.array([proba_1n2(a, b, -0.06)[2] for a, b in lam])
    y = ((t["FTHG"] > 0) & (t["FTAG"] > 0)).to_numpy(float)
    return np.clip(p, 1e-6, 1 - 1e-6), y


def corriger(p, a, b):
    return 1 / (1 + np.exp(-(a * np.log(p / (1 - p)) + b)))


def tableau(p, y):
    for lo, hi in ((0.3, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 1.01)):
        s = (p >= lo) & (p < hi)
        if s.sum() >= 30:
            print(f"    {lo:.0%}-{min(hi, 1):.0%} : {s.sum():5d} matchs, annoncé {p[s].mean():.0%} -> arrivé {y[s].mean():.0%}")


def main():
    df = charger_tout()
    pr, yr = chances(df, *REGLAGE)
    res = minimize(lambda x: bin_ll(corriger(pr, *x), yr), x0=[1.0, 0.0], method="Nelder-Mead")
    a, b = res.x
    print(f"Réglage 2024-25 ({len(pr)} matchs) : a = {a:.3f}, b = {b:.3f}")
    pt, yt = chances(df, *TEST)
    pc = corriger(pt, a, b)
    print(f"\nMesure finale ({len(pt)} matchs) : log loss sans correction {bin_ll(pt, yt):.4f}, "
          f"avec correction {bin_ll(pc, yt):.4f}")
    print("  Sans correction :")
    tableau(pt, yt)
    print("  Avec correction :")
    tableau(pc, yt)


if __name__ == "__main__":
    main()
