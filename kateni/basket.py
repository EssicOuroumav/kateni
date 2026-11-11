"""
Kateni — modèle de basket (NBA, EuroLeague, EuroCup ; ajouté le 07/11/2026)
============================================================================
Chaque équipe a une force d'attaque et une force de défense (points marqués / encaissés par rapport à la
moyenne de sa ligue), plus un avantage du terrain par ligue. Ajustement par moindres carrés pondérés dans
le temps (les matchs récents comptent plus), avec un rappel vers 0 pour les équipes peu connues :
    points domicile  = moyenne + terrain + attaque(dom) − défense(ext)
    points extérieur = moyenne            + attaque(ext) − défense(dom)
L'écart et le total suivent une loi normale dont les écarts-types sont mesurés sur les erreurs du modèle
(scripts/mesure_basket.py). Mi-temps et quart-temps : même méthode sur les points de la période.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import norm

PERIODES = {"Match": None, "1re mi-temps": ("1", "2"), "1er quart-temps": ("1",)}
# Mesurés (scripts/mesure_basket.py, docs/mesures/2026-11-07_basket.txt) : réglage janvier-juin 2025, mesure
# 2025-26 sur 1 849 matchs (log loss vainqueur 0,613 contre 0,681 naïf, 66,7 % de bons vainqueurs, calibré).
DEMI_VIE, RAPPEL = 60.0, 2.0
# Les erreurs réelles sont un peu plus dispersées que celles des matchs d'apprentissage (rapport mesuré sur
# 2025-26) : on élargit les écarts-types d'autant pour ne pas être trop sûr de soi.
ELARGIR_ECART, ELARGIR_TOTAL = 1.08, 1.06


@dataclass
class ModeleBasket:
    moyenne: dict          # ligue -> points moyens par équipe
    terrain: dict          # ligue -> avantage du terrain (points)
    attaque: dict
    defense: dict
    ligue_equipe: dict
    n_matchs: dict
    sd_ecart: float = 12.5
    sd_total: float = 18.0
    extra: dict = field(default_factory=dict)
    n_reels: dict = field(default_factory=dict)   # vrais matchs joués (sans pondération par l'âge)

    def connait(self, equipe: str) -> bool:
        """Au moins 5 vrais matchs joués. (Avant : 5 matchs « pondérés », ce qui écartait les équipes de début de
        saison, surtout en EuroCup : 6 matchs récents ne pesaient pas 5.)"""
        if self.n_reels:
            return self.n_reels.get(equipe, 0) >= 5
        return self.n_matchs.get(equipe, 0.0) >= 5

    def points(self, dom: str, ext: str, ligue: str | None = None, neutre: bool = False) -> tuple[float, float]:
        lg = ligue or self.ligue_equipe.get(dom) or self.ligue_equipe.get(ext)
        mu, h = self.moyenne.get(lg, 100.0), 0.0 if neutre else self.terrain.get(lg, 2.5)
        pd_ = mu + h + self.attaque.get(dom, 0.0) - self.defense.get(ext, 0.0)
        pe = mu + self.attaque.get(ext, 0.0) - self.defense.get(dom, 0.0)
        return pd_, pe


def _points_periode(df: pd.DataFrame, quarts) -> tuple[pd.Series, pd.Series]:
    if quarts is None:
        return df["HPTS"].astype(float), df["APTS"].astype(float)
    return (df[[f"H{q}" for q in quarts]].astype(float).sum(axis=1),
            df[[f"A{q}" for q in quarts]].astype(float).sum(axis=1))


def ajuster(df: pd.DataFrame, date_ref=None, demi_vie: float = DEMI_VIE, rappel: float = RAPPEL,
            quarts=None, elargir: bool = True) -> ModeleBasket:
    """df : basket_resultats.csv (colonnes ligue, DateUtc, HomeTeam, AwayTeam, H1..H4, A1..A4, HPTS, APTS)."""
    d = df.copy()
    d["t"] = pd.to_datetime(d["DateUtc"], utc=True, format="ISO8601")
    ref = pd.Timestamp(date_ref, tz="UTC") if date_ref is not None and pd.Timestamp(date_ref).tzinfo is None \
        else (pd.Timestamp(date_ref) if date_ref is not None else d["t"].max() + pd.Timedelta(days=1))
    d = d[d["t"] < ref]
    hp, ap = _points_periode(d, quarts)
    d = d.assign(hp=hp, ap=ap).dropna(subset=["hp", "ap"])
    w = 0.5 ** ((ref - d["t"]).dt.total_seconds() / 86400 / demi_vie)

    equipes = sorted(set(d["HomeTeam"]) | set(d["AwayTeam"]))
    ligues = sorted(d["ligue"].unique())
    ie, il = {e: i for i, e in enumerate(equipes)}, {l: i for i, l in enumerate(ligues)}
    n, nl = len(equipes), len(ligues)
    # Une ligne par score d'équipe : moyenne(ligue) + terrain(ligue, si domicile) + attaque(équipe) − défense(adv)
    m = len(d)
    X = np.zeros((2 * m, 2 * nl + 2 * n))
    y = np.concatenate([d["hp"].to_numpy(), d["ap"].to_numpy()])
    ww = np.concatenate([w.to_numpy(), w.to_numpy()])
    for k, (lg, h, a) in enumerate(zip(d["ligue"], d["HomeTeam"], d["AwayTeam"])):
        X[k, il[lg]] = 1
        X[k, nl + il[lg]] = 1
        X[k, 2 * nl + ie[h]] = 1
        X[k, 2 * nl + n + ie[a]] = -1
        X[m + k, il[lg]] = 1
        X[m + k, 2 * nl + ie[a]] = 1
        X[m + k, 2 * nl + n + ie[h]] = -1
    pen = np.r_[np.zeros(2 * nl), np.full(2 * n, rappel)]
    A = X.T @ (X * ww[:, None]) + np.diag(pen)
    beta = np.linalg.solve(A, X.T @ (ww * y))
    res = y - X @ beta
    ecart = res[:m] - res[m:]
    total = res[:m] + res[m:]
    nm, nr = {}, {}
    for h, a, wi in zip(d["HomeTeam"], d["AwayTeam"], w):
        nm[h] = nm.get(h, 0.0) + wi
        nm[a] = nm.get(a, 0.0) + wi
        nr[h] = nr.get(h, 0) + 1
        nr[a] = nr.get(a, 0) + 1
    ligue_eq = {}
    for lg, h, a in zip(d["ligue"], d["HomeTeam"], d["AwayTeam"]):
        ligue_eq[h], ligue_eq[a] = lg, lg
    sd = lambda r: float(np.sqrt(np.average(r ** 2, weights=w)))  # noqa: E731
    return ModeleBasket(
        moyenne={l: float(beta[il[l]]) for l in ligues}, terrain={l: float(beta[nl + il[l]]) for l in ligues},
        attaque={e: float(beta[2 * nl + ie[e]]) for e in equipes},
        defense={e: float(beta[2 * nl + n + ie[e]]) for e in equipes},
        ligue_equipe=ligue_eq, n_matchs=nm, n_reels=nr, sd_ecart=sd(ecart) * (ELARGIR_ECART if elargir else 1.0),
        sd_total=sd(total) * (ELARGIR_TOTAL if elargir else 1.0))


def _lignes(centre: float, pas: float, n: int = 3) -> list[float]:
    base = np.floor(centre) + 0.5
    return [float(base + pas * k) for k in range(-n, n + 1)]


def marches(pd_: float, pe: float, sd_ecart: float, sd_total: float, periode: str = "Match") -> dict:
    """Marchés d'une période à partir des points attendus (dom, ext) et des écarts-types mesurés."""
    e, t = pd_ - pe, pd_ + pe
    out = {}
    nul = norm.cdf(0.5, e, sd_ecart) - norm.cdf(-0.5, e, sd_ecart)   # égalité (prolongation en match entier)
    gagne = 1 - norm.cdf(0.5, e, sd_ecart)
    if periode == "Match":
        # Vainqueur, prolongations comprises : l'égalité se partage presque à parts égales
        out["Vainqueur"] = {"1": gagne + nul * 0.5, "2": 1 - gagne - nul * 0.5}
        out["Temps réglementaire"] = {"1": gagne, "N": nul, "2": 1 - gagne - nul}
    else:
        out[f"{periode} : résultat"] = {"1": gagne, "N": nul, "2": 1 - gagne - nul}
    pas_h, pas_t = (2.0, 5.0) if periode == "Match" else ((1.0, 3.0) if periode == "1re mi-temps" else (1.0, 2.0))
    for ligne in _lignes(-e, pas_h):  # handicap de l'équipe à domicile (−5,5 = doit gagner de 6 ou plus)
        q = 1 - norm.cdf(-ligne, e, sd_ecart)
        out[f"{periode} : handicap {ligne:+.1f}"] = {"1": q, "2": 1 - q}
    for ligne in _lignes(t, pas_t):
        q = 1 - norm.cdf(ligne, t, sd_total)
        out[f"{periode} : total {ligne:.1f}"] = {"Plus": q, "Moins": 1 - q}
    sd_eq = sd_total / np.sqrt(2)
    for cote, moy in (("Dom.", pd_), ("Ext.", pe)):
        for ligne in _lignes(moy, pas_t, 2):
            q = 1 - norm.cdf(ligne, moy, sd_eq)
            out[f"{periode} : points {cote} {ligne:.1f}"] = {"Plus": q, "Moins": 1 - q}
    if periode == "Match":
        bandes = [(1, 5), (6, 10), (11, 15), (16, 20), (21, 99)]
        for cote, signe in (("1", 1), ("2", -1)):
            for a, b in bandes:
                q = norm.cdf(b + 0.5, signe * e, sd_ecart) - norm.cdf(a - 0.5, signe * e, sd_ecart)
                if a == 1:  # égalité à la fin du temps réglementaire : prolongation, gagnée de peu (même partage)
                    q += nul * 0.5
                out.setdefault("Écart final", {})[f"{cote} de {a} à {b}" if b < 99 else f"{cote} de 21 ou plus"] = q
        out["Total pair ou impair"] = {"Pair": 0.5, "Impair": 0.5}
    return out


