"""
Cotes Betclic -> probabilités sans marge, espérance de gain, mise.
"""

import numpy as np
from scipy.optimize import minimize

from kateni.config import KELLY_FRACTION, MARGE_SUPPOSEE, MIN_EDGE_PCT, MISE_MAX_PCT, POIDS_MODELE
from kateni.marches import marches, matrice_scores


def sans_marge(cotes: list[float]) -> tuple[list[float], float]:
    """Probabilités implicites normalisées (méthode proportionnelle) et marge du bookmaker."""
    inv = [1 / c for c in cotes]
    s = sum(inv)
    return [x / s for x in inv], s - 1


def esperance(prob: float, cote: float) -> float:
    """Espérance de gain pour 1 FCFA misé : 0,05 = +5 %."""
    return prob * cote - 1


def mise(prob: float, cote: float, bankroll: float) -> dict:
    """Kelly au quart, plafond dur 2 %, rien sous le seuil d'espérance."""
    b = cote - 1
    ev = esperance(prob, cote)
    kelly = max(0.0, (b * prob - (1 - prob)) / b) if b > 0 else 0.0
    pct = min(KELLY_FRACTION * kelly, MISE_MAX_PCT) if ev >= MIN_EDGE_PCT else 0.0
    return {
        "esperance_pct": round(ev * 100, 1),
        "kelly_pct": round(kelly * 100, 1),
        "mise_pct": round(pct * 100, 2),
        "mise_fcfa": int(round(pct * bankroll / 50) * 50),  # arrondi à 50 FCFA
    }


def cote_minimale(p_modele: float) -> float | None:
    """Plus petite cote Betclic pour laquelle Kateni propose ce pari, quand cette seule cote est saisie.
    Même règle que l'analyse : p = w·modèle + (1−w)·(1/cote)/(1+marge), puis p·cote − 1 ≥ seuil.
    None si aucune cote raisonnable (≤ 100) ne suffit."""
    if p_modele <= 0:
        return None
    c = (1 + MIN_EDGE_PCT - (1 - POIDS_MODELE) / (1 + MARGE_SUPPOSEE)) / (POIDS_MODELE * p_modele)
    return max(1.01, c) if c <= 100 else None


def lambdas_depuis_cotes(c1: float, cn: float, c2: float,
                         c_plus25: float | None = None, c_moins25: float | None = None,
                         rho: float = 0.0) -> tuple[float, float]:
    """Buts attendus implicites dans les cotes 1N2 (+ plus/moins 2,5 si fournies).
    Utile quand le modèle connaît mal une équipe (C1, petits championnats)."""
    p1n2, _ = sans_marge([c1, cn, c2])
    p_ou = sans_marge([c_plus25, c_moins25])[0][0] if c_plus25 and c_moins25 else None

    def erreur(x):
        ld, le = np.exp(x)
        p = marches(matrice_scores(ld, le, rho))
        e = (p["1N2"]["1"] - p1n2[0]) ** 2 + (p["1N2"]["2"] - p1n2[2]) ** 2 + (p["1N2"]["N"] - p1n2[1]) ** 2
        if p_ou is not None:
            e += (p["Total buts 2.5"]["Plus"] - p_ou) ** 2
        return e

    res = minimize(erreur, np.log([1.4, 1.1]), method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-8})
    ld, le = np.exp(res.x)
    return float(ld), float(le)
