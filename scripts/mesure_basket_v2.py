"""
Kateni — basket : nouvelles ligues, enchaînements, écarts-types par ligue, mi-temps (24/11/2026)
================================================================================================
Sans fuite : modèle réajusté chaque semaine avec les seuls matchs passés. Période de test : juillet 2025 à
novembre 2026 (pour couvrir la WNBA, jouée de mai à octobre). Chaque variante n'est adoptée que si elle
améliore la mesure.

  1. Par ligue (NBA, EuroLeague, EuroCup, NBL, WNBA, NCAA) : le modèle bat-il le « naïf » (taux de victoire à
     domicile de la ligue) ? Une ligue qui ne le bat pas n'est pas proposée.
  2. Enchaînements : l'équipe qui a joué la veille marque-t-elle moins / encaisse-t-elle plus ?
  3. Écarts-types propres à chaque ligue (au lieu d'un seul pour toutes).
  4. 1re mi-temps et 1er quart-temps : fiabilité (calibration du vainqueur de la période).

Usage : python3 scripts/mesure_basket_v2.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kateni.basket import MI_TEMPS, PERIODES, _points_periode, ajuster, joue_la_veille  # noqa: E402

DEBUT, FIN = pd.Timestamp("2025-07-01", tz="UTC"), pd.Timestamp("2026-11-21", tz="UTC")
df = pd.read_csv(Path(__file__).resolve().parent.parent / "basket_resultats.csv")
df = df[df["HPTS"].notna()].reset_index(drop=True)
T = pd.to_datetime(df["DateUtc"], utc=True, format="ISO8601")
VH, VA = joue_la_veille(df)


def predire(fatigue=False, par_ligue=False, quarts=None, **reglages):
    hp, ap = _points_periode(df, quarts)
    sel = df.index[(T >= DEBUT) & (T < FIN) & hp.notna()]
    if quarts is not None and len(quarts) == 1:
        sel = [i for i in sel if df.at[i, "ligue"] not in MI_TEMPS]
    out, semaine = [], DEBUT
    while semaine < FIN:
        bloc = [i for i in sel if semaine <= T[i] < semaine + pd.Timedelta(days=7)]
        if bloc:
            m = ajuster(df, date_ref=semaine, elargir=False, quarts=quarts, fatigue=fatigue, **reglages)
            for i in bloc:
                r = df.loc[i]
                if not (m.connait(r["HomeTeam"]) and m.connait(r["AwayTeam"])):
                    continue
                ne = r.get("Neutre")
                a, b = m.points(r["HomeTeam"], r["AwayTeam"], r["ligue"], bool(ne) if pd.notna(ne) else False,
                                bool(VH[i]), bool(VA[i]))
                sd_e, _ = m.ecarts_types(r["ligue"], par_ligue)
                out.append({"ligue": r["ligue"], "date": T[i], "e": a - b, "sd_e": sd_e, "vrai": hp[i] - ap[i]})
        semaine += pd.Timedelta(days=7)
    p = pd.DataFrame(out)
    # Période : égalité possible (on la compte comme une demi-victoire) ; match : prolongations
    p["q"] = (1 - norm.cdf(0, p["e"], p["sd_e"])).clip(1e-4, 1 - 1e-4)
    p["y"] = np.where(p["vrai"] > 0, 1.0, np.where(p["vrai"] < 0, 0.0, 0.5))
    return p


def ll(p):
    return float(-np.mean(p["y"] * np.log(p["q"]) + (1 - p["y"]) * np.log(1 - p["q"])))


def naif(p):
    base = df[T < DEBUT]
    dom = (base["HPTS"] > base["APTS"]).groupby(base["ligue"]).mean()
    q = p["ligue"].map(dom).fillna(0.55).clip(1e-4, 1 - 1e-4)
    return float(-np.mean(p["y"] * np.log(q) + (1 - p["y"]) * np.log(1 - q)))


def ligne(nom, p):
    bons = float(((p["q"] > 0.5) == (p["y"] > 0.5))[p["y"] != 0.5].mean())
    return f"  {nom:34} {len(p):6d} matchs · log loss {ll(p):.4f} · bons vainqueurs {bons:.1%}"


def main():
    print(f"Test : {DEBUT:%d/%m/%Y} au {FIN:%d/%m/%Y}\n\n1. Par ligue (modèle actuel) :")
    base = predire()
    for lg, g in base.groupby("ligue"):
        print(ligne(lg, g) + f" · naïf {naif(g):.4f}" + ("  -> bat le naïf" if ll(g) < naif(g) else "  -> NE BAT PAS le naïf"))

    print("\n2-3. Variantes (toutes ligues) :")
    variantes = {"actuel": base, "enchaînements": predire(fatigue=True), "écarts-types par ligue": predire(par_ligue=True),
                 "les deux": predire(fatigue=True, par_ligue=True)}
    for nom, p in variantes.items():
        print(ligne(nom, p))
    m = ajuster(df, fatigue=True)
    print(f"  Effet mesuré d'un match la veille : {m.extra['fatigue'][0]:+.2f} points marqués, "
          f"{m.extra['fatigue'][1]:+.2f} points encaissés")

    print("\n4. Périodes (calibration du vainqueur de la période : annoncé -> arrivé) :")
    for nom, q in PERIODES.items():
        p = predire(quarts=q)
        print(ligne(nom, p))
        for lo, hi in ((0, .35), (.35, .5), (.5, .65), (.65, 1.01)):
            s = p[(p["q"] >= lo) & (p["q"] < hi)]
            if len(s) >= 50:
                print(f"      {lo:.0%}-{min(hi, 1):.0%} : {len(s):5d} matchs, annoncé {s['q'].mean():.0%} -> arrivé {s['y'].mean():.0%}")


if __name__ == "__main__":
    main()
