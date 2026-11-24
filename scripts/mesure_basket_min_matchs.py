"""
Kateni — basket : écarter de l'ajustement les équipes presque absentes (24/11/2026)
=====================================================================================
Constat : en NCAA, l'avantage du terrain sortait à 12 points (réalité : 3 à 6). Cause : les petites universités
hors 1re division jouent 1 ou 2 matchs, toujours à l'extérieur chez des équipes bien plus fortes. Test : ne garder
pour l'ajustement que les matchs entre équipes ayant au moins N matchs connus. Mesure sans fuite
(juillet 2025 - novembre 2026), adoptée seulement si elle s'améliore.

Usage : python3 scripts/mesure_basket_min_matchs.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mesure_basket_v2 import ligne, ll, predire  # noqa: E402

for n in (0, 4, 8):
    p = predire(min_matchs=n)
    print(ligne(f"au moins {n} matchs" if n else "actuel (toutes les équipes)", p))
    for lg, g in p.groupby("ligue"):
        print(f"      {lg:11} {len(g):5d} matchs · log loss {ll(g):.4f}")
