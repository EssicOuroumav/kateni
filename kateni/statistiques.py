"""
Kateni — statistiques de match : tirs, tirs cadrés, fautes (et « plus grand nombre » pour les corners)
======================================================================================================
Même méthode que les corners (kateni/corners.py) : chaque club a une force « obtenus » et « concédés »
pour la statistique, pondérée dans le temps, plus un avantage du terrain par championnat (modele.ajuster
appliqué à la statistique), puis une loi binomiale négative dont la dispersion est mesurée sur 2024-25
(scripts/mesure_stats.py, mesure finale sur 2025-26 : docs/mesures/2026-10-25_stats.txt).
Données : football-data.co.uk (HS/AS tirs, HST/AST tirs cadrés, HF/AF fautes), 15 championnats.
« Plus grand nombre » : qui aura le plus de tirs / corners… (égalité possible), les deux équipes étant
supposées indépendantes ; la calibration de ce marché est vérifiée dans la même mesure.
"""

import numpy as np
import pandas as pd
from scipy.stats import nbinom

from kateni import modele

# nom : (colonne domicile, colonne extérieur, rappel, taille équipe, taille total, seuils total, seuils équipe)
# rappel et tailles mesurés sur 2024-25 (scripts/mesure_stats.py, docs/mesures/2026-10-25_stats.txt)
STATS = {
    "Tirs": ("HS", "AS", 10.0, 19.1, 74.8, (19.5, 21.5, 23.5, 25.5, 27.5, 29.5), (8.5, 10.5, 12.5, 14.5, 16.5)),
    "Tirs cadrés": ("HST", "AST", 10.0, 25.9, 51.3, (5.5, 6.5, 7.5, 8.5, 9.5, 10.5), (2.5, 3.5, 4.5, 5.5, 6.5)),
    "Fautes": ("HF", "AF", 30.0, 89.3, 100.5, (17.5, 19.5, 21.5, 23.5, 25.5, 27.5), (8.5, 9.5, 10.5, 11.5, 12.5)),
}
RAPPEL_MIN = 8.0         # matchs (pondérés) connus au minimum pour chaque club
K = np.arange(0, 81)


def donnees_stat(df: pd.DataFrame, col_d: str, col_e: str) -> pd.DataFrame:
    """Matchs dont la statistique est connue, présentés comme des « buts » pour modele.ajuster."""
    if col_d not in df.columns or col_e not in df.columns:
        return df.iloc[0:0][["Date", "HomeTeam", "AwayTeam", "competition"]].assign(FTHG=[], FTAG=[])
    v_d, v_e = pd.to_numeric(df[col_d], errors="coerce"), pd.to_numeric(df[col_e], errors="coerce")
    d = df[v_d.notna() & v_e.notna()][["Date", "HomeTeam", "AwayTeam", "competition"]].copy()
    d["FTHG"], d["FTAG"] = v_d[d.index].astype(float), v_e[d.index].astype(float)
    return d


def ajuster_stat(df: pd.DataFrame, nom: str, date_ref=None, ridge: float | None = None, demi_vie: float = 365.0):
    col_d, col_e, rappel = STATS[nom][:3]
    return modele.ajuster(donnees_stat(df, col_d, col_e), date_ref=date_ref, demi_vie=demi_vie,
                          ridge=rappel if ridge is None else ridge)


def _loi(moy: float, taille: float) -> np.ndarray:
    return nbinom.pmf(K, taille, taille / (taille + moy))


def _sup(moy: float, seuil: float, taille: float) -> float:
    return float(nbinom.sf(np.floor(seuil), taille, taille / (taille + moy)))


def plus_grand_nombre(m_d: float, m_e: float, taille: float) -> dict:
    """Chance que l'équipe à domicile ait plus (« 1 »), autant (« N ») ou moins (« 2 ») que l'autre."""
    a, b = _loi(m_d, taille), _loi(m_e, taille)
    grille = np.outer(a, b)
    i, j = np.indices(grille.shape)
    p = np.array([grille[i > j].sum(), grille[i == j].sum(), grille[i < j].sum()])
    p = p / p.sum()
    return {"1": float(p[0]), "N": float(p[1]), "2": float(p[2])}


def marches_stat(nom: str, m_d: float, m_e: float) -> dict:
    """Marchés d'une statistique : total du match, chaque équipe, et qui en aura le plus."""
    _, _, _, t_eq, t_tot, s_tot, s_eq = STATS[nom]
    out = {f"{nom} plus grand nombre": plus_grand_nombre(m_d, m_e, t_eq)}
    for s in s_tot:
        q = _sup(m_d + m_e, s, t_tot)
        out[f"{nom} total {s}"] = {"Plus": q, "Moins": 1 - q}
    for cote, moy in (("Dom.", m_d), ("Ext.", m_e)):
        for s in s_eq:
            q = _sup(moy, s, t_eq)
            out[f"{nom} {cote} {s}"] = {"Plus": q, "Moins": 1 - q}
    return out
