"""
Kateni — sentinelle des données, lancée par le robot après chaque mise à jour (24/11/2026).
Écrit alertes_donnees.json (affiché au propriétaire dans l'app) et l'affiche dans le journal du robot.

    python3 scripts/sentinelle.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kateni.config import RACINE  # noqa: E402
from kateni.donnees import charger_tout  # noqa: E402
from kateni.sentinelle import FICHIER, ecrire, verifier  # noqa: E402

b = RACINE / "basket_resultats.csv"
r = verifier(charger_tout(), pd.read_csv(b) if b.exists() else None)
ecrire(r, RACINE / FICHIER)
if r["alertes"]:
    print("Sentinelle : données EN RETARD pour " + ", ".join(
        f"{a['championnat']} (dernier résultat le {a['dernier']}, il y a {a['jours']} jours)" for a in r["alertes"]))
else:
    print(f"Sentinelle : rien d'anormal ({r['en_saison']} championnats en saison"
          + (", trêve générale" if r["treve"] else "") + ").")
