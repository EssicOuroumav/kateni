"""
Kateni — enregistre une adresse Neon copiée dans le presse-papiers
====================================================================
Évite d'éditer .streamlit/secrets.toml à la main. L'adresse n'est JAMAIS
affichée : seul le nom du serveur l'est, pour vérifier.

    1. Dans Neon : Connect -> Show password -> Copy snippet
    2. python3 ~/Documents/Kateni/scripts/neon_connexion.py test
       (ou « production » pour la branche production)
"""

import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

SECRETS = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
CLES = {"production": "url", "test": "url_test"}


def verifier_adresse(url: str) -> str | None:
    """Message d'erreur, ou None si l'adresse est utilisable."""
    if not url.startswith(("postgresql://", "postgres://")):
        return "Le presse-papiers ne contient pas une adresse Neon (elle doit commencer par postgresql://)."
    if "*" in url:
        return "L'adresse contient des étoiles (*****) : clique d'abord sur « Show password » dans Neon, puis recopie."
    p = urlsplit(url)
    if not p.password or not p.hostname or not p.hostname.endswith(".neon.tech"):
        return "Adresse incomplète (mot de passe ou serveur Neon manquant). Recopie-la avec « Copy snippet »."
    return None


def enregistrer(branche: str, url: str, chemin: Path = SECRETS) -> str:
    """Écrit l'adresse dans secrets.toml (droits 600) et renvoie le nom du serveur."""
    conf = tomllib.loads(chemin.read_text(encoding="utf-8")).get("neon", {}) if chemin.exists() else {}
    conf[CLES[branche]] = url
    conf.setdefault("cible", "prod")
    autre = conf.get(CLES["test" if branche == "production" else "production"], "")
    if autre and urlsplit(autre).hostname == urlsplit(url).hostname:
        raise ValueError("Cette adresse est la même que celle de l'autre branche : "
                         "change de branche dans Neon (sélecteur en haut à gauche) puis recopie.")
    lignes = ["# Adresses Neon de Kateni — fichier local, jamais dans Git.", "[neon]",
              f'cible = "{conf["cible"]}"']
    for cle in ("url", "url_test"):
        if conf.get(cle):
            lignes.append(f'{cle} = "{conf[cle]}"')
    chemin.parent.mkdir(exist_ok=True)
    chemin.touch(mode=0o600, exist_ok=True)
    chemin.chmod(0o600)
    chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return urlsplit(url).hostname


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in CLES:
        print("Usage : python3 scripts/neon_connexion.py production   (ou : test)")
        sys.exit(2)
    branche = sys.argv[1]
    url = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout.strip()
    erreur = verifier_adresse(url)
    if erreur:
        print(f"Rien n'a été enregistré. {erreur}")
        sys.exit(1)
    try:
        serveur = enregistrer(branche, url)
    except ValueError as e:
        print(f"Rien n'a été enregistré. {e}")
        sys.exit(1)
    print(f"OK : adresse de la branche « {branche} » enregistrée (serveur {serveur}).")
    conf = tomllib.loads(SECRETS.read_text(encoding="utf-8"))["neon"]
    manque = [b for b, c in CLES.items() if not conf.get(c)]
    print("Il manque encore la branche : " + manque[0] if manque else "Les deux branches sont enregistrées.")


if __name__ == "__main__":
    main()
