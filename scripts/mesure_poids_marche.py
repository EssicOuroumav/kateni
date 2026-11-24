"""
Kateni — foot : quelle part donner au modèle quand les cotes du marché existent ? (24/11/2026)
================================================================================================
Constat (backtest du 21/10) : marché seul 0,9933 de log loss, mélange 25 % modèle 0,9954 -> le mélange était
un peu moins bon que le marché seul. Depuis, le modèle a été recalibré (calibrer). On remesure avec le modèle
de l'app : part du modèle w réglée sur 2024-25, vérifiée sur 2025-26 et début 2026-27, sans fuite.
Marché = cotes Bet365 d'avant-match, marge retirée (ce que l'app reçoit en général). 1N2 et plus/moins 2,5 buts.

Usage : python3 scripts/mesure_poids_marche.py
"""
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ameliorer import CHAMPIONNATS, REGLAGE, TEST, bin_ll, lambdas_v2, log_loss  # noqa: E402
from kateni.donnees import charger_tout  # noqa: E402
from kateni.marches import calibrer, marches, matrice_scores  # noqa: E402

POIDS = (0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.35)


def main():
    t0 = time.time()
    df = charger_tout()
    ch = df[df["competition"].isin(CHAMPIONNATS) & (df["Date"] >= REGLAGE[0]) & (df["Date"] < TEST[1])].copy()
    c = ch[["B365H", "B365D", "B365A", "B365>2.5", "B365<2.5"]].apply(lambda s: s.astype(float))
    ok = (c > 1).all(axis=1).to_numpy()
    ch, c = ch[ok].reset_index(drop=True), c[ok].to_numpy()
    lam = lambdas_v2(df, ch, REGLAGE[0], TEST[1])
    print(f"{len(ch)} matchs avec cotes ({time.time() - t0:.0f} s)\n", flush=True)
    pm = [calibrer(marches(matrice_scores(a, b, -0.06))) for a, b in lam]
    mod = np.array([[p["1N2"]["1"], p["1N2"]["N"], p["1N2"]["2"]] for p in pm])
    mod25 = np.array([p["Total buts 2.5"]["Plus"] for p in pm])
    inv = 1 / c[:, :3]
    mar = inv / inv.sum(1, keepdims=True)
    inv2 = 1 / c[:, 3:]
    mar25 = inv2[:, 0] / inv2.sum(1)
    y = ch["FTR"].map({"H": 0, "D": 1, "A": 2}).to_numpy()
    y25 = ((ch["FTHG"] + ch["FTAG"]) > 2.5).to_numpy(float)
    reg = (ch["Date"] < REGLAGE[1]).to_numpy()
    tst = ~reg
    print(f"Réglage {reg.sum()} matchs · test {tst.sum()} matchs\n")
    print(f"{'Part du modèle':16} {'1N2 réglage':>12} {'1N2 test':>10} {'bons 1N2 test':>14} {'+2,5 réglage':>13} {'+2,5 test':>10}")
    for w in POIDS:
        p = w * mod + (1 - w) * mar
        q = w * mod25 + (1 - w) * mar25
        print(f"{w:16.0%} {log_loss(p[reg], y[reg]):12.4f} {log_loss(p[tst], y[tst]):10.4f} "
              f"{np.mean(p[tst].argmax(1) == y[tst]):14.1%} {bin_ll(q[reg], y25[reg]):13.4f} {bin_ll(q[tst], y25[tst]):10.4f}")
    print(f"\nModèle seul : 1N2 test {log_loss(mod[tst], y[tst]):.4f} · +2,5 test {bin_ll(mod25[tst], y25[tst]):.4f}")
    print(f"Durée : {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
