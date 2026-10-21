"""
Kateni — prépare les secrets de Streamlit Cloud
=================================================
Copie dans le presse-papiers le bloc à coller dans Streamlit Cloud
(réglages de l'app > Secrets). Rien n'est affiché à l'écran sauf le serveur.

Le bloc ne contient QUE la branche production : l'app en ligne n'a pas
besoin de la branche test (moindre privilège).

    python3 ~/Documents/Kateni/scripts/secrets_cloud.py
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kateni.db import ConfigurationBase, hote, lire_config, url_base  # noqa: E402


def bloc_cloud(conf: dict) -> str:
    url = url_base(conf, "prod")
    if "HOTE-pooler" in url:
        raise ConfigurationBase("L'adresse de production est encore l'exemple : "
                                "lance d'abord scripts/neon_connexion.py production.")
    return f'[neon]\ncible = "prod"\nurl = "{url}"\n'


def main():
    try:
        bloc = bloc_cloud(lire_config({}))  # le fichier du Mac seulement, pas l'environnement
    except ConfigurationBase as e:
        print(f"Rien n'a été copié. {e}")
        sys.exit(1)
    subprocess.run(["pbcopy"], input=bloc, text=True, check=True)
    serveur = hote(url_base(lire_config({}), "prod"))
    print(f"Copié dans le presse-papiers : bloc [neon] de la branche production (serveur {serveur}).")
    print("Colle-le dans Streamlit Cloud > ton app > Settings > Secrets, puis Save.")
    print("Ensuite, copie autre chose (n'importe quel mot) pour vider le presse-papiers.")


if __name__ == "__main__":
    main()
