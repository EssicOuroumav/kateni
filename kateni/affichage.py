"""Carte de pronostic d'un match, partagée par les pages Calendrier et Prédictions."""

import pandas as pd
import streamlit as st

from kateni.config import POIDS_MODELE
from kateni.cotes import sans_marge
from kateni.marches import calibrer, marches, matrice_scores, scores_probables
from kateni.modele import terrain_neutre
from kateni.corners import SEUILS_EQUIPE, SEUILS_TOTAL, marches_corners
from kateni.ui import corners_attendus, fr, predire

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


COLS_COTES = ("B365H", "B365D", "B365A", "B365>2.5", "B365<2.5", "bookmaker", "releve")


def pronostic(match: dict, cotes: dict | None = None) -> dict:
    """Probabilités du match. Si les cotes du marché sont publiées : 25 % modèle + 75 % marché
    (+1,5 point de bons pronostics mesuré sur 5 252 matchs de 2025-26). Mis en cache par match."""
    from kateni.donnees import signature_donnees
    c = tuple(None if pd.isna(v) else v for v in ((cotes or {}).get(k) for k in COLS_COTES))
    neutre = match.get("neutre")
    if neutre is None:
        neutre = terrain_neutre(match["competition"], match.get("date") or pd.Timestamp.today())
    return _pronostic(match["competition"], match["dom"], match["ext"], bool(neutre), c, signature_donnees())


@st.cache_data(ttl=3600, max_entries=2000, show_spinner=False)
def _pronostic(competition: str, dom: str, ext: str, neutre: bool, c: tuple, _sig: tuple) -> dict:
    match = {"competition": competition, "dom": dom, "ext": ext, "neutre": neutre}
    cotes = dict(zip(COLS_COTES, c))
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
    releve = (cotes or {}).get("releve")
    if isinstance(releve, str) and releve:
        t = pd.Timestamp(releve)
        bookmaker += f", relevées le {t:%d/%m} à {t:%H:%M}"
    corners = corners_attendus(match)
    if corners:
        p = {**p, **marches_corners(*corners)}
    return {"p": p, "mat": mat, "ld": ld, "le": le, "modele": nom_modele, "neutre": neutre, "corners": corners, "modele_1n2": modele_1n2, "bookmaker": bookmaker,
            "marche_1n2": marche_1n2, "cotes_1n2": (c1, cn, c2), "p1n2": p1n2, "plus25": plus25}


EVENEMENTS = [("1N2", "1"), ("1N2", "N"), ("1N2", "2"),
              ("Double chance", "1N"), ("Double chance", "12"), ("Double chance", "N2"),
              *[(f"Total buts {x}", c) for x in ("0.5", "1.5", "2.5", "3.5", "4.5") for c in ("Plus", "Moins")],
              ("Les deux équipes marquent", "Oui"), ("Les deux équipes marquent", "Non"),
              ("Dom. marque", "Oui"), ("Dom. marque", "Non"), ("Ext. marque", "Oui"), ("Ext. marque", "Non"),
              *[(f"Corners total {x}", c) for x in SEUILS_TOTAL for c in ("Plus", "Moins")],
              *[(f"Corners {e} {x}", c) for e in ("Dom.", "Ext.") for x in SEUILS_EQUIPE for c in ("Plus", "Moins")]]


def chance_evenement(r: dict, marche: str, sel: str) -> float | None:
    """Chance d'un événement, avec les mêmes chiffres que le pronostic affiché (1N2, double chance et
    +/-2,5 buts : modèle + marché quand les cotes existent). None si inconnue (corners d'un club sans données)."""
    q1, qn, q2 = r["p1n2"]
    proba = {("1N2", "1"): q1, ("1N2", "N"): qn, ("1N2", "2"): q2,
             ("Double chance", "1N"): q1 + qn, ("Double chance", "12"): q1 + q2, ("Double chance", "N2"): qn + q2,
             ("Total buts 2.5", "Plus"): r["plus25"], ("Total buts 2.5", "Moins"): 1 - r["plus25"]}
    if (marche, sel) in proba:
        return proba[(marche, sel)]
    return r["p"].get(marche, {}).get(sel)


def evenements(match: dict, r: dict) -> pd.DataFrame:
    """Tous les événements du match, du plus probable au moins probable, avec les mêmes chiffres que le
    pronostic affiché (1N2, double chance et +/-2,5 buts : modèle + marché quand les cotes existent)."""
    from kateni.ui import libelle
    lignes = []
    for marche, sel in EVENEMENTS:
        q = chance_evenement(r, marche, sel)
        if q is None:  # corners inconnus pour ce match
            continue
        lignes.append({"Événement": libelle(marche, sel, match["dom"], match["ext"]), "Chance": q,
                       "Cote juste": 1 / q if q > 0.005 else None})
    return pd.DataFrame(lignes).sort_values("Chance", ascending=False, kind="mergesort").reset_index(drop=True)


COLONNES_EVENEMENTS = {
    "Chance": st.column_config.ProgressColumn("Chance", format="percent", min_value=0, max_value=1),
    "Cote juste": st.column_config.NumberColumn(
        "Cote juste", format="%.2f",
        help="La cote qui correspond exactement à cette chance (1 ÷ chance). Si Betclic propose plus, l'événement "
             "est mieux payé qu'il ne le devrait ; s'il propose moins, il est moins bien payé."),
}


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
            if r["neutre"]:
                st.badge("Terrain neutre", icon=":material/stadium:", color="blue",
                         help="Aucune des deux équipes ne joue chez elle : Kateni retire l'avantage du terrain.")
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
                + (f"- **Corners attendus** : {dom} {fr(r['corners'][0])} – {fr(r['corners'][1])} {ext} "
                   f"(total {fr(sum(r['corners']))}) · plus de 8,5 {p['Corners total 8.5']['Plus']:.0%} · plus de 9,5 "
                   f"{p['Corners total 9.5']['Plus']:.0%} · plus de 10,5 {p['Corners total 10.5']['Plus']:.0%}\n"
                   if r["corners"] else "- **Corners** : pas d'historique de corners pour l'un des deux clubs\n")
                + "- **Scores les plus probables** : "
                + " · ".join(f"{s} ({q:.0%})" for s, q in scores_probables(mat, 5)))
            st.markdown("**Événements, du plus probable au moins probable**")
            st.dataframe(evenements(match, r), hide_index=True, column_config=COLONNES_EVENEMENTS,
                         placeholder="–", height=300)
            st.caption(f"Calcul du modèle : {r['modele']}.")
            if st.button("Comparer avec mes cotes Betclic", key=f"cmp_{cle}", icon=":material/compare_arrows:"):
                st.session_state["match_envoye"] = {k: match[k] for k in ("competition", "dom", "ext", "date")}
                st.switch_page("app_pages/avant_match.py")
