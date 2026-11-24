"""
Kateni — basket : un avantage du terrain propre à chaque équipe améliore-t-il les pronostics ? (24/11/2026)
==========================================================================================================
Demande du propriétaire : certaines équipes gagnent surtout chez elles, d'autres surtout dehors. Le modèle
actuel donne le même avantage du terrain à toutes les équipes d'une ligue. Test : ajouter un avantage propre à
chaque équipe, rappelé vers 0 (force réglée sur janvier-juin 2025), mesuré sur 2025-26 sans fuite.
Adopté seulement si la mesure finale s'améliore.

Usage : python3 scripts/mesure_basket_terrain.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mesure_basket import REGLAGE, TEST, bilan, predire  # noqa: E402

df = pd.read_csv(Path(__file__).resolve().parent.parent / "basket_resultats.csv")
t = pd.to_datetime(df["DateUtc"], utc=True, format="ISO8601")


def base_dom(avant):
    b = df[t < avant]
    return (b["HPTS"] > b["APTS"]).groupby(b["ligue"]).mean().to_dict()


print("Réglage (janvier-juin 2025) :")
meilleur = None
for rd in (None, 5.0, 15.0, 40.0, 100.0):
    r = bilan(predire(df, *REGLAGE, ridge_dom=rd), base_dom(REGLAGE[0]))
    print(f"  {'même avantage pour toute la ligue' if rd is None else f'avantage propre, rappel {rd:5.1f}'} : "
          f"log loss {r['log loss vainqueur']:.4f}, bons vainqueurs {r['bons vainqueurs']:.1%}")
    if rd is not None and (meilleur is None or r["log loss vainqueur"] < meilleur[0]):
        meilleur = (r["log loss vainqueur"], rd)
rd = meilleur[1]
print(f"\nMesure finale 2025-26 (rappel retenu {rd}) :")
for nom, x in (("Même avantage pour toute la ligue (actuel)", None), ("Avantage propre à chaque équipe", rd)):
    p = predire(df, *TEST, ridge_dom=x)
    r = bilan(p, base_dom(TEST[0]))
    print(f"  {nom:44} {r['matchs']} matchs · log loss {r['log loss vainqueur']:.4f} · bons vainqueurs "
          f"{r['bons vainqueurs']:.1%} · erreur écart {r['erreur moyenne écart']:.2f} pts")
