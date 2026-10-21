"""Règle automatiquement les paris en attente à partir des résultats connus."""

import pandas as pd

from kateni.equipes import canon
from kateni.marches import regler


def resultat(df_matchs: pd.DataFrame, date_match: str, dom: str, ext: str) -> tuple[int, int] | None:
    d = pd.to_datetime(date_match)
    m = df_matchs[(df_matchs["HomeTeam"] == canon(dom)) & (df_matchs["AwayTeam"] == canon(ext))
                  & (df_matchs["Date"].between(d - pd.Timedelta(days=1), d + pd.Timedelta(days=1)))]
    if not len(m):
        return None
    r = m.iloc[-1]
    return int(r.FTHG), int(r.FTAG)


def gagne(pari: dict, buts_d: int, buts_e: int) -> bool | None:
    marche, sel = pari["marche"], pari["selection"]
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
