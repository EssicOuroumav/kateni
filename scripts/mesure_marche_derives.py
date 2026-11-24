"""
Kateni — foot : les autres paris (les deux marquent, buts de chaque équipe, mi-temps) sont-ils plus justes calculés
à partir des cotes du marché (buts attendus implicites dans le 1N2 et le plus/moins 2,5) ? (24/11/2026)
Mesure sur 2025-26 et début 2026-27 (cotes Bet365 d'avant-match), sans fuite, contre les buts attendus du modèle.
Corrections déjà adoptées appliquées des deux côtés (« les deux marquent » recalibré, part de mi-temps).

Usage : python3 scripts/mesure_marche_derives.py
"""
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ameliorer import CHAMPIONNATS, TEST, bin_ll, lambdas_v2, log_loss  # noqa: E402
from kateni.cotes import lambdas_depuis_cotes  # noqa: E402
from kateni.donnees import charger_tout  # noqa: E402
from kateni.marches import calibrer, marches, matrice_scores, mi_temps  # noqa: E402


def derives(ld, le):
    p = calibrer(marches(matrice_scores(ld, le, -0.06)))
    mt = mi_temps(ld, le)
    return [p["Les deux équipes marquent"]["Oui"], p["Dom. marque"]["Oui"], p["Ext. marque"]["Oui"],
            p["Total buts 1.5"]["Plus"], p["Total buts 3.5"]["Plus"],
            mt["Mi-temps 1N2"]["1"], mt["Mi-temps 1N2"]["N"], mt["Mi-temps 1N2"]["2"]]


def main():
    t0 = time.time()
    df = charger_tout()
    t = df[df["competition"].isin(CHAMPIONNATS) & (df["Date"] >= TEST[0]) & (df["Date"] < TEST[1])].copy()
    c = t[["B365H", "B365D", "B365A", "B365>2.5", "B365<2.5"]].astype(float)
    t = t[(c > 1).all(axis=1).to_numpy()].reset_index(drop=True)
    c = t[["B365H", "B365D", "B365A", "B365>2.5", "B365<2.5"]].astype(float).to_numpy()
    lam_mod = lambdas_v2(df, t, *TEST)
    lam_mar = np.array([lambdas_depuis_cotes(*row, rho=-0.06) for row in c])
    print(f"{len(t)} matchs ({time.time() - t0:.0f} s)\n", flush=True)
    A = np.array([derives(a, b) for a, b in lam_mod])
    B = np.array([derives(a, b) for a, b in lam_mar])
    hg, ag = t["FTHG"].to_numpy(), t["FTAG"].to_numpy()
    cibles = {"Les deux équipes marquent": (0, (hg > 0) & (ag > 0)), "Domicile marque": (1, hg > 0),
              "Extérieur marque": (2, ag > 0), "Plus de 1,5 but": (3, hg + ag > 1.5), "Plus de 3,5 buts": (4, hg + ag > 3.5)}
    print(f"{'Pari':28} {'buts du modèle':>15} {'buts du marché':>15}")
    for nom, (k, y) in cibles.items():
        print(f"{nom:28} {bin_ll(A[:, k], y.astype(float)):15.4f} {bin_ll(B[:, k], y.astype(float)):15.4f}")
    ok = t["HTHG"].notna().to_numpy()
    if ok.any():
        h, a = t.loc[ok, "HTHG"].to_numpy(), t.loc[ok, "HTAG"].to_numpy()
        ymt = np.where(h > a, 0, np.where(h == a, 1, 2))
        print(f"{'Résultat à la mi-temps':28} {log_loss(A[ok, 5:8], ymt):15.4f} {log_loss(B[ok, 5:8], ymt):15.4f}")
    print(f"\nDurée : {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
