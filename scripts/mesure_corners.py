"""
Kateni — mesure du modèle de corners
=====================================
Réglage sur 2024-25 (dispersion, demi-vie), mesure sur 2025-26 : chaque semaine, le modèle est réajusté avec
les seuls matchs passés, puis prédit les corners de la semaine. Comparaison avec une référence naïve
(moyenne du championnat) et contrôle de calibration (chance annoncée contre fréquence réelle).

Usage : python3 scripts/mesure_corners.py
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
from kateni.corners import SEUILS_EQUIPE, SEUILS_TOTAL, ajuster_corners, donnees_corners  # noqa: E402
from kateni.donnees import charger_tout  # noqa: E402


def attendus(df, matchs, debut, fin, **reglages):
    out = np.zeros((len(matchs), 2))
    for d0 in semaines(debut, fin):
        sel = (matchs["Date"] >= d0) & (matchs["Date"] < d0 + pd.Timedelta(days=7))
        if not sel.any():
            continue
        m = ajuster_corners(df, date_ref=d0, **reglages)
        for k in np.flatnonzero(sel.to_numpy()):
            r = matchs.iloc[k]
            out[k] = m.lambdas(r.HomeTeam, r.AwayTeam, r.competition)
    return out


def naif(df, matchs):
    """Moyenne du championnat sur les 365 jours précédents (domicile, extérieur)."""
    out = np.zeros((len(matchs), 2))
    for k, r in enumerate(matchs.itertuples()):
        p = df[(df.competition == r.competition) & (df.Date < r.Date) & (df.Date >= r.Date - pd.Timedelta(days=365))]
        out[k] = (p.FTHG.mean(), p.FTAG.mean())
    return out


def nll(y, moy, taille):
    return float(-np.mean(nbinom.logpmf(y, taille, taille / (taille + moy))))


def calibration(moy, y, seuils, taille, nom):
    lignes = []
    for s in seuils:
        p = nbinom.sf(np.floor(s), taille, taille / (taille + moy))
        reel = (y > s).astype(float)
        lignes.append({"Marché": f"{nom} plus de {s}", "Chance moyenne annoncée": p.mean(), "Fréquence réelle": reel.mean(),
                       "Brier": np.mean((p - reel) ** 2), "Brier naïf": np.mean((reel.mean() - reel) ** 2)})
    return lignes


def main():
    t0 = time.time()
    df = charger_tout()
    dc = donnees_corners(df)
    reg = dc[(dc.Date >= REGLAGE[0]) & (dc.Date < REGLAGE[1])].reset_index(drop=True)
    tst = dc[(dc.Date >= TEST[0]) & (dc.Date < TEST[1])].reset_index(drop=True)
    print(f"Réglage : {len(reg)} matchs · Test : {len(tst)} matchs\n")

    # 1. Réglage : demi-vie et rappel vers la moyenne (erreur sur les corners de chaque équipe)
    best = None
    for dv in (180, 365):
        for rg in (3.0, 10.0, 30.0, 100.0):
            a = attendus(df, reg, *REGLAGE, demi_vie=dv, ridge=rg)
            err = float(np.mean((a[:, 0] - reg.FTHG) ** 2 + (a[:, 1] - reg.FTAG) ** 2) / 2)
            print(f"  demi-vie {dv:>3} j · rappel {rg:>4} : erreur quadratique {err:.3f} ({time.time()-t0:.0f} s)", flush=True)
            if best is None or err < best[0]:
                best = (err, dv, rg, a)
    _, DV, RG, a_reg = best
    # 2. Dispersion (binomiale négative), par équipe et pour le total
    y_eq = np.concatenate([reg.FTHG, reg.FTAG])
    m_eq = np.concatenate([a_reg[:, 0], a_reg[:, 1]])
    T_EQ = minimize_scalar(lambda t: nll(y_eq, m_eq, t), bounds=(1, 500), method="bounded").x
    T_TOT = minimize_scalar(lambda t: nll(reg.FTHG + reg.FTAG, a_reg.sum(1), t), bounds=(1, 500), method="bounded").x
    print(f"\n-> retenu : demi-vie {DV} j, rappel {RG}, taille équipe {T_EQ:.1f}, taille total {T_TOT:.1f}\n")

    # 3. Mesure finale
    a = attendus(df, tst, *TEST, demi_vie=DV, ridge=RG)
    nv = naif(dc, tst)
    tot, tot_n = a.sum(1), nv.sum(1)
    y_tot = (tst.FTHG + tst.FTAG).to_numpy()
    print("Période de test (2025-26) :")
    print(f"  Corners total — écart moyen : modèle {np.mean(np.abs(tot - y_tot)):.2f} · naïf {np.mean(np.abs(tot_n - y_tot)):.2f}")
    print(f"  Corners total — log loss  : modèle {nll(y_tot, tot, T_TOT):.4f} · naïf {nll(y_tot, tot_n, T_TOT):.4f}")
    y_e = np.concatenate([tst.FTHG, tst.FTAG])
    print(f"  Corners équipe — log loss : modèle {nll(y_e, np.concatenate([a[:, 0], a[:, 1]]), T_EQ):.4f} · "
          f"naïf {nll(y_e, np.concatenate([nv[:, 0], nv[:, 1]]), T_EQ):.4f}")
    lignes = calibration(tot, y_tot, SEUILS_TOTAL, T_TOT, "Total")
    lignes += calibration(a[:, 0], tst.FTHG.to_numpy(), SEUILS_EQUIPE, T_EQ, "Domicile")
    lignes += calibration(a[:, 1], tst.FTAG.to_numpy(), SEUILS_EQUIPE, T_EQ, "Extérieur")
    print("\n" + pd.DataFrame(lignes).round(3).to_string(index=False))
    print(f"\nDurée : {time.time()-t0:.0f} s")


if __name__ == "__main__":
    main()
