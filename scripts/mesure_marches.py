"""
Kateni — sur quels types de paris le modèle est-il le plus fiable ? (11/11/2026)
=================================================================================
Pour chaque type de pari (résultat, double chance, nombre de buts, les deux marquent, une équipe marque…),
sur tous les matchs de championnat d'août 2025 à octobre 2026, avec le modèle réajusté chaque semaine sans
fuite : quand Kateni annonce 60-70 %, 70-80 %, 80 % ou plus, combien de fois le pari passe-t-il vraiment ?
Modèle seul (sans les cotes du marché, que l'app ajoute quand elles existent).

Usage : python3 scripts/mesure_marches.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ameliorer import CHAMPIONNATS, TEST, lambdas_v2  # noqa: E402
from kateni.donnees import charger_tout  # noqa: E402
from kateni.marches import calibrer, marches, matrice_scores, regler  # noqa: E402

FAMILLES = {"1N2": "Résultat (1N2)", "Double chance": "Double chance", "Total buts": "Nombre de buts",
            "Les deux équipes marquent": "Les deux équipes marquent", "Dom. marque": "Une équipe marque",
            "Ext. marque": "Une équipe marque"}
BANDES = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]


def famille(marche: str) -> str:
    for k, v in FAMILLES.items():
        if marche.startswith(k):
            return v
    return marche


def main():
    df = charger_tout()
    t = df[df["competition"].isin(CHAMPIONNATS) & (df["Date"] >= TEST[0]) & (df["Date"] < TEST[1])].reset_index(drop=True)
    print(f"{len(t)} matchs de championnat testés ({TEST[0]:%d/%m/%Y} - {TEST[1]:%d/%m/%Y})\n")
    lam = lambdas_v2(df, t, *TEST)
    lignes = []
    for (ld, le), (_, r) in zip(lam, t.iterrows()):
        p = calibrer(marches(matrice_scores(ld, le, -0.06)))
        for mk, d in p.items():
            if mk in ("Total buts 0.5", "Total buts 5.5"):
                continue
            for sel, q in d.items():
                if q >= 0.5:
                    lignes.append({"famille": famille(mk), "p": q,
                                   "ok": bool(regler(mk, sel, int(r["FTHG"]), int(r["FTAG"])))})
    d = pd.DataFrame(lignes)
    print(f"{'Type de pari':28}" + "".join(f"{f'{a:.0%}-{min(b, 1):.0%}':>18}" for a, b in BANDES))
    for fam, g in d.groupby("famille"):
        cases = []
        for a, b in BANDES:
            s = g[(g["p"] >= a) & (g["p"] < b)]
            cases.append(f"{s['ok'].mean():.0%} ({s['p'].mean():.0%}, {len(s)})" if len(s) >= 30 else "–")
        print(f"{fam:28}" + "".join(f"{c:>18}" for c in cases))
    print("\nLecture : « 74% (72%, 812) » = sur 812 paris annoncés dans cette tranche (72 % en moyenne), 74 % sont "
          "passés. Plus l'arrivé colle à l'annoncé, plus Kateni est fiable sur ce type de pari.")


if __name__ == "__main__":
    main()
