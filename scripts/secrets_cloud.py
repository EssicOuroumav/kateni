"""
Kateni — prépare les secrets de Streamlit Cloud
=================================================
Copie dans le presse-papiers le bloc à coller dans Streamlit Cloud
(réglages de l'app > Secrets). Rien n'est affiché à l'écran sauf le serveur.

Le bloc ne contient QUE la branche production (l'app en ligne n'a pas
besoin de la branche test : moindre privilège) et la clé OddsPapi.

    python3 ~/Documents/Kateni/scripts/secrets_cloud.py
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kateni.db import ConfigurationBase, hote, lire_config, url_base  # noqa: E402


def bloc_cloud(conf: dict, cle_odds: str | None = None) -> str:
    url = url_base(conf, "prod")
    if "HOTE-pooler" in url:
        raise ConfigurationBase("L'adresse de production est encore l'exemple : "
                                "lance d'abord scripts/neon_connexion.py production.")
    bloc = f'[neon]\ncible = "prod"\nurl = "{url}"\n'
    if cle_odds:  # l'app relève elle-même les cotes Pinnacle des matchs imminents
        bloc += f'\n[odds_api]\nkey = "{cle_odds}"\n'
    return bloc


def main():
    try:
        from kateni.pinnacle import cle
        bloc = bloc_cloud(lire_config({}), cle())  # le fichier du Mac seulement
    except ConfigurationBase as e:
        print(f"Rien n'a été copié. {e}")
        sys.exit(1)
    subprocess.run(["pbcopy"], input=bloc, text=True, check=True)
    # Messages volontairement sans crochets ni mots du bloc : rien à copier ici par erreur.
    print("C'EST PRÊT. Ne sélectionne et ne copie RIEN dans ce Terminal.")
    print("Va sur Streamlit, clique dans la zone Secrets vide, puis appuie sur Cmd+V.")
    try:
        input("Quand c'est collé, reviens ici et appuie sur Entrée pour effacer la mémoire... ")
    except EOFError:
        return
    subprocess.run(["pbcopy"], input="", text=True, check=True)
    print("Mémoire effacée.")


if __name__ == "__main__":
    main()
