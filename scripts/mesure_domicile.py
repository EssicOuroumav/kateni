"""
Kateni — l'avantage du terrain propre à chaque club améliore-t-il la prédiction ?
==================================================================================
Le modèle global a déjà un avantage du terrain par championnat. On teste un terme en plus, propre à chaque
club (certains clubs sont bien plus forts chez eux qu'ailleurs), rappelé vers 0 avec une force à régler.
Réglage sur 2024-25, mesure sur 2025-26 (même méthode que ameliorer.py, sans fuite de données).

Usage : python3 scripts/mesure_domicile.py
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ameliorer import CHAMPIONNATS, REGLAGE, TEST, bin_ll, lambdas_v2, log_loss, proba_1n2  # noqa: E402
from kateni.donnees import charger_tout  # noqa: E402

FORCES = [None, 3.0, 10.0, 30.0, 100.0]   # None = modèle actuel (avantage par championnat seulement)


def mesurer(df, matchs, periode, ridge_dom):
    lam = lambdas_v2(df, matchs, *periode, ridge_dom=ridge_dom)
    res = [proba_1n2(a, b, -0.06) for a, b in lam]
    p = np.array([r[0] for r in res])
    y = matchs["FTR"].map({"H": 0, "D": 1, "A": 2}).to_numpy()
    plus = (matchs["FTHG"] + matchs["FTAG"] > 2.5).to_numpy(float)
    return {"Bons pronostics 1N2": np.mean(p.argmax(1) == y), "Log loss 1N2": log_loss(p, y),
            "Log loss +2,5 buts": bin_ll(np.array([r[1] for r in res]), plus)}


def main():
    t0 = time.time()
    df = charger_tout()
    dom = df[df["competition"].isin(CHAMPIONNATS)]
    reg = dom[(dom["Date"] >= REGLAGE[0]) & (dom["Date"] < REGLAGE[1])].reset_index(drop=True)
    tst = dom[(dom["Date"] >= TEST[0]) & (dom["Date"] < TEST[1])].reset_index(drop=True)
    print(f"Réglage : {len(reg)} matchs · Test : {len(tst)} matchs\n")
    lignes = []
    for f in FORCES:
        r = mesurer(df, reg, REGLAGE, f)
        lignes.append({"Force du rappel": "aucun terme (actuel)" if f is None else f, **r})
        print(f"  réglage, rappel {f} : log loss {r['Log loss 1N2']:.4f} ({time.time() - t0:.0f} s)", flush=True)
    tab = pd.DataFrame(lignes)
    meilleur = min(FORCES[1:], key=lambda f: tab.loc[FORCES.index(f), "Log loss 1N2"])
    print("\nPériode de réglage (2024-25) :\n" + tab.round(4).to_string(index=False))
    print(f"\n-> force retenue sur le réglage : {meilleur}\nMesure finale sur 2025-26…", flush=True)
    avant, apres = mesurer(df, tst, TEST, None), mesurer(df, tst, TEST, meilleur)
    fin = pd.DataFrame([{"Version": "Actuel (avantage par championnat)", **avant},
                        {"Version": f"+ avantage propre au club (rappel {meilleur})", **apres}])
    print("\nPériode de test (2025-26) :\n" + fin.round(4).to_string(index=False))
    print(f"\nDurée : {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
