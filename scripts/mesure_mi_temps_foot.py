"""
Kateni — foot : pronostics de 1re mi-temps (24/11/2026)
=========================================================
Demande du propriétaire : proposer le résultat à la mi-temps et les buts en 1re mi-temps. Méthode : les buts
de 1re mi-temps de chaque équipe suivent une loi de Poisson de moyenne « part × buts attendus du match ».
La part est réglée sur 2024-25 (matchs dont le score à la mi-temps est connu), la fiabilité mesurée sur 2025-26
et début 2026-27, sans fuite. Comparaison au « naïf » (fréquences de 2024-25) et calibration.
Proposé dans l'app seulement si le modèle bat le naïf et reste calibré.

Usage : python3 scripts/mesure_mi_temps_foot.py
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import poisson

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ameliorer import CHAMPIONNATS, REGLAGE, TEST, bin_ll, lambdas_v2, log_loss  # noqa: E402
from kateni.donnees import charger_tout  # noqa: E402

K = np.arange(11)


def marches_mt(ld, le, part):
    a, b = poisson.pmf(K, ld * part), poisson.pmf(K, le * part)
    g = np.outer(a, b)
    i, j = np.indices(g.shape)
    return (np.array([g[i > j].sum(), g[i == j].sum(), g[i < j].sum()]),
            g[(i + j) > 0.5].sum(), g[(i + j) > 1.5].sum())


def main():
    t0 = time.time()
    df = charger_tout()
    ch = df[df["competition"].isin(CHAMPIONNATS) & (df["Date"] >= REGLAGE[0]) & (df["Date"] < TEST[1])
            & df["HTHG"].notna() & df["HTAG"].notna()].reset_index(drop=True)
    lam = lambdas_v2(df, ch, REGLAGE[0], TEST[1])
    print(f"{len(ch)} matchs avec score à la mi-temps ({time.time() - t0:.0f} s)\n", flush=True)
    hd, he = ch["HTHG"].to_numpy(int), ch["HTAG"].to_numpy(int)
    y = np.where(hd > he, 0, np.where(hd == he, 1, 2))
    y05, y15 = (hd + he > 0.5).astype(float), (hd + he > 1.5).astype(float)
    reg = (ch["Date"] < REGLAGE[1]).to_numpy()
    tst = ~reg

    def proba(part):
        r = [marches_mt(a, b, part) for a, b in lam]
        return np.array([x[0] for x in r]), np.array([x[1] for x in r]), np.array([x[2] for x in r])

    part = minimize_scalar(lambda s: log_loss(proba(s)[0][reg], y[reg]), bounds=(0.3, 0.6), method="bounded").x
    print(f"Part des buts marqués en 1re mi-temps (réglée sur 2024-25) : {part:.3f}\n")
    p1n2, p05, p15 = proba(part)
    freq = np.bincount(y[reg], minlength=3) / reg.sum()
    naif = np.tile(freq, (tst.sum(), 1))
    print(f"{'Marché de 1re mi-temps':34s} {'Kateni':>8s} {'naïf':>8s}   bons pronostics (Kateni / naïf)")
    print(f"{'Résultat à la mi-temps (1N2)':34s} {log_loss(p1n2[tst], y[tst]):8.4f} {log_loss(naif, y[tst]):8.4f}   "
          f"{np.mean(p1n2[tst].argmax(1) == y[tst]):.1%} / {np.mean(freq.argmax() == y[tst]):.1%}")
    for nom, p, yy in (("Plus de 0,5 but en 1re mi-temps", p05, y05), ("Plus de 1,5 but en 1re mi-temps", p15, y15)):
        print(f"{nom:34s} {bin_ll(p[tst], yy[tst]):8.4f} {bin_ll(np.full(tst.sum(), yy[reg].mean()), yy[tst]):8.4f}")
    print("\nCalibration (annoncé -> arrivé) sur la période de test :")
    for nom, p, yy in (("Victoire dom. à la mi-temps", p1n2[:, 0], (y == 0).astype(float)),
                       ("Nul à la mi-temps", p1n2[:, 1], (y == 1).astype(float)),
                       ("Plus de 0,5 but", p05, y05), ("Plus de 1,5 but", p15, y15)):
        print(f"  {nom}")
        pt, yt = p[tst], yy[tst]
        for lo, hi in ((0, .3), (.3, .45), (.45, .6), (.6, .75), (.75, 1.01)):
            s = (pt >= lo) & (pt < hi)
            if s.sum() >= 50:
                print(f"     {lo:.0%}-{min(hi, 1):.0%} : {s.sum():5d} matchs, annoncé {pt[s].mean():.0%} -> arrivé {yt[s].mean():.0%}")
    print(f"\nDurée : {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
