"""
Kateni — enregistre la clé OddsPapi copiée dans le presse-papiers, sans jamais l'afficher.
  1. sur oddspapi.io : avatar en haut à droite > réglages du compte (account settings), copie la clé API
  2. double-clic sur Odds_API_cle.command
La clé va : (a) dans les secrets du dépôt GitHub (ODDS_API_KEY) pour le robot,
            (b) dans .streamlit/secrets.toml (local, hors Git) pour les essais sur le Mac.
"""
import re
import subprocess
import sys
import tomllib
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SECRETS = RACINE / ".streamlit" / "secrets.toml"


def main():
    cle = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", cle):
        print("Rien n'a été enregistré : le presse-papiers ne contient pas une clé API "
              "(une suite de lettres, chiffres et tirets). Recopie-la depuis oddspapi.io (réglages du compte), puis relance.")
        sys.exit(1)
    # (a) GitHub : la clé passe par l'entrée standard, jamais sur la ligne de commande ni à l'écran
    r = subprocess.run(["gh", "secret", "set", "ODDS_API_KEY", "--repo", "EssicOuroumav/kateni"],
                       input=cle, text=True, capture_output=True)
    if r.returncode != 0:
        print("GitHub a refusé l'enregistrement du secret (connexion gh ?). Rien n'a été modifié sur GitHub.")
        sys.exit(1)
    # (b) fichier local hors Git, droits 600
    texte = SECRETS.read_text(encoding="utf-8") if SECRETS.exists() else ""
    tomllib.loads(texte)  # le fichier doit rester valide
    texte = re.sub(r"\n?\[odds_api\]\nkey = \"[^\"]*\"\n?", "\n", texte).rstrip() + f'\n\n[odds_api]\nkey = "{cle}"\n'
    SECRETS.write_text(texte, encoding="utf-8")
    SECRETS.chmod(0o600)
    tomllib.loads(SECRETS.read_text(encoding="utf-8"))
    subprocess.run(["pbcopy"], input="", text=True)
    print(f"OK : clé enregistrée sur GitHub et sur ce Mac (longueur {len(cle)} caractères). Presse-papiers effacé.")


if __name__ == "__main__":
    main()
