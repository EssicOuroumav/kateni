"""
Kateni — synthèse : modèle de l'app (meilleur par championnat) contre le marché
Matchs de championnat du 01/08/2025 au 20/10/2026, chacun prédit avec les seules données d'avant.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import poisson

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kateni.config import COMPETITIONS, MODELE_PAR_COMPETITION  # noqa: E402
from kateni.donnees import charger_tout  # noqa: E402
from kateni.modele import ajuster  # noqa: E402
from kateni.modele_v1 import ajuster_v1  # noqa: E402

K = np.arange(11)
PRINCIPAUX = ["PL", "LIGA", "L1", "SA", "BL", "POR", "TUR", "BEL", "NED", "CHAMP", "LIGA2", "L2"]


def probas(ld, le, rho):
    m = np.outer(poisson.pmf(K, ld), poisson.pmf(K, le))
    if rho:
        m[0, 0] *= 1 - ld * le * rho; m[0, 1] *= 1 + ld * rho; m[1, 0] *= 1 + le * rho; m[1, 1] *= 1 - rho
    m = np.clip(m, 0, None); m /= m.sum(); i, j = np.indices(m.shape)
    return [m[i > j].sum(), m[i == j].sum(), m[i < j].sum()], m[(i + j) > 2.5].sum()


df = charger_tout()
t = df[df.competition.isin(PRINCIPAUX) & (df.Date >= "2025-08-01")].reset_index(drop=True)
P, OV = np.zeros((len(t), 3)), np.zeros(len(t))
for d0 in pd.date_range("2025-08-01", "2026-10-21", freq="7D"):
    s = ((t.Date >= d0) & (t.Date < d0 + pd.Timedelta(days=7))).to_numpy()
    if not s.any():
        continue
    m2 = ajuster(df, date_ref=d0); passe = df[df.Date < d0]; v1 = {}
    for k in np.flatnonzero(s):
        r = t.iloc[k]
        if MODELE_PAR_COMPETITION.get(r.competition) == "V1":
            if r.competition not in v1:
                v1[r.competition] = ajuster_v1(passe[passe.competition == r.competition])
            P[k], OV[k] = probas(*v1[r.competition].lambdas(r.HomeTeam, r.AwayTeam), 0.0)
        else:
            P[k], OV[k] = probas(*m2.lambdas(r.HomeTeam, r.AwayTeam, r.competition), m2.rho)

y = t.FTR.map({"H": 0, "D": 1, "A": 2}).to_numpy()
over = ((t.FTHG + t.FTAG) > 2.5).astype(int).to_numpy()
c = t[["B365H", "B365D", "B365A"]].apply(pd.to_numeric, errors="coerce").to_numpy()
cc = t[["B365CH", "B365CD", "B365CA"]].apply(pd.to_numeric, errors="coerce").to_numpy() if "B365CH" in t else c * np.nan
ok = ~np.isnan(c).any(1)
M = (1 / c) / (1 / c).sum(1, keepdims=True)
ll = lambda p, yy: float(np.mean(-np.log(np.clip(p[np.arange(len(yy)), yy], 1e-12, 1))))
rps = lambda p, yy: float(np.mean([((np.cumsum(pp)[:2] - np.cumsum(np.eye(3)[v])[:2]) ** 2).sum() / 2 for pp, v in zip(p, yy)]))

print(f"MATCHS : {len(t)} (avec cotes : {ok.sum()}), 12 championnats européens, 01/08/2025 -> 20/10/2026\n")
print("1N2                        Kateni    Marché (Bet365, marge retirée)")
print(f"Bons pronostics          {np.mean(P[ok].argmax(1)==y[ok]):8.1%}  {np.mean(M[ok].argmax(1)==y[ok]):8.1%}")
print(f"Log loss (bas=mieux)     {ll(P[ok],y[ok]):8.4f}  {ll(M[ok],y[ok]):8.4f}")
print(f"RPS (bas=mieux)          {rps(P[ok],y[ok]):8.4f}  {rps(M[ok],y[ok]):8.4f}")
print(f"Marge moyenne Bet365 1N2 : {np.mean((1/c[ok]).sum(1)-1):.1%}")
fav = P[ok].max(1) >= 0.6
print(f"Quand Kateni donne un favori à ≥ 60 % : {fav.sum()} matchs, il gagne {np.mean(P[ok][fav].argmax(1)==y[ok][fav]):.1%} (marché sur ces matchs : {np.mean(M[ok][fav].argmax(1)==y[ok][fav]):.1%})")
print(f"Nuls : réels {np.mean(y[ok]==1):.1%} · moyenne prévue Kateni {P[ok][:,1].mean():.1%} · marché {M[ok][:,1].mean():.1%}")

o = t[["B365>2.5", "B365<2.5"]].apply(pd.to_numeric, errors="coerce").to_numpy() if "B365>2.5" in t else None
if o is not None:
    oko = ~np.isnan(o).any(1)
    mo = (1 / o[oko, 0]) / (1 / o[oko]).sum(1)
    print(f"\nPLUS DE 2,5 BUTS ({oko.sum()} matchs) : bons pronostics Kateni {np.mean((OV[oko]>.5)==over[oko]):.1%} · marché {np.mean((mo>.5)==over[oko]):.1%}")

print("\nCALIBRATION (Kateni annonce X % pour le favori → il gagne réellement Y %)")
pf, gf = P.max(1), (P.argmax(1) == y)
for a, b in [(.33, .4), (.4, .5), (.5, .6), (.6, .7), (.7, 1)]:
    s = (pf >= a) & (pf < b)
    print(f"  {a:.0%}-{b:.0%} : {s.sum():5d} matchs · annoncé {pf[s].mean():.1%} · réel {gf[s].mean():.1%}")

print("\nPARIS SIMULÉS à 1 FCFA (cote Bet365 d'avant-match), pari si espérance Kateni ≥ 3 %")
for nom, cotes_pari in (("modèle seul", c), ):
    ev = P * cotes_pari - 1; k = np.nanargmax(np.where(np.isnan(ev), -9, ev), 1); e = ev[np.arange(len(t)), k]
    s = ok & (e >= 0.03); g = np.where(k[s] == y[s], cotes_pari[s, k[s]] - 1, -1)
    clv = (cotes_pari[s, k[s]] / cc[s, k[s]] - 1) if not np.isnan(cc).all() else np.array([np.nan])
    print(f"  {nom} : {s.sum()} paris · ROI {g.mean():+.1%} · battre la cote de clôture : {np.nanmean(clv > 0):.0%} des paris")
print(f"  Référence « parier tout favori du marché » : ROI {np.mean(np.where(M[ok].argmax(1)==y[ok], c[ok][np.arange(ok.sum()), M[ok].argmax(1)]-1, -1)):+.1%}")

print("\nPAR CHAMPIONNAT (bons pronostics 1N2)")
g = pd.DataFrame({"c": t.competition[ok], "k": P[ok].argmax(1) == y[ok], "m": M[ok].argmax(1) == y[ok]}).groupby("c").agg(matchs=("k", "size"), kateni=("k", "mean"), marche=("m", "mean"))
g["écart"] = g.kateni - g.marche
print((g.assign(kateni=g.kateni.map("{:.1%}".format), marche=g.marche.map("{:.1%}".format), écart=g["écart"].map("{:+.1%}".format))).to_string())
