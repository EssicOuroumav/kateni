"""
Kateni — calibrage du module Live sur nos matchs (score à la mi-temps -> score final)
Réglage : 2024-25 · mesure : 08/2025 -> 10/2026. Force avant-match = modèle global, réajusté chaque semaine.

Buts de 2e mi-temps attendus pour une équipe : lambda_match × F2 × m(écart au score à la mi-temps)
  F2 : part des buts du match marqués en 2e mi-temps (temps additionnel compris)
  m  : menée de 1 (T1), menée de 2+ (T2), mène de 1 (L1), mène de 2+ (L2), égalité = 1
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kateni.config import RACINE  # noqa: E402
from kateni.donnees import charger_tout  # noqa: E402
from kateni.live import ADDITIONNEL_MT2, MENE, MENE_DE_1, MENE_DE_2, fraction_restante  # noqa: E402
from kateni.modele import ajuster  # noqa: E402

K = np.arange(11)


def donnees(df, debut, fin):
    t = df[(df.Date >= debut) & (df.Date < fin) & ~df.competition.isin(["CL", "EL"])].dropna(subset=["HTHG", "HTAG"])
    t = t.reset_index(drop=True)
    lam = np.zeros((len(t), 2))
    for d0 in pd.date_range(debut, fin, freq="7D"):
        s = ((t.Date >= d0) & (t.Date < d0 + pd.Timedelta(days=7))).to_numpy()
        if s.any():
            m = ajuster(df, date_ref=d0)
            for k in np.flatnonzero(s):
                r = t.iloc[k]
                lam[k] = m.lambdas(r.HomeTeam, r.AwayTeam, r.competition)
    return t, lam


def mult(ecart, T1, T2, L1, L2):
    return np.select([ecart <= -2, ecart == -1, ecart == 1, ecart >= 2], [T2, T1, L1, L2], 1.0)


def attendus(t, lam, F2, T1, T2, L1, L2):
    e = (t.HTHG - t.HTAG).to_numpy()
    return lam[:, 0] * F2 * mult(e, T1, T2, L1, L2), lam[:, 1] * F2 * mult(-e, T1, T2, L1, L2)


def nll(x, t, lam):
    rh, ra = attendus(t, lam, *x)
    gh, ga = (t.FTHG - t.HTHG).to_numpy(), (t.FTAG - t.HTAG).to_numpy()
    return -(poisson.logpmf(gh, rh).sum() + poisson.logpmf(ga, ra).sum())


def ll_final(t, lam, x):
    """Log loss du résultat final 1N2, prédit à la mi-temps."""
    rh, ra = attendus(t, lam, *x)
    tot = 0.0
    for k in range(len(t)):
        m = np.outer(poisson.pmf(K, rh[k]), poisson.pmf(K, ra[k]))
        i, j = np.indices(m.shape)
        dh, da = i + t.HTHG.iloc[k], j + t.HTAG.iloc[k]
        p = {"H": m[dh > da].sum(), "D": m[dh == da].sum(), "A": m[dh < da].sum()}[t.FTR.iloc[k]]
        tot += -np.log(max(p / m.sum(), 1e-12))
    return tot / len(t)


if __name__ == "__main__":
    df = charger_tout()
    tr, lr = donnees(df, pd.Timestamp("2024-08-01"), pd.Timestamp("2025-08-01"))
    tt, lt = donnees(df, pd.Timestamp("2025-08-01"), pd.Timestamp("2026-10-21"))
    actuel = [fraction_restante(45, ADDITIONNEL_MT2), MENE_DE_1, MENE_DE_2, MENE, MENE]
    res = minimize(nll, actuel, args=(tr, lr), method="Nelder-Mead", options={"maxiter": 2000, "xatol": 1e-4})
    nouveau = [float(v) for v in res.x]
    noms = ["F2 (part 2e mi-temps)", "menée de 1", "menée de 2+", "mène de 1", "mène de 2+"]
    print(f"Réglage 2024-25 : {len(tr)} matchs · Test 2025-26 : {len(tt)} matchs\n")
    print(f"{'Coefficient':24}{'actuel (études)':>17}{'mesuré':>10}")
    for n, a, b in zip(noms, actuel, nouveau):
        print(f"{n:24}{a:>17.3f}{b:>10.3f}")
    print(f"\nRésultat final prédit à la mi-temps, log loss sur le TEST (plus bas = mieux) :")
    print(f"  coefficients actuels : {ll_final(tt, lt, actuel):.4f}")
    print(f"  coefficients mesurés : {ll_final(tt, lt, nouveau):.4f}")
    (RACINE / "docs" / "mesures" / "2026-10-21_live_coefficients.json").write_text(
        json.dumps(dict(zip(["F2", "T1", "T2", "L1", "L2"], nouveau)), indent=2))