def fr(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def libelle(marche: str, sel: str, dom: str, ext: str) -> str:
    nom = {"1": dom, "2": ext}
    if marche == "Vainqueur":
        return f"Vainqueur (prolongations comprises) : {nom[sel]}"
    if marche == "Temps réglementaire" or marche.endswith(": résultat"):
        quand = "Temps réglementaire" if marche == "Temps réglementaire" else marche.split(" :")[0]
        return f"{quand} : " + ("égalité" if sel == "N" else f"{nom[sel]} gagne")
    if marche == "Écart final":
        cote, reste = sel.split(" ", 1)
        return f"Écart final : {nom[cote]} gagne {reste} points"
    if marche == "Total pair ou impair":
        return f"Total de points {sel.lower()}"
    periode, quoi = marche.split(" : ", 1)
    prefixe = "" if periode == "Match" else f"{periode} · "
    if quoi.startswith("handicap"):
        ligne = float(quoi.split()[1])
        eq, l = (dom, ligne) if sel == "1" else (ext, -ligne)
        return f"{prefixe}Handicap {eq} {fr(l) if l < 0 else '+' + fr(l)}"
    if quoi.startswith("total"):
        return f"{prefixe}Total de points : {'plus' if sel == 'Plus' else 'moins'} de {fr(float(quoi.split()[1]))}"
    if quoi.startswith("points"):
        _, cote, ligne = quoi.split()
        eq = dom if cote == "Dom." else ext
        return f"{prefixe}Points {eq} : {'plus' if sel == 'Plus' else 'moins'} de {fr(float(ligne))}"
    return f"{marche} : {sel}"
