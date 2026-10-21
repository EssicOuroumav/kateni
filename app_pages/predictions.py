import pandas as pd
import streamlit as st

from kateni.config import COMPETITIONS, POIDS_MODELE
from kateni.cotes import sans_marge
from kateni.donnees import equipes_de
from kateni.equipes import canon
from kateni.marches import calibrer, marches, matrice_scores, scores_probables
from kateni.ui import NOMS_COURTS, a_venir, contexte, fr, predire

df, m = contexte()
JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]


def _cote(cotes: dict | None, k: str) -> float | None:
    v = (cotes or {}).get(k)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v > 1 else None


def carte(match: dict, cle: str, cotes: dict | None = None) -> None:
    """Pronostic d'un match. Si les cotes du marché sont publiées, le pronostic mélange le modèle (25 %)
    et le marché (75 %) : +1,5 point de bons pronostics mesuré sur 5 252 matchs de 2025-26."""
    dom, ext = match["dom"], match["ext"]
    ld, le, rho, nom_modele = predire(match)
    mat = matrice_scores(ld, le, rho)
    p = calibrer(marches(mat))
    modele_1n2 = [p["1N2"]["1"], p["1N2"]["N"], p["1N2"]["2"]]
    c1, cn, c2 = _cote(cotes, "B365H"), _cote(cotes, "B365D"), _cote(cotes, "B365A")
    avec_marche = bool(c1 and cn and c2)
    if avec_marche:
        marche_1n2 = sans_marge([c1, cn, c2])[0]
        p1n2 = [POIDS_MODELE * a + (1 - POIDS_MODELE) * b for a, b in zip(modele_1n2, marche_1n2)]
    else:
        p1n2 = modele_1n2
    cp, cm = _cote(cotes, "B365>2.5"), _cote(cotes, "B365<2.5")
    plus25 = p["Total buts 2.5"]["Plus"]
    if cp and cm:
        plus25 = POIDS_MODELE * plus25 + (1 - POIDS_MODELE) * sans_marge([cp, cm])[0][0]
    issues = {f"{dom} gagne": p1n2[0], "Match nul": p1n2[1], f"{ext} gagne": p1n2[2]}
    favori, chance = max(issues.items(), key=lambda x: x[1])
    score, p_score = scores_probables(mat, 1)[0]
    with st.container(border=True):
        quand = match.get("quand", "")
        st.markdown(f"**{dom} – {ext}**" + (f"  ·  {quand}" if quand else ""))
        st.markdown(f"Pronostic : **{favori}** ({chance:.0%})"
                    + ("  ·  match serré" if chance < 0.45 else ""))
        st.caption(f"{dom} {p1n2[0]:.0%} · nul {p1n2[1]:.0%} · {ext} {p1n2[2]:.0%}"
                   f"  —  score le plus probable **{score}** ({p_score:.0%})"
                   f"  —  plus de 2,5 buts {plus25:.0%}"
                   f"  —  les 2 équipes marquent {p['Les deux équipes marquent']['Oui']:.0%}")
        if avec_marche:
            st.badge("Modèle + cotes du marché", icon=":material/insights:", color="green",
                     help="Pronostic = 25 % modèle Kateni + 75 % cotes du marché (Bet365, marge retirée). "
                          "Mesuré sur 5 252 matchs : 50,9 % de bons pronostics contre 49,4 % pour le modèle seul.")
        else:
            st.badge("Modèle seul (cotes pas encore publiées)", icon=":material/functions:", color="gray")
        with st.expander("Détail du pronostic"):
            if avec_marche:
                st.markdown(
                    f"- **Modèle Kateni seul** : {dom} {modele_1n2[0]:.0%} · nul {modele_1n2[1]:.0%} · {ext} "
                    f"{modele_1n2[2]:.0%}\n"
                    f"- **Marché** (Bet365 {fr(c1)} / {fr(cn)} / {fr(c2)}, marge retirée) : {dom} "
                    f"{marche_1n2[0]:.0%} · nul {marche_1n2[1]:.0%} · {ext} {marche_1n2[2]:.0%}")
            st.markdown(
                f"- **Double chance** (modèle) : {dom} ou nul {p['Double chance']['1N']:.0%} · {dom} ou {ext} "
                f"{p['Double chance']['12']:.0%} · nul ou {ext} {p['Double chance']['N2']:.0%}\n"
                f"- **Nombre de buts** (modèle) : plus de 1,5 {p['Total buts 1.5']['Plus']:.0%} · plus de 2,5 "
                f"{p['Total buts 2.5']['Plus']:.0%} · plus de 3,5 {p['Total buts 3.5']['Plus']:.0%}\n"
                f"- **Les 2 équipes marquent** : oui {p['Les deux équipes marquent']['Oui']:.0%} · non "
                f"{p['Les deux équipes marquent']['Non']:.0%}\n"
                f"- **Buts attendus** : {dom} {fr(ld)} – {fr(le)} {ext}\n"
                "- **Scores les plus probables** : "
                + " · ".join(f"{s} ({q:.0%})" for s, q in scores_probables(mat, 5)))
            st.caption(f"Calcul du modèle : {nom_modele}.")
            if st.button("Comparer avec mes cotes Betclic", key=f"cmp_{cle}", icon=":material/compare_arrows:"):
                st.session_state["match_envoye"] = {k: match[k] for k in ("competition", "dom", "ext", "date")}
                st.switch_page("app_pages/avant_match.py")


# ---------------------------------------------------------------- choix du championnat
cal = a_venir()
codes = list(COMPETITIONS)
avec_matchs = set(cal["competition"]) if len(cal) else set()
comp = st.selectbox(
    "Championnat", codes, key="pr_comp",
    format_func=lambda c: NOMS_COURTS.get(c, c) + ("" if c in avec_matchs else "  (pas de match publié)"),
    index=codes.index(next((c for c in codes if c in avec_matchs), codes[0])))

st.subheader("Prochains matchs", anchor=False)
prochains = cal[cal["competition"] == comp] if len(cal) else cal
if not len(prochains):
    st.info("Aucun match à venir publié pour ce championnat pour l'instant. Le calendrier se remplit avant "
            "chaque journée : dans **Mes paris**, clique sur **Mettre à jour les résultats**. En attendant, "
            "utilise **Simuler un match** plus bas.", icon=":material/event_busy:")
for i, r in prochains.head(40).iterrows():
    d = pd.to_datetime(r["Date"])
    match = {"competition": comp, "dom": canon(r["HomeTeam"]), "ext": canon(r["AwayTeam"]),
             "date": r["Date"], "quand": f"{JOURS[d.weekday()]} {d:%d/%m}"
             + (f" · {r['Heure_CET']}" if isinstance(r.get("Heure_CET"), str) else "")}
    carte(match, f"cal_{i}", r.to_dict())

# ---------------------------------------------------------------- simulation libre
st.subheader("Simuler un match", anchor=False)
st.caption("N'importe quelle affiche de ce championnat, même si elle n'est pas au calendrier.")
equipes = equipes_de(df, comp)
c1, c2 = st.columns(2)
dom = c1.selectbox("Équipe à domicile", equipes, key=f"pr_dom_{comp}")
ext = c2.selectbox("Équipe à l'extérieur", [e for e in equipes if e != dom], key=f"pr_ext_{comp}")
carte({"competition": comp, "dom": dom, "ext": ext, "date": pd.Timestamp.today().strftime("%Y-%m-%d")},
      f"libre_{comp}_{dom}_{ext}")
