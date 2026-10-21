"""
Kateni — module live (nouveau)
================================
« Paris mène 2-0 contre Barcelone à la 34e » -> probabilités de la fin du match.

Modèle de Poisson dépendant de l'état du match (Dixon & Robinson, 1998) :
- taux de buts croissant au fil du match : w(t) = 1 + KAPPA·t/90
  (KAPPA mesuré : 53,9 % des buts attendus après la pause, avant l'effet du score) ;
- temps additionnel ajouté au taux de fin de période ;
- l'équipe menée d'un but attaque plus (+15 %), celle qui mène d'un but un peu moins (−5 %) ;
- carton rouge : l'équipe à 10 marque moins, l'adversaire un peu plus.

Coefficients MESURÉS sur nos matchs (scripts/calibrer_live.py, 21/10/2026) : réglés sur 4 796 matchs
de 2024-25 (score à la mi-temps -> score final), vérifiés sur 5 822 matchs de 2025-26
(log loss du résultat final prédit à la mi-temps : 0,8158 avec les coefficients des études -> 0,8153).
Les cartons rouges gardent les valeurs des études (Maia et al., IJF 2026) : nos données ne donnent pas
la minute des expulsions.
"""

from dataclasses import dataclass

import numpy as np

from kateni.marches import marches, matrice_finale, matrice_scores, scores_probables

KAPPA = 0.2027   # profil des buts : 53,9 % des buts attendus après la pause (mesuré)
MENE_DE_1 = 1.154    # équipe menée d'un but : +15 % (mesuré ; études : +10 %)
MENE_DE_2 = 1.047    # menée de deux buts ou plus : +5 % (mesuré ; études : +20 %)
MENE = 0.947         # équipe qui mène d'un but : -5 % (mesuré)
MENE_DE_2_PLUS = 1.004  # équipe qui mène de deux buts ou plus : inchangé (mesuré)
ROUGE_SUBI = 0.70    # par carton rouge reçu : -30 %
ROUGE_ADVERSE = 1.20  # par carton rouge de l'adversaire : +20 %
ADDITIONNEL_MT1 = 2.0
ADDITIONNEL_MT2 = 5.0


def _integrale_w(a: float, b: float) -> float:
    """∫ w(t) dt de a à b (minutes)."""
    return (b - a) + KAPPA * (b ** 2 - a ** 2) / 180


TOTAL_W = _integrale_w(0, 90) + (1 + KAPPA * 45 / 90) * ADDITIONNEL_MT1 + (1 + KAPPA) * ADDITIONNEL_MT2


def fraction_restante(minute: float, additionnel_mt2: float = ADDITIONNEL_MT2) -> float:
    """Part des buts attendus du match qui reste à jouer après `minute`."""
    minute = max(0.0, min(float(minute), 90.0 + additionnel_mt2))
    reste = 0.0
    if minute < 45:
        reste += _integrale_w(minute, 45) + (1 + KAPPA * 0.5) * ADDITIONNEL_MT1
        reste += _integrale_w(45, 90) + (1 + KAPPA) * additionnel_mt2
    elif minute < 90:
        reste += _integrale_w(minute, 90) + (1 + KAPPA) * additionnel_mt2
    else:
        reste += (1 + KAPPA) * max(0.0, 90 + additionnel_mt2 - minute)
    return reste / TOTAL_W


def multiplicateur_score(ecart_pour: int) -> float:
    if ecart_pour <= -2:
        return MENE_DE_2
    if ecart_pour == -1:
        return MENE_DE_1
    if ecart_pour >= 2:
        return MENE_DE_2_PLUS
    if ecart_pour == 1:
        return MENE
    return 1.0


@dataclass
class EtatLive:
    minute: float
    buts_d: int
    buts_e: int
    rouges_d: int = 0
    rouges_e: int = 0
    additionnel_mt2: float = ADDITIONNEL_MT2


def buts_restants_attendus(lam_d: float, lam_e: float, e: EtatLive) -> tuple[float, float]:
    f = fraction_restante(e.minute, e.additionnel_mt2)
    ecart = e.buts_d - e.buts_e
    m_d = multiplicateur_score(ecart) * ROUGE_SUBI ** e.rouges_d * ROUGE_ADVERSE ** e.rouges_e
    m_e = multiplicateur_score(-ecart) * ROUGE_SUBI ** e.rouges_e * ROUGE_ADVERSE ** e.rouges_d
    return lam_d * f * m_d, lam_e * f * m_e


def predire_live(lam_d: float, lam_e: float, e: EtatLive) -> dict:
    """lam_d, lam_e = buts attendus sur le match ENTIER (avant le coup d'envoi)."""
    r_d, r_e = buts_restants_attendus(lam_d, lam_e, e)
    m_fin = matrice_finale(matrice_scores(r_d, r_e), e.buts_d, e.buts_e)
    p = marches(m_fin)
    p_aucun = float(np.exp(-(r_d + r_e)))
    part_d = r_d / (r_d + r_e) if r_d + r_e > 0 else 0.5
    p["Prochain but"] = {"Dom.": (1 - p_aucun) * part_d, "Aucun": p_aucun, "Ext.": (1 - p_aucun) * (1 - part_d)}
    p["Dom. marque encore"] = {"Oui": float(1 - np.exp(-r_d)), "Non": float(np.exp(-r_d))}
    p["Ext. marque encore"] = {"Oui": float(1 - np.exp(-r_e)), "Non": float(np.exp(-r_e))}
    # Seules les lignes de total encore ouvertes ont un sens en live
    total_actuel = e.buts_d + e.buts_e
    for k in [k for k in p if k.startswith("Total buts ")]:
        if float(k.split()[-1]) < total_actuel:
            del p[k]
    return {
        "restants": (r_d, r_e),
        "marches": p,
        "scores": scores_probables(m_fin),
    }
