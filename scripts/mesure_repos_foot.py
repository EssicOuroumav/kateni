"""
Kateni — foot : les enchaînements (peu de jours de repos) changent-ils le résultat ? (24/11/2026)
==================================================================================================
Demande du propriétaire : une équipe qui a joué 2 ou 3 jours avant (souvent en coupe d'Europe le mercredi)
perd-elle plus souvent ? Pronostic de référence = celui de l'app (25 % modèle + 75 % cotes du marché).
Repos = jours depuis le dernier match connu de l'équipe (championnats + coupes d'Europe ; les coupes
nationales ne sont pas dans les données). Correction : victoire dom × exp(b·x), victoire ext × exp(−b·x).
b réglé sur 2024-25, mesure finale sur 2025-26 et début 2026-27. Adopté seulement si la mesure s'améliore.

Usage : python3 scripts/mesure_repos_foot.py
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


def main():
    t0 = time.time()
    df = charger_tout()
    # Jours de repos de chaque équipe avant chaque match (toutes compétitions connues)
    lignes = pd.concat([df[["Date", "HomeTeam"]].rename(columns={"HomeTeam": "eq"}),
                        df[["Date", "AwayTeam"]].rename(columns={"AwayTeam": "eq"})]).drop_duplicates()
    lignes = lignes.sort_values(["eq", "Date"])
    lignes["repos"] = lignes.groupby("eq")["Date"].diff().dt.days
    repos = lignes.set_index(["eq", "Date"])["repos"]
    repos = repos[~repos.index.duplicated()]

    ch = df[df["competition"].isin(CHAMPIONNATS) & (df["Date"] >= REGLAGE[0]) & (df["Date"] < TEST[1])].copy()
    cotes = ch[["B365H", "B365D", "B365A"]].apply(pd.to_numeric, errors="coerce").to_numpy()
    ok = ~np.isnan(cotes).any(axis=1)
    ch, cotes = ch[ok].reset_index(drop=True), cotes[ok]
    lam = lambdas_v2(df, ch, REGLAGE[0], TEST[1])
    print(f"Buts attendus calculés pour {len(ch)} matchs ({time.time() - t0:.0f} s)", flush=True)
    p_mod = np.array([proba_1n2(a, b, -0.06)[0] for a, b in lam])
    p_mar = (1 / cotes) / (1 / cotes).sum(axis=1, keepdims=True)
    p = POIDS_MODELE * p_mod + (1 - POIDS_MODELE) * p_mar
    y = ch["FTR"].map({"H": 0, "D": 1, "A": 2}).to_numpy()
    rd = repos.reindex(list(zip(ch["HomeTeam"], ch["Date"]))).to_numpy(float)
    re_ = repos.reindex(list(zip(ch["AwayTeam"], ch["Date"]))).to_numpy(float)
    court_d = (rd <= 3).astype(float)   # NaN (premier match connu) -> pas court
    court_e = (re_ <= 3).astype(float)
    ecart = np.clip(np.nan_to_num(rd, nan=7) - np.nan_to_num(re_, nan=7), -7, 7) / 7

    def corrige(p, x, b):
        q = p * np.c_[np.exp(b * x), np.ones(len(x)), np.exp(-b * x)]
        return q / q.sum(axis=1, keepdims=True)

    reg = (ch["Date"] < REGLAGE[1]).to_numpy()
    tst = ~reg
    print(f"Réglage : {reg.sum()} matchs · Test : {tst.sum()} matchs")
    print(f"Matchs où une seule équipe a joué 3 jours avant ou moins : {int(((court_d + court_e) == 1).sum())}\n")
    base = log_loss(p[tst], y[tst])
    print(f"{'Version':52s} {'log loss test':>14s} {'bons pronostics':>16s}")
    print(f"{'Actuelle (25 % modèle + 75 % marché)':52s} {base:14.4f} {np.mean(p[tst].argmax(1) == y[tst]):16.1%}")
    for nom, x in (("+ joué 3 jours avant ou moins (dom − ext)", court_e - court_d),
                   ("+ différence de jours de repos", ecart)):
        b = minimize_scalar(lambda b: log_loss(corrige(p[reg], x[reg], b), y[reg]), bounds=(-1, 1), method="bounded").x
        q = corrige(p[tst], x[tst], b)
        print(f"{nom + f' (b = {b:+.3f})':52s} {log_loss(q, y[tst]):14.4f} {np.mean(q.argmax(1) == y[tst]):16.1%}")
    # Pour information : modèle seul (sans le marché, qui connaît déjà le calendrier)
    print("\nModèle seul (le marché tient sans doute déjà compte du calendrier) :")
    print(f"{'Modèle seul':52s} {log_loss(p_mod[tst], y[tst]):14.4f}")
    x = court_e - court_d
    b = minimize_scalar(lambda b: log_loss(corrige(p_mod[reg], x[reg], b), y[reg]), bounds=(-1, 1), method="bounded").x
    q = corrige(p_mod[tst], x[tst], b)
    print(f"{'Modèle seul + joué 3 jours avant' + f' (b = {b:+.3f})':52s} {log_loss(q, y[tst]):14.4f}")
    print(f"\nDurée : {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
