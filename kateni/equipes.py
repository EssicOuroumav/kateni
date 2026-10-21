"""
Noms d'équipes : une seule orthographe par club, quelle que soit la source.
La table `equipes_alias.csv` (alias -> canonique) est éditable à la main.
Le nom canonique est celui de football-data.co.uk (championnats), parce que
c'est la source qui a les cotes et le plus de matchs.
"""

from functools import lru_cache

import pandas as pd

from kateni.config import ALIAS_PATH


@lru_cache(maxsize=1)
def table_alias() -> dict[str, str]:
    if not ALIAS_PATH.exists():
        return {}
    df = pd.read_csv(ALIAS_PATH, dtype=str).dropna()
    return {a.strip(): c.strip() for a, c in zip(df["alias"], df["canonique"])}


def canon(nom: str) -> str:
    nom = str(nom).strip()
    return table_alias().get(nom, nom)


def canoniser(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    alias = table_alias()
    for col in ("HomeTeam", "AwayTeam"):
        df[col] = df[col].astype(str).str.strip().replace(alias)
    return df
