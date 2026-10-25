"""Règle automatiquement les paris en attente à partir des résultats connus."""

import pandas as pd

from kateni.equipes import canon
from kateni.marches import regler


def resultat(df_matchs: pd.DataFrame, date_match: str, dom: str, ext: str) -> tuple | None:
    """(buts dom, buts ext, corners dom, corners ext, statistiques) ; corners None s'ils ne sont pas publiés,
    statistiques = {« Tirs » : (dom, ext), « Tirs cadrés » : …, « Fautes » : …} pour celles qui sont publiées."""
    d = pd.to_datetime(date_match)
    m = df_matchs[(df_matchs["HomeTeam"] == canon(dom)) & (df_matchs["AwayTeam"] == canon(ext))
                  & (df_matchs["Date"].between(d - pd.Timedelta(days=1), d + pd.Timedelta(days=1)))]
    if not len(m):
        return None
    r = m.iloc[-1]
    hc, ac = pd.to_numeric(pd.Series([r.get("HC"), r.get("AC")]), errors="coerce")
    corners = (None, None) if pd.isna(hc) or pd.isna(ac) else (int(hc), int(ac))
    stats = {}
    for nom, (cd, ce) in {"Tirs": ("HS", "AS"), "Tirs cadrés": ("HST", "AST"), "Fautes": ("HF", "AF")}.items():
        a, b = pd.to_numeric(pd.Series([r.get(cd), r.get(ce)]), errors="coerce")
        if not (pd.isna(a) or pd.isna(b)):
            stats[nom] = (int(a), int(b))
    return int(r.FTHG), int(r.FTAG), *corners, stats


def gagne(pari: dict, buts_d: int, buts_e: int, corners_d: int | None = None,
          corners_e: int | None = None, stats: dict | None = None) -> bool | None:
    marche, sel = pari["marche"], pari["selection"]
    comptes = dict(stats or {})
    if corners_d is not None and corners_e is not None:
        comptes["Corners"] = (corners_d, corners_e)
    for nom in ("Corners", "Tirs cadrés", "Tirs", "Fautes"):  # « Tirs cadrés » avant « Tirs »
        if not marche.startswith(nom + " "):
            continue
        reste = marche[len(nom) + 1:]
        if nom not in comptes:
            return None  # statistique pas encore publiée : réglé à la mise à jour suivante
        d, e = comptes[nom]
        if reste == "plus grand nombre":   # « Plus de corners : Arsenal / égalité / Chelsea »
            return {"1": d > e, "N": d == e, "2": d < e}[sel]
        qui, ligne = reste.split()
        n = {"total": d + e, "Dom.": d, "Ext.": e}[qui]
        return (n > float(ligne)) == (sel == "Plus")
    if marche in ("Dom. marque encore", "Ext. marque encore"):
        avant = str(pari.get("score_au_pari") or "0-0").split("-")
        deja = int(avant[0]) if marche.startswith("Dom") else int(avant[1])
        final = buts_d if marche.startswith("Dom") else buts_e
        return (final > deja) == (sel == "Oui")
    return regler(marche, sel, buts_d, buts_e)  # None pour « Prochain but » : à régler à la main


def regler_tout(store, df_matchs: pd.DataFrame) -> int:
    paris = store.lire()
    n = 0
    for _, p in paris[paris["statut"] == "en attente"].iterrows():
        if p.get("type") == "combiné":
            n += regler_combine(store, p, df_matchs)
            continue
        r = resultat(df_matchs, p["date_match"], p["dom"], p["ext"])
        if r is None:
            continue
        g = gagne(p.to_dict(), *r)
        if g is None:
            continue
        mise = 0.0 if pd.isna(p["mise_fcfa"]) else float(p["mise_fcfa"])
        gain = mise * (float(p["cote"]) - 1) if g else -mise
        store.mettre_a_jour(p["id"], statut="gagné" if g else "perdu",
                            score_final=f"{r[0]}-{r[1]}", gain_fcfa=round(gain))
        n += 1
    return n


def regler_combine(store, p, df_matchs: pd.DataFrame) -> int:
    """Règle les sélections connues d'un combiné ; le combiné est réglé dès qu'une sélection est perdue
    ou quand toutes sont gagnées. Rend 1 si le combiné vient d'être réglé."""
    from kateni.combine import ecrire_selections, lire_selections, statut_combine
    selections = lire_selections(p["selections"])
    change = False
    for s in selections:
        if s.get("statut", "en attente") != "en attente":
            continue
        r = resultat(df_matchs, s["date_match"], s["dom"], s["ext"])
        g = None if r is None else gagne(s, *r)
        if g is not None:
            s["statut"] = "gagné" if g else "perdu"
            s["score_final"] = f"{r[0]}-{r[1]}"
            change = True
    if not change:
        return 0
    statut = statut_combine(selections)
    champs = {"selections": ecrire_selections(selections)}
    if statut != "en attente":
        mise = 0.0 if pd.isna(p["mise_fcfa"]) else float(p["mise_fcfa"])
        champs.update(statut=statut, gain_fcfa=round(mise * (float(p["cote"]) - 1)) if statut == "gagné" else -round(mise))
    store.mettre_a_jour(p["id"], **champs)
    return int(statut != "en attente")
