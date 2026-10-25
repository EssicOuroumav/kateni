"""
Kateni — mesure des modèles de tirs, tirs cadrés, fautes et du marché « plus grand nombre » (corners compris)
=============================================================================================================
Réglage sur 2024-25 (rappel vers la moyenne, dispersion), mesure sur 2025-26, comme scripts/mesure_corners.py.
Usage : python3 scripts/mesure_stats.py
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import nbinom

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ameliorer import REGLAGE, TEST, semaines  # noqa: E402
from kateni import modele  # noqa: E402
from kateni.corners import TAILLE_EQUIPE as T_CORNERS  # noqa: E402
from kateni.donnees import charger_tout  # noqa: E402
from kateni.statistiques import STATS, donnees_stat, plus_grand_nombre  # noqa: E402

A_MESURER = {**{n: v[:2] for n, v in STATS.items()}, "Corners": ("HC", "AC")}


def attendus(dstat, matchs, debut, fin, ridge):
    out = np.zeros((len(matchs), 2))
    for d0 in semaines(debut, fin):
        sel = (matchs["Date"] >= d0) & (matchs["Date"] < d0 + pd.Timedelta(days=7))
        if not sel.any():
            continue
        m = modele.ajuster(dstat, date_ref=d0, ridge=ridge)
        for k in np.flatnonzero(sel.to_numpy()):
            r = matchs.iloc[k]
            out[k] = m.lambdas(r.HomeTeam, r.AwayTeam, r.competition)
    return out


def naif(dstat, matchs):
    out = np.zeros((len(matchs), 2))
    for k, r in enumerate(matchs.itertuples()):
        p = dstat[(dstat.competition == r.competition) & (dstat.Date < r.Date) & (dstat.Date >= r.Date - pd.Timedelta(days=365))]
        out[k] = (p.FTHG.mean(), p.FTAG.mean())
    return out


def nll(y, moy, t):
    return float(-np.mean(nbinom.logpmf(y, t, t / (t + moy))))


def main():
    t0 = time.time()
    df = charger_tout()
    for nom, (cd, ce) in A_MESURER.items():
        d = donnees_stat(df, cd, ce)
        reg = d[(d.Date >= REGLAGE[0]) & (d.Date < REGLAGE[1])].reset_index(drop=True)
        tst = d[(d.Date >= TEST[0]) & (d.Date < TEST[1])].reset_index(drop=True)
        print(f"===== {nom} : réglage {len(reg)} matchs, test {len(tst)} matchs", flush=True)
        if nom == "Corners":
            rg, t_eq = 30.0, T_CORNERS          # déjà mesurés (docs/mesures/2026-10-21_corners.txt)
            a_reg = None
        else:
            best = None
            for rg_ in (10.0, 30.0, 100.0):
                a = attendus(d, reg, *REGLAGE, rg_)
                err = float(np.mean((a[:, 0] - reg.FTHG) ** 2 + (a[:, 1] - reg.FTAG) ** 2))
                print(f"  rappel {rg_:>5} : erreur {err:.2f}", flush=True)
                best = min(best or (9e9,), (err, rg_, a))
            _, rg, a_reg = best
            y_eq, m_eq = np.r_[reg.FTHG, reg.FTAG], np.r_[a_reg[:, 0], a_reg[:, 1]]
            t_eq = minimize_scalar(lambda t: nll(y_eq, m_eq, t), bounds=(1, 500), method="bounded").x
            t_tot = minimize_scalar(lambda t: nll(reg.FTHG + reg.FTAG, a_reg.sum(1), t), bounds=(1, 500), method="bounded").x
            print(f"  -> rappel {rg}, taille équipe {t_eq:.1f}, taille total {t_tot:.1f}")
        a = attendus(d, tst, *TEST, rg)
        nv = naif(d, tst)
        y_e = np.r_[tst.FTHG, tst.FTAG]
        print(f"  Test, log loss par équipe : modèle {nll(y_e, np.r_[a[:, 0], a[:, 1]], t_eq):.4f} · "
              f"naïf {nll(y_e, np.r_[nv[:, 0], nv[:, 1]], t_eq):.4f}")
        if nom != "Corners":
            y_t = (tst.FTHG + tst.FTAG).to_numpy()
            print(f"  Test, écart moyen total : modèle {np.mean(np.abs(a.sum(1) - y_t)):.2f} · naïf {np.mean(np.abs(nv.sum(1) - y_t)):.2f}")
        # « Plus grand nombre »
        pg = np.array([[v["1"], v["N"], v["2"]] for v in (plus_grand_nombre(x, z, t_eq) for x, z in a)])
        pn = np.array([[v["1"], v["N"], v["2"]] for v in (plus_grand_nombre(x, z, t_eq) for x, z in nv)])
        y = np.select([tst.FTHG > tst.FTAG, tst.FTHG == tst.FTAG], [0, 1], 2)
        ll = lambda p: float(np.mean(-np.log(np.clip(p[np.arange(len(y)), y], 1e-9, 1))))  # noqa: E731
        print(f"  Plus grand nombre — log loss : modèle {ll(pg):.4f} · naïf {ll(pn):.4f} · "
              f"bons pronostics {np.mean(pg.argmax(1) == y):.1%}")
        print(f"    chance moyenne annoncée dom/égalité/ext : {pg.mean(0).round(3)} · réel : "
              f"{np.bincount(y, minlength=3) / len(y)}")
        for lo, hi in ((0, .4), (.4, .55), (.55, .7), (.7, 1)):
            s = (pg[:, 0] >= lo) & (pg[:, 0] < hi)
            if s.sum() > 50:
                print(f"    domicile annoncé {lo:.0%}-{hi:.0%} : {pg[s, 0].mean():.1%} annoncé, {np.mean(y[s] == 0):.1%} réel ({s.sum()} matchs)")
        print(f"  ({time.time() - t0:.0f} s)\n", flush=True)


if __name__ == "__main__":
    main()
