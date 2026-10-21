"""
Kateni — choix de la base Neon, SANS REPLI (règle starter `snippets/dburl.ts.txt`).

Deux branches Neon dans le même projet :
  - main  -> « prod » : les vrais paris, partagés entre le Mac et l'app en ligne
  - test  -> « test » : essais, tests automatiques, migrations avant la prod

Configuration (jamais dans Git) : `.streamlit/secrets.toml`
    [neon]
    cible = "prod"                 # base utilisée par l'app
    url = "postgresql://…"         # branche main
    url_test = "postgresql://…"    # branche test (sur le Mac seulement)

Ou variables d'environnement : KATENI_CIBLE, KATENI_DB_URL, KATENI_DB_URL_TEST.
Si la cible demandée n'a pas d'adresse : erreur. Jamais de bascule silencieuse
vers une autre base (ni vers la prod, ni vers le CSV local).
"""

import os
import tomllib
from urllib.parse import urlsplit

from kateni.config import RACINE

SECRETS = RACINE / ".streamlit" / "secrets.toml"
CIBLES = ("prod", "test")


class ConfigurationBase(Exception):
    pass


def lire_config(env: dict | None = None, secrets_path=SECRETS) -> dict:
    """Fusionne secrets.toml puis variables d'environnement (ces dernières l'emportent)."""
    env = os.environ if env is None else env
    conf = {}
    if secrets_path and secrets_path.exists():
        conf.update(tomllib.loads(secrets_path.read_text(encoding="utf-8")).get("neon", {}))
    for cle, var in (("cible", "KATENI_CIBLE"), ("url", "KATENI_DB_URL"), ("url_test", "KATENI_DB_URL_TEST")):
        if env.get(var):
            conf[cle] = env[var]
    return conf


def base_configuree(conf: dict) -> bool:
    """Vrai dès qu'une adresse Neon est fournie : l'app doit alors utiliser Neon (pas le CSV)."""
    return bool(conf.get("url") or conf.get("url_test"))


def url_base(conf: dict, cible: str | None = None) -> str:
    """Adresse de la base pour la cible demandée (ou celle de la configuration). Fonction pure."""
    cible = cible or conf.get("cible") or "prod"
    if cible not in CIBLES:
        raise ConfigurationBase(f"Cible inconnue « {cible} » (attendu : prod ou test).")
    url = conf.get("url") if cible == "prod" else conf.get("url_test")
    if not url:
        champ = "url" if cible == "prod" else "url_test"
        raise ConfigurationBase(
            f"Adresse de la base {cible} manquante ([neon] {champ} dans .streamlit/secrets.toml). "
            "Aucun repli vers une autre base.")
    if not url.startswith(("postgresql://", "postgres://")):
        raise ConfigurationBase(f"L'adresse de la base {cible} ne ressemble pas à une adresse Postgres.")
    return url


def hote(url: str) -> str:
    """Nom d'hôte seul, pour afficher la cible sans jamais montrer le mot de passe."""
    return urlsplit(url).hostname or "?"
