"""
Kateni — mesure du modèle de basket (kateni/basket.py)
========================================================
Sans fuite : le modèle est réajusté chaque semaine avec les seuls matchs passés.
Réglage (demi-vie, rappel) sur janvier-juin 2025, mesure finale sur la saison 2025-26 (octobre 2025 à
juin 2026), par ligue. On compare au « naïf » (taux de victoire à domicile de la ligue) et on vérifie que
les chances annoncées arrivent (calibration) et que les totaux tombent bien de part et d'autre de la ligne.

Usage : python3 scripts/mesure_basket.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kateni.basket import ajuster  # noqa: E402

REGLAGE = (pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2025-07-01", tz="UTC"))
TEST = (pd.Timestamp("2025-10-01", tz="UTC"), pd.Timestamp("2026-07-01", tz="UTC"))


def predire(df, debut, fin, **reglages):
    t = pd.to_datetime(df["DateUtc"], utc=True)
    sel = df[(t >= debut) & (t < fin)].copy()
    sel["t"] = pd.to_datetime(sel["DateUtc"], utc=True)
    out = []
    semaine = debut
    while semaine < fin:
        bloc = sel[(sel["t"] >= semaine) & (sel["t"] < semaine + pd.Timedelta(days=7))]
        if len(bloc):
            m = ajuster(df, date_ref=semaine, elargir=False, **reglages)
            for _, r in bloc.iterrows():
                if not (m.connait(r["HomeTeam"]) and m.connait(r["AwayTeam"])):
                    continue
                a, b = m.points(r["HomeTeam"], r["AwayTeam"], r["ligue"])
                out.append({"ligue": r["ligue"], "e": a - b, "t": a + b, "sd_e": m.sd_ecart, "sd_t": m.sd_total,
                            "vrai_e": r["HPTS"] - r["APTS"], "vrai_t": r["HPTS"] + r["APTS"]})
        semaine += pd.Timedelta(days=7)
    return pd.DataFrame(out)


def bilan(p: pd.DataFrame, base_dom: dict) -> dict:
    q = 1 - norm.cdf(0, p["e"], p["sd_e"])
    y = (p["vrai_e"] > 0).astype(float)
    q = q.clip(1e-4, 1 - 1e-4)
    b = p["ligue"].map(base_dom).clip(1e-4, 1 - 1e-4)
    ll = lambda x: float(-np.mean(y * np.log(x) + (1 - y) * np.log(1 - x)))  # noqa: E731
    return {"matchs": len(p), "log loss vainqueur": ll(q), "naïf": ll(b), "bons vainqueurs": float(((q > .5) == y).mean()),
            "total au-dessus de la ligne": float((p["vrai_t"] > p["t"]).mean()),
            "erreur moyenne écart": float((p["vrai_e"] - p["e"]).abs().mean()),
            "erreur moyenne total": float((p["vrai_t"] - p["t"]).abs().mean())}


def main():
    df = pd.read_csv(Path(__file__).resolve().parent.parent / "basket_resultats.csv")
    t = pd.to_datetime(df["DateUtc"], utc=True)
    base = df[t < REGLAGE[0]]
    base_dom = (base["HPTS"] > base["APTS"]).groupby(base["ligue"]).mean().to_dict()
    print("Réglage sur janvier-juin 2025 :")
    meilleur = None
    for dv in (60, 120, 240):
        for rp in (2.0, 6.0, 15.0):
            r = bilan(predire(df, *REGLAGE, demi_vie=dv, rappel=rp), base_dom)
            print(f"  demi-vie {dv:3d} j, rappel {rp:4.1f} : log loss {r['log loss vainqueur']:.4f} "
                  f"(naïf {r['naïf']:.4f}), {r['matchs']} matchs")
            if meilleur is None or r["log loss vainqueur"] < meilleur[0]:
                meilleur = (r["log loss vainqueur"], dv, rp)
    _, dv, rp = meilleur
    print(f"\nRetenu : demi-vie {dv} jours, rappel {rp}\n\nMesure finale sur 2025-26 :")
    p = predire(df, *TEST, demi_vie=dv, rappel=rp)
    base = df[t < TEST[0]]
    base_dom = (base["HPTS"] > base["APTS"]).groupby(base["ligue"]).mean().to_dict()
    for lg, g in [("Toutes", p), *p.groupby("ligue")]:
        r = bilan(g, base_dom)
        print(f"  {lg:11} {r['matchs']:5d} matchs · log loss {r['log loss vainqueur']:.4f} (naïf {r['naïf']:.4f}) · "
              f"bons vainqueurs {r['bons vainqueurs']:.1%} · total au-dessus de la ligne {r['total au-dessus de la ligne']:.1%}"
              f" · erreur écart {r['erreur moyenne écart']:.1f} pts, total {r['erreur moyenne total']:.1f} pts")
    q = 1 - norm.cdf(0, p["e"], p["sd_e"])
    y = p["vrai_e"] > 0
    print("\nCalibration du vainqueur (annoncé -> arrivé) :")
    for a, b in ((0, .2), (.2, .35), (.35, .5), (.5, .65), (.65, .8), (.8, 1.01)):
        s = (q >= a) & (q < b)
        if s.sum():
            print(f"  {a:.0%}-{min(b, 1):.0%} : {s.sum():4d} matchs, annoncé {q[s].mean():.0%} -> arrivé {y[s].mean():.0%}")
    z = (p["vrai_t"] - p["t"]) / p["sd_t"]
    print(f"\nTotaux : écart-type des erreurs / écart-type annoncé = {z.std():.2f} (1,00 = bien réglé)")
    z = (p["vrai_e"] - p["e"]) / p["sd_e"]
    print(f"Écarts : écart-type des erreurs / écart-type annoncé = {z.std():.2f} (1,00 = bien réglé)")


if __name__ == "__main__":
    main()
