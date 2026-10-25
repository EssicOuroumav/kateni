"""
Kateni — la forme récente et les confrontations directes améliorent-elles le pronostic ?
==========================================================================================
Pronostic de référence = celui de l'app : 25 % modèle global + 75 % cotes du marché (marge retirée).
Pour chaque match, uniquement avec les matchs d'avant :
  - forme  = écart moyen « buts marqués − encaissés » par rapport à ce que le modèle attendait, sur les
             6 derniers matchs de chaque équipe (une équipe « en forme » fait mieux que prévu) ;
  - face-à-face = même écart, sur les 4 dernières confrontations des deux équipes (4 ans au plus).
Correction testée : victoire domicile × exp(+b·x), victoire extérieur × exp(−b·x), puis normalisation.
b est réglé sur 2024-25 et la mesure finale faite sur 2025-26 (log loss, plus bas = mieux).

Usage : python3 scripts/mesure_forme.py
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ameliorer import CHAMPIONNATS, REGLAGE, TEST, lambdas_v2, log_loss, proba_1n2  # noqa: E402
from kateni.config import POIDS_MODELE  # noqa: E402
from kateni.donnees import charger_tout  # noqa: E402

DEBUT = pd.Timestamp("2023-08-01")


def main():
    t0 = time.time()
    df = charger_tout()
    tous = df[(df["Date"] >= DEBUT) & (df["Date"] < TEST[1])].reset_index(drop=True)
    lam = lambdas_v2(df, tous, DEBUT, TEST[1])
    tous["ecart_attendu"] = lam[:, 0] - lam[:, 1]
    tous["residu"] = (tous["FTHG"] - tous["FTAG"]) - tous["ecart_attendu"]   # du point de vue du domicile
    print(f"Buts attendus calculés pour {len(tous)} matchs ({time.time() - t0:.0f} s)", flush=True)

    # Historique par équipe : (date, résidu de son point de vue)
    lignes = pd.concat([tous[["Date", "HomeTeam", "residu"]].rename(columns={"HomeTeam": "eq"}),
                        tous[["Date", "AwayTeam", "residu"]].rename(columns={"AwayTeam": "eq"})
                        .assign(residu=lambda x: -x["residu"])]).sort_values("Date")
    par_eq = {e: g for e, g in lignes.groupby("eq")}

    def forme(eq, date, n=6):
        g = par_eq.get(eq)
        if g is None:
            return 0.0
        g = g[g["Date"] < date].tail(n)
        return float(g["residu"].mean()) if len(g) >= 3 else 0.0

    def face_a_face(dom, ext, date):
        h = tous[(tous["Date"] < date) & (tous["Date"] >= date - pd.Timedelta(days=4 * 365))
                 & (((tous.HomeTeam == dom) & (tous.AwayTeam == ext)) | ((tous.HomeTeam == ext) & (tous.AwayTeam == dom)))]
        h = h.tail(4)
        if not len(h):
            return 0.0
        return float(np.where(h.HomeTeam == dom, h.residu, -h.residu).mean())

    ch = tous[tous["competition"].isin(CHAMPIONNATS) & (tous["Date"] >= REGLAGE[0])].copy()
    cotes = ch[["B365H", "B365D", "B365A"]].apply(pd.to_numeric, errors="coerce").to_numpy()
    ok = ~np.isnan(cotes).any(axis=1)
    ch, cotes = ch[ok].reset_index(drop=True), cotes[ok]
    lam_ch = np.c_[ch["ecart_attendu"]]  # (non utilisé directement)
    i_ch = tous.reset_index().merge(ch[["Date", "HomeTeam", "AwayTeam"]], on=["Date", "HomeTeam", "AwayTeam"])["index"]
    p_mod = np.array([proba_1n2(a, b, -0.06)[0] for a, b in lam[i_ch.to_numpy()]])
    p_mar = (1 / cotes) / (1 / cotes).sum(axis=1, keepdims=True)
    p = POIDS_MODELE * p_mod + (1 - POIDS_MODELE) * p_mar
    ch["f"] = [forme(r.HomeTeam, r.Date) - forme(r.AwayTeam, r.Date) for r in ch.itertuples()]
    ch["h"] = [face_a_face(r.HomeTeam, r.AwayTeam, r.Date) for r in ch.itertuples()]
    y = ch["FTR"].map({"H": 0, "D": 1, "A": 2}).to_numpy()
    print(f"Variables calculées ({time.time() - t0:.0f} s)\n", flush=True)

    def corrige(p, x, b):
        q = p * np.c_[np.exp(b * x), np.ones(len(x)), np.exp(-b * x)]
        return q / q.sum(axis=1, keepdims=True)

    reg = (ch["Date"] < REGLAGE[1]).to_numpy()
    tst = ~reg
    print(f"Réglage : {reg.sum()} matchs (2024-25) · Test : {tst.sum()} matchs (2025-26 et début 2026-27)\n")
    print(f"{'Version':45s} {'log loss test':>14s} {'bons pronostics':>16s}")
    base = log_loss(p[tst], y[tst])
    print(f"{'Actuelle (25 % modèle + 75 % marché)':45s} {base:14.4f} {np.mean(p[tst].argmax(1) == y[tst]):16.1%}")
    for nom, col in (("+ forme des 6 derniers matchs", "f"), ("+ confrontations directes", "h")):
        x = ch[col].to_numpy()
        b = minimize_scalar(lambda b: log_loss(corrige(p[reg], x[reg], b), y[reg]), bounds=(-1, 1), method="bounded").x
        q = corrige(p[tst], x[tst], b)
        print(f"{nom + f' (b = {b:+.3f})':45s} {log_loss(q, y[tst]):14.4f} {np.mean(q.argmax(1) == y[tst]):16.1%}")
    print(f"\nDurée : {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
