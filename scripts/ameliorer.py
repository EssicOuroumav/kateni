"""
Kateni — amélioration mesurée du modèle de prédiction
=======================================================
Méthode (sans fuite de données) :
  - période de RÉGLAGE : 01/08/2024 -> 31/07/2025 (tous les choix sont faits ici)
  - période de TEST    : 01/08/2025 -> aujourd'hui (mesure finale, jamais utilisée pour régler)
Chaque semaine, les modèles sont réajustés avec les seuls matchs passés, puis prédisent la semaine.

Améliorations testées :
  1. réglages du modèle V2 (demi-vie, poids du xG, rappel vers la moyenne)
  2. matchs nuls (correction des petits scores rho + facteur sur la diagonale)
  3. correction de confiance (exposant de calibration sur les probabilités 1N2)
  4. combinaison V1 + V2 (poids par championnat)

Usage : python3 scripts/ameliorer.py            (≈ 15 minutes)
Résultat : tableau avant/après + reglages_modele.json (lu par l'app si on décide de l'adopter)
"""

import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import poisson

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kateni.config import COMPETITIONS, RACINE  # noqa: E402
from kateni.donnees import charger_tout  # noqa: E402
from kateni.modele import ajuster  # noqa: E402
from kateni.modele_v1 import ajuster_v1  # noqa: E402

REGLAGE = (pd.Timestamp("2024-08-01"), pd.Timestamp("2025-08-01"))
TEST = (pd.Timestamp("2025-08-01"), pd.Timestamp("2026-10-21"))
K = np.arange(11)
CHAMPIONNATS = [c for c, comp in COMPETITIONS.items() if comp.fd_code]


# ------------------------------------------------------------------ probabilités
def proba_1n2(ld, le, rho=0.0, nul=0.0, expo=1.0):
    m = np.outer(poisson.pmf(K, ld), poisson.pmf(K, le))
    if rho:
        m[0, 0] *= 1 - ld * le * rho
        m[0, 1] *= 1 + ld * rho
        m[1, 0] *= 1 + le * rho
        m[1, 1] *= 1 - rho
    m = np.clip(m, 0, None)
    i, j = np.indices(m.shape)
    p = np.array([m[i > j].sum(), m[i == j].sum() * (1 + nul), m[i < j].sum()])
    p = p / p.sum()
    if expo != 1.0:
        p = p ** expo
        p = p / p.sum()
    tot = m / m.sum()
    return p, tot[(i + j) > 2.5].sum(), tot[(i > 0) & (j > 0)].sum()


def log_loss(p, y):
    return float(np.mean(-np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1))))


def bin_ll(p, y):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(np.mean(-(y * np.log(p) + (1 - y) * np.log(1 - p))))


# ------------------------------------------------------------------ prédictions semaine par semaine
def semaines(debut, fin):
    return list(pd.date_range(debut, fin, freq="7D"))


def lambdas_v2(df, matchs, debut, fin, **reglages):
    out = np.zeros((len(matchs), 2))
    for d0 in semaines(debut, fin):
        sel = (matchs["Date"] >= d0) & (matchs["Date"] < d0 + pd.Timedelta(days=7))
        if not sel.any():
            continue
        m = ajuster(df, date_ref=d0, **reglages)
        for k in np.flatnonzero(sel.to_numpy()):
            r = matchs.iloc[k]
            out[k] = m.lambdas(r.HomeTeam, r.AwayTeam, r.competition)
    return out


def lambdas_v1(df, matchs, debut, fin):
    out = np.zeros((len(matchs), 2))
    for d0 in semaines(debut, fin):
        sel = (matchs["Date"] >= d0) & (matchs["Date"] < d0 + pd.Timedelta(days=7))
        if not sel.any():
            continue
        passe = df[df["Date"] < d0]
        cache = {}
        for k in np.flatnonzero(sel.to_numpy()):
            r = matchs.iloc[k]
            if r.competition not in cache:
                cache[r.competition] = ajuster_v1(passe[passe["competition"] == r.competition])
            out[k] = cache[r.competition].lambdas(r.HomeTeam, r.AwayTeam)
    return out


