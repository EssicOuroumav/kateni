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
# Écart (qui gagne) : réglé le 24/11/2026 par période, NCAA filtrée (scripts/mesure_basket_elargir.py, réglage
# juil. 2025-juin 2026, vérifié juil.-nov. 2026, 6 ligues ; docs/mesures/2026-11-24_basket_elargir_v2.txt) :
# match 1,06 ; 1re mi-temps 1,31 ; 1er quart-temps 1,60.
ELARGIR_ECART, ELARGIR_TOTAL = 1.06, 1.06
ELARGIR_PERIODE = {None: 1.06, ("1", "2"): 1.31, ("1",): 1.60}
# Mesurés le 24/11/2026 (scripts/mesure_basket_v2.py), non adoptés : match la veille (« back-to-back ») et
# écarts-types propres à chaque ligue (sauf la NCAA, qui a les siens).
FATIGUE = False
SD_PAR_LIGUE = False
# NCAA : un match ne sert à l'ajustement que si les deux équipes ont au moins 8 matchs connus (les petites
# universités hors 1re division faussaient l'avantage du terrain : 12 points au lieu de ~5). Mesuré le 24/11/2026
# (scripts/mesure_basket_min_matchs.py) : log loss NCAA 0,5706 -> 0,5395. Les autres ligues ne sont pas filtrées
# (en EuroCup, cela écartait les équipes de début de saison).
MIN_MATCHS = 8
LIGUES_FILTREES = {"NCAA"}  # filtrées, et avec leurs propres écarts-types


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

    def ecarts_types(self, ligue: str | None, par_ligue: bool = SD_PAR_LIGUE) -> tuple[float, float]:
        """(écart-type de l'écart, écart-type du total) : celui de la ligue s'il est connu et adopté, sinon global."""
        if (par_ligue or ligue in LIGUES_FILTREES) and ligue in self.extra.get("sd_ligue", {}):
            return self.extra["sd_ligue"][ligue]
        return self.sd_ecart, self.sd_total

    def points(self, dom: str, ext: str, ligue: str | None = None, neutre: bool = False,
               veille_dom: bool = False, veille_ext: bool = False) -> tuple[float, float]:
        lg = ligue or self.ligue_equipe.get(dom) or self.ligue_equipe.get(ext)
        mu, h = self.moyenne.get(lg, 100.0), 0.0 if neutre else self.terrain.get(lg, 2.5)
        if not neutre:
            h += self.extra.get("dom_equipe", {}).get(dom, 0.0)
        pd_ = mu + h + self.attaque.get(dom, 0.0) - self.defense.get(ext, 0.0)
        pe = mu + self.attaque.get(ext, 0.0) - self.defense.get(dom, 0.0)
        if "fatigue" in self.extra:   # équipe qui a joué la veille : points marqués / encaissés en plus (mesuré)
            marque, encaisse = self.extra["fatigue"]
            pd_ += marque * veille_dom + encaisse * veille_ext
            pe += marque * veille_ext + encaisse * veille_dom
        return pd_, pe


MI_TEMPS = {"NCAA"}  # ligues jouées en deux mi-temps (rangées en H1 et H3) : pas de quart-temps


def _points_periode(df: pd.DataFrame, quarts) -> tuple[pd.Series, pd.Series]:
    if quarts is None:
        return df["HPTS"].astype(float), df["APTS"].astype(float)
    return (df[[f"H{q}" for q in quarts]].astype(float).sum(axis=1, min_count=1),
            df[[f"A{q}" for q in quarts]].astype(float).sum(axis=1, min_count=1))


