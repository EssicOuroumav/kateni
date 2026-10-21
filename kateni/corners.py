"""
Kateni — corners
=================
Même principe que les buts : chaque club a une force « corners obtenus » et « corners concédés », pondérée
dans le temps, plus un avantage du terrain par championnat (modele.ajuster appliqué aux corners).
Les corners varient plus qu'une loi de Poisson : on utilise une loi binomiale négative, dont la dispersion
a été mesurée sur 2024-25 (scripts/mesure_corners.py).
Données : football-data.co.uk (colonnes HC, AC), 14 championnats ; pas de corners pour les coupes d'Europe
ni pour les championnats au format « new » : les clubs sont alors jugés sur leurs matchs de championnat.
"""

import numpy as np
import pandas as pd
from scipy.stats import nbinom

from kateni import modele

# Mesurés sur 2024-25 (docs/mesures/2026-10-21_corners.txt) : demi-vie 365 j, rappel 30, dispersion
# (paramètre « taille » de la binomiale négative ; plus grand = plus proche de Poisson)
TAILLE_EQUIPE = 11.2
TAILLE_TOTAL = 75.0
RAPPEL_MIN = 8.0         # matchs (pondérés) de corners connus au minimum pour chaque club
SEUILS_TOTAL = (7.5, 8.5, 9.5, 10.5, 11.5, 12.5)
SEUILS_EQUIPE = (2.5, 3.5, 4.5, 5.5, 6.5)


def donnees_corners(df: pd.DataFrame) -> pd.DataFrame:
    """Matchs dont les corners sont connus, présentés comme des « buts » pour modele.ajuster."""
    d = df[pd.to_numeric(df.get("HC"), errors="coerce").notna() & pd.to_numeric(df.get("AC"), errors="coerce").notna()]
    d = d[["Date", "HomeTeam", "AwayTeam", "competition", "HC", "AC"]].copy()
    d["FTHG"], d["FTAG"] = d["HC"].astype(float), d["AC"].astype(float)
    return d.drop(columns=["HC", "AC"])


def ajuster_corners(df: pd.DataFrame, date_ref=None, demi_vie: float = 365.0, ridge: float = 30.0):
    return modele.ajuster(donnees_corners(df), date_ref=date_ref, demi_vie=demi_vie, ridge=ridge)


def _sup(moy: float, seuil: float, taille: float) -> float:
    """P(X > seuil) pour une binomiale négative de moyenne moy."""
    p = taille / (taille + moy)
    return float(nbinom.sf(np.floor(seuil), taille, p))


def marches_corners(c_dom: float, c_ext: float, deja_d: int = 0, deja_e: int = 0, reste: float = 1.0) -> dict:
    """Probabilités des marchés corners à partir des corners attendus de chaque équipe sur le match.
    En live : deja_d/deja_e = corners déjà obtenus, reste = part du match encore à jouer ; seuls les
    marchés pas encore joués d'avance sont rendus. La dispersion est ramenée à la part restante."""
    out = {}
    if reste <= 0:
        return out
    for s in SEUILS_TOTAL:
        if deja_d + deja_e < s:
            q = _sup((c_dom + c_ext) * reste, s - deja_d - deja_e, TAILLE_TOTAL * reste)
            out[f"Corners total {s}"] = {"Plus": q, "Moins": 1 - q}
    for cote, moy, deja in (("Dom.", c_dom, deja_d), ("Ext.", c_ext, deja_e)):
        for s in SEUILS_EQUIPE:
            if deja < s:
                q = _sup(moy * reste, s - deja, TAILLE_EQUIPE * reste)
                out[f"Corners {cote} {s}"] = {"Plus": q, "Moins": 1 - q}
    return out
