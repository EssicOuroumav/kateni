"""
Kateni — code d'accès du propriétaire (voir kateni/acces.py)
=============================================================
Crée ou remplace TON code pour Kateni en ligne et l'affiche UNE fois dans cette fenêtre (jamais
enregistré ailleurs : la base ne garde qu'une empreinte). Les codes des camarades se créent dans la
page « Accès » de Kateni.

    python3 scripts/acces.py proprietaire --cible prod
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kateni.acces import PROPRIETAIRE, Acces  # noqa: E402
from kateni.db import ConfigurationBase, hote, lire_config, url_base  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Code d'accès du propriétaire de Kateni")
    ap.add_argument("commande", choices=["proprietaire"])
    ap.add_argument("--cible", choices=["test", "prod"], default="prod")
    args = ap.parse_args()
    try:
        url = url_base(lire_config(), args.cible)
    except ConfigurationBase as e:
        print(f"Configuration : {e}")
        sys.exit(2)
    print(f"Base ciblée : {args.cible} ({hote(url)})")
    code = Acces(url).creer(PROPRIETAIRE, PROPRIETAIRE)
    print("\nTon code d'accès à Kateni en ligne (l'ancien, s'il existait, ne marche plus) :\n")
    print(f"    {code}\n")
    print("Note-le dans un endroit sûr (gestionnaire de mots de passe, carnet). Il ne sera plus affiché.")


if __name__ == "__main__":
    main()
