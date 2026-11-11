"""
Matrice des scores -> tous les marchés.
Le même code sert à l'avant-match (score de départ 0-0) et au live
(score actuel + buts restants).
"""

import numpy as np
from scipy.stats import poisson

MAX_BUTS = 10
LIGNES_TOTAL = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5]


def matrice_scores(lam_d: float, lam_e: float, rho: float = 0.0) -> np.ndarray:
    """P(dom marque i, ext marque j), avec correction Dixon-Coles des petits scores."""
    k = np.arange(MAX_BUTS + 1)
    m = np.outer(poisson.pmf(k, lam_d), poisson.pmf(k, lam_e))
    if rho:
        m[0, 0] *= 1 - lam_d * lam_e * rho
        m[0, 1] *= 1 + lam_d * rho
        m[1, 0] *= 1 + lam_e * rho
        m[1, 1] *= 1 - rho
    m = np.clip(m, 0, None)
    return m / m.sum()


def matrice_finale(m_restants: np.ndarray, buts_d: int, buts_e: int) -> np.ndarray:
    """Décale la matrice des buts restants par le score actuel -> matrice du score final."""
    taille = MAX_BUTS + 1 + max(buts_d, buts_e)
    f = np.zeros((taille, taille))
    f[buts_d:buts_d + MAX_BUTS + 1, buts_e:buts_e + MAX_BUTS + 1] = m_restants
    return f


def marches(m: np.ndarray) -> dict[str, dict[str, float]]:
    """Probabilités de tous les marchés à partir d'une matrice de score FINAL."""
    i, j = np.indices(m.shape)
    total = i + j
    p1, pn, p2 = m[i > j].sum(), m[i == j].sum(), m[i < j].sum()
    res = {
        "1N2": {"1": p1, "N": pn, "2": p2},
        "Double chance": {"1N": p1 + pn, "12": p1 + p2, "N2": pn + p2},
        "Les deux équipes marquent": {"Oui": m[(i > 0) & (j > 0)].sum(),
                                      "Non": m[(i == 0) | (j == 0)].sum()},
    }
    for ligne in LIGNES_TOTAL:
        plus = m[total > ligne].sum()
        res[f"Total buts {ligne}"] = {"Plus": plus, "Moins": 1 - plus}
    res["Dom. marque"] = {"Oui": m[i > 0].sum(), "Non": m[i == 0].sum()}
    res["Ext. marque"] = {"Oui": m[j > 0].sum(), "Non": m[j == 0].sum()}
    return {k: {s: float(p) for s, p in v.items()} for k, v in res.items()}


def scores_probables(m: np.ndarray, n: int = 5) -> list[tuple[str, float]]:
    plat = [(f"{i}-{j}", float(m[i, j])) for i in range(m.shape[0]) for j in range(m.shape[1])]
    return sorted(plat, key=lambda x: -x[1])[:n]


def calibrer(p: dict) -> dict:
    """Corrige la prudence du modèle sur les favoris (1N2 d'avant-match), puis recalcule la double chance ;
    corrige aussi « les deux équipes marquent », trop tranché sans correction. Les buts ne sont pas touchés."""
    from kateni.config import BTTS_A, BTTS_B, CALIB_A, CALIB_B
    q = dict(p["1N2"])
    fav = max(q, key=q.get)
    pf = min(max(q[fav], 1e-6), 1 - 1e-6)
    nf = 1 / (1 + np.exp(-(CALIB_A * np.log(pf / (1 - pf)) + CALIB_B)))
    facteur = (1 - nf) / (1 - pf)
    q = {k: (nf if k == fav else v * facteur) for k, v in q.items()}
    out = dict(p)
    out["1N2"] = {k: float(v) for k, v in q.items()}
    out["Double chance"] = {"1N": q["1"] + q["N"], "12": q["1"] + q["2"], "N2": q["N"] + q["2"]}
    if "Les deux équipes marquent" in p:
        b = min(max(p["Les deux équipes marquent"]["Oui"], 1e-6), 1 - 1e-6)
        oui = float(1 / (1 + np.exp(-(BTTS_A * np.log(b / (1 - b)) + BTTS_B))))
        out["Les deux équipes marquent"] = {"Oui": oui, "Non": 1 - oui}
    return out


def regler(marche: str, selection: str, buts_d: int, buts_e: int) -> bool | None:
    """Le pari est-il gagné avec ce score final ? None = marché non réglable automatiquement."""
    m = np.zeros((max(buts_d, buts_e) + 1,) * 2)
    m[buts_d, buts_e] = 1.0
    p = marches(m)
    if marche in p and selection in p[marche]:
        return p[marche][selection] > 0.5
    return None
