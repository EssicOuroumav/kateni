"""
Kateni — modèle d'origine (V1), conservé à l'identique
========================================================
Même calcul que `kateni_engine.py` (calculer_forces + calculer_lambdas) :
forces d'attaque et de défense par championnat, sur tout l'historique de
ce championnat (xG quand il existe), rappel vers la moyenne (6 matchs
virtuels), puis loi de Poisson simple.

Utilisé dans les championnats où il a mieux prédit que le modèle V2
(backtest du 21/10/2026, voir kateni/config.py : MODELE_PAR_COMPETITION).
"""

from dataclasses import dataclass, field

import pandas as pd

REGUL_MATCHES_PRIOR = 6


@dataclass
class ModeleV1:
    avg_home_goals: float
    avg_away_goals: float
    attack: dict = field(default_factory=dict)
    defense: dict = field(default_factory=dict)
    rho: float = 0.0  # pas de correction des petits scores dans la V1

    def connait(self, equipe: str) -> bool:
        return equipe in self.attack

    def lambdas(self, dom: str, ext: str, competition: str | None = None) -> tuple[float, float]:
        lam_d = self.avg_home_goals * self.attack.get(dom, 1.0) * self.defense.get(ext, 1.0)
        lam_e = self.avg_away_goals * self.attack.get(ext, 1.0) * self.defense.get(dom, 1.0)
        return max(0.1, lam_d), max(0.1, lam_e)


def ajuster_v1(df_competition: pd.DataFrame) -> ModeleV1:
    """Copie fidèle de kateni_engine.calculer_forces, sur les matchs d'UN championnat."""
    df = df_competition.copy()
    if "HxG" in df.columns:
        df["_buts_home"] = pd.to_numeric(df["HxG"], errors="coerce").fillna(df["FTHG"])
        df["_buts_away"] = pd.to_numeric(df["AxG"], errors="coerce").fillna(df["FTAG"])
    else:
        df["_buts_home"] = df["FTHG"]
        df["_buts_away"] = df["FTAG"]

    avg_home = df["_buts_home"].mean()
    avg_away = df["_buts_away"].mean()
    moyenne_ligue = (avg_home + avg_away) / 2
    modele = ModeleV1(avg_home_goals=avg_home, avg_away_goals=avg_away)

    for team in pd.unique(df[["HomeTeam", "AwayTeam"]].values.ravel()):
        dom = df[df["HomeTeam"] == team]
        ext = df[df["AwayTeam"] == team]
        n = len(dom) + len(ext)
        marques = pd.concat([dom["_buts_home"], ext["_buts_away"]])
        encaisses = pd.concat([dom["_buts_away"], ext["_buts_home"]])
        att = marques.mean() / moyenne_ligue if n else 1.0
        dfn = encaisses.mean() / moyenne_ligue if n else 1.0
        poids = n / (n + REGUL_MATCHES_PRIOR)
        modele.attack[team] = poids * att + (1 - poids) * 1.0
        modele.defense[team] = poids * dfn + (1 - poids) * 1.0
    return modele
