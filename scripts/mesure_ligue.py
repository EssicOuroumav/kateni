"""
Kateni — le modèle global prédit-il correctement un championnat ajouté ?
=========================================================================
Utilisé pour la A-League (07/11/2026) puis l'Argentine, le Brésil, le Mexique, la Finlande et la Russie
(08/11/2026). Le modèle est réajusté chaque semaine avec les seuls matchs passés (aucune fuite), puis comparé,
sur les matchs du championnat de la période de test (août 2025 à octobre 2026), à une prédiction naïve
(fréquences 1/N/2 et +2,5 buts du championnat avant la période de test), seul et mélangé avec elle.

Usage : python3 scripts/mesure_ligue.py AUS ARG BRA
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ameliorer import TEST, bin_ll, lambdas_v2, log_loss, proba_1n2  # noqa: E402
from kateni.donnees import charger_tout  # noqa: E402


def mesurer(df, code):
    aus = df[df["competition"] == code]
    avant = aus[aus["Date"] < TEST[0]]
    tst = aus[(aus["Date"] >= TEST[0]) & (aus["Date"] < TEST[1])].reset_index(drop=True)
    print(f"\n=== {code} : {len(avant)} matchs pour apprendre, {len(tst)} matchs de test ===")
    y = tst["FTR"].map({"H": 0, "D": 1, "A": 2}).to_numpy()
    plus = (tst["FTHG"] + tst["FTAG"] > 2.5).to_numpy(float)

    freq = avant["FTR"].value_counts(normalize=True).reindex(["H", "D", "A"]).to_numpy()
    f_plus = float((avant["FTHG"] + avant["FTAG"] > 2.5).mean())
    naif = np.tile(freq, (len(tst), 1))

    lam = lambdas_v2(df, tst, *TEST)
    res = [proba_1n2(a, b, -0.06) for a, b in lam]
    p = np.array([r[0] for r in res])
    q = np.array([r[1] for r in res])

    print(f"{'':28}{'Modèle Kateni':>15}{'Naïf':>10}")
    print(f"{'Log loss 1N2 (plus bas = mieux)':28}{log_loss(p, y):15.4f}{log_loss(naif, y):10.4f}")
    print(f"{'Bons pronostics 1N2':28}{np.mean(p.argmax(1) == y):15.1%}{np.mean(naif.argmax(1) == y):10.1%}")
    print(f"{'Log loss +2,5 buts':28}{bin_ll(q, plus):15.4f}{bin_ll(np.full(len(tst), f_plus), plus):10.4f}")
    print("\nMélange prudent (part du modèle, le reste = fréquences du championnat) :")
    for w in (1.0, 0.75, 0.5, 0.25, 0.0):
        m = w * p + (1 - w) * naif
        mq = w * q + (1 - w) * f_plus
        print(f"  modèle {w:.0%} : log loss 1N2 {log_loss(m, y):.4f} · +2,5 buts {bin_ll(mq, plus):.4f}")
    print("\nCalibration victoire domicile (annoncé -> arrivé) :")
    for a, b in ((0, .35), (.35, .5), (.5, .65), (.65, 1.01)):
        s = (p[:, 0] >= a) & (p[:, 0] < b)
        if s.sum():
            print(f"  {a:.0%}-{min(b, 1):.0%} : {s.sum():3d} matchs, annoncé {p[s, 0].mean():.0%} -> arrivé {(y[s] == 0).mean():.0%}")


def main():
    df = charger_tout()
    for code in sys.argv[1:] or ["AUS"]:
        mesurer(df, code)


if __name__ == "__main__":
    main()
