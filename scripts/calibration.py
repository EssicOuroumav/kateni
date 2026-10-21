"""
Kateni — correction de la prudence sur les favoris (calibration), mesurée sans fuite
Réglage sur 2024-25, mesure sur 08/2025 -> 10/2026. Modèle de l'app (meilleur par championnat).
Correction testée : p_favori' = sigmoïde(a · logit(p_favori) + b), les deux autres issues gardant leurs
proportions. a > 1 = plus confiant sur les favoris.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kateni.config import MODELE_PAR_COMPETITION  # noqa: E402
from kateni.donnees import charger_tout  # noqa: E402
from kateni.modele import ajuster  # noqa: E402
from kateni.modele_v1 import ajuster_v1  # noqa: E402

K = np.arange(11)
PRINCIPAUX = ["PL", "LIGA", "L1", "SA", "BL", "POR", "TUR", "BEL", "NED", "CHAMP", "LIGA2", "L2"]


def p1n2(ld, le, rho):
    m = np.outer(poisson.pmf(K, ld), poisson.pmf(K, le))
    if rho:
        m[0, 0] *= 1 - ld * le * rho; m[0, 1] *= 1 + ld * rho; m[1, 0] *= 1 + le * rho; m[1, 1] *= 1 - rho
    m = np.clip(m, 0, None); m /= m.sum(); i, j = np.indices(m.shape)
    return [m[i > j].sum(), m[i == j].sum(), m[i < j].sum()]


def predictions(df, debut, fin):
    t = df[df.competition.isin(PRINCIPAUX) & (df.Date >= debut) & (df.Date < fin)].reset_index(drop=True)
    P = np.zeros((len(t), 3))
    for d0 in pd.date_range(debut, fin, freq="7D"):
        s = ((t.Date >= d0) & (t.Date < d0 + pd.Timedelta(days=7))).to_numpy()
        if not s.any():
            continue
        m2 = ajuster(df, date_ref=d0); passe = df[df.Date < d0]; v1 = {}
        for k in np.flatnonzero(s):
            r = t.iloc[k]
            if MODELE_PAR_COMPETITION.get(r.competition) == "V1":
                v1.setdefault(r.competition, ajuster_v1(passe[passe.competition == r.competition]))
                P[k] = p1n2(*v1[r.competition].lambdas(r.HomeTeam, r.AwayTeam), 0.0)
            else:
                P[k] = p1n2(*m2.lambdas(r.HomeTeam, r.AwayTeam, r.competition), m2.rho)
    return t, P, t.FTR.map({"H": 0, "D": 1, "A": 2}).to_numpy()


def corriger(P, a, b):
    P = P.copy(); f = P.argmax(1); pf = P[np.arange(len(P)), f]
    z = a * np.log(pf / (1 - pf)) + b; nf = 1 / (1 + np.exp(-z))
    reste = 1 - pf; facteur = (1 - nf) / reste
    for i in range(3):
        autre = f != i; P[autre, i] *= facteur[autre]
    P[np.arange(len(P)), f] = nf
    return P


ll = lambda P, y: float(np.mean(-np.log(np.clip(P[np.arange(len(y)), y], 1e-12, 1))))


def tableau(P, y, titre):
    pf, g = P.max(1), P.argmax(1) == y
    print(titre)
    for a, b in [(.33, .4), (.4, .5), (.5, .6), (.6, .7), (.7, 1.01)]:
        s = (pf >= a) & (pf < b)
        print(f"  {a:.0%}-{min(b, 1):.0%} : {s.sum():5d} matchs · annoncé {pf[s].mean():.1%} · réel {g[s].mean():.1%}")


if __name__ == "__main__":
    df = charger_tout()
    tr, Pr, yr = predictions(df, pd.Timestamp("2024-08-01"), pd.Timestamp("2025-08-01"))
    tt, Pt, yt = predictions(df, pd.Timestamp("2025-08-01"), pd.Timestamp("2026-10-21"))
    tableau(Pr, yr, f"RÉGLAGE 2024-25 ({len(yr)} matchs), modèle actuel :")
    res = minimize(lambda x: ll(corriger(Pr, *x), yr), [1.0, 0.0], method="Nelder-Mead")
    a, b = res.x
    print(f"\nCorrection réglée sur 2024-25 : a = {a:.3f}, b = {b:.3f}  (log loss réglage {ll(Pr, yr):.4f} -> {ll(corriger(Pr, a, b), yr):.4f})\n")
    tableau(Pt, yt, f"TEST 2025-26 ({len(yt)} matchs), AVANT correction :")
    Pc = corriger(Pt, a, b)
    tableau(Pc, yt, "TEST 2025-26, APRÈS correction :")
    print(f"\nTEST log loss : avant {ll(Pt, yt):.4f} · après {ll(Pc, yt):.4f} · "
          f"bons pronostics : {np.mean(Pt.argmax(1) == yt):.1%} (inchangés par construction)")
