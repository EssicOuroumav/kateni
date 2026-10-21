"""Carte de pronostic d'un match, partagée par les pages Calendrier et Prédictions."""

import pandas as pd
import streamlit as st

from kateni.config import POIDS_MODELE
from kateni.cotes import sans_marge
from kateni.marches import calibrer, marches, matrice_scores, scores_probables
from kateni.ui import fr, predire

JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
JOURS_LONGS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]


def date_longue(d) -> str:
    d = pd.Timestamp(d)
    return f"{JOURS_LONGS[d.weekday()]} {d.day} {MOIS[d.month - 1]} {d.year}"


def _cote(cotes: dict | None, k: str) -> float | None:
    v = (cotes or {}).get(k)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v > 1 else None


def pronostic(match: dict, cotes: dict | None = None) -> dict:
    """Probabilités du match. Si les cotes du marché sont publiées : 25 % modèle + 75 % marché
    (+1,5 point de bons pronostics mesuré sur 5 252 matchs de 2025-26)."""
    ld, le, rho, nom_modele = predire(match)
    mat = matrice_scores(ld, le, rho)
    p = calibrer(marches(mat))
    modele_1n2 = [p["1N2"]["1"], p["1N2"]["N"], p["1N2"]["2"]]
    c1, cn, c2 = _cote(cotes, "B365H"), _cote(cotes, "B365D"), _cote(cotes, "B365A")
    marche_1n2 = sans_marge([c1, cn, c2])[0] if (c1 and cn and c2) else None
    p1n2 = ([POIDS_MODELE * a + (1 - POIDS_MODELE) * b for a, b in zip(modele_1n2, marche_1n2)]
            if marche_1n2 else modele_1n2)
    plus25 = p["Total buts 2.5"]["Plus"]
    cp, cm = _cote(cotes, "B365>2.5"), _cote(cotes, "B365<2.5")
    if cp and cm:
        plus25 = POIDS_MODELE * plus25 + (1 - POIDS_MODELE) * sans_marge([cp, cm])[0][0]
    bookmaker = (cotes or {}).get("bookmaker")
    bookmaker = bookmaker if isinstance(bookmaker, str) and bookmaker else "Bet365"
    return {"p": p, "mat": mat, "ld": ld, "le": le, "modele": nom_modele, "modele_1n2": modele_1n2, "bookmaker": bookmaker,
            "marche_1n2": marche_1n2, "cotes_1n2": (c1, cn, c2), "p1n2": p1n2, "plus25": plus25}


def carte(match: dict, cle: str, cotes: dict | None = None, compact: bool = False) -> None:
    dom, ext = match["dom"], match["ext"]
    r = pronostic(match, cotes)
    p, mat, p1n2 = r["p"], r["mat"], r["p1n2"]
    issues = {f"{dom} gagne": p1n2[0], "Match nul": p1n2[1], f"{ext} gagne": p1n2[2]}
    favori, chance = max(issues.items(), key=lambda x: x[1])
    score, p_score = scores_probables(mat, 1)[0]
    jours = (pd.to_datetime(match["date"]) - pd.Timestamp.today().normalize()).days
    with st.container(border=True):
        quand = match.get("quand", "")
        st.markdown(f"**{dom} – {ext}**" + (f"  ·  {quand}" if quand else ""))
        st.markdown(f"Pronostic : **{favori}** ({chance:.0%})" + ("  ·  match serré" if chance < 0.45 else "")
                    + f"  ·  score le plus probable **{score}**")
        if not compact:
            st.caption(f"{dom} {p1n2[0]:.0%} · nul {p1n2[1]:.0%} · {ext} {p1n2[2]:.0%}"
                       f"  —  score le plus probable {score} ({p_score:.0%})"
                       f"  —  plus de 2,5 buts {r['plus25']:.0%}"
                       f"  —  les 2 équipes marquent {p['Les deux équipes marquent']['Oui']:.0%}")
        with st.container(horizontal=True):
            if r["marche_1n2"]:
                st.badge("Modèle + cotes du marché", icon=":material/insights:", color="green",
                         help=f"Pronostic = 25 % modèle Kateni + 75 % cotes du marché ({r['bookmaker']}, marge retirée). "
                              "Mesuré sur 5 252 matchs : 50,9 % de bons pronostics contre 49,4 % pour le modèle seul.")
            else:
                st.badge("Modèle seul", icon=":material/functions:", color="gray",
                         help="Les cotes du marché ne sont pas encore publiées (en général 2 à 3 jours avant).")
            if jours > 7:
                st.badge("Provisoire", icon=":material/update:", color="orange",
                         help=f"Match dans {jours} jours : le pronostic est recalculé après chaque journée de "
                              "championnat, puis avec les cotes 2 à 3 jours avant. Le pronostic qui compte est "
                              "celui de la veille.")
        with st.expander("Détail du pronostic"):
            if compact:
                st.markdown(f"**{dom}** {p1n2[0]:.0%} · **nul** {p1n2[1]:.0%} · **{ext}** {p1n2[2]:.0%}")
            if r["marche_1n2"]:
                c1, cn, c2 = r["cotes_1n2"]
                m1, mm = r["modele_1n2"], r["marche_1n2"]
                st.markdown(
                    f"- **Modèle Kateni seul** : {dom} {m1[0]:.0%} · nul {m1[1]:.0%} · {ext} {m1[2]:.0%}\n"
                    f"- **Marché** ({r['bookmaker']} {fr(c1)} / {fr(cn)} / {fr(c2)}, marge retirée) : {dom} "
                    f"{mm[0]:.0%} · nul {mm[1]:.0%} · {ext} {mm[2]:.0%}")
            st.markdown(
                f"- **Double chance** (modèle) : {dom} ou nul {p['Double chance']['1N']:.0%} · {dom} ou {ext} "
                f"{p['Double chance']['12']:.0%} · nul ou {ext} {p['Double chance']['N2']:.0%}\n"
                f"- **Nombre de buts** : plus de 1,5 {p['Total buts 1.5']['Plus']:.0%} · plus de 2,5 "
                f"{r['plus25']:.0%} · plus de 3,5 {p['Total buts 3.5']['Plus']:.0%}\n"
                f"- **Les 2 équipes marquent** : oui {p['Les deux équipes marquent']['Oui']:.0%} · non "
                f"{p['Les deux équipes marquent']['Non']:.0%}\n"
                f"- **Buts attendus** : {dom} {fr(r['ld'])} – {fr(r['le'])} {ext}\n"
                "- **Scores les plus probables** : "
                + " · ".join(f"{s} ({q:.0%})" for s, q in scores_probables(mat, 5)))
            st.caption(f"Calcul du modèle : {r['modele']}.")
            if st.button("Comparer avec mes cotes Betclic", key=f"cmp_{cle}", icon=":material/compare_arrows:"):
                st.session_state["match_envoye"] = {k: match[k] for k in ("competition", "dom", "ext", "date")}
                st.switch_page("app_pages/avant_match.py")
