"""Chargement de tous les historiques, noms d'équipes unifiés."""

import pandas as pd

from kateni.config import COMPETITIONS, RACINE
from kateni.equipes import canoniser


def charger_competition(code: str) -> pd.DataFrame:
    comp = COMPETITIONS[code]
    chemin = RACINE / comp.fichier
    if not chemin.exists():
        return pd.DataFrame()
    df = pd.read_csv(chemin, low_memory=False)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", format="mixed")
    df = df.dropna(subset=["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"])
    df["FTHG"] = df["FTHG"].astype(int)
    df["FTAG"] = df["FTAG"].astype(int)
    df["competition"] = code
    if code == "INT" and "Neutre" in df.columns:
        # Sélections sur terrain neutre : compétition à part, pour que le modèle n'y apprenne aucun avantage
        # du terrain (l'avantage de « INT » reste celui des matchs joués à domicile)
        df.loc[df["Neutre"].astype(str).str.lower().eq("true"), "competition"] = "INTN"
    return canoniser(df)


def charger_tout() -> pd.DataFrame:
    morceaux = [charger_competition(c) for c in COMPETITIONS]
    df = pd.concat([m for m in morceaux if len(m)], ignore_index=True)
    return df.sort_values("Date").reset_index(drop=True)


def equipes_de(df: pd.DataFrame, code: str, depuis_jours: int = 400) -> list[str]:
    """Équipes ayant joué dans cette compétition récemment (pour les listes déroulantes)."""
    d = df[df["competition"] == code]
    if len(d):
        d = d[d["Date"] >= d["Date"].max() - pd.Timedelta(days=depuis_jours)]
    return sorted(set(d["HomeTeam"]) | set(d["AwayTeam"]))


def signature_donnees() -> tuple:
    """Change dès qu'un CSV change : sert de clé de cache au modèle."""
    sig = []
    for c in COMPETITIONS.values():
        p = RACINE / c.fichier
        sig.append((c.fichier, p.stat().st_mtime if p.exists() else 0))
    alias = RACINE / "equipes_alias.csv"
    sig.append(("alias", alias.stat().st_mtime if alias.exists() else 0))
    return tuple(sig)