def main():
    t0 = time.time()
    df = charger_tout()
    dom = df[df["competition"].isin(CHAMPIONNATS)]
    reg = dom[(dom["Date"] >= REGLAGE[0]) & (dom["Date"] < REGLAGE[1])].reset_index(drop=True)
    tst = dom[(dom["Date"] >= TEST[0]) & (dom["Date"] < TEST[1])].reset_index(drop=True)
    y_reg = reg["FTR"].map({"H": 0, "D": 1, "A": 2}).to_numpy()
    y_tst = tst["FTR"].map({"H": 0, "D": 1, "A": 2}).to_numpy()
    print(f"Réglage : {len(reg)} matchs (2024-25) · Test : {len(tst)} matchs (2025-26 et début 2026-27)\n")

    def evaluer(lam, y, rho=0.0, nul=0.0, expo=1.0):
        p = np.array([proba_1n2(a, b, rho, nul, expo)[0] for a, b in lam])
        return log_loss(p, y), p

    # 1. Réglages V2 (sur la période de réglage uniquement)
    grille = list(itertools.product([180, 270, 365, 540], [0.0, 0.5, 0.8], [1.0, 3.0, 8.0]))
    meilleur = None
    for dv, px, rg in grille:
        import kateni.modele as mod
        mod.POIDS_XG = px
        lam = lambdas_v2(df, reg, *REGLAGE, demi_vie=dv, ridge=rg)
        ll, _ = evaluer(lam, y_reg, rho=-0.06)
        print(f"  demi-vie {dv:>3} j · xG {px:.1f} · rappel {rg:>3} : {ll:.4f}")
        if meilleur is None or ll < meilleur[0]:
            meilleur = (ll, dv, px, rg, lam)
    _, DV, PX, RG, lam2_reg = meilleur
    import kateni.modele as mod
    mod.POIDS_XG = PX
    print(f"-> réglage retenu : demi-vie {DV} j, poids xG {PX}, rappel {RG}  ({time.time()-t0:.0f} s)\n")

    # 2. Nuls : rho et facteur sur la diagonale
    best = (9, 0, 0)
    for rho in (0.0, -0.03, -0.06, -0.1, -0.15):
        for nul in (0.0, 0.03, 0.06, 0.1):
            ll, _ = evaluer(lam2_reg, y_reg, rho, nul)
            best = min(best, (ll, rho, nul))
    _, RHO, NUL = best
    print(f"-> matchs nuls : rho {RHO}, facteur nul +{NUL:.0%}")

    # 3. Calibration : exposant
    r = minimize_scalar(lambda a: evaluer(lam2_reg, y_reg, RHO, NUL, a)[0], bounds=(0.6, 1.6), method="bounded")
    EXPO = round(float(r.x), 3)
    print(f"-> correction de confiance : exposant {EXPO}")

    # 4. Combinaison V1 + V2, poids par championnat (choisi sur la période de réglage)
    lam1_reg = lambdas_v1(df, reg, *REGLAGE)
    p1_reg = np.array([proba_1n2(a, b)[0] for a, b in lam1_reg])
    _, p2_reg = evaluer(lam2_reg, y_reg, RHO, NUL, EXPO)
    POIDS_V1 = {}
    for c in CHAMPIONNATS:
        s = (reg["competition"] == c).to_numpy()
        if not s.any():
            continue
        scores = {w: log_loss(w * p1_reg[s] + (1 - w) * p2_reg[s], y_reg[s]) for w in np.linspace(0, 1, 11)}
        POIDS_V1[c] = round(float(min(scores, key=scores.get)), 2)
    print(f"-> poids du modèle d'origine par championnat : {POIDS_V1}\n")

    # ------------------------------------------------------------- MESURE FINALE sur la période de test
    print(f"Mesure finale sur la période de test ({time.time()-t0:.0f} s écoulées)…")
    mod.POIDS_XG = 0.5
    lam2_old = lambdas_v2(df, tst, *TEST)                        # V2 d'avant
    mod.POIDS_XG = PX
    lam2_new = lambdas_v2(df, tst, *TEST, demi_vie=DV, ridge=RG)  # V2 réglé
    lam1 = lambdas_v1(df, tst, *TEST)
    p1 = np.array([proba_1n2(a, b)[0] for a, b in lam1])
    p2_old = np.array([proba_1n2(a, b, -0.06)[0] for a, b in lam2_old])
    p2_new = np.array([proba_1n2(a, b, RHO, NUL, EXPO)[0] for a, b in lam2_new])
    w = tst["competition"].map(POIDS_V1).fillna(0).to_numpy()[:, None]
    p_ens = w * p1 + (1 - w) * p2_new
    # « Avant » = le choix actuel de l'app (V1 en PL, L1, BEL, TUR ; V2 ailleurs)
    from kateni.config import MODELE_PAR_COMPETITION
    v1_ici = tst["competition"].map(lambda c: MODELE_PAR_COMPETITION.get(c) == "V1").to_numpy()[:, None]
    p_avant = np.where(v1_ici, p1, p2_old)

    marche = tst[["B365H", "B365D", "B365A"]].apply(pd.to_numeric, errors="coerce").to_numpy()
    ok = ~np.isnan(marche).any(axis=1)
    pm = (1 / marche[ok]) / (1 / marche[ok]).sum(axis=1, keepdims=True)

    def ligne(nom, p):
        return {"Version": nom, "Bons pronostics 1N2": f"{np.mean(p.argmax(1) == y_tst):.1%}",
                "Log loss 1N2": round(log_loss(p, y_tst), 4),
                "Log loss (matchs avec cotes)": round(log_loss(p[ok], y_tst[ok]), 4)}
    tab = pd.DataFrame([ligne("Avant (app actuelle)", p_avant), ligne("V2 réglé + nuls + confiance", p2_new),
                        ligne("Après (combinaison V1 + V2 réglé)", p_ens)])
    tab.loc[len(tab)] = {"Version": "Cotes du marché (référence)", "Bons pronostics 1N2": f"{np.mean(pm.argmax(1) == y_tst[ok]):.1%}",
                         "Log loss 1N2": "–", "Log loss (matchs avec cotes)": round(log_loss(pm, y_tst[ok]), 4)}
    print("\n" + tab.to_string(index=False))

    par = pd.DataFrame({"c": tst["competition"], "avant": [-np.log(p_avant[i, y]) for i, y in enumerate(y_tst)],
                        "apres": [-np.log(p_ens[i, y]) for i, y in enumerate(y_tst)]}).groupby("c").mean()
    par["gain"] = np.where(par.apres < par.avant, "mieux", "moins bien")
    print("\nPar championnat (log loss 1N2, période de test) :\n" + par.round(4).to_string())

    reglages = {"date": pd.Timestamp.today().strftime("%Y-%m-%d"), "demi_vie": DV, "poids_xg": PX, "ridge": RG,
                "rho": RHO, "facteur_nul": NUL, "exposant": EXPO, "poids_v1": POIDS_V1,
                "mesure_test": tab.to_dict("records")}
    (RACINE / "reglages_modele_candidat.json").write_text(json.dumps(reglages, indent=2, ensure_ascii=False))
    print(f"\nRéglages candidats écrits dans reglages_modele_candidat.json ({time.time()-t0:.0f} s au total)")


if __name__ == "__main__":
    main()
