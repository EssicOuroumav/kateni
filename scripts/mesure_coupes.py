"""
Kateni — apport des 9 championnats ajoutés sur les prédictions de C1/C3
Matchs de C1/C3 du 01/08/2025 au 20/10/2026, chacun prédit avec les seules données d'avant,
modèle global ajusté (a) sans et (b) avec les 9 championnats.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kateni.donnees import charger_tout  # noqa: E402
from kateni.marches import marches, matrice_scores  # noqa: E402
from kateni.modele import ajuster  # noqa: E402

NOUVEAUX = {"SCO", "GRE", "AUT", "SUI", "NOR", "DAN", "SUE", "POL", "ROU"}
df = charger_tout()
coupes = df[df["competition"].isin(["CL", "EL"]) & (df["Date"] >= "2025-08-01")].reset_index(drop=True)
y = coupes["FTR"].map({"H": 0, "D": 1, "A": 2}).to_numpy()
res = {}
for nom, base in (("sans les 9 championnats", df[~df["competition"].isin(NOUVEAUX)]), ("avec les 9 championnats", df)):
    p = np.zeros((len(coupes), 3))
    for d0 in pd.date_range("2025-08-01", "2026-10-21", freq="7D"):
        sel = ((coupes["Date"] >= d0) & (coupes["Date"] < d0 + pd.Timedelta(days=7))).to_numpy()
        if not sel.any():
            continue
        m = ajuster(base, date_ref=d0)
        for k in np.flatnonzero(sel):
            r = coupes.iloc[k]
            q = marches(matrice_scores(*m.lambdas(r.HomeTeam, r.AwayTeam, r.competition), m.rho))["1N2"]
            p[k] = [q["1"], q["N"], q["2"]]
    res[nom] = p
    print(f"{nom:26} : {len(coupes)} matchs · bons pronostics {np.mean(p.argmax(1) == y):.1%} · "
          f"log loss {np.mean(-np.log(p[np.arange(len(y)), y])):.4f}")
