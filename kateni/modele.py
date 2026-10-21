"""
Kateni V2 — modèle avant-match
================================
Poisson « Dixon-Coles » global, pondéré dans le temps, ajusté en une fois sur
TOUTES les compétitions (noms d'équipes unifiés) :

    log λ_dom = μ + avantage_dom[compétition] + attaque[dom] − défense[ext]
    log λ_ext = μ                              + attaque[ext] − défense[dom]

- Un match récent compte plus qu'un ancien (demi-vie DEMI_VIE_JOURS).
- Un club garde UNE force, mise à jour par ses matchs de championnat ET
  d'Europe : c'est ce qui relie les championnats entre eux (corrige le
  constat n°2 de la V1, où la C1 n'utilisait que les matchs de C1).
- Quand le xG existe, la cible mélange buts réels et xG (moins de bruit).
- Une pénalité (ridge) ramène vers la moyenne les clubs avec peu de matchs.
- Correction Dixon-Coles (ρ) des scores 0-0, 1-0, 0-1, 1-1.

Paramètres par défaut raisonnables ; leur réglage par backtest = lot 1.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize

DEMI_VIE_JOURS = 365.0   # un match d'il y a 1 an pèse moitié moins qu'un match d'hier
POIDS_XG = 0.5           # cible = 0,5 × buts + 0,5 × xG quand le xG est connu
RIDGE = 3.0              # rappel vers la moyenne
RHO_DC = -0.06           # corrélation des petits scores (valeur usuelle de la littérature)
ANNEES_MAX = 6           # matchs plus anciens ignorés (poids < 2 %)
COUPES = {"CL", "EL"}


@dataclass
class Modele:
    mu: float
    avantage_dom: dict
    attaque: dict
    defense: dict
    n_matchs: dict
    date_donnees: pd.Timestamp
    rho: float = RHO_DC
    inconnues: set = field(default_factory=set)

    def connait(self, equipe: str) -> bool:
        return equipe in self.attaque

    def lambdas(self, dom: str, ext: str, competition: str) -> tuple[float, float]:
        h = self.avantage_dom.get(competition, np.mean(list(self.avantage_dom.values())))
        a_d, d_d = self.attaque.get(dom, 0.0), self.defense.get(dom, 0.0)
        a_e, d_e = self.attaque.get(ext, 0.0), self.defense.get(ext, 0.0)
        lam_d = float(np.exp(self.mu + h + a_d - d_e))
        lam_e = float(np.exp(self.mu + a_e - d_d))
        return lam_d, lam_e

    def classement(self, equipes: list[str] | None = None) -> pd.DataFrame:
        eq = equipes or list(self.attaque)
        df = pd.DataFrame({
            "Équipe": eq,
            "Attaque": [np.exp(self.attaque.get(e, 0.0)) for e in eq],
            "Défense": [np.exp(-self.defense.get(e, 0.0)) for e in eq],
            "Matchs (pondérés)": [round(self.n_matchs.get(e, 0.0), 1) for e in eq],
        })
        df["Force nette"] = df["Attaque"] / df["Défense"]
        return df.sort_values("Force nette", ascending=False).reset_index(drop=True)


def _cible(df: pd.DataFrame, cote: str) -> np.ndarray:
    buts = df[f"FT{cote}G"].to_numpy(float)
    col = f"{cote}xG"
    if col in df.columns:
        xg = pd.to_numeric(df[col], errors="coerce").to_numpy(float)
        return np.where(np.isnan(xg), buts, (1 - POIDS_XG) * buts + POIDS_XG * xg)
    return buts


def ajuster(df: pd.DataFrame, date_ref: pd.Timestamp | None = None,
            demi_vie: float = DEMI_VIE_JOURS, ridge: float = RIDGE) -> Modele:
    """Ajuste le modèle sur les matchs STRICTEMENT antérieurs à date_ref (anti-fuite)."""
    date_ref = date_ref or (df["Date"].max() + pd.Timedelta(days=1))
    d = df[(df["Date"] < date_ref) & (df["Date"] >= date_ref - pd.Timedelta(days=365 * ANNEES_MAX))]
    d = d.reset_index(drop=True)

    equipes = pd.Index(sorted(set(d["HomeTeam"]) | set(d["AwayTeam"])))
    comps = pd.Index(sorted(d["competition"].unique()))
    n, c = len(equipes), len(comps)
    i_d = equipes.get_indexer(d["HomeTeam"])
    i_e = equipes.get_indexer(d["AwayTeam"])
    i_c = comps.get_indexer(d["competition"])
    # Clubs qui n'apparaissent qu'en coupe d'Europe (championnat non couvert : Autriche,
    # Norvège, Ukraine...) : leur force de départ est un niveau commun estimé, pas la
    # moyenne générale (sinon LASK ou Viking seraient vus comme un club moyen de Ligue 1).
    domestiques = set(d.loc[~d["competition"].isin(COUPES), "HomeTeam"]) | set(
        d.loc[~d["competition"].isin(COUPES), "AwayTeam"])
    hors = np.array([e not in domestiques for e in equipes], dtype=float)
    age = (date_ref - d["Date"]).dt.days.to_numpy(float)
    w = np.power(0.5, age / demi_vie)
    y_d, y_e = _cible(d, "H"), _cible(d, "A")

    # vecteur : [mu, home(c), att(n), def(n), att_hors, def_hors]
    def nll(theta):
        mu, h = theta[0], theta[1:1 + c]
        a_r, d_r = theta[1 + c:1 + c + n], theta[1 + c + n:1 + c + 2 * n]
        att, dfn = a_r + hors * theta[-2], d_r + hors * theta[-1]
        eta_d = mu + h[i_c] + att[i_d] - dfn[i_e]
        eta_e = mu + att[i_e] - dfn[i_d]
        lam_d, lam_e = np.exp(eta_d), np.exp(eta_e)
        f = np.sum(w * (lam_d - y_d * eta_d)) + np.sum(w * (lam_e - y_e * eta_e))
        f += ridge * (np.sum(a_r ** 2) + np.sum(d_r ** 2))
        r_d, r_e = w * (lam_d - y_d), w * (lam_e - y_e)
        g = np.zeros_like(theta)
        g[0] = r_d.sum() + r_e.sum()
        g[1:1 + c] = np.bincount(i_c, r_d, minlength=c)
        g_att = np.bincount(i_d, r_d, minlength=n) + np.bincount(i_e, r_e, minlength=n)
        g_def = -np.bincount(i_e, r_d, minlength=n) - np.bincount(i_d, r_e, minlength=n)
        g[1 + c:1 + c + n] = g_att + 2 * ridge * a_r
        g[1 + c + n:1 + c + 2 * n] = g_def + 2 * ridge * d_r
        g[-2] = np.dot(g_att, hors)
        g[-1] = np.dot(g_def, hors)
        return f, g

    theta0 = np.zeros(1 + c + 2 * n + 2)
    theta0[0] = np.log(max(0.1, np.average((y_d + y_e) / 2, weights=w)))
    res = minimize(nll, theta0, jac=True, method="L-BFGS-B", options={"maxiter": 2000})
    t = res.x
    att = t[1 + c:1 + c + n] + hors * t[-2]
    dfn = t[1 + c + n:1 + c + 2 * n] + hors * t[-1]
    n_pond = np.bincount(i_d, w, minlength=n) + np.bincount(i_e, w, minlength=n)
    return Modele(
        mu=float(t[0]),
        avantage_dom={k: float(v) for k, v in zip(comps, t[1:1 + c])},
        attaque={k: float(v) for k, v in zip(equipes, att)},
        defense={k: float(v) for k, v in zip(equipes, dfn)},
        n_matchs={k: float(v) for k, v in zip(equipes, n_pond)},
        date_donnees=d["Date"].max(),
    )