def joue_la_veille(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Pour chaque match de df : l'équipe à domicile / à l'extérieur a-t-elle joué la veille (moins de 36 h avant) ?
    Calculé sur tous les matchs de df (joués et à venir), toutes ligues."""
    t = pd.to_datetime(df["DateUtc"], utc=True, format="ISO8601")
    lignes = pd.concat([pd.DataFrame({"i": df.index, "eq": df["HomeTeam"], "t": t, "cote": "H"}),
                        pd.DataFrame({"i": df.index, "eq": df["AwayTeam"], "t": t, "cote": "A"})])
    lignes = lignes.sort_values(["eq", "t"], kind="mergesort")
    ecart = lignes.groupby("eq")["t"].diff().dt.total_seconds() / 3600
    lignes["veille"] = (ecart > 0) & (ecart < 36)
    v = lignes.set_index(["i", "cote"])["veille"]
    v = v[~v.index.duplicated()]
    return (v.reindex(list(zip(df.index, ["H"] * len(df)))).fillna(False).to_numpy(bool),
            v.reindex(list(zip(df.index, ["A"] * len(df)))).fillna(False).to_numpy(bool))


def ajuster(df: pd.DataFrame, date_ref=None, demi_vie: float = DEMI_VIE, rappel: float = RAPPEL,
            quarts=None, elargir: bool = True, ridge_dom: float | None = None,
            fatigue: bool | None = None, min_matchs: int | None = None) -> ModeleBasket:
    """df : basket_resultats.csv (colonnes ligue, DateUtc, HomeTeam, AwayTeam, H1..H4, A1..A4, HPTS, APTS).
    Matrice creuse : la NCAA compte des centaines d'équipes."""
    from scipy import sparse
    d = df.copy()
    d["t"] = pd.to_datetime(d["DateUtc"], utc=True, format="ISO8601")
    ref = pd.Timestamp(date_ref, tz="UTC") if date_ref is not None and pd.Timestamp(date_ref).tzinfo is None \
        else (pd.Timestamp(date_ref) if date_ref is not None else d["t"].max() + pd.Timedelta(days=1))
    fatigue = FATIGUE if fatigue is None else fatigue
    if fatigue:
        vh, va = joue_la_veille(d)
        d = d.assign(veille_dom=vh, veille_ext=va)
    d = d[d["t"] < ref]
    min_matchs = MIN_MATCHS if min_matchs is None else min_matchs
    if min_matchs:  # équipes presque absentes (petites universités hors 1re division) : faussent l'avantage du terrain
        n_eq = pd.concat([d["HomeTeam"], d["AwayTeam"]]).value_counts()
        assez = d["HomeTeam"].map(n_eq).ge(min_matchs) & d["AwayTeam"].map(n_eq).ge(min_matchs)
        d = d[assez | ~d["ligue"].isin(LIGUES_FILTREES)]
    if quarts is not None and len(quarts) == 1:  # quart-temps : pas pour les ligues jouées en mi-temps
        d = d[~d["ligue"].isin(MI_TEMPS)]
    hp, ap = _points_periode(d, quarts)
    d = d.assign(hp=hp, ap=ap).dropna(subset=["hp", "ap"])
    w = 0.5 ** ((ref - d["t"]).dt.total_seconds() / 86400 / demi_vie)

    equipes = sorted(set(d["HomeTeam"]) | set(d["AwayTeam"]))
    ligues = sorted(d["ligue"].unique())
    ie, il = {e: i for i, e in enumerate(equipes)}, {l: i for i, l in enumerate(ligues)}
    n, nl = len(equipes), len(ligues)
    # Une ligne par score d'équipe : moyenne(ligue) + terrain(ligue, si domicile) + attaque(équipe) − défense(adv)
    m = len(d)
    nd = n if ridge_dom else 0   # avantage du terrain propre à chaque équipe (testé, non adopté)
    lg_i = d["ligue"].map(il).to_numpy()
    h_i = d["HomeTeam"].map(ie).to_numpy()
    a_i = d["AwayTeam"].map(ie).to_numpy()
    k = np.arange(m)
    # Terrain neutre (tournois NCAA, Coupe NBA…) : pas d'avantage du terrain pour ce match
    chez = 1.0 - (d["Neutre"].fillna(False).astype(bool).to_numpy(float) if "Neutre" in d.columns else np.zeros(m))
    lignes_ = [k, k, k, k, m + k, m + k, m + k]
    cols_ = [lg_i, nl + lg_i, 2 * nl + h_i, 2 * nl + n + a_i, lg_i, 2 * nl + a_i, 2 * nl + n + h_i]
    vals_ = [1, chez, 1, -1, 1, 1, -1]
    if nd:
        lignes_.append(k)
        cols_.append(2 * nl + 2 * n + h_i)
        vals_.append(1)
    nf = 2 if fatigue else 0   # [points marqués par l'équipe fatiguée, points encaissés par elle]
    if fatigue:
        f0 = 2 * nl + 2 * n + nd
        vd, ve = d["veille_dom"].to_numpy(float), d["veille_ext"].to_numpy(float)
        lignes_ += [k, k, m + k, m + k]
        cols_ += [np.full(m, f0), np.full(m, f0 + 1), np.full(m, f0), np.full(m, f0 + 1)]
        vals_ += [vd, ve, ve, vd]   # score dom : dom fatigué (marque) / ext fatigué (encaisse) ; idem pour ext
    X = sparse.csr_matrix((np.concatenate([np.broadcast_to(np.asarray(v, float), m) for v in vals_]),
                           (np.concatenate(lignes_), np.concatenate(cols_))), shape=(2 * m, 2 * nl + 2 * n + nd + nf))
    y = np.concatenate([d["hp"].to_numpy(), d["ap"].to_numpy()])
    ww = np.concatenate([w.to_numpy(), w.to_numpy()])
    pen = np.r_[np.zeros(2 * nl), np.full(2 * n, rappel), np.full(nd, ridge_dom or 0.0), np.full(nf, 1e-3)]
    Xw = X.multiply(ww[:, None]).tocsr()
    A = (X.T @ Xw).toarray() + np.diag(pen)
    beta = np.linalg.solve(A, Xw.T @ y)
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
    wv = w.to_numpy()
    sd = lambda r, s=slice(None): float(np.sqrt(np.average(r[s] ** 2, weights=wv[s])))  # noqa: E731
    extra = {"dom_equipe": {e: float(beta[2 * nl + 2 * n + ie[e]]) for e in equipes}} if nd else {}
    if fatigue:
        extra["fatigue"] = (float(beta[2 * nl + 2 * n + nd]), float(beta[2 * nl + 2 * n + nd + 1]))
    # Écarts-types propres à chaque ligue (la WNBA ou la NCAA ne se dispersent pas comme la NBA)
    lg_arr = d["ligue"].to_numpy()
    autres = ~np.isin(lg_arr, list(LIGUES_FILTREES))
    if not autres.any():
        autres = slice(None)
    extra["sd_ligue"] = {l: (sd(ecart, lg_arr == l) * (ELARGIR_PERIODE.get(quarts, ELARGIR_ECART) if elargir else 1.0),
                             sd(total, lg_arr == l) * (ELARGIR_TOTAL if elargir else 1.0))
                         for l in ligues if (lg_arr == l).sum() >= 100}
    return ModeleBasket(
        moyenne={l: float(beta[il[l]]) for l in ligues}, terrain={l: float(beta[nl + il[l]]) for l in ligues},
        attaque={e: float(beta[2 * nl + ie[e]]) for e in equipes},
        defense={e: float(beta[2 * nl + n + ie[e]]) for e in equipes},
        ligue_equipe=ligue_eq, n_matchs=nm, n_reels=nr,
        # Écarts-types « globaux » sans la NCAA (elle a les siens, dans sd_ligue) : sinon elle déforme les autres ligues
        sd_ecart=sd(ecart, autres) * (ELARGIR_PERIODE.get(quarts, ELARGIR_ECART) if elargir else 1.0),
        sd_total=sd(total, autres) * (ELARGIR_TOTAL if elargir else 1.0), extra=extra)


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


# ------------------------------------------------------------------ paris de basket d'un coupon (Mon coupon, 25/11/2026)
# Une sélection de basket : {"sport": "basket", "competition": ligue, "dom", "ext", "date_match", "marche",
# "selection", "ligne"} ; « ligne » = le chiffre du pari (handicap −5,5 ; total 221,5 ; points 112,5).
CHOIX_BASKET = [("Basket Vainqueur", "1"), ("Basket Vainqueur", "2"),
                ("Basket Handicap", "1"), ("Basket Handicap", "2"),
                ("Basket Total", "Plus"), ("Basket Total", "Moins"),
                ("Basket Points Dom.", "Plus"), ("Basket Points Dom.", "Moins"),
                ("Basket Points Ext.", "Plus"), ("Basket Points Ext.", "Moins")]
AVEC_LIGNE = {"Basket Handicap", "Basket Total", "Basket Points Dom.", "Basket Points Ext."}


def libelle_selection(marche: str, sel: str, dom: str, ext: str, ligne: float | None = None) -> str:
    eq = {"1": dom, "2": ext}
    l = "…" if ligne is None else fr(abs(ligne)) if marche != "Basket Handicap" else (
        f"+{fr(ligne)}" if ligne > 0 else f"−{fr(-ligne)}")
    if marche == "Basket Vainqueur":
        return f"Vainqueur (prolongations comprises) : {eq[sel]}"
    if marche == "Basket Handicap":
        return f"Handicap {eq[sel]} {l}"
    sens = "plus" if sel == "Plus" else "moins"
    if marche == "Basket Total":
        return f"Total de points : {sens} de {l}"
    qui = dom if marche == "Basket Points Dom." else ext
    return f"Points de {qui} : {sens} de {l}"


def chance_selection(m: "ModeleBasket", s: dict, neutre: bool = False) -> float | None:
    """Chance que la sélection passe (match entier, prolongations comprises), avec les écarts-types mesurés."""
    if not (m.connait(s["dom"]) and m.connait(s["ext"])):
        return None
    a, b = m.points(s["dom"], s["ext"], s.get("competition"), neutre)
    sd_e, sd_t = m.ecarts_types(s.get("competition"))
    marche, sel, ligne = s["marche"], s["selection"], s.get("ligne")
    if marche == "Basket Vainqueur":
        v = marches(a, b, sd_e, sd_t)["Vainqueur"]
        return float(v[sel])
    if ligne is None:
        return None
    if marche == "Basket Handicap":   # dom avec handicap h gagne si écart + h > 0 ; ext si écart < h
        e = a - b
        return float(1 - norm.cdf(-ligne, e, sd_e)) if sel == "1" else float(norm.cdf(ligne, e, sd_e))
    moy, sd = ((a + b, sd_t) if marche == "Basket Total" else
               ((a if marche == "Basket Points Dom." else b), sd_t / np.sqrt(2)))
    plus = float(1 - norm.cdf(ligne, moy, sd))
    return plus if sel == "Plus" else 1 - plus


def regler_selection(s: dict, pts_d: int, pts_e: int) -> bool | None:
    """Gagné / perdu avec le score final (prolongations comprises). None si la ligne tombe pile (remboursé)."""
    marche, sel, ligne = s["marche"], s["selection"], s.get("ligne")
    if marche == "Basket Vainqueur":
        return (pts_d > pts_e) == (sel == "1")
    if ligne is None:
        return None
    if marche == "Basket Handicap":
        v = (pts_d - pts_e + ligne) if sel == "1" else (pts_e - pts_d + ligne)
    else:
        n = pts_d + pts_e if marche == "Basket Total" else (pts_d if marche == "Basket Points Dom." else pts_e)
        v = (n - ligne) if sel == "Plus" else (ligne - n)
    return None if v == 0 else v > 0


def pari_lu(bloc: str, dom: str, ext: str) -> tuple[str, str, float | None] | None:
    """(marché, sélection, ligne) reconnu dans le texte d'une sélection de basket du coupon Betclic."""
    import re
    import unicodedata
    t = unicodedata.normalize("NFKD", bloc).encode("ascii", "ignore").decode().lower()

    def a(nom: str) -> bool:
        from kateni.coupon import _equipe_dans
        return _equipe_dans(bloc, nom)
    plus = re.search(r"(plus|moins|over|under|\+|-)\s*(?:de\s*)?(\d{2,3})[.,](5)", t)
    hand = re.search(r"([+-]\s?\d{1,2}[.,]5)", t)
    if plus and ("point" in t or "total" in t or int(plus.group(2)) >= 60):
        sens = "Plus" if plus.group(1) in ("plus", "over", "+") else "Moins"
        ligne = float(f"{plus.group(2)}.{plus.group(3)}")
        if ligne >= 120 or not (a(dom) ^ a(ext)):
            return ("Basket Total", sens, ligne)
        return ("Basket Points Dom." if a(dom) else "Basket Points Ext.", sens, ligne)
    if "handicap" in t and hand and (a(dom) ^ a(ext)):
        return ("Basket Handicap", "1" if a(dom) else "2", float(hand.group(1).replace(" ", "").replace(",", ".")))
    if a(dom) ^ a(ext):
        return ("Basket Vainqueur", "1" if a(dom) else "2", None)
    return None
