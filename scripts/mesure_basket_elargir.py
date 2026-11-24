"""
Kateni — basket : régler l'élargissement des écarts-types par période et par ligue (24/11/2026)
================================================================================================
Constat (mesure_basket_v2.py) : le modèle est trop sûr de lui (annoncé 80 % -> arrivé 76 % ; mi-temps 78 % -> 71 % ;
quart-temps 72 % -> 62 %). Correction : multiplier l'écart-type de l'écart par un facteur k (une par période, et
pour le match une par ligue). k réglé sur juillet 2025 - juin 2026, vérifié sur juillet - novembre 2026 (sans fuite).

Usage : python3 scripts/mesure_basket_elargir.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mesure_basket_v2 import predire  # noqa: E402
from kateni.basket import PERIODES  # noqa: E402

COUPURE = pd.Timestamp("2026-07-01", tz="UTC")


def ll(q, y):
    q = np.clip(q, 1e-4, 1 - 1e-4)
    return float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))


def calib(q, y):
    out = []
    for lo, hi in ((0, .35), (.35, .5), (.5, .65), (.65, 1.01)):
        s = (q >= lo) & (q < hi)
        if s.sum() >= 30:
            out.append(f"{lo:.0%}-{min(hi, 1):.0%} : annoncé {q[s].mean():.0%} -> arrivé {y[s].mean():.0%} ({s.sum()})")
    return " | ".join(out)


def main():
    for nom, quarts in PERIODES.items():
        p = predire(quarts=quarts)
        print(f"\n=== {nom} ===")
        groupes = [("toutes", p)] if nom != "Match" else [("toutes", p), *p.groupby("ligue")]
        for g_nom, g in groupes:
            reg, tst = g[g["date"] < COUPURE], g[g["date"] >= COUPURE]
            if len(reg) < 100 or len(tst) < 50:
                print(f"  {g_nom:11} : trop peu de matchs ({len(reg)} / {len(tst)})")
                continue
            f = lambda k, x: 1 - norm.cdf(0, x["e"], k * x["sd_e"])  # noqa: E731
            k = minimize_scalar(lambda k: ll(f(k, reg), reg["y"]), bounds=(0.8, 1.6), method="bounded").x
            print(f"  {g_nom:11} k = {k:.2f} · test {len(tst)} matchs : log loss {ll(f(1.0, tst), tst['y']):.4f} -> "
                  f"{ll(f(k, tst), tst['y']):.4f}")
            print(f"     avant : {calib(np.asarray(f(1.0, tst)), tst['y'].to_numpy())}")
            print(f"     après : {calib(np.asarray(f(k, tst)), tst['y'].to_numpy())}")


if __name__ == "__main__":
    main()
